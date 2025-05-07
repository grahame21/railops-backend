import os
import time
import requests
import json

cookie_value = os.environ.get("COOKIE_VALUE")
netlify_token = os.environ.get("NETLIFY_TOKEN")
netlify_site_id = os.environ.get("NETLIFY_SITE_ID")

headers = {
    "Cookie": f".ASPXAUTH={cookie_value}",
    "User-Agent": "Mozilla/5.0",
}

def fetch_trains():
    print("🔄 Fetching train data from TrainFinder...")
    try:
        params = {
            "north": -10.0,
            "south": -45.0,
            "east": 155.0,
            "west": 110.0,
            "zoom": 6
        }
        response = requests.get(
            "https://trainfinder.otenko.com/Home/GetViewPortData",
            headers=headers,
            params=params,
            timeout=10,
        )
        print(f"STATUS: {response.status_code}")
        if response.status_code != 200:
            print(f"❌ HTTP {response.status_code} from TrainFinder.")
            return None
        data = response.json()
        if "Trains" not in data or not data["Trains"]:
            print("⚠️ No train data found in response.")
            return None
        print(f"✅ Fetched {len(data['Trains'])} trains.")
        return data["Trains"]
    except Exception as e:
        print(f"❌ Error fetching trains: {e}")
        return None

def save_trains(trains):
    with open("trains.json", "w") as f:
        json.dump(trains, f, indent=2)
    print("💾 Saved trains to trains.json.")

def upload_to_netlify():
    print("🚀 Uploading trains.json to Netlify...")
    url = f"https://api.netlify.com/api/v1/sites/{netlify_site_id}/deploys"
    files = {"file": ("trains.json", open("trains.json", "rb"))}
    headers = {"Authorization": f"Bearer {netlify_token}"}
    response = requests.post(url, files=files, headers=headers)
    print(f"📡 Upload status: {response.status_code}")
    if response.ok:
        print("✅ Upload to Netlify successful.")
    else:
        print(f"❌ Netlify upload failed: {response.text}")

while True:
    trains = fetch_trains()
    if trains:
        save_trains(trains)
        upload_to_netlify()
    else:
        print("⚠️ No trains fetched, skipping save/upload.")
    time.sleep(60)