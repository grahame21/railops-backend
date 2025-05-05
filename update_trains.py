import os
import requests
import json

TRAINFINDER_COOKIE = os.environ.get("TRAINFINDER_COOKIE")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN")
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID")

if not TRAINFINDER_COOKIE:
    print("❌ Missing TRAINFINDER_COOKIE. Aborting.")
    exit(1)

headers = {
    "Cookie": f".ASPXAUTH={TRAINFINDER_COOKIE}",
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": "https://trainfinder.otenko.com/home/nextlevel",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://trainfinder.otenko.com"
}

try:
    response = requests.post("https://trainfinder.otenko.com/Home/GetViewPortData", headers=headers)
    response.raise_for_status()
    data = response.json()

    with open("trains.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("✅ Train data updated successfully.")

    if NETLIFY_TOKEN and NETLIFY_SITE_ID:
        print("🚀 Uploading trains.json to Netlify...")
        deploy_url = f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/files/trains.json"
        with open("trains.json", "rb") as f:
            r = requests.put(deploy_url, headers={
                "Authorization": f"Bearer {NETLIFY_TOKEN}",
                "Content-Type": "application/json"
            }, data=f.read())
        if r.status_code == 200:
            print("✅ trains.json deployed to Netlify.")
        else:
            print(f"⚠️ Netlify upload failed: {r.status_code} - {r.text}")

except Exception as e:
    print(f"❌ Error: {e}")
