import requests
import json
import os

cookie = os.getenv("ASPXAUTH")

headers = {
    "Cookie": f".ASPXAUTH={cookie}",
    "User-Agent": "Mozilla/5.0"
}

r = requests.get("https://trainfinder.otenko.com/Home/GetViewPortData", headers=headers)

if r.status_code == 200:
    with open("static/trains.json", "w") as f:
        json.dump(r.json(), f)
    print("✅ trains.json updated.")
else:
    print(f"❌ Failed to fetch train data: {r.status_code}")
