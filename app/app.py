import os, re, requests
from flask import Flask, request, jsonify, make_response

ORIGIN = "https://trainfinder.otenko.com"
app = Flask(__name__)

def get_cookie():
    return (request.cookies.get(".ASPXAUTH")
            or request.cookies.get("ASPXAUTH")
            or os.getenv("ASPXAUTH")
            or "").strip()

def is_html(t: str) -> bool:
    s = t.strip().lower()
    return s.startswith("<!doctype html") or s.startswith("<html")

def extract_token(html: str) -> str:
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html, re.I)
    return m.group(1) if m else ""

def warmup(s: requests.Session, cookie: str, lat: float, lng: float, zm: int):
    h = {
        "cookie": f".ASPXAUTH={cookie}" if cookie else "",
        "accept": "text/html,*/*",
        "referer": f"{ORIGIN}/",
        "user-agent": "Mozilla/5.0",
    }
    r = s.get(f"{ORIGIN}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", headers=h, timeout=15)
    return {"status": r.status_code, "bytes": len(r.text), "token": extract_token(r.text)}

def post_viewport(s: requests.Session, cookie: str, token: str, form: dict):
    h = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
        "origin": ORIGIN,
        "referer": f"{ORIGIN}/",
        "cookie": f".ASPXAUTH={cookie}" if cookie else "",
        "user-agent": "Mozilla/5.0",
    }
    if token: h["RequestVerificationToken"] = token
    r = s.post(f"{ORIGIN}/Home/GetViewPortData", data=form, headers=h, timeout=15)
    return {
        "status": r.status_code,
        "bytes": len(r.text),
        "looks_like_html": is_html(r.text),
        "preview": r.text[:200],
    }, r.text

@app.get("/")
def root():
    return (
        "RailOps JSON\n\n"
        "Set cookie once: /set-aspxauth?value=PASTE_TOKEN\n"
        "Check:           /authcheck\n"
        "Debug:           /debug/viewport?lat=-33.8688&lng=151.2093&zm=12\n"
        "Scan:            /scan\n"
    ), 200, {"content-type":"text/plain; charset=utf-8"}

@app.get("/set-aspxauth")
def set_cookie():
    val = (request.args.get("value") or "").strip()
    if not val:
        return jsonify({"ok": False, "reason": "provide ?value=YOUR_.ASPXAUTH_value"}), 400
    resp = make_response(jsonify({"ok": True, "cookie_len": len(val)}))
    for name in (".ASPXAUTH", "ASPXAUTH"):
        resp.set_cookie(name, val, max_age=60*60*24*30, httponly=True, secure=True, samesite="Lax")
    return resp

@app.get("/authcheck")
def authcheck():
    cookie = get_cookie()
    if not cookie:
        return jsonify({"is_logged_in": False, "cookie_present": False, "email_address": ""})
    s = requests.Session()
    # include token just in case that endpoint cares on their side
    w = warmup(s, cookie, -33.8688, 151.2093, 12)
    h = {
        "accept": "*/*",
        "x-requested-with": "XMLHttpRequest",
        "origin": ORIGIN,
        "referer": f"{ORIGIN}/",
        "cookie": f".ASPXAUTH={cookie}",
        "user-agent": "Mozilla/5.0",
    }
    if w.get("token"):
        h["RequestVerificationToken"] = w["token"]
    r = s.post(f"{ORIGIN}/Home/IsLoggedIn", headers=h, timeout=15)
    email = ""
    is_logged_in = False
    try:
        data = r.json()
        email = data.get("email_address") or ""
        is_logged_in = bool(data.get("is_logged_in"))
    except Exception:
        pass
    return jsonify({
        "status": r.status_code,
        "bytes": len(r.text),
        "text": r.text,
        "is_logged_in": is_logged_in,
        "email": email,
        "cookie_present": True
    })

@app.get("/debug/viewport")
def debug_viewport():
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm = int(request.args.get("zm", "12"))
    cookie = get_cookie()
    s = requests.Session()
    w = warmup(s, cookie, lat, lng, zm)
    attempts, winner, last = [], "none", {}
    for form in [
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
        {"neLat": f"{lat+0.085563:.6f}", "neLng": f"{lng+0.154495:.6f}",
         "swLat": f"{lat-0.085477:.6f}", "swLng": f"{lng-0.154496:.6f}",
         "zoomLevel": str(zm)},
    ]:
        meta, _ = post_viewport(s, cookie, w.get("token",""), form)
        attempts.append({"form": form, "resp": meta})
        last = meta
        if meta["status"] == 200 and not meta["looks_like_html"]:
            winner = "found"; break
    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            "used_cookie": bool(cookie),
            "verification_token_present": bool(w.get("token")),
            "warmup": {"status": w["status"], "bytes": w["bytes"]},
            "viewport": {"attempts": attempts, "winner": winner, "response": last}
        }
    })

@app.get("/scan")
def scan():
    cookie = get_cookie()
    s = requests.Session()
    cities = [
        ("Sydney", -33.8688, 151.2093),
        ("Melbourne", -37.8136, 144.9631),
        ("Brisbane", -27.4698, 153.0251),
        ("Perth", -31.9523, 115.8613),
        ("Adelaide", -34.9285, 138.6007),
    ]
    zms = [11, 12, 13]
    out = []
    for city, lat, lng in cities:
        for zm in zms:
            w = warmup(s, cookie, lat, lng, zm)
            meta, _ = post_viewport(s, cookie, w.get("token",""),
                                    {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)})
            out.append({
                "city": city, "lat": lat, "lng": lng, "zm": zm,
                "warmup_bytes": w["bytes"],
                "viewport_bytes": meta["bytes"],
                "looks_like_html": meta["looks_like_html"],
            })
    return jsonify({"count": len(out), "results": out})
