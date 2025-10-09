# fetch_trains.py
import json, sys, requests
from pathlib import Path

COOKIE_FILE = Path("cookie.txt")
OUT = Path("trains.json")
BASE = "https://trainfinder.otenko.com"

if not COOKIE_FILE.exists():
    print("❌ cookie.txt not found. Run trainfinder_fetch_pw.py first."); sys.exit(1)

aspx = COOKIE_FILE.read_text().strip()
s = requests.Session()
s.cookies.set(".ASPXAUTH", aspx, domain="trainfinder.otenko.com", path="/")

headers = {
    "Referer": f"{BASE}/Home/NextLevel",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "railops-backend/gh-actions"
}
url = f"{BASE}/Home/GetViewPortData"

r = s.get(url, headers=headers)
if r.status_code in (403, 405, 404) or r.text.strip().startswith("<"):
    r = s.post(url, headers=headers, data={})

if not r.ok:
    print(f"❌ Fetch failed: HTTP {r.status_code}\n{r.text[:500]}"); sys.exit(1)

try:
    data = r.json()
except Exception:
    data = json.loads(r.text)

OUT.write_text(json.dumps(data, indent=2))
print(f"✅ Wrote {OUT} ({OUT.stat().st_size} bytes)")
