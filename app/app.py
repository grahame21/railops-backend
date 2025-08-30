# app/app.py
import math, os, re, json, time
from typing import Tuple, Dict, Any, List, Optional

import requests
from flask import Flask, request, jsonify, make_response

app = Flask(__name__)

# --------------------
# Config
# --------------------
TF_BASE = "https://trainfinder.otenko.com"
WARMUP_PATH = "/home/nextlevel"
API_VIEWPORT_PATH = "/Home/GetViewPortData"

VIEW_W = 1024
VIEW_H = 768
TILE_SIZE = 256
MAX_LAT = 85.05112878  # WebMercator clamp

# --------------------
# Utility
# --------------------
def _clamp_lat(lat: float) -> float:
    return max(-MAX_LAT, min(MAX_LAT, lat))

def looks_like_html(resp: requests.Response) -> bool:
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" in ct:
        return True
    head = resp.text.strip()[:20].lower()
    return head.startswith("<!") or head.startswith("<html")

def get_cookie_from_request() -> Optional[str]:
    """
    Accept the .ASPXAUTH in several ways so it's easy to use:
      1) as a cookie on THIS service (name: .ASPXAUTH)
      2) ?cookie=... or ?aspxauth=...
      3) header X-ASPXAUTH: ...
    """
    c = request.cookies.get(".ASPXAUTH")
    if c: return c

    q = request.args.get("cookie") or request.args.get("aspxauth")
    if q: return q

    h = request.headers.get("X-ASPXAUTH")
    if h: return h

    return None

# --------------------
# Web Mercator math (safe; no overflow)
# --------------------
def _latlng_to_pixel(lat: float, lng: float, zoom: int) -> Tuple[float, float]:
    lat = _clamp_lat(lat)
    scale = TILE_SIZE * (2 ** zoom)
    x = (lng + 180.0) / 360.0 * scale
    siny = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * scale
    return x, y

def _pixel_to_latlng(x: float, y: float, zoom: int) -> Tuple[float, float]:
    scale = TILE_SIZE * (2 ** zoom)
    lng = x / scale * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * y / scale
    lat = math.degrees(math.atan(math.sinh(n)))
    return lat, lng

def compute_bounds(lat: float, lng: float, zoom: int, vw: int, vh: int) -> Dict[str, float]:
    cx, cy = _latlng_to_pixel(lat, lng, zoom)
    tlx, tly = cx - vw / 2.0, cy - vh / 2.0
    brx, bry = cx + vw / 2.0, cy + vh / 2.0
    north, west = _pixel_to_latlng(tlx, tly, zoom)
    south, east = _pixel_to_latlng(brx, bry, zoom)
    # return as (compass) bounds
    return {
        "north": float(north),
        "south": float(south),
        "east": float(east),
        "west": float(west),
    }

# --------------------
# HTTP session & token harvesting
# --------------------
def make_session(aspxauth_token: Optional[str]) -> requests.Session:
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
        "Accept": "*/*",
        "Accept-Language": "en-AU,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Referer": TF_BASE + WARMUP_PATH,
    })
    if aspxauth_token:
        # store on TF domain for outbound requests from this server
        sess.cookies.set(".ASPXAUTH", aspxauth_token, domain="trainfinder.otenko.com", path="/")
    return sess

TOKEN_PAGES = [
    "/", "/home", "/Home", "/home/index", "/Home/Index", "/home/nextlevel", WARMUP_PATH
]

def extract_request_verification_token(html: str, cookies: requests.cookies.RequestsCookieJar) -> Optional[str]:
    # Hidden input (ASP.NET & ASP.NET Core)
    m = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', html, re.I)
    if m:
        return m.group(1)
    # Meta variants (some SPA shells)
    m = re.search(r'<meta[^>]+name=["\'](?:csrf-token|xsrf-token)["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    if m:
        return m.group(1)
    # Antiforgery cookies
    for c in cookies:
        name = c.name or ""
        if ("RequestVerificationToken" in name) or name.startswith(".AspNetCore.Antiforgery") or name == "XSRF-TOKEN":
            return c.value
    return None

def probe_token_pages(sess: requests.Session) -> Tuple[Optional[str], Optional[str]]:
    where = None
    token = None
    for path in TOKEN_PAGES:
        try:
            r = sess.get(TF_BASE + path, timeout=20)
            token = extract_request_verification_token(r.text, sess.cookies)
            if token:
                where = path
                break
        except Exception:
            pass
    if not token:
        # try warmup with coords as a last resort
        try:
            r = sess.get(f"{TF_BASE}{WARMUP_PATH}?lat=-33.8688&lng=151.2093&zm=12", timeout=20)
            token = extract_request_verification_token(r.text, sess.cookies)
            if token and not where:
                where = WARMUP_PATH
        except Exception:
            pass
    return token, where

# --------------------
# TF POST attempts
# --------------------
def tf_post_viewport(sess: requests.Session, bounds: Dict[str, float], zm: int, token: Optional[str]):
    url = f"{TF_BASE}{API_VIEWPORT_PATH}"
    attempts = []

    def do_post(form: Dict[str, str]):
        headers = {}
        if token:
            # try the common anti-forgery header names
            headers["RequestVerificationToken"] = token
            headers["X-RequestVerificationToken"] = token
            headers["X-XSRF-TOKEN"] = token
        r = sess.post(url, data=form, headers=headers, timeout=30)
        body = r.text
        htmlish = looks_like_html(r)
        ok_json = (not htmlish) and r.status_code == 200
        emptyish = ok_json and len(body) <= 120 and "null" in body
        return {
            "form": form,
            "resp": {
                "status": r.status_code,
                "bytes": len(r.content),
                "looks_like_html": htmlish,
                "preview": body[:200],
            },
            "is_winner": ok_json and not emptyish
        }

    # 1) bounds with cardinal keys
    attempts.append(do_post({
        "north": f"{bounds['north']:.6f}",
        "south": f"{bounds['south']:.6f}",
        "east":  f"{bounds['east']:.6f}",
        "west":  f"{bounds['west']:.6f}",
        "zoomLevel": str(zm),
    }))
    # 2) bounds with NE/SW keys
    attempts.append(do_post({
        "neLat": f"{bounds['north']:.6f}",
        "neLng": f"{bounds['east']:.6f}",
        "swLat": f"{bounds['south']:.6f}",
        "swLng": f"{bounds['west']:.6f}",
        "zoomLevel": str(zm),
    }))
    # 3) center + zoom
    center_lat = (bounds["north"] + bounds["south"]) / 2.0
    center_lng = (bounds["east"] + bounds["west"]) / 2.0
    attempts.append(do_post({
        "lat": f"{center_lat:.6f}",
        "lng": f"{center_lng:.6f}",
        "zoomLevel": str(zm),
    }))

    winner_idx = next((i for i, a in enumerate(attempts) if a["is_winner"]), None)
    winner = ("none" if winner_idx is None else winner_idx)
    response = attempts[winner_idx]["resp"] if winner_idx is not None else attempts[-1]["resp"]
    return attempts, winner, response

# --------------------
# Routes
# --------------------
@app.get("/authcheck")
def authcheck():
    token = get_cookie_from_request()
    email = request.cookies.get("email") or ""  # optional convenience
    text = json.dumps({"is_logged_in": bool(token), "email_address": email})
    return jsonify({
        "status": 200,
        "ms": None,
        "cookie_present": bool(token),
        "email": email or None,
        "is_logged_in": bool(token),
        "bytes": len(text),
        "text": text
    })

@app.get("/set-aspxauth")
def set_aspxauth():
    """Convenience: call /set-aspxauth?value=PASTE_YOUR_COOKIE to store it as a cookie on THIS service."""
    value = request.args.get("value", "").strip()
    if not value:
        return "Pass ?value=YOUR_.ASPXAUTH", 400
    resp = make_response("OK")
    # Store on OUR domain; we'll read it when calling TF
    resp.set_cookie(".ASPXAUTH", value, httponly=True, secure=True, samesite="Lax", max_age=60*60*24*30)
    return resp

@app.get("/debug/viewport")
def debug_viewport():
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(request.args.get("zm", "12"))

    token_val = get_cookie_from_request()
    sess = make_session(token_val)

    # Find anti-forgery token
    antitoken, token_from = probe_token_pages(sess)

    # Optional warmup fetch (helps prime cookies)
    warm = sess.get(f"{TF_BASE}{WARMUP_PATH}?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", timeout=30)
    bounds = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)
    attempts, winner, response = tf_post_viewport(sess, bounds, zm, antitoken)

    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "bounds": bounds,
        "tf": {
            "used_cookie": bool(token_val),
            "verification_token_present": bool(antitoken),
            "verification_token_from": token_from or "",
            "warmup": {"status": warm.status_code, "bytes": len(warm.content)},
            "viewport": {
                "attempts": attempts,
                "winner": winner,
                "response": response
            }
        }
    })

CITIES = [
    ("Sydney",   -33.8688, 151.2093),
    ("Melbourne",-37.8136, 144.9631),
    ("Brisbane", -27.4698, 153.0251),
    ("Perth",    -31.9523, 115.8613),
    ("Adelaide", -34.9285, 138.6007),
]
ZOOMS = [11, 12, 13]

@app.get("/scan")
def scan():
    token_val = get_cookie_from_request()
    sess = make_session(token_val)

    antitoken, token_from = probe_token_pages(sess)
    out = []
    for city, lat, lng in CITIES:
        for zm in ZOOMS:
            warm = sess.get(f"{TF_BASE}{WARMUP_PATH}?lat={lat:.5f}&lng={lng:.5f}&zm={zm}", timeout=30)
            bounds = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)
            attempts, winner, response = tf_post_viewport(sess, bounds, zm, antitoken)
            out.append({
                "city": city, "lat": lat, "lng": lng, "zm": zm,
                "looks_like_html": response.get("looks_like_html", False),
                "viewport_bytes": response.get("bytes", 0),
                "warmup_bytes": len(warm.content),
                "winner": winner
            })

    return jsonify({
        "count": len(out),
        "verification_token_present": bool(antitoken),
        "verification_token_from": token_from or "",
        "results": out
    })

@app.get("/try")
def try_page():
    return (
        "<h1>RailOps JSON</h1>"
        "<ol>"
        "<li>Set your cookie here once: "
        "<code>/set-aspxauth?value=PASTE_.ASPXAUTH</code></li>"
        "<li>Check: <code>/authcheck</code></li>"
        "<li>Test: <code>/debug/viewport?lat=-33.8688&lng=151.2093&zm=12</code></li>"
        "<li>Scan: <code>/scan</code></li>"
        "</ol>", 200, {"Content-Type": "text/html"}
    )
