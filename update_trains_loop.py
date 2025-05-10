import requests
import time
import os

cookie = os.environ["TF_COOKIE"]
headers = {
    "Cookie": f".ASPXAUTH={cookie}",
    "User-Agent": "Mozilla/5.0"
}

while True:
    try:
        r = requests.get("https://trainfinder.otenko.com/Home/GetViewPortData", headers=headers)
        r.raise_for_status()

        with open("trains.json", "w") as f:
            f.write(r.text)

        print("✅ Updated trains.json")
    except Exception as e:
        print(f"❌ Error: {e}")

    time.sleep(30)