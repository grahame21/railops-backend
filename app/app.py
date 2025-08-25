import os, json, time, logging
from flask import Flask, jsonify, request, send_file
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s:railops:%(message)s")
log = logging.getLogger("railops")

TF_ENDPOINT = "https://trainfinder.otenko.com/Home/GetViewPortData"

# ---- Required ENV (set these in Render) --------------------------------------
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "").strip()  # cookie VALUE only (no "TF_ASPXAUTH=" prefix)
TF_REFERER  = os.getenv("TF_REFERER",  "").strip()  # e.g. https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=12
TF_UA       = os.getenv("TF_UA",       "").strip()  # desktop Chrome UA

# sensible defaults if you haven’t set them yet
if not TF_UA:
    TF_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# ------------------------------------------------------------------------------
app = Flask(__name__)

def require_env_ok():
    missing = []
    if not TF_ASPXAUTH: missing.append("TF_ASPXAUTH")
    if not TF_REFERER:  missing.append("TF_REFERER")
    if not TF_UA:       missing.append("TF_UA")
    return missing

def clamp_zoom(z):
    try:
        z = int(z)
    except Exception:
        z = 12
    # Station/vehicle layers often need >= 10–12 to return data
    if z < 10:
        z = 10
    if z > 19:
        z = 19
    return z

def build_headers():
    return {
        "User-Agent": TF_UA,
        "Referer": TF_REFERER,
        "Origin": "https://trainfinder.otenko.com",
        "X-Requested-With": "XMLHttpRequest",
    }

def fetch_viewport(lat: float, lng: float, zm: int, bbox: str | None = None):
    """
    Calls TrainFinder with strict headers + cookie.
    Returns (json_dict, raw_text, status_code)
    """
    s = requests.Session()
    # set cookie properly (VALUE ONLY)
    if TF_ASPXAUTH:
        s.cookies.set("TF_ASPXAUTH", TF_ASPXAUTH, domain="trainfinder.otenko.com", secure=True, httponly=True)

    headers = build_headers()
    data = {
        "lat": f"{lat:.4f}",
        "lng": f"{lng:.4f}",
        "zm":  str(zm),
    }
    # If caller provided a bbox, pass it through exactly as given
    if bbox:
        data["bbox"] = bbox

    log.info("POST %s (form=%s)", TF_ENDPOINT, data)
    r = s.post(TF_ENDPOINT, headers=headers, data=data, timeout=20)
    ct = r.headers.get("content-type","")
    txt = r.text

    if "application/json" in ct.lower():
        try:
            j = r.json()
        except Exception:
            j = None
    else:
        # Sometimes site replies 200 text/html when blocked/unauthorized.
        j = None

    return j, txt, r.status_code


@app.get("/")
def root():
    return jsonify(ok=True, msg="RailOps backend up. Try /trains?lat=-33.86&lng=151.21&zm=12")

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/trains")
def trains():
    """
    Primary endpoint the frontend calls.
    Query params:
      lat, lng, zm  (required-ish; we clamp zoom and default to Sydney if missing)
      bbox          (optional: 'south,west,north,east' decimal degrees)
    """
    missing_env = require_env_ok()
    if missing_env:
        return jsonify(
            ok=False,
            error="missing_env",
            missing=missing_env,
            hint="Set these environment variables on Render."
        ), 500

    try:
        lat = float(request.args.get("lat", "-33.86"))
        lng = float(request.args.get("lng", "151.21"))
    except Exception:
        lat, lng = -33.86, 151.21

    zm = clamp_zoom(request.args.get("zm","12"))
    bbox = request.args.get("bbox")  # passthrough if provided

    # Warmup GET (helps some ASP.NET stacks validate Referer)
    try:
        warmup = requests.get(
            TF_REFERER,
            headers={"User-Agent": TF_UA, "Referer": TF_REFERER},
            timeout=10
        )
        log.info("Warmup GET %s -> %s", TF_REFERER, warmup.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

    j, txt, code = fetch_viewport(lat, lng, zm, bbox)

    if code != 200:
        log.warning("TrainFinder non-200: %s", code)
        return jsonify(ok=False, status=code, error="upstream_error"), 502

    if not j or all(j.get(k) is None for k in ["favs","alerts","places","tts","webcams","atcsGomi","atcsObj"]):
        log.warning("TrainFinder payload looks empty/unauthorized.")
        return jsonify(
            ok=False,
            status=200,
            error="empty_or_unauthorized",
            hint="Check TF_ASPXAUTH cookie value, TF_REFERER URL (with lat,lng,zm), and TF_UA.",
            sample_keys=(list(j.keys()) if isinstance(j, dict) else [])
        ), 200

    # Convert whatever TrainFinder gives us into a flat "trains" list if present.
    # If the data model differs, tweak here.
    trains = []
    # Common place: 'tts' or 'atcsObj' might carry active trains/telemetry
    for bucket in ("tts", "atcsObj"):
        if isinstance(j.get(bucket), list):
            for item in j[bucket]:
                # Try common fields with safe fallbacks
                trains.append({
                    "id": item.get("id") or item.get("trainId") or item.get("tid"),
                    "lat": item.get("lat") or item.get("y") or item.get("Lat"),
                    "lng": item.get("lng") or item.get("x") or item.get("Lng"),
                    "ts":  item.get("ts")  or item.get("timestamp"),
                    "raw": item,
                })

    return jsonify(ok=True, count=len(trains), trains=trains, raw=j)


@app.get("/debug/echo-env")
def echo_env():
    """Quick way to verify the backend sees the env you set on Render."""
    masked = TF_ASPXAUTH[:4] + "..." + TF_ASPXAUTH[-4:] if TF_ASPXAUTH and len(TF_ASPXAUTH) > 8 else TF_ASPXAUTH
    return jsonify(
        TF_ASPXAUTH_masked=masked,
        TF_REFERER=TF_REFERER,
        TF_UA=TF_UA[:50] + ("..." if len(TF_UA) > 50 else "")
    )

@app.get("/debug/raw")
def debug_raw():
    """Returns the raw upstream response text so you can see if it’s HTML (blocked) or JSON."""
    lat = float(request.args.get("lat", "-33.86"))
    lng = float(request.args.get("lng", "151.21"))
    zm = clamp_zoom(request.args.get("zm","12"))
    j, txt, code = fetch_viewport(lat, lng, zm, request.args.get("bbox"))
    return (txt, code, {"Content-Type": "text/plain; charset=utf-8"})
