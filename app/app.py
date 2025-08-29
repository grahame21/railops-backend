# app/app.py
import os, json, time, logging
from typing import Any, Dict, List, Tuple, Optional
from urllib.parse import urlencode
from flask import Flask, request, jsonify, make_response
import requests

# ──────────────────────────────────────────────
# CONFIG / ENV
# ──────────────────────────────────────────────
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "").strip()
TF_REFERER  = os.getenv("TF_REFERER", "https://trainfinder.otenko.com/home/nextlevel").strip()

# Use your desktop Chrome UA if TF_UA is not set
TF_UA = os.getenv(
    "TF_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
).strip()

SESSION_TIMEOUT = 15  # seconds for outbound requests

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s:railops:%(message)s")
log = logging.getLogger("railops")

# ──────────────────────────────────────────────
# FLASK
# ──────────────────────────────────────────────
app = Flask(__name__)

def add_cors(resp):
    # very permissive CORS for quick testing; lock down later
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.after_request
def after(resp):
    return add_cors(resp)

@app.route("/healthz")
def healthz():
    return add_cors(make_response("ok", 200))

@app.route("/")
def root():
    return add_cors(make_response("ok, true", 200))

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": TF_UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": TF_REFERER if TF_REFERER else "https://trainfinder.otenko.com/",
        "Origin": "https://trainfinder.otenko.com",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    })
    # Attach auth cookie if provided
    if TF_ASPXAUTH:
        # IMPORTANT: 'httponly' must go via 'rest'
        s.cookies.set(
            "TF_ASPXAUTH",
            TF_ASPXAUTH,
            domain="trainfinder.otenko.com",
            secure=True,
            rest={"HttpOnly": True}
        )
    return s

def warmup(s: requests.Session, lat: float, lng: float, zm: int) -> Tuple[int, str]:
    """
    Prime the server (mimic opening map at a viewport).
    """
    try:
        params = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}
        url = f"https://trainfinder.otenko.com/home/nextlevel?{urlencode(params)}"
        r = s.get(url, timeout=SESSION_TIMEOUT)
        log.info("Warmup GET %s -> %d", url, r.status_code)
        return r.status_code, r.text
    except Exception as e:
        log.warning("Warmup failed: %s", e)
        return 0, str(e)

def fetch_viewport(
    lat: float, lng: float, zm: int,
    bbox: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], str, int]:
    """
    POST to TrainFinder to get viewport data.
    Returns: (json_dict or None, raw_text, http_status)
    """
    s = new_session()

    # Warmup (best effort)
    warmup(s, lat, lng, zm)

    url = "https://trainfinder.otenko.com/Home/GetViewPortData"

    # Some deployments expect form data, others accept JSON; form works reliably.
    form = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}
    if bbox:
        # If caller passes bbox (south,west,north,east), forward it as-is
        form["bbox"] = bbox

    try:
        r = s.post(url, data=form, timeout=SESSION_TIMEOUT)
        log.info("POST %s (form=%s) -> %d", url, f"lat={form['lat']},lng={form['lng']},zm={form['zm']}" + (f",bbox={bbox}" if bbox else ""), r.status_code)
        txt = r.text
        j = None
        if r.headers.get("content-type", "").startswith("application/json"):
            try:
                j = r.json()
            except Exception:
                # fall back to manual parse attempt
                pass
        if j is None:
            try:
                j = json.loads(txt)
            except Exception:
                # Not valid JSON; return raw
                return None, txt, r.status_code

        # Quick sanity check — in prior logs we saw keys but empty content
        keys = sorted(list(j.keys())) if isinstance(j, dict) else []
        if keys:
            log.info("Sample JSON keys: %s", keys[:8])

        # Heuristic: if everything is null/empty, hint about auth/zoom
        if isinstance(j, dict) and all((v is None or v == [] or v == {}) for v in j.values()):
            log.warning("TrainFinder payload looks empty/unauthorized.")

        return j, txt, r.status_code

    except Exception as e:
        log.exception("Viewport fetch failed: %s", e)
        return None, str(e), 0

def _get_float(d: Dict[str, Any], *names) -> Optional[float]:
    for n in names:
        if n in d and isinstance(d[n], (int, float)):
            return float(d[n])
        if n in d and isinstance(d[n], str):
            try:
                return float(d[n])
            except Exception:
                pass
    return None

def extract_trains(payload: Any) -> List[Dict[str, Any]]:
    """
    Try to extract marker-like entries (lat/lng + id/title) from whatever
    structure TrainFinder returns. We scan common buckets and generic lists.
    """
    results: List[Dict[str, Any]] = []

    if not isinstance(payload, dict):
        return results

    candidate_lists: List[Any] = []
    # Buckets we've seen in logs
    for key in ("tts", "places", "alerts", "webcams", "atcsObj", "atcsGomi"):
        val = payload.get(key)
        if isinstance(val, list):
            candidate_lists.append(val)
        elif isinstance(val, dict):
            # sometimes nested lists live inside dicts (e.g., places: {items:[...]})
            for v in val.values():
                if isinstance(v, list):
                    candidate_lists.append(v)

    # Fallback: scan any list values for lat/lng patterns
    if not candidate_lists:
        for v in payload.values():
            if isinstance(v, list):
                candidate_lists.append(v)

    def add_marker(obj: Dict[str, Any]):
        lat = _get_float(obj, "lat", "Lat", "latitude", "Latitude", "iLat", "y")
        lng = _get_float(obj, "lng", "Lng", "longitude", "Longitude", "iLng", "x")
        if lat is None or lng is None:
            return
        # Try to build a reasonable label
        title = None
        for k in ("name", "title", "desc", "Description", "id", "train", "service"):
            if k in obj and isinstance(obj[k], (str, int, float)):
                title = str(obj[k]); break
        marker = {"lat": lat, "lng": lng}
        if title:
            marker["title"] = title
        # Include a few raw fields for debugging
        for k in ("id", "train", "line", "service", "speed", "dir"):
            if k in obj:
                marker[k] = obj[k]
        results.append(marker)

    for arr in candidate_lists:
        if not isinstance(arr, list):
            continue
        for item in arr:
            if isinstance(item, dict):
                add_marker(item)

    return results

# ──────────────────────────────────────────────
# API
# ──────────────────────────────────────────────
@app.route("/trains", methods=["GET", "OPTIONS"])
def trains():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    # Defaults if not provided
    lat = float(request.args.get("lat", "-33.860000"))
    lng = float(request.args.get("lng", "151.210000"))
    zm  = int(request.args.get("zm", "12"))

    # Optional bbox "south,west,north,east"
    bbox = request.args.get("bbox")
    j, txt, code = fetch_viewport(lat, lng, zm, bbox)

    if j is None:
        # Pass through raw error text to help debugging
        return add_cors(make_response(jsonify({
            "ok": False, "status": code, "error": "upstream", "detail": txt
        }), 502))

    markers = extract_trains(j)
    # Persist to container (for quick inspection)
    try:
        with open("/app/trains.json", "w") as f:
            json.dump({"at": int(time.time()), "lat": lat, "lng": lng, "zm": zm,
                       "bbox": bbox, "count": len(markers), "markers": markers}, f)
        log.info("wrote /app/trains.json with %d markers", len(markers))
    except Exception as e:
        log.warning("Failed writing trains.json: %s", e)

    return add_cors(make_response(jsonify({
        "ok": True,
        "count": len(markers),
        "markers": markers
    }), 200))


# ──────────────────────────────────────────────
# LOCAL DEV ENTRY
# ──────────────────────────────────────────────
if __name__ == "__main__":
    # For local testing only: flask’s built-in server
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=True)