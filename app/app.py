# app/app.py
import os, json, time, logging, re
from pathlib import Path
from datetime import datetime
import requests
from flask import Flask, request, jsonify, send_file

APP_ROOT = Path(__file__).resolve().parent
DATA_DIR  = APP_ROOT / "static" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TRAINS_JSON_PATH = DATA_DIR / "trains.json"

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# ---------------- Config ----------------
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "").strip()
UA_CHROME = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
)
DEFAULT_LAT = float(os.getenv("VIEW_LAT", "-33.8688"))   # Sydney
DEFAULT_LNG = float(os.getenv("VIEW_LNG", "151.2093"))
DEFAULT_ZM  = int(os.getenv("VIEW_ZM", "6"))             # 6–7 usually best
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "30"))

# --------------- HTTP session ---------------
session = requests.Session()

# Core headers used by both GET and POST calls
BASE_HEADERS = {
    "User-Agent": UA_CHROME,
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://trainfinder.otenko.com",
    # Extra browser-y bits; not always required but helps some ASP.NET stacks
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    # Client Hints (static string is fine)
    "sec-ch-ua": '"Google Chrome";v="123", "Chromium";v="123", "Not:A-Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

session.headers.update(BASE_HEADERS)

# Attach cookie
if TF_ASPXAUTH:
    session.cookies.set(".ASPXAUTH", TF_ASPXAUTH, domain="trainfinder.otenko.com")

# --------------- Helpers ---------------
def _referer(lat: float, lng: float, zm: int) -> str:
    return f"https://trainfinder.otenko.com/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"

def _warmup(lat: float, lng: float, zm: int) -> int:
    ref = _referer(lat, lng, zm)
    h = {"Referer": ref}
    g = session.get(ref, headers=h, timeout=20)
    app.logger.info("Warmup GET %s -> %s", ref, g.status_code)
    return g.status_code

def fetch_viewport(lat: float, lng: float, zm: int) -> dict:
    """
    Warm up TrainFinder page, then POST the viewport request.
    Returns parsed JSON ({} if TF returns 'null' or parsing fails).
    """
    ref = _referer(lat, lng, zm)
    _warmup(lat, lng, zm)

    # POST payload as x-www-form-urlencoded
    post_headers = {
        "Referer": ref,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    post_headers.update({k: v for k, v in BASE_HEADERS.items() if k not in ("Accept",)})
    # Accept is already fine; leaving as-is

    resp = session.post(
        "https://trainfinder.otenko.com/Home/GetViewPortData",
        data={"lat": lat, "lng": lng, "zm": zm},
        headers=post_headers,
        timeout=25,
    )
    app.logger.info(
        "POST GetViewPortData (lat=%.6f,lng=%.6f,zm=%s) -> %s; bytes=%s; preview=%r",
        lat, lng, zm, resp.status_code, len(resp.text), resp.text[:160]
    )
    resp.raise_for_status()

    t = resp.text.strip()
    if t == "null" or t == "":
        return {}
    try:
        return resp.json()
    except Exception as e:
        app.logger.warning("JSON parse failed: %s", e)
        return {}

def transform_tf_payload(tf: dict) -> dict:
    """
    Normalize the TF response into a stable schema:
      { updated, source, viewport, trains[], raw }
    For now, we leave trains[] empty and keep raw so you can inspect it.
    Once you share a sample of /debug/viewport, we’ll fill trains[].
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
    if not path.exists():
        return True
    age = time.time() - path.stat().st_mtime
    return age > max_age_seconds

def looks_like_logged_in(html: str) -> bool:
    """
    Heuristic: if we're authenticated the HTML often contains things like
    'Log off' / 'Logout' / a profile name / rules page that only appears post-login.
    Adjust this if you see a unique marker on your account.
    """
    markers = [
        "Log off", "Logout", "My Account", "Rules of Use", "Signed in",
        "TrainFinder", "Your Account", "Favorites",
    ]
    lower = html.lower()
    return any(m.lower() in lower for m in markers)

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
        "cookie_head": TF_ASPXAUTH[:12] + "..." if TF_ASPXAUTH else None,
        "view": {"lat": DEFAULT_LAT, "lng": DEFAULT_LNG, "zm": DEFAULT_ZM},
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
    """
    Debug: show which cookies this server will send to trainfinder.otenko.com
    (only the names, not values). Helps confirm .ASPXAUTH is present.
    """
    names = [c.name for c in session.cookies if c.domain.endswith("otenko.com")]
    return jsonify({"cookies_for_otenko": names})

@app.get("/authcheck")
def authcheck():
    """
    Fetch a page that should look different when logged in (rules / nextlevel).
    We don't expose the HTML; we just run a heuristic to decide if it looks logged in.
    """
    ref = _referer(DEFAULT_LAT, DEFAULT_LNG, DEFAULT_ZM)
    h = {"Referer": ref}
    r = session.get(ref, headers=h, timeout=20)
    ok = looks_like_logged_in(r.text)
    app.logger.info("Authcheck GET -> %s; logged_in_guess=%s; bytes=%s",
                    r.status_code, ok, len(r.text))
    return jsonify({"status": r.status_code, "logged_in_guess": ok, "bytes": len(r.text)})

@app.get("/trains.json")
def trains_json():
    """
    Serve cached trains; auto-refresh if file is too old (> CACHE_SECONDS).
    """
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm = int(request.args.get("zm", DEFAULT_ZM))

    if needs_refresh(TRAINS_JSON_PATH, CACHE_SECONDS):
        app.logger.info("Cache expired -> fetching TF viewport")
        tf = fetch_viewport(lat, lng, zm)
        data = transform_tf_payload(tf)
        write_trains(data)
    return send_file(TRAINS_JSON_PATH, mimetype="application/json")

@app.get("/update")
def update_now():
    """
    Force an immediate fetch (useful for manual refresh or CI pings).
    """
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm = int(request.args.get("zm", DEFAULT_ZM))

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
    """
    Raw JSON passthrough of TF response (no transform).
    """
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm  = int(request.args.get("zm", DEFAULT_ZM))
    tf = fetch_viewport(lat, lng, zm)
    return (json.dumps(tf, ensure_ascii=False), 200, {"Content-Type": "application/json"})

@app.get("/scan")
def scan():
    """
    Try multiple busy viewports (zm 6/7 across major cities).
    Writes trains.json with the first non-empty result.
    """
    probes = [
        (-33.8688, 151.2093, 6),  # Sydney
        (-33.8688, 151.2093, 7),
        (-37.8136, 144.9631, 6),  # Melbourne
        (-37.8136, 144.9631, 7),
        (-27.4698, 153.0251, 6),  # Brisbane
        (-27.4698, 153.0251, 7),
        (-31.9523, 115.8613, 6),  # Perth
        (-31.9523, 115.8613, 7),
        (-34.9285, 138.6007, 6),  # Adelaide
        (-34.9285, 138.6007, 7),
    ]
    tried = []
    for lat, lng, zm in probes:
        tf = fetch_viewport(lat, lng, zm)
        txt = json.dumps(tf, ensure_ascii=False)
        tried.append({"lat": lat, "lng": lng, "zm": zm, "bytes": len(txt)})
        if len(txt) > 200:  # heuristic to dodge the "null shell"
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
            "/health", "/status", "/cookie/echo", "/authcheck",
            "/trains.json", "/update", "/debug/viewport", "/scan"
        ]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
