import os
import re
import time
import json
from urllib.parse import urlencode

import requests
from flask import Flask, request, jsonify, Response

# ----------------------------
# Config
# ----------------------------
TRAINFINDER_BASE = "https://trainfinder.otenko.com"
WARMUP_PATHS = [
    "/",                                    # 1) root
    "/home/nextlevel",                      # 2) map page (commonly used)
]

# The JSON endpoints we’ll try in order (ASP.NET MVC often uses this)
POST_ENDPOINTS = [
    "/Home/GetViewPortData",
    "/home/GetViewPortData",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36"
)

# Global in-memory store for your TrainFinder auth cookie (.ASPXAUTH)
ASPXAUTH_VALUE = os.environ.get("ASPXAUTH", "").strip()

app = Flask(__name__)


# ----------------------------
# Helpers
# ----------------------------
def _session_with_auth():
    """
    Create a requests.Session with the .ASPXAUTH cookie set (if we have it).
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    })
    if ASPXAUTH_VALUE:
        # Set as a cookie for the trainfinder domain.
        s.cookies.set(".ASPXAUTH", ASPXAUTH_VALUE, domain="trainfinder.otenko.com", path="/")
    return s


def _extract_verification_token_from_html(html: str) -> str:
    """
    Try multiple patterns to find the anti-forgery verification token that ASP.NET emits.
    Common cases:
      <input name="__RequestVerificationToken" type="hidden" value="...">
      <meta name="__RequestVerificationToken" content="...">
      window.__RequestVerificationToken = '...';
    """
    if not html:
        return ""

    # input hidden
    m = re.search(
        r'<input[^>]*name=["\']__RequestVerificationToken["\'][^>]*value=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if m:
        return m.group(1)

    # meta tag
    m = re.search(
        r'<meta[^>]*name=["\']__RequestVerificationToken["\'][^>]*content=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if m:
        return m.group(1)

    # JS assignment
    m = re.search(
        r'__RequestVerificationToken\s*=\s*[\'"]([^\'"]+)[\'"]',
        html, re.IGNORECASE)
    if m:
        return m.group(1)

    return ""


def _token_header_candidates(session: requests.Session, form_token: str):
    """
    Build a set of header candidates for ASP.NET anti-forgery:
      - RequestVerificationToken: "<cookie-token>:<form-token>"
      - RequestVerificationToken: "<form-token>"
      - __RequestVerificationToken: "<form-token>"
    Sometimes the cookie named __RequestVerificationToken also exists—if so,
    we’ll try cookie:form format first.
    """
    cookie_token = session.cookies.get("__RequestVerificationToken", domain="trainfinder.otenko.com")
    headers_list = []

    if cookie_token and form_token:
        headers_list.append({"RequestVerificationToken": f"{cookie_token}:{form_token}"})

    if form_token:
        headers_list.append({"RequestVerificationToken": form_token})
        headers_list.append({"__RequestVerificationToken": form_token})

    # As a last resort, try with no explicit header (rarely works, but cheap)
    headers_list.append({})

    return headers_list


def _warmup_and_get_token(session: requests.Session, lat=None, lng=None, zm=None):
    """
    Visit a warmup page to obtain HTML + cookies. Then extract the verification token.
    """
    warmup_diags = []
    html_snippet = ""
    token = ""

    for path in WARMUP_PATHS:
        url = TRAINFINDER_BASE + path
        if path.lower().endswith("nextlevel") and lat is not None:
            # Keep query params in case the page renders a map around the lat/lng
            q = {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm or 12)}
            url += "?" + urlencode(q)

        try:
            r = session.get(url, timeout=15)
            warmup_diags.append({"url": url, "status": r.status_code, "bytes": len(r.content)})
            if r.ok:
                html = r.text
                if not html_snippet:
                    html_snippet = html[:256]
                token = _extract_verification_token_from_html(html)
                if token:
                    return token, {"warmup": warmup_diags, "token_source": url, "html_preview": html_snippet}
        except Exception as ex:
            warmup_diags.append({"url": url, "error": str(ex)})

    return "", {"warmup": warmup_diags, "token_source": "", "html_preview": html_snippet}


def _post_viewport(session: requests.Session, form: dict, token_headers: dict, referer_url: str):
    """
    Try all known POST endpoints with the provided form + token headers.
    Return first successful JSON-ish response (status 200 and non-empty body).
    """
    headers = {
        "User-Agent": USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TRAINFINDER_BASE,
        "Referer": referer_url,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    headers.update(token_headers)

    attempts = []
    for ep in POST_ENDPOINTS:
        url = TRAINFINDER_BASE + ep
        t0 = time.time()
        try:
            resp = session.post(url, data=form, headers=headers, timeout=20)
            elapsed = int((time.time() - t0) * 1000)
            # bytes + preview for diagnostics
            preview = resp.text[:200]
            looks_like_html = "<!DOCTYPE html" in preview or "<html" in preview.lower()

            attempts.append({
                "url": url,
                "status": resp.status_code,
                "ms": elapsed,
                "bytes": len(resp.content),
                "looks_like_html": looks_like_html,
                "preview": preview,
            })

            if resp.ok and resp.text.strip():
                # Return both raw text and attempt data for caller to inspect
                return resp, attempts
        except Exception as ex:
            attempts.append({"url": url, "error": str(ex)})

    return None, attempts


def fetch_viewport(lat: float, lng: float, zm: int):
    """
    Main worker:
      1) Build a session with .ASPXAUTH if we have it
      2) Warmup a page to get anti-forgery token (if required)
      3) Try several form shapes and token header permutations
      4) Return diag + the 'best' response we got
    """
    session = _session_with_auth()

    # 1) Warmup and token
    token, warm_diag = _warmup_and_get_token(session, lat=lat, lng=lng, zm=zm)
    referer_url = warm_diag.get("token_source") or (TRAINFINDER_BASE + "/home/nextlevel")

    # 2) Form variants commonly seen in your logs
    forms = [
        # A) simple lat/lng/zm
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
        # B) same but using 'zoomLevel'
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
    ]

    # 3) Token header candidates
    token_headers_list = _token_header_candidates(session, token)

    diag_attempts = []
    for form in forms:
        for th in token_headers_list:
            resp, attempts = _post_viewport(session, form, th, referer_url)
            diag_attempts.append({"form": form, "token_headers": th, "attempts": attempts})
            if resp and resp.ok and resp.text.strip():
                # success — try to parse JSON, otherwise return raw text
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text}
                return {
                    "used_cookie": bool(ASPXAUTH_VALUE),
                    "verification_token_present": bool(token),
                    "token_source": warm_diag.get("token_source", ""),
                    "viewport": {
                        "status": resp.status_code,
                        "bytes": len(resp.content),
                        "looks_like_html": False,
                        "preview": resp.text[:200],
                        "data": data,
                    },
                    "warmup": {
                        "status": 200,
                        "bytes": warm_diag["warmup"][0]["bytes"] if warm_diag.get("warmup") else 0,
                    },
                    "diag": {
                        "attempts": diag_attempts,
                        "html_preview": warm_diag.get("html_preview", "")[:200],
                    }
                }

    # If we get here, nothing succeeded
    return {
        "used_cookie": bool(ASPXAUTH_VALUE),
        "verification_token_present": bool(token),
        "token_source": warm_diag.get("token_source", ""),
        "viewport": {
            "status": 0,
            "bytes": 0,
            "looks_like_html": False,
            "preview": "",
            "data": None,
            "note": "no_successful_post"
        },
        "warmup": {
            "status": 200 if warm_diag.get("warmup") else 0,
            "bytes": warm_diag["warmup"][0]["bytes"] if warm_diag.get("warmup") else 0,
        },
        "diag": {
            "attempts": diag_attempts,
            "html_preview": warm_diag.get("html_preview", "")[:200],
            "error": "verification token not found" if not token else "post failed"
        }
    }


# ----------------------------
# Routes
# ----------------------------
@app.get("/")
def home():
    html = f"""
<!doctype html>
<html><head><meta charset="utf-8"><title>RailOps JSON</title></head>
<body style="font-family:system-ui,Segoe UI,Arial">
<h1>RailOps JSON</h1>
<ol>
  <li>Set your cookie once:<br>
    <code>/set-aspxauth?value=PASTE_.ASPXAUTH</code>
  </li>
  <li>Check login:<br>
    <code>/authcheck</code>
  </li>
  <li>Test viewport:<br>
    <code>/debug/viewport?lat=-33.8688&lng=151.2093&zm=12</code>
  </li>
  <li>Simple pass-through for your frontend:<br>
    <code>/trains?lat=-33.8688&lng=151.2093&zm=12</code>
  </li>
  <li>Scan cities:<br>
    <code>/scan</code>
  </li>
</ol>
<p style="color:#666">.ASPXAUTH set: <b>{'yes' if ASPXAUTH_VALUE else 'no'}</b></p>
</body></html>
"""
    return Response(html, mimetype="text/html")


@app.get("/set-aspxauth")
def set_aspxauth():
    global ASPXAUTH_VALUE
    value = request.args.get("value", "").strip()
    if not value:
        return jsonify({"ok": False, "message": "Provide ?value=<FULL_.ASPXAUTH>"}), 400
    ASPXAUTH_VALUE = value
    # Keep it in env too so restarts on Render hot-reload might keep it (best effort).
    os.environ["ASPXAUTH"] = value
    return jsonify({"ok": True, "note": ".ASPXAUTH stored in memory"})


@app.get("/authcheck")
def authcheck():
    """
    Mirrors your successful curl:
    POST Home/IsLoggedIn with AJAX headers. Returns JSON showing login state.
    """
    s = _session_with_auth()
    url = f"{TRAINFINDER_BASE}/Home/IsLoggedIn"
    try:
        r = s.post(url, headers={
            "X-Requested-With": "XMLHttpRequest",
            "Origin": TRAINFINDER_BASE,
            "Referer": f"{TRAINFINDER_BASE}/home/nextlevel"
        }, timeout=15)
        text = r.text.strip()
        # Attempt to parse JSON, fall back to raw
        try:
            data = r.json()
        except Exception:
            data = {"raw": text}

        email = data.get("email_address") or ""
        is_logged_in = bool(data.get("is_logged_in"))
        return jsonify({
            "status": r.status_code,
            "bytes": len(r.content),
            "cookie_present": bool(ASPXAUTH_VALUE),
            "email": email,
            "is_logged_in": is_logged_in,
            "text": text
        })
    except Exception as ex:
        return jsonify({
            "status": 0,
            "cookie_present": bool(ASPXAUTH_VALUE),
            "error": str(ex)
        }), 500


@app.get("/debug/viewport")
def debug_viewport():
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
        zm = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "Provide lat,lng,zm"}), 400

    res = fetch_viewport(lat, lng, zm)
    return jsonify(res)


@app.get("/trains")
def trains():
    """
    Small wrapper your frontend can call: returns only the TrainFinder JSON (data) if available,
    otherwise returns a short diagnostic with HTTP 502.
    """
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm = int(request.args.get("zm", "12"))

    out = fetch_viewport(lat, lng, zm)
    data = out.get("viewport", {}).get("data")

    if data is not None:
        return jsonify(data)

    # Fallback: signal upstream error with minimal info
    return jsonify({
        "error": "upstream_failed",
        "diag": {
            "used_cookie": out.get("used_cookie"),
            "verification_token_present": out.get("verification_token_present"),
            "note": out.get("viewport", {}).get("note", ""),
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

    results = []
    for (name, lat, lng) in cities:
        for zm in zooms:
            r = fetch_viewport(lat, lng, zm)
            vp = r.get("viewport", {})
            results.append({
                "city": name,
                "lat": lat,
                "lng": lng,
                "zm": zm,
                "verification_token_present": r.get("verification_token_present", False),
                "viewport_bytes": vp.get("bytes", 0),
                "looks_like_html": vp.get("looks_like_html", False),
                "note": vp.get("note", ""),
            })

    return jsonify({"count": len(results), "results": results})


# Allow local dev: `python main.py`
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=True)
