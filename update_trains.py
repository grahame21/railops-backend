import os
import json
import requests

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)

# Load TrainFinder cookie from environment or file
cookie_path = "cookie.txt"
if not os.path.exists(cookie_path):
    print("❌ Missing cookie.txt file.")
    exit(1)

with open(cookie_path, "r") as f:
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
    output = []

    for train in data.get("Trains", []):
        if train.get("Latitude") and train.get("Longitude"):
            output.append({
                "loco": train["LocoNum"],
                "lat": train["Latitude"],
                "lon": train["Longitude"],
                "operator": train.get("Operator", ""),
                "service": train.get("Service", ""),
                "status": train.get("Status", "")
            })

    with open("static/trains.json", "w") as f:
        json.dump(output, f, indent=2)
    print("✅ trains.json updated in static/")
else:
    print(f"❌ Failed to fetch train data: {response.status_code}")