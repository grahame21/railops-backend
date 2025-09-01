import os, re, math, json
from flask import Flask, request, jsonify
import requests

UP = "https://trainfinder.otenko.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

app = Flask(__name__)
ASPXAUTH = os.environ.get("ASPXAUTH", "").strip()

def set_cookie(val: str) -> None:
    global ASPXAUTH
    ASPXAUTH = (val or "").strip()

def new_session_with_warmup(lat: float, lng: float, zm: int):
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8,en-AU;q=0.7",
        "Accept": "*/*",
    })
    if ASPXAUTH:
        s.cookies.set(".ASPXAUTH", ASPXAUTH, domain="trainfinder.otenko.com", secure=True)
    token = ""
    html = ""
    try:
        r = s.get(f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", timeout=20)
        html = r.text or ""
        pats = [
            r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"',
            r'name="__RequestVerificationToken"\s+value="([^"]+)"',
            r'meta\s+name="__RequestVerificationToken"\s+content="([^"]+)"',
            r'RequestVerificationToken["\']\s*[:=]\s*["\']([^"\']+)["\']',
            r'__RequestVerificationToken["\']\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        for p in pats:
            m = re.search(p, html, re.IGNORECASE)
            if m:
                token = m.group(1)
                break
        if not token:
            for c in s.cookies:
                if c.name.lower().startswith("__requestverificationtoken"):
                    token = c.value
                    break
    except Exception:
        pass
    return s, token, len(html), html[:4000]

TILE = 256.0

def _lat_to_merc_y(lat: float) -> float:
    lat = max(min(lat, 85.05112878), -85.05112878)
    siny = math.sin(lat * math.pi / 180.0)
    return 0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)

def _lng_to_merc_x(lng: float) -> float:
    return (lng + 180.0) / 360.0

def compute_bounds(lat: float, lng: float, zm: int, px_w: int = 640, px_h: int = 640):
    scale = 2 ** zm
    cx, cy = _lng_to_merc_x(lng), _lat_to_merc_y(lat)
    w_frac = (px_w / TILE) / scale
    h_frac = (px_h / TILE) / scale
    west_x  = cx - w_frac / 2
    east_x  = cx + w_frac / 2
    north_y = cy - h_frac / 2
    south_y = cy + h_frac / 2
    west_lng = west_x * 360.0 - 180.0
    east_lng = east_x * 360.0 - 180.0
    def y_to_lat(y):
        n = math.pi - 2.0 * math.pi * y
        return 180.0 / math.pi * math.atan(0.5 * (math.exp(n) - math.exp(-n)))
    north_lat = y_to_lat(north_y)
    south_lat = y_to_lat(south_y)
    return {"west": round(west_lng, 6), "east": round(east_lng, 6), "north": round(north_lat, 6), "south": round(south_lat, 6)}

def looks_trainy(obj) -> bool:
    if isinstance(obj, dict):
        for k in ("trains", "items", "features", "markers", "results", "data"):
            v = obj.get(k)
            if isinstance(v, list) and v:
                return True
            if isinstance(v, dict):
                if any(isinstance(x, list) and x for x in v.values()):
                    return True
        if any(isinstance(v, list) and v for v in obj.values()):
            return True
    if isinstance(obj, list) and obj:
        return True
    return False

def _ajax_headers(lat, lng, zm, token=""):
    h = {
        "Origin": UP,
        "Referer": f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
    }
    if token:
        h["RequestVerificationToken"] = token
    return h

def try_call(sess, url, method, params_or_data, as_json, lat, lng, zm, token=""):
    headers = _ajax_headers(lat, lng, zm, token)
    if method == "GET":
        r = sess.get(url, headers=headers, timeout=20, params=params_or_data)
    else:
        if as_json:
            r = sess.post(url, headers={**headers, "Content-Type": "application/json"}, json=params_or_data, timeout=20)
        else:
            data = dict(params_or_data)
            if token and "__RequestVerificationToken" not in data:
                data["__RequestVerificationToken"] = token
            r = sess.post(url, headers={**headers, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}, data=data, timeout=20)
    text = r.text or ""
    looks_html = text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html")
    parsed = None
    if not looks_html and text.strip().startswith("{"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
    rec = {
        "url": url,
        "method": method,
        "status": r.status_code,
        "bytes": len(r.content),
        "looks_like_html": looks_html,
    }
    if parsed is not None:
        rec["keys"] = list(parsed.keys()) if isinstance(parsed, dict) else None
        rec["trainy"] = looks_trainy(parsed)
        return rec,
