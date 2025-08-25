# app/app.py
import os
import re
import logging
from flask import Flask, request, jsonify
import requests

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
log = logging.getLogger("railops")

# -----------------------------------------------------------------------------
# Flask app (Gunicorn looks for `app` in module `app`)
# -----------------------------------------------------------------------------
app = Flask(__name__)

# -----------------------------------------------------------------------------
# External site configuration (env-driven)
# -----------------------------------------------------------------------------
TF_HOST = "trainfinder.otenko.com"
TF_BASE = f"https://{TF_HOST}"
TF_ASPXAUTH = os.environ.get("TF_ASPXAUTH", "").strip()

# Desktop-ish UA is safest unless you set TF_UA yourself
TF_UA = os.environ.get(
    "TF_UA",
    # Chrome on Windows 10, generic and stable
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
).strip()

# Keep one session for connection reuse and cookie handling
S = requests.Session()
S.headers.update({"User-Agent": TF_UA})

# If we have an auth cookie, attach it to this domain
if TF_ASPXAUTH:
    # Name is typical for ASP.NET auth cookie (may be ".ASPXAUTH")
    S.cookies.set(".ASPXAUTH", TF_ASPXAUTH, domain=TF_HOST)
    log.info("ASPXAUTH cookie set for %s", TF_HOST)
else:
    log.warning("TF_ASPXAUTH not set; responses may be limited or empty.")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def nextlevel_url(lat: float, lng: float, zm: int) -> str:
    # This is the URL they build in their app when viewing the map
    return f"{TF_BASE}/home/nextlevel?lat={lat:.5f}&lng={lng:.5f}&zm={zm}"

def sanitize_url_like(s: str) -> str:
    """Extract the first URL-like token so `requests` won't reject it."""
    m = re.search(r"https?://\S+", s or "")
    return m.group(0) if m else s

def build_headers(lat: float, lng: float, zm: int) -> dict:
    referer = sanitize_url_like(nextlevel_url(lat, lng, zm))
    return {
        "User-Agent": TF_UA,
        "Referer": referer,
        "Origin": TF_BASE,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

def bbox_from_center_zoom(lat: float, lng: float, zm: int):
    """
    Simple heuristic: viewport width shrinks by powers of 2 as zoom increases.
    Adjust height by latitude so tiles look reasonable at higher latitudes.
    """
    base_width_deg = 40.0
    width = base_width_deg / (2 ** max(zm, 0))
    height = width * max(0.6, abs(lat) / 90.0 + 0.1)
    swlat, swlng = lat - height / 2.0, lng - width / 2.0
    nelat, nelng = lat + height / 2.0, lng + width / 2.0
    return swlat, swlng, nelat, nelng

def tf_post(form: dict, lat: float, lng: float, zm: int):
    """
    POST to TrainFinder with proper headers. Returns (json, status_code) tuple.
    """
    url = f"{TF_BASE}/Home/GetViewPortData"
    headers = build_headers(lat, lng, zm)
    try:
        r = S.post(url, headers=headers, data=form, timeout=20)
    except requests.RequestException as e:
        log.exception("POST %s failed: %s", url, e)
        return {"error": f"upstream request failed: {e.__class__.__name__}"}, 502

    ct = r.headers.get("content-type", "")
    if r.status_code != 200:
        log.warning("Upstream non-200 (%s): %s", r.status_code, r.text[:300])
        return {"error": "upstream non-200", "status": r.status_code, "body": r.text}, 502

    # Defensive JSON handling
    try:
        data = r.json()
    except ValueError:
        log.warning("Upstream non-JSON content-type=%s body=%r", ct, r.text[:300])
        return {"error": "upstream non-json", "body": r.text}, 502

    # Quick visibility in logs
    if isinstance(data, dict):
        log.info("Sample JSON keys: %s", list(data.keys())[:8])
    else:
        log.info("Upstream returned %s items", len(data) if isinstance(data, list) else type(data).__name__)
    return data, 200

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
def root():
    # Keep the same feel you've been using: "ok, true"
    return "ok, true", 200, {"Content-Type": "text/plain; charset=utf-8"}

@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "ua": TF_UA[:80] + ("…" if len(TF_UA) > 80 else "")})

@app.get("/trains")
def trains():
    """
    Query TrainFinder using an explicit bounding box plus current center/zoom.
    Required query params:
      swlat, swlng, nelat, nelng, lat, lng
    Optional:
      zm (int, default 10)
    """
    swlat = request.args.get("swlat", type=float)
    swlng = request.args.get("swlng", type=float)
    nelat = request.args.get("nelat", type=float)
    nelng = request.args.get("nelng", type=float)
    lat   = request.args.get("lat", type=float)
    lng   = request.args.get("lng", type=float)
    zm    = request.args.get("zm",  type=int, default=10)

    missing = [k for k, v in [
        ("swlat", swlat), ("swlng", swlng),
        ("nelat", nelat), ("nelng", nelng),
        ("lat", lat), ("lng", lng),
    ] if v is None]
    if missing:
        return jsonify({"error": "missing parameters", "missing": missing}), 400

    form = {
        "lat":  f"{lat:.5f}",
        "lng":  f"{lng:.5f}",
        "zm":   str(zm),
        "bbox": f"{swlat:.5f},{swlng:.5f},{nelat:.5f},{nelng:.5f}",
    }
    log.info(
        "POST %s (lat=%s,lng=%s,zm=%s,bbox=%s)",
        "/Home/GetViewPortData", form["lat"], form["lng"], form["zm"], form["bbox"]
    )

    data, status = tf_post(form, lat, lng, zm)
    return jsonify(data), status

@app.get("/trains_by_center")
def trains_by_center():
    """
    Query TrainFinder with only center (lat,lng) and zoom (z
