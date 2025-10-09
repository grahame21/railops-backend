# fetch_trains.py
import json, requests, sys
from pathlib import Path

COOKIE_FILE = Path("cookie.txt")
OUT_FILE = Path("trains.json")
BASE = "https://trainfinder.otenko.com"

if not COOKIE_FILE.exists():
    print("❌ cookie.txt not found. Run trainfinder_fetch_pw.py first.")
    sys.exit(1)

aspx = COOKIE_FILE.read_text().strip()
s = requests.Session()
s.cookies.set(".ASPXAUTH", aspx, domain="trainfinder.otenko.com", path="/")

headers = {
    "Accept": "*/*",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Origin": BASE,
    "Referer": f"{BASE}/Home/NextLevel",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "X-Requested-With": "XMLHttpRequest",
}

# Melbourne viewport (adjust as needed)
payload = {
    "nwLat": -37.5,
    "nwLng": 144.5,
    "seLat": -38.2,
    "seLng": 145.5,
    "zm": 7
}

print("🌍 Fetching trains in viewport:", payload)

r = s.post(f"{BASE}/Home/GetViewPortData", headers=headers, data=payload)

if not r.ok:
    print(f"❌ HTTP {r.status_code}")
    print(r.text[:300])
    sys.exit(1)

try:
    data = r.json()
except Exception as e:
    print("❌ JSON decode failed:", e)
    print(r.text[:300])
    sys.exit(1)

OUT_FILE.write_text(json.dumps(data, indent=2))
print(f"✅ Saved {OUT_FILE} ({OUT_FILE.stat().st_size} bytes)")
