import os
from flask import Flask, send_file, jsonify, make_response

app = Flask(__name__)
OUT_FILE = os.environ.get("OUT_FILE", "trains.json")

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

@app.get("/")
def root():
    return cors(make_response(jsonify({"ok": True, "hint": "Use /trains.json"})))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
