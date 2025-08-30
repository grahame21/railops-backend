import os, re, math, json, time
import requests
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ---- Config ----
VIEW_W = 800
VIEW_H = 600
TF_BASE = "https://trainfinder.otenko.com"
TF_AUTH_ENV = "TF_ASPXAUTH"
ASPXAUTH = os.getenv(TF_AUTH_ENV, "").strip()

# ---- CORS (for your Netlify frontend) ----
@app.after_request
def add_cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "*"
    return r

@app.route("/<path:p>", methods=["OPTIONS"])
def options_passthru(p):
    return ("", 204)

# ---- Cookie helpers ----
def set_cookie(val: str):
    global ASPXAUTH
    ASPXAUTH = (val or "").strip()

def get_cookie() -> str:
    return ASPXAUTH

# ---- Mercator helpers (no overflows) ----
def _lat_to_y(lat):
    s = math.sin(math.radians(lat))
    return 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)

def _lng_to_x(lng):
    return (lng + 180.0) / 360.0

def _y_to_lat(y):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y))))

def _x_to_lng(x):
    return x * 360.0 - 180.0

def compute_bounds(lat, lng, zm, w=VIEW_W, h=VIEW_H):
    world = 256 * (2 ** int(zm))
    cx = _lng_to_x(lng) * world
    cy = _lat_to_y(lat) * world
    tlx, tly = cx - w/2, cy - h/2
    brx, bry = cx + w/2, cy + h/2
    west  = _x_to_lng(tlx / world)
    east  = _x_to_lng(brx / world)
    north = _y_to_lat(tly / world)
    south = _y_to_lat(bry / world)
    return {"west": west, "east": east, "north": north, "south": south}

def looks_like_html(text: str) -> bool:
    t = text.lstrip().lower()
    return t.startswith("<!doctype") or t.startswith("<html")

def extract_verification_token(html: str):
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html, re.I)
    if m: return m.group(1)
    m = re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)["\']', html, re.I)
    return m.group(1) if m else None

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 RailOpsFetcher",
        "Accept": "application/json, */*;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
    })
    ck = get_cookie()
    if ck:
        s.cookies.set(".ASPXAUTH", ck, domain="trainfinder.otenko.com")
    return s

def tf_warmup_and_tokens(s, lat, lng, zm):
    warm_url = f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    warm = s.get(warm_url, timeout=15)
    form_token = extract_verification_token(warm.text)
    cookie_token = (
        s.cookies.get("__RequestVerificationToken")
        or s.cookies.get("RequestVerificationToken")
        or s.cookies.get("XSRF-TOKEN")
    )
    # ASP.NET variants: header can be cookie, form, or cookie:form
    header_token = None
    if cookie_token and form_token:
        header_token = f"{cookie_token}:{form_token}"
    elif cookie_token:
        header_token = cookie_token
    elif form_token:
        header_token = form_token

    headers = {
        "Referer": warm_url,
        "Origin": TF_BASE,
        "Accept": "application/json, */*;q=0.8",
    }
    if header_token:
        headers["RequestVerificationToken"] = header_token
        headers["X-RequestVerificationToken"] = header_token

    return warm, headers, form_token

def tf_post_viewport(s, headers, form):
    # Try both casings, some IIS setups are picky
    urls = [
        f"{TF_BASE}/Home/GetViewPortData",
        f"{TF_BASE}/home/GetViewPortData",
    ]
    for u in urls:
        r = s.post(u, data=form, headers=headers, timeout=20)
        if r.status_code == 200 and not looks_like_html(r.text):
            return r
    return None

def fetch_viewport(lat, lng, zm):
    s = make_session()
    warm, hdrs, form_token = tf_warmup_and_tokens(s, lat, lng, zm)
    bounds = compute_bounds(lat, lng, zm)

    attempts = [
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
        {"east": f"{bounds['east']:.6f}", "west": f"{bounds['west']:.6f}",
         "north": f"{bounds['north']:.6f}", "south": f"{bounds['south']:.6f}",
         "zoomLevel": str(zm)},
        {"neLat": f"{bounds['north']:.6f}", "neLng": f"{bounds['east']:.6f}",
         "swLat": f"{bounds['south']:.6f}", "swLng": f"{bounds['west']:.6f}",
         "zoomLevel": str(zm)},
    ]
    # Also try putting the form token as a field (some ASP.NET variants require it)
    if form_token:
        for a in list(attempts):
            b = dict(a)
            b["__RequestVerificationToken"] = form_token
            attempts.append(b)

    logs = []
    for form in attempts:
        r = tf_post_viewport(s, hdrs, form)
        if r is not None:
            return {
                "ok": True,
                "bounds": bounds,
                "response": r,
                "warm": warm,
                "headers_used": bool(hdrs.get("RequestVerificationToken")),
            }
        # keep last try preview (best effort)
        try:
            logs.append({"form": form, "note": "failed"})
        except Exception:
            pass

    return {
        "ok": False,
        "bounds": bounds,
        "warm": warm,
        "headers_used": bool(hdrs.get("RequestVerificationToken")),
        "attempts": logs,
    }

# ---- Routes ----
@app.get("/")
def index():
    return jsonify({
        "service": "RailOps JSON proxy",
        "how_to": {
            "1_set_cookie_once": "/set-aspxauth?value=PASTE_FULL_.ASPXAUTH",
            "2_check": "/authcheck",
            "3_test_one": "/debug/viewport?lat=-33.8688&lng=151.2093&zm=12",
            "4_frontend_calls": "/trains?lat=-33.8688&lng=151.2093&zm=12"
        },
        "env_alternative": f"Set {TF_AUTH_ENV} in your host to persist cookie across restarts."
    })

@app.get("/set-aspxauth")
def set_aspxauth():
    v = request.args.get("value", "")
    set_cookie(v)
    return jsonify({"ok": bool(get_cookie()), "stored_length": len(get_cookie())})

@app.get("/authcheck")
def authcheck():
    s = make_session()
    try:
        r = s.post(f"{TF_BASE}/Home/IsLoggedIn", timeout=10)
        txt = r.text
        try:
            data = r.json()
        except Exception:
            data = {}
        is_in = (
            data.get("is_logged_in") or data.get("isLoggedIn")
            or '"is_logged_in":true' in txt or '"isLoggedIn":true' in txt
        ) or False
        email = data.get("email_address") or data.get("emailAddress") or data.get("email") or ""
        return jsonify({
            "status": r.status_code,
            "bytes": len(r.content),
            "cookie_present": bool(get_cookie()),
            "is_logged_in": bool(is_in),
            "email": email,
            "text": txt[:1000]
        })
    except Exception as e:
        return jsonify({"error": str(e), "cookie_present": bool(get_cookie())}), 500

@app.get("/debug/viewport")
def debug_viewport():
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(float(request.args.get("zm", "12")))
    res = fetch_viewport(lat, lng, zm)
    if not res["ok"]:
        warm = res["warm"]
        return jsonify({
            "input": {"lat": lat, "lng": lng, "zm": zm},
            "bounds": res["bounds"],
            "tf": {
                "used_cookie": bool(get_cookie()),
                "verification_token_present": res["headers_used"],
                "warmup": {"status": warm.status_code, "bytes": len(warm.content)},
                "attempts": res.get("attempts", []),
                "winner": "none"
            }
        }), 502

    r = res["response"]; warm = res["warm"]
    return jsonify({
        "bounds": res["bounds"],
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            "used_cookie": bool(get_cookie()),
            "verification_token_present": res["headers_used"],
            "viewport": {
                "status": r.status_code,
                "bytes": len(r.content),
                "looks_like_html": looks_like_html(r.text),
                "preview": r.text[:400]
            },
            "warmup": {"status": warm.status_code, "bytes": len(warm.content)}
        }
    })

# NEW: simple proxy your frontend can call directly
@app.get("/trains")
def trains():
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(float(request.args.get("zm", "12")))
    res = fetch_viewport(lat, lng, zm)
    if not res["ok"]:
        return jsonify({"error": "failed to fetch viewport", "hint": "check /authcheck and your cookie"}), 502
    txt = res["response"].text
    # Pass through TrainFinder JSON
    return Response(txt, status=200, mimetype="application/json")

@app.get("/healthz")
def health():
    return "ok", 200
