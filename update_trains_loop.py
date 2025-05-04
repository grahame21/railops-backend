import os
import requests
import json
import time
import random
from datetime import datetime

def fetch_trains():
    try:
        cookie_value = os.environ["COOKIE_VALUE"]

        headers = {
            "Cookie": f".ASPXAUTH={cookie_value}",
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://trainfinder.otenko.com/home/nextlevel",
            "X-Requested-With": "XMLHttpRequest"
        }

        url = "https://trainfinder.otenko.com/Home/GetViewPortData"
        response = requests.post(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            for train in data:
                train["fetched_at"] = datetime.utcnow().isoformat()

            with open("trains.json", "w") as f:
                json.dump(data, f, indent=2)

            print(f"[{datetime.now()}] ✅ Updated {len(data)} trains.")
            if len(data) > 0:
                upload_to_netlify()
            else:
                print(f"[{datetime.now()}] ⚠️ Skipping upload — empty train list.")
        else:
            print(f"[{datetime.now()}] ❌ HTTP {response.status_code}: {response.text[:100]}")

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Exception: {e}")

def upload_to_netlify():
    try:
        netlify_token = os.environ["NETLIFY_TOKEN"]
        netlify_site_id = os.environ["NETLIFY_SITE_ID"]

        deploy_url = f"https://api.netlify.com/api/v1/sites/{netlify_site_id}/deploys"
        headers = {
            "Authorization": f"Bearer {netlify_token}"
        }

        with open("trains.json", "rb") as f:
            content = f.read()
            if len(content.strip()) < 10:
                print(f"[{datetime.now()}] ⚠️ Not uploading — file too small.")
                return

        files = {
            'files[trains.json]': open('trains.json', 'rb')
        }

        response = requests.post(deploy_url, headers=headers, files=files)
        if response.status_code == 200:
            print(f"[{datetime.now()}] 🚀 trains.json uploaded to Netlify.")
        else:
            print(f"[{datetime.now()}] ⚠️ Netlify upload failed: {response.status_code} - {response.text[:100]}")

    except Exception as e:
        print(f"[{datetime.now()}] ❌ Upload error: {e}")

# Infinite loop with randomized delay
while True:
    fetch_trains()
    delay = random.randint(30, 60)
    print(f"🔄 Next update in {delay} seconds...\n")
    time.sleep(delay)
