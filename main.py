import os
import re
import time
from urllib.parse import urlencode

import requests
from flask import Flask, request, jsonify, Response

# =========================================
# Config
# =========================================
TRAINFINDER_BASE = "https://trainfinder.otenko.com"

# Pages to visit to pick up cookies / tokens automatically (best-effort)
WARMUP_PATHS = [
    "/", "/Home", "/home",
    "/Home/Index", "/home/index",
    "/Home/NextLevel", "/home/nextlevel",
]

# Endpoints that (in your logs) handled the viewport POST
POST_ENDPOINTS = [
    "/Home/GetViewPortData",
    "/home/GetViewPortData",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36"
)

# =========================================
# In-memory “settings” (you set these via routes)
# =========================================
ASPXAUTH_VALUE = os.environ.get("ASPXAUTH", "").strip()
VTOKEN_COOKIE = ""  # __RequestVerificationToken cookie token
VTOKEN_FORM   = ""  # __RequestVerificationToken hidden form token

app = Flask(__name__)

# =========================================
# Helpers
# =========================================
def _session_with_auth():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    if ASPXAUTH_VALUE:
        s.cookies.set(".ASPXAUTH", ASPXAUTH_VALUE, domain="trainfinder.otenko.com", path="/")
    if VTOKEN_COOKIE:
        s.cookies.set("__RequestVerificationToken", VTOKEN_COOKIE, domain="trainfinder.otenko.com", path="/")
    return s

def _extract_verification_token_from_html(html: str) -> str:
    if not html:
        return ""
    # Hidden input
    m = re.search(
        r'<input[^>]*name=["\']__RequestVerificationToken["\'][^>]*value=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if m: return m.group(1)
    # Meta tag
    m = re.search(
        r'<meta[^>]*name=["\']__RequestVerificationToken["\'][^>]*content=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if m: return m.group(1)
    # JS assignment
    m = re.search(
        r'__RequestVerificationToken\s*=\s*[\'"]([^\'"]+)[\'"]',
        html, re.IGNORECASE)
    if m: return m.group(1)
    return ""

def _token_header_candidates(session: requests.Session, form_token: str):
    cookie_token = session.cookies.get("__RequestVerificationToken", domain="trainfinder.otenko.com")
    headers_list = []
    if cookie_token and form_token:
        headers_list.append({"RequestVerificationToken": f"{cookie_token}:{form_token}"})
    if form_token:
        headers_list.append({"RequestVerificationToken": form_token})
        headers_list.append({"__RequestVerificationToken": form_token})
    headers_list.append({})  # last resort
    return headers_list

def _warmup_and_try_get_tokens(session: requests.Session, lat=None, lng=None, zm=None):
    warm = []
    got_form = ""
    for path in WARMUP_PATHS:
        url = TRAINFINDER_BASE + path
        if path.lower().endswith("nextlevel") and lat is not None:
            url += "?" + urlencode({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm or 12)})
        try:
            r = session.get(url, timeout=15)
            warm.append({"url": url, "status": r.status_code, "bytes": len(r.content)})
            if r.ok and not got_form:
                got_form = _extract_verification_token_from_html(r.text)
            # if we saw a token, we can stop early
            if got_form:
                break
        except Exception as ex:
            warm.append({"url": url, "error": str(ex)})
    cookie_token = session.cookies.get("__RequestVerificationToken", domain="trainfinder.otenko.com") or ""
    return got_form, cookie_token, warm

def _post_viewport(session: requests.Session, form: dict, token_headers: dict, referer_url: str):
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TRAINFINDER_BASE,
        "Referer": referer_url,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": USER_AGENT,
    }
    headers.update(token_headers)

    attempts = []
    for ep in POST_ENDPOINTS:
        url = TRAINFINDER_BASE + ep
        t0 = time.time()
        try:
            resp = session.post(url, data=form, headers=headers, timeout=20)
            ms = int((time.time() - t0) * 1000)
            preview = resp.text[:200]
            looks_like_html = "<!DOCTYPE html" in preview or "<html" in preview.lower()
            attempts.append({
                "url": url,
                "status": resp.status_code,
                "ms": ms,
                "bytes": len(resp.content),
                "looks_like_html": looks_like_html,
                "preview": preview,
            })
            if resp.ok and resp.text.strip():
                return resp, attempts
        except Exception as ex:
            attempts.append({"url": url, "error": str(ex)})
    return None, attempts

def fetch_viewport(lat: float, lng: float, zm: int):
    session = _session_with_auth()

    # 1) Try to auto-pick up tokens (won’t overwrite manual ones)
    auto_form = auto_cookie = ""
    if not VTOKEN_FORM or not VTOKEN_COOKIE:
        auto_form, auto_cookie, warm = _warmup_and_try_get_tokens(session, lat, lng, zm)
    else:
        warm = []

    # decide which tokens to use
    form_token   = VTOKEN_FORM or auto_form or ""
    cookie_token = VTOKEN_COOKIE or auto_cookie or session.cookies.get("__RequestVerificationToken", domain="trainfinder.otenko.com") or ""

    token_headers_list = _token_header_candidates(session, form_token)

    # 2) Try several form shapes
    forms = [
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
        # If the site actually wants bounds, your old logs showed these names:
        # (we compute ~2km bounds just to test; TrainFinder ignores if not needed)
    ]

    referer_url = f"{TRAINFINDER_BASE}/home/nextlevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    diag_attempts = []
    for form in forms:
        for th in token_headers_list:
            resp, attempts = _post_viewport(session, form, th, referer_url)
            diag_attempts.append({"form": form, "token_headers": th, "attempts": attempts})
            if resp and resp.ok and resp.text.strip():
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text}
                return {
                    "used_cookie": bool(ASPXAUTH_VALUE),
                    "verification_token_present": bool(form_token),
                    "tokens": {
                        "cookie_token": bool(cookie_token),
                        "form_token": bool(form_token)
                    },
                    "viewport": {
                        "status": resp.status_code,
                        "bytes": len(resp.content),
                        "looks_like_html": False,
                        "preview": resp.text[:200],
                        "data": data,
                    },
                    "warmup": {"items": warm},
                    "diag": diag_attempts
                }

    return {
        "used_cookie": bool(ASPXAUTH_VALUE),
        "verification_token_present": bool(form_token),
        "tokens": {
            "cookie_token": bool(cookie_token),
            "form_token": bool(form_token)
        },
        "viewport": {"status": 0, "bytes": 0, "looks_like_html": False, "preview": "", "data": None, "note": "no_successful_post"},
        "warmup": {"items": warm},
        "diag": diag_attempts
    }

# =========================================
# Routes
# =========================================
@app.get("/")
def home():
    html = f"""
<!doctype html>
<html><head><meta charset="utf-8"><title>RailOps JSON</title></head>
<body style="font-family:system-ui,Segoe UI,Arial;max-width:800px;margin:24px auto;line-height:1.4">
  <h1>RailOps JSON</h1>
  <p>Quick setup:</p>
  <ol>
    <li>Set your TrainFinder login cookie (.ASPXAUTH) once:<br>
      <code>/set-aspxauth?value=PASTE_FULL_.ASPXAUTH</code>
    </li>
    <li>Check you’re logged in:<br>
      <code>/authcheck</code>
    </li>
    <li><b>Set anti-forgery verification tokens</b> (one time):<br>
      Open TrainFinder, log in, then:
      <ul>
        <li>DevTools → Application → Cookies → <code>https://trainfinder.otenko.com</code> → copy value of <code>__RequestVerificationToken</code> (this is the <i>cookie token</i>).</li>
        <li>On any page, View Source and find <code>&lt;input name="__RequestVerificationToken" value="..."></code> — copy that value (the <i>form token</i>).</li>
      </ul>
      Then visit:<br>
      <code>/set-vtokens?cookie=PASTE_COOKIE_TOKEN&amp;form=PASTE_FORM_TOKEN</code>
    </li>
    <li>Test viewport:<br>
      <code>/debug/viewport?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code>
    </li>
    <li>Frontend JSON (what your app should call):<br>
      <code>/trains?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code>
    </li>
    <li>Scan sample cities:<br>
      <code>/scan</code>
    </li>
  </ol>
  <p style="color:#666">.ASPXAUTH set: <b>{'yes' if ASPXAUTH_VALUE else 'no'}</b> &nbsp; | &nbsp;
     vtoken(cookie): <b>{'yes' if VTOKEN_COOKIE else 'no'}</b> &nbsp; | &nbsp;
     vtoken(form): <b>{'yes' if VTOKEN_FORM else 'no'}</b></p>
</body></html>
"""
    return Response(html, mimetype="text/html")

@app.get("/set-aspxauth")
def set_aspxauth():
    global ASPXAUTH_VALUE
    val = request.args.get("value", "").strip()
    if not val:
        return jsonify({"ok": False, "message": "Provide ?value=<FULL_.ASPXAUTH>"}), 400
    ASPXAUTH_VALUE = val
    os.environ["ASPXAUTH"] = val  # best-effort for restarts
    return jsonify({"ok": True, "message": ".ASPXAUTH stored"})

@app.get("/set-vtokens")
def set_vtokens():
    global VTOKEN_COOKIE, VTOKEN_FORM
    c = request.args.get("cookie", "").strip()
    f = request.args.get("form", "").strip()
    if not c or not f:
        return jsonify({"ok": False, "message": "Need both ?cookie=...&form=..."}), 400
    VTOKEN_COOKIE = c
    VTOKEN_FORM = f
    return jsonify({"ok": True, "message": "verification tokens stored"})

@app.get("/authcheck")
def authcheck():
    s = _session_with_auth()
    url = f"{TRAINFINDER_BASE}/Home/IsLoggedIn"
    try:
        r = s.post(url, headers={
            "X-Requested-With": "XMLHttpRequest",
            "Origin": TRAINFINDER_BASE,
            "Referer": f"{TRAINFINDER_BASE}/home/nextlevel"
        }, timeout=15)
        text = r.text.strip()
        try:
            data = r.json()
        except Exception:
            data = {"raw": text}
        return jsonify({
            "status": r.status_code,
            "bytes": len(r.content),
            "cookie_present": bool(ASPXAUTH_VALUE),
            "email": data.get("email_address") or "",
            "is_logged_in": bool(data.get("is_logged_in")),
            "text": text
        })
    except Exception as ex:
        return jsonify({"status": 0, "cookie_present": bool(ASPXAUTH_VALUE), "error": str(ex)}), 500

@app.get("/debug/viewport")
def debug_viewport():
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
        zm  = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "Provide lat,lng,zm"}), 400
    return jsonify(fetch_viewport(lat, lng, zm))

@app.get("/trains")
def trains():
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm  = int(request.args.get("zm", "12"))
    out = fetch_viewport(lat, lng, zm)
    data = out.get("viewport", {}).get("data")
    if data is not None:
        return jsonify(data)
    return jsonify({
        "error": "upstream_failed",
        "diag": {
            "logged_in": out.get("used_cookie"),
            "vtoken_present": out.get("verification_token_present"),
            "note": out.get("viewport", {}).get("note", "")
        }
    }), 502

@app.get("/scan")
def scan():
    cities = [
        ("Sydney",    -33.8688, 151.2093),
        ("Melbourne", -37.8136, 144.9631),
        ("Brisbane",  -27.4698, 153.0251),
        ("Perth",     -31.9523, 115.8613),
        ("Adelaide",  -34.9285, 138.6007),
    ]
    zooms = [11, 12, 13]
    items = []
    for (name, lat, lng) in cities:
        for zm in zooms:
            r = fetch_viewport(lat, lng, zm)
            vp = r.get("viewport", {})
            items.append({
                "city": name, "lat": lat, "lng": lng, "zm": zm,
                "verification_token_present": r.get("verification_token_present", False),
                "viewport_bytes": vp.get("bytes", 0),
                "looks_like_html": vp.get("looks_like_html", False),
                "note": vp.get("note", "")
            })
    return jsonify({"count": len(items), "results": items})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")), debug=True)
