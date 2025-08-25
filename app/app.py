import math
import os
import time
from typing import Any, Dict, List, Tuple, Optional

import requests
from flask import Flask, jsonify, request, Response

app = Flask(__name__)

# ------------------------------ Config ---------------------------------

TF_BASE = "https://trainfinder.otenko.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0")

# Default map viewport (Sydney CBD)
DEFAULT_LAT = -33.8688
DEFAULT_LNG = 151.2093
DEFAULT_ZM  = 12

# Known “hot” test spots where the site often has data
HOTSPOTS = [
    ("Tokyo",    35.681236, 139.767125),
    ("Osaka",    34.702485, 135.495951),
    ("Nagoya",   35.170915, 136.881537),
    ("Sapporo",  43.068661, 141.350755),
]

ZOOMS = [11, 12, 13]

VIEW_W, VIEW_H = 1280, 720   # used only for internal bound calc demo (safe now)
TILE_SIZE = 256.0

# ------------------------------ Helpers --------------------------------

def _safe_float(s: Any, fallback: float) -> float:
    try:
        return float(s)
    except Exception:
        return fallback

def _safe_int(s: Any, fallback: int) -> int:
    try:
        return int(str(s).strip())
    except Exception:
        return fallback

def _new_session(aspx_cookie: Optional[str]) -> requests.Session:
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": UA,
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel?lat={DEFAULT_LAT}&lng={DEFAULT_LNG}&zm={DEFAULT_ZM}",
    })
    # Allow both env var and per-request override
    cookie_value = (request.headers.get("X-TF-ASPXAUTH")
                    or request.args.get("cookie")
                    or aspx_cookie)
    if cookie_value:
        # Pin cookie to the proper domain & path
        sess.cookies.set(".ASPXAUTH", cookie_value, domain="trainfinder.otenko.com", path="/")
    return sess

def is_logged_in(sess: requests.Session) -> Tuple[bool, str]:
    """Hit IsLoggedIn exactly as the browser does; return (bool, raw_text)."""
    url = f"{TF_BASE}/Home/IsLoggedIn"
    r = sess.post(url, data=b"")
    text = (r.text or "").strip()
    ok = r.ok and ("true" in text.lower() or text == "True" or text == "1")
    return ok, text

# ------------------------ (Safe) math utilities -------------------------

def _world_to_latlng(x: float, y: float) -> Tuple[float, float]:
    """Inverse Spherical Mercator; clamp to avoid exp overflow."""
    # Clamp to a sane world range
    MAX = 3.0e6
    x = max(-MAX, min(MAX, x))
    y = max(-MAX, min(MAX, y))
    n = (math.pi - (2.0 * math.pi * y) / TILE_SIZE)
    # tanh-identity variant to avoid overflow
    # lat = atan(sinh(n)) in degrees
    sinh_n = math.sinh(max(-20.0, min(20.0, n)))
    lat = math.degrees(math.atan(sinh_n))
    lng = (x / TILE_SIZE) * 360.0 - 180.0
    return lat, lng

def compute_bounds(lat: float, lng: float, zm: int, w: int, h: int) -> Tuple[float,float,float,float]:
    """Demonstrational bounds calc; not sent to TF anymore (TF only needs lat,lng,zm)."""
    scale = 2.0 ** zm
    # Convert center lat/lng to world pixels
    siny = math.sin(math.radians(lat))
    siny = max(min(siny, 0.9999), -0.9999)
    world_y = TILE_SIZE * (0.5 - math.log((1 + siny)/(1 - siny)) / (4 * math.pi))
    world_x = TILE_SIZE * ((lng + 180.0) / 360.0)
    # top-left / bottom-right in world px
    tlx = world_x - (w / 2.0)
    tly = world_y - (h / 2.0)
    brx = world_x + (w / 2.0)
    bry = world_y + (h / 2.0)
    west, north = _world_to_latlng(tlx / scale * TILE_SIZE, tly / scale * TILE_SIZE)
    east, south = _world_to_latlng(brx / scale * TILE_SIZE, bry / scale * TILE_SIZE)
    return west, south, east, north

# --------------------------- TF endpoints -------------------------------

def fetch_viewport(sess: requests.Session, lat: float, lng: float, zm: int) -> requests.Response:
    """
    Replays the site’s XHR. The site currently accepts lat/lng/zm form fields.
    (Don’t guess extra params; the server ignores them and in some cases
     returns ‘null’ fields regardless.)
    """
    url = f"{TF_BASE}/Home/GetViewPortData"
    data = {
        "lat": f"{lat:.6f}",
        "lng": f"{lng:.6f}",
        "zm":  str(int(zm)),
    }
    # Warm up like a browser (the site does this on every pan/zoom)
    _ = sess.get(f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", timeout=12)
    r = sess.post(url, data=data, timeout=12)
    return r

# ----------------------------- Routes ----------------------------------

@app.get("/healthz")
def healthz():
    return jsonify(ok=True, ts=int(time.time()))

@app.get("/authcheck")
def authcheck():
    sess = _new_session(os.getenv("TF_AUTH_COOKIE"))
    ok, raw = is_logged_in(sess)
    return jsonify(ok=ok, raw=raw, cookie_present=(".ASPXAUTH" in sess.cookies.get_dict()))

@app.get("/debug/viewport")
def debug_viewport():
    lat = _safe_float(request.args.get("lat"), DEFAULT_LAT)
    lng = _safe_float(request.args.get("lng"), DEFAULT_LNG)
    zm  = _safe_int(request.args.get("zm"),  DEFAULT_ZM)

    sess = _new_session(os.getenv("TF_AUTH_COOKIE"))
    ok, raw = is_logged_in(sess)
    warm = sess.get(f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", timeout=12)
    r = fetch_viewport(sess, lat, lng, zm)

    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "is_logged_in": ok,
        "is_logged_in_raw": raw,
        "warmup_status": warm.status_code,
        "status": r.status_code,
        "bytes": len(r.content or b""),
        "preview": (r.text[:200] if r.text else ""),
    })

@app.get("/proxy/raw")
def proxy_raw():
    """
    Return the raw TF JSON (helpful to A/B with your browser devtools).
    Pass lat,lng,zm and optional ?cookie=... to override env var.
    """
    lat = _safe_float(request.args.get("lat"), DEFAULT_LAT)
    lng = _safe_float(request.args.get("lng"), DEFAULT_LNG)
    zm  = _safe_int(request.args.get("zm"),  DEFAULT_ZM)

    sess = _new_session(os.getenv("TF_AUTH_COOKIE"))
    r = fetch_viewport(sess, lat, lng, zm)
    # pipe through exactly what TF sent back
    return Response(response=r.content, status=r.status_code, mimetype=r.headers.get("Content-Type","application/json"))

@app.get("/scan")
def scan():
    """
    Try caller coords first (if provided), then several known hot spots, at multiple zooms.
    Returns the first non-empty payload + small summary so your logs don’t just show 'nulls'.
    """
    cookie_override = request.args.get("cookie")
    sess = _new_session(cookie_override or os.getenv("TF_AUTH_COOKIE"))

    # First: whatever the caller asked for
    coords: List[Tuple[str,float,float]] = []
    if "lat" in request.args and "lng" in request.args:
        coords.append(("caller", _safe_float(request.args["lat"], DEFAULT_LAT),
                                _safe_float(request.args["lng"], DEFAULT_LNG)))
    # Then: known hotspots
    coords.extend(HOTSPOTS)

    tried = []
    for name, la, ln in coords:
        for z in ZOOMS:
            r = fetch_viewport(sess, la, ln, z)
            text = (r.text or "")
            payload_len = len(text)
            tried.append({"where": name, "lat": la, "lng": ln, "zm": z, "status": r.status_code, "bytes": payload_len})
            # Most “all-null” replies are tiny (≈98 bytes). If it's bigger, return it.
            if r.ok and payload_len > 150:
                return jsonify({
                    "hit": {"where": name, "lat": la, "lng": ln, "zm": z},
                    "bytes": payload_len,
                    "snippet": text[:400],
                })
    return jsonify({"hit": None, "tried": tried})

@app.get("/")
def root():
    return jsonify(
        message="railops-json ready",
        routes=["/healthz", "/authcheck", "/debug/viewport?lat=&lng=&zm=", "/proxy/raw?lat=&lng=&zm=", "/scan?lat=&lng=&cookie="]
    )
