import os, json, logging, re, time
from typing import Any, Dict, Optional, Tuple, List

import requests
from flask import Flask, request, jsonify, Response

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("railops")

# -------------------------
# Config from env
# -------------------------
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)

TF_HOST = "https://trainfinder.otenko.com"

def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

def build_referer(lat: float, lng: float, zm: int) -> str:
    return f"{TF_HOST}/home/nextlevel?lat={lat}&lng={lng}&zm={zm}"

# -------------------------
# Anti-forgery token helpers
# -------------------------

TOKEN_COOKIE_NAME = "__RequestVerificationToken"
TOKEN_HEADER_NAME = "RequestVerificationToken"   # typical ASP.NET AJAX header
TOKEN_INPUT_RE = re.compile(
    r'name=[\'"]__RequestVerificationToken[\'"]\s+value=[\'"]([^\'"]+)[\'"]',
    re.IGNORECASE
)

def extract_token_from_html(html: str) -> Optional[str]:
    m = TOKEN_INPUT_RE.search(html or "")
    if m:
        return m.group(1)
    return None

def find_anti_forgery_token(resp: requests.Response, session: requests.Session) -> Optional[str]:
    """
    Try to locate the anti-forgery token in either:
      - cookies named __RequestVerificationToken, OR
      - hidden input __RequestVerificationToken in HTML.
    """
    # 1) Cookie on response or session
    if TOKEN_COOKIE_NAME in resp.cookies:
        return resp.cookies.get(TOKEN_COOKIE_NAME)

    for c in session.cookies:
        if c.name == TOKEN_COOKIE_NAME and c.domain.endswith("otenko.com"):
            return c.value

    # 2) Hidden input in HTML
    token_html = extract_token_from_html(resp.text)
    if token_html:
        return token_html

    return None

# -------------------------
# TrainFinder fetch
# -------------------------

def new_session() -> requests.Session:
    s = requests.Session()
    ua = env("TF_UA", DEFAULT_UA)
    s.headers.update({
        "User-Agent": ua,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_HOST,
    })

    # Core cookies
    auth = env("TF_ASPXAUTH")
    sess = env("TF_SESSION")
    extra = env("TF_EXTRA_COOKIES")  # "k1=v1; k2=v2"

    jar = requests.cookies.RequestsCookieJar()
    if auth:
        jar.set("TF_ASPXAUTH", auth)
    if sess:
        jar.set("ASP.NET_SessionId", sess)

    if extra:
        for pair in [p.strip() for p in extra.split(";") if p.strip()]:
            if "=" in pair:
                k, v = pair.split("=", 1)
                jar.set(k.strip(), v.strip())

    s.cookies.update(jar)
    return s

def fetch_viewport(lat: float, lng: float, zm: int,
                   bbox: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], str, int]:
    """
    Returns (json_or_none, raw_text, http_status)
    """
    s = new_session()
    referer = build_referer(lat, lng, zm)
    s.headers["Referer"] = referer

    # Warmup: load the map page to get cookies + anti-forgery token
    warm = s.get(referer, timeout=20)
    log.info("Warmup GET %s -> %s (ctype=%s final=%s)",
             referer, warm.status_code, warm.headers.get("Content-Type"), warm.url)

    token = find_anti_forgery_token(warm, s)
    if token:
        s.headers[TOKEN_HEADER_NAME] = token
        log.info("Found anti-forgery token (header set).")
    else:
        log.warning("No anti-forgery token found in cookies or HTML.")

    # Build POST body
    form = {"lat": f"{lat}", "lng": f"{lng}", "zm": f"{zm}"}
    if bbox:
        form["bbox"] = bbox

    r = s.post(f"{TF_HOST}/Home/GetViewPortData", data=form, timeout=25)
    ctype = (r.headers.get("Content-Type") or "").lower()
    log.info("POST GetViewPortData -> %s (ctype=%s) cookies_sent=%s",
             r.status_code, ctype, {c.name: (c.value[:16] + "…") for c in s.cookies})

    # Expect JSON; otherwise we likely got logged-out HTML
    if "application/json" in ctype:
        try:
            return r.json(), r.text, r.status_code
        except Exception:
            pass

    # Not JSON -> return sample HTML so caller can display helpful error
    return None, r.text[:512], r.status_code

# -------------------------
# Data shaping
# -------------------------

def build_markers(tf_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Given TrainFinder JSON payload, extract points we can plot.
    The TF payload often includes keys like 'places', 'tts' (trains?), etc.
    This function is defensive and only emits markers if lat/lng exist.
    """
    markers: List[Dict[str, Any]] = []

    # Common places bucket
    places = tf_json.get("places") or []
    for p in places:
        lat = p.get("Lat") or p.get("lat")
        lng = p.get("Lng") or p.get("lng")
        if lat is None or lng is None:
            continue
        title = p.get("Name") or p.get("name") or "Place"
        markers.append({
            "type": "place",
            "lat": float(lat),
            "lng": float(lng),
            "title": title,
            "raw": p,
        })

    # Trains / tts? (depends on site naming)
    tts = tf_json.get("tts") or []
    for t in tts:
        lat = t.get("Lat") or t.get("lat")
        lng = t.get("Lng") or t.get("lng")
        if lat is None or lng is None:
            continue
        label = t.get("TrainNo") or t.get("service") or "Train"
        markers.append({
            "type": "train",
            "lat": float(lat),
            "lng": float(lng),
            "title": str(label),
            "raw": t,
        })

    return markers

# -------------------------
# Flask app
# -------------------------

app = Flask(__name__)

@app.get("/")
def root():
    return jsonify(ok=True, service="railops-json", message="ok")

@app.get("/healthz")
def healthz():
    return Response("ok", mimetype="text/plain")

@app.get("/debug")
def debug():
    info = {
        "TF_ASPXAUTH_set": bool(env("TF_ASPXAUTH")),
        "TF_SESSION_set": bool(env("TF_SESSION")),
        "TF_EXTRA_COOKIES_present": bool(env("TF_EXTRA_COOKIES")),
        "TF_UA_prefix": env("TF_UA", DEFAULT_UA)[:42],
    }
    return jsonify(info)

@app.get("/trains")
def trains():
    """
    Query string:
      lat, lng, zm (required)
      bbox (optional)
    """
    try:
        lat = float(request.args.get("lat", ""))
        lng = float(request.args.get("lng", ""))
        zm  = int(request.args.get("zm", ""))
    except Exception:
        return jsonify(ok=False, message="lat,lng,zm are required numeric query params"), 400

    bbox = request.args.get("bbox")

    tf_json, raw, code = fetch_viewport(lat, lng, zm, bbox=bbox)

    if tf_json is None:
        # Not JSON -> user probably not authenticated
        return jsonify(
            ok=False,
            message="TrainFinder payload looks empty/unauthorized.",
            meta={
                "http_status": code,
                "referer": build_referer(lat, lng, zm),
                "sample": raw[:300],
            },
        ), 200

    markers = build_markers(tf_json)
    return jsonify(ok=True, count=len(markers), markers=markers)

if __name__ == "__main__":
    # Local debug
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
