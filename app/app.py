# app/app.py
import math
import os
import time
import logging
from typing import Dict, Tuple, Any, Optional

import requests
from flask import Flask, jsonify, request

# ------------------------------------------------------------------------------
# Flask app MUST exist before any decorators run
# ------------------------------------------------------------------------------
app = Flask(__name__)

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s",
)
log = logging.getLogger("railops")

# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
TF_BASE = "https://trainfinder.otenko.com"
TILE_SIZE = 256.0
VIEW_W = int(os.environ.get("VIEW_W", 900))
VIEW_H = int(os.environ.get("VIEW_H", 600))
DEFAULT_LAT = float(os.environ.get("DEFAULT_LAT", -33.8688))   # Sydney
DEFAULT_LNG = float(os.environ.get("DEFAULT_LNG", 151.2093))
DEFAULT_ZM  = int(os.environ.get("DEFAULT_ZM", 12))

HTTP_TIMEOUT = (10, 20)  # connect, read

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36"
)

# ------------------------------------------------------------------------------
# Helpers: numeric parsing (robust)
# ------------------------------------------------------------------------------
def to_float(v: Optional[str], default: float) -> float:
    try:
        x = float(v)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return default

def to_int(v: Optional[str], default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default

# ------------------------------------------------------------------------------
# Web Mercator conversions (no overflow)
# ------------------------------------------------------------------------------
def _latlng_to_world(lat: float, lng: float) -> Tuple[float, float]:
    x = (lng + 180.0) / 360.0 * TILE_SIZE
    siny = math.sin(math.radians(lat))
    siny = min(max(siny, -0.9999), 0.9999)  # clamp
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * TILE_SIZE
    return x, y

def _world_to_latlng(px: float, py: float) -> Tuple[float, float]:
    lng = px / TILE_SIZE * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * (py / TILE_SIZE)
    lat = math.degrees(math.atan(math.sinh(n)))
    return lat, lng

def compute_bounds(lat: float, lng: float, zm: int, vw: int, vh: int) -> Dict[str, float]:
    scale = 2.0 ** zm
    cx, cy = _latlng_to_world(lat, lng)
    cx *= scale; cy *= scale

    tlx = cx - vw / 2.0
    tly = cy - vh / 2.0
    brx = cx + vw / 2.0
    bry = cy + vh / 2.0

    west, north = _world_to_latlng(tlx / scale, tly / scale)
    east, south = _world_to_latlng(brx / scale, bry / scale)

    return {"north": north, "south": south, "west": west, "east": east}

# ------------------------------------------------------------------------------
# HTTP session + auth cookie sourcing
# ------------------------------------------------------------------------------
def _session(auth_cookie: Optional[str]) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8,en-AU;q=0.7",
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel?lat={DEFAULT_LAT}&lng={DEFAULT_LNG}&zm={DEFAULT_ZM}",
        "X-Requested-With": "XMLHttpRequest",
    })
    if auth_cookie:
        s.cookies.set(".ASPXAUTH", auth_cookie, domain="trainfinder.otenko.com", secure=True)
    return s

def _get_auth_cookie_from_request() -> Optional[str]:
    # Priority: custom header, else env var
    hdr = request.headers.get("X-TF-ASPXAUTH")
    if hdr and hdr.strip():
        return hdr.strip()
    env = os.environ.get("TF_AUTH_COOKIE", "").strip()
    return env or None

# ------------------------------------------------------------------------------
# Upstream calls
# ------------------------------------------------------------------------------
def warmup(s: requests.Session, lat: float, lng: float, zm: int) -> Dict[str, Any]:
    url = f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    t0 = time.time()
    r = s.get(url, timeout=HTTP_TIMEOUT)
    dur = time.time() - t0
    info = {"status": r.status_code, "bytes": len(r.content), "ms": int(dur * 1000)}
    log.info(f"Warmup GET {url} -> {r.status_code}; bytes={info['bytes']}")
    return info

def tf_is_logged_in(s: requests.Session) -> Dict[str, Any]:
    url = f"{TF_BASE}/Home/IsLoggedIn"
    t0 = time.time()
    r = s.post(url, data=b"", timeout=HTTP_TIMEOUT)
    dur = time.time() - t0
    text = r.text.strip()
    info = {
        "status": r.status_code,
        "bytes": len(r.content),
        "text": (text[:120] + "…") if len(text) > 120 else text,
        "ms": int(dur * 1000),
    }
    log.info(f"IsLoggedIn -> {r.status_code}; bytes={info['bytes']}")
    return info

def tf_get_viewport_data(s: requests.Session, lat: float, lng: float, zm: int) -> Dict[str, Any]:
    url = f"{TF_BASE}/Home/GetViewPortData"
    form = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}
    t0 = time.time()
    r = s.post(url, data=form, timeout=HTTP_TIMEOUT)
    dur = time.time() - t0
    text = r.text.strip()
    info = {
        "status": r.status_code,
        "bytes": len(r.content),
        "preview": (text[:120] + "…") if len(text) > 120 else text,
        "ms": int(dur * 1000),
    }
    log.info(f"POST GetViewPortData (lat={form['lat']},lng={form['lng']},zm={form['zm']}) -> {r.status_code}; bytes={info['bytes']}; preview={info['preview']!r}")
    return info

def fetch_viewport(lat: float, lng: float, zm: int) -> Dict[str, Any]:
    cookie = _get_auth_cookie_from_request()
    s = _session(cookie)
    warm = warmup(s, lat, lng, zm)
    vp   = tf_get_viewport_data(s, lat, lng, zm)
    return {"warmup": warm, "viewport": vp, "used_cookie": bool(cookie)}

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.get("/authcheck")
def authcheck():
    cookie = _get_auth_cookie_from_request()
    s = _session(cookie)
    info = tf_is_logged_in(s)
    info["logged_in_guess"] = (info["status"] == 200 and ("true" in info["text"].lower() or "logged" in info["text"].lower()))
    info["cookie_present"] = bool(cookie)
    return jsonify(info), 200

@app.get("/debug/viewport")
def debug_viewport():
    lat = to_float(request.args.get("lat"), DEFAULT_LAT)
    lng = to_float(request.args.get("lng"), DEFAULT_LNG)
    zm  = to_int(request.args.get("zm"),  DEFAULT_ZM)

    # safety: zoom bounds
    zm = max(1, min(22, zm))

    bounds = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)
    tf = fetch_viewport(lat, lng, zm)
    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "bounds": bounds,
        "tf": tf,
    }), 200

@app.get("/scan")
def scan():
    # a tiny sweep of AU capitals at a few zooms
    cities = [
        ("Sydney",   -33.8688, 151.2093),
        ("Melbourne",-37.8136, 144.9631),
        ("Brisbane", -27.4698, 153.0251),
        ("Perth",    -31.9523, 115.8613),
        ("Adelaide", -34.9285, 138.6007),
    ]
    zooms = [11, 12, 13]
    results = []
    for name, lat, lng in cities:
        for z in zooms:
            try:
                tf = fetch_viewport(lat, lng, z)
                results.append({
                    "city": name, "lat": lat, "lng": lng, "zm": z,
                    "warmup_bytes": tf["warmup"]["bytes"],
                    "viewport_bytes": tf["viewport"]["bytes"],
                })
            except Exception as ex:
                log.exception("scan error")
                results.append({"city": name, "lat": lat, "lng": lng, "zm": z, "error": str(ex)})
    return jsonify({"count": len(results), "results": results}), 200

@app.get("/")
def root():
    return jsonify({"ok": True, "routes": ["/try", "/authcheck", "/debug/viewport?lat=..&lng=..&zm=..", "/scan"]})

# ------------------------------------------------------------------------------
# Register test UI blueprint (/try)
# ------------------------------------------------------------------------------
from .try_ui import bp as try_ui_bp  # noqa: E402
app.register_blueprint(try_ui_bp)
