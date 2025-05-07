import requests
import time
import os
import json
import logging

# Configuration
TRAINFINDER_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"
OUTPUT_FILE = "trains.json"
SLEEP_INTERVAL = 30  # seconds

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # Logs to console
        logging.FileHandler("trainfinder_debug.log", encoding="utf-8")  # Logs to file
    ]
)

def fetch_trains():
    # Retrieve the cookie from environment variables
    cookie_value = os.getenv("TRAINFINDER_COOKIE")
    if not cookie_value:
        logging.error("Environment variable 'TRAINFINDER_COOKIE' is missing.")
        return

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": f".ASPXAUTH={cookie_value}",
        "Referer": "https://trainfinder.otenko.com/home/nextlevel",
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        logging.debug(f"Sending GET request to {TRAINFINDER_URL} with headers: {headers}")
        response = requests.get(TRAINFINDER_URL, headers=headers, timeout=10)
        logging.debug(f"Received response with status code: {response.status_code}")

        if response.status_code == 200:
            if response.text.strip():
                try:
                    data = response.json()
                    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    logging.info(f"Updated {OUTPUT_FILE} at {time.strftime('%H:%M:%S')}")
                except json.JSONDecodeError as e:
                    logging.error(f"JSON decoding failed: {e}")
                    logging.debug(f"Response text: {response.text}")
            else:
                logging.warning("Received empty response body.")
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    f.write("[]")
        else:
            logging.error(f"Unexpected status code: {response.status_code}")
            logging.debug(f"Response text: {response.text}")
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("[]")
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")

def main():
    logging.info("Starting train data fetch loop.")
    while True:
        fetch_trains()
        time.sleep(SLEEP_INTERVAL)

if __name__ == "__main__":
    main()