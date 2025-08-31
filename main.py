from __future__ import annotations
import os
import re
import json
from typing import Optional, Tuple

import requests
from flask import Flask, jsonify, request, make_response

# ------------------------------
# Flask app (module-level "app")
# ------------------------------
app = Flask(__name__)

# Store the TrainFinder auth cookie in memory (ephemeral)
ASPXAUTH_VALUE: Optional[str] = None
TF_BASE = "https://trainfinder.otenko.com"

# ------------------------------
# Helpers
# ------------------------------

def _looks_like_html(s: str) -> bool:
    t = (s or "").lstrip()
    return t.startswith("<!DOCTYPE") or t.startswith("<html") or t.startswith("<")


def _session_with_cookie() -> requests.Session:
    if not ASPXAUTH_VALUE:
        raise RuntimeError("No .ASPXAUTH cookie set. Call /set-aspxauth?value=... first.")
    s = requests.Session()
    # Pretend to be a normal browser
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    # Set the auth cookie for the TF domain (secure cookie is fine over HTTPS)
    s.cookies.set(".ASPXAUTH", ASPXAUTH_VALUE, domain="trainfinder.otenko.com", secure=True)
    return s


def _extract_verification_token(html: str) -> Optional[str]:
    """Try several ways TF might expose an antiforgery token."""
    patterns = [
        r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
        r'name="RequestVerificationToken"[^>]*value="([^"]+)"',
        r'<meta[^>]+name="__RequestVerificationToken"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="RequestVerificationToken"[^>]+content="([^"]+)"',
        r'window\.__RequestVerificationToken\s*=\s*"([^"]+)"',
        r'var\s+__RequestVerificationToken\s*=\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.I | re.S)
        if m:
            return m.group(1)
    return None


def _extract_token_from_cookies(cookiejar) -> Tuple[Optional[str], list[str]]:
    names = []
    token = None
    for c in cookiejar:
        if ("Antiforgery" in c.name) or c.name.startswith("__RequestVerificationToken"):
            names.append(c.name)
            token = token or c.value
    return token, names


# ------------------------------
# Core TF fetch
# ------------------------------

def fetch_viewport_diag(lat: float, lng: float, zm: int) -> dict:
    """Warm up the page, try to harvest a verification token, then post for data.
    Returns a diagnostic dict so you can see exactly what's happening.
    """
    s = _session_with_cookie()

    # 1) Warmup
    warmup_url = f"{TF_BASE}/Home/NextLevel"
    warmup = s.get(warmup_url, params={"lat": lat, "lng": lng, "zm": zm}, timeout=20)
    warmup_html = warmup.text or ""

    token_html = _extract_verification_token(warmup_html)
    token_cookie, anti_cookie_names = _extract_token_from_cookies(s.cookies)
    token = token_html or token_cookie

    diag: dict = {
        "used_cookie": True,
        "verification_token_present": bool(token),
        "token_source": "html" if token_html else ("cookie" if token_cookie else ""),
        "anti_cookie_names": anti_cookie_names,
        "warmup": {
            "status": warmup.status_code,
            "bytes": len(warmup_html),
            # Trim so responses stay small but still debuggable
            "preview": warmup_html[:600],
        },
    }

    if not token:
        diag["viewport"] = {
            "status": 0,
            "bytes": 0,
            "looks_like_html": False,
            "preview": "",
            "note": "no_verification_token"
        }
        return diag

    # 2) POST for the JSON payload. Include token in both header and form (common ASP.NET pattern).
    form = {
        "lat": f"{lat:.6f}",
        "lng": f"{lng:.6f}",
        "zoomLevel": str(zm),
        "__RequestVerificationToken": token,
    }
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{TF_BASE}/Home/NextLevel?lat={lat}&lng={lng}&zm={zm}",
        "RequestVerificationToken": token,
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    vp = s.post(f"{TF_BASE}/home/GetViewPortData", data=form, headers=headers, timeout=30)
    body = vp.text or ""
    diag["viewport"] = {
        "status": vp.status_code,
        "bytes": len(body),
        "looks_like_html": _looks_like_html(body),
        "preview": body[:2000],
    }
    return diag


def fetch_viewport_json(lat: float, lng: float, zm: int) -> dict:
    """Convenience call that returns parsed JSON (or raises RuntimeError with details)."""
    s = _session_with_cookie()

    warmup = s.get(f"{TF_BASE}/Home/NextLevel", params={"lat": lat, "lng": lng, "zm": zm}, timeout=20)
    token = _extract_verification_token(warmup.text or "")
    if not token:
        token, _ = _extract_token_from_cookies(s.cookies)
    if not token:
        raise RuntimeError("verification token not found")

    form = {
        "lat": f"{lat:.6f}",
        "lng": f"{lng:.6f}",
        "zoomLevel": str(zm),
        "__RequestVerificationToken": token,
    }
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{TF_BASE}/Home/NextLevel?lat={lat}&lng={lng}&zm={zm}",
        "RequestVerificationToken": token,
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    r = s.post(f"{TF_BASE}/home/GetViewPortData", data=form, headers=headers, timeout=30)
    txt = r.text or ""
    if r.status_code != 200:
        raise RuntimeError(f"viewport http {r.status_code}: {txt[:400]}")
    if _looks_like_html(txt) or len(txt) < 120:
        # 98-byte nulls or an HTML error page
        raise RuntimeError(f"viewport looks wrong (bytes={len(txt)})")
    try:
        return json.loads(txt)
    except Exception as e:
        raise RuntimeError(f"viewport not JSON: {e}: {txt[:200]}")


# ------------------------------
# Routes
# ------------------------------

@app.get("/")
def index():
    return make_response(
        """
        <h1>RailOps JSON</h1>
        <p>Quick endpoints (paste into address bar):</p>
        <ul>
          <li>Set your cookie once: <code>/set-aspxauth?value=PASTE_.ASPXAUTH</code></li>
          <li>Check: <code>/authcheck</code></li>
          <li>Debug: <code>/debug/viewport?lat=-33.8688&lng=151.2093&zm=12</code></li>
          <li>Scan: <code>/scan</code></li>
          <li>Data: <code>/trains?lat=-33.8688&lng=151.2093&zm=12</code></li>
        </ul>
        """,
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


@app.get("/set-aspxauth")
def set_aspxauth():
    global ASPXAUTH_VALUE
    val = request.args.get("value", "").strip()
    if not val:
        return jsonify({"ok": False, "error": "missing ?value=..."}), 400
    # Accept raw string; user might paste with leading '.ASPXAUTH=' — strip it.
    if val.startswith(".ASPXAUTH="):
        val = val.split("=", 1)[1]
    ASPXAUTH_VALUE = val
    # Also drop a convenience cookie in the browser (NOT used for TF; just to avoid re-pasting).
    resp = jsonify({"ok": True, "stored": bool(ASPXAUTH_VALUE), "length": len(ASPXAUTH_VALUE)})
    resp.set_cookie("railops_aspxauth_set", "1", max_age=864000)
    return resp


@app.get("/authcheck")
def authcheck():
    """POST to TF /Home/IsLoggedIn to verify the cookie is valid."""
    if not ASPXAUTH_VALUE:
        return jsonify({"is_logged_in": False, "email_address": "", "note": "no .ASPXAUTH set"}), 200
    s = _session_with_cookie()
    try:
        r = s.post(f"{TF_BASE}/Home/IsLoggedIn", headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
    except Exception as e:
        return jsonify({"is_logged_in": False, "email_address": "", "error": str(e)}), 200
    text = r.text or ""
    email = ""
    try:
        data = json.loads(text)
        email = data.get("email_address") or data.get("Email") or data.get("email") or ""
        is_logged_in = bool(data.get("is_logged_in") or data.get("IsLoggedIn"))
    except Exception:
        is_logged_in = False
    return jsonify({
        "is_logged_in": is_logged_in,
        "email_address": email,
        "status": r.status_code,
        "text": text,
    })


@app.get("/debug/viewport")
def debug_viewport():
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm = int(request.args.get("zm", "12"))
    try:
        diag = fetch_viewport_diag(lat, lng, zm)
        return jsonify({"input": {"lat": lat, "lng": lng, "zm": zm}, "tf": diag})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    for (name, lat, lng) in cities:
        for zm in (11, 12, 13):
            try:
                diag = fetch_viewport_diag(lat, lng, zm)
                vp = diag.get("viewport", {})
                out.append({
                    "city": name,
                    "lat": lat,
                    "lng": lng,
                    "zm": zm,
                    "verification_token_present": diag.get("verification_token_present", False),
                    "token_source": diag.get("token_source", ""),
                    "warmup_bytes": diag.get("warmup", {}).get("bytes", 0),
                    "viewport_bytes": vp.get("bytes", 0),
                    "looks_like_html": vp.get("looks_like_html", False),
                })
            except Exception as e:
                out.append({"city": name, "lat": lat, "lng": lng, "zm": zm, "error": str(e)})
    return jsonify({"count": len(out), "results": out})


@app.get("/trains")
def trains():
    """Return the real TF JSON body so your frontend can use it directly.
    Example: /trains?lat=-33.8688&lng=151.2093&zm=12
    """
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm = int(request.args.get("zm", "12"))
    try:
        data = fetch_viewport_json(lat, lng, zm)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ------------------------------
# Local dev entrypoint (ignored by Gunicorn)
# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
