import os
from flask import Flask, send_file, jsonify

app = Flask(__name__)
OUT_FILE = os.environ.get("OUT_FILE", "trains.json")

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.get("/trains.json")
def trains():
    if not os.path.exists(OUT_FILE):
        return jsonify({"lastUpdated": None, "note": "No trains.json yet", "trains": []})
    return send_file(OUT_FILE, mimetype="application/json", as_attachment=False)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
