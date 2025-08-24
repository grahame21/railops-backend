import os
import time
import json
import threading
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

import requests
from flask import Flask, jsonify, make_response
from playwright.sync_api import sync_playwright  # headless browser fallback

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------- Env / Config ----------
ASPXAUTH = os.getenv("ASPXAUTH", "").strip()
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", "60"))
PROXY_URL = os.getenv("PROXY_URL", "").strip()

# Primary referer (lat/lng preferred). You can override with TRAINFINDER_REFERER in Render.
PRIMARY_REFERER = os.getenv(
    "TRAINFINDER_REFERER",
    "https://trainfinder.otenko.com/home/nextlevel?lat=-34.93&lng=138.60&zm=10"  # Adelaide metro default
).strip()

# Useful fallbacks (SA-wide, AU-wide). We’ll try these if the first returns nulls.
FALLBACK_REFERERS = [
    "https://trainfinder.otenko.com/home/nextlevel?lat=-30.0&lng=136.0&zm=6",   # South Australia
    "https://trainfinder.otenko.com/home/nextlevel?lat=-25.5&lng=134.5&zm=6",   # Australia
]

# Build ordered list (avoid duplicates)
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
    Accepts either:
      - ...?lat=..&lng=..&zm=..   (preferred)
      - ...?bbox=w,s,e,n&zm=..
    Returns (zoom:int, (w,s,e,n)) with floats.
    If only lat/lng provided, we approximate a bbox from zoom.
    """
    def approx_bbox_from_latlng(lat, lng, zm):
        # crude but effective bbox size by zoom
        lon_delta = 360 / (2 ** zm)   # degrees
        lat_delta = 170 / (2 ** zm)   # mercator-ish
        return (lng - lon_delta, lat - lat_delta, lng + lon_delta, lat + lat_delta)

    try:
        qs = parse_qs(urlparse(referer).query)
        zm = int(qs.get("zm", [6])[0])

        if "bbox" in qs:
            w, s, e, n = [float(x) for x in qs["bbox"][0].split(",")]
            return zm, (w, s, e, n)

        if "lat" in qs and "lng" in qs:
            lat = float(qs["lat"][0]); lng = float(qs["lng"][0])
            return zm, approx_bbox_from_latlng(lat, lng, zm)

        # final fallback (AU-wide)
        return 6, (112.0, -44.0, 154.0, -9.0)
    except Exception:
        return 6, (112.0, -44.0, 154.0, -9.0)


def _post_viewport(url: str, headers: dict, cookies: dict, payload: dict):
    """POST helper with form-encoded payload."""
    form_headers = headers.copy()
    form_headers["content-type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    return session.post(url, headers=form_headers, cookies=cookies, data=payload, proxies=proxies, timeout=30)


def _is_all_null(obj):
    return obj is None or (isinstance(obj, dict) and all(v is None for v in obj.values()))


def _try_fetch_with_requests(referer: str):
    """
    Fast path: prime ASP.NET session with GET, then POST common payload shapes via requests.
    Returns (data, 'requests:<shape>') or (None, None).
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
        ("empty", {}),
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
            return data, f"requests:{shape_name}"

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
            return data2, f"requests:{shape_name}"

    return None, None


def _try_fetch_with_browser(referer: str):
    """
    Open the map in a real browser, 'wiggle' the map so the site fires its own
    /Home/GetViewPortData XHR, capture that exact response. If the site uses
    anti-forgery tokens, reuse theirs. Falls back to an in-page fetch with token.
    """
    if not ASPXAUTH:
        raise RuntimeError("ASPXAUTH env var is not set")

    launch_kwargs = {"headless": True, "args": ["--no-sandbox"]}
    if PROXY_URL:
        launch_kwargs["proxy"] = {"server": PROXY_URL}

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context()
        # Set auth cookie before navigating
        context.add_cookies([{
            "name": ".ASPXAUTH",
            "value": ASPXAUTH,
            "domain": "trainfinder.otenko.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax"
        }])
        page = context.new_page()
        page.goto(referer, wait_until="domcontentloaded", timeout=30000)

        # Nudge the map to trigger their XHR
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        try:
            box = page.viewport_size or {"width": 1280, "height": 800}
            x = int(box["width"] * 0.5); y = int(box["height"] * 0.5)
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 80, y, steps=12)  # small pan
            page.mouse.up()
            page.wait_for_timeout(600)
            page.mouse.wheel(0, -300)            # slight zoom
            page.wait_for_timeout(600)
        except Exception:
            pass

        # 1) Prefer: capture the site's own POST
        data = None
        try:
            resp = page.wait_for_response(
                lambda r: ("/Home/GetViewPortData" in r.url) and (r.request.method == "POST"),
                timeout=15000
            )
            try:
                data = resp.json()
            except Exception:
                data = None
        except Exception:
            data = None

        # 2) Fallback: do an in-page fetch, include anti-forgery token if present
        if data is None:
            token = None
            try:
                token = page.locator('input[name="__RequestVerificationToken"]').first().evaluate("el => el.value")
            except Exception:
                try:
                    token = page.locator('meta[name="__RequestVerificationToken"]').first().get_attribute("content")
                except Exception:
                    token = None

            js = """
                async (tok) => {
                    const headers = { 'X-Requested-With': 'XMLHttpRequest' };
                    if (tok) headers['RequestVerificationToken'] = tok;
                    try {
                        const res = await fetch('/Home/GetViewPortData', {
                            method: 'POST',
                            credentials: 'include',
                            headers
                        });
                        try { return await res.json(); } catch { return null; }
                    } catch { return null; }
                }
            """
            try:
                data = page.evaluate(js, token)
            except Exception:
                data = None

        context.close(); browser.close()

    if data is not None and not _is_all_null(data):
        return data, "browser:captured"
    return None, None


def fetch_trainfinder():
    """
    Try requests first (faster). If null, try full browser capture.
    Iterate across PRIMARY + FALLBACK referers until one works.
    """
    for ref in REFERERS_TO_TRY:
        try:
            logging.info("Attempt (requests) with referer: %s", ref)
            data, shape = _try_fetch_with_requests(ref)
            if data is not None:
                return data, ref, shape
            logging.warning("Null via requests for %s; will try browser.", ref)

            logging.info("Attempt (browser) with referer: %s", ref)
            data2, shape2 = _try_fetch_with_browser(ref)
            if data2 is not None:
                return data2, ref, shape2
            logging.warning("Null via browser for %s; trying next referer.", ref)
        except Exception as e:
            logging.error("Error for referer %s: %s", ref, e)

    raise RuntimeError("All referers and methods returned null payloads. Check cookie and viewport.")


def background_loop():
    global latest_payload, last_updated, last_success_referer, last_payload_shape
    while True:
        try:
            data, used_ref, shape = fetch_trainfinder()
            with lock:
                latest_payload = data  # passthrough; adapt shape here if your frontend needs a different format
                last_success_referer = used_ref
                last_payload_shape = shape
                last_updated = datetime.now(timezone.utc).isoformat()
            logging.info("Updated trains.json at %s (via %s, referer: %s)", last_updated, shape, used_ref)
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


# Start background fetcher
threading.Thread(target=background_loop, daemon=True).start()
