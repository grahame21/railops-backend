from flask import Flask, request, jsonify
import os, requests, logging, re

app = Flask(__name__)
log = logging.getLogger("railops"); logging.basicConfig(level=logging.INFO)

TF_COOKIE = os.environ.get("TF_ASPXAUTH", "").strip()
TF_UA     = os.environ.get("TF_UA", "Mozilla/5.0")

S = requests.Session()
if TF_COOKIE:
    S.cookies.set(".ASPXAUTH", TF_COOKIE, domain="trainfinder.otenko.com")

def build_headers(lat, lng, zm):
    referer = f"https://trainfinder.otenko.com/home/nextlevel?lat={lat}&lng={lng}&zm={zm}"
    # keep referer a single URL (defensive)
    m = re.search(r'https?://\S+', referer)
    referer = m.group(0) if m else referer
    return {
        "User-Agent": TF_UA,
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://trainfinder.otenko.com",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

@app.get("/trains")
def trains():
    # required: bounds from client
    swlat = request.args.get("swlat", type=float)
    swlng = request.args.get("swlng", type=float)
    nelat = request.args.get("nelat", type=float)
    nelng = request.args.get("nelng", type=float)
    lat   = request.args.get("lat",   type=float, default=(swlat+nelat)/2 if swlat and nelat else None)
    lng   = request.args.get("lng",   type=float, default=(swlng+nelng)/2 if swlng and nelng else None)
    zm    = request.args.get("zm",    type=int,   default=10)

    if None in (swlat, swlng, nelat, nelng, lat, lng):
        return jsonify({"error":"missing bounds"}), 400

    # TrainFinder usually wants lat/lng/zm plus bounds in the POST body
    form = {
        "lat": f"{lat:.5f}",
        "lng": f"{lng:.5f}",
        "zm":  str(zm),
        "bbox": f"{swlat:.5f},{swlng:.5f},{nelat:.5f},{nelng:.5f}",
    }
    headers = build_headers(lat, lng, zm)

    r = S.post("https://trainfinder.otenko.com/Home/GetViewPortData",
               headers=headers, data=form, timeout=15)
    r.raise_for_status()
    data = r.json()  # might be the big JSON that includes tts/atcsObj/etc.

    return jsonify(data)
