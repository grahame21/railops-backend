import os
import re
import time
import json
import itertools
import requests
from html import unescape
from datetime import datetime
from typing import Optional, Tuple

URL_BASE = "https://trainfinder.otenko.com"
URL_NEXTLEVEL = f"{URL_BASE}/home/nextlevel"
URL_API = f"{URL_BASE}/Home/GetViewPortData"

# === CONFIG ===
COOKIE_VALUE = os.getenv("ASPXAUTH", ".ASPXAUTH=YOUR_COOKIE_HERE")
FORCED_REFERER = os.getenv("TRAINFINDER_REFERER")  # optional: override viewport completely
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))

VIEWPORTS = [
    ("Australia_centre", -25.2744, 133.7751),
    ("Adelaide", -34.9285, 138.6007),
    ("Melbourne", -37.8136, 144.9631),
    ("Sydney", -33.8688, 151.2093),
    ("Brisbane", -27.4698, 153.0251),
    ("Perth", -31.9523, 115.8613),
    ("Newcastle", -32.9283, 151.7817),
    ("Wagga", -35.1080, 147.3694),
    ("Port_Augusta", -32.4922, 137.7650),
    ("Kalgoorlie", -30.7494, 121.4650),
]
ZOOMS = [6, 7, 8]

# === Helpers ===
def parse_cookie(val: str) -> str:
    return val.replace(".ASPXAUTH=", "").strip()

def mk_referer(lat: float, lng: float, zm: int) -> str:
    # TrainFinder reads viewport hints from the referer query.
    return f"{URL_NEXTLEVEL}?zm={zm}&lat={lat:.5f}&lng={lng:.5f}"

def looks_null_payload(d: dict) -> bool:
    if not isinstance(d, dict) or not d:
        return True
    for v in d.values():
        if v not in (None, [], {}, ""):
            return False
    return True

def extract_anti_forgery_token_from_html(html: str) -> Optional[str]:
    # Try hidden field first
    m = re.search(r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"', html, re.I)
    if m:
        return unescape(m.group(1))
    # Some MVC apps put it in a meta tag
    m = re.search(r'<meta\s+name="__RequestVerificationToken"\s+content="([^"]+)"', html, re.I)
    if m:
        return unescape(m.group(1))
    return None

def get_verification_token_from_session(session: requests.Session) -> Optional[str]:
    # Sometimes provided as a cookie
    for c in session.cookies:
        if c.name.lower() == "__requestverificationtoken" and c.value:
            return c.value
    return None

def fetch_token(session: requests.Session, referer: str) -> Optional[str]:
    # GET nextlevel to seed any tokens/cookies
    headers = {
        "user-agent": UA,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "referer": referer,
    }
    r = session.get(referer, headers=headers, timeout=20)
    r.raise_for_status()
    token = extract_anti_forgery_token_from_html(r.text) or get_verification_token_from_session(session)
    if not token:
        print("⚠️ No __RequestVerificationToken found (hidden/meta/cookie). Will still try without it.")
    return token

def try_api(session: requests.Session, referer: str, token: Optional[str], lat: float, lng: float, zm: int) -> Tuple[Optional[dict], str]:
    # We’ll try 3 strategies in order. Return first non-null.
    strategies = []

    # Strategy A: classic empty body (legacy)
    strategies.append(("empty", {}, "application/x-www-form-urlencoded"))

    # Strategy B: form-encoded viewport (common MVC pattern)
    form_payload = {
        "lat": f"{lat:.5f}",
        "lng": f"{lng:.5f}",
        "zm": str(zm),
    }
    strategies.append(("form", form_payload, "application/x-www-form-urlencoded"))

    # Strategy C: JSON body viewport
    json_payload = {"lat": lat, "lng": lng, "zm": zm}
    strategies.append(("json", json_payload, "application/json"))

    common_headers = {
        "accept": "*/*",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "origin": URL_BASE,
        "referer": referer,
        "sec-ch-ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "user-agent": UA,
    }
    if token:
        # MVC anti-forgery header name is commonly RequestVerificationToken
        common_headers["RequestVerificationToken"] = token

    for name, payload, ctype in strategies:
        headers = dict(common_headers)
        headers["content-type"] = ctype
        try:
            if name == "json":
                resp = session.post(URL_API, headers=headers, json=payload, timeout=25)
            else:
                resp = session.post(URL_API, headers=headers, data=payload, timeout=25)

            if resp.status_code != 200:
                return None, f"HTTP {resp.status_code} via {name}: {resp.text[:200]}"

            data = resp.json()
            if looks_null_payload(data):
                # keep trying next strategy
                continue
            return data, f"ok via {name}"
        except requests.RequestException as e:
            return None, f"network error via {name}: {e}"
        except ValueError as e:
            return None, f"json parse error via {name}: {e}"

    return None, "null after all strategies"

def write_trains_json(data: dict):
    with open("trains.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ {datetime.now().isoformat(timespec='seconds')}  trains.json updated")

def rotate_attempts():
    if FORCED_REFERER:
        # Try to parse lat/lng/zm out of forced referer for payloads; fallback to AU centre if missing.
        lat, lng, zm = -25.2744, 133.7751, 7
        mlat = re.search(r"[?&]lat=(-?\d+(?:\.\d+)?)", FORCED_REFERER)
        mlng = re.search(r"[?&]lng=(-?\d+(?:\.\d+)?)", FORCED_REFERER)
        mzm  = re.search(r"[?&]zm=(\d+)", FORCED_REFERER)
        if mlat: lat = float(mlat.group(1))
        if mlng: lng = float(mlng.group(1))
        if mzm: zm = int(mzm.group(1))
        while True:
            yield FORCED_REFERER, lat, lng, zm
    combos = list(itertools.product(VIEWPORTS, ZOOMS))
    i = 0
    while True:
        (name, lat, lng), zm = combos[i % len(combos)]
        yield mk_referer(lat, lng, zm), lat, lng, zm
        i += 1

# === Main ===
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")

def main():
