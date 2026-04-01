import os
import json
from flask import Flask, send_file, jsonify, make_response, request

app = Flask(__name__)

# File served to the frontend
OUT_FILE = os.environ.get("OUT_FILE", "trains.json")

# Shared secret: worker must send this in X-Auth-Token
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "")

def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.get("/health")
def health():
    return cors(make_response(jsonify({"ok": True})))

@app.get("/trains.json")
def trains():
    if not os.path.exists(OUT_FILE):
        return cors(make_response(jsonify({"lastUpdated": None, "note": "No trains.json yet", "trains": []})))
    resp = make_response(send_file(OUT_FILE, mimetype="application/json", as_attachment=False))
    return cors(resp)

@app.post("/push")
def push():
    # Protect this endpoint (so randoms can't overwrite your trains)
    if not PUSH_TOKEN:
        return cors(make_response(jsonify({"ok": False, "error": "PUSH_TOKEN not set on server"}), 500))

    token = request.headers.get("X-Auth-Token", "")
    if token != PUSH_TOKEN:
        return cors(make_response(jsonify({"ok": False, "error": "unauthorized"}), 401))

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return cors(make_response(jsonify({"ok": False, "error": "invalid json"}), 400))

    # Minimal validation
    if "trains" not in data or "lastUpdated" not in data:
        return cors(make_response(jsonify({"ok": False, "error": "missing keys"}), 400))

    # Write atomically
    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUT_FILE)

    return cors(make_response(jsonify({"ok": True, "count": len(data.get("trains") or [])})))

@app.get("/")
def root():
    return cors(make_response(jsonify({"ok": True, "hint": "Use /trains.json"})))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
