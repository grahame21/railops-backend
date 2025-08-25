import os, json, time, logging, threading, requests
from urllib.parse import urlparse, parse_qs
from flask import Flask, jsonify, send_file

# ---------- Logging ----------
logging.basicConfig(
    level=getattr(logging, os.getenv("TF_LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(levelname)s:%(name)s:%(message)s",
)
log = logging.getLogger("railops")

# ---------- Env ----------
TF_COOKIE  = os.getenv("TF_ASPXAUTH", "").strip()   # ONLY the value, not ".ASPXAUTH=<...>"
TF_REFERER = os.getenv("TF_REFERER", "").strip()    # e.g. https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=7
TF_UA      = os.getenv("TF_UA", "Mozilla/5.0").strip()

DATA_PATH = "/app/trains.json"
API_WARM  = TF_REFERER or "https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=7"
API_POST  = "https://trainfinder.otenko.com/Home/GetViewPortData"

# ---------- Helpers ----------
def parse_view_from_url(u: str):
    """
    Pull lat/lng/zm from the TF_REFERER URL.
    Returns tuple (lat, lng, zm) as strings, or (None, None, None) if missing.
    """
    try:
        qs = parse_qs(urlparse(u).query)
        lat = (qs.get("lat") or [None])[0]
        lng = (qs.get("lng") or [None])[0]
        zm  = (qs.get("zm")  or [None])[0]
        return lat, lng, zm
    except Exception as e:
        log.warning("Failed to parse lat/lng/zm from referer: %s", e)
        return None, None, None

# ---------- HTTP session ----------
S = requests.Session()
S.headers.update({
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "user-agent": TF_UA or "Mozilla/5.0",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://trainfinder.otenko.com",
    "referer": TF_REFERER or API_WARM,
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "dnt": "1",
})
if TF_COOKIE:
    S.cookies.set(".ASPXAUTH", TF_COOKIE, domain="trainfinder.otenko.com", secure=True)

def warmup():
    """Open the exact map URL (with lat/lng/zm) to set server-side viewport/session."""
    try:
        r = S.get(API_WARM, timeout=20, allow_redirects=True)
        log.info("Warmup GET %s -> %s", API_WARM, r.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

def fetch_raw():
    """
    POST with a small form that includes the map view the server expects.
    If your browser shows different param names in DevTools, we can adjust here.
    """
    warmup()
    lat, lng, zm = parse_view_from_url(API_WARM)
    form = {}
    if lat and lng:
        form.update({"lat": lat, "lng": lng})
    if zm:
        form["zm"] = zm

    try:
        r = S.post(API_POST, data=form or b"", timeout=30)
        log.info("POST %s (form=%s) -> %s", API_POST, form or "{}", r.status_code)
        try:
            js = r.json()
        except Exception:
            log.error("Non-JSON response: %s", r.text[:500])
            return None

        # Log a short sample so we can adapt parsing if needed
        log.info("Sample JSON keys: %s", list(js.keys())[:8] if isinstance(js, dict) else type(js))

        # Heuristic emptiness check
        if not js or (isinstance(js, dict) and all(v in (None, [], {}) for v in js.values())):
            log.warning("Empty-ish payload. Check TF_ASPXAUTH / TF_REFERER (and try a busy area/zoom).")
            log.warning("Sample of JSON: %s", str(js)[:400])
            return js  # return whatever we got so we can inspect downstream

        return js
    except Exception as e:
        log.exception("fetch_raw error: %s", e)
        return None

def extract_trains(js):
    """
    Try common shapes. If the server returns a dict with relevant arrays, pick them up.
    Update this once we see the real schema that contains trains.
    """
    if js is None:
        return []

    # If the API returns a dict with lists, merge any list-like values
    if isinstance(js, dict):
        candidate_lists = []
        for k, v in js.items():
            if isinstance(v, list):
                candidate_lists.extend(v)
        if candidate_lists:
            return candidate_lists

        # Fallback: look for like
