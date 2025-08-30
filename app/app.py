import os, re, json, math
from typing import Dict, Any, Tuple, Optional, List
import requests
from flask import Flask, request, jsonify

TF_BASE = "https://trainfinder.otenko.com"

# Viewport math constants
VIEW_W = 800
VIEW_H = 600
TILE_SIZE = 256

app = Flask(__name__)

# Regexes to catch the token regardless of attribute order/quotes
TOKEN_PATTERNS = [
    r'name=[\'"]__RequestVerificationToken[\'"][^>]*value=[\'"]([^\'"]+)[\'"]',
    r'value=[\'"]([^\'"]+)[\'"][^>]*name=[\'"]__RequestVerificationToken[\'"]',
    r'id=[\'"]__RequestVerificationToken[\'"][^>]*value=[\'"]([^\'"]+)[\'"]',
    r'name=[\'"]__RequestVerificationToken[\'"][^>]*content=[\'"]([^\'"]+)[\'"]',
]

def get_aspxauth() -> Optional[str]:
    v = os.environ.get("ASPXAUTH", "").strip()
    return v or None

def set_aspxauth(v: str) -> None:
    os.environ["ASPXAUTH"] = v.strip()

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "RailOps-JSON/1.0",
        "Accept": "*/*",
    })
    token = get_aspxauth()
    if token:
        # scope auth cookie to TF domain so it is sent to TF
        s.cookies.set(".ASPXAUTH", token, domain="trainfinder.otenko.com", path="/")
    return s

# ---------- Web Mercator helpers ----------
def _latlng_to_world(lat: float, lng: float, scale: float) -> Tuple[float, float]:
    # Clamp to prevent overflow
    lat = max(min(lat, 85.05112878), -85.05112878)
    x = (lng + 180.0) / 360.0 * TILE_SIZE * scale
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
    tlx, tly = cx - VIEW_W / 2.0, cy - VIEW_H / 2.0
    brx, bry = cx + VIEW_W / 2.0, cy + VIEW_H / 2.0
    north, west = _world_to_latlng(tlx, tly, scale)
    south, east = _world_to_latlng(brx, bry, scale)
    return {
        "north": round(north, 6),
        "south": round(south, 6),
        "west":  round(west, 6),
        "east":  round(east, 6),
    }

# ---------- Token discovery ----------
def extract_token_from_html(html: str) -> Optional[str]:
    if not html:
        return None
    low = html.lower()
    if "<html" not in low and "<!doctype" not in low:
        # probably not HTML
        return None
    for pat in TOKEN_PATTERNS:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1)
    return None

def find_token_cookie(jar: requests.cookies.RequestsCookieJar) -> Optional[Tuple[str, str]]:
    # Look for common antiforgery cookie names
    for c in jar:
        name_low = c.name.lower()
        if ("requestverificationtoken" in name_low) or ("antiforgery" in name_low):
            return (c.name, c.value)
    return None

def warmup_and_get_token(sess: requests.Session, lat: float, lng: float, zm: int):
    url = f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    r = sess.get(url, headers={
        "Accept": "text/html, */*;q=0.1",
        "Referer": TF_BASE + "/",
    }, timeout=15)

    html = r.text or ""
    token = extract_token_from_html(html)
    token_source = "html" if token else None

    if not token:
        # Try a Set-Cookie based token
        ck = find_token_cookie(r.cookies)
        if not ck:
            ck = find_token_cookie(sess.cookies)
        if ck:
            token = ck[1]
            token_source = "set-cookie"

    info = {
        "status": r.status_code,
        "bytes": len(r.content or b""),
        "token_found": bool(token),
        "token_source": token_source or "",
        "had_token_cookie": bool(find_token_cookie(sess.cookies)),
    }
    return token, info

# ---------- Viewport POST ----------
def post_viewport(sess: requests.Session, token: Optional[str], lat: float, lng: float, zm: int) -> Dict[str, Any]:
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
    }
    # Send all common header names when we have a token
    if token:
        headers["RequestVerificationToken"] = token
        headers["X-RequestVerificationToken"] = token
        headers["X-CSRF-TOKEN"] = token

    url = f"{TF_BASE}/Home/GetViewPortData"
    b = compute_bounds(lat, lng, zm)
    attempts: List[Dict[str, Any]] = []

    def send(form: Dict[str, Any]) -> Dict[str, Any]:
        form2 = dict(form)
        if token:
            # Send both names commonly used by ASP.NET MVC/Core
            form2["__RequestVerificationToken"] = token
            form2["RequestVerificationToken"] = token
        r = sess.post(url, data=form2, headers=headers, timeout=20)
        txt = r.text or ""
        looks_like_html = ("<html" in txt.lower()) or ("<!doctype html" in txt.lower())
        return {
            "form": form,
            "resp": {
                "status": r.status_code,
                "bytes": len(r.content or b""),
                "looks_like_html": bool(looks_like_html),
                "preview": txt[:200],
            }
        }

    forms = [
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
        {"east": f"{b['east']:.6f}", "north": f"{b['north']:.6f}", "south": f"{b['south']:.6f}", "west": f"{b['west']:.6f}", "zoomLevel": str(zm)},
        {"neLat": f"{b['north']:.6f}", "neLng": f"{b['east']:.6f}", "swLat": f"{b['south']:.6f}", "swLng": f"{b['west']:.6f}", "zoomLevel": str(zm)},
    ]

    for f in forms:
        attempts.append(send(f))

    # Choose winner: biggest non-HTML, 200 OK
    winner_idx = -1
    best_bytes = -1
    for i, a in enumerate(attempts):
        r = a["resp"]
        if r["status"] == 200 and not r["looks_like_html"] and r["bytes"] > best_bytes:
            best_bytes = r["bytes"]; winner_idx = i

    winner = attempts[winner_idx] if winner_idx >= 0 else None
    return {
        "verification_token_present": bool(token),
        "attempts": attempts,
        "response": winner["resp"] if winner else (attempts[0]["resp"] if attempts else None),
        "winner": winner_idx if winner_idx >= 0 else "none",
    }

# ---------- Routes ----------
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
    url = f"{TF_BASE}/Home/IsLoggedIn"
    r = sess.post(url, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
    txt = r.text or ""
    try:
        data = json.loads(txt)
    except Exception:
        data = {}
    return jsonify({
        "status": r.status_code,
        "bytes": len(r.content or b""),
        "cookie_present": bool(get_aspxauth()),
        "is_logged_in": bool(data.get("is_logged_in") or data.get("IsLoggedIn")),
        "email": data.get("email_address") or data.get("EmailAddress") or "",
        "text": txt,
    })

@app.get("/token")
def token_probe():
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
        zm  = int(request.args.get("zm"))
    except Exception:
        return jsonify({"error":"pass ?lat=..&lng=..&zm=.."}), 400
    sess = make_session()
    token, warm = warmup_and_get_token(sess, lat, lng, zm)
    cookie_hint = None
    ck = find_token_cookie(sess.cookies)
    if ck:
        cookie_hint = {"name": ck[0], "present": True}
    return jsonify({
        "present": bool(token),
        "source": warm.get("token_source"),
        "warmup": warm,
        "token_cookie": cookie_hint or {"present": False},
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
    token, warm = warmup_and_get_token(sess, lat, lng, zm)
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
    sess = make_session()
    token, warm = warmup_and_get_token(sess, cities[0][1], cities[0][2], zm_levels[0])
    results = []
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
    return jsonify({"count": len(results), "results": results})

@app.get("/")
def root():
    return jsonify({
        "name": "RailOps JSON",
        "routes": [
            "Set your cookie once: /set-aspxauth?value=PASTE_.ASPXAUTH",
            "Check: /authcheck",
            "Token debug: /token?lat=-33.8688&lng=151.2093&zm=12",
            "Test: /debug/viewport?lat=-33.8688&lng=151.2093&zm=12",
            "Scan: /scan",
        ]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
