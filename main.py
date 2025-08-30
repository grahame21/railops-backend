import os, re, math, json, time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ---- Config ----
VIEW_W = 800  # pretend viewport size for bounds calc
VIEW_H = 600
TF_BASE = "https://trainfinder.otenko.com"
TF_AUTH_ENV = "TF_ASPXAUTH"  # optional env var to persist cookie between restarts
ASPXAUTH = os.getenv(TF_AUTH_ENV, "").strip()

# ---- Helpers ----
def set_cookie(val: str):
    """Store ASPXAUTH in memory (or set TF_ASPXAUTH env in Render dashboard)."""
    global ASPXAUTH
    ASPXAUTH = (val or "").strip()

def get_cookie() -> str:
    return ASPXAUTH

def _lat_to_y(lat):
    # 0..1 mercator Y, stable (no overflow)
    s = math.sin(math.radians(lat))
    return 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)

def _lng_to_x(lng):
    # 0..1 mercator X
    return (lng + 180.0) / 360.0

def _y_to_lat(y):
    # inverse mercator
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
    # Common ASP.NET anti-forgery input field
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html, re.I)
    return m.group(1) if m else None

def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 RailOpsFetcher",
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
    })
    ck = get_cookie()
    if ck:
        s.cookies.set(".ASPXAUTH", ck, domain="trainfinder.otenko.com")
    return s

# ---- Routes ----
@app.get("/")
def index():
    return jsonify({
        "service": "RailOps JSON proxy",
        "how_to": {
            "1_set_cookie_once": "/set-aspxauth?value=PASTE_FULL_.ASPXAUTH",
            "2_check": "/authcheck",
            "3_test_one": "/debug/viewport?lat=-33.8688&lng=151.2093&zm=12",
            "4_scan": "/scan"
        },
        "env_alternative": f"Set {TF_AUTH_ENV} in your host to persist cookie across restarts."
    })

@app.get("/set-aspxauth")
def set_aspxauth():
    v = request.args.get("value", "")
    set_cookie(v)
    return jsonify({
        "ok": bool(get_cookie()),
        "stored_length": len(get_cookie()),
        "tip": f"For persistence, set env var {TF_AUTH_ENV} in your host."
    })

@app.get("/authcheck")
def authcheck():
    s = make_session()
    used_cookie = bool(get_cookie())
    try:
        r = s.post(f"{TF_BASE}/Home/IsLoggedIn", timeout=10)
        txt = r.text
        try:
            data = r.json()
        except Exception:
            data = {}
        # Try multiple shapes
        is_in = (
            data.get("is_logged_in") or data.get("isLoggedIn")
            or '"is_logged_in":true' in txt or '"isLoggedIn":true' in txt
        ) or False
        email = data.get("email_address") or data.get("emailAddress") or data.get("email") or ""
        return jsonify({
            "status": r.status_code,
            "bytes": len(r.content),
            "cookie_present": used_cookie,
            "is_logged_in": bool(is_in),
            "email": email,
            "text": txt[:2000]  # debug preview
        })
    except Exception as e:
        return jsonify({"error": str(e), "cookie_present": used_cookie}), 500

@app.get("/debug/viewport")
def debug_viewport():
    # Inputs
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(float(request.args.get("zm", "12")))

    s = make_session()

    # 1) Warmup page to get anti-forgery tokens
    warm_url = f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    warm = s.get(warm_url, timeout=15)
    form_token = extract_verification_token(warm.text)
    cookie_token = (
        s.cookies.get("__RequestVerificationToken")
        or s.cookies.get("RequestVerificationToken")
        or s.cookies.get("XSRF-TOKEN")
    )
    # ASP.NET often wants header "RequestVerificationToken: {cookie}:{form}"
    header_token = None
    if cookie_token and form_token:
        header_token = f"{cookie_token}:{form_token}"
    elif cookie_token:
        header_token = cookie_token
    elif form_token:
        header_token = form_token

    common_headers = {}
    if header_token:
        common_headers["RequestVerificationToken"] = header_token
        common_headers["X-RequestVerificationToken"] = header_token

    # 2) Try the likely POST payloads
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

    got = None
    try_log = []
    for form in attempts:
        try:
            r = s.post(f"{TF_BASE}/home/GetViewPortData", data=form, headers=common_headers, timeout=20)
            txt = r.text
            ok = (r.status_code == 200) and (not looks_like_html(txt))
            try_log.append({"form": form, "status": r.status_code, "bytes": len(r.content), "looks_like_html": looks_like_html(txt), "preview": txt[:180]})
            if ok:
                got = r
                break
        except Exception as e:
            try_log.append({"form": form, "error": str(e)})

    if got is None:
        return jsonify({
            "input": {"lat": lat, "lng": lng, "zm": zm},
            "bounds": bounds,
            "tf": {
                "used_cookie": bool(get_cookie()),
                "verification_token_present": bool(header_token),
                "warmup": {"status": warm.status_code, "bytes": len(warm.content)},
                "attempts": try_log,
                "winner": "none"
            }
        }), 502

    return jsonify({
        "bounds": bounds,
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            "used_cookie": bool(get_cookie()),
            "verification_token_present": bool(header_token),
            "viewport": {
                "status": got.status_code,
                "bytes": len(got.content),
                "looks_like_html": looks_like_html(got.text),
                "preview": got.text[:400]
            },
            "warmup": {"status": warm.status_code, "bytes": len(warm.content)}
        }
    })

@app.get("/scan")
def scan():
    cities = [
        ("Sydney",   -33.8688, 151.2093),
        ("Melbourne",-37.8136, 144.9631),
        ("Brisbane", -27.4698, 153.0251),
        ("Perth",    -31.9523, 115.8613),
        ("Adelaide", -34.9285, 138.6007),
    ]
    out = []
    for name, lat, lng in cities:
        res = app.test_client().get(f"/debug/viewport?lat={lat}&lng={lng}&zm=12")
        j = json.loads(res.get_data(as_text=True))
        tfv = j.get("tf", {}).get("viewport", {})
        out.append({
            "city": name,
            "lat": lat, "lng": lng, "zm": 12,
            "viewport_bytes": tfv.get("bytes"),
            "looks_like_html": tfv.get("looks_like_html"),
        })
        time.sleep(0.1)
    return jsonify({"count": len(out), "results": out})

# Health
@app.get("/healthz")
def health():
    return "ok", 200
