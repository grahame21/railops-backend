# app.py
import os
import json
import time
import threading
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from flask import Flask, jsonify, send_file, request, render_template, abort, Response

# -----------------------------------------------------------------------------
# Flask app
# -----------------------------------------------------------------------------
app = Flask(
    __name__,
    static_folder="static",      # serve /static/*
    template_folder="templates"  # look for dashboard.html here if you have it
)

log = logging.getLogger("railops")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(levelname)s:%(name)s:%(message)s"
)

# -----------------------------------------------------------------------------
# Config / Env
# -----------------------------------------------------------------------------
# TrainFinder
TF_BASE = "https://trainfinder.otenko.com"
TF_AUTH = os.getenv("TF_ASPXAUTH", "").strip()  # cookie value for .ASPXAUTH
TF_UA = os.getenv("TF_UA", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
# Optional: if you want to force a specific warmup URL; otherwise we build one from lat/lng/zm
TF_REFERER_URL = os.getenv("TF_REFERER_URL", "").strip()

# Refresh cadence
REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "30"))

# Default viewport if none provided by query
DEFAULT_LAT = os.getenv("DEFAULT_LAT", "-33.86")
DEFAULT_LNG = os.getenv("DEFAULT_LNG", "151.21")
DEFAULT_ZM  = os.getenv("DEFAULT_ZM",  "7")

# Storage paths
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR  # keep alongside app.py so Render logs show it in /app
TRAINS_JSON_PATH = DATA_DIR / "trains.json"

# -----------------------------------------------------------------------------
# HTTP session with headers/cookies
# -----------------------------------------------------------------------------
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": TF_UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": TF_REFERER_URL if TF_REFERER_URL else f"{TF_BASE}/home/nextlevel"
    })
    if TF_AUTH:
        # .ASPXAUTH cookie name used by TrainFinder
        s.cookies.set(".ASPXAUTH", TF_AUTH, domain="trainfinder.otenko.com", path="/")
    return s

# -----------------------------------------------------------------------------
# TrainFinder fetch
# -----------------------------------------------------------------------------
def build_referer(lat: str, lng: str, zm: str) -> str:
    """A clean Referer URL (no 'TF_REFERER=' prefix)."""
    if TF_REFERER_URL:
        return TF_REFERER_URL
    return f"{TF_BASE}/home/nextlevel?lat={lat}&lng={lng}&zm={zm}"

def fetch_trains(lat: str, lng: str, zm: str, bbox: Optional[str] = None) -> Dict[str, Any]:
    """
    Warm up the site with a GET (Referer), then POST to GetViewPortData.
    Returns raw JSON dict from TrainFinder.
    """
    sess = make_session()

    # Warmup GET
    ref = build_referer(lat, lng, zm)
    try:
        r_get = sess.get(ref, timeout=20)
        log.info("Warmup GET %s -> %s", ref, r_get.status_code)
    except Exception as e:
        log.warning("Warmup failed: %s", e)

    # POST payload
    form = {"lat": lat, "lng": lng, "zm": zm}
    if bbox:
        # bbox format: "south,west,north,east"
        form["bbox"] = bbox

    # Ensure Referer header points to the warmup viewport
    sess.headers["Referer"] = ref

    url = f"{TF_BASE}/Home/GetViewPortData"
    r = sess.post(url, data=form, timeout=30)
    log.info("POST %s (form=%s) -> %s", url, {k: form[k] for k in form}, r.status_code)
    r.raise_for_status()
    data = r.json()

    # Debug what keys we actually see
    if isinstance(data, dict):
        log.info("Sample JSON keys: %s", list(data.keys()))
        # Some TF responses put objects under 'atcsObj' or similar; keep raw
    else:
        log.warning("Unexpected JSON shape: %s", type(data))

    return data

def write_trains_file(payload: Dict[str, Any]) -> int:
    """Write raw JSON; return a simple 'count' heuristic if available."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRAINS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    # Try to derive a count from known keys (best-effort)
    count = 0
    if isinstance(payload, dict):
        # If ATCS objects present as dict with trains keyed, try length
        for key in ("atcsObj", "trains", "objects"):
            val = payload.get(key)
            if isinstance(val, (list, dict)):
                count = len(val)
                break
    log.info("wrote %s with %d trains", str(TRAINS_JSON_PATH), count)
    return count

# -----------------------------------------------------------------------------
# Background refresher (optional)
# -----------------------------------------------------------------------------
_stop_flag = threading.Event()

def _refresher():
    # Use defaults unless overridden via environment
    lat = DEFAULT_LAT
    lng = DEFAULT_LNG
    zm  = DEFAULT_ZM
    bbox = os.getenv("DEFAULT_BBOX", "").strip() or None

    while not _stop_flag.is_set():
        try:
            data = fetch_trains(lat, lng, zm, bbox=bbox)
            write_trains_file(data)
        except Exception as e:
            log.exception("refresher error: %s", e)
        _stop_flag.wait(REFRESH_SECONDS)

# Start thread unless disabled
if os.getenv("DISABLE_REFRESHER", "").lower() not in ("1", "true", "yes"):
    t = threading.Thread(target=_refresher, name="refresher", daemon=True)
    t.start()

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
def root_ok():
    return Response("ok, true", mimetype="text/plain")

@app.get("/trains")
def get_trains_now():
    """
    On-demand refresh based on query params:
      /trains?lat=-33.86&lng=151.21&zm=12&bbox=-35.8,138.4,-34.6,139.0
    If no params, returns the last written trains.json (or fetches with defaults if missing).
    """
    lat = request.args.get("lat", "").strip()
    lng = request.args.get("lng", "").strip()
    zm  = request.args.get("zm", "").strip()
    bbox = request.args.get("bbox", "").strip() or None

    # If full viewport specified, fetch fresh
    if lat and lng and zm:
        try:
            data = fetch_trains(lat, lng, zm, bbox=bbox)
            write_trains_file(data)
            return jsonify(data)
        except Exception as e:
            log.exception("on-demand fetch failed: %s", e)
            return jsonify({"error": str(e)}), 500

    # Otherwise, serve the last snapshot (or fetch with defaults on first run)
    if TRAINS_JSON_PATH.exists():
        return send_file(TRAINS_JSON_PATH, mimetype="application/json")

    # No file yet — fetch with defaults
    try:
        data = fetch_trains(DEFAULT_LAT, DEFAULT_LNG, DEFAULT_ZM, bbox=os.getenv("DEFAULT_BBOX"))
        write_trains_file(data)
        return jsonify(data)
    except Exception as e:
        log.exception("initial fetch failed: %s", e)
        return jsonify({"error": str(e)}), 500

@app.get("/data/trains.json")
def data_trains_json():
    """Static JSON endpoint the frontend can poll."""
    if not TRAINS_JSON_PATH.exists():
        return jsonify({"error": "trains.json not available yet"}), 404
    return send_file(TRAINS_JSON_PATH, mimetype="application/json")

@app.get("/dashboard")
def dashboard():
    """
    Serve your existing templates/dashboard.html if it exists.
    If you don’t have a templates/ folder in the image, we return a simple fallback page
    that fetches /data/trains.json so you still get a basic view.
    """
    # If a real template exists, render it
    tpl = APP_DIR / "templates" / "dashboard.html"
    if tpl.exists():
        return render_template("dashboard.html")

    # Fallback minimal page
    html = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>RailOps Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
      pre { background:#111; color:#0f0; padding:12px; border-radius:8px; overflow:auto; }
      .row { margin: 8px 0; }
      label { display:inline-block; width:60px; }
      input { width: 200px; }
      button { padding:6px 12px; }
    </style>
  </head>
  <body>
    <h1>RailOps – Dashboard (fallback)</h1>

    <div class="row"><label>lat</label><input id="lat" value="-33.86"></div>
    <div class="row"><label>lng</label><input id="lng" value="151.21"></div>
    <div class="row"><label>zm</label><input id="zm"  value="12"></div>
    <div class="row"><label>bbox</label><input id="bbox" placeholder="-35.8,138.4,-34.6,139.0"></div>
    <div class="row"><button id="btn">Fetch /trains</button></div>

    <pre id="out">Loading /data/trains.json …</pre>

    <script>
      async function loadSnapshot() {
        try {
          const r = await fetch('/data/trains.json', {cache:'no-store'});
          const t = await r.text();
          out.textContent = t;
        } catch (e) {
          out.textContent = 'Failed to load trains.json: ' + e;
        }
      }
      document.getElementById('btn').onclick = async () => {
        const lat = document.getElementById('lat').value.trim();
        const lng = document.getElementById('lng').value.trim();
        const zm  = document.getElementById('zm').value.trim();
        const bbox= document.getElementById('bbox').value.trim();
        const qs  = new URLSearchParams({lat, lng, zm});
        if (bbox) qs.set('bbox', bbox);
        out.textContent = 'Fetching /trains…';
        try {
          const r = await fetch('/trains?' + qs.toString(), {cache:'no-store'});
          const t = await r.text();
          out.textContent = t;
        } catch (e) {
          out.textContent = 'Fetch error: ' + e;
        }
      };
      loadSnapshot();
      // poll snapshot every 30s so you see updates from background refresher
      setInterval(loadSnapshot, 30000);
    </script>
  </body>
</html>"""
    return Response(html, mimetype="text/html")

# Simple route so you can test alternate viewports without the dashboard
@app.get("/test")
def test_help():
    return jsonify({
        "usage": "/trains?lat=-33.86&lng=151.21&zm=12&bbox=-35.8,138.4,-34.6,139.0",
        "notes": "bbox is optional; background refresher uses DEFAULT_* envs."
    })

# -----------------------------------------------------------------------------
# Graceful shutdown on Gunicorn stop
# -----------------------------------------------------------------------------
@app.before_serving
def _startup_note():
    log.info("Service starting; refresher=%s", "on" if not _stop_flag.is_set() else "off")

@app.after_serving
def _shutdown_note():
    _stop_flag.set()
    log.info("Service stopping")

# -----------------------------------------------------------------------------
# Local dev
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # For local testing: python app.py
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
