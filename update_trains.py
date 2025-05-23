import os
import json
import requests

# Ensure the static folder exists
os.makedirs("static", exist_ok=True)

# Load cookie
if not os.path.exists("cookie.txt"):
    print("❌ cookie.txt not found.")
    exit(1)

with open("cookie.txt", "r") as f:
    cookie_value = f.read().strip()

headers = {
    "Cookie": f".ASPXAUTH={cookie_value}",
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://trainfinder.otenko.com/home/nextlevel"
}

url = "https://trainfinder.otenko.com/Home/GetViewPortData"
response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
    trains = data.get("Trains", [])
    results = []

    for train in trains:
        if train.get("Latitude") and train.get("Longitude"):
            results.append({
                "loco": train["LocoNum"],
                "lat": train["Latitude"],
                "lon": train["Longitude"],
                "operator": train.get("Operator", ""),
                "service": train.get("Service", ""),
                "status": train.get("Status", "")
            })

    with open("static/trains.json", "w") as f:
        json.dump(results, f, indent=2)
    print("✅ trains.json written to static/")
else:
    print(f"❌ Error: HTTP {response.status_code}")