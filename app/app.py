import os
import re
import json
import math
import time
from typing import Dict, Any, Optional

import requests
from flask import Flask, request, jsonify

# -----------------------------
# Config
# -----------------------------
TF_BASE = "https://trainfinder.otenko.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
DEFAULT_LAT = -33.8688
DEFAULT_LNG = 151.2093
DEFAULT_ZM  = 12
VIEW_W = 1024
VIEW_H = 768

app = Flask(__name__)

# Single requests session reused across calls
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept": "*/*",
})

def _set_cookie_from_env():
    """Set .ASPXAUTH cookie from env once, if provided."""
    val = os.getenv("ASPXAUTH", "").strip()
    if not val:
        return False
    # Set cookie for the target domain
    SESSION.cookies.set(".ASPXAUTH", val, domain="trainfinder.otenko.com", path="/")
    return True

COOKIE_SET = _set_cookie_from_env()

def _looks_like_html(s: str) -> bool:
    t = s.strip().lower()
    return t.startswith("<!doctype") or t.startswith("<html")

def _ok_json_bytes(text: str) -> bool:
    # Consider "98 bytes with all nulls" as useless
    return not (len(text) <= 120 and '"favs":null' in text and '"alerts":null' in text)

def _extract_verification_token(html: str) -> Optional[str]:
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html, re.I)
    if m:
        return m.group(1)
    return None

def _warmup(lat: float, lng: float, zm: int) -> Dict[str, Any]:
    url = f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    r = SESSION.get(url, headers={
        "Referer": url,
    }, timeout=15)
    html = r.text
    token = _extract_verification_token(html)
    return {
        "status": r.status_code,
        "bytes": len(html),
        "token": token,
        "url": url,
        "token_found": token is not None
    }

def _is_logged_in() -> Dict[str, Any]:
    url = f"{TF_BASE}/Home/IsLoggedIn"
    r = SESSION.post(url, headers={
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel",
    }, data=b"", timeout=15)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return {"status": r.status_code, "text": json.dumps(data), "bytes": len(r.text)}

def _mpp(lat_deg: float, zoom: int) -> float:
    # meters per pixel at latitude
    return 156543.03392 * math.cos(math.radians(lat_deg)) / (2 ** zoom)

def _bounds_for(lat: float, lng: float, zoom: int, w: int, h: int) -> Dict[str, float]:
    # Quick geographic bbox using meters-per-pixel approximation
    mpp = _mpp(lat, zoom)
    meters_w = mpp * w
    meters_h = mpp * h
    # Convert meters to degrees (rough)
    deg_lat = meters_h / 111320.0
    deg_lng = meters_w / (111320.0 * max(0.1, math.cos(math.radians(lat))))
    north = lat + deg_lat / 2.0
    south = lat - deg_lat / 2.0
    east  = lng + deg_lng / 2.0
    west  = lng - deg_lng / 2.0
    return {
        "north": round(north, 6),
        "south": round(south, 6),
        "east":  round(east, 6),
        "west":  round(west, 6),
    }

def _attempts(lat: float, lng: float, zm: int, token: Optional[str]) -> Dict[str, Any]:
    url = f"{TF_BASE}/Home/GetViewPortData"
    hdrs = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    if token:
        hdrs["RequestVerificationToken"] = token

    bbox = _bounds_for(lat, lng, zm, VIEW_W, VIEW_H)

    forms = [
        # 0) Lat/Lng + zm
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
        # 1) Lat/Lng + zoomLevel
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
        # 2) Bounds + zoomLevel (west/east/north/south)
        {"west": f"{bbox['west']:.6f}", "east": f"{bbox['east']:.6f}",
         "north": f"{bbox['north']:.6f}", "south": f"{bbox['south']:.6f}",
         "zoomLevel": str(zm)},
        # 3) NE/SW + zoomLevel
        {"neLat": f"{bbox['north']:.6f}", "neLng": f"{bbox['east']:.6f}",
         "swLat": f"{bbox['south']:.6f}", "swLng": f"{bbox['west']:.6f}",
         "zoomLevel": str(zm)},
    ]

    results = []
    winner_idx = None
    best_bytes = -1

    for idx, form in enumerate(forms):
        r = SESSION.post(url, data=form, headers=hdrs, timeout=20)
        text = r.text or ""
        looks_html = _looks_like_html(text)
        usable = (r.status_code == 200) and (not looks_html) and _ok_json_bytes(text)

        results.append({
            "form": form,
            "resp": {
                "status": r.status_code,
                "bytes": len(text),
                "looks_like_html": looks_html,
                "preview": text[:160]
            },
            "is_winner": bool(usable)
        })
        if usable and len(text) > best_bytes:
            best_bytes = len(text)
            winner_idx = idx

        # small pause between attempts
        time.sleep(0.1)

    # If nothing usable, still return the biggest non-HTML response
    if winner_idx is None:
        for idx, r in enumerate(results):
            if (r["resp"]["status"] == 200) and (not r["resp"]["looks_like_html"]):
                if r["resp"]["bytes"] > best_bytes:
                    best_bytes = r["resp"]["bytes"]
                    winner_idx = idx

    return {
        "attempts": results,
        "winner": winner_idx if winner_idx is not None else "none",
        "response": results[winner_idx]["resp"] if winner_idx is not None else results[-1]["resp"],
    }

# -----------------------------
# Routes
# -----------------------------

@app.get("/")
def root():
    return jsonify({
        "service": "RailOps JSON",
        "env_cookie_present": bool(os.getenv("ASPXAUTH", "").strip()),
        "cookie_in_session": (SESSION.cookies.get(".ASPXAUTH", domain="trainfinder.otenko.com") is not None),
        "routes": [
            "/set-aspxauth?value=YOUR_TOKEN_ONCE   (optional if using env var)",
            "/authcheck",
            "/debug/viewport?lat=-33.8688&lng=151.2093&zm=12",
            "/scan"
        ]
    })

@app.get("/set-aspxauth")
def set_aspxauth():
    val = request.args.get("value", "").strip()
    ok = False
    if val:
        SESSION.cookies.set(".ASPXAUTH", val, domain="trainfinder.otenko.com", path="/")
        ok = True
    return jsonify({
        "ok": ok,
        "cookie_present": SESSION.cookies.get(".ASPXAUTH", domain="trainfinder.otenko.com") is not None
    })

@app.get("/authcheck")
def authcheck():
    present = SESSION.cookies.get(".ASPXAUTH", domain="trainfinder.otenko.com") is not None
    il = _is_logged_in()
    out = {
        "cookie_present": present,
        "status": il["status"],
        "bytes": il["bytes"],
        "text": il["text"],
        "is_logged_in": False,
        "email": None
    }
    try:
        j = json.loads(il["text"])
        out["is_logged_in"] = bool(j.get("is_logged_in") or j.get("isLoggedIn"))
        out["email"] = j.get("email_address") or j.get("emailAddress") or None
    except Exception:
        pass
    return jsonify(out)

@app.get("/debug/viewport")
def debug_viewport():
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm  = int(request.args.get("zm",  DEFAULT_ZM))

    # Warmup page (to set anti-forgery token & cookies)
    warm = _warmup(lat, lng, zm)
    atts = _attempts(lat, lng, zm, warm.get("token"))

    bbox = _bounds_for(lat, lng, zm, VIEW_W, VIEW_H)
    return jsonify({
        "bounds": {
            "east": bbox["east"],
            "north": bbox["north"],
            "south": bbox["south"],
            "west": bbox["west"],
        },
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            "used_cookie": SESSION.cookies.get(".ASPXAUTH", domain="trainfinder.otenko.com") is not None,
            "verification_token_present": bool(warm.get("token")),
            "warmup": {"status": warm["status"], "bytes": warm["bytes"], "token_found": warm["token_found"]},
            "viewport": atts
        }
    })

CITIES = [
    ("Sydney",    -33.8688, 151.2093),
    ("Melbourne", -37.8136, 144.9631),
    ("Brisbane",  -27.4698, 153.0251),
    ("Perth",     -31.9523, 115.8613),
    ("Adelaide",  -34.9285, 138.6007),
]

@app.get("/scan")
def scan():
    out = []
    for name, lat, lng in CITIES:
        for zm in (11, 12, 13):
            warm = _warmup(lat, lng, zm)
            atts = _attempts(lat, lng, zm, warm.get("token"))
            resp = atts["response"]
            out.append({
                "city": name, "lat": lat, "lng": lng, "zm": zm,
                "warmup_bytes": warm["bytes"],
                "viewport_bytes": resp["bytes"],
                "looks_like_html": resp["looks_like_html"],
                "winner": atts["winner"],
            })
            time.sleep(0.1)
    return jsonify({"count": len(out), "results": out})

if __name__ == "__main__":
    # For local debugging only
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
