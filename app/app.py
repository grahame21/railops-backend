import os, re, math, time
from typing import Dict, Any, Optional, Tuple
import requests
from flask import Flask, request, jsonify, make_response

# --------------------
# Config
# --------------------
TF_BASE = "https://trainfinder.otenko.com"
DEFAULT_UA = os.getenv("UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0")
VIEW_W = 1024
VIEW_H = 768
TILE_SIZE = 256

# In-memory store for your ASPXAUTH (persists only while the container is alive)
ASPXAUTH_VALUE: Optional[str] = os.getenv("ASPXAUTH") or None

app = Flask(__name__)

# --------------------
# Helpers
# --------------------
def _make_session(aspxauth: Optional[str]) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": DEFAULT_UA,
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
    })
    # Attach .ASPXAUTH if we have it
    if aspxauth:
        c = requests.cookies.create_cookie(
            domain="trainfinder.otenko.com",
            name=".ASPXAUTH",
            value=aspxauth,
            path="/",
            secure=True,
            rest={"HttpOnly": True}
        )
        s.cookies.set_cookie(c)
    return s

def _looks_like_html(text: str, content_type: str = "") -> bool:
    if content_type and "html" in content_type.lower():
        return True
    t = text.strip().lower()
    return t.startswith("<!doctype") or t.startswith("<html")

def _preview(b: bytes, limit=180) -> str:
    try:
        t = b.decode("utf-8", "replace")
    except Exception:
        t = repr(b[:limit])
    return t[:limit]

# Web Mercator math (safe; no overflow)
def _latlng_to_pixel(lat: float, lng: float, zoom: int) -> Tuple[float, float]:
    scale = TILE_SIZE * (2 ** zoom)
    x = (lng + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y

def _pixel_to_latlng(px: float, py: float, zoom: int) -> Tuple[float, float]:
    scale = TILE_SIZE * (2 ** zoom)
    lng = px / scale * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * (py / scale)
    lat = math.degrees(math.atan(math.sinh(n)))
    return lat, lng

def compute_bounds(lat: float, lng: float, zm: int, w: int, h: int) -> Dict[str, float]:
    cx, cy = _latlng_to_pixel(lat, lng, zm)
    tlx, tly = cx - w / 2.0, cy - h / 2.0
    brx, bry = cx + w / 2.0, cy + h / 2.0

    tl_lat, tl_lng = _pixel_to_latlng(tlx, tly, zm)
    br_lat, br_lng = _pixel_to_latlng(brx, bry, zm)

    north = max(tl_lat, br_lat)
    south = min(tl_lat, br_lat)
    west  = min(tl_lng, br_lng)
    east  = max(tl_lng, br_lng)
    return {"north": north, "south": south, "west": west, "east": east}

def _warmup_and_get_token(s: requests.Session, lat: float, lng: float, zm: int) -> Dict[str, Any]:
    url = f"{TF_BASE}/home/nextlevel"
    params = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}
    r = s.get(url, params=params, headers={
        "Referer": f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
        "Origin": TF_BASE
    }, timeout=20)
    html = r.text
    token = None

    # Typical ASP.NET AntiForgery hidden input
    m = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', html, re.I)
    if m:
        token = m.group(1)

    # Some apps accept header "RequestVerificationToken: <value>" when the cookie with same name exists.
    token_cookie = s.cookies.get("__RequestVerificationToken")

    return {
        "status": r.status_code,
        "bytes": len(r.content),
        "token": token,
        "token_cookie_present": token_cookie is not None
    }

def _post_viewport(s: requests.Session, payload: Dict[str, str], token: Optional[str], lat: float, lng: float, zm: int) -> Dict[str, Any]:
    url = f"{TF_BASE}/Home/GetViewPortData"
    headers = {
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
        "X-Requested-With": "XMLHttpRequest"
    }
    if token:
        # Header name most commonly used by ASP.NET AntiForgery for AJAX
        headers["RequestVerificationToken"] = token

    r = s.post(url, data=payload, headers=headers, timeout=20)
    content_type = r.headers.get("content-type", "")
    body = r.content
    return {
        "status": r.status_code,
        "bytes": len(body),
        "looks_like_html": _looks_like_html(body.decode("utf-8", "replace"), content_type),
        "preview": _preview(body)
    }

def _try_all_forms(s: requests.Session, lat: float, lng: float, zm: int, token: Optional[str]) -> Dict[str, Any]:
    attempts = []
    winner = None

    # A) center + zm
    attempts.append({
        "form": {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
    })

    # B) bounds + zm
    b = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)
    attempts.append({
        "form": {
            "east": f"{b['east']:.6f}",
            "north": f"{b['north']:.6f}",
            "south": f"{b['south']:.6f}",
            "west": f"{b['west']:.6f}",
            "zoomLevel": str(zm),
        }
    })

    # C) NE/SW + zm
    attempts.append({
        "form": {
            "neLat": f"{b['north']:.6f}",
            "neLng": f"{b['east']:.6f}",
            "swLat": f"{b['south']:.6f}",
            "swLng": f"{b['west']:.6f}",
            "zoomLevel": str(zm),
        }
    })

    # Execute
    for i, a in enumerate(attempts):
        resp = _post_viewport(s, a["form"], token, lat, lng, zm)
        a["resp"] = resp
        # Heuristic: valid JSON with > 300 bytes probably means data showed up
        if resp["status"] == 200 and not resp["looks_like_html"] and resp["bytes"] > 300:
            winner = i
            break

    # If none large enough, pick the largest anyway for debugging
    if winner is None:
        best_i = max(range(len(attempts)), key=lambda j: attempts[j]["resp"]["bytes"])
        # only mark as winner if it's meaningfully different from the 98-byte empty JSON
        if attempts[best_i]["resp"]["bytes"] > 98:
            winner = best_i

    out = {
        "attempts": attempts,
        "winner": "none" if winner is None else winner,
        "response": attempts[winner]["resp"] if winner is not None else attempts[0]["resp"]
    }
    return out

def _check_login(s: requests.Session) -> Dict[str, Any]:
    url = f"{TF_BASE}/Home/IsLoggedIn"
    r = s.post(url, headers={
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel",
        "X-Requested-With": "XMLHttpRequest"
    }, timeout=15)
    text = r.text
    is_html = _looks_like_html(text, r.headers.get("content-type", ""))
    email = ""
    is_logged_in = False
    try:
        # expected: {"is_logged_in":true,"email_address":"..."}
        m1 = re.search(r'"is_logged_in"\s*:\s*(true|false)', text)
        m2 = re.search(r'"email_address"\s*:\s*"([^"]*)"', text)
        if m1: is_logged_in = (m1.group(1) == "true")
        if m2: email = m2.group(1)
    except Exception:
        pass
    return {
        "status": r.status_code,
        "bytes": len(r.content),
        "text": text if len(text) < 400 else text[:400],
        "looks_like_html": is_html,
        "is_logged_in": is_logged_in,
        "email": email,
        "cookie_present": (s.cookies.get(".ASPXAUTH") is not None)
    }

# --------------------
# Routes
# --------------------
@app.get("/")
def root():
    return jsonify({
        "name": "RailOps JSON",
        "endpoints": {
            "set cookie once": "/set-aspxauth?value=PASTE_.ASPXAUTH_VALUE_ONLY",
            "check": "/authcheck",
            "test": "/debug/viewport?lat=-33.8688&lng=151.2093&zm=12",
            "scan": "/scan"
        }
    })

@app.get("/set-aspxauth")
def set_aspxauth():
    global ASPXAUTH_VALUE
    v = request.args.get("value", "").strip()
    if not v:
        return make_response("Missing ?value=<ASPXAUTH>", 400)
    # Accept raw ".ASPXAUTH=...." or just the value
    if v.startswith(".ASPXAUTH="):
        v = v.split("=", 1)[1]
    ASPXAUTH_VALUE = v
    return jsonify({"ok": True, "stored": len(v) > 0, "length": len(v)})

@app.get("/authcheck")
def authcheck():
    # Allow quick override via ?aspxauth=... for testing, else use stored
    raw = request.args.get("aspxauth")
    aspx = (raw.split("=",1)[1] if (raw and raw.startswith(".ASPXAUTH=")) else raw) if raw else ASPXAUTH_VALUE
    s = _make_session(aspx)
    t0 = time.time()
    res = _check_login(s)
    ms = int((time.time() - t0) * 1000)
    out = {
        "status": res["status"],
        "ms": ms,
        "cookie_present": res["cookie_present"],
        "is_logged_in": res["is_logged_in"],
        "email": res["email"],
        "bytes": res["bytes"],
        "text": res["text"]
    }
    return jsonify(out)

@app.get("/debug/viewport")
def debug_viewport():
    # Inputs
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(request.args.get("zm", "12"))

    # Optional inline cookie override
    raw = request.args.get("aspxauth")
    aspx = (raw.split("=",1)[1] if (raw and raw.startswith(".ASPXAUTH=")) else raw) if raw else ASPXAUTH_VALUE

    s = _make_session(aspx)

    warm = _warmup_and_get_token(s, lat, lng, zm)
    token = warm.get("token")

    tf = _try_all_forms(s, lat, lng, zm, token)

    bounds = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)
    out = {
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "bounds": {k: round(v, 6) for k, v in bounds.items()},
        "tf": {
            "used_cookie": bool(aspx),
            "verification_token_present": bool(token),
            "warmup": {"status": warm["status"], "bytes": warm["bytes"], "token_cookie_found": warm["token_cookie_present"]},
            "viewport": tf
        }
    }
    return jsonify(out)

@app.get("/scan")
def scan():
    points = [
        ("Sydney",   -33.8688, 151.2093),
        ("Melbourne",-37.8136, 144.9631),
        ("Brisbane", -27.4698, 153.0251),
        ("Perth",    -31.9523, 115.8613),
        ("Adelaide", -34.9285, 138.6007),
    ]
    zms = [11,12,13]
    raw = request.args.get("aspxauth")
    aspx = (raw.split("=",1)[1] if (raw and raw.startswith(".ASPXAUTH=")) else raw) if raw else ASPXAUTH_VALUE

    results = []
    s = _make_session(aspx)
    for city, lat, lng in points:
        warm = _warmup_and_get_token(s, lat, lng, 12)
        token = warm.get("token")
        for zm in zms:
            tf = _try_all_forms(s, lat, lng, zm, token)
            results.append({
                "city": city, "lat": lat, "lng": lng, "zm": zm,
                "viewport_bytes": tf["response"]["bytes"],
                "looks_like_html": tf["response"]["looks_like_html"],
                "winner": tf["winner"],
                "warmup_bytes": warm["bytes"],
            })
    return jsonify({"count": len(results), "results": results})
