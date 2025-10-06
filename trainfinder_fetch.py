# trainfinder_fetch.py
import requests, json
from bs4 import BeautifulSoup
import os

username = os.getenv("TRAINFINDER_USERNAME")
password = os.getenv("TRAINFINDER_PASSWORD")

s = requests.Session()
login_url = "https://trainfinder.otenko.com/Home/NextLevel"

# Get login page
resp = s.get(login_url)
soup = BeautifulSoup(resp.text, "lxml")

token_input = soup.find("input", {"name": "__RequestVerificationToken"})
if not token_input:
    print("❌ Could not find verification token — login page may have changed.")
    exit(1)

token = token_input["value"]

# Prepare login payload
payload = {
    "UserName": username,
    "Password": password,
    "__RequestVerificationToken": token
}

# Login
r = s.post(login_url, data=payload)
if "Logout" not in r.text:
    print("❌ Login failed — check username/password.")
    exit(1)

print("✅ Logged in successfully")

# Fetch live data
fetch_url = "https://trainfinder.otenko.com/Home/GetViewPortData"
headers = {"x-requested-with": "XMLHttpRequest"}

res = s.post(fetch_url, headers=headers)
if not res.ok:
    print("❌ Failed to fetch data:", res.status_code)
    print(res.text)
    exit(1)

data = res.json()
with open("trains.json", "w") as f:
    json.dump(data, f, indent=2)

print("✅ trains.json updated successfully")
