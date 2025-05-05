import os
import requests
import json
import time

def fetch_train_data(cookie):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": f".ASPXAUTH={cookie}",
        "Referer": "https://trainfinder.otenko.com/home/nextlevel",
        "X-Requested-With": "XMLHttpRequest"
    }
    url = "https://trainfinder.otenko.com/Home/GetViewPortData"
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        with open("trains.json", "w") as f:
            json.dump(data, f)
        print("✅ trains.json updated successfully.")
    except Exception as e:
        print(f"❌ Failed to fetch/update train data: {e}")

def main():
    cookie = os.environ.get("COOKIE_VALUE")
    if not cookie:
        print("❌ COOKIE_VALUE not found in environment variables.")
        return
    while True:
        fetch_train_data(cookie)
        time.sleep(30)

if __name__ == "__main__":
    main()
