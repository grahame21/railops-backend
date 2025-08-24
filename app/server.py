import os
import time
import json
import threading
import logging
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, make_response

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------- Env / Config ----------
ASPXAUTH = os.getenv("ASPXAUTH", "").strip()
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", "60"))
PROXY_URL = os.getenv("PROXY_URL", "").strip()

# Primary referer (if you set TRAINFINDER_REFERER in Render, we’ll try it first)
PRIMARY_REFERER = os.getenv(
    "TRAINFINDER_REFERER",
    "https://trainfinder.otenko.com/home/nextlevel?zm=6&bbox=112.0,-44.0,154.0,-9.0"  # AU-wide default
).strip()

# Useful fallbacks (SA-wide and Adelaide corridor). We’ll try these if the first returns nulls.
FALLBACK_REFERERS = [
    "https://trainfinder.otenko.com/home/nextlevel?zm=6&bbox=129.0,-38.5,141.5,-25.5",  # South Australia
    "https://trainfinder.otenko.com/home/nextlevel?zm=7&bbox=134.0,-35.9,141.0,-28.0",  # Adelaide corridor
]

# Build ordered list (avoid duplicates)
REFERERS_TO_TRY = [PRIMARY_REFERER] + [r for r in FALLBACK_REFERERS if r != PRIMARY_REFERER]

proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
session = requests.Session()

latest_payload = {"status": "starting"}
last_updated = None
last_success_referer = None
lock = threading.Lock()


def _try_fetch_with_referer(referer: str):
    """
    1) GET the NextLevel page (primes ASP.NET session with viewport)
    2) POST the XHR to GetViewPortData using the same session/cookies
    3) If we get an all-null payload, retry the POST once after a short pause
    Returns JSON dict on success, or None if still null.
    Raises on HTTP/network issues.
    """
    if not ASPXAUTH:
        raise RuntimeError("ASPXAUTH env var is not set")

    browser_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
    }
    xhr_headers = {
        "accept": "*/*",
        "x-requested-with": "XMLHttpRequest",
        "referer": referer,
        "origin": "https://trainfinder.otenko.com",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "user-agent": browser_headers["user-agent"],
    }
    cookies = {".ASPXAUTH": ASPXAUTH}

    # 1) Prime session/viewport
    g = session.get(referer, headers=browser_headers, cookies=cookies, proxies=proxies, timeout=30)
    g.raise_for_status()

    # 2) XHR call
    url = "https://trainfinder.otenko.com/Home/GetViewPortData"
    r = session.post(url, headers=xhr_headers, cookies=cookies, data=b"", proxies=proxies, timeout=30)
    logging.info("TrainFinder HTTP %s (referer zm/bbox used)", r.status_code)
    r.raise_for_status()

    def is_all_null(obj):
        return obj is None or (isinstance(obj, dict) and all(v is None for v in obj.values()))

    try:
        data = r.json()
    except Exception:
        logging.error("Response not JSON")
        return None

    if not is_all_null(data):
        return data

    # brief retry on same referer
    time.sleep(1.0)
    r2 = session.post(url, headers=xhr_headers, cookies=cookies, data=b"", proxies=proxies, timeout=30)
    logging.info("TrainFinder retry HTTP %s (same referer)", r2.status_code)
    r2.raise_for_status()
    try:
        data2 = r2.json()
    except Exception:
        logging.error("Retry response not JSON")
        return None

    return None if is_all_null(data2) else data2


def fetch_trainfinder():
    """
    Try PRIMARY_REFERER first, then fallbacks.
    Return first non-null payload or raise if all attempts fail.
    """
    last_error = None
    for idx, ref in enumerate(REFERERS_TO_TRY, start=1):
        try:
            logging.info("Attempt %d using referer: %s", idx, ref)
            data = _try_fetch_with_referer(ref)
            if data is not None:
                return data, ref
            logging.warning("Null payload with referer %s; trying next.", ref)
        except Exception as e:
            last_error = e
            logging.error("Error with referer %s: %s", ref, e)

    # If we got here, every referer failed or returned null
    if last_error:
        raise RuntimeError(f"All referers failed; last error: {last_error}")
    raise RuntimeError("All referers returned null payloads. Adjust TRAINFINDER_REFERER zoom/bbox.")


def background_loop():
    global latest_payload, last_updated, last_success_referer
    while True:
        try:
            data, used_ref = fetch_trainfinder()
            with lock:
                latest_payload = data  # passthrough; adapt shape here if your frontend needs a different format
                last_success_referer = used_ref
                last_updated = datetime.now(timezone.utc).isoformat()
            logging.info("Updated trains.json at %s (used referer: %s)", last_updated, used_ref)
        except Exception as e:
            logging.error("Fetch cycle error: %s", e)
        time.sleep(UPDATE_INTERVAL_SECONDS)


app = Flask(__name__)


@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/")
def health():
    with lock:
        return jsonify({
            "ok": True,
            "last_updated": last_updated,
            "last_success_referer": last_success_referer,
            "interval_seconds": UPDATE_INTERVAL_SECONDS
        })


@app.route("/trains.json")
def trains():
    with lock:
        resp = make_response(json.dumps(latest_payload, ensure_ascii=False, separators=(",", ":")))
    resp.mimetype = "application/json"
    return resp


# Start background fetcher
threading.Thread(target=background_loop, daemon=True).start()
