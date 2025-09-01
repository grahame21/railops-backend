import os, math, json, time
from typing import Any, Dict, List, Tuple, Optional
from flask import Flask, request, jsonify, make_response
import requests

UP = "https://trainfinder.otenko.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

app = Flask(__name__)
ASPXAUTH = os.environ.get("ASPXAUTH", "").strip()

def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8,en-AU;q=0.7",
    })
    if ASPXAUTH:
        s.cookies.set(".ASPXAUTH", ASPXAUTH, domain="trainfinder.otenko.com", secure=True)
    return s

def set_cookie(val: str):
    global ASPXAUTH
    ASPXAUTH = (val or "").strip()

# ---------- viewport helpers (in case bounds are required) ----------
TILE_SIZE = 256.0

def _lat_to_merc_y(lat: float) -> float:
    lat = max(min(lat, 85.05112878), -85.05112878)  # clamp Mercator
    siny = math.sin(lat * math.pi / 180.0)
    y = 0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)
    return y

def _lng_to_merc_x(lng: float) -> float:
    x = (lng + 180.0) / 360.0
    return x

def compute_bounds(lat: float, lng: float, zm: int, px_w: int = 640, px_h: int = 640):
    """Approximate bounds of a viewport around center lat/lng at zoom zm."""
    scale = 2 ** zm
    cx, cy = _lng_to_merc_x(lng), _lat_to_merc_y(lat)
    w_frac = (px_w / TILE_SIZE) / scale
    h_frac = (px_h / TILE_SIZE) / scale
    west_x  = cx - w_frac / 2
    east_x  = cx + w_frac / 2
    north_y = cy - h_frac / 2
    south_y = cy + h_frac / 2

    west_lng = west_x * 360.0 - 180.0
    east_lng = east_x * 360.0 - 180.0

    def y_to_lat(y):
        n = math.pi - 2.0 * math.pi * y
        return 180.0 / math.pi * math.atan(0.5 * (math.exp(n) - math.exp(-n)))

    north_lat = y_to_lat(north_y)
    south_lat = y_to_lat(south_y)
    return {
        "west": round(west_lng, 6),
        "east": round(east_lng, 6),
        "north": round(north_lat, 6),
        "south": round(south_lat, 6),
    }

# ---------- probing logic ----------
def looks_trainy(obj: Any) -> bool:
    """Heuristic: does JSON look like it contains trains/markers/features?"""
    try:
        if isinstance(obj, dict):
            # common keys to try
            for key in ("trains", "items", "features", "markers", "results", "data"):
                v = obj.get(key)
                if isinstance(v, list) and len(v) > 0:
                    return True
                if isinstance(v, dict):
                    # nested lists?
                    for vv in v.values():
                        if isinstance(vv, list) and len(vv) > 0:
                            return True
            # any non-empty list anywhere?
            for v in obj.values():
                if isinstance(v, list) and len(v) > 0:
                    return True
        if isinstance(obj, list) and len(obj) > 0:
            return True
    except Exception:
        pass
    return False

def _headers_ajax(lat: float, lng: float, zm: int) -> Dict[str, str]:
    return {
        "Origin": UP,
        "Referer": f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
    }

def try_call(s: requests.Session, url: str, method: str, data: Any, as_json: bool) -> Tuple[int, str, Dict[str, Any]]:
    hdrs = _headers_ajax(data.get("lat", -33.8688), data.get("lng", 151.2093), int(data.get("zm", 12)))
    if method == "GET":
        r = s.get(url, headers=hdrs, timeout=20, params=data)
    else:
        if as_json:
            r = s.post(url, headers={**hdrs, "Content-Type": "application/json"}, json=data, timeout=20)
        else:
            r = s.post(url, headers={**hdrs, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}, data=data, timeout=20)
    info = {"status": r.status_code, "bytes": len(r.content)}
    text = r.text
    return r.status_code, text, info

def smart_probe(lat: float, lng: float, zm: int) -> Dict[str, Any]:
    s = new_session()

    # hit a page first so cookies feel "real"
    try:
        s.get(f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", timeout=20)
    except Exception:
        pass

    b = compute_bounds(lat, lng, zm)
    attempts: List[Dict[str, Any]] = []

    # candidates to try (order matters)
    candidates: List[Tuple[str, str, Dict[str, Any], bool]] = [
        (f"{UP}/Home/GetViewPortData", "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/Home/GetViewPortData", "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)}, False),
        (f"{UP}/Home/GetViewPortData", "POST", {"neLat": f"{b['north']}", "neLng": f"{b['east']}", "swLat": f"{b['south']}", "swLng": f"{b['west']}", "zoomLevel": str(zm)}, False),

        # plausible alternates
        (f"{UP}/Home/GetTrains", "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/Home/Trains", "GET",  {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/Home/GetMarkers", "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/Home/GetMapData", "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/api/trains", "GET",  {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/api/viewport", "POST", {"lat": lat, "lng": lng, "zm": zm}, True),
    ]

    best: Optional[Dict[str, Any]] = None

    for url, method, data, as_json in candidates:
        try:
            status, text, meta = try_call(s, url, method, data, as_json)
        except Exception as e:
            attempts.append({"url": url, "method": method, "error": str(e)})
            continue

        parsed = None
        looks_html = text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html")
        if not looks_html and text.strip().startswith("{"):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None

        attempt_rec = {
            "url": url,
            "method": method,
            "status": status,
            "bytes": meta["bytes"],
            "looks_like_html": looks_html,
        }
        if parsed is not None:
            attempt_rec["keys"] = list(parsed.keys()) if isinstance(parsed, dict) else None
            attempt_rec["trainy"] = looks_trainy(parsed)
        else:
            attempt_rec["preview"] = text[:160]

        attempts.append(attempt_rec)

        if status == 200 and parsed is not None and looks_trainy(parsed):
            best = {"url": url, "method": method, "data": parsed}
            break

    return {"attempts": attempts, "best": best}

# ---------- routes ----------
@app.get("/")
def root():
    return """
    <h1>RailOps JSON</h1>
    <p>Set cookie once: <code>/set-aspxauth?value=PASTE_FULL_.ASPXAUTH</code></p>
    <p>Check login: <code>/authcheck</code></p>
    <p>Probe endpoints: <code>/probe?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code></p>
    <p>Trains (auto-picks working endpoint): <code>/trains?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code></p>
    """, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.get("/set-aspxauth")
def set_aspx():
    v = request.args.get("value", "").strip()
    if not v:
        return jsonify({"ok": False, "message": "Provide ?value=PASTE_FULL_.ASPXAUTH"}), 400
    set_cookie(v)
    return jsonify({"ok": True, "cookie_len": len(v)})

@app.get("/authcheck")
def authcheck():
    s = new_session()
    try:
        r = s.post(f"{UP}/Home/IsLoggedIn", headers={
            "Origin": UP, "Referer": f"{UP}/", "X-Requested-With": "XMLHttpRequest", "Accept": "*/*"
        }, timeout=20)
        email = ""
        logged = False
        try:
            j = r.json()
            email = j.get("email_address") or ""
            logged = bool(j.get("is_logged_in"))
        except Exception:
            pass
        return jsonify({
            "status": r.status_code,
            "bytes": len(r.content),
            "cookie_present": bool(ASPXAUTH),
            "is_logged_in": logged,
            "email": email
        })
    except Exception as e:
        return jsonify({"cookie_present": bool(ASPXAUTH), "error": str(e)}), 502

@app.get("/probe")
def probe():
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm  = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "bad lat/lng/zm"}), 400

    if not ASPXAUTH:
        return jsonify({"error": ".ASPXAUTH not set. Call /set-aspxauth?value=... first."}), 400

    res = smart_probe(lat, lng, zm)
    return jsonify(res)

@app.get("/trains")
def trains():
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm 
