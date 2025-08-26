import math, os, time, logging, json
from typing import Dict, Tuple, Any, Optional, List
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s",
)
log = logging.getLogger("railops")

# ------------ Config ------------
TF_BASE = "https://trainfinder.otenko.com"
TILE_SIZE = 256.0
VIEW_W = int(os.environ.get("VIEW_W", 900))
VIEW_H = int(os.environ.get("VIEW_H", 600))
DEFAULT_LAT = float(os.environ.get("DEFAULT_LAT", -33.8688))
DEFAULT_LNG = float(os.environ.get("DEFAULT_LNG", 151.2093))
DEFAULT_ZM  = int(os.environ.get("DEFAULT_ZM", 12))
HTTP_TIMEOUT = (10, 20)  # (connect, read)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")

EMPTY_JSON_PREFIXES = (
    '{"favs":null,"alerts":null,"places":null,"tts":null,"webcams":null,"atcsGomi":null,"atcsObj":null}',
    '{"favs":[],"alerts":[],"places":[],"tts":[],"webcams":[],"atcsGomi":[],"atcsObj":[]}',
)

# ------------ Helpers ------------
def to_float(v: Optional[str], default: float) -> float:
    try:
        x = float(v)
        if math.isfinite(x): return x
    except Exception:
        pass
    return default

def to_int(v: Optional[str], default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default

def _latlng_to_world(lat: float, lng: float) -> Tuple[float, float]:
    x = (lng + 180.0) / 360.0 * TILE_SIZE
    siny = math.sin(math.radians(lat))
    siny = min(max(siny, -0.9999), 0.9999)
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * TILE_SIZE
    return x, y

def _world_to_latlng(px: float, py: float) -> Tuple[float, float]:
    lng = px / TILE_SIZE * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * (py / TILE_SIZE)
    lat = math.degrees(math.atan(math.sinh(n)))
    return lat, lng

def compute_bounds(lat: float, lng: float, zm: int, vw: int, vh: int) -> Dict[str, float]:
    scale = 2.0 ** zm
    cx, cy = _latlng_to_world(lat, lng)
    cx *= scale; cy *= scale
    tlx, tly = cx - vw/2.0, cy - vh/2.0
    brx, bry = cx + vw/2.0, cy + vh/2.0
    north_lat, west_lng = _world_to_latlng(tlx / scale, tly / scale)
    south_lat, east_lng = _world_to_latlng(brx / scale, bry / scale)
    return {"north": north_lat, "south": south_lat, "west": west_lng, "east": east_lng}

def _session(auth_cookie: Optional[str]) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, */*;q=0.1",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8,en-AU;q=0.7",
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel?lat={DEFAULT_LAT}&lng={DEFAULT_LNG}&zm={DEFAULT_ZM}",
        "X-Requested-With": "XMLHttpRequest",
        "Cache-Control": "no-cache",
    })
    if auth_cookie:
        s.cookies.set(".ASPXAUTH", auth_cookie, domain="trainfinder.otenko.com", secure=True)
    return s

def _get_auth_cookie_from_request() -> Optional[str]:
    hdr = request.headers.get("X-TF-ASPXAUTH")
    if hdr and hdr.strip():
        return hdr.strip()
    env = os.environ.get("TF_AUTH_COOKIE", "").strip()
    return env or None

def looks_empty(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    for p in EMPTY_JSON_PREFIXES:
        if t.startswith(p):
            return True
    return False

# ------------ Upstream calls ------------
def warmup(s: requests.Session, lat: float, lng: float, zm: int) -> Dict[str, Any]:
    url = f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    t0 = time.time()
    r = s.get(url, timeout=HTTP_TIMEOUT)
    dt = int((time.time()-t0)*1000)
    log.info(f"Warmup GET {url} -> {r.status_code}; bytes={len(r.content)}")
    return {"status": r.status_code, "bytes": len(r.content), "ms": dt}

def tf_is_logged_in(s: requests.Session) -> Dict[str, Any]:
    url = f"{TF_BASE}/Home/IsLoggedIn"
    t0 = time.time()
    r = s.post(url, data=b"", timeout=HTTP_TIMEOUT)
    dt = int((time.time()-t0)*1000)
    is_logged_in = False; email = ""; j = None; raw = r.text.strip()
    try:
        j = r.json()
        is_logged_in = bool(j.get("is_logged_in", False))
        email = (j.get("email_address") or "") if isinstance(j, dict) else ""
    except Exception:
        pass
    return {
        "status": r.status_code,
        "ms": dt,
        "bytes": len(r.content),
        "json": j,
        "text": (raw[:200]+"…") if len(raw) > 200 else raw,
        "is_logged_in": is_logged_in,
        "email": email,
    }

def _post_viewport(s: requests.Session, form: Dict[str, str]) -> Dict[str, Any]:
    url = f"{TF_BASE}/Home/GetViewPortData"
    t0 = time.time()
    r = s.post(url, data=form, timeout=HTTP_TIMEOUT)
    dt = int((time.time()-t0)*1000)
    preview = r.text.strip()
    looks_html = preview.lstrip().startswith("<!DOCTYPE html") or "<html" in preview[:200].lower()
    if len(preview) > 200:
        preview = preview[:200] + "…"
    log.info(f"POST GetViewPortData {form} -> {r.status_code}; bytes={len(r.content)}")
    return {
        "status": r.status_code,
        "ms": dt,
        "bytes": len(r.content),
        "looks_like_html": looks_html,
        "preview": preview,
        "raw": r.text,  # keep raw for emptiness check
    }

def tf_get_viewport_data(s: requests.Session, lat: float, lng: float, zm: int, bounds: Dict[str, float]) -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []

    # Attempt A: lat/lng/zm
    a_form = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}
    a = _post_viewport(s, a_form); attempts.append({"form": a_form, "resp": {k:v for k,v in a.items() if k!='raw'}})
    if a["status"] == 200 and not looks_empty(a["raw"]):
        return {"winner": "latlng", "attempts": attempts, "response": {k:v for k,v in a.items() if k!='raw'}}

    # Attempt B: bounds north/south/west/east (+zm)
    b_form = {
        "north": f"{bounds['north']:.6f}",
        "south": f"{bounds['south']:.6f}",
        "west":  f"{bounds['west']:.6f}",
        "east":  f"{bounds['east']:.6f}",
        "zm": str(zm),
    }
    b = _post_viewport(s, b_form); attempts.append({"form": b_form, "resp": {k:v for k,v in b.items() if k!='raw'}})
    if b["status"] == 200 and not looks_empty(b["raw"]):
        return {"winner": "bounds_nsew", "attempts": attempts, "response": {k:v for k,v in b.items() if k!='raw'}}

    # Attempt C: alternate names (ne/sw)
    c_form = {
        "neLat": f"{bounds['north']:.6f}", "neLng": f"{bounds['east']:.6f}",
        "swLat": f"{bounds['south']:.6f}", "swLng": f"{bounds['west']:.6f}",
        "zm": str(zm),
    }
    c = _post_viewport(s, c_form); attempts.append({"form": c_form, "resp": {k:v for k,v in c.items() if k!='raw'}})
    if c["status"] == 200 and not looks_empty(c["raw"]):
        return {"winner": "bounds_nesw", "attempts": attempts, "response": {k:v for k,v in c.items() if k!='raw'}}

    # if still empty, return last attempt info
    return {"winner": "none", "attempts": attempts, "response": {k:v for k,v in c.items() if k!='raw'}}

def fetch_viewport(lat: float, lng: float, zm: int) -> Dict[str, Any]:
    cookie = _get_auth_cookie_from_request()
    s = _session(cookie)
    warm = warmup(s, lat, lng, zm)
    bounds = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)
    vp = tf_get_viewport_data(s, lat, lng, zm, bounds)
    used_cookie = bool(cookie)
    return {"warmup": warm, "used_cookie": used_cookie, "bounds": bounds, "viewport": vp}

# ------------ Routes ------------
@app.get("/authcheck")
def authcheck():
    cookie = _get_auth_cookie_from_request()
    info = tf_is_logged_in(_session(cookie))
    return jsonify({
        "status": info["status"],
        "ms": info["ms"],
        "bytes": info["bytes"],
        "cookie_present": bool(cookie),
        "is_logged_in": info["is_logged_in"],
        "email": info["email"],
        "text": info["text"],
    }), 200

@app.get("/debug/viewport")
def debug_viewport():
    lat = to_float(request.args.get("lat"), DEFAULT_LAT)
    lng = to_float(request.args.get("lng"), DEFAULT_LNG)
    zm  = to_int(request.args.get("zm"),  DEFAULT_ZM)
    zm = max(1, min(22, zm))

    tf = fetch_viewport(lat, lng, zm)

    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "bounds": tf["bounds"],
        "tf": {k:v for k,v in tf.items() if k != "bounds"}
    }), 200

@app.get("/scan")
def scan():
    cities = [
        ("Sydney",-33.8688,151.2093),
        ("Melbourne",-37.8136,144.9631),
        ("Brisbane",-27.4698,153.0251),
        ("Perth",-31.9523,115.8613),
        ("Adelaide",-34.9285,138.6007),
    ]
    zooms = [11,12,13]
    results = []
    for name, lat, lng in cities:
        for z in zooms:
            try:
                tf = fetch_viewport(lat, lng, z)
                vp = tf["viewport"]["response"]
                results.append({
                    "city": name, "lat": lat, "lng": lng, "zm": z,
                    "warmup_bytes": tf["warmup"]["bytes"],
                    "viewport_bytes": vp["bytes"],
                    "looks_like_html": vp["looks_like_html"],
                    "winner": tf["viewport"]["winner"],
                })
            except Exception as ex:
                log.exception("scan error")
                results.append({"city": name, "lat": lat, "lng": lng, "zm": z, "error": str(ex)})
    return jsonify({"count": len(results), "results": results}), 200

@app.get("/")
def root():
    return jsonify({
        "ok": True,
        "message": "Use /try for the tester UI.",
        "routes": ["/try", "/authcheck", "/debug/viewport?lat=..&lng=..&zm=..", "/scan"]
    })

# register tester UI
from .try_ui import bp as try_ui_bp
app.register_blueprint(try_ui_bp)
