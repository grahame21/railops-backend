import os
import json
from flask import Flask, send_file, jsonify, make_response, request

app = Flask(__name__)

OUT_FILE = os.environ.get("OUT_FILE", "trains.json")
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "")
DOWNLOAD_DIR = os.path.join("static", "downloads")


def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Auth-Token"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
      return cors(make_response("", 204))

    payload = {"ok": True, "out_file": OUT_FILE, "has_trains_file": os.path.exists(OUT_FILE)}

    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            trains = data.get("trains", [])
            payload["lastUpdated"] = data.get("lastUpdated")
            payload["count"] = len(trains) if isinstance(trains, list) else 0
            payload["note"] = data.get("note")
        except Exception as e:
            payload["read_error"] = str(e)

    return cors(make_response(jsonify(payload)))


@app.route("/trains.json", methods=["GET", "OPTIONS"])
def trains():
    if request.method == "OPTIONS":
        return cors(make_response("", 204))

    if not os.path.exists(OUT_FILE):
        return cors(make_response(jsonify({
            "lastUpdated": None,
            "note": "No trains.json yet",
            "trains": []
        })))

    resp = make_response(send_file(OUT_FILE, mimetype="application/json", as_attachment=False))
    return cors(resp)


@app.route("/push", methods=["POST", "OPTIONS"])
def push():
    if request.method == "OPTIONS":
        return cors(make_response("", 204))

    if not PUSH_TOKEN:
        return cors(make_response(jsonify({
            "ok": False,
            "error": "PUSH_TOKEN not set on server"
        }), 500))

    token = request.headers.get("X-Auth-Token", "")
    if token != PUSH_TOKEN:
        return cors(make_response(jsonify({
            "ok": False,
            "error": "unauthorized"
        }), 401))

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return cors(make_response(jsonify({
            "ok": False,
            "error": "invalid json"
        }), 400))

    if "trains" not in data or "lastUpdated" not in data:
        return cors(make_response(jsonify({
            "ok": False,
            "error": "missing keys"
        }), 400))

    trains = data.get("trains") or []
    if not isinstance(trains, list):
        return cors(make_response(jsonify({
            "ok": False,
            "error": "trains must be a list"
        }), 400))

    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, OUT_FILE)

    return cors(make_response(jsonify({
        "ok": True,
        "count": len(trains),
        "lastUpdated": data.get("lastUpdated"),
        "note": data.get("note", "")
    })))


def send_download(filename, mimetype=None, as_attachment=False):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        return cors(make_response(jsonify({
            "ok": False,
            "error": f"{filename} not found"
        }), 404))
    return cors(make_response(send_file(
        path,
        mimetype=mimetype,
        as_attachment=as_attachment,
        download_name=filename if as_attachment else None
    )))


@app.get("/downloads/loco_database.xlsx")
def download_loco_database():
    return send_download(
        "loco_database.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True
    )


@app.get("/downloads/loco_numbers_only.xlsx")
def download_loco_numbers_only():
    return send_download(
        "loco_numbers_only.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True
    )


@app.get("/downloads/loco_database.html")
def loco_database_html():
    return send_download("loco_database.html", mimetype="text/html; charset=utf-8", as_attachment=False)


@app.get("/downloads/recently_added.html")
def recently_added_html():
    return send_download("recently_added.html", mimetype="text/html; charset=utf-8", as_attachment=False)


@app.get("/downloads/loco_numbers_only.html")
def loco_numbers_only_html():
    return send_download("loco_numbers_only.html", mimetype="text/html; charset=utf-8", as_attachment=False)


@app.get("/")
def root():
    return cors(make_response(jsonify({
        "ok": True,
        "hint": "Use /trains.json, /health, /downloads/loco_database.html, /downloads/recently_added.html, /downloads/loco_numbers_only.html, /downloads/loco_database.xlsx, or /downloads/loco_numbers_only.xlsx"
    })))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)