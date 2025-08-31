import json
import re
from typing import Any, Dict, Optional

import requests
from flask import Flask, jsonify, make_response, request

app = Flask(__name__)

TF_BASE = "https://trainfinder.otenko.com"

# Store the latest .ASPXAUTH here (process memory).
# You set it once via /set-aspxauth?value=...
ASPXAUTH_VALUE: Optional[str] = None


# ------------------------ Helpers ------------------------

def _extract_verification_token(html: str) -> Optional[str]:
    """
    Pulls __RequestVerificationToken from the warmup HTML.
    """
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else None


def _looks_like_html(s: str) -> bool:
    t = s.lstrip()
    return t.startswith("<!DOCTYPE") or t.startswith("<html") or t.startswith("<")


def _session_with_cookie() -> requests.Session:
    """
    Builds a session carrying the user's .ASPXAUTH cookie.
    """
    if not ASPXAUTH_VALUE:
        raise RuntimeError("No .ASPXAUTH cookie set. Call /set-aspxauth first.")
    s = requests.Session()
    # Important: set cookie for the correct domain; secure=True for HTTPS.
    s.cookies.set(".ASPXAUTH", ASPXAUTH_VALUE, domain="trainfinder.otenko.com", secure=True)
    return s


def fetch_viewport(lat: float, lng: float, zm: int) -> Dict[str, Any]:
    """
    Warm up /home/nextlevel to get __RequestVerificationToken, then POST to
    /home/GetViewPortData with the token in BOTH form and header.
    Returns a diagnostics dict with the raw body preview.
    """
    s = _session_with_cookie()

    # 1) Warmup
    warmup_url = f"{TF_BASE}/home/nextlevel"
    warmup = s.get(warmup_url, params={"lat": lat, "lng": lng, "zm": zm}, timeout=15)
    token = _extract_verification_token(warmup.text)

    diag: Dict[str, Any] = {
        "used_cookie": True,
        "verification_token_present": bool(token),
        "warmup": {
            "status": warmup.status_code,
            "bytes": len(warmup.text),
        },
        "viewport": {},
    }

    if not token:
        # Without the token, TF replies with the 98-byte nulls.
        diag["viewport"] = {
            "status": 0,
            "bytes": 0,
            "looks_like_html": False,
            "preview": "",
            "note": "no_verification_token_in_warmup_html",
        }
        return diag

    # 2) POST to GetViewPortData
    # Either shape works; keep it simple with lat/lng/zoomLevel.
    form = {
        "lat": f"{lat:.6f}",
        "lng": f"{lng:.6f}",
        "zoomLevel": str(zm),
        "__RequestVerificationToken": token,  # token in FORM
    }
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{TF_BASE}/home/nextlevel?lat={lat}&lng={lng}&zm={zm}",
        "RequestVerificationToken": token,     # token in HEADER
    }
    vp = s.post(f"{TF_BASE}/home/GetViewPortData", data=form, headers=headers, timeout=20)

    body = vp.text
    diag["viewport"] = {
        "status": vp.status_code,
        "bytes": len(body),
        "looks_like_html": _looks_like_html(body),
        "preview": body[:2000],
    }
    return diag


def try_json_parse(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return {"raw": s}


# ------------------------ Routes ------------------------

@app.get("/")
def root():
    return (
        "RailOps JSON\n\n"
        "Set your cookie: /set-aspxauth?value=PASTE_FULL_.ASPXAUTH\n"
        "Check:          /authcheck\n"
        "Debug viewport: /debug/viewport?lat=-33.8688&lng=151.2093&zm=12\n"
        "API (trains):   /trains?lat=-33.8688&lng=151.2093&zm=12\n"
    ), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.get("/set-aspxauth")
def set_aspxauth():
    global ASPXAUTH_VALUE
    val = request.args.get("value", "").strip()
    ASPXAUTH_VALUE = val or None

    resp = {
        "ok": bool(ASPXAUTH_VALUE),
        "cookie_len": len(ASPXAUTH_VALUE or ""),
        "hint": "Now call /authcheck",
    }
    # also set a browser cookie for your convenience (not required for server->TF)
    r = make_response(jsonify(resp))
    if ASPXAUTH_VALUE:
        r.set_cookie(".ASPXAUTH", ASPXAUTH_VALUE, secure=True, samesite="Lax")
    return r


@app.get("/authcheck")
def authcheck():
    if not ASPXAUTH_VALUE:
        return jsonify(
            {
                "is_logged_in": False,
                "email_address": "",
                "cookie_present": False,
                "bytes": 0,
                "status": 200,
                "text": json.dumps({"is_logged_in": False, "email_address": ""}),
            }
        )

    s = _session_with_cookie()
    # TF checks login via POST to Home/IsLoggedIn with XHR header
    resp = s.post(f"{TF_BASE}/Home/IsLoggedIn", headers={"X-Requested-With": "XMLHttpRequest"}, timeout=10)
    return jsonify(
        {
            "is_logged_in": True if '"is_logged_in":true' in resp.text else False,
            "email_address": re.search(r'"email_address"\s*:\s*"([^"]*)"', resp.text or "") and re.search(r'"email_address"\s*:\s*"([^"]*)"', resp.text).group(1) or "",
            "cookie_present": True,
            "bytes": len(resp.text),
            "status": resp.status_code,
            "text": resp.text,
        }
    )


@app.get("/debug/viewport")
def debug_viewport():
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm = int(request.args.get("zm", "12"))

    try:
        diag = fetch_viewport(lat, lng, zm)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Also include the computed bounds TF expects (for reference only)
    # (Not strictly needed when using lat/lng/zoomLevel)
    return jsonify(
        {
            "input": {"lat": lat, "lng": lng, "zm": zm},
            "tf": diag,
        }
    )


@app.get("/trains")
def trains():
    """
    Simple API your frontend can hit.
    Returns the parsed JSON TF gives from GetViewPortData.
    """
    lat = float(request.args.get("lat", "-33.8688"))
    lng = float(request.args.get("lng", "151.2093"))
    zm = int(request.args.get("zm", "12"))

    try:
        diag = fetch_viewport(lat, lng, zm)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    vp = diag.get("viewport", {})
    if not diag.get("verification_token_present"):
        return jsonify({"error": "no_verification_token", "diag": diag}), 502

    if vp.get("status") != 200:
        return jsonify({"error": "upstream_error", "diag": diag}), 502

    body = vp.get("preview", "")
    data = try_json_parse(body)
    return jsonify(data)


# ------------------------ Run local (optional) ------------------------

if __name__ == "__main__":
    # Local dev only; Render uses gunicorn.
    app.run(host="0.0.0.0", port=10000, debug=True)
