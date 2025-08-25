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
TF_EXTRA_COOKIES = os.getenv("TF_EXTRA_COOKIES", "").strip()  # e.g. "_ga=GA1.1.188...; __stripe_mid=abc; ..."
UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
DEFAULT_LAT = float(os.getenv("VIEW_LAT", "-33.8688"))   # Sydney by default
DEFAULT_LNG = float(os.getenv("VIEW_LNG", "151.2093"))
DEFAULT_ZM  = int(os.getenv("VIEW_ZM", "6"))             # 6–7 usually best
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
TOKEN_RE = re.compile(
    r'name=["\']__RequestVerificationToken["\']\s+value=["\']([^"\']+)["\']',
    re.IGNORECASE
)

def _referer(lat: float, lng: float, zm: int) -> str:
    return f"https://trainfinder.otenko.com/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"

def _parse_float(name: str, default: float) -> float:
    val = request.args.get(name)
    if val is None:
        return float(default)
    try:
        return float(str(val).strip())
    except Exception:
        return float(default)

def _parse_int(name: str, default: int) -> int:
    val = request.args.get(name)
    if val is None:
        return int(default)
    s = str(val).strip()
    num = ""
    for ch in s:
        if ch.isdigit() or (ch == "-" and not num):
            num += ch
        else:
            break
    try:
        return int(num) if num else int(default)
    except Exception:
        return int(default)

def _extract_verification_token(html: str) -> str | None:
    # Try hidden input on the page
    m = TOKEN_RE.search(html or "")
    if m:
        return m.group(1)
    # Fallback: sometimes token appears in cookies
    for c in session.cookies:
        if "VerificationToken" in c.name or "RequestVerificationToken" in c.name:
            return c.value
    return None

def _warmup_and_token(lat: float, lng: float, zm: int) -> tuple[int, str | None]:
    ref = _referer(lat, lng, zm)
    h = {"Referer": ref}
    g = session.get(ref, headers=h, timeout=20)
    token = _extract_verification_token(g.text)
    app.logger.info(
        "Warmup GET %s -> %s; token_len=%s",
        ref, g.status_code, (len(token) if token else 0)
    )
    return g.status_code, token

def fetch_viewport(lat: float, lng: float, zm: int) -> dict:
    """
    Warm up TF page, extract anti-forgery token, then POST viewport request.
    Returns parsed JSON or {} if TF sends 'null'.
    """
    _, token = _warmup_and_token(lat, lng, zm)
    ref = _referer(lat, lng, zm)

    post_headers = {
        "Referer": ref,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    # Include RequestVerificationToken header if we found one
    if token:
        post_headers["RequestVerificationToken"] = token

    # Keep the browser-ish headers
    for k, v in BASE_HEADERS.items():
        if k not in post_headers:
            post_headers[k] = v

    form = {"lat": lat, "lng": lng, "zm": zm}
    if token:
        form["__RequestVerificationToken"] = token

    resp = session.post(
        "https://trainfinder.otenko.com/Home/GetViewPortData",
        data=form,
        headers=post_headers,
        timeout=25,
    )
    app.logger.info(
        "POST GetViewPortData (lat=%.6f,lng=%.6f,zm=%s) -> %s; token=%s; bytes=%s; preview=%r",
        lat, lng, zm, resp.status_code, bool(token), len(resp.text), resp.text[:160]
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
    Normalize TF response into a stable schema. We'll fill trains[] later
    once we see a real payload structure from /debug/viewport.
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

def _looks_logged_in(html: str) -> bool:
    lower = (html or "").lower()
    markers = ["log off", "logout", "rules of use", "signed in", "favorites", "favourites"]
    return any(m in lower for m in markers)

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
    names = {c.domain: [ck.name for ck in session.cookies if ck.domain == c.domain] for c in session.cookies}
    return jsonify({"cookies": names})

@app.get("/headers")
def headers_echo():
    return jsonify(dict(session.headers))

@app.get("/authcheck")
def authcheck():
    ref = _referer(DEFAULT_LAT, DEFAULT_LNG, DEFAULT_ZM)
    r = session.get(ref, headers={"Referer": ref}, timeout=20)
    ok = _looks_logged_in(r.text)
    # Show if token exists on the default warmup, too
    token = _extract_verification_token(r.text)
    app.logger.info("Authcheck GET -> %s; logged_in_guess=%s; bytes=%s; token_len=%s",
                    r.status_code, ok, len(r.text), (len(token) if token else 0))
    return jsonify({"status": r.status_code, "logged_in_guess": ok, "bytes": len(r.text), "token_len": (len(token) if token else 0)})

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
    """Return raw TF JSON for a given viewport."""
    lat = _parse_float("lat", DEFAULT_LAT)
    lng = _parse_float("lng", DEFAULT_LNG)
    zm  = _parse_int("zm", DEFAULT_ZM)
    tf = fetch_viewport(lat, lng, zm)
    return (json.dumps(tf, ensure_ascii=False), 200, {"Content-Type": "application/json"})

@app.get("/scan")
def scan():
    """Probe multiple busy viewports (zm 6/7) and write the first non-empty."""
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
        if len(txt) > 200:  # heuristic to dodge the 98-byte "null"
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
            "/trains.json", "/update", "/debug/viewport", "/scan"
        ],
        "note": "App extracts __RequestVerificationToken from warmup page and sends it in POST."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
