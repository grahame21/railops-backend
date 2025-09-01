import os
import math
import json
from flask import Flask, request, jsonify, make_response
import requests

UP = "https://trainfinder.otenko.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

app = Flask(__name__)

# Will be set by /set-aspxauth
ASPXAUTH = os.environ.get("ASPXAUTH", "").strip()

def set_cookie(val: str) -> None:
    global ASPXAUTH
    ASPXAUTH = (val or "").strip()

def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8,en-AU;q=0.7",
        "Accept": "*/*",
    })
    if ASPXAUTH:
        # Preload cookie so subsequent calls carry it
        s.cookies.set(".ASPXAUTH", ASPXAUTH, domain="trainfinder.otenko.com", secure=True)
    return s

# ----------------- viewport helpers -----------------
TILE = 256.0

def _lat_to_merc_y(lat: float) -> float:
    lat = max(min(lat, 85.05112878), -85.05112878)
    siny = math.sin(lat * math.pi / 180.0)
    return 0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)

def _lng_to_merc_x(lng: float) -> float:
    return (lng + 180.0) / 360.0

def compute_bounds(lat: float, lng: float, zm: int, px_w: int = 640, px_h: int = 640):
    scale = 2 ** zm
    cx, cy = _lng_to_merc_x(lng), _lat_to_merc_y(lat)
    w_frac = (px_w / TILE) / scale
    h_frac = (px_h / TILE) / scale
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

# ----------------- heuristics & HTTP helpers -----------------
def looks_trainy(obj) -> bool:
    if isinstance(obj, dict):
        for k in ("trains", "items", "features", "markers", "results", "data"):
            v = obj.get(k)
            if isinstance(v, list) and v:
                return True
            if isinstance(v, dict):
                if any(isinstance(x, list) and x for x in v.values()):
                    return True
        if any(isinstance(v, list) and v for v in obj.values()):
            return True
    if isinstance(obj, list) and obj:
        return True
    return False

def _ajax_headers(lat: float, lng: float, zm: int):
    return {
        "Origin": UP,
        "Referer": f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
    }

def try_call(sess: requests.Session, url: str, method: str, params_or_data: dict, as_json: bool, lat: float, lng: float, zm: int):
    headers = _ajax_headers(lat, lng, zm)
    if method == "GET":
        r = sess.get(url, headers=headers, timeout=20, params=params_or_data)
    else:
        if as_json:
            r = sess.post(url, headers={**headers, "Content-Type": "application/json"}, json=params_or_data, timeout=20)
        else:
            r = sess.post(url, headers={**headers, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}, data=params_or_data, timeout=20)
    text = r.text
    looks_html = text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html")
    parsed = None
    if not looks_html and text.strip().startswith("{"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
    return {
        "url": url,
        "method": method,
        "status": r.status_code,
        "bytes": len(r.content),
        "looks_like_html": looks_html,
        "parsed": parsed,
        "preview": text[:160],
    }

def smart_probe(lat: float, lng: float, zm: int):
    s = new_session()

    # Warmup (ignore failures)
    try:
        s.get(f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", timeout=15)
    except Exception:
        pass

    b = compute_bounds(lat, lng, zm)

    candidates = [
        # Known one (returns tiny all-nulls for you, but keep it first)
        (f"{UP}/Home/GetViewPortData", "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),

        # Shape variations
        (f"{UP}/Home/GetViewPortData", "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)}, False),
        (f"{UP}/Home/GetViewPortData", "POST",
         {"neLat": f"{b['north']}", "neLng": f"{b['east']}", "swLat": f"{b['south']}", "swLng": f"{b['west']}", "zoomLevel": str(zm)}, False),

        # Plausible alternates you might actually be using
        (f"{UP}/Home/GetTrains",     "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/Home/Trains",        "GET",  {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/Home/GetMarkers",    "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/Home/GetMapData",    "POST", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/api/trains",         "GET",  {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, False),
        (f"{UP}/api/viewport",       "POST", {"lat": lat, "lng": lng, "zm": zm}, True),
    ]

    attempts = []
    best = None

    for url, method, payload, as_json in candidates:
        try:
            res = try_call(s, url, method, payload, as_json, lat, lng, zm)
        except Exception as e:
            attempts.append({"url": url, "method": method, "error": str(e)})
            continue

        rec = {
            "url": res["url"],
            "method": res["method"],
            "status": res["status"],
            "bytes": res["bytes"],
            "looks_like_html": res["looks_like_html"],
        }

        if res["parsed"] is not None:
            rec["keys"] = list(res["parsed"].keys()) if isinstance(res["parsed"], dict) else None
            rec["trainy"] = looks_trainy(res["parsed"])
            if res["status"] == 200 and rec["trainy"]:
                best = {"url": res["url"], "method": res["method"], "data": res["parsed"]}
                attempts.append(rec)
                break
        else:
            rec["preview"] = res["preview"]

        attempts.append(rec)

    return {"attempts": attempts, "best": best}

# ----------------- routes -----------------
@app.get("/")
def root():
    return (
        "<h1>RailOps JSON</h1>"
        "<p>Set cookie once: <code>/set-aspxauth?value=PASTE_FULL_.ASPXAUTH</code></p>"
        "<p>Check login: <code>/authcheck</code></p>"
        "<p>Probe endpoints: <code>/probe?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code></p>"
        "<p>Trains: <code>/trains?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code></p>"
    ), 200, {"Content-Type": "text/html; charset=utf-8"}

@app.get("/set-aspxauth")
def set_aspxauth():
    v = request.args.get("value", "").strip()
    if not v:
        return jsonify({"ok": False, "message": "Provide ?value=PASTE_FULL_.ASPXAUTH"}), 400
    set_cookie(v)
    return jsonify({"ok": True, "cookie_len": len(v)})

@app.get("/authcheck")
def authcheck():
    s = new_session()
    try:
        r = s.post(
            f"{UP}/Home/IsLoggedIn",
            headers={"Origin": UP, "Referer": f"{UP}/", "X-Requested-With": "XMLHttpRequest", "Accept": "*/*"},
            timeout=20,
        )
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
        zm  = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "bad lat/lng/zm"}), 400

    if not ASPXAUTH:
        return jsonify({"error": ".ASPXAUTH not set. Call /set-aspxauth?value=... first."}), 400

    res = smart_probe(lat, lng, zm)
    if res.get("best"):
        return jsonify(res["best"]["data"])

    # fallback: return first 200/JSON even if empty (consistent shape for frontend)
    s = new_session()
    b = compute_bounds(lat, lng, zm)
    for att in res.get("attempts", []):
        if att.get("status") == 200 and not att.get("looks_like_html"):
            url = att["url"]
            method = att["method"]
            # Pick a reasonable payload shape
            default_form = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}
            bounds_form  = {"neLat": f"{b['north']}", "neLng": f"{b['east']}", "swLat": f"{b['south']}", "swLng": f"{b['west']}", "zoomLevel": str(zm)}
            payload = default_form
            try:
                again = try_call(s, url, method, payload, False, lat, lng, zm)
                if again["status"] == 200 and again["parsed"] is not None:
                    return jsonify(again["parsed"])
                if again["status"] == 200:
                    # pass through body as JSON if possible
                    return make_response(again["preview"], 200, {"Content-Type": "application/json"})
            except Exception:
                # try bounds form as last resort
                try:
                    again = try_call(s, url, method, bounds_form, False, lat, lng, zm)
                    if again["status"] == 200 and again["parsed"] is not None:
                        return jsonify(again["parsed"])
                except Exception:
                    pass

    return jsonify({"error": "no train data found", "probe": res}), 502

@app.get("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
