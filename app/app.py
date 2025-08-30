import os, math, re, json
from flask import Flask, request, jsonify, Response, render_template_string
import requests

app = Flask(__name__)

# ------------------------ Config ------------------------
TF_BASE = "https://trainfinder.otenko.com"
WARMUP_PATH = "/home/nextlevel"
API_VIEWPORT_PATH = "/Home/GetViewPortData"
API_ISLOGGEDIN_PATH = "/Home/IsLoggedIn"

# Default view size used to compute bounds
VIEW_W = 980
VIEW_H = 740
TILE_SIZE = 256

# --------------------- Map math -------------------------
def _lnglat_to_pixelxy(lng: float, lat: float, zoom: int):
    scale = TILE_SIZE * (2 ** zoom)
    x = (lng + 180.0) / 360.0 * scale
    siny = math.sin(math.radians(lat))
    siny = min(max(siny, -0.9999), 0.9999)
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * scale
    return x, y

def _pixelxy_to_lnglat(x: float, y: float, zoom: int):
    scale = TILE_SIZE * (2 ** zoom)
    lng = x / scale * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * y / scale
    lat = math.degrees(math.atan(math.sinh(n)))
    return lng, lat

def compute_bounds(center_lat: float, center_lng: float, zoom: int, width: int, height: int):
    cx, cy = _lnglat_to_pixelxy(center_lng, center_lat, zoom)
    half_w = width / 2.0
    half_h = height / 2.0
    tlx, tly = cx - half_w, cy - half_h
    brx, bry = cx + half_w, cy + half_h
    west, north = _pixelxy_to_lnglat(tlx, tly, zoom)  # returns (lng, lat)
    east, south = _pixelxy_to_lnglat(brx, bry, zoom)
    # Normalize to named fields: north/south are lats, east/west are lngs
    return {
        "north": north,
        "south": south,
        "east": east,
        "west": west,
    }

# ----------------- TrainFinder session ------------------
def make_session(aspxauth_token: str | None):
    sess = requests.Session()
    # Required headers to mimic browser AJAX
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; RailOpsBot/1.0)",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Referer": TF_BASE + WARMUP_PATH,
    })
    if aspxauth_token:
        sess.cookies.set(".ASPXAUTH", aspxauth_token, domain="trainfinder.otenko.com", path="/")
    return sess

def extract_request_verification_token(html: str, cookies: requests.cookies.RequestsCookieJar):
    """
    Try both sources:
    1) a hidden input named __RequestVerificationToken in the page
    2) a cookie whose name contains 'RequestVerificationToken'
    """
    # hidden input
    m = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', html, re.I)
    if m:
        return m.group(1)

    # cookie (ASP.NET sometimes places an anti-forgery cookie)
    for c in cookies:
        if "RequestVerificationToken" in c.name:
            return c.value

    return None

def warmup_and_token(sess: requests.Session, lat: float, lng: float, zm: int):
    warmup_url = f"{TF_BASE}{WARMUP_PATH}?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    r = sess.get(warmup_url, timeout=20)
    html = r.text
    token = extract_request_verification_token(html, sess.cookies)
    return {
        "status": r.status_code,
        "bytes": len(r.content),
        "token": token,
        "url": warmup_url
    }

def looks_like_html(resp: requests.Response) -> bool:
    ct = resp.headers.get("Content-Type", "")
    if "text/html" in ct.lower():
        return True
    t = resp.text.lstrip()
    return t.startswith("<!DOCTYPE") or t.startswith("<html")

def tf_post_viewport(sess: requests.Session, bounds: dict, zm: int, token: str | None):
    url = f"{TF_BASE}{API_VIEWPORT_PATH}"
    attempts = []

    def do_post(form):
        headers = {}
        if token:
            # ASP.NET MVC default header name:
            headers["RequestVerificationToken"] = token
        r = sess.post(url, data=form, headers=headers, timeout=30)
        preview = r.text[:160]
        htmlish = looks_like_html(r)
        ok_json = (not htmlish) and r.status_code == 200
        body = r.text
        # Heuristic: the “empty” response is ~98 bytes and all nulls
        emptyish = ok_json and len(body) <= 120 and "null" in body
        return {
            "form": form,
            "resp": {
                "status": r.status_code,
                "bytes": len(r.content),
                "looks_like_html": htmlish,
                "preview": preview
            },
            "is_winner": ok_json and not emptyish
        }

    # 1) Named bounds + zoomLevel
    attempts.append(do_post({
        "north": f"{bounds['north']:.6f}",
        "south": f"{bounds['south']:.6f}",
        "east":  f"{bounds['east']:.6f}",
        "west":  f"{bounds['west']:.6f}",
        "zoomLevel": str(zm),
    }))

    # 2) NE/SW names + zoomLevel
    attempts.append(do_post({
        "neLat": f"{bounds['north']:.6f}",
        "neLng": f"{bounds['east']:.6f}",
        "swLat": f"{bounds['south']:.6f}",
        "swLng": f"{bounds['west']:.6f}",
        "zoomLevel": str(zm),
    }))

    # 3) Center point + zoomLevel
    center_lat = (bounds["north"] + bounds["south"]) / 2.0
    center_lng = (bounds["east"] + bounds["west"]) / 2.0
    attempts.append(do_post({
        "lat": f"{center_lat:.6f}",
        "lng": f"{center_lng:.6f}",
        "zoomLevel": str(zm),
    }))

    winner = next((i for i, a in enumerate(attempts) if a["is_winner"]), None)
    return attempts, winner

def get_cookie_from_request():
    # 1) Header wins (X-TF-ASPXAUTH)
    header_val = request.headers.get("X-TF-ASPXAUTH", "").strip()
    if header_val:
        return header_val
    # 2) Query override (for the /try page)
    q = request.args.get("cookie", "").strip()
    if q:
        return q
    # 3) Environment variable on Render
    env_val = os.environ.get("TF_AUTH_COOKIE", "").strip()
    if env_val:
        return env_val
    return None

# ---------------------- Routes --------------------------
@app.get("/")
def root():
    return jsonify({
        "routes": ["/try", "/authcheck", "/debug/viewport?lat=...&lng=...&zm=...", "/scan"]
    })

TRY_HTML = """
<!doctype html>
<html>
  <head><meta charset="utf-8"><title>TF Tester</title>
  <style>body{font-family:system-ui,Segoe UI,Roboto,Arial;margin:24px}input,button{font-size:16px;padding:8px} code{background:#f4f4f4;padding:2px 6px;border-radius:6px}</style>
  </head>
  <body>
    <h1>TrainFinder Tester</h1>
    <form method="get" action="/debug/viewport">
      <div>
        <label>.ASPXAUTH cookie value:</label><br/>
        <input style="width:600px" name="cookie" placeholder="paste ONLY the hex value (no .ASPXAUTH=)" />
        <div style="color:#555">You can also set env var <code>TF_AUTH_COOKIE</code> on Render, or send header <code>X-TF-ASPXAUTH</code>.</div>
      </div>
      <p/>
      <div>
        <label>lat</label>
        <input name="lat" value="-33.8688"/>
        <label>lng</label>
        <input name="lng" value="151.2093"/>
        <label>zm</label>
        <input name="zm" value="12"/>
      </div>
      <p/>
      <button>Test /debug/viewport</button>
    </form>

    <p/>
    <p><a href="/authcheck">/authcheck</a> (will use cookie from the field, header, or env)</p>
    <p><a href="/scan">/scan</a> (tests five cities × 3 zooms)</p>
  </body>
</html>
"""

@app.get("/try")
def try_page():
    return Response(TRY_HTML, mimetype="text/html")

@app.get("/authcheck")
def authcheck():
    token = get_cookie_from_request()
    sess = make_session(token)
    r = sess.post(f"{TF_BASE}{API_ISLOGGEDIN_PATH}", data={}, timeout=20)
    out = {
        "status": r.status_code,
        "ms": r.elapsed.total_seconds() * 1000.0,
        "cookie_present": bool(token),
        "text": r.text,
        "bytes": len(r.content),
    }
    # Try to pick email and value
    try:
        j = r.json()
        out["is_logged_in"] = bool(j.get("is_logged_in"))
        out["email"] = j.get("email_address", "")
    except Exception:
        pass
    return jsonify(out)

@app.get("/debug/viewport")
def debug_viewport():
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(request.args.get("zm", "12"))

    token = get_cookie_from_request()
    sess = make_session(token)

    warm = warmup_and_token(sess, lat, lng, zm)
    bounds = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)

    attempts, winner = tf_post_viewport(sess, bounds, zm, warm.get("token"))

    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "bounds": bounds,
        "tf": {
            "used_cookie": bool(token),
            "warmup": {"status": warm["status"], "bytes": warm["bytes"], "ms": None},
            "verification_token_present": bool(warm.get("token")),
            "viewport": {
                "attempts": attempts,
                "winner": ("none" if winner is None else winner),
                "response": (attempts[winner]["resp"] if winner is not None else attempts[-1]["resp"])
            }
        }
    })

@app.get("/scan")
def scan():
    token = get_cookie_from_request()
    sess = make_session(token)

    cities = [
        ("Sydney",   -33.8688, 151.2093),
        ("Melbourne",-37.8136, 144.9631),
        ("Brisbane", -27.4698, 153.0251),
        ("Perth",    -31.9523, 115.8613),
        ("Adelaide", -34.9285, 138.6007),
    ]
    zooms = [11, 12, 13]
    results = []

    for name, lat, lng in cities:
        # warm up each city once at the middle zoom to harvest token/cookies
        warm = warmup_and_token(sess, lat, lng, 12)
        token_v = warm.get("token")
        for zm in zooms:
            b = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)
            attempts, winner = tf_post_viewport(sess, b, zm, token_v)
            last = attempts[-1]["resp"]
            results.append({
                "city": name, "lat": lat, "lng": lng, "zm": zm,
                "viewport_bytes": last["bytes"],
                "looks_like_html": last["looks_like_html"],
                "warmup_bytes": warm["bytes"],
                "winner": ("none" if winner is None else winner)
            })

    return jsonify({"count": len(results), "results": results})
