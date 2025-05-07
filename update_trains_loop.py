import requests
import time
import os
import json

TRAINFINDER_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"
OUTPUT_FILE = "trains.json"
SLEEP_INTERVAL = 30  # seconds

# Load cookie from GitHub secret (Render sets it as an env variable)
cookie_value = os.getenv("TRAINFINDER_COOKIE")

if not cookie_value:
    print("ERROR: TRAINFINDER_COOKIE environment variable is missing.")
    exit(1)

headers = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": f".ASPXAUTH={cookie_value}",
    "Referer": "https://trainfinder.otenko.com/home/nextlevel",
    "X-Requested-With": "XMLHttpRequest",
}

def fetch_trains():
    try:
        response = requests.get(TRAINFINDER_URL, headers=headers, timeout=10)
        if response.status_code == 200 and response.text.strip():
            data = response.json()
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"Updated {OUTPUT_FILE} at {time.strftime('%H:%M:%S')}")
        else:
            print(f"TrainFinder returned status {response.status_code} or empty body.")
            with open(OUTPUT_FILE, "w") as f:
                f.write("[]")  # write empty list to avoid errors
    except Exception as e:
        print(f"Error fetching train data: {e}")

while True:
    fetch_trains()
    time.sleep(SLEEP_INTERVAL)