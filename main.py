# main.py
import os, re, math, json
from urllib.parse import urlencode
import requests
from flask import Flask, request, jsonify, make_response

app = Flask(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
BASE = "https://trainfinder.otenko.com"
TF_NEXTLEVEL = f"{BASE}/home/nextlevel"
TF_ISLOGGED = f"{BASE}/Home/IsLoggedIn"
TF_VIEWPORT = f"{BASE}/Home/GetViewPortData"

# Keep a single Session so cookies are reused
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})

# ---- Cookie storage (in-memory) ----
ASPXAUTH = {"value": None}

@app.get("/")
def root():
    return (
        "RailOps JSON<br>"
        "1) Set cookie once: /set-aspxauth?value=PASTE_.ASPXAUTH<br>"
        "2) Check: /authcheck<br>"
        "3) Debug: /debug/viewport?lat=-33.8688&lng=151.2093&zm=12<br>"
        "4) Data: /trains?lat=-33.8688&lng=151.2093&zm=12<br>"
    )

@app.get("/set-aspxauth")
def set_cookie():
    v = request.args.get("value", "").strip()
    ok = v and len(v) > 50
    if ok:
        ASPXAUTH["value"] = v
        # set on session for the TF domain
        SESSION.cookies.set(".ASPXAUTH", v, domain="trainfinder.otenko.com", path="/")
    return jsonify({"ok": bool(ok)})

@app.get("/authcheck")
def authcheck():
    cookie_present = ASPXAUTH["value"] is not None
    email = ""
    is_logged_in = False
    text = ""
    status = 200
    try:
        r = SESSION.post(TF_ISLOGGED, headers={
            "Accept":"*/*",
            "X-Requested-With":"XMLHttpRequest",
            "Origin": BASE,
            "Referer": f"{BASE}/home/nextlevel",
        }, data=b"")
        text = r.text
        status = r.status_code
        # Expect: {"is_logged_in":true/false,"email_address":"..."}
        try:
            j = r.json()
            is_logged_in = bool(j.get("is_logged_in"))
            email = j.get("email_address") or ""
        except Exception:
            pass
    except Exception as ex:
        text = f"error: {ex}"
        status = 500
    return jsonify({
        "cookie_present": cookie_present,
        "is_logged_in": is_logged_in,
        "email": email,
        "status": status,
        "text": text
    })

# ----- helpers -----

def extract_verification_token(html: str) -> str | None:
    # hidden input (most common)
    m = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', html, re.I)
    if m: return m.group(1)
    # meta tag variant
    m = re.search(r'<meta\s+name="RequestVerificationToken"\s+content="([^"]+)"', html, re.I)
    if m: return m.group(1)
    # JS assignment variant
    m = re.search(r'__RequestVerificationToken\s*[:=]\s*[\'"]([^\'"]+)[\'"]', html, re.I)
    if m: return m.group(1)
    return None

TILE_SIZE = 256
def _latlng_to_world(lat, lng):
    s = math.sin(lat * math.pi / 180.0)
    x = (lng + 180.0) / 360.0 * TILE_SIZE
    y = (0.5 - math.log((1.0 + s) / (1.0 - s)) / (4.0 * math.pi)) * TILE_SIZE
    return x, y

def _world_to_latlng(x, y):
    lng = x / TILE_SIZE * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * y / TILE_SIZE
    # clamp to avoid overflow at extreme values
    n = max(min(n, 20), -20)
    lat = 180.0 / math.pi * math.atan(0.5 * (math.exp(n) - math.exp(-n)))
    return lat, lng

def compute_bounds(lat, lng, zm, w=800, h=600):
    scale = 2 ** zm
    cx, cy = _latlng_to_world(lat, lng)
    cx *= scale; cy *= scale
    half_w = (w / TILE_SIZE) / 2.0
    half_h = (h / TILE_SIZE) / 2.0
    tlx = cx - half_w; tly = cy - half_h
    brx = cx + half_w; bry = cy + half_h
    west, north = _world_to_latlng(tlx / scale * TILE_SIZE, tly / scale * TILE_SIZE)
    east, south = _world_to_latlng(brx / scale * TILE_SIZE, bry / scale * TILE_SIZE)
    # normalize to (N,W,S,E) same as your earlier logs
    return {
        "north": round(north, 6),
        "west": round(west, 6),
        "south": round(south, 6),
        "east": round(east, 6),
    }

def warmup_and_token(lat, lng, zm):
    # load the page that contains the anti-forgery token, with your auth cookie
    params = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}
    r = SESSION.get(TF_NEXTLEVEL, params=params, headers={
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": TF_NEXTLEVEL,
    })
    html = r.text
    token = extract_verification_token(html) if r.status_code == 200 else None
    return {"status": r.status_code, "bytes": len(html), "token": token, "html": html}

def post_viewport(lat, lng, zm, token, bounds):
    base_headers = {
        "Accept":"*/*",
        "X-Requested-With":"XMLHttpRequest",
        "Origin": BASE,
        "Referer": TF_NEXTLEVEL,
        "RequestVerificationToken": token or "",
    }
    attempts = []

    def one(form):
        rr = SESSION.post(TF_VIEWPORT, data=form, headers=base_headers)
        looks_like_html = rr.headers.get("content-type","").startswith("text/html") or rr.text.strip().startswith("<!")
        rec = {
            "form": form,
            "resp": {
                "status": rr.status_code,
                "bytes": len(rr.content),
                "looks_like_html": bool(looks_like_html),
                "preview": rr.text[:200]
            }
        }
        return rr, rec

    # 1) lat/lng/zm
    rr, rec = one({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)})
    attempts.append(rec)
    if rr.ok and len(rr.content) > 200 and not rec["resp"]["looks_like_html"]:
        return rr, attempts, 0

    # 2) zoomLevel + bounds (W/N/S/E)
    rr, rec = one({
        "west": f'{bounds["west"]:.6f}',
        "north": f'{bounds["north"]:.6f}',
        "south": f'{bounds["south"]:.6f}',
        "east": f'{bounds["east"]:.6f}',
        "zoomLevel": str(zm),
    })
    attempts.append(rec)
    if rr.ok and len(rr.content) > 200 and not rec["resp"]["looks_like_html"]:
        return rr, attempts, 1

    # 3) ne/sw + zoomLevel
    rr, rec = one({
        "neLat": f'{bounds["north"]:.6f}',
        "neLng": f'{bounds["east"]:.6f}',
        "swLat": f'{bounds["south"]:.6f}',
        "swLng": f'{bounds["west"]:.6f}',
        "zoomLevel": str(zm),
    })
    attempts.append(rec)
    if rr.ok and len(rr.content) > 200 and not rec["resp"]["looks_like_html"]:
        return rr, attempts, 2

    return rr, attempts, None

# ----- routes -----

@app.get("/debug/viewport")
def debug_viewport():
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm  = int(request.args.get("zm", "12"))
    except:
        return jsonify({"error":"bad
