import os, re, json, threading
from flask import Flask, request, jsonify, make_response
import requests

# ----------------------------
# Config / globals
# ----------------------------
UP = "https://trainfinder.otenko.com"
ASPX_LOCK = threading.Lock()
# Read from environment first; you can also set it at runtime via /set-aspxauth
ASPXAUTH_VALUE = os.environ.get("ASPXAUTH", "").strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

app = Flask(__name__)

def set_aspxauth(val: str):
    global ASPXAUTH_VALUE
    with ASPX_LOCK:
        ASPXAUTH_VALUE = val.strip()

def has_cookie() -> bool:
    return bool(ASPXAUTH_VALUE)

def new_session() -> requests.Session:
    """Create a session preloaded with .ASPXAUTH cookie for trainfinder."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    if ASPXAUTH_VALUE:
        # cookie must be for upstream domain
        s.cookies.set(".ASPXAUTH", ASPXAUTH_VALUE, domain="trainfinder.otenko.com", secure=True)
    return s

def get_tokens(s: requests.Session, lat: float, lng: float, zm: int):
    """
    Load /Home/NextLevel to get both the __RequestVerificationToken cookie and
    the hidden input token from the HTML.
    """
    url = f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    r = s.get(url, timeout=20)
    r.raise_for_status()

    # cookie token comes from Set-Cookie -> session cookies
    cookie_tok = s.cookies.get("__RequestVerificationToken")

    # form token appears as hidden input
    m = re.search(r'name="__RequestVerificationToken"\s+value="([^"]+)"', r.text)
    form_tok = m.group(1) if m else ""

    return {
        "cookie": cookie_tok or "",
        "form": form_tok or "",
        "warmup_bytes": len(r.content),
        "warmup_url": url,
        "warmup_status": r.status_code,
        "warmup_preview": r.text[:800]
    }

def get_viewport(s: requests.Session, lat: float, lng: float, zm: int, cookie_tok: str, form_tok: str):
    """
    POST /Home/GetViewPortData with both tokens. Returns (status, text, bytes).
    """
    headers = {
        "Origin": "https://trainfinder.otenko.com",
        "Referer": f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        # ASP.NET anti-forgery combined header:
        "RequestVerificationToken": f"{cookie_tok}:{form_tok}",
    }
    data = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}

    r = s.post(f"{UP}/Home/GetViewPortData", headers=headers, data=data, timeout=20)
    return r.status_code, r.text, len(r.content)

# ----------------------------
# Routes
# ----------------------------

@app.get("/")
def root():
    return """
    <h1>RailOps JSON</h1>
    <p>Set your cookie once: <code>/set-aspxauth?value=PASTE_.ASPXAUTH</code></p>
    <p>Check: <code>/authcheck</code></p>
    <p>Test one view: <code>/debug/viewport?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code></p>
    <p>Scan many: <code>/scan</code></p>
    <p>Simple trains proxy: <code>/trains?lat=-33.8688&amp;lng=151.2093&amp;zm=12</code></p>
    """, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.get("/set-aspxauth")
def set_cookie():
    val = request.args.get("value", "").strip()
    if not val:
        return jsonify({"ok": False, "message": "Provide ?value=PASTE_FULL_.ASPXAUTH"}), 400
    set_aspxauth(val)
    return jsonify({"ok": True, "cookie_present": True, "length": len(val)})

@app.get("/authcheck")
def authcheck():
    s = new_session()
    used = has_cookie()
    try:
        # This endpoint doesn’t need tokens
        r = s.post(f"{UP}/Home/IsLoggedIn", headers={
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://trainfinder.otenko.com",
            "Referer": f"{UP}/",
            "Accept": "*/*",
        }, timeout=20)
        txt = r.text
        email = ""
        try:
            obj = r.json()
            email = obj.get("email_address") or ""
            is_logged_in = bool(obj.get("is_logged_in"))
        except Exception:
            is_logged_in, email = False, ""
        return jsonify({
            "status": r.status_code,
            "bytes": len(r.content),
            "cookie_present": used,
            "is_logged_in": is_logged_in,
            "email": email,
            "text": txt
        })
    except Exception as e:
        return jsonify({"cookie_present": used, "error": str(e)}), 502

@app.get("/debug/viewport")
def debug_viewport():
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm  = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "bad lat/lng/zm"}), 400

    s = new_session()
    used = has_cookie()
    diag = {"used_cookie": used}

    try:
        toks = get_tokens(s, lat, lng, zm)
        cookie_tok, form_tok = toks["cookie"], toks["form"]
        diag["verification_token_present"] = bool(cookie_tok and form_tok)
        diag["warmup"] = {
            "status": toks["warmup_status"],
            "bytes": toks["warmup_bytes"],
        }
        if not diag["verification_token_present"]:
            diag["viewport"] = {"status": 0, "bytes": 0, "note": "no_verification_token"}
            return jsonify({"input": {"lat": lat, "lng": lng, "zm": zm}, "tf": diag, "error": "verification token not found"}), 502

        status, text, nbytes = get_viewport(s, lat, lng, zm, cookie_tok, form_tok)

        looks_like_html = text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html")
        preview = text if len(text) < 800 else text[:800]
        parsed = None
        if not looks_like_html:
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None

        diag["viewport"] = {
            "status": status,
            "bytes": nbytes,
            "looks_like_html": looks_like_html,
            "preview": preview
        }

        return jsonify({
            "input": {"lat": lat, "lng": lng, "zm": zm},
            "tf": diag,
            "data": parsed if parsed is not None else text
        })
    except Exception as e:
        diag["error"] = str(e)
        return jsonify({"input": {"lat": lat, "lng": lng, "zm": zm}, "tf": diag, "error": str(e)}), 502

@app.get("/scan")
def scan():
    # A few AU metros at three zooms
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
                    "verification_token_present": js.get("tf", {}).get("verification_token_present", False),
                    "looks_like_html": vp.get("looks_like_html", False),
                    "viewport_bytes": vp.get("bytes", 0),
                    "note": vp.get("note", "")
                })
            except Exception:
                out.append({"city": name, "lat": lat, "lng": lng, "zm": zm, "error": "parse_failed"})
    return jsonify({"count": len(out), "results": out})

@app.get("/trains")
def trains():
    """Simple proxy that returns upstream JSON for a given lat/lng/zm."""
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm  = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "bad lat/lng/zm"}), 400

    s = new_session()
    toks = get_tokens(s, lat, lng, zm)
    cookie_tok, form_tok = toks["cookie"], toks["form"]
    if not (cookie_tok and form_tok):
        return jsonify({"error": "verification token not found"}), 502

    status, text, _ = get_viewport(s, lat, lng, zm, cookie_tok, form_tok)
    if status != 200:
        return jsonify({"error": "upstream error", "status": status}), 502

    # Return JSON if possible, otherwise raw text
    try:
        return jsonify(json.loads(text))
    except Exception:
        return make_response(text, 200, {"Content-Type": "application/json; charset=utf-8"})

# For Render health checks if needed
@app.get("/healthz")
def healthz():
    return "ok", 200

if __name__ == "__main__":
    # local run: python main.py
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
