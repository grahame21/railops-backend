# app/app.py
import math
import os
import time
import re
from typing import Any, Dict, List, Tuple, Optional

import requests
from flask import Flask, jsonify, request, Response

app = Flask(__name__)

TF_BASE = "https://trainfinder.otenko.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0")

DEFAULT_LAT = -33.8688
DEFAULT_LNG = 151.2093
DEFAULT_ZM  = 12

# Sample scan points and zooms
HOTSPOTS: List[Tuple[str, float, float]] = [
    ("Sydney",   -33.868800, 151.209300),
    ("Melbourne",-37.813600, 144.963100),
    ("Brisbane", -27.469800, 153.025100),
    ("Perth",    -31.952300, 115.861300),
    ("Adelaide", -34.928500, 138.600700),
]
ZOOMS = [11, 12, 13]

VIEW_W, VIEW_H = 1280, 720
TILE_SIZE = 256.0

def _safe_float(s: Any, fallback: float) -> float:
    try:
        return float(s)
    except Exception:
        try:
            # Extract first float-like token if garbage is appended
            m = re.search(r"-?\d+(?:\.\d+)?", str(s))
            return float(m.group(0)) if m else fallback
        except Exception:
            return fallback

def _safe_int(s: Any, fallback: int) -> int:
    try:
        return int(s)
    except Exception:
        # Be tolerant of things like "12https://..." in logs
        m = re.search(r"-?\d+", str(s))
        return int(m.group(0)) if m else fallback

def _new_session(aspx_cookie: Optional[str]) -> requests.Session:
    """Creates a session and optionally injects the .ASPXAUTH cookie.

    Precedence:
      - X-TF-ASPXAUTH header on the inbound request
      - ?cookie= query string on our endpoint
      - TF_AUTH_COOKIE environment variable (Render → Env Vars)
      - function argument (aspx_cookie)
    """
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": UA,
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel?lat={DEFAULT_LAT}&lng={DEFAULT_LNG}&zm={DEFAULT_ZM}",
    })

    header_cookie = request.headers.get("X-TF-ASPXAUTH")
    query_cookie  = request.args.get("cookie")
    env_cookie    = os.getenv("TF_AUTH_COOKIE")
    cookie_value = header_cookie or query_cookie or env_cookie or aspx_cookie

    if cookie_value:
        # domain/path allow the cookie to be sent to trainfinder.otenko.com
        sess.cookies.set(".ASPXAUTH", cookie_value, domain="trainfinder.otenko.com", path="/")
    return sess

def is_logged_in(sess: requests.Session) -> Tuple[bool, str]:
    r = sess.post(f"{TF_BASE}/Home/IsLoggedIn", data=b"", timeout=12)
    text = (r.text or "").strip()
    ok = r.ok and text.lower() in {"true", "1", "ok", "yes"}
    return ok, text

# ---- mercator helpers with overflow guards ----
def _world_to_latlng(x: float, y: float) -> Tuple[float, float]:
    # Clamp world coords to keep exp/sinh well-behaved
    MAX = 3.0e6
    x = max(-MAX, min(MAX, x))
    y = max(-MAX, min(MAX, y))
    # Standard inverse mercator, but use sinh and clamp argument
    n = (math.pi - (2.0 * math.pi * y) / TILE_SIZE)
    n = max(-20.0, min(20.0, n))        # avoid overflow in sinh
    lat = math.degrees(math.atan(math.sinh(n)))
    lng = (x / TILE_SIZE) * 360.0 - 180.0
    return lat, lng

def compute_bounds(lat: float, lng: float, zm: int, w: int, h: int) -> Tuple[float, float, float, float]:
    scale = 2.0 ** zm

    # Forward mercator to "world" coords
    siny = math.sin(math.radians(lat))
    siny = max(min(siny, 0.9999), -0.9999)
    world_y = TILE_SIZE * (0.5 - math.log((1 + siny)/(1 - siny)) / (4 * math.pi))
    world_x = TILE_SIZE * ((lng + 180.0) / 360.0)

    # Viewport corners (in world pixels), then convert back to lat/lng
    tlx = world_x - (w / 2.0); tly = world_y - (h / 2.0)
    brx = world_x + (w / 2.0); bry = world_y + (h / 2.0)
    west, north = _world_to_latlng(tlx / scale * TILE_SIZE, tly / scale * TILE_SIZE)
    east, south = _world_to_latlng(brx / scale * TILE_SIZE, bry / scale * TILE_SIZE)
    return west, south, east, north

def fetch_viewport(sess: requests.Session, lat: float, lng: float, zm: int) -> requests.Response:
    # Many endpoints expect a warmup navigation
    _ = sess.get(f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", timeout=12)
    url = f"{TF_BASE}/Home/GetViewPortData"
    data = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(int(zm))}
    return sess.post(url, data=data, timeout=12)

# ---------------- routes ----------------

@app.get("/healthz")
def healthz():
    return jsonify(ok=True, ts=int(time.time()))

@app.get("/authcheck")
def authcheck():
    sess = _new_session(None)
    ok, raw = is_logged_in(sess)
    return jsonify(ok=ok, raw=raw, cookie_present=(".ASPXAUTH" in sess.cookies.get_dict()))

@app.get("/debug/viewport")
def debug_viewport():
    lat = _safe_float(request.args.get("lat"), DEFAULT_LAT)
    lng = _safe_float(request.args.get("lng"), DEFAULT_LNG)
    zm  = _safe_int(request.args.get("zm"),  DEFAULT_ZM)

    sess = _new_session(None)
    ok, raw = is_logged_in(sess)

    warm = sess.get(f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", timeout=12)
    r = fetch_viewport(sess, lat, lng, zm)
    text = r.text or ""
    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "is_logged_in": ok,
        "is_logged_in_raw": raw,
        "warmup_status": warm.status_code,
        "status": r.status_code,
        "bytes": len(text),
        "preview": text[:200],
    })

@app.get("/proxy/raw")
def proxy_raw():
    lat = _safe_float(request.args.get("lat"), DEFAULT_LAT)
    lng = _safe_float(request.args.get("lng"), DEFAULT_LNG)
    zm  = _safe_int(request.args.get("zm"),  DEFAULT_ZM)
    sess = _new_session(None)
    r = fetch_viewport(sess, lat, lng, zm)
    return Response(response=r.content, status=r.status_code,
                    mimetype=r.headers.get("Content-Type","application/json"))

@app.get("/scan")
def scan():
    sess = _new_session(request.args.get("cookie"))
    coords: List[Tuple[str,float,float]] = []
    if "lat" in request.args and "lng" in request.args:
        coords.append(("caller", _safe_float(request.args["lat"], DEFAULT_LAT),
                                _safe_float(request.args["lng"], DEFAULT_LNG)))
    coords.extend(HOTSPOTS)
    tried = []
    for name, la, ln in coords:
        for z in ZOOMS:
            r = fetch_viewport(sess, la, ln, z)
            text = r.text or ""
            tried.append({"where": name, "lat": la, "lng": ln, "zm": z,
                          "status": r.status_code, "bytes": len(text)})
            if r.ok and len(text) > 150:
                return jsonify({
                    "hit": {"where": name, "lat": la, "lng": ln, "zm": z},
                    "bytes": len(text),
                    "snippet": text[:400],
                })
    return jsonify({"hit": None, "tried": tried})

@app.get("/")
def root():
    return jsonify(
        message="railops-json ready",
        routes=["/healthz",
                "/authcheck",
                "/debug/viewport?lat=&lng=&zm=",
                "/proxy/raw?lat=&lng=&zm=",
                "/scan?lat=&lng=&cookie="]
    )
