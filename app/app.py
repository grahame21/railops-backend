# app/app.py
import os
import json
import time
import threading
import logging
from typing import Dict, Any, Optional

import requests
from flask import Flask, jsonify, send_file, make_response

# ------------------------------------------------------------------------------
# Config (via env vars with sane defaults)
# ------------------------------------------------------------------------------
PORT = int(os.environ.get("PORT", "10000"))

# TrainFinder auth + headers
TF_ASPXAUTH = os.environ.get("TF_ASPXAUTH", "").strip()
TF_UA       = os.environ.get("TF_UA", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
# Where you want to "look" on first load (you can change these via env if you like)
INIT_LAT = os.environ.get("INIT_LAT", "-33.86")   # Sydney default
INIT_LNG = os.environ.get("INIT_LNG", "151.21")
INIT_ZM  = os.environ.get("INIT_ZM",  "12")

# Optional bounding box to constrain the viewport (comma separated: s,w,n,e)
# Example: "-35.8,138.4,-34.6,139.0"
BBOX = os.environ.get("BBOX", "").strip()

# Polling interval (seconds)
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "30"))

# Files
TRAINS_PATH = "/app/trains.json"

# External URLs
TF_BASE     = "https://trainfinder.otenko.com"
TF_WARM_URL = f"{TF_BASE}/home/nextlevel?lat={INIT_LAT}&lng={INIT_LNG}&zm={INIT_ZM}"
TF_DATA_URL = f"{TF_BASE}/Home/GetViewPortData"

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="%(levelname)s:railops:%(message)s",
)
log = logging.getLogger("railops")

# ------------------------------------------------------------------------------
# Flask app
# ------------------------------------------------------------------------------
app = Flask(__name__)


@app.get("/")
def root():
    # For Render healthchecks / quick sanity probe
    return jsonify(ok=True)


@app.get("/healthz")
def health():
    exists = os.path.exists(TRAINS_PATH)
    return jsonify(status="ok", trains_ready=exists)


def _nocache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/trains")
def trains_route():
    if not os.path.exists(TRAINS_PATH):
        return jsonify(error="trains file not ready"), 503
    resp = make_response(send_file(TRAINS_PATH, mimetype="application/json"))
    return _nocache(resp)


@app.get("/trains.json")
def trains_json_route():
    return trains_route()


# ------------------------------------------------------------------------------
# TrainFinder poller
# ------------------------------------------------------------------------------
_session: Optional[requests.Session] = None
_poll_thread_started = False


def _session_headers() -> Dict[str, str]:
    # Build headers for both warmup (GET) and data (POST)
    headers = {
        "User-Agent": TF_UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Origin": TF_BASE,
        "Referer": TF_WARM_URL,  # Referer helps the backend understand the viewport context
    }
    if TF_ASPXAUTH:
        headers["Cookie"] = f".ASPXAUTH={TF_ASPXAUTH}"
    return headers


def _warmup(sess: requests.Session) -> None:
    try:
        r = sess.get(TF_WARM_URL, headers=_session_headers(), timeout=20)
        log.info("Warmup GET %s -> %s", TF_WARM_URL, r.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)


def _fetch_once(sess: requests.Session) -> Dict[str, Any]:
    """
    Calls TrainFinder's viewport API and returns parsed JSON (may be empty slots).
    """
    headers = _session_headers()

    # The site typically expects form-encoded fields for viewport state.
    form = {
        "lat": str(INIT_LAT),
        "lng": str(INIT_LNG),
        "zm":  str(INIT_ZM),
    }
    # Provide a bbox if supplied (helps get actual trains when zoomed in enough)
    if BBOX:
        form["bbox"] = BBOX

    r = sess.post(TF_DATA_URL, headers=headers, data=form, timeout=30)
    log.info("POST %s (lat=%s,lng=%s,zm=%s%s) -> %s",
             TF_DATA_URL, INIT_LAT, INIT_LNG, INIT_ZM,
             f",bbox={BBOX}" if BBOX else "", r.status_code)

    r.raise_for_status()
    # Some responses are JSON; some can be JSON wrapped in text
    try:
        data = r.json()
    except Exception:
        data = json.loads(r.text)

    # Helpful visibility in logs
    if isinstance(data, dict):
        log.info("Sample JSON keys: %s", list(data.keys())[:8])

    return data


def _write_trains_file(data: Dict[str, Any]) -> None:
    # You might restructure data here into a slimmer schema for the frontend.
    with open(TRAINS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    log.info("wrote %s", TRAINS_PATH)


def _poll_forever():
    global _session
    sess = requests.Session()
    _session = sess

    # One warm-up so Referer page is “visited”
    _warmup(sess)

    while True:
        try:
            data = _fetch_once(sess)
            _write_trains_file(data)
        except Exception as e:
            log.exception("refresher error: %s", e)
        time.sleep(REFRESH_SECONDS)


def _start_poller_once():
    global _poll_thread_started
    if _poll_thread_started:
        return
    _poll_thread_started = True
    t = threading.Thread(target=_poll_forever, name="trainfinder-poller", daemon=True)
    t.start()


# ------------------------------------------------------------------------------
# App startup hook
# ------------------------------------------------------------------------------
@app.before_first_request
def _on_first_request():
    _start_poller_once()


# If you run locally: python app.py
if __name__ == "__main__":
    # Start poller when running the module directly
    _start_poller_once()
    app.run(host="0.0.0.0", port=PORT)