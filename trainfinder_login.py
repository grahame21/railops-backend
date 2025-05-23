import requests

with open("cookie.txt", "r") as f:
    cookie_value = f.read().strip()

cookies = {
    ".ASPXAUTH": cookie_value
}

r = requests.get("https://trainfinder.otenko.com/Home/IsLoggedIn", cookies=cookies)

if r.text.strip() == "true":
    print("✅ Still logged in.")
else:
    print("❌ Not logged in.")
