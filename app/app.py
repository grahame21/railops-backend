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
TF_EXTRA_COOKIES = os.getenv("TF_EXTRA_COOKIES", "").strip()  # semicolon-separated cookie list from your browser (optional)

UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Default viewport and window size (px) used for bbox
DEFAULT_LAT = float(os.getenv("VIEW_LAT", "-33.8688"))   # Sydney
DEFAULT_LNG = float(os.getenv("VIEW_LNG", "151.2093"))
DEFAULT_ZM  = int(os.getenv("VIEW_ZM", "12"))            # detail shows up >= 11
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

# Attach cookies you supply (optional but helps)
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

# --------------- Token finders ---------------
# HTML patterns (hidden input, meta, JS var)
TOKEN_RE = re.compile(r'name=["\']__RequestVerificationToken["\']\s+value=["\']([^"\']+)["\']', re.IGNORECASE)
META_RE  = re.compile(r'<meta[^>]+(?:name|id)=["\'](?:csrf\-token|xsrf\-token|requestverificationtoken)["\'][^>]*content=["\']([^"\']+)["\']', re.IGNORECASE)
JS_RE    = re.compile(r'RequestVerificationToken["\']?\s*[:=]\s*["\']([^"\']+)["\']', re.IGNORECASE)

# Cookie patterns (ASP.NET Core anti-forgery defaults)
COOKIE_CANDIDATES = (
    "__RequestVerificationToken",
    ".AspNetCore.Antiforgery",   # prefix (random suffix)
    "XSRF-TOKEN", "CSRF-TOKEN",  # common alternates
)

def _extract_token_from(html_full: str) -> str | None:
    """Try multiple token shapes in the full HTML."""
    if html_full:
        for regex in (TOKEN_RE, META_RE, JS_RE):
            m = regex.search(html_full)
            if m:
                return m.group(1)
    return None

def _find_cookie_token() -> tuple[str | None, str | None]:
    """
    Return (cookie_name, cookie_value) for any likely anti-forgery cookie.
    Looks across both the session cookie jar AND the last response cookies.
    """
    # Prefer ASP.NET Core antiforgery cookie (randomized suffix)
    best_name, best_val = None, None
    for c in session.cookies:
        name = c.name
        lname = name.lower()
        if any(k.lower() in lname for k in COOKIE_CANDIDATES) or lname.startswith(".aspnetcore.antiforgery"):
            best_name, best_val = name, c.value
            break
    return best_name, best_val

# --------------- Web Mercator (safe) ---------------
TILE_SIZE = 256.0
MIN_LAT = -85.05112878
MAX_LAT =  85.05112878

def _project(lng: float, lat: float, zoom: int) -> tuple[float, float]:
    lat = max(MIN_LAT, min(MAX_LAT, lat))
    world = TILE_SIZE * (1 << zoom)
    x = (lng + 180.0) / 360.0 * world
    siny = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * world
    return x, y

def _unproject(x: float, y: float, zoom: int) -> tuple[float, float]:
    world = TILE_SIZE * (1 << zoom)
    lng = x / world * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * (y / world)
    lat = math.degrees(math.atan(math.sinh(n)))
    return lng, lat

def compute_bounds(lat: float, lng: float, zoom: int, px_w: int, px_h: int):
    cx, cy = _project(lng, lat, zoom)
    half_w = px_w / 2.0
    half_h = px_h / 2.0
    world = TILE_SIZE * (1 << zoom)

    # pixel bounds (clamped)
    left   = max(0.0, min(world, cx - half_w))
    right  = max(0.0, min(world, cx + half_w))
    top    = max(0.0, min(world, cy - half_h))
    bottom = max(0.0, min(world, cy + half_h))

    west,  north = _unproject(left,  top,    zoom)
    east,  south = _unproject(right, bottom, zoom)

    if east < west:
        east += 360.0

    return {
        "north": north, "south": south, "east": east, "west": west,
        "minLat": min(north, south), "maxLat": max(north, south),
        "minLng": min(west, east),  "maxLng": max(west, east),
        "px": {"left": left, "right": right, "top": top, "bottom": bottom, "world": world}
    }

# --------------- Parse helpers ---------------
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

# --------------- Network helpers ---------------
def _referer(lat: float, lng: float, zm: int) -> str:
    return f"https://trainfinder.otenko.com/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"

def _warmup_sequence(lat: float, lng: float, zm: int) -> str:
    """
    Hit multiple pages to seed cookies and surface any hidden tokens.
    Return concatenated HTML bodies for scanning.
    """
    html_blobs: list[str] = []

    def _get(url: str, ref: str):
        r = session.get(url, headers={"Referer": ref}, timeout=25, allow_redirects=True)
        app.logger.info("Warmup GET %s -> %s; bytes=%s", url, r.status_code, len(r.text or ""))
        html_blobs.append(r.text or "")

    ref0 = _referer(lat, lng, zm)
    _get(ref0, ref0)  # /home/nextlevel
    _get("https://trainfinder.otenko.com/home", ref0)
    _get("https://trainfinder.otenko.com/", ref0)
    _get("https://trainfinder.otenko.com/home/index", ref0)

    return "\n<!-- SPLIT -->\n".join(html_blobs)

def _build_verification_headers(html: str) -> dict:
    """
    Build the right header(s) for ASP.NET anti-forgery:
    - If we have both cookie and form token, send "RequestVerificationToken: cookie:form" (ASP.NET Core).
    - Else if only form token, send it.
    - Also mirror into common alternate header names.
    """
    form_token = _extract_token_from(html)
    cookie_name, cookie_token = _find_cookie_token()

    app.logger.info(
        "Token guess length: %s; cookie token: %s",
        (len(form_token) if form_token else 0),
        (f"{cookie_name}({len(cookie_token)})" if cookie_token else "None")
    )

    headers = {}
    if cookie_token and form_token:
        combo = f"{cookie_token}:{form_token}"
        headers["RequestVerificationToken"] = combo
        headers["X-CSRF-TOKEN"] = combo
        headers["X-XSRF-TOKEN"] = combo
    elif form_token:
        headers["RequestVerificationToken"] = form_token
        headers["X-CSRF-TOKEN"] = form_token
        headers["X-XSRF-TOKEN"] = form_token
    elif cookie_token:
        # Some stacks accept cookie only for simple endpoints; try it.
        headers["RequestVerificationToken"] = cookie_token
        headers["X-CSRF-TOKEN"] = cookie_token
        headers["X-XSRF-TOKEN"] = cookie_token

    return headers

def fetch_viewport(lat: float, lng: float, zm: int) -> dict:
    """
    Warm up several pages, extract anti-forgery tokens, compute bounds,
    then POST a super-set of common field names so the server model binder can hit.
    """
    html = _warmup_sequence(lat, lng, zm)
    vf_headers = _build_verification_headers(html)

    bounds = compute_bounds(lat, lng, zm, VIEW_W, VIEW_H)
    ref = _referer(lat, lng, zm)

    post_headers = {
        "Referer": ref,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        **BASE_HEADERS,
        **vf_headers,
    }

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
    if "RequestVerificationToken" in post_headers:
        form["__RequestVerificationToken"] = post_headers["RequestVerificationToken"].split(":")[-1]

    resp = session.post(
        "https://trainfinder.otenko.com/Home/GetViewPortData",
        data=form,
        headers=post_headers,
        timeout=25,
        allow_redirects=True,
    )
    txt = resp.text.strip()
    app.logger.info(
        "POST GetViewPortData (lat=%.5f,lng=%.5f,zm=%s) -> %s; token=%s; bytes=%s; preview=%r",
        lat, lng, zm, resp.status_code, bool(vf_headers), len(txt), txt[:160]
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
    """Stub mapper: fill when we see real keys."""
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
    html = _warmup_sequence(lat, lng, zm)
    token = _extract_token_from(html)
    cname, ctoken = _find_cookie_token()
    full = request.args.get("full") == "1"
    show = html if full else html[:4096]
    out = (
        f"=== warmup HTML ({'full' if full else 'first 4096 chars'}) ===\n{show}\n\n"
        f"[guessed form token length: {len(token) if token else 0}] "
        f"[cookie token: {cname}({len(ctoken) if ctoken else 0})]"
    )
    return Response(out, mimetype="text/plain")

@app.get("/debug/tokens")
def debug_tokens():
    html = _warmup_sequence(DEFAULT_LAT, DEFAULT_LNG, DEFAULT_ZM)
    t = _extract_token_from(html)
    cname, ctoken = _find_cookie_token()
    return jsonify({
        "warmup_concat_len": len(html),
        "form_token_len": (len(t) if t else 0),
        "cookie_token_name": cname,
        "cookie_token_len": (len(ctoken) if ctoken else 0),
        "cookie_names": [c.name for c in session.cookies if c.domain.endswith("otenko.com")],
    })

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
        "note": "Warms multiple pages; supports ASP.NET Core token format cookie:form; sends many bbox aliases."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
