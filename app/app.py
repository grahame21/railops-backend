import os
import json
import logging
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
log = logging.getLogger("railops")
logging.basicConfig(level=logging.INFO)

# --- Environment variables required ---
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH", "")
TF_UA = os.getenv("TF_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0.0.0 Safari/537.36")
TF_REFERER = os.getenv("TF_REFERER", "https://trainfinder.otenko.com/home/nextlevel")

TRAINFINDER_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"
TRAINS_FILE = "/app/trains.json"


def fetch_viewport(lat, lng, zm, bbox=None):
    """
    Calls TrainFinder API with the right headers/cookies and returns JSON response.
    """
    headers = {
        "User-Agent": TF_UA,
        "Referer": f"{TF_REFERER}?lat={lat}&lng={lng}&zm={zm}",
        "X-Requested-With": "XMLHttpRequest",
    }
    cookies = {".ASPXAUTH": TF_ASPXAUTH}
    form = {"lat": str(lat), "lng": str(lng), "zm": str(zm)}
    if bbox:
        form["bbox"] = bbox

    log.info("POST %s (form=%s)", TRAINFINDER_URL, form)
    r = requests.post(TRAINFINDER_URL, headers=headers, cookies=cookies, data=form)

    try:
        j = r.json()
        return j, r.text, r.status_code
    except Exception:
        return None, r.text, r.status_code


@app.route("/")
def index():
    return jsonify(ok=True, message="RailOps backend running")


@app.route("/trains")
def trains():
    """
    Main endpoint for the frontend → returns live trains from TrainFinder.
    """
    lat = request.args.get("lat", "-33.8688")
    lng = request.args.get("lng", "151.2093")
    zm = request.args.get("zm", "10")
    bbox = request.args.get("bbox")

    j, txt, code = fetch_viewport(lat, lng, zm, bbox)

    if not j or not isinstance(j, dict) or "favs" not in j:
        log.warning("TrainFinder payload looks empty/unauthorized.")
        return jsonify({
            "ok": False,
            "message": "TrainFinder payload looks empty/unauthorized.",
            "meta": {
                "http_status": code,
                "referer": f"{TF_REFERER}?lat={lat}&lng={lng}&zm={zm}",
                "sample": txt[:500]
            }
        }), 200

    # Write to trains.json for debugging / persistence
    try:
        with open(TRAINS_FILE, "w") as f:
            json.dump(j, f)
        log.info("wrote %s with %s keys", TRAINS_FILE, list(j.keys()))
    except Exception as e:
        log.error("could not write trains.json: %s", e)

    return jsonify({"ok": True, "data": j})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
