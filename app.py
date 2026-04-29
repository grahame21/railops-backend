import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
    make_response,
    send_file,
)

try:
    from werkzeug.security import check_password_hash
    HAS_WERKZEUG = True
except ImportError:
    HAS_WERKZEUG = False


# ============================================================
# RailOps GitHub database paths
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
STATIC_DATA_DIR = BASE_DIR / "static" / "data"
STATIC_DOWNLOADS_DIR = BASE_DIR / "static" / "downloads"

USERS_FILE = DATA_DIR / "users.json"
TOKENS_FILE = DATA_DIR / "guest_tokens.json"
LOGS_FILE = DATA_DIR / "activity_log.json"

LIVE_TRAINS_FILE = BASE_DIR / "trains.json"
LIVE_TRAINS_ALIAS_FILE = BASE_DIR / "live_trains.json"

LIVE_LOCOS_FILE = BASE_DIR / "locos.json"
LIVE_LOCO_HISTORY_FILE = BASE_DIR / "loco_history.json"
LIVE_LOCO_EXPORT_FILE = BASE_DIR / "loco_export.csv"
LIVE_LOCO_SUMMARY_FILE = BASE_DIR / "loco_summary.txt"

LOCO_DATABASE_HTML = STATIC_DOWNLOADS_DIR / "loco_database.html"
RECENTLY_ADDED_HTML = STATIC_DOWNLOADS_DIR / "recently_added.html"
LOCO_NUMBERS_ONLY_HTML = STATIC_DOWNLOADS_DIR / "loco_numbers_only.html"
LOCO_DATABASE_XLSX = STATIC_DOWNLOADS_DIR / "loco_database.xlsx"
LOCO_NUMBERS_ONLY_XLSX = STATIC_DOWNLOADS_DIR / "loco_numbers_only.xlsx"

BLOCKLIST_FILE = BASE_DIR / "blocklist.json"


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key-now")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)


# ============================================================
# Helpers
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, POST"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Cache-Control, X-Auth-Token"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def count_json_records(path: Path) -> int:
    if not path.exists():
        return 0

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0

    if isinstance(payload, list):
        return len(payload)

    if isinstance(payload, dict):
        for key in ["trains", "locos", "items", "data"]:
            if isinstance(payload.get(key), list):
                return len(payload[key])

    return 0


def file_info(path: Path) -> dict:
    return {
        "path": str(path.relative_to(BASE_DIR)) if path.exists() else str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
        "records": count_json_records(path) if path.suffix.lower() == ".json" else None,
        "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        if path.exists()
        else None,
    }


def ensure_seed_files() -> None:
    ensure_dirs()

    if not USERS_FILE.exists():
        save_json(
            USERS_FILE,
            {
                "admins": [
                    {
                        "username": "admin",
                        "password": "change-me-now",
                        "display_name": "RailOps Admin",
                    }
                ],
                "guests": [
                    {
                        "username": "guest",
                        "password": "guest123",
                        "display_name": "Guest User",
                        "disabled": False,
                        "expires_at": None,
                        "device_lock": False,
                        "device_id": None,
                    }
                ],
                "flight_only_users": [],
            },
        )

    if not TOKENS_FILE.exists():
        save_json(TOKENS_FILE, {"tokens": []})

    if not LOGS_FILE.exists():
        save_json(LOGS_FILE, {"events": []})

    if not LIVE_TRAINS_FILE.exists():
        save_json(
            LIVE_TRAINS_FILE,
            {
                "lastUpdated": iso_now(),
                "note": "No live trains generated yet",
                "trains": [],
            },
        )

    if not LIVE_LOCOS_FILE.exists():
        save_json(LIVE_LOCOS_FILE, [])

    if not LIVE_LOCO_HISTORY_FILE.exists():
        save_json(LIVE_LOCO_HISTORY_FILE, [])

    if not LIVE_LOCO_EXPORT_FILE.exists():
        LIVE_LOCO_EXPORT_FILE.write_text("", encoding="utf-8")

    if not LIVE_LOCO_SUMMARY_FILE.exists():
        LIVE_LOCO_SUMMARY_FILE.write_text("No loco summary generated yet.\n", encoding="utf-8")

    if not RECENTLY_ADDED_HTML.exists():
        RECENTLY_ADDED_HTML.write_text(
            "<!doctype html><html><body><h1>RailOps Recently Added Locos</h1><p>No recently added file generated yet.</p></body></html>",
            encoding="utf-8",
        )

    if not LOCO_DATABASE_HTML.exists():
        LOCO_DATABASE_HTML.write_text(
            "<!doctype html><html><body><h1>RailOps Loco Database</h1><p>No database generated yet.</p></body></html>",
            encoding="utf-8",
        )

    if not LOCO_NUMBERS_ONLY_HTML.exists():
        LOCO_NUMBERS_ONLY_HTML.write_text(
            "<!doctype html><html><body><h1>RailOps Loco Numbers Only</h1><p>No numbers-only file generated yet.</p></body></html>",
            encoding="utf-8",
        )

    if not BLOCKLIST_FILE.exists():
        save_json(
            BLOCKLIST_FILE,
            {
                "blocked_locos": [],
                "blocked_routes": [],
                "blocked_descriptions": [],
                "blocked_operators": [],
                "notes": "Use * as a wildcard. Example: TNSW* blocks all loco numbers starting with TNSW.",
            },
        )


ensure_seed_files()


# ============================================================
# Auth helpers
# ============================================================

def log_event(action: str, details: dict | None = None) -> None:
    payload = load_json(LOGS_FILE, {"events": []})
    payload["events"].insert(
        0,
        {
            "time": iso_now(),
            "user": session.get("username", "anonymous"),
            "role": session.get("role", "anonymous"),
            "action": action,
            "details": details or {},
        },
    )
    payload["events"] = payload["events"][:200]
    save_json(LOGS_FILE, payload)


def get_users():
    return load_json(USERS_FILE, {"admins": [], "guests": [], "flight_only_users": []})


def find_user(username: str):
    users = get_users()

    for admin in users.get("admins", []):
        if admin.get("username") == username:
            return "admin", admin

    for guest in users.get("guests", []):
        if guest.get("username") == username:
            return "guest", guest

    for flight_user in users.get("flight_only_users", []):
        if flight_user.get("username") == username:
            return "flight_only", flight_user

    return None, None


def is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) < utc_now()
    except Exception:
        return False


def _is_password_hash(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return any(value.startswith(pattern) for pattern in ["pbkdf2:", "scrypt$", "bcrypt$", "argon2"])


def verify_password(stored_password: str | None, provided_password: str) -> bool:
    if not stored_password or not provided_password:
        return False

    if _is_password_hash(stored_password):
        try:
            if HAS_WERKZEUG:
                return check_password_hash(stored_password, provided_password)
        except Exception:
            pass

    return stored_password == provided_password


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        if session.get("role") != "admin":
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


# ============================================================
# Public routes
# ============================================================

@app.get("/")
def home():
    if session.get("logged_in"):
        if session.get("role") == "admin":
            return redirect(url_for("admin_page"))
        if session.get("role") == "flight_only":
            return redirect(url_for("flight_page"))
        return redirect(url_for("dashboard_page"))

    return jsonify(
        {
            "ok": True,
            "storage": "github_repo_files",
            "hint": (
                "Use /trains.json, /health, /locos.json, /loco_history.json, "
                "/downloads/loco_database.html, /downloads/recently_added.html, "
                "/downloads/loco_numbers_only.html, /debug/files"
            ),
        }
    )


@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    resp = jsonify(
        {
            "ok": True,
            "service": "railops-backend",
            "storage": "github_repo_files",
            "time": iso_now(),
            "base_dir": str(BASE_DIR),
            "trains_count": count_json_records(LIVE_TRAINS_FILE),
            "locos_count": count_json_records(LIVE_LOCOS_FILE),
            "trains_exists": LIVE_TRAINS_FILE.exists(),
            "locos_exists": LIVE_LOCOS_FILE.exists(),
            "downloads_dir_exists": STATIC_DOWNLOADS_DIR.exists(),
        }
    )
    return add_cors(resp)


@app.route("/debug/files", methods=["GET", "OPTIONS"])
def debug_files():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    files = [
        LIVE_TRAINS_FILE,
        LIVE_TRAINS_ALIAS_FILE,
        LIVE_LOCOS_FILE,
        LIVE_LOCO_HISTORY_FILE,
        LIVE_LOCO_EXPORT_FILE,
        LIVE_LOCO_SUMMARY_FILE,
        LOCO_DATABASE_HTML,
        RECENTLY_ADDED_HTML,
        LOCO_NUMBERS_ONLY_HTML,
        LOCO_DATABASE_XLSX,
        LOCO_NUMBERS_ONLY_XLSX,
        BLOCKLIST_FILE,
        USERS_FILE,
        TOKENS_FILE,
        LOGS_FILE,
    ]

    return add_cors(
        jsonify(
            {
                "ok": True,
                "storage": "github_repo_files",
                "files": [file_info(path) for path in files],
            }
        )
    )


@app.route("/trains.json", methods=["GET", "OPTIONS"])
def public_trains_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))
    return add_cors(send_file(LIVE_TRAINS_FILE, mimetype="application/json"))


@app.route("/live_trains.json", methods=["GET", "OPTIONS"])
def public_live_trains_json_alias():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    if LIVE_TRAINS_ALIAS_FILE.exists():
        return add_cors(send_file(LIVE_TRAINS_ALIAS_FILE, mimetype="application/json"))

    return add_cors(send_file(LIVE_TRAINS_FILE, mimetype="application/json"))


@app.route("/locos.json", methods=["GET", "OPTIONS"])
def public_locos_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))
    return add_cors(send_file(LIVE_LOCOS_FILE, mimetype="application/json"))


@app.route("/loco_history.json", methods=["GET", "OPTIONS"])
def public_loco_history_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))
    return add_cors(send_file(LIVE_LOCO_HISTORY_FILE, mimetype="application/json"))


@app.route("/loco_export.csv", methods=["GET", "OPTIONS"])
def public_loco_export_csv():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))
    return add_cors(send_file(LIVE_LOCO_EXPORT_FILE, mimetype="text/csv"))


@app.route("/loco_summary.txt", methods=["GET", "OPTIONS"])
def public_loco_summary_txt():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))
    return add_cors(send_file(LIVE_LOCO_SUMMARY_FILE, mimetype="text/plain"))


@app.route("/downloads/<path:filename>", methods=["GET", "OPTIONS"])
def public_downloads(filename: str):
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))
    return add_cors(send_from_directory(STATIC_DOWNLOADS_DIR, filename, as_attachment=False))


# ============================================================
# Login / dashboard / admin
# ============================================================

@app.get("/login")
def login_page():
    if session.get("logged_in"):
        if session.get("role") == "admin":
            return redirect(url_for("admin_page"))
        if session.get("role") == "flight_only":
            return redirect(url_for("flight_page"))
        return redirect(url_for("dashboard_page"))

    return render_template("login.html")


@app.post("/login")
def login_submit():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    device_id = request.form.get("device_id", "").strip() or None

    role, user = find_user(username)

    if not user or not verify_password(user.get("password"), password):
        flash("Invalid username or password.", "error")
        return redirect(url_for("login_page"))

    if role == "guest":
        if user.get("disabled"):
            flash("This guest account is blocked.", "error")
            return redirect(url_for("login_page"))
        if is_expired(user.get("expires_at")):
            flash("This guest account has expired.", "error")
            return redirect(url_for("login_page"))

        if user.get("device_lock"):
            users = get_users()
            for guest in users.get("guests", []):
                if guest.get("username") == username:
                    if guest.get("device_id") and guest.get("device_id") != device_id:
                        flash("This guest account is locked to another device.", "error")
                        return redirect(url_for("login_page"))
                    guest["device_id"] = device_id
                    save_json(USERS_FILE, users)
                    break

    if role == "flight_only":
        if user.get("disabled"):
            flash("This flight-only account is blocked.", "error")
            return redirect(url_for("login_page"))
        if is_expired(user.get("expires_at")):
            flash("This flight-only account has expired.", "error")
            return redirect(url_for("login_page"))

    session.permanent = True
    session["logged_in"] = True
    session["username"] = username
    session["display_name"] = user.get("display_name", username)
    session["role"] = role
    session["device_id"] = device_id

    log_event("login", {"target": username})

    if role == "admin":
        return redirect(url_for("admin_page"))
    if role == "flight_only":
        return redirect(url_for("flight_page"))
    return redirect(url_for("dashboard_page"))


@app.get("/logout")
def logout():
    log_event("logout")
    session.clear()
    return redirect(url_for("login_page"))


@app.get("/dashboard")
@login_required
def dashboard_page():
    return render_template("dashboard.html")


@app.get("/flight")
def flight_page():
    if not session.get("logged_in"):
        return redirect(url_for("login_page"))
    if session.get("role") not in ["flight_only", "admin"]:
        abort(403)
    return render_template("flight.html")


@app.get("/admin")
@admin_required
def admin_page():
    users = get_users()
    tokens = load_json(TOKENS_FILE, {"tokens": []})
    logs = load_json(LOGS_FILE, {"events": []})

    file_links = [
        {"name": "Live Train Data", "path": "/trains.json"},
        {"name": "Locos JSON", "path": "/locos.json"},
        {"name": "Loco History JSON", "path": "/loco_history.json"},
        {"name": "Loco Export CSV", "path": "/loco_export.csv"},
        {"name": "Loco Summary TXT", "path": "/loco_summary.txt"},
        {"name": "Locomotive Database HTML", "path": "/downloads/loco_database.html"},
        {"name": "Recently Added HTML", "path": "/downloads/recently_added.html"},
        {"name": "Numbers Only HTML", "path": "/downloads/loco_numbers_only.html"},
        {"name": "Locomotive Database XLSX", "path": "/downloads/loco_database.xlsx"},
        {"name": "Numbers Only XLSX", "path": "/downloads/loco_numbers_only.xlsx"},
        {"name": "Debug Files", "path": "/debug/files"},
    ]

    return render_template(
        "admin.html",
        guest_accounts=users.get("guests", []),
        flight_only_accounts=users.get("flight_only_users", []),
        tokens=tokens.get("tokens", []),
        logs=logs.get("events", [])[:20],
        file_links=file_links,
        github_workflow=os.getenv("GITHUB_WORKFLOW_ID", "update-database.yml"),
        github_repo=os.getenv("GITHUB_REPO", "grahame21/railops-backend"),
    )


@app.get("/session")
def session_info():
    return jsonify(
        {
            "logged_in": bool(session.get("logged_in")),
            "username": session.get("username"),
            "display_name": session.get("display_name"),
            "role": session.get("role"),
        }
    )


@app.post("/admin/create-guest")
@admin_required
def create_guest():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    display_name = request.form.get("display_name", "").strip() or username
    expires_days = request.form.get("expires_days", "").strip()
    device_lock = request.form.get("device_lock") == "on"

    if not username or not password:
        flash("Guest username and password are required.", "error")
        return redirect(url_for("admin_page"))

    role, _ = find_user(username)
    if role:
        flash("That username already exists.", "error")
        return redirect(url_for("admin_page"))

    expires_at = None
    if expires_days:
        try:
            expires_at = (utc_now() + timedelta(days=int(expires_days))).isoformat()
        except ValueError:
            flash("Expiry days must be a number.", "error")
            return redirect(url_for("admin_page"))

    users = get_users()
    users.setdefault("guests", [])
    users["guests"].append(
        {
            "username": username,
            "password": password,
            "display_name": display_name,
            "disabled": False,
            "expires_at": expires_at,
            "device_lock": device_lock,
            "device_id": None,
        }
    )
    save_json(USERS_FILE, users)

    log_event("create_guest", {"guest": username})
    flash(f"Guest account {username} created.", "success")
    return redirect(url_for("admin_page"))


@app.post("/admin/toggle-guest/<username>")
@admin_required
def toggle_guest(username: str):
    users = get_users()

    for guest in users.get("guests", []):
        if guest.get("username") == username:
            guest["disabled"] = not guest.get("disabled", False)
            save_json(USERS_FILE, users)
            log_event("toggle_guest", {"guest": username, "disabled": guest["disabled"]})
            flash(f"Guest {username} updated.", "success")
            break

    return redirect(url_for("admin_page"))


@app.post("/admin/generate-token")
@admin_required
def generate_token():
    label = request.form.get("label", "").strip() or "Guest token"
    expires_days = request.form.get("expires_days", "").strip()
    token = secrets.token_urlsafe(18)

    expires_at = None
    if expires_days:
        try:
            expires_at = (utc_now() + timedelta(days=int(expires_days))).isoformat()
        except ValueError:
            flash("Token expiry must be a number.", "error")
            return redirect(url_for("admin_page"))

    payload = load_json(TOKENS_FILE, {"tokens": []})
    payload.setdefault("tokens", [])
    payload["tokens"].insert(
        0,
        {
            "token": token,
            "label": label,
            "created_at": iso_now(),
            "expires_at": expires_at,
            "disabled": False,
        },
    )

    save_json(TOKENS_FILE, payload)
    log_event("create_token", {"label": label})
    flash(f"Token created: {token}", "success")
    return redirect(url_for("admin_page"))


@app.get("/access")
def token_access():
    token = request.args.get("token", "").strip()

    if not token:
        return redirect(url_for("login_page"))

    payload = load_json(TOKENS_FILE, {"tokens": []})

    for item in payload.get("tokens", []):
        if item.get("token") == token:
            if item.get("disabled"):
                abort(403)
            if is_expired(item.get("expires_at")):
                abort(403)

            session.permanent = True
            session["logged_in"] = True
            session["username"] = f"token:{item.get('label', 'guest')}"
            session["display_name"] = item.get("label", "Guest token")
            session["role"] = "guest"
            session["device_id"] = request.headers.get("User-Agent", "")[:120]

            log_event("token_login", {"label": item.get("label")})
            return redirect(url_for("dashboard_page"))

    abort(403)


@app.errorhandler(403)
def forbidden(_):
    return (
        render_template(
            "simple_page.html",
            title="Access denied",
            message="You do not have permission to open this page.",
        ),
        403,
    )


@app.errorhandler(404)
def not_found(_):
    return (
        jsonify(
            {
                "ok": False,
                "error": "not_found",
                "message": "Route not found. Try /health, /debug/files, /trains.json, /locos.json, or /downloads/recently_added.html",
            }
        ),
        404,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))