import os, time, json
from typing import Dict, Any, Tuple, List
from flask import Flask, request, jsonify, make_response
import requests

UPSTREAM = "https://trainfinder.otenko.com"
SESSION_COOKIE_ENV = "TF_ASPXAUTH"   # optional: allow setting via env var for convenience

app = Flask(__name__)

# -----------------------
# simple in-memory cookie
# -----------------------
_ASPXAUTH_VALUE = os.environ.get(SESSION_COOKIE_ENV, "").strip()

def set_cookie_value(v: str):
    global _ASPXAUTH_VALUE
    _ASPXAUTH_VALUE = (v or "").strip()

def have_cookie() -> bool:
    return bool(_ASPXAUTH_VALUE)

def cookie_jar() -> requests.cookies.RequestsCookieJar:
    jar = requests.cookies.RequestsCookieJar()
    if have_cookie():
        jar.set(".ASPXAUTH", _ASPXAUTH_VALUE, domain="trainfinder.otenko.com", path="/")
    return jar

def std_headers(referer: str = None) -> Dict[str, str]:
    h = {
        "User-Agent": "RailOps JSON Relay/1.0 (+requests)",
        "Accept": "*/*",
        "Origin": UPSTREAM,
        "X-Requested-With": "XMLHttpRequest",
    }
    if referer:
        h["Referer"] = referer
    return h

def warmup(lat: float, lng: float, zm: int) -> Dict[str, Any]:
    """GET the NextLevel page to pick up any extra cookies and simulate the UI."""
    url = f"{UPSTREAM}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    r = requests.get(url, headers=std_headers(), cookies=cookie_jar(), timeout=15)
    return {
        "url": url,
        "status": r.status_code,
        "bytes": len(r.content),
        "token": "none",  # this site doesn’t expose a RequestVerificationToken in our tests
        "preview": r.text[:400]
    }

def post_viewport(form: Dict[str, str], referer: str) -> Tuple[requests.Response, Dict[str, Any]]:
    url = f"{UPSTREAM}/Home/GetViewPortData"
    r = requests.post(
        url,
        data=form,                          # form-encoded
        headers=std_headers(referer),
        cookies=cookie_jar(),
        timeout=20,
    )
    looks_like_html = r.headers.get("Content-Type", "").lower().startswith("text/html")
    trainy = False
    keys = []
    try:
        j = r.json()
        if isinstance(j, dict):
            keys = list(j.keys())[:8]
            # If it has data keys we expect, call it "trainy"
            trainy = any(k in j for k in ("favs","alerts","places","tts","webcams","atcsGomi","atcsObj"))
    except Exception:
        pass
    meta = {
        "method": "POST",
        "status": r.status_code,
        "bytes": len(r.content),
        "looks_like_html": looks_like_html,
        "trainy": trainy,
        "url": url,
        "keys": keys,
        "preview": (r.text[:200] if looks_like_html else r.text[:200]),
    }
    return r, meta

def try_viewport(lat: float, lng: float, zm: int) -> Dict[str, Any]:
    referer = f"{UPSTREAM}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    attempts: List[Dict[str, Any]] = []

    # 1) as used earlier
    r1, m1 = post_viewport({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, referer)
    attempts.append(m1)
    if m1["status"] == 200 and not m1["looks_like_html"]:
        return {"response": m1, "data": safe_json(r1), "winner": 0}

    # 2) explicit zoomLevel
    r2, m2 = post_viewport({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)}, referer)
    attempts.append(m2)
    if m2["status"] == 200 and not m2["looks_like_html"]:
        return {"response": m2, "data": safe_json(r2), "winner": 1}

    # 3) try bounds (east/north/south/west + zoomLevel)
    # fake a 0.15° box around the center (rough)
    half = 0.15
    west, east = lng - half, lng + half
    south, north = lat - half, lat + half
    r3, m3 = post_viewport({
        "east": f"{east:.6f}",
        "north": f"{north:.6f}",
        "south": f"{south:.6f}",
        "west": f"{west:.6f}",
        "zoomLevel": str(zm)
    }, referer)
    attempts.append(m3)
    if m3["status"] == 200 and not m3["looks_like_html"]:
        return {"response": m3, "data": safe_json(r3), "winner": 2}

    # None worked
    # If we got HTML of ~700 bytes, that’s the “TrainFinder Index” page => wrong method/fields.
    return {"response": attempts[-1] if attempts else {}, "data": None, "winner": "none", "attempts": attempts}

def safe_json(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        return None

def cors(resp):
    # minimal CORS for your frontend testing
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

# -----------------------
# Routes
# -----------------------

@app.get("/")
def index():
    body = {
        "name": "RailOps JSON",
        "endpoints": {
            "set_cookie": "/set-aspxauth?value=PASTE_FULL_.ASPXAUTH",
            "authcheck": "/authcheck",
            "debug_viewport": "/debug/viewport?lat=-33.8688&lng=151.2093&zm=12",
            "scan": "/scan",
            "trains": "/trains?lat=-33.8688&lng=151.2093&zm=12"
        }
    }
    return jsonify(body)

@app.get("/set-aspxauth")
def set_aspxauth():
    v = request.args.get("value", "").strip()
    set_cookie_value(v)
    return jsonify({"ok": True, "len": len(v)})

@app.get("/authcheck")
def authcheck():
    if not have_cookie():
        return jsonify({
            "is_logged_in": False,
            "email_address": "",
            "cookie_present": False
        })
    url = f"{UPSTREAM}/Home/IsLoggedIn"
    r = requests.post(url, headers=std_headers(UPSTREAM+"/home/nextlevel"), cookies=cookie_jar(), timeout=15)
    ok = False
    email = ""
    try:
        j = r.json()
        ok = bool(j.get("is_logged_in"))
        email = j.get("email_address") or ""
    except Exception:
        pass
    return jsonify({
        "is_logged_in": ok,
        "email_address": email,
        "cookie_present": have_cookie(),
        "status": r.status_code,
        "text": r.text if len(r.text) < 300 else r.text[:300]
    })

@app.get("/debug/viewport")
def debug_viewport():
    if not have_cookie():
        return cors(make_response(jsonify({"error": "no .ASPXAUTH set; visit /set-aspxauth first"}), 400))
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(request.args.get("zm", "12"))

    w = warmup(lat, lng, zm)
    result = try_viewport(lat, lng, zm)
    out = {
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            "used_cookie": have_cookie(),
            "verification_token_present": False,  # we never saw one in the warmup
            "viewport": result,
            "warmup": w
        }
    }
    return cors(make_response(jsonify(out), 200))

@app.get("/scan")
def scan():
    if not have_cookie():
        return cors(make_response(jsonify({"error": "no .ASPXAUTH set"}), 400))
    cities = [
        ("Sydney",    -33.8688, 151.2093),
        ("Melbourne", -37.8136, 144.9631),
        ("Brisbane",  -27.4698, 153.0251),
        ("Perth",     -31.9523, 115.8613),
        ("Adelaide",  -34.9285, 138.6007),
    ]
    zooms = [11, 12, 13]
    results = []
    for (name, lat, lng) in cities:
        for zm in zooms:
            r = try_viewport(lat, lng, zm)
            vb = r.get("response", {}).get("bytes", 0)
            looks_like_html = r.get("response", {}).get("looks_like_html", False)
            results.append({
                "city": name, "lat": lat, "lng": lng, "zm": zm,
                "viewport_bytes": vb,
                "looks_like_html": looks_like_html,
                "verification_token_present": False,
                "note": "",
            })
            time.sleep(0.2)
    return cors(make_response(jsonify({"count": len(results), "results": results}), 200))

@app.get("/trains")
def trains():
    """
    Simple wrapper that returns only the upstream JSON object (what your UI likely wants).
    """
    if not have_cookie():
        return cors(make_response(jsonify({"error": "no .ASPXAUTH set"}), 400))
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(request.args.get("zm", "12"))

    _ = warmup(lat, lng, zm)
    result = try_viewport(lat, lng, zm)
    data = result.get("data") or {}
    return cors(make_response(jsonify(data), 200))

# health check for Render
@app.head("/")
def head_ok():
    return "", 200
