from flask import Flask, request, jsonify
import requests, os, logging, re

app = Flask(__name__)
log = logging.getLogger("railops"); logging.basicConfig(level=logging.INFO)

# --- TF cookie & session ---
TF_COOKIE = os.environ.get("TF_ASPXAUTH", "").strip()
TF_UA     = os.environ.get("TF_UA", "Mozilla/5.0")

S = requests.Session()
if TF_COOKIE:
    S.cookies.set(".ASPXAUTH", TF_COOKIE, domain="trainfinder.otenko.com")

def build_headers(lat, lng, zm):
    referer = f"https://trainfinder.otenko.com/home/nextlevel?lat={lat}&lng={lng}&zm={zm}"
    m = re.search(r'https?://\S+', referer)
    referer = m.group(0) if m else referer
    return {
        "User-Agent": TF_UA,
        "Referer": referer,
        "Origin": "https://trainfinder.otenko.com",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

# === ROUTE 1: Frontend passes bbox ===
@app.get("/trains")
def trains():
    swlat = request.args.get("swlat", type=float)
    swlng = request.args.get("swlng", type=float)
    nelat = request.args.get("nelat", type=float)
    nelng = request.args.get("nelng", type=float)
    lat   = request.args.get("lat", type=float)
    lng   = request.args.get("lng", type=float)
    zm    = request.args.get("zm", type=int, default=10)

    if None in (swlat, swlng, nelat, nelng, lat, lng):
        return jsonify({"error":"missing bounds"}), 400

    form = {
        "lat": f"{lat:.5f}", "lng": f"{lng:.5f}", "zm": str(zm),
        "bbox": f"{swlat:.5f},{swlng:.5f},{nelat:.5f},{nelng:.5f}",
    }
    headers = build_headers(lat, lng, zm)

    r = S.post("https://trainfinder.otenko.com/Home/GetViewPortData",
               headers=headers, data=form, timeout=15)
    return jsonify(r.json())

# === ROUTE 2: Fallback, pass only center+zoom ===
def bbox_from_center_zoom(lat, lng, zm):
    base_width_deg = 40.0
    width = base_width_deg / (2 ** zm)
    height = width * max(0.6, abs(lat)/90.0 + 0.1)
    swlat, swlng = lat - height/2, lng - width/2
    nelat, nelng = lat + height/2, lng + width/2
    return swlat, swlng, nelat, nelng

@app.get("/trains_by_center")
def trains_by_center():
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    zm  = request.args.get("zm",  type=int, default=10)
    if lat is None or lng is None:
        return jsonify({"error":"lat/lng required"}), 400

    swlat, swlng, nelat, nelng = bbox_from_center_zoom(lat, lng, zm)
    form = {
        "lat": f"{lat:.5f}", "lng": f"{lng:.5f}", "zm": str(zm),
        "bbox": f"{swlat:.5f},{swlng:.5f},{nelat:.5f},{nelng:.5f}",
    }
    headers = build_headers(lat, lng, zm)

    r = S.post("https://trainfinder.otenko.com/Home/GetViewPortData",
               headers=headers, data=form, timeout=15)
    return jsonify(r.json())
