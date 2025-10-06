import os, json, sys, re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE = "https://trainfinder.otenko.com/"
LOGIN_PATHS = ["Home/NextLevel", "Account/Login", "Home/Login"]
VIEW_URL = urljoin(BASE, "Home/GetViewPortData")

USERNAME = os.environ.get("TRAINFINDER_USERNAME","")
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD","")

def extract_form(html):
    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form") or soup
    payload = {}
    for i in form.find_all("input"):
        n = i.get("name")
        if not n: 
            continue
        payload[n] = i.get("value", "")
    uname_key = next((k for k in payload if any(t in k.lower() for t in ["user","email","login"])), "UserName")
    pwd_key   = next((k for k in payload if "pass" in k.lower()), "Password")
    token = None
    tok_input = form.find("input", {"name": "__RequestVerificationToken"})
    if tok_input and tok_input.get("value"):
        token = tok_input["value"]
    if not token:
        meta = soup.find("meta", {"name": "__RequestVerificationToken"})
        if meta and meta.get("content"): 
            token = meta["content"]
    action = form.get("action") or "Home/NextLevel"
    return payload, uname_key, pwd_key, token, action, soup

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
})

logged_in = False
last_html = ""
for path in LOGIN_PATHS:
    url = urljoin(BASE, path)
    try:
        r = s.get(url, allow_redirects=True, timeout=20)
    except Exception as e:
        print(f"⚠️ Failed GET {url}: {e}")
        continue

    last_html = r.text
    payload, uname_key, pwd_key, token, action, soup = extract_form(r.text)
    payload[uname_key] = USERNAME
    payload[pwd_key]   = PASSWORD
    if token:
        payload["__RequestVerificationToken"] = token
    post_url = action if action.startswith("http") else urljoin(BASE, action)
    headers = {
        "Referer": url,
        "Origin": BASE.rstrip("/"),
    }
    if token:
        headers["RequestVerificationToken"] = token

    try:
        pr = s.post(post_url, data=payload, headers=headers, allow_redirects=True, timeout=20)
    except Exception as e:
        print(f"⚠️ Failed POST {post_url}: {e}")
        continue

    last_html = pr.text
    if any(x in pr.text for x in ["Logout", "Sign out", "Welcome"]):
        print(f"✅ Logged in via {path} (token: {'yes' if token else 'no'})")
        logged_in = True
        break

if not logged_in:
    open("login_debug.html","w",encoding="utf-8").write(last_html)
    print("❌ Login failed. Saved login_debug.html for inspection.")
    sys.exit(1)

headers = {"X-Requested-With": "XMLHttpRequest", "Referer": BASE}
try:
    res = s.post(VIEW_URL, headers=headers, timeout=30)
    if not res.ok:
        res = s.get(VIEW_URL, headers=headers, timeout=30)
except Exception as e:
    print("⚠️ Data fetch failed:", e)
    sys.exit(1)

try:
    data = res.json()
except Exception:
    data = {"status": res.status_code, "preview": res.text[:400]}

with open("trains.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("✅ trains.json updated")
