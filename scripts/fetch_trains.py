import requests
import time
import json

# TrainFinder API endpoint
URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

# Replace with your valid .ASPXAUTH cookie value
COOKIE = ".ASPXAUTH=YOUR_COOKIE_HERE"

# Headers (mimic real browser request)
HEADERS = {
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "origin": "https://trainfinder.otenko.com",
    "referer": "https://trainfinder.otenko.com/home/nextlevel",  # adjust zoom/viewport later if needed
    "sec-ch-ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest",
}

# Cookie dict for requests
COOKIES = {
    ".ASPXAUTH": COOKIE.replace(".ASPXAUTH=", "")
}

def fetch_trains():
    try:
        # POST with empty body — TrainFinder expects viewport info from referer/headers
        resp = requests.post(URL, headers=HEADERS, cookies=COOKIES, data={})
        if resp.status_code == 200:
            data = resp.json()
            if not data or all(v is None for v in data.values()):
                print("⚠️ Warning: Null payload. Try a different referer (zm ~ 6-7 works best).")
            else:
                with open("trains.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print("✅ trains.json updated.")
        else:
            print(f"❌ Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Exception while fetching trains: {e}")

if __name__ == "__main__":
    while True:
        fetch_trains()
        # Wait 30 seconds before next update
        time.sleep(30)
