import os, time, math, json
from urllib.parse import urlencode
import requests
from flask import Flask, request, jsonify, Response

TF_BASE = "https://trainfinder.otenko.com"
ASPX_COOKIE_NAME = ".ASPXAUTH"

app = Flask(__name__)
session = requests.Session()
session.headers.update({
    "User-Agent": "RailOps-Helper/1.0 (+render)",
    "Accept": "*/*",
    "Origin": TF_BASE,
    "Referer": TF_BASE + "/",
    "X-Requested-With": "XMLHttpRequest",
})
# 10s connect/read timeout everywhere
TIMEOUT = (10, 10)

def set_cookie_from_env():
    """Load cookie from env once on boot (Render restarts safe)."""
    token = os.environ.get("RAILOPS_ASPXAUTH", "").strip()
    if token:
        session.cookies.set(ASPX_COOKIE_NAME, token, domain="trainfinder.otenko.com", secure=True)
    return bool(token)

def set_cookie_value(raw_value: str) -> bool:
    """Set cookie from a raw token value (no .ASPXAUTH= prefix)."""
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return False
    session.cookies.set(ASPX_COOKIE_NAME, raw_value, domain="trainfinder.otenko.com", secure=True)
    return True

def has_cookie() -> bool:
    c = session.cookies.get(ASPX_COOKIE_NAME, domain="trainfinder.otenko.com")
    return bool(c)

def warmup(lat: float, lng: float, zm: int):
    # Load the page the site uses to prime session
    url = f"{TF_BASE}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={int(zm)}"
    r = session.get(url, timeout=TIMEOUT)
    return {"status": r.status_code, "bytes": len(r.content), "url": url, "preview": r.text[:400]}

def viewport_call(payload: dict):
    """POST to GetViewPortData with given form payload."""
    url = f"{TF_BASE}/Home/GetViewPortData"
    r = session.post(url, data=payload, timeout=TIMEOUT)
    looks_like_html = r.headers.get("content-type","").lower().startswith("text/html")
    data = None
    try:
        data = r.json()
    except Exception:
        pass
    return {
        "url": url,
        "status": r.status_code,
        "bytes": len(r.content),
        "looks_like_html": looks_like_html,
        "preview": (r.text[:200] if looks_like_html else json.dumps(data)[:200] if data is not None else r.text[:200]),
        "data": data,
    }

def deg_box(lat: float, lng: float, zm: int):
    """Rough viewport box around a point, sized by zoom. Good enough to trigger data if server needs bounds."""
    # crude but serviceable: pixel span ~ 800x600
    world_px = 256 * (2 ** zm)
    deg_per_px = 360.0 / world_px
    half_w_px, half_h_px = 400, 300
    dlon = deg_per_px * half_w_px
    dlat = deg_per_px * half_h_px
    north = lat + dlat
    south = lat - dlat
    east = lng + dlon
    west = lng - dlon
    return north, south, east, west

def try_viewport(lat: float, lng: float, zm: int):
    """Try several payload shapes the site historically accepted and pick the first with non-empty data."""
    attempts = []
    # 1) simple lat/lng/zm (as seen in their JS sometimes)
    attempts.append(viewport_call({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}))
    # 2) same but 'zoomLevel'
    attempts.append(viewport_call({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)}))
    # 3) east/west/north/south + zoomLevel
    n, s, e, w = deg_box(lat, lng, zm)
    attempts.append(viewport_call({
        "east": f"{e:.6f}", "west": f"{w:.6f}",
        "north": f"{n:.6f}", "south": f"{s:.6f}",
        "zoomLevel": str(zm),
    }))
    # 4) ne/sw variant + zoomLevel
    attempts.append(viewport_call({
        "neLat": f"{n:.6f}", "neLng": f"{e:.6f}",
        "swLat": f"{s:.6f}", "swLng": f"{w:.6f}",
        "zoomLevel": str(zm),
    }))

    # Pick the first that looks like JSON with any non-null section
    winner_idx = None
    for i, att in enumerate(attempts):
        data = att.get("data") or {}
        # Heuristic: if any top-level value is not None, call it a win
        if isinstance(data, dict) and any(v is not None for v in data.values()):
            winner_idx = i
            break

    return attempts, winner_idx

@app.route("/", methods=["GET"])
def index():
    return Response(
        "RailOps JSON\n\n"
        "1) Set cookie once (recommended env var): /set-aspxauth?value=PASTE_TOKEN\n"
        "2) Check login: /authcheck\n"
        "3) Test one viewport: /debug/viewport?lat=-33.8688&lng=151.2093&zm=12\n"
        "4) Simple scan: /scan\n"
        "5) Trains proxy (same params): /trains?lat=-33.8688&lng=151.2093&zm=12\n",
        mimetype="text/plain"
    )

@app.route("/set-aspxauth", methods=["GET", "POST"])
def set_aspxauth():
    token = request.values.get("value", "")
    ok = set_cookie_value(token)
    return jsonify({"ok": ok, "len": len(token)})

@app.route("/authcheck", methods=["GET"])
def authcheck():
    cookie_present = has_cookie() or set_cookie_from_env()
    # Poke a private page to infer login email if they expose it; otherwise just echo true/false
    # We can infer nothing reliable without a dedicated endpoint, so only return presence.
    return jsonify({
        "cookie_present": cookie_present,
        "is_logged_in": bool(cookie_present),  # with this site we can only assert cookie presence
        "email_address": os.environ.get("RAILOPS_EMAIL","") if cookie_present else ""
    })

@app.route("/debug/viewport", methods=["GET"])
def debug_viewport():
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(request.args.get("zm", "12"))

    used_cookie = has_cookie() or set_cookie_from_env()
    wu = warmup(lat, lng, zm)
    attempts, winner_idx = try_viewport(lat, lng, zm)

    resp = {
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            "used_cookie": used_cookie,
            "warmup": wu,
            "viewport": {
                "attempts": attempts,
                "winner": winner_idx if winner_idx is not None else "none",
                "response": attempts[winner_idx] if winner_idx is not None else (attempts[0] if attempts else {}),
            }
        }
    }
    return jsonify(resp)

@app.route("/trains", methods=["GET"])
def trains():
    """Returns the best viewport payload result (or the last attempt) for your front-end."""
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(request.args.get("zm", "12"))

    set_cookie_from_env()
    warmup(lat, lng, zm)
    attempts, winner_idx = try_viewport(lat, lng, zm)
    best = attempts[winner_idx] if winner_idx is not None else attempts[-1]
    # surface only the data part to the frontend
    return jsonify(best.get("data") or {})

@app.route("/scan", methods=["GET"])
def scan():
    cities = [
        ("Sydney",   -33.8688, 151.2093),
        ("Melbourne",-37.8136, 144.9631),
        ("Brisbane", -27.4698, 153.0251),
        ("Perth",    -31.9523, 115.8613),
        ("Adelaide", -34.9285, 138.6007),
    ]
    zm_list = [11,12,13]
    out = []
    used_cookie = has_cookie() or set_cookie_from_env()
    for city, lat, lng in cities:
        warmup(lat,lng,12)
        attempts, winner_idx = try_viewport(lat, lng, 12)
        bytes_ = attempts[winner_idx]["bytes"] if winner_idx is not None else attempts[-1]["bytes"]
        looks = attempts[winner_idx]["looks_like_html"] if winner_idx is not None else attempts[-1]["looks_like_html"]
        for zm in zm_list:
            out.append({
                "city": city, "lat": lat, "lng": lng, "zm": zm,
                "viewport_bytes": bytes_, "looks_like_html": looks,
                "verification_token_present": False,  # not required here
            })
    return jsonify({"count": len(out), "used_cookie": used_cookie, "results": out})

if __name__ == "__main__":
    # local dev: python main.py
    set_cookie_from_env()
    app.run(host="0.0.0.0", port=10000, debug=False)
