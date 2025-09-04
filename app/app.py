import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
import requests

# -------------------------------
# Config & Logging
# -------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:railops:%(message)s"
)
log = logging.getLogger("railops")

TF_HOST = "trainfinder.otenko.com"
TF_BASE = f"https://{TF_HOST}"
TF_POST = f"{TF_BASE}/Home/GetViewPortData"

# ENV VARS (set these in Render)
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "").strip()   # required
TF_UA       = os.getenv("TF_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
DEFAULT_REF = os.getenv("TF_REFERER", "https://trainfinder.otenko.com/home/nextlevel?lat=-33.8688&lng=151.2093&zm=12")

PORT = int(os.getenv("PORT", "10000"))

app = Flask(__name__)

# -------------------------------
# Helpers
# -------------------------------
def mask_token(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return "***"
    return s[:4] + "..." + s[-4:]

def build_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": TF_UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": TF_BASE,
        "Referer": DEFAULT_REF,  # can be overridden
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "keep-alive",
    })
    # Set BOTH cookie names to the same token (some apps check one or the other)
    if TF_ASPXAUTH:
        for name in (".ASPXAUTH", "ASPXAUTH"):
            s.cookies.set(name, TF_ASPXAUTH, domain=TF_HOST, secure=True)
    return s

def is_json_response(resp: requests.Response) -> bool:
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "application/json" in ct:
        return True
    # Some ASP.NET apps return JSON with text/html; try to parse
    try:
        _ = resp.json()
        return True
    except Exception:
        return False

def parse_json(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        return None

def make_referer(lat, lng, zm):
    return f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={int(round(zm))}"

def viewport_payload(lat, lng, zm, bbox=None):
    # TrainFinder typically accepts these form fields
    data = {
        "lat": f"{lat:.6f}",
        "lng": f"{lng:.6f}",
        "zm": str(int(round(zm))),
    }
    # Optional bbox string "-35.8,138.4,-34.6,139.0"
    if bbox:
        data["bbox"] = bbox
    return data

def fetch_viewport(lat, lng, zm, bbox=None, referer=None):
    s = build_session()
    ref_url = referer or make_referer(lat, lng, zm)
    # Refresh headers to use per-request referer
    s.headers["Referer"] = ref_url

    # Warmup GET to referer (some servers require)
    warm = s.get(ref_url, timeout=10)
    log.info("Warmup GET %s -> %s", ref_url, warm.status_code)

    # POST viewport
    form = viewport_payload(lat, lng, zm, bbox)
    resp = s.post(TF_POST, data=form, timeout=15)
    log.info("POST %s (form=%s) -> %s", TF_POST, ",".join([f"{k}={v}" for k,v in form.items()]), resp.status_code)

    if not is_json_response(resp):
        # Not JSON — very likely login page or HTML (unauthorized)
        sample = resp.text[:300]
        return None, {
            "http_status": resp.status_code,
            "referer": ref_url,
            "sample": sample
        }, False

    data = parse_json(resp)
    # Check for keys usually present (tts etc.) — when unauthorized they’re often null
    ok = bool(data) and isinstance(data, dict)
    return data, {"http_status": resp.status_code, "referer": ref_url}, ok

# -------------------------------
# Routes
# -------------------------------
@app.get("/")
def root():
    return jsonify({"ok": True, "message": "ok", "time": datetime.utcnow().isoformat() + "Z"})

@app.get("/health")
def health():
    return "ok, true"

@app.get("/debug/env")
def debug_env():
    return jsonify({
        "ok": True,
        "TF_ASPXAUTH_present": bool(TF_ASPXAUTH),
        "TF_ASPXAUTH_masked": mask_token(TF_ASPXAUTH),
        "TF_UA": TF_UA[:80] + ("..." if len(TF_UA) > 80 else ""),
        "DEFAULT_REFERER": DEFAULT_REF
    })

@app.get("/debug/test")
def debug_test():
    # Quick manual test from the browser:
    # /debug/test?lat=-33.8688&lng=151.2093&zm=12
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm  = float(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"ok": False, "message": "Invalid lat/lng/zm"}), 400

    bbox = request.args.get("bbox")
    ref  = request.args.get("referer")
    data, meta, ok = fetch_viewport(lat, lng, zm, bbox=bbox, referer=ref)
    if not ok:
        return jsonify({"ok": False, "message": "TrainFinder payload looks empty/unauthorized.", "meta": meta}), 200
    return jsonify({"ok": True, "meta": meta, "data_keys": list(data.keys())})

@app.get("/trains")
def trains():
    # Called by your dashboard front-end
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm  = float(request.args.get("zm", "10"))
    except Exception:
        return jsonify({"ok": False, "message": "Invalid lat/lng/zm"}), 400

    bbox = request.args.get("bbox")
    ref  = request.args.get("referer")

    data, meta, ok = fetch_viewport(lat, lng, zm, bbox=bbox, referer=ref)
    if not ok or not data:
        # Return helpful diagnostics to the UI
        # The front-end will display a message and show zero markers.
        # You can see details in the browser console / Network tab.
        meta = meta or {}
        # include a small HTML sample to prove it's a login/HTML page if any:
        if "sample" not in meta:
            meta["sample"] = "(no sample)"
        return jsonify({"ok": False, "message": "TrainFinder payload looks empty/unauthorized.", "meta": meta}), 200

    # Normalize to a consistent shape for the front-end
    # Expect data.get("tts") to be list of trains (if authorized)
    tts = data.get("tts") if isinstance(data, dict) else None
    return jsonify({"ok": True, "count": len(tts) if isinstance(tts, list) else 0, "data": data})

# -------------------------------
# Entrypoint (for local dev)
# -------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
