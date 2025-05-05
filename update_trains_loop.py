import os
import requests
import json
import time

def update_trains():
    try:
        cookie = os.environ["TRAINFINDER_COOKIE"]
        headers = {
            "Content-Type": "application/json",
            "Cookie": f".ASPXAUTH={cookie}",
            "User-Agent": "Mozilla/5.0"
        }
        url = "https://trainfinder.otenko.com/Home/GetViewPortData"
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            with open("trains.json", "w", encoding="utf-8") as f:
                json.dump(response.json(), f, indent=2)
            print("✅ Train data updated.")
        else:
            print(f"❌ Failed to fetch train data: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")

def push_to_netlify():
    try:
        site_id = os.environ["NETLIFY_SITE_ID"]
        token = os.environ["NETLIFY_TOKEN"]
        headers = {
            "Authorization": f"Bearer {token}"
        }
        files = {
            'files': ('trains.json', open('trains.json', 'rb'))
        }
        deploy_url = f"https://api.netlify.com/api/v1/sites/{site_id}/deploys"
        response = requests.post(deploy_url, headers=headers, files=files)
        if response.status_code == 200 or response.status_code == 201:
            print("✅ trains.json pushed to Netlify.")
        else:
            print(f"❌ Failed to push: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"❌ Netlify push error: {e}")

if __name__ == "__main__":
    while True:
        update_trains()
        push_to_netlify()
        time.sleep(60)
