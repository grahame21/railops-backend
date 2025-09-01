import os, json, re
from urllib.parse import urlencode
import requests
from flask import Flask, request, jsonify, make_response

# --------------------
# Config
# --------------------
TF_BASE = "https://trainfinder.otenko.com"
DEFAULT_LAT = -33.8688
DEFAULT_LNG = 151.2093
DEFAULT_ZM  = 12

app = Flask(__name__)
session = requests.Session()
session.headers.update({
    "User-Agent": "RailOps-JSON/1.0 (+render)",
    "Accept": "*/*",
})

def _looks_like_html(text: str) -> bool:
    if not text:
        return False
    t = text.lstrip().lower()
    return t.startswith("<!doctype") or t.startswith("<html")

def _preview(b, n=200):
    try:
        s = b if isinstance(b, str) else b.decode("utf-8", "ignore")
    except Exception:
        return ""
    return s[:n]

def _json_or_none(text):
    try:
        return json.loads(text)
    except Exception:
        return None

def _find_verification_token(html_text):
    """Try to find classic ASP.NET anti-forgery token in HTML."""
    if not html_text:
        return None
    m = re.search(r'name="__RequestVerificationToken"\s+value="([^"]+)"', html_text)
    if m:
        return m.group(1)
    # sometimes meta:
    m2 = re.search(r'<meta[^>]+name="__RequestVerificationToken"[^>]+content="([^"]+)"', html_text, re.I)
    return m2.group(1) if m2 else None

def _warmup(lat, lng, zm):
    u = f"{TF_BASE}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={int(zm)}"
    r = session.get(u, timeout=30)
    html = r.text
    token = _find_verification_token(html)
    # also check for possible anti-forgery cookie names
    cookie_token_keys = [k for k in session.cookies.keys() if "RequestVerificationToken" in k or "Antiforgery" in k]
    return {
        "url": u,
        "status": r.status_code,
        "bytes": len(r.content or b""),
        "has_token": bool(token),
        "token": token or "",
        "cookie_token_keys": cookie_token_keys,
        "preview": _preview(html, 5000),
    }

def _post(url, data=None, extra_headers=None, referer=None):
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Accept": "*/*",
    }
    if referer:
        headers["Referer"] = referer
    if extra_headers:
        headers.update(extra_headers)
    r = session.post(url, data=data or {}, headers=headers, timeout=30)
    text = r.text or ""
    looks_html = _looks_like_html(text)
    parsed = None if looks_html else _json_or_none(text)
    keys = list(parsed.keys()) if isinstance(parsed, dict) else []
    return {
        "url": url,
        "method": "POST",
        "status": r.status_code,
        "bytes": len(text),
        "looks_like_html": looks_html,
        "preview": _preview(text, 300),
        "keys": keys,
        "raw_json": parsed if isinstance(parsed, dict) else None,
    }

@app.get("/")
def index():
    return (
        "RailOps JSON<br>"
        "Set cookie once: <code>/set-aspxauth?value=PASTE_.ASPXAUTH=....</code><br>"
        "Check: <code>/authcheck</code><br>"
        "Warmup HTML: <code>/debug/warmup-html</code><br>"
        "Viewport test: <code>/debug/viewport?lat=-33.8688&lng=151.2093&zm=12</code><br>"
        "Probe (find train endpoints): <code>/probe?lat=-33.8688&lng=151.2093&zm=12</code><br>"
    )

@app.get("/set-aspxauth")
def set_aspxauth():
    value = request.args.get("value", "").strip()
    # Accept either ".ASPXAUTH=<token>" or just the token part.
    if value and not value.startswith(".ASPXAUTH="):
        value = ".ASPXAUTH=" + value
    if not value:
        return jsonify({"ok": False, "error": "Provide ?value=FULL_.ASPXAUTH=..."}), 400

    # Wipe any previous one, set new
    if ".ASPXAUTH" in session.cookies:
        del session.cookies[".ASPXAUTH"]
    # split name=value
    try:
        name, token = value.split("=", 1)
    except ValueError:
        return jsonify({"ok": False, "error": "Bad format. Include .ASPXAUTH=..."}), 400

    session.cookies.set(name, token, domain="trainfinder.otenko.com", path="/")
    return jsonify({"ok": True, "set": True, "cookie_name": name, "token_len": len(token)})

@app.get("/authcheck")
def authcheck():
    # Fast check
    has_cookie = (".ASPXAUTH" in session.cookies)
    try:
        r = session.post(f"{TF_BASE}/Home/IsLoggedIn",
                         headers={"X-Requested-With": "XMLHttpRequest", "Origin": TF_BASE},
                         timeout=30)
        ok = (r.status_code == 200)
        payload = _json_or_none(r.text) or {}
        email = payload.get("email_address") or ""
        is_logged_in = bool(payload.get("is_logged_in"))
        return jsonify({
            "cookie_present": has_cookie,
            "status": r.status_code,
            "bytes": len(r.text or ""),
            "text": r.text,
            "is_logged_in": is_logged_in,
            "email": email,
        })
    except Exception as e:
        return jsonify({"cookie_present": has_cookie, "error": str(e)}), 500

@app.get("/debug/warmup-html")
def warmup_html():
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm = int(request.args.get("zm", DEFAULT_ZM))
    info = _warmup(lat, lng, zm)
    return jsonify({
        "status": info["status"],
        "bytes": info["bytes"],
        "has_token": info["has_token"],
        "cookie_token_keys": info["cookie_token_keys"],
        "preview": info["preview"],
    })

@app.get("/debug/viewport")
def debug_viewport():
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm = int(request.args.get("zm", DEFAULT_ZM))

    warm = _warmup(lat, lng, zm)
    token = warm["token"] or ""
    referer = warm["url"]
    hdr = {}
    # If we found a token, try adding both header and form key (covers both ASP.NET styles)
    forms = []
    if token:
        hdr["RequestVerificationToken"] = token

    # 3 shapes that TF has accepted before; include zoom both as 'zm' and 'zoomLevel'
    forms.append({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)})
    forms.append({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)})
    # Bounds
    # Fake mercator-ish bounds around the center (just to try both styles)
    # In your earlier logs you computed them; we’ll keep it simple here:
    forms.append({"neLat": f"{lat-0.09:.6f}", "neLng": f"{lng+0.17:.6f}",
                  "swLat": f"{lat+0.09:.6f}", "swLng": f"{lng-0.17:.6f}",
                  "zoomLevel": str(zm)})

    attempts = []
    for f in forms:
        res = _post(f"{TF_BASE}/Home/GetViewPortData", data=f, extra_headers=hdr, referer=referer)
        res["form"] = f
        attempts.append(res)

    # Pick the first non-HTML JSON as "response"
    winner = None
    for i, a in enumerate(attempts):
        if a["status"] == 200 and not a["looks_like_html"]:
            winner = i
            break

    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            "used_cookie": (".ASPXAUTH" in session.cookies),
            "verification_token_present": bool(token),
            "viewport": {
                "attempts": attempts,
                "response": attempts[winner] if winner is not None else None,
                "winner": winner if winner is not None else "none",
            },
            "warmup": {"bytes": warm["bytes"], "status": warm["status"], "token_found": warm["has_token"]},
        }
    })

@app.get("/probe")
def probe():
    """
    Tries a handful of plausible endpoints to discover where trains might live.
    We don't know the exact path; this reports back raw findings so we stop guessing.
    """
    lat = float(request.args.get("lat", DEFAULT_LAT))
    lng = float(request.args.get("lng", DEFAULT_LNG))
    zm = int(request.args.get("zm", DEFAULT_ZM))

    warm = _warmup(lat, lng, zm)
    token = warm["token"] or ""
    referer = warm["url"]
    hdr = {"X-Requested-With": "XMLHttpRequest", "Origin": TF_BASE, "Referer": referer}
    if token:
        hdr["RequestVerificationToken"] = token

    # Try the viewport first (known to be real but user-data-ish)
    payloads = [
        ("Home/GetViewPortData", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}),
        ("Home/GetViewPortData", {"neLat": f"{lat-0.09:.6f}", "neLng": f"{lng+0.17:.6f}",
                                  "swLat": f"{lat+0.09:.6f}", "swLng": f"{lng-0.17:.6f}",
                                  "zoomLevel": str(zm)}),

        # Known 404s you tested — we still include to keep a single place to see status
        ("Home/GetTrains", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}),
        ("Home/Trains", {}),

        # A few reasonable guesses based on field names in the JSON:
        ("Home/GetATCS", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}),
        ("Home/GetAtcs", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}),
        ("Home/GetAtcsObj", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}),
        ("Home/GetAtcsGomi", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}),

        # Simple API-looking guesses:
        ("api/trains", {}),
        ("api/viewport", {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}),
    ]

    results = []
    for path, data in payloads:
        url = f"{TF_BASE}/{path}"
        try:
            r = session.request("POST" if data else "GET", url,
                                data=data if data else None, headers=hdr, timeout=30)
            text = r.text or ""
            parsed = _json_or_none(text)
            results.append({
                "url": url,
                "method": "POST" if data else "GET",
                "status": r.status_code,
                "bytes": len(text),
                "looks_like_html": _looks_like_html(text),
                "keys": list(parsed.keys()) if isinstance(parsed, dict) else [],
                "preview": _preview(text, 300),
            })
        except Exception as e:
            results.append({"url": url, "error": str(e)})

    return jsonify({
        "used_cookie": (".ASPXAUTH" in session.cookies),
        "token_present": bool(token),
        "warmup_status": warm["status"],
        "warmup_has_token": warm["has_token"],
        "results": results
    })

# Render/Heroku health check sends HEAD /
@app.route("/", methods=["HEAD"])
def head_root():
    return ("", 200)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
