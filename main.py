import os, json, time, logging
from typing import Tuple, Dict, Any, List, Optional

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

log = logging.getLogger("railops")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:railops:%(message)s")

# ------------------ Config (env) ------------------
TRAINFINDER_BASE = "https://trainfinder.otenko.com"
VIEW_URL = f"{TRAINFINDER_BASE}/home/nextlevel"
API_URL  = f"{TRAINFINDER_BASE}/Home/GetViewPortData"

TF_ASPXAUTH   = os.getenv("TF_ASPXAUTH", "").strip()  # REQUIRED
TF_SESSION    = os.getenv("TF_SESSION", "").strip()   # optional: ASP.NET_SessionId
TF_AUTH2      = os.getenv("TF_AUTH2", "").strip()     # optional: any extra cookie name/value
TF_EXTRA_COOKIES = os.getenv("TF_EXTRA_COOKIES", "").strip()  # optional: raw "k=v; k2=v2"

TF_UA      = os.getenv("TF_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")
TF_REFERER = os.getenv("TF_REFERER", "")  # if blank, built from lat/lng/zm

DEFAULT_LAT = float(os.getenv("TF_DEFAULT_LAT", "-33.8688"))
DEFAULT_LNG = float(os.getenv("TF_DEFAULT_LNG", "151.2093"))
DEFAULT_ZM  = int(float(os.getenv("TF_DEFAULT_ZM", "10")))

# ------------------ Helpers ------------------
def build_referer(lat: float, lng: float, zm: int) -> str:
    return TF_REFERER or f"{VIEW_URL}?lat={lat:.4f}&lng={lng:.4f}&zm={zm}"

def extract_markers(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def add(lat, lng, name=""):
        try:
            lat = float(lat); lng = float(lng)
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                out.append({"lat": lat, "lng": lng, "name": str(name or "")})
        except Exception:
            pass

    if not isinstance(payload, dict):
        return out

    # Common shapes encountered:
    atcs = payload.get("atcsObj")
    if isinstance(atcs, dict):
        for k, v in atcs.items():
            if isinstance(v, dict):
                lat = v.get("Lat") or v.get("lat")
                lng = v.get("Lng") or v.get("lng")
                name = v.get("Name") or v.get("name") or k
                if lat is not None and lng is not None:
                    add(lat, lng, name)

    tts = payload.get("tts")
    if isinstance(tts, list):
        for v in tts:
            if isinstance(v, dict):
                lat = v.get("lat") or v.get("Lat")
                lng = v.get("lng") or v.get("Lng")
                name = v.get("name") or v.get("Name") or v.get("id") or ""
                if lat is not None and lng is not None:
                    add(lat, lng, name)

    places = payload.get("places")
    if isinstance(places, list):
        for v in places:
            if isinstance(v, dict):
                lat = v.get("lat") or v.get("Lat")
                lng = v.get("lng") or v.get("Lng")
                name = v.get("name") or v.get("Name") or ""
                if lat is not None and lng is not None:
                    add(lat, lng, name)

    return out

def _apply_cookies(session: requests.Session):
    # Minimal required cookie:
    if TF_ASPXAUTH:
        session.cookies.set("TF_ASPXAUTH", TF_ASPXAUTH, domain="trainfinder.otenko.com", path="/", secure=True)
    # Optional cookies that sometimes matter:
    if TF_SESSION:
        session.cookies.set("ASP.NET_SessionId", TF_SESSION, domain="trainfinder.otenko.com", path="/", secure=True)
    if TF_AUTH2:
        # Expect TF_AUTH2 like "SomeCookie=abc123"
        try:
            name, val = TF_AUTH2.split("=", 1)
            session.cookies.set(name.strip(), val.strip(), domain="trainfinder.otenko.com", path="/", secure=True)
        except Exception:
            pass
    if TF_EXTRA_COOKIES:
        # Format: "k1=v1; k2=v2"
        for pair in TF_EXTRA_COOKIES.split(";"):
            if "=" in pair:
                name, val = pair.split("=", 1)
                session.cookies.set(name.strip(), val.strip(), domain="trainfinder.otenko.com", path="/", secure=True)

def fetch_viewport(lat: float, lng: float, zm: int, bbox: Optional[str]) -> Tuple[Optional[Dict[str, Any]], str, int, Dict[str, Any]]:
    if not TF_ASPXAUTH:
        return None, "TF_ASPXAUTH not set", 401, {"reason":"missing_cookie"}

    s = requests.Session()
    _apply_cookies(s)

    referer = build_referer(lat, lng, zm)
    # Headers that mimic browser XHR
    headers = {
        "User-Agent": TF_UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": TRAINFINDER_BASE,
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
    }

    warm_status = None
    try:
        warm = s.get(referer, headers={"User-Agent": TF_UA, "Referer": TRAINFINDER_BASE}, timeout=12)
        warm_status = warm.status_code
        log.info("Warmup GET %s -> %s", warm.url, warm.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

    form = {"lat": f"{lat:.5f}", "lng": f"{lng:.5f}", "zm": str(zm)}
    if bbox:
        form["bbox"] = bbox

    try:
        r = s.post(API_URL, data=form, headers=headers, timeout=15)
        log.info("POST %s -> %s", API_URL, r.status_code)
        text = r.text
        if r.status_code != 200:
            return None, text, r.status_code, {"warmup_status": warm_status, "referer": referer}

        try:
            j = r.json()
        except Exception:
            j = None

        return j, text, r.status_code, {"warmup_status": warm_status, "referer": referer}
    except Exception as e:
        return None, f"request error: {e}", 502, {"warmup_status": warm_status, "referer": referer}

# ------------------ Routes ------------------
@app.get("/")
def root():
    return jsonify(ok=True, service="railops-json", time=int(time.time()))

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/trains")
def trains():
    """
    Query: lat,lng,zm,bbox
    Response: { ok, markers:[{lat,lng,name}], meta:{...} }
    """
    try:
        lat = float(request.args.get("lat", DEFAULT_LAT))
        lng = float(request.args.get("lng", DEFAULT_LNG))
        zm  = int(float(request.args.get("zm", DEFAULT_ZM)))
    except Exception:
        lat, lng, zm = DEFAULT_LAT, DEFAULT_LNG, DEFAULT_ZM
    bbox = request.args.get("bbox")

    j, txt, code, meta = fetch_viewport(lat, lng, zm, bbox)

    if code != 200 or j is None or not isinstance(j, dict):
        sample = (txt or "")[:400]
        log.warning("TrainFinder payload looks empty/unauthorized.")
        return jsonify(ok=False,
                       message="TrainFinder payload looks empty/unauthorized.",
                       meta={"http_status": code, "sample": sample, **(meta or {})}), 200

    markers = extract_markers(j)

    try:
        with open("/app/trains.json", "w") as f:
            json.dump({"ts": int(time.time()), "markers": markers}, f)
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "markers": markers,
        "meta": {
            "count": len(markers),
            "source_keys": list(j.keys()),
            **(meta or {})
        }
    }), 200
