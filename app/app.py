import os, json, time, logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import requests
from flask import Flask, jsonify, request, make_response
from flask_cors import CORS

# -----------------------------------------------------------------------------
# Flask setup
# -----------------------------------------------------------------------------
app = Flask(__name__)

# Only allow your Netlify site by default (adjust domain if needed)
NETLIFY_ORIGIN = os.getenv("NETLIFY_ORIGIN", "https://traintracker2-0.netlify.app")
CORS(app, resources={r"/*": {"origins": [NETLIFY_ORIGIN]}}, supports_credentials=False)

# Logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("railops")

# -----------------------------------------------------------------------------
# TrainFinder config via env vars (optional). If missing, we serve demo data.
# -----------------------------------------------------------------------------
TF_BASE = "https://trainfinder.otenko.com"
TF_VIEW = f"{TF_BASE}/home/nextlevel"
TF_API  = f"{TF_BASE}/Home/GetViewPortData"

TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "").strip()
TF_REFERER  = os.getenv("TF_REFERER", "https://trainfinder.otenko.com/home/nextlevel?lat=-33.86&lng=151.21&zm=11")
TF_UA       = os.getenv("TF_UA", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": TF_UA,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": TF_REFERER,
})
if TF_ASPXAUTH:
    SESSION.cookies.set(".ASPXAUTH", TF_ASPXAUTH, domain="trainfinder.otenko.com", secure=True)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def to_float(s: Any, default: float = None) -> float | None:
    try:
        return float(s)
    except Exception:
        return default

def fetch_trainfinder(lat: float, lng: float, zm: int) -> Dict[str, Any] | None:
    """
    Try to warm-up (GET) then POST the viewport.
    Return JSON dict or None if not usable.
    """
    try:
        warm_url = f"{TF_VIEW}?lat={lat:.2f}&lng={lng:.2f}&zm={zm}"
        w = SESSION.get(warm_url, timeout=10)
        log.info("Warmup GET %s -> %s", warm_url, w.status_code)

        form = {"lat": str(lat), "lng": str(lng), "zm": str(zm)}
        r = SESSION.post(TF_API, data=form, timeout=15)
        log.info("POST %s -> %s", TF_API, r.status_code)
        if not r.ok:
            return None

        data = r.json()
        # Heuristic: their successful payloads include these buckets
        if not isinstance(data, dict):
            return None
        # If everything is None, treat as empty/unauth
        if all(data.get(k) in (None, [], {}) for k in ("favs", "alerts", "places", "tts", "webcams", "atcsGomi", "atcsObj")):
            log.warning("TrainFinder payload looks empty/unauthorized.")
            return None
        return data
    except Exception as e:
        log.warning("TrainFinder fetch failed: %s", e)
        return None

def normalize_trains(data: Any) -> List[Dict[str, Any]]:
    """
    Accept a few shapes and normalize to:
      { id, name, lat, lng, speed, source, when, extra }
    """
    out: List[Dict[str, Any]] = []

    # case: { "trains": [...] }
    if isinstance(data, dict) and isinstance(data.get("trains"), list):
        data = data["trains"]

    # case: TF-ish dict with 'tts'
    if isinstance(data, dict) and isinstance(data.get("tts"), list):
        for i, t in enumerate(data["tts"]):
            lat = t.get("la") or t.get("lat") or (t.get("pos") or {}).get("la")
            lng = t.get("lo") or t.get("lng") or (t.get("pos") or {}).get("lo")
            if lat is None or lng is None:
                continue
            out.append({
                "id": t.get("id", i),
                "name": t.get("n") or t.get("title") or f"Train {t.get('id', i)}",
                "lat": float(lat),
                "lng": float(lng),
                "speed": t.get("sp") or t.get("speed"),
                "source": "TF",
                "when": t.get("ts"),
                "extra": t
            })
        return out

    # case: already list
    if isinstance(data, list):
        for i, t in enumerate(data):
            lat = t.get("lat") if isinstance(t, dict) else None
            lng = (t.get("lng") or t.get("lon") or t.get("longitude")) if isinstance(t, dict) else None
            if lat is None or lng is None:
                continue
            out.append({
                "id": t.get("id", i),
                "name": t.get("name") or t.get("title") or f"Train {t.get('id', i)}",
                "lat": float(lat),
                "lng": float(lng),
                "speed": t.get("speed"),
                "source": t.get("source", "railops"),
                "when": t.get("when"),
                "extra": t
            })
        return out

    return out

def demo_trains(lat: float, lng: float, zm: int) -> List[Dict[str, Any]]:
    """
    Always return a couple of markers near the requested view so the
    frontend can render even if upstream is empty.
    """
    jitter = 0.05 if zm >= 11 else 0.3
    return [
        {"id": "demo-1", "name": "Demo Train A", "lat": lat + jitter, "lng": lng + jitter/2, "speed": 45, "source": "demo", "when": now_iso()},
        {"id": "demo-2", "name": "Demo Train B", "lat": lat - jitter/2, "lng": lng - jitter, "speed": 62, "source": "demo", "when": now_iso()},
    ]

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
def home():
    return jsonify(ok=True, service="railops-json", time=now_iso())

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/trains")
def get_trains():
    """
    Query params (optional):
      lat, lng, zm  -> viewport hint; defaults to Sydney
    """
    lat = to_float(request.args.get("lat"), -33.86)
    lng = to_float(request.args.get("lng"), 151.21)
    zm  = int(request.args.get("zm", 11))

    # Try TF first if we have auth cookie; otherwise skip
    payload = fetch_trainfinder(lat, lng, zm) if TF_ASPXAUTH else None
    trains = normalize_trains(payload) if payload else []

    if not trains:
        trains = demo_trains(lat, lng, zm)

    resp = jsonify({"updated": now_iso(), "count": len(trains), "trains": trains})
    # Friendly cache headers for quick polling
    resp.headers["Cache-Control"] = "no-store"
    return resp
