# app/app.py
import os, json, time, logging
from pathlib import Path
from datetime import datetime
import requests
from flask import Flask, request, jsonify, send_file, abort

APP_ROOT = Path(__file__).resolve().parent
DATA_DIR  = APP_ROOT / "static" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TRAINS_JSON_PATH = DATA_DIR / "trains.json"

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# ---------------- Config ----------------
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "").strip()
TF_EXTRA_COOKIES = os.getenv("TF_EXTRA_COOKIES", "").strip()  # e.g. "_ga=GA1.1.123; _ga_X=GS1.1.2; __stripe_mid=abc"
UA_CHROME = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
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

# Optionally attach all other TF cookies you see in DevTools (Application → Cookies)
if TF_EXTRA_COOKIES:
    for part in TF_EXTRA_COOKIES.split(";"):
        part = part.strip()
        if "=" in part:
            name, val = part.split("=", 1)
            name, val = name.strip(), val.strip()
            if name and val:
                session.cookies.set(name, val, domain="trainfinder.otenko.com")

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
    Warm up TF page, then POST viewport request.
    Returns parsed JSON or {} if TF sends 'null'.
    """
    ref = _referer(lat, lng, zm)
    _warmup(lat, lng, zm)

    post_headers = {
        "Referer": ref,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    # Keep the browser-ish headers
    post_headers.update({k: v for k, v in BASE_HEADERS.items() if k not in ("Accept",)})

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
    Normalize TF response into a stable schema.
    We'll keep trains[] empty until we see real TF structure.
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
    return age > max_age_secon
