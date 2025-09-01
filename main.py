import os
import json
import time
from typing import Dict, Any, Tuple, Optional

import requests
from flask import Flask, request, jsonify, make_response

TF_ORIGIN = "https://trainfinder.otenko.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36"
)

def create_app() -> Flask:
    app = Flask(__name__)
    # Store the upstream auth cookie in memory (and optionally ENV)
    app.config["ASPXAUTH"] = os.getenv("RAILOPS_ASPXAUTH", "").strip()

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _make_session() -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Origin": TF_ORIGIN,
            "Referer": f"{TF_ORIGIN}/home/nextlevel",
        })
        token = app.config.get("ASPXAUTH", "")
        if token:
            # attach auth cookie for the upstream domain
            s.cookies.set(".ASPXAUTH", token, domain="trainfinder.otenko.com", path="/")
        return s

    def _cors(resp):
        # Open CORS so your Netlify app can call this
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        return resp

    def _json(data: Dict[str, Any], status: int = 200):
        return _cors(make_response(jsonify(data), status))

    # Warmup hit (loads the page; sometimes apps set server-side context)
    def _warmup(s: requests.Session, lat: float, lng: float, zm: int) -> Tuple[int, bytes]:
        url = f"{TF_ORIGIN}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
        r = s.get(url, timeout=15)
        return r.status_code, r.content

    # Attempt different POST forms that we’ve seen in the wild
    def _try_viewport_forms(s: requests.Session, lat: float, lng: float, zm: int) -> Dict[str, Any]:
        trials = []

        forms = [
            ({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)}, "lat/lng/zm"),
            ({"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)}, "lat/lng/zoomLevel"),
        ]

        for form, label in forms:
            r = s.post(f"{TF_ORIGIN}/Home/GetViewPortData", data=form, timeout=15,
                       headers={"X-Requested-With": "XMLHttpRequest"})
            looks_like_html = r.text.lstrip().startswith("<!DOCTYPE html>") or r.text.lstrip().startswith("<html")
            payload = None
            try:
                payload = r.json()
            except Exception:
                pass

            trials.append({
                "label": label,
                "status": r.status_code,
                "bytes": len(r.content),
                "looks_like_html": looks_like_html,
                "keys": list(payload.keys()) if isinstance(payload, dict) else [],
                "preview": (r.text[:120] + "…") if looks_like_html else (r.text[:120] if r.text else ""),
            })

            # If we got JSON back, that’s the “winner”
            if isinstance(payload, dict):
                return {
                    "winner": label,
                    "response": {
                        "status": r.status_code,
                        "bytes": len(r.content),
                        "looks_like_html": looks_like_html,
                        "data": payload,
                    },
                    "attempts": trials,
                }

        # If none returned JSON, show attempts
        return {"winner": "none", "attempts": trials}

    # ---------------------------------------------------------------------
    # Routes
    # ---------------------------------------------------------------------

    @app.route("/", methods=["GET"])
    def index():
        return _json({
            "name": "RailOps JSON",
            "endpoints": {
                "set_cookie": "/set-aspxauth?value=PASTE_.ASPXAUTH",
                "clear_cookie": "/clear-aspxauth",
                "check": "/authcheck",
                "viewport_debug": "/debug/viewport?lat=-33.8688&lng=151.2093&zm=12",
                "scan": "/scan",
                "trains": "/trains?lat=-33.8688&lng=151.2093&zm=12"
            },
            "cookie_set": bool(app.config.get("ASPXAUTH")),
        })

    @app.route("/set-aspxauth", methods=["GET"])
    def set_aspxauth():
        value = request.args.get("value", "").strip()
        app.config["ASPXAUTH"] = value
        return _json({
            "ok": True,
            "cookie_present": bool(value),
            "mask": (value[:6] + "…" + value[-6:]) if value else "",
            "hint": "Now open /authcheck"
        })

    @app.route("/clear-aspxauth", methods=["GET"])
    def clear_aspxauth():
        app.config["ASPXAUTH"] = ""
        return _json({"ok": True, "cookie_present": False})

    @app.route("/authcheck", methods=["GET"])
    def authcheck():
        s = _make_session()
        # Some instances expect POST with empty body
        try:
            r = s.post(f"{TF_ORIGIN}/Home/IsLoggedIn", timeout=15)
            data = {}
            try:
                data = r.json()
            except Exception:
                pass
            resp = {
                "status": r.status_code,
                "cookie_present": bool(app.config.get("ASPXAUTH")),
                "text": r.text if not data else json.dumps(data),
            }
            # Normalize shape if JSON present
            if isinstance(data, dict):
                resp.update({
                    "is_logged_in": bool(data.get("is_logged_in") or data.get("IsLoggedIn")),
                    "email": data.get("email_address") or data.get("EmailAddress") or "",
                    "bytes": len(r.content)
                })
            return _json(resp)
        except Exception as ex:
            return _json({"error": str(ex), "cookie_present": bool(app.config.get("ASPXAUTH"))}, 502)

    @app.route("/debug/viewport", methods=["GET"])
    def debug_viewport():
        try:
            lat = float(request.args.get("lat", "-33.8688"))
            lng = float(request.args.get("lng", "151.2093"))
            zm = int(request.args.get("zm", "12"))
        except Exception:
            return _json({"error": "invalid lat/lng/zm"}, 400)

        s = _make_session()

        w_status, w_body = _warmup(s, lat, lng, zm)
        tried = _try_viewport_forms(s, lat, lng, zm)

        out = {
            "input": {"lat": lat, "lng": lng, "zm": zm},
            "tf": {
                "used_cookie": bool(app.config.get("ASPXAUTH")),
                "warmup": {"status": w_status, "bytes": len(w_body)},
            }
        }

        if tried.get("winner") != "none":
            out["tf"]["viewport"] = tried["response"]
        else:
            # Fallback: show what we attempted
            out["tf"]["viewport"] = {"winner": "none", "attempts": tried.get("attempts", [])}

        return _json(out)

    @app.route("/scan", methods=["GET"])
    def scan():
        cities = [
            ("Sydney", -33.8688, 151.2093),
            ("Melbourne", -37.8136, 144.9631),
            ("Brisbane", -27.4698, 153.0251),
            ("Perth", -31.9523, 115.8613),
            ("Adelaide", -34.9285, 138.6007),
        ]
        zooms = [11, 12, 13]
        s = _make_session()

        results = []
        for city, lat, lng in cities:
            for zm in zooms:
                try:
                    w_status, w_body = _warmup(s, lat, lng, zm)
                    tried = _try_viewport_forms(s, lat, lng, zm)
                    vp_bytes = 0
                    looks_like_html = False
                    winner = "none"
                    if tried.get("winner") != "none":
                        vp_bytes = tried["response"]["bytes"]
                        looks_like_html = tried["response"]["looks_like_html"]
                        winner = tried.get("winner", "unknown")
                    results.append({
                        "city": city,
                        "lat": lat,
                        "lng": lng,
                        "zm": zm,
                        "viewport_bytes": vp_bytes,
                        "looks_like_html": looks_like_html,
                        "winner": winner,
                        "warmup_bytes": w_body and len(w_body) or 0
                    })
                except Exception:
                    results.append({
                        "city": city, "lat": lat, "lng": lng, "zm": zm,
                        "viewport_bytes": 0, "looks_like_html": False,
                        "winner": "error", "warmup_bytes": 0
                    })
        return _json({"count": len(results), "results": results})

    # NOTE: TrainFinder doesn’t expose a documented “trains” endpoint we can see.
    # Many deployments you tested returned 404 for /Home/GetTrains and API routes.
    # So we expose /trains as an alias of GetViewPortData so your Netlify app has something to call.
    @app.route("/trains", methods=["GET"])
    def trains():
        # Accept t=… (ignored), keep signature your frontend used
        _ = request.args.get("t")
        try:
            lat = float(request.args.get("lat", "-33.8688"))
            lng = float(request.args.get("lng", "151.2093"))
            zm = int(request.args.get("zm", "12"))
        except Exception:
            # If you only pass t=timestamp we still send a default viewport
            lat, lng, zm = -33.8688, 151.2093, 12

        s = _make_session()
        # Warmup optional
        try:
            _warmup(s, lat, lng, zm)
        except Exception:
            pass

        # Try the viewport JSON (this is the only stable JSON we see)
        r = s.post(f"{TF_ORIGIN}/Home/GetViewPortData",
                   data={"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
                   timeout=15,
                   headers={"X-Requested-With": "XMLHttpRequest"})
        # If not JSON, return a harmless empty structure your UI can handle
        try:
            payload = r.json()
            return _json(payload, r.status_code)
        except Exception:
            return _json({
                "favs": None, "alerts": None, "places": None, "tts": None,
                "webcams": None, "atcsGomi": None, "atcsObj": None,
                "_note": "Upstream did not return JSON; returning placeholders."
            }, 200)

    # Simple allow preflight for CORS
    @app.route("/<path:anything>", methods=["OPTIONS"])
    def options_any(anything):
        return _cors(make_response("", 200))

    return app


app = create_app()

# For local testing (not used on Render)
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
