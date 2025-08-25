import os
import time
import json
import logging
import requests
from flask import Flask, jsonify

# Logging setup
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("railops")

app = Flask(__name__)

# TrainFinder settings from environment variables
TF_ASPXAUTH = os.getenv("TF_ASPXAUTH")
TF_UA = os.getenv("TF_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/127 Safari/537.36")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": TF_UA,
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
    "Cookie": f".ASPXAUTH={TF_ASPXAUTH}"
})

# Where we’ll store trains.json
TRAINS_FILE = "/app/trains.json"

def fetch_trains():
    """Fetch train data from TrainFinder and save to trains.json"""
    try:
        # Wide coverage: all of Australia
        form = {
            "lat": "-27.0",
            "lng": "133.0",
            "zm": "5",
            "bbox": "-44,112,-10,154"  # (S,W,N,E)
        }

        # Warmup GET (important for session)
        warmup_url = "https://trainfinder.otenko.com/home/nextlevel?lat=-27.0&lng=133.0&zm=5"
        r1 = SESSION.get(warmup_url, timeout=20)
        log.info("Warmup GET %s -> %s", warmup_url, r1.status_code)

        # Actual data request
        url = "https://trainfinder.otenko.com/Home/GetViewPortData"
        r2 = SESSION.post(url, data=form, timeout=20)
        log.info("POST %s -> %s", url, r2.status_code)

        data = r2.json()
        sample_keys = list(data.keys())
        log.info("Sample JSON keys: %s", sample_keys)

        # Extract trains (atcsObj usually holds them)
        trains = data.get("atcsObj", [])
        log.info("Fetched %d trains", len(trains))

        with open(TRAINS_FILE, "w") as f:
            json.dump(trains, f)

        return trains

    except Exception as e:
        log.exception("fetch_trains error: %s", e)
        return []


@app.route("/")
def index():
    return jsonify({"ok": True, "source": "railops"})


@app.route("/trains.json")
def trains_json():
    # If trains.json exists, serve it
    if os.path.exists(TRAINS_FILE):
        with open(TRAINS_FILE) as f:
            return jsonify(json.load(f))
    return jsonify([])


# Background refresher
def refresher_loop():
    while True:
        fetch_trains()
        time.sleep(30)  # refresh every 30 seconds


if __name__ == "__main__":
    # Start refresher in a thread
    import threading
    t = threading.Thread(target=refresher_loop, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=10000)
