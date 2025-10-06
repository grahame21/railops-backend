import os, sys, json, requests
from bs4 import BeautifulSoup

BASE = "https://trainfinder.otenko.com"
LOGIN = f"{BASE}/Home/NextLevel"
ALT_LOGIN = f"{BASE}/Account/Login"
VIEWPORT = f"{BASE}/Home/GetViewPortData"

U = os.environ.get("TRAINFINDER_USERNAME", "").strip()
P = os.environ.get("TRAINFINDER_PASSWORD", "").strip()
if not U or not P:
    print("❌ Missing TRAINFINDER_USERNAME or TRAINFINDER_PASSWORD")
    sys.exit(1)

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE,
})

def token_from(html, cookies):
    soup = BeautifulSoup(html, "lxml")
    # hidden input
    inp = soup.find("input", attrs={"name": "__RequestVerificationToken"})
    if inp and inp.get("value"):
        return inp["value"]
    # meta tag
    meta = soup.find("meta", attrs={"name": "__RequestVerificationToken"})
    if meta and meta.get("content"):
        return meta["content"]
    # cookie variant
    for k in cookies.keys():
        if "__RequestVerificationToken" in k:
            return cookies.get(k)
    return None

def try_login(url):
    r1 = s.get(url, allow_redirects=True, timeout=30)
    tok = token_from(r1.text, s.cookies)
    if not tok:
        return False, "no-token"

    headers = {
        "Origin": BASE,
        "Referer": url,
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "RequestVerificationToken": tok,
    }

    # Try common field names
    candidates = (
        {"UserName": U, "Password": P, "__RequestVerificationToken": tok},
        {"Email": U, "Password": P, "__RequestVerificationToken": tok},
    )

    for payload in candidates:
        r2 = s.post(url, data=payload, headers=headers, allow_redirects=True, timeout=30)
        # success heuristics: logout links or no longer on a login URL
        if ("Logout" in r2.text) or ("Sign out" in r2.text) or ("/Login" not in r2.url):
            return True, "ok"
    return False, "bad-creds"

ok, why = try_login(LOGIN)
if not ok:
    ok, why = try_login(ALT_LOGIN)
if not ok:
    print("❌ Could not log in:", why)
    # Help debugging
    with open("login_debug.html", "w", encoding="utf-8") as f:
        f.write(s.get(BASE, timeout=30).text)
    sys.exit(1)

print("✅ Logged in")

# Fresh token for AJAX after login
r_home = s.get(BASE, timeout=30)
ajax_tok = token_from(r_home.text, s.cookies)

headers = {"X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/"}
if ajax_tok:
    headers["RequestVerificationToken"] = ajax_tok

# Try POST then GET
for m in ("post", "get"):
    try:
        r = getattr(s, m)(VIEWPORT, headers=headers, timeout=30)
        if r.ok:
            try:
                data = r.json()
                with open("trains.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print("✅ trains.json updated")
                sys.exit(0)
            except ValueError:
                pass
    except requests.RequestException:
        pass

print("❌ Failed to fetch viewport data.", r.status_code if 'r' in locals() else "no response")
print((r.text[:400] + "...") if 'r' in locals() else "")
sys.exit(1)
