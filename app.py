import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, make_response, request, send_file, send_from_directory


# ============================================================
# RailOps backend web server
#
# Purpose:
# - Serve generated database files from the GitHub-backed Railway app
# - Serve rendered HTML downloads
# - Serve V/Line service database pages/files
#
# This app does NOT run the scraper.
# The Railway cron service runs:
#   python railway_all_in_one_cron.py
# ============================================================


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DOWNLOADS_DIR = STATIC_DIR / "downloads"

app = Flask(__name__)


# ============================================================
# Helpers
# ============================================================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, POST"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Cache-Control, X-Auth-Token"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def json_response(payload, status: int = 200):
    return add_cors(make_response(jsonify(payload), status))


def text_response(text: str, status: int = 200, mimetype: str = "text/plain"):
    resp = make_response(text, status)
    resp.mimetype = mimetype
    return add_cors(resp)


def file_response(path: Path, mimetype: str, missing_payload=None, missing_status: int = 404):
    if not path.exists():
        if missing_payload is None:
            missing_payload = {
                "ok": False,
                "error": "file_not_found",
                "path": str(path.relative_to(BASE_DIR)) if path.is_relative_to(BASE_DIR) else str(path),
            }

        if isinstance(missing_payload, dict):
            return json_response(missing_payload, missing_status)

        return text_response(str(missing_payload), missing_status)

    return add_cors(send_file(path, mimetype=mimetype))


def safe_stat(path: Path):
    if not path.exists():
        return {
            "path": str(path.relative_to(BASE_DIR)) if path.is_relative_to(BASE_DIR) else str(path),
            "exists": False,
            "size": 0,
            "modified_utc": None,
        }

    return {
        "path": str(path.relative_to(BASE_DIR)) if path.is_relative_to(BASE_DIR) else str(path),
        "exists": True,
        "size": path.stat().st_size,
        "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
    }


def ensure_dirs():
    STATIC_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_placeholder_downloads():
    """
    Creates very small placeholder HTML files only if missing.
    These are overwritten by railway_all_in_one_cron.py after successful database generation.
    """
    ensure_dirs()

    placeholders = {
        "loco_database.html": (
            "RailOps Loco Database",
            "No locomotive database file has been generated yet.",
        ),
        "recently_added.html": (
            "RailOps Recently Added Locos",
            "No recently added locomotive file has been generated yet.",
        ),
        "loco_numbers_only.html": (
            "RailOps Loco Numbers Only",
            "No locomotive numbers-only file has been generated yet.",
        ),
        "vline_services.html": (
            "RailOps V/Line Services",
            "No V/Line services file has been generated yet. Run Railway cron after adding vline_database.py.",
        ),
    }

    for filename, (title, message) in placeholders.items():
        path = STATIC_DOWNLOADS_DIR / filename
        if path.exists():
            continue

        path.write_text(
            f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{
  margin: 0;
  padding: 24px;
  background: #071222;
  color: #eaf2ff;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
}}
.card {{
  background: #102039;
  border: 1px solid #274569;
  border-radius: 20px;
  padding: 22px;
  max-width: 900px;
  margin: auto;
}}
h1 {{
  margin-top: 0;
}}
p {{
  color: #9fb3d3;
  font-size: 18px;
  line-height: 1.45;
}}
</style>
</head>
<body>
<div class="card">
<h1>{title}</h1>
<p>{message}</p>
</div>
</body>
</html>
""",
            encoding="utf-8",
        )


ensure_placeholder_downloads()


# ============================================================
# Main routes
# ============================================================

@app.route("/", methods=["GET", "OPTIONS"])
def home():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return json_response(
        {
            "ok": True,
            "service": "railops-backend-web",
            "storage": "github_repo_files",
            "time": utc_now_iso(),
            "hint": (
                "Use /health, /debug/files, /trains.json, /live_trains.json, "
                "/locos.json, /loco_history.json, /loco_export.csv, /loco_summary.txt, "
                "/vline_services.json, /vline_services.csv, "
                "/downloads/loco_database.html, /downloads/recently_added.html, "
                "/downloads/loco_numbers_only.html, /downloads/vline_services.html"
            ),
        }
    )


@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return json_response(
        {
            "ok": True,
            "service": "railops-backend-web",
            "time": utc_now_iso(),
            "base_dir": str(BASE_DIR),
            "static_downloads_dir": str(STATIC_DOWNLOADS_DIR),
            "downloads_exists": STATIC_DOWNLOADS_DIR.exists(),
            "trains_exists": (BASE_DIR / "trains.json").exists(),
            "locos_exists": (BASE_DIR / "locos.json").exists(),
            "vline_services_exists": (BASE_DIR / "vline_services.json").exists(),
            "vline_html_exists": (STATIC_DOWNLOADS_DIR / "vline_services.html").exists(),
        }
    )


@app.route("/debug/files", methods=["GET", "OPTIONS"])
def debug_files():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    files = [
        BASE_DIR / "trains.json",
        BASE_DIR / "live_trains.json",
        BASE_DIR / "locos.json",
        BASE_DIR / "locos_master.json",
        BASE_DIR / "loco_history.json",
        BASE_DIR / "loco_export.csv",
        BASE_DIR / "loco_summary.txt",
        BASE_DIR / "blocklist.json",
        BASE_DIR / "vline_services.json",
        BASE_DIR / "vline_services.csv",
        STATIC_DOWNLOADS_DIR / "loco_database.html",
        STATIC_DOWNLOADS_DIR / "recently_added.html",
        STATIC_DOWNLOADS_DIR / "loco_numbers_only.html",
        STATIC_DOWNLOADS_DIR / "loco_database.xlsx",
        STATIC_DOWNLOADS_DIR / "loco_numbers_only.xlsx",
        STATIC_DOWNLOADS_DIR / "vline_services.html",
    ]

    return json_response(
        {
            "ok": True,
            "time": utc_now_iso(),
            "base_dir": str(BASE_DIR),
            "static_downloads_dir": str(STATIC_DOWNLOADS_DIR),
            "files": [safe_stat(path) for path in files],
        }
    )


# ============================================================
# JSON / CSV public file routes
# ============================================================

@app.route("/trains.json", methods=["GET", "OPTIONS"])
def public_trains_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        BASE_DIR / "trains.json",
        "application/json",
        {"ok": False, "error": "trains.json not found"},
    )


@app.route("/live_trains.json", methods=["GET", "OPTIONS"])
def public_live_trains_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    live_path = BASE_DIR / "live_trains.json"

    if live_path.exists():
        return file_response(live_path, "application/json")

    return file_response(
        BASE_DIR / "trains.json",
        "application/json",
        {"ok": False, "error": "live_trains.json and trains.json not found"},
    )


@app.route("/locos.json", methods=["GET", "OPTIONS"])
def public_locos_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        BASE_DIR / "locos.json",
        "application/json",
        [],
    )


@app.route("/locos_master.json", methods=["GET", "OPTIONS"])
def public_locos_master_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        BASE_DIR / "locos_master.json",
        "application/json",
        [],
    )


@app.route("/loco_history.json", methods=["GET", "OPTIONS"])
def public_loco_history_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        BASE_DIR / "loco_history.json",
        "application/json",
        [],
    )


@app.route("/loco_export.csv", methods=["GET", "OPTIONS"])
def public_loco_export_csv():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        BASE_DIR / "loco_export.csv",
        "text/csv",
        "loco_export.csv not found\n",
    )


@app.route("/loco_summary.txt", methods=["GET", "OPTIONS"])
def public_loco_summary_txt():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        BASE_DIR / "loco_summary.txt",
        "text/plain",
        "loco_summary.txt not found\n",
    )


@app.route("/blocklist.json", methods=["GET", "OPTIONS"])
def public_blocklist_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        BASE_DIR / "blocklist.json",
        "application/json",
        {"ok": False, "error": "blocklist.json not found"},
    )


# ============================================================
# V/Line service database public routes
# ============================================================

@app.route("/vline_services.json", methods=["GET", "OPTIONS"])
def public_vline_services_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        BASE_DIR / "vline_services.json",
        "application/json",
        {
            "ok": False,
            "error": "vline_services.json not found",
            "hint": "Run Railway cron after adding vline_database.py",
        },
    )


@app.route("/vline_services.csv", methods=["GET", "OPTIONS"])
def public_vline_services_csv():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        BASE_DIR / "vline_services.csv",
        "text/csv",
        "vline_services.csv not found. Run Railway cron after adding vline_database.py\n",
    )


@app.route("/downloads/vline_services.html", methods=["GET", "OPTIONS"])
def public_vline_services_html():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    return file_response(
        STATIC_DOWNLOADS_DIR / "vline_services.html",
        "text/html",
        """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RailOps V/Line Services</title>
</head>
<body>
<h1>RailOps V/Line Services</h1>
<p>No V/Line services file has been generated yet.</p>
<p>Run Railway cron after adding <strong>vline_database.py</strong>.</p>
</body>
</html>
""",
    )


# ============================================================
# Generic downloads route
# ============================================================

@app.route("/downloads/<path:filename>", methods=["GET", "OPTIONS"])
def public_downloads(filename: str):
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    ensure_dirs()

    try:
        return add_cors(
            send_from_directory(
                STATIC_DOWNLOADS_DIR,
                filename,
                as_attachment=False,
            )
        )
    except Exception:
        return json_response(
            {
                "ok": False,
                "error": "download_not_found",
                "file": filename,
                "message": (
                    "Download file not found. Try /debug/files, "
                    "/downloads/loco_database.html, /downloads/recently_added.html, "
                    "/downloads/loco_numbers_only.html, or /downloads/vline_services.html"
                ),
            },
            404,
        )


# ============================================================
# Error handlers
# ============================================================

@app.errorhandler(404)
def not_found(_):
    return json_response(
        {
            "ok": False,
            "error": "not_found",
            "message": (
                "Route not found. Try /health, /debug/files, /trains.json, "
                "/locos.json, /vline_services.json, "
                "/downloads/recently_added.html, or /downloads/vline_services.html"
            ),
        },
        404,
    )


@app.errorhandler(500)
def server_error(error):
    return json_response(
        {
            "ok": False,
            "error": "server_error",
            "message": str(error),
        },
        500,
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
