import requests
import time
import os
import json

TRAINFINDER_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"
OUTPUT_FILE = "trains.json"
SLEEP_INTERVAL = 30  # seconds

# Load cookie from environment (Render sets it via GitHub secret)
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

        print(f"HTTP {response.status_code} at {time.strftime('%H:%M:%S')}")

        if response.status_code == 200:
            if response.text.strip().startswith("{") or response.text.strip().startswith("["):
                data = response.json()
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print(f"Updated {OUTPUT_FILE} with {len(data)} records.")
            else:
                print("Empty or invalid JSON response from TrainFinder!")
                print("Raw response body:")
                print(response.text[:500])  # Print first 500 chars for inspection
                with open(OUTPUT_FILE, "w") as f:
                    f.write("[]")  # Write empty list to avoid frontend errors
        else:
            print(f"TrainFinder returned status {response.status_code}")
            with open(OUTPUT_FILE, "w") as f:
                f.write("[]")
    except Exception as e:
        print(f"Exception while fetching train data: {e}")
        with open(OUTPUT_FILE, "w") as f:
            f.write("[]")

# Loop forever
while True:
    fetch_trains()
    time.sleep(SLEEP_INTERVAL)
