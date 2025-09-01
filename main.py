# main.py
import os, json, re, time
from typing import Dict, Any, List
import requests
from flask import Flask, request, jsonify, session, make_response

# ---------- Flask app ----------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")  # set a real SECRET_KEY in Render

# make session cookie work on Render with HTTPS
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)

BASE = "https://trainfinder.otenko.com"
UA = "RailOps-JSON/1.0 (+render)"

# ---------- helpers ----------
def _cookie_str() -> str:
    val = session.get("aspxauth", "")
    return f".ASPXAUTH={val}" if val else ""

def _new_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE,
        "Referer": f"{BASE}/",
    })
    if session.get("aspxauth"):
        # set outbound cookie to talk to TrainFinder as the user
        s.cookies.set(".ASPXAUTH", session["aspxauth"], domain="trainfinder.otenko.com")
    s.timeout = 15  # type: ignore[attr-defined]
    return s

def _parse_verification_token(html: str) -> str:
    """
    Try to find ASP.NET anti-forgery token if it exists.
    Many pages won’t include it; that’s OK — we’ll call without it.
    """
    # hidden input
    m = re.search(r'name="__RequestVerificationToken"\s+value="([^"]+)"', html, re.I)
    if m:
        return m.group(1)
    # meta
    m = re.search(r'<meta\s+name="__RequestVerificationToken"\s+content="([^"]+)"', html, re.I)
    return m.group(1) if m else ""

def _warmup_and_token(lat: float, lng: float, zm: int, client: requests.Session) -> Dict[str, Any]:
    diag = {"bytes": 0, "status": 0, "token": "", "url": ""}
    url = f"{BASE}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
    resp = client.get(url)
    diag["url"] = url
    diag["status"] = resp.status_code
    diag["bytes"] = len(resp.content or b"")
    token = ""
    if resp.ok and resp.text:
        token = _parse_verification_token(resp.text)
    diag["token"] = "present" if token else "none"
    return {"diag": diag, "token": token, "html": resp.text if resp.ok else ""}

def _post_viewport(lat: float, lng: float, zm: int, client: requests.Session, token: str) -> Dict[str, Any]:
    """
    Try multiple known payload shapes for GetViewPortData.
    Stop at the first that returns JSON with expected keys.
    """
    attempts: List[Dict[str, Any]] = []
    url = f"{BASE}/Home/GetViewPortData"

    headers = {}
    if token:
        # If we ever saw a token, pass it in the classic header name
        headers["RequestVerificationToken"] = token

    def try_one(payload: Dict[str, str]) -> Dict[str, Any]:
        t0 = time.time()
        resp = client.post(url, data=payload, headers=headers)
        dt = int((time.time() - t0) * 1000)
        looks_like_html = resp.headers.get("Content-Type", "").lower().startswith("text/html")
        preview = ""
        data: Any = None
        ok_json = False
        try:
            data = resp.json()
            preview = json.dumps(data)[:200]
            # the shape we’ve been seeing
            ok_json = isinstance(data, dict) and all(k in data for k in ["favs","alerts","places","tts","webcams","atcsGomi","atcsObj"])
        except Exception:
            preview = (resp.text or "")[:200]
        return {
            "method": "POST",
            "ms": dt,
            "status": resp.status_code,
            "bytes": len(resp.content or b""),
            "looks_like_html": looks_like_html,
            "url": url,
            "payload": payload,
            "preview": preview,
            "ok_json": ok_json,
            "data": data if ok_json else None,
        }

    # Try payload variants in the order that worked most often
    variants = [
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": f"{zm}"},
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": f"{zm}"},
        {"east": f"{lng + 0.1545:.6f}", "west": f"{lng - 0.1373:.6f}",
         "north": f"{lat + 0.0856:.6f}", "south": f"{lat - 0.0855:.6f}", "zoomLevel": f"{zm}"},
        {"neLat": f"{lat + 0.0856:.6f}", "neLng": f"{lng + 0.1545:.6f}",
         "swLat": f"{lat - 0.0855:.6f}", "swLng": f"{lng - 0.1373:.6f}", "zoomLevel": f"{zm}"},
    ]

    winner = None
    for v in variants:
        res = try_one(v)
        attempts.append(res)
        if res["ok_json"]:
            winner = res
            break

    out = {
        "attempts": attempts,
        "winner": "found" if winner else "none",
        "response": winner if winner else (attempts[-1] if attempts else None),
        "data": (winner or {}).get("data") if winner else None
    }
    return out

# ---------- routes ----------
@app.get("/")
def root():
    return make_response(
        """
        <pre>RailOps JSON

Set your cookie once:
  /set-aspxauth?value=PASTE_FULL_.ASPXAUTH

Check:
  /authcheck

Test one viewport:
  /debug/viewport?lat=-33.8688&lng=151.2093&zm=12

Scan a few cities:
  /scan
</pre>
        """,
        200,
    )

@app.get("/set-aspxauth")
def set_aspxauth():
    value = request.args.get("value", "").strip()
    if not value:
        return jsonify({"ok": False, "error": "provide ?value=PASTE_FULL_.ASPXAUTH"}), 400
    # Accept either raw token or full ".ASPXAUTH=..." string
    if value.startswith(".ASPXAUTH="):
        value = value.split("=", 1)[1]
    session["aspxauth"] = value
    return jsonify({"ok": True, "stored": bool(session.get("aspxauth")), "len": len(session["aspxauth"])})

@app.get("/authcheck")
def authcheck():
    client = _new_client()
    used_cookie = bool(session.get("aspxauth"))
    info = {
        "cookie_present": used_cookie,
        "sent_cookie": _cookie_str() if used_cookie else "",
    }
    try:
        # TrainFinder uses POST with empty body for IsLoggedIn
        url = f"{BASE}/Home/IsLoggedIn"
        r = client.post(url, data={})
        info["status"] = r.status_code
        info["bytes"] = len(r.content or b"")
        text = r.text or ""
        email = ""
        is_logged = False

        # common shapes:
        #  - JSON: {"isLoggedIn":true,"email":"..."} (example you showed)
        #  - plain: "True" or "False"
        try:
            j = r.json()
            # normalize keys
            email = j.get("email") or j.get("email_address") or j.get("EmailAddress") or ""
            is_logged = j.get("is_logged_in") or j.get("isLoggedIn") or False
            info["text"] = json.dumps(j)
        except Exception:
            info["text"] = text[:200]
            t = text.strip().lower()
            if t in ("true", "false"):
                is_logged = (t == "true")

        return jsonify({
            "status": info.get("status", 0),
            "bytes": info.get("bytes", 0),
            "cookie_present": used_cookie,
            "is_logged_in": bool(is_logged),
            "email": email,
            "text": info.get("text", ""),
        })
    except Exception as e:
        return jsonify({"cookie_present": used_cookie, "error": str(e)}), 500

@app.get("/debug/viewport")
def debug_viewport():
    try:
        lat = float(request.args.get("lat", "-33.8688"))
        lng = float(request.args.get("lng", "151.2093"))
        zm = int(request.args.get("zm", "12"))
    except Exception:
        return jsonify({"error": "provide lat,lng,zm"}), 400

    client = _new_client()
    used_cookie = bool(session.get("aspxauth"))

    warm = _warmup_and_token(lat, lng, zm, client)
    token = warm["token"]
    vp = _post_viewport(lat, lng, zm, client, token)

    resp = {
        "input": {"lat": lat, "lng": lng, "zm": zm},
        "tf": {
            "used_cookie": used_cookie,
            "verification_token_present": bool(token),
            "warmup": {**warm["diag"]},
            "viewport": {
                "winner": vp["winner"],
                "response": {
                    "status": (vp["response"] or {}).get("status", 0),
                    "bytes": (vp["response"] or {}).get("bytes", 0),
                    "looks_like_html": (vp["response"] or {}).get("looks_like_html", False),
                    "preview": (vp["response"] or {}).get("preview", "")[:200],
                }
            }
        }
    }
    # include data if we got real JSON
    if vp.get("data") is not None:
        resp["data"] = vp["data"]

    return jsonify(resp)

@app.get("/scan")
def scan():
    client = _new_client()
    used_cookie = bool(session.get("aspxauth"))
    cities = [
        ("Sydney", -33.8688, 151.2093),
        ("Melbourne", -37.8136, 144.9631),
        ("Brisbane", -27.4698, 153.0251),
        ("Perth", -31.9523, 115.8613),
        ("Adelaide", -34.9285, 138.6007),
    ]
    zooms = [11, 12, 13]
    results = []
    for city, lat, lng in cities:
        for zm in zooms:
            warm = _warmup_and_token(lat, lng, zm, client)
            token = warm["token"]
            vp = _post_viewport(lat, lng, zm, client, token)
            resp = (vp["response"] or {})
            results.append({
                "city": city,
                "lat": lat,
                "lng": lng,
                "zm": zm,
                "looks_like_html": resp.get("looks_like_html", False),
                "viewport_bytes": resp.get("bytes", 0),
                "warmup_bytes": warm["diag"]["bytes"],
                "winner": vp["winner"],
            })
    return jsonify({"count": len(results), "results": results})

@app.get("/trains")
def trains_placeholder():
    # Placeholder: TF doesn't expose public /Trains or /GetTrains for us.
    return jsonify({"error": "not implemented on TrainFinder; use /debug/viewport or /scan"}), 404

# For local dev (Render will use gunicorn)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
