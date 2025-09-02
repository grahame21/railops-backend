import json, math, time
from urllib.parse import urlencode
import requests
from flask import Flask, request, jsonify, Response

# -----------------------------
# Config
# -----------------------------
TARGET = "https://trainfinder.otenko.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8,en-AU;q=0.7",
})

app = Flask(__name__)

def _xhr_headers(referer=None):
    h = {
        "Accept": "*/*",
        "Origin": TARGET,
        "X-Requested-With": "XMLHttpRequest",
    }
    if referer:
        h["Referer"] = referer
    return h

def _has_cookie(name=".ASPXAUTH"):
    return any(c.name == name for c in session.cookies)

def _get_cookie(name):
    for c in session.cookies:
        if c.name == name:
            return c.value
    return ""

def _set_cookie(name, val, domain="trainfinder.otenko.com", path="/"):
    # wipe old
    if _has_cookie(name):
        try:
            del session.cookies[name]
        except Exception:
            pass
    session.cookies.set(name, val, domain=domain, path=path)

def _is_logged_in():
    """POST /Home/IsLoggedIn, like the site does."""
    url = f"{TARGET}/Home/IsLoggedIn"
    # The live site posts with empty body
    r = session.post(url, data=b"", headers=_xhr_headers(referer=f"{TARGET}/home/nextlevel"))
    text = ""
    email = ""
    ok = False
    try:
        text = r.text
        j = r.json()
        ok = bool(j.get("is_logged_in"))
        email = j.get("email_address") or ""
    except Exception:
        pass
    return {
        "cookie_present": _has_cookie(),
        "is_logged_in": ok,
        "email": email,
        "status": getattr(r, "status_code", 0),
        "text": text
    }

# -----------------------------
# Routes
# -----------------------------

@app.route("/", methods=["GET", "HEAD"])
def root():
    body = """
<html><body>
<h3>RailOps JSON</h3>
<ul>
<li>Set cookie: <code>/set-aspxauth?value=PASTE_.ASPXAUTH_VALUE_ONLY</code></li>
<li>Generic cookie: <code>/set-cookie?name=ASP.NET_SessionId&value=XXXX</code></li>
<li>Auth check: <a href="/authcheck">/authcheck</a></li>
<li>Viewport test (Sydney): <a href="/debug/viewport?lat=-33.8688&lng=151.2093&zm=12">/debug/viewport</a></li>
<li>Probe: <a href="/probe">/probe</a></li>
<li>Scan: <a href="/scan">/scan</a></li>
<li>Trains (placeholder): <a href="/trains">/trains</a></li>
</ul>
</body></html>
"""
    return Response(body, mimetype="text/html")

@app.get("/set-aspxauth")
def set_aspxauth():
    raw = (request.args.get("value") or "").strip()
    if not raw:
        return jsonify({"ok": False, "error": "Missing ?value"}), 400
    # Accept either VALUE or ".ASPXAUTH=VALUE"
    if raw.startswith(".ASPXAUTH="):
        token = raw.split("=", 1)[1]
    else:
        token = raw
    _set_cookie(".ASPXAUTH", token)
    return jsonify({"ok": True, "cookie": ".ASPXAUTH", "len": len(token)})

@app.get("/set-cookie")
def set_cookie_generic():
    name = (request.args.get("name") or "").strip()
    value = (request.args.get("value") or "").strip()
    if not name or not value:
        return jsonify({"ok": False, "error": "Provide ?name=CookieName&value=CookieValue"}), 400
    _set_cookie(name, value)
    return jsonify({"ok": True, "set": {"name": name, "len": len(value)}})

@app.get("/authcheck")
def authcheck():
    info = _is_logged_in()
    return jsonify(info)

@app.get("/debug/viewport")
def debug_viewport():
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm  = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "supply numeric ?lat & ?lng & ?zm"}), 400

    nextlevel = f"{TARGET}/Home/NextLevel?{urlencode({'lat': f'{lat:.6f}','lng': f'{lng:.6f}','zm': zm})}"
    warmup = session.get(nextlevel, headers={"User-Agent": UA})
    warmup_bytes = len(warmup.content or b"")
    warmup_preview = warmup.text[:600] if warmup_bytes else ""
    # Attempts
    forms = [
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
        # bounds version
        {
            "neLat": f"{lat - 0.09:.6f}",
            "neLng": f"{lng + 0.15:.6f}",
            "swLat": f"{lat + 0.09:.6f}",
            "swLng": f"{lng - 0.15:.6f}",
            "zoomLevel": str(zm),
        },
    ]
    attempts = []
    last = {}
    for form in forms:
        r = session.post(f"{TARGET}/Home/GetViewPortData", data=form, headers=_xhr_headers(referer=nextlevel))
        looks_html = r.headers.get("Content-Type","").lower().startswith("text/html") or r.text.strip().startswith("<")
        preview = r.text[:200]
        item = {
            "url": f"{TARGET}/Home/GetViewPortData",
            "status": r.status_code,
            "bytes": len(r.content or b""),
            "looks_like_html": bool(looks_html),
            "preview": preview
        }
        try:
            j = r.json()
            item["keys"] = list(j.keys())
            item["data"] = j
            last = j
        except Exception:
            pass
        attempts.append(item)

    return jsonify({
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            "used_cookie": _has_cookie(),
            "warmup": {"status": warmup.status_code, "bytes": warmup_bytes, "preview": warmup_preview},
            "viewport": {
                "response": attempts[-1] if attempts else {},
                "attempts": attempts,
                "winner": "none"
            },
        }
    })

@app.get("/probe")
def probe():
    tests = [
        ("POST", f"{TARGET}/Home/GetViewPortData"),
        ("POST", f"{TARGET}/Home/GetTrains"),
        ("GET",  f"{TARGET}/Home/Trains"),
        ("POST", f"{TARGET}/Home/GetATCS"),
        ("POST", f"{TARGET}/Home/GetAtcs"),
        ("POST", f"{TARGET}/Home/GetAtcsObj"),
        ("POST", f"{TARGET}/Home/GetAtcsGomi"),
        ("GET",  f"{TARGET}/api/trains"),
        ("POST", f"{TARGET}/api/viewport"),
    ]
    results = []
    for method, url in tests:
        try:
            if method == "GET":
                r = session.get(url, headers=_xhr_headers(referer=f"{TARGET}/home/nextlevel"))
            else:
                r = session.post(url, data={}, headers=_xhr_headers(referer=f"{TARGET}/home/nextlevel"))
            looks_html = "text/html" in (r.headers.get("Content-Type","").lower())
            item = {
                "method": method,
                "url": url,
                "status": r.status_code,
                "bytes": len(r.content or b""),
                "looks_like_html": looks_html
            }
            if not looks_html:
                try:
                    j = r.json()
                    item["keys"] = list(j.keys())
                    item["preview"] = (r.text[:180] if r.text else "")
                except Exception:
                    item["keys"] = []
                    item["preview"] = (r.text[:180] if r.text else "")
            else:
                item["preview"] = (r.text[:180] if r.text else "")
            results.append(item)
        except Exception as e:
            results.append({"method": method, "url": url, "error": str(e)})

    return jsonify({
        "used_cookie": _has_cookie(),
        "warmup_has_token": False,
        "warmup_status": 200,
        "token_present": False,
        "results": results
    })

@app.get("/scan")
def scan():
    cities = [
        ("Sydney", -33.8688, 151.2093),
        ("Melbourne", -37.8136, 144.9631),
        ("Brisbane", -27.4698, 153.0251),
        ("Perth", -31.9523, 115.8613),
        ("Adelaide", -34.9285, 138.6007),
    ]
    out = []
    for name, lat, lng in cities:
        r = session.post(f"{TARGET}/Home/GetViewPortData",
                         data={"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": "12"},
                         headers=_xhr_headers(referer=f"{TARGET}/home/nextlevel"))
        looks_html = r.headers.get("Content-Type","").lower().startswith("text/html") or (r.text or "").startswith("<")
        out.append({
            "city": name,
            "lat": lat, "lng": lng, "zm": 12,
            "viewport_bytes": len(r.content or b""),
            "looks_like_html": bool(looks_html),
            "verification_token_present": False,
            "note": ""
        })
    return jsonify({"count": len(out), "results": out})

@app.get("/trains")
def trains():
    """Placeholder so your frontend stops 404ing.
       If/when we identify the real train stream, we’ll fill this."""
    # Try viewport (still returns only user lists)
    try:
        r = session.post(f"{TARGET}/Home/GetViewPortData",
                         data={"lat": "-33.868800", "lng": "151.209300", "zm": "12"},
                         headers=_xhr_headers(referer=f"{TARGET}/home/nextlevel"))
        data = {}
        try:
            data = r.json()
        except Exception:
            pass
        # No trains in here, keep stable shape:
        return jsonify({
            "trains": [],
            "source": "GetViewPortData",
            "raw_keys": list(data.keys()) if data else [],
            "note": "TrainFinder did not return train arrays. This is a placeholder."
        })
    except Exception as e:
        return jsonify({"trains": [], "error": str(e)}), 502

if __name__ == "__main__":
    # For local testing only. On Render, use gunicorn.
    app.run(host="0.0.0.0", port=10000, debug=False)
