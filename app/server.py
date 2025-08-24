import os
import time
import json
import threading
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

import requests
from flask import Flask, jsonify, make_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ASPXAUTH = os.getenv("ASPXAUTH", "").strip()
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", "60"))
PROXY_URL = os.getenv("PROXY_URL", "").strip()

PRIMARY_REFERER = os.getenv(
    "TRAINFINDER_REFERER",
    "https://trainfinder.otenko.com/home/nextlevel?zm=6&bbox=112.0,-44.0,154.0,-9.0"  # AU-wide default
).strip()

FALLBACK_REFERERS = [
    "https://trainfinder.otenko.com/home/nextlevel?zm=6&bbox=129.0,-38.5,141.5,-25.5",  # SA-wide
    "https://trainfinder.otenko.com/home/nextlevel?zm=7&bbox=134.0,-35.9,141.0,-28.0",  # Adelaide corridor
]

REFERERS_TO_TRY = [PRIMARY_REFERER] + [r for r in FALLBACK_REFERERS if r != PRIMARY_REFERER]

proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
session = requests.Session()

latest_payload = {"status": "starting"}
last_updated = None
last_success_referer = None
last_payload_shape = None
lock = threading.Lock()


def _parse_referer_viewport(referer: str):
    """
    Extract zm and bbox=minlon,minlat,maxlon,maxlat from the referer query string.
    Returns (zoom:int, (w,s,e,n)) with floats. If missing, returns sensible defaults.
    """
    try:
        qs = parse_qs(urlparse(referer).query)
        zm = int(qs.get("zm", [6])[0])
        bbox_str = qs.get("bbox", ["112.0,-44.0,154.0,-9.0"])[0]
        parts = [float(x) for x in bbox_str.split(",")]
        if len(parts) == 4:
            w, s, e, n = parts
        else:
            w, s, e, n = 112.0, -44.0, 154.0, -9.0
        return zm, (w, s, e, n)
    except Exception:
        return 6, (112.0, -44.0, 154.0, -9.0)


def _post_viewport(url: str, headers: dict, cookies: dict, payload: dict):
    """POST helper with form-encoded payload."""
    form_headers = headers.copy()
    form_headers["content-type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    return session.post(url, headers=form_headers, cookies=cookies, data=payload, proxies=proxies, timeout=30)


def _is_all_null(obj):
    return obj is None or (isinstance(obj, dict) and all(v is None for v in obj.values()))


def _try_fetch_with_referer(referer: str):
    """
    1) GET NextLevel (primes ASP.NET session).
    2) Try several POST body shapes to /Home/GetViewPortData using the same session.
    Returns (data, payload_shape) or (None, None) if still null.
    Raises on HTTP/network errors.
    """
    if not ASPXAUTH:
        raise RuntimeError("ASPXAUTH env var is not set")

    zm, (w, s, e, n) = _parse_referer_viewport(referer)

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

    # 2) Try payload shapes
    url = "https://trainfinder.otenko.com/Home/GetViewPortData"
    payloads = [
        ("bbox_zm", {"bbox": f"{w},{s},{e},{n}", "zm": str(zm)}),
        ("bounds_zoom", {"bounds": f"{w},{s},{e},{n}", "zoom": str(zm)}),
        ("nsew_zoom", {"north": str(n), "south": str(s), "east": str(e), "west": str(w), "zoom": str(zm)}),
        ("vp_combo", {"vp": f"{w},{s},{e},{n}|{zm}"}),
        ("empty", {}),  # last resort: some builds use empty body
    ]

    for shape_name, payload in payloads:
        r = _post_viewport(url, xhr_headers, cookies, payload)
        logging.info("POST shape=%s HTTP %s", shape_name, r.status_code)
        r.raise_for_status()
        try:
            data = r.json()
        except Exception:
            logging.error("Response not JSON for shape=%s", shape_name)
            data = None

        if not _is_all_null(data):
            return data, shape_name

        # brief retry on same shape
        time.sleep(0.8)
        r2 = _post_viewport(url, xhr_headers, cookies, payload)
        logging.info("Retry shape=%s HTTP %s", shape_name, r2.status_code)
        r2.raise_for_status()
        try:
            data2 = r2.json()
        except Exception:
            logging.error("Retry response not JSON for shape=%s", shape_name)
            data2 = None

        if not _is_all_null(data2):
            return data2, shape_name

    return None, None


def fetch_trainfinder():
    last_error = None
    for idx, ref in enumerate(REFERERS_TO_TRY, start=1):
        try:
            logging.info("Attempt %d with referer: %s", idx, ref)
            data, shape = _try_fetch_with_referer(ref)
            if data is not None:
                return data, ref, shape
            logging.warning("Null payload for %s; trying next referer.", ref)
        except Exception as e:
            last_error = e
            logging.error("Error with referer %s: %s", ref, e)

    if last_error:
        raise RuntimeError(f"All referers failed; last error: {last_error}")
    raise RuntimeError("All referers returned null payloads. Adjust TRAINFINDER_REFERER zoom/bbox.")


def background_loop():
    global latest_payload, last_updated, last_success_referer, last_payload_shape
    while True:
        try:
            data, used_ref, shape = fetch_trainfinder()
            with lock:
                latest_payload = data
                last_success_referer = used_ref
                last_payload_shape = shape
                last_updated = datetime.now(timezone.utc).isoformat()
            logging.info("Updated trains.json at %s (referer used: %s, shape: %s)",
                         last_updated, used_ref, shape)
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
            "payload_shape": last_payload_shape,
            "interval_seconds": UPDATE_INTERVAL_SECONDS
        })


@app.route("/trains.json")
def trains():
    with lock:
        resp = make_response(json.dumps(latest_payload, ensure_ascii=False, separators=(",", ":")))
    resp.mimetype = "application/json"
    return resp


threading.Thread(target=background_loop, daemon=True).start()
