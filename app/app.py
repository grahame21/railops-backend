# app.py
import os, re, json, math, time
from typing import Dict, Any, Tuple, Optional, List
import requests
from flask import Flask, request, jsonify

# -----------------------------
# Config
# -----------------------------
TF_BASE = "https://trainfinder.otenko.com"
# viewport size to compute bounds (pixels)
VIEW_W = 800
VIEW_H = 600
TILE_SIZE = 256

# -----------------------------
# App
# -----------------------------
app = Flask(__name__)

TOKEN_RE = re.compile(
    r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
    re.IGNORECASE
)

# -----------------------------
# Cookie storage helpers
# -----------------------------
def get_aspxauth() -> Optional[str]:
    v = os.environ.get("ASPXAUTH", "").strip()
    return v or None

def set_aspxauth(v: str) -> None:
    os.environ["ASPXAUTH"] = v.strip()

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "RailOps-JSON/1.0 (+requests)",
        "Accept": "*/*",
    })
    aspx = get_aspxauth()
    if aspx:
        # scope the cookie to the TF domain
        s.cookies.set(".ASPXAUTH", aspx, domain="trainfinder.otenko.com", path="/")
    return s

# -----------------------------
# Map math (Web Mercator)
# -----------------------------
def _latlng_to_world(lat: float, lng: float, scale: float) -> Tuple[float, float]:
    x = (lng + 180.0) / 360.0 * TILE_SIZE * scale
    # clamp latitude to avoid overflow in math functions
    lat = max(min(lat, 85.05112878), -85.05112878)
    siny = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * TILE_SIZE * scale
    return x, y

def _world_to_latlng(x: float, y: float, scale: float) -> Tuple[float, float]:
    lng = x / (TILE_SIZE * scale) * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * y / (TILE_SIZE * scale)
    lat = math.degrees(math.atan(math.sinh(n)))
    return lat, lng

def compute_bounds(lat: float, lng: float, zm: int) -> Dict[str, float]:
    scale = 2.0 ** zm
    cx, cy = _latlng_to_world(lat, lng, scale)
    half_w = VIEW_W / 2.0
    half_h = VIEW_H / 2.0
    tlx, tly = cx - half_w, cy - half_h
    brx, bry = cx + half_w, cy + half_h
    north, west = _world_to_latlng(tlx, tly, scale)
    south, east = _world_to_latlng(brx, bry, scale)
    return {
        "north": round(north, 6),
        "south": round(south, 6),
        "west":  round(west, 6),
        "east":  round(east, 6),
    }

# -----------------------------
# TF fetch (token + viewport)
# -----------------------------
def warmup_and_get_token(sess: requests.Session, lat: float, lng: float, zm: int) -> Tuple[Optional[str], Dict[str, Any]]:
    url = f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    r = sess.get(url, headers={
        "Accept": "text/html, */*;q=0.1",
        "Referer": f"{TF_BASE}/",
    }, timeout=15)
    html = r.text or ""
    m = TOKEN_RE.search(html)
    token = m.group(1) if m else None
    return token, {
        "status": r.status_code,
        "bytes": len(r.content or b""),
        "token_found": bool(token),
    }

def post_viewport(sess: requests.Session, token: Optional[str], lat: float, lng: float, zm: int) -> Dict[str, Any]:
    # Common headers for anti-forgery
    post_headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
    }
    if token:
        # Both header and field—cover both implementations
        post_headers["RequestVerificationToken"] = token

    url = f"{TF_BASE}/Home/GetViewPortData"

    b = compute_bounds(lat, lng, zm)
    attempts: List[Dict[str, Any]] = []

    def send(form: Dict[str, Any]) -> Dict[str, Any]:
        form2 = dict(form)
        if token:
            form2["__RequestVerificationToken"] = token

        r = sess.post(url, data=form2, headers=post_headers, timeout=20)
        txt = r.text or ""
        looks_like_html = "<html" in txt.lower() or "<!doctype html" in txt.lower()
        return {
            "form": form,
            "resp": {
                "status": r.status_code,
                "bytes": len(r.content or b""),
                "looks_like_html": bool(looks_like_html),
                "preview": txt[:200],
            }
        }

    # Try multiple shapes the site might accept
    forms = [
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
        {"east": f"{b['east']:.6f}", "north": f"{b['north']:.6f}", "south": f"{b['south']:.6f}", "west": f"{b['west']:.6f}", "zoomLevel": str(zm)},
        {"neLat": f"{b['north']:.6f}", "neLng": f"{b['east']:.6f}", "swLat": f"{b['south']:.6f}", "swLng": f"{b['west']:.6f}", "zoomLevel": str(zm)},
    ]

    for f in forms:
        attempts.append(send(f))

    # Heuristic "winner": largest non-HTML body
    winner_idx = -1
    best_bytes = -1
    for i, a in enumerate(attempts):
        r = a["resp"]
        if not r["looks_like_html"] and r["status"] == 200 and r["bytes"] > best_bytes:
            best_bytes = r["bytes"]; winner_idx = i

    winner = attempts[winner_idx] if winner_idx >= 0 else None
    return {
        "verification_token_present": bool(token),
        "attempts": attempts,
        "response": winner["resp"] if winner else (attempts[0]["resp"] if attempts else None),
        "winner": winner_idx if winner_idx >= 0 else "none",
    }

# -----------------------------
# Routes
# -----------------------------
@app.get("/set-aspxauth")
def set_cookie_route():
    val = request.args.get("value", "").strip()
    if not val:
        return "Missing ?value=", 400
    set_aspxauth(val)
    return "OK"

@app.get("/authcheck")
def authcheck():
    sess = make_session()
    # simple check endpoint
    url = f"{TF_BASE}/Home/IsLoggedIn"
    r = sess.post(url, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
    txt = r.text
    try:
        data = json.loads(txt)
    except Exception:
        data = {"is_logged_in": False, "email_address": ""}

    return jsonify({
        "status": r.status_code,
        "ms": None,
        "bytes": len(r.content or b""),
        "cookie_present": bool(get_aspxauth()),
        "is_logged_in": bool(data.get("is_logged_in") or data.get("IsLoggedIn")),
        "email": data.get("email_address") or data.get("EmailAddress") or "",
        "text": txt,
    })

@app.get("/debug/viewport")
def debug_viewport():
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
        zm  = int(request.args.get("zm"))
    except Exception:
        return jsonify({"error":"pass ?lat=..&lng=..&zm=.."}), 400

    bounds = compute_bounds(lat, lng, zm)
    sess = make_session()
    token_info = {}
    token, warm = warmup_and_get_token(sess, lat, lng, zm)
    token_info = {"verification_token_present": bool(token)}
    vp = post_viewport(sess, token, lat, lng, zm)

    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "bounds": bounds,
        "tf": {
            "used_cookie": bool(get_aspxauth()),
            "warmup": warm,
            "viewport": vp
        }
    })

@app.get("/scan")
def scan():
    cities = [
        ("Sydney", -33.8688, 151.2093),
        ("Melbourne", -37.8136, 144.9631),
        ("Brisbane", -27.4698, 153.0251),
        ("Perth", -31.9523, 115.8613),
        ("Adelaide", -34.9285, 138.6007),
    ]
    zm_levels = [11, 12, 13]

    results = []
    sess = make_session()
    # Warm once per run (use Sydney for token)
    token, _ = warmup_and_get_token(sess, cities[0][1], cities[0][2], zm_levels[0])

    for city, lat, lng in cities:
        for zm in zm_levels:
            vp = post_viewport(sess, token, lat, lng, zm)
            resp = vp.get("response") or {}
            results.append({
                "city": city, "lat": lat, "lng": lng, "zm": zm,
                "looks_like_html": bool(resp.get("looks_like_html")),
                "viewport_bytes": int(resp.get("bytes") or 0),
                "winner": vp.get("winner"),
            })

    return jsonify({
        "count": len(results),
        "results": results
    })

@app.get("/")
def root():
    return jsonify({
        "name": "RailOps JSON",
        "routes": [
            "Set your cookie here once: /set-aspxauth?value=PASTE_.ASPXAUTH",
            "Check: /authcheck",
            "Test: /debug/viewport?lat=-33.8688&lng=151.2093&zm=12",
            "Scan: /scan",
        ]
    })

# -----------------------------
# Entrypoint (local dev)
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
