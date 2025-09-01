import os, re, json, threading
from typing import Tuple, Optional
from flask import Flask, request, jsonify, make_response
import requests

UP = "https://trainfinder.otenko.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

app = Flask(__name__)

# -------------------------------
# In-memory state (thread-safe)
# -------------------------------
STATE_LOCK = threading.Lock()
ASPXAUTH = os.environ.get("ASPXAUTH", "").strip()
VTOKEN_COOKIE = os.environ.get("VTOKEN_COOKIE", "").strip()   # left side (cookie token)
VTOKEN_FORM   = os.environ.get("VTOKEN_FORM", "").strip()     # right side (form token)

def set_aspxauth(value: str):
    global ASPXAUTH
    with STATE_LOCK:
        ASPXAUTH = value.strip()

def set_vtokens(cookie_tok: str, form_tok: str):
    global VTOKEN_COOKIE, VTOKEN_FORM
    with STATE_LOCK:
        VTOKEN_COOKIE = (cookie_tok or "").strip()
        VTOKEN_FORM   = (form_tok or "").strip()

def have_vtokens() -> bool:
    with STATE_LOCK:
        return bool(VTOKEN_COOKIE and VTOKEN_FORM)

def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
        "Upgrade-Insecure-Requests": "1",
    })
    if ASPXAUTH:
        s.cookies.set(".ASPXAUTH", ASPXAUTH, domain="trainfinder.otenko.com", secure=True)
    return s

# -------------------------------
# Token harvesting helpers
# -------------------------------
TOKEN_INPUT_RE = re.compile(
    r'name=["\']__RequestVerificationToken["\']\s+value=["\']([^"\']+)["\']',
    re.I
)

def _cookie_token_from_jar(jar) -> str:
    for c in jar:
        if c.name.startswith("__RequestVerificationToken"):
            return c.value
    return ""

def _warm_headers(navigate: bool = True) -> dict:
    if navigate:
        return {
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
        }
    else:
        return {
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "X-Requested-With": "XMLHttpRequest",
        }

def harvest_tokens(s: requests.Session, lat: float, lng: float, zm: int):
    """
    Try to load a full HTML page that renders both the anti-forgery cookie
    and the hidden form token. If a JS challenge blocks us, this may fail.
    """
    pages = [
        f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
        f"{UP}/Home/Index",
        f"{UP}/Home",
        f"{UP}/",
    ]
    last = {"url": "", "status": 0, "bytes": 0, "looks_like_html": False, "preview": ""}
    cookie_tok, form_tok = "", ""

    for url in pages:
        r = s.get(url, headers=_warm_headers(True), timeout=20)
        last = {
            "url": r.url,
            "status": r.status_code,
            "bytes": len(r.content),
            "looks_like_html": r.text.strip().startswith("<!DOCTYPE") or r.text.strip().startswith("<html"),
            "preview": (r.text[:800] if r.text else "")
        }
        if not cookie_tok:
            cookie_tok = _cookie_token_from_jar(s.cookies)

        if not form_tok and last["looks_like_html"]:
            m = TOKEN_INPUT_RE.search(r.text)
            if m:
                form_tok = m.group(1)

        if cookie_tok and form_tok:
            break

    return cookie_tok, form_tok, last

def post_viewport(s: requests.Session, lat: float, lng: float, zm: int,
                  cookie_tok: str, form_tok: str) -> Tuple[int, str, int]:
    """
    POST /Home/GetViewPortData with tokens in:
      - header RequestVerificationToken: "<cookie>:<form>"
      - header X-RequestVerificationToken: "<form>"
      - form field __RequestVerificationToken: "<form>"
    """
    headers = {
        **_warm_headers(False),
        "Origin": UP,
        "Referer": f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "*/*",
        "RequestVerificationToken": f"{cookie_tok}:{form_tok}",
        "X-RequestVerificationToken": form_tok,
    }
    data = {
        "__RequestVerificationToken": form_tok,
        "lat": f"{lat:.6f}",
        "lng": f"{lng:.6f}",
        "zm": str(zm),
    }
    r = s.post(f"{UP}/Home/GetViewPortData", headers=headers, data=data, timeout=20)
    return r.status_code, r.text, len(r.content)

# -------------------------------
# Routes
# -------------------------------
@app.get("/")
def root():
    return """
    <h1>RailOps JSON</h1>
    <p>1) Set cookie once: <code>/set-aspxauth?value=PASTE_.ASPXAUTH</code></p>
    <p>2) (If needed) Set verification token captured in your browser:<br>
       <code>/set-vtoken?cookie=COOKIE_TOKEN&form=FORM_TOKEN</code></p>
    <p>Check: <code>/authcheck</code></p>
    <p>Debug: <code>/debug/viewport?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code></p>
    <p>Scan: <code>/scan</code></p>
    <p>Data: <code>/trains?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code></p>
    """, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.get("/set-aspxauth")
def set_aspx():
    val = request.args.get("value", "").strip()
    if not val:
        return jsonify({"ok": False, "message": "Provide ?value=PASTE_FULL_.ASPXAUTH"}), 400
    set_aspxauth(val)
    return jsonify({"ok": True, "cookie_present": True, "length": len(val)})

@app.get("/set-vtoken")
def set_vtoken():
    """
    Easiest path: paste the tokens your browser used:
    - cookie token (left side): from header RequestVerificationToken before the colon
    - form token (right side): from header X-RequestVerificationToken (or after the colon)
    """
    ck = request.args.get("cookie", "").strip()
    fm = request.args.get("form", "").strip()
    if not ck or not fm:
        return jsonify({"ok": False, "message": "Provide ?cookie=...&form=..."}), 400
    set_vtokens(ck, fm)
    return jsonify({"ok": True, "cookie_len": len(ck), "form_len": len(fm)})

@app.get("/clear-vtoken")
def clear_vtoken():
    set_vtokens("", "")
    return jsonify({"ok": True, "cleared": True})

@app.get("/authcheck")
def authcheck():
    s = new_session()
    try:
        r = s.post(f"{UP}/Home/IsLoggedIn", headers={
            **_warm_headers(False),
            "Origin": UP,
            "Referer": f"{UP}/",
            "Accept": "*/*",
        }, timeout=20)
        email = ""
        logged = False
        try:
            j = r.json()
            email = j.get("email_address") or ""
            logged = bool(j.get("is_logged_in"))
        except Exception:
            pass
        with STATE_LOCK:
            token_ready = bool(VTOKEN_COOKIE and VTOKEN_FORM)
        return jsonify({
            "status": r.status_code,
            "bytes": len(r.content),
            "cookie_present": bool(ASPXAUTH),
            "is_logged_in": logged,
            "email": email,
            "verification_token_ready": token_ready,
        })
    except Exception as e:
        return jsonify({"cookie_present": bool(ASPXAUTH), "error": str(e)}), 502

@app.get("/debug/viewport")
def debug_viewport():
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm  = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "bad lat/lng/zm"}), 400

    s = new_session()

    # Try manual tokens first (if you set them)
    with STATE_LOCK:
        ck, fm = VTOKEN_COOKIE, VTOKEN_FORM

    diag = {"used_cookie": bool(ASPXAUTH)}

    if ck and fm:
        status, text, n = post_viewport(s, lat, lng, zm, ck, fm)
        diag["used_manual_tokens"] = True
        looks_like_html = text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html")
        return jsonify({
            "input": {"lat": lat, "lng": lng, "zm": zm},
            "tf": {
                **diag,
                "viewport": {"status": status, "bytes": n, "looks_like_html": looks_like_html},
            },
            "data": (json.loads(text) if (not looks_like_html and text.strip().startswith("{")) else text)
        })

    # Otherwise try to harvest automatically
    cookie_tok, form_tok, last = harvest_tokens(s, lat, lng, zm)
    diag.update({
        "token_lengths": {"cookie": len(cookie_tok or ""), "form": len(form_tok or "")},
        "verification_token_present": bool(cookie_tok and form_tok),
        "warmup": {"url": last.get("url",""), "status": last.get("status",0), "bytes": last.get("bytes",0)},
    })

    if not (cookie_tok and form_tok):
        return jsonify({"error": "verification token not found", "input": {"lat": lat, "lng": lng, "zm": zm}, "tf": diag}), 502

    status, text, n = post_viewport(s, lat, lng, zm, cookie_tok, form_tok)
    looks_like_html = text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html")
    preview = text if len(text) <= 800 else text[:800]
    parsed = None
    if not looks_like_html:
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None

    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            **diag,
            "viewport": {"status": status, "bytes": n, "looks_like_html": looks_like_html, "preview": preview},
        },
        "data": parsed if parsed is not None else text
    })

@app.get("/scan")
def scan():
    cities = [
        ("Sydney",    -33.8688, 151.2093),
        ("Melbourne", -37.8136, 144.9631),
        ("Brisbane",  -27.4698, 153.0251),
        ("Perth",     -31.9523, 115.8613),
        ("Adelaide",  -34.9285, 138.6007),
    ]
    zms = [11, 12, 13]
    out = []
    for name, lat, lng in cities:
        for zm in zms:
            resp = app.test_client().get(f"/debug/viewport?lat={lat}&lng={lng}&zm={zm}")
            try:
                js = json.loads(resp.get_data(as_text=True))
                vp = js.get("tf", {}).get("viewport", {})
                out.append({
                    "city": name, "lat": lat, "lng": lng, "zm": zm,
                    "verification_token_present": js.get("tf", {}).get("verification_token_present", True),
                    "viewport_bytes": vp.get("bytes", 0),
                    "looks_like_html": vp.get("looks_like_html", False),
                })
            except Exception:
                out.append({"city": name, "lat": lat, "lng": lng, "zm": zm, "error": "parse_failed"})
    return jsonify({"count": len(out), "results": out})

@app.get("/trains")
def trains():
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm  = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "bad lat/lng/zm"}), 400

    s = new_session()

    # prefer manual tokens if available
    with STATE_LOCK:
        ck, fm = VTOKEN_COOKIE, VTOKEN_FORM

    if not (ck and fm):
        ck, fm, _ = harvest_tokens(s, lat, lng, zm)

    if not (ck and fm):
        return jsonify({"error": "verification token not found"}), 502

    status, text, _ = post_viewport(s, lat, lng, zm, ck, fm)
    if status != 200:
        return jsonify({"error": "upstream error", "status": status}), 502

    try:
        return jsonify(json.loads(text))
    except Exception:
        return make_response(text, 200, {"Content-Type": "application/json; charset=utf-8"})

@app.get("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
