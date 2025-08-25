# app/app.py
import os, json, time, math, logging, re
from pathlib import Path
from datetime import datetime
import requests
from flask import Flask, request, jsonify, send_file, Response

APP_ROOT = Path(__file__).resolve().parent
DATA_DIR  = APP_ROOT / "static" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TRAINS_JSON_PATH = DATA_DIR / "trains.json"

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# ---------------- Config ----------------
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "").strip()
TF_EXTRA_COOKIES = os.getenv("TF_EXTRA_COOKIES", "").strip()  # semicolon-separated cookie list
UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Default viewport and window size (px) used for bbox
DEFAULT_LAT = float(os.getenv("VIEW_LAT", "-33.8688"))   # Sydney
DEFAULT_LNG = float(os.getenv("VIEW_LNG", "151.2093"))
DEFAULT_ZM  = int(os.getenv("VIEW_ZM", "12"))            # many layers unlock >= 11
VIEW_W = int(os.getenv("VIEW_W", "1280"))
VIEW_H = int(os.getenv("VIEW_H", "800"))

CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "30"))

# --------------- HTTP session ---------------
session = requests.Session()
BASE_HEADERS = {
    "User-Agent": UA_CHROME,
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://trainfinder.otenko.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not:A-Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
session.headers.update(BASE_HEADERS)

# Attach cookies
if TF_ASPXAUTH:
    session.cookies.set(".ASPXAUTH", TF_ASPXAUTH, domain="trainfinder.otenko.com")
if TF_EXTRA_COOKIES:
    for part in TF_EXTRA_COOKIES.split(";"):
        part = part.strip()
        if "=" in part:
            name, val = part.split("=", 1)
            name, val = name.strip(), val.strip()
            if name and val:
                session.cookies.set(name, val, domain="trainfinder.otenko.com")

# --------------- Helpers ---------------
TOKEN_RE = re.compile(r'name=["\']__RequestVerificationToken["\']\s+value=["\']([^"\']+)["\']', re.IGNORECASE)
META_RE  = re.compile(r'<meta[^>]+(?:name|id)=["\'](?:csrf\-token|xsrf\-token|requestverificationtoken)["\'][^>]*content=["\']([^"\']+)["\']', re.IGNORECASE)
JS_RE    = re.compile(r'RequestVerificationToken["\']?\s*[:=]\s*["\']([^"\']+)["\']', re.IGNORECASE)

TILE_SIZE = 256.0
MIN_LAT = -85.05112878
MAX_LAT =  85.05112878

def _referer(lat: float, lng: float, zm: int) -> str:
    return f"https://trainfinder.otenko.com/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"

def _parse_float(name: str, default: float) -> float:
    val = request.args.get(name)
    if val is None: return float(default)
    try: return float(str(val).strip())
    except Exception: return float(default)

def _parse_int(name: str, default: int) -> int:
    val = request.args.get(name)
    if val is None: return int(default)
    s = str(val).strip()
    num = ""
    for ch in s:
        if ch.isdigit() or (ch == "-" and not num): num += ch
        else: break
    try: return int(num) if num else int(default)
    except Exception: return int(default)

def _warmup(lat: float, lng: float, zm: int) -> tuple[int, str]:
    """GET the page to seed session; return (status, html[:2048])."""
    ref = _referer(lat, lng, zm)
    g = session.get(ref, headers={"Referer": ref}, timeout=20)
    app.logger.info("Warmup GET %s -> %s; bytes=%s", ref, g.status_code, len(g.text or ""))
    return g.status_code, (g.text or "")[:2048]

def _extract_token_from(html: str) -> str | None:
    for regex in (TOKEN_RE, META_RE, JS_RE):
        m = regex.search(html or "")
        if m: return m.group(1)
    # Cookie fallbacks used by some stacks
    for c in session.cookies:
        nm = c.name.lower()
        if any(k in nm for k in ("xsrf", "csrf", "verification", "antiforg")):
            return c.value
    return None

# --- Web Mercator projection utilities (correct + safe) ---
def _project(lng: float, lat: float, zoom: int) -> tuple[float, float]:
    """to pixel coords at zoom z."""
    lat = max(MIN_LAT, min(MAX_LAT, lat))
    world = TILE_SIZE * (1 << zoom)
    x = (lng + 180.0) / 360.0 * world
    siny = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * world
    return x, y

def _unproject(x: float, y: float, zoom: int) -> tuple[float, float]:
    """from pixel coords at zoom z to (lng, lat)."""
    world = TILE_SIZE * (1 << zoom)
    lng = x / world * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * (y / world)
    lat = math.degrees(math.atan(math.sinh(n)))  # no overflow; y∈[0,world] ⇒ n∈[-π,π]
    return lng, lat

def compute_bounds(lat: float, lng: float, zoom: int, px_w: int, px_h: int):
    """Compute geographic bounds (north/south/east/west) for a given center, zoom and viewport size."""
    cx, cy = _project(lng, lat, zoom)
    half_w = px_w / 2.0
    half_h = px_h / 2.0

    world = TILE_SIZE * (1 << zoom)

    # pixel bounds (clamped to world)
    left   = max(0.0, min(world, cx - half_w))
    right  = max(0.0, min(world, cx + half_w))
    top    = max(0.0, min(world, cy - half_h))
    bottom = max(0.0, min(world, cy + half_h))

    west,  north = _unproject(left,  top,    zoom)
    east,  south = _unproject(right, bottom, zoom)

    # handle dateline wrap (not typical for AU, but keep it tidy)
    if east < west:
        east += 360.0

    return {
        "north": north, "south": south, "east": east, "west": west,
        "minLat": min(north, south), "maxLat": max(north, south),
        "minLng": min(west, east),  "maxLng": max(west, east),
        "px": {"left": left, "right": right, "top": top, "bottom": bottom, "world": world}
    }

def fetch_viewport(lat: float, lng: float, zm: int) -> dict:
    """
    Warm up, try to extract any token-ish value (best-effort), compute bounds,
    then POST a super-set of common field names so the server model binder can hit.
    """
    _, html = _warmup(lat, lng, zm)
    token = _extract_token_from(html)
    bounds = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)

    ref = _referer(lat, lng, zm)
    post_headers = {
        "Referer": ref,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    if token:
        post_headers["RequestVerificationToken"] = token
        post_headers.setdefault("X-CSRF-TOKEN", token)
        post_headers.setdefault("X-XSRF-TOKEN", token)
    for k, v in BASE_HEADERS.items():
        if k not in post_headers:
            post_headers[k] = v

    # Primary fields + common aliases
    form = {
        "lat": lat, "lng": lng, "zm": zm, "z": zm,
        # bounds under many aliases
        "n": bounds["north"], "s": bounds["south"], "e": bounds["east"], "w": bounds["west"],
        "north": bounds["north"], "south": bounds["south"], "east": bounds["east"], "west": bounds["west"],
        "minLat": bounds["minLat"], "maxLat": bounds["maxLat"], "minLng": bounds["minLng"], "maxLng": bounds["maxLng"],
        "boundsNE": f"{bounds['north']},{bounds['east']}",
        "boundsSW": f"{bounds['south']},{bounds['west']}",
        "northEastLat": bounds["north"], "northEastLng": bounds["east"],
        "southWestLat": bounds["south"], "southWestLng": bounds["west"],
        "width": VIEW_W, "height": VIEW_H,
    }
    if token:
        form["__RequestVerificationToken"] = token

    resp = session.post(
        "https://trainfinder.otenko.com/Home/GetViewPortData",
        data=form,
        headers=post_headers,
        timeout=25,
    )
    txt = resp.text.strip()
    app.logger.info(
        "POST GetViewPortData (lat=%.5f,lng=%.5f,zm=%s) -> %s; token=%s; bytes=%s; preview=%r",
        lat, lng, zm, resp.status_code, bool(token), len(txt), txt[:160]
    )
    resp.raise_for_status()

    if txt in ("", "null"):
        return {}
    try:
        return resp.json()
    except Exception as e:
        app.logger.warning("JSON parse failed: %s", e)
        return {}

def transform_tf_payload(tf: dict) -> dict:
    """
    Stub mapper: once we see real data at /debug/viewport, we’ll fill trains[].
    """
    now = datetime.utcnow().isoformat() + "Z"
    return {
        "updated": now,
        "source": "trainfinder",
        "viewport": {},
        "trains": [],
        "raw": tf if isinstance(tf, dict) else {}
    }

def write_trains(data: dict):
    tmp = TRAINS_JSON_PATH.with_suffix(".tmp.json")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(TRAINS_JSON_PATH)

def needs_refresh(path: Path, max_age_seconds: int) -> bool:
    if not path.exists(): return True
    age = time.time() - path.stat().st_mtime
    return age > max_age_seconds

# --------------- Routes ---------------
@app.get("/health")
def health():
    return jsonify(ok=True, ts=datetime.utcnow().isoformat()+"Z")

@app.get("/status")
def status():
    info = {
        "ok": True,
        "has_cookie": bool(TF_ASPXAUTH),
        "cookie_len": len(TF_ASPXAUTH),
        "extra_cookies": [c.name for c in session.cookies if c.domain.endswith("otenko.com") and c.name != ".ASPXAUTH"],
        "view": {"lat": DEFAULT_LAT, "lng": DEFAULT_LNG, "zm": DEFAULT_ZM, "w": VIEW_W, "h": VIEW_H},
        "trains_json_exists": TRAINS_JSON_PATH.exists(),
        "trains_json_mtime": (
            datetime.utcfromtimestamp(TRAINS_JSON_PATH.stat().st_mtime).isoformat()+"Z"
            if TRAINS_JSON_PATH.exists() else None
        ),
        "cache_seconds": CACHE_SECONDS,
    }
    return jsonify(info)

@app.get("/cookie/echo")
def cookie_echo():
    names = {c.domain: [ck.name for ck in session.cookies if ck.domain == c.domain] for c in session.cookies}
    return jsonify({"cookies": names})

@app.get("/headers")
def headers_echo():
    return jsonify(dict(session.headers))

@app.get("/authcheck")
def authcheck():
    ref = _referer(DEFAULT_LAT, DEFAULT_LNG, DEFAULT_ZM)
    r = session.get(ref, headers={"Referer": ref}, timeout=20)
    ok = "logout" in (r.text or "").lower() or "rules of use" in (r.text or "").lower()
    return jsonify({"status": r.status_code, "logged_in_guess": ok, "bytes": len(r.text)})

@app.get("/debug/warmup_dump")
def warmup_dump():
    lat = _parse_float("lat", DEFAULT_LAT)
    lng = _parse_float("lng", DEFAULT_LNG)
    zm  = _parse_int("zm", DEFAULT_ZM)
    _, html = _warmup(lat, lng, zm)
    token = _extract_token_from(html)
    out = f"=== first 2048 chars of warmup HTML ===\n{html}\n\n[guessed token length: {len(token) if token else 0}]"
    return Response(out, mimetype="text/plain")

@app.get("/debug/tokens")
def debug_tokens():
    html_len = 0
    try:
        _, html = _warmup(DEFAULT_LAT, DEFAULT_LNG, DEFAULT_ZM)
        html_len = len(html)
        token = _extract_token_from(html)
        tlen = len(token) if token else 0
    except Exception:
        tlen = 0
    cookie_tokens = [
        {"name": c.name, "len": len(c.value)}
        for c in session.cookies
        if any(k in c.name.lower() for k in ("xsrf", "csrf", "verification", "antiforg"))
    ]
    return jsonify({"warmup_html_len": html_len, "token_len": tlen, "cookie_tokens": cookie_tokens})

@app.get("/debug/bounds")
def debug_bounds():
    lat = _parse_float("lat", DEFAULT_LAT)
    lng = _parse_float("lng", DEFAULT_LNG)
    zm  = _parse_int("zm", DEFAULT_ZM)
    b = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)
    return jsonify(b)

@app.get("/trains.json")
def trains_json():
    lat = _parse_float("lat", DEFAULT_LAT)
    lng = _parse_float("lng", DEFAULT_LNG)
    zm  = _parse_int("zm", DEFAULT_ZM)

    if needs_refresh(TRAINS_JSON_PATH, CACHE_SECONDS):
        app.logger.info("Cache expired -> fetching TF viewport")
        tf = fetch_viewport(lat, lng, zm)
        data = transform_tf_payload(tf)
        write_trains(data)
    return send_file(TRAINS_JSON_PATH, mimetype="application/json")

@app.get("/update")
def update_now():
    lat = _parse_float("lat", DEFAULT_LAT)
    lng = _parse_float("lng", DEFAULT_LNG)
    zm  = _parse_int("zm", DEFAULT_ZM)

    tf = fetch_viewport(lat, lng, zm)
    data = transform_tf_payload(tf)
    write_trains(data)
    return jsonify({
        "ok": True,
        "wrote": str(TRAINS_JSON_PATH),
        "counts": {
            "trains": len(data.get("trains", [])),
            "raw_keys": list(data.get("raw", {}).keys()) if isinstance(data.get("raw"), dict) else None
        }
    })

@app.get("/debug/viewport")
def debug_viewport():
    lat = _parse_float("lat", DEFAULT_LAT)
    lng = _parse_float("lng", DEFAULT_LNG)
    zm  = _parse_int("zm", DEFAULT_ZM)
    tf = fetch_viewport(lat, lng, zm)
    return (json.dumps(tf, ensure_ascii=False), 200, {"Content-Type": "application/json"})

@app.get("/scan")
def scan():
    """
    Probe busy AU viewports at zooms 11–13; write first non-empty to trains.json.
    """
    probes = [
        (-33.8688, 151.2093, 11), (-33.8688, 151.2093, 12), (-33.8688, 151.2093, 13),  # Sydney
        (-37.8136, 144.9631, 11), (-37.8136, 144.9631, 12), (-37.8136, 144.9631, 13),  # Melbourne
        (-27.4698, 153.0251, 11), (-27.4698, 153.0251, 12), (-27.4698, 153.0251, 13),  # Brisbane
        (-31.9523, 115.8613, 11), (-31.9523, 115.8613, 12), (-31.9523, 115.8613, 13),  # Perth
        (-34.9285, 138.6007, 11), (-34.9285, 138.6007, 12), (-34.9285, 138.6007, 13),  # Adelaide
    ]
    tried = []
    for lat, lng, zm in probes:
        tf = fetch_viewport(lat, lng, zm)
        txt = json.dumps(tf, ensure_ascii=False)
        tried.append({"lat": lat, "lng": lng, "zm": zm, "bytes": len(txt)})
        if len(txt) > 200:  # heuristic: non-empty payload
            data = transform_tf_payload(tf)
            write_trains(data)
            return jsonify({
                "ok": True,
                "picked": {"lat": lat, "lng": lng, "zm": zm},
                "bytes": len(txt),
                "wrote": str(TRAINS_JSON_PATH),
                "trains_guess": len(data.get("trains", [])),
                "tried": tried
            })
    return jsonify({"ok": False, "message": "All probes looked empty", "tried": tried})

@app.get("/")
def root():
    return jsonify({
        "ok": True,
        "endpoints": [
            "/health", "/status", "/headers", "/cookie/echo", "/authcheck",
            "/debug/warmup_dump", "/debug/tokens", "/debug/bounds",
            "/trains.json", "/update", "/debug/viewport", "/scan"
        ],
        "note": "Correct Web Mercator bounds; sends many bbox aliases; unknown fields are ignored server-side."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
