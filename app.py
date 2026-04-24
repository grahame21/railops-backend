import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import requests
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

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DATA_DIR = BASE_DIR / "static" / "data"
STATIC_DOWNLOADS_DIR = BASE_DIR / "static" / "downloads"
USERS_FILE = DATA_DIR / "users.json"
TOKENS_FILE = DATA_DIR / "guest_tokens.json"
LOGS_FILE = DATA_DIR / "activity_log.json"
LIVE_TRAINS_FILE = BASE_DIR / "live_trains.json"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-key-now")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

for folder in [DATA_DIR, STATIC_DATA_DIR, STATIC_DOWNLOADS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, POST"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Cache-Control, X-Auth-Token"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def ensure_seed_files() -> None:
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
                "note": "No live trains uploaded yet",
                "trains": [],
            },
        )

    placeholders = {
        "locomotives.db": "Put your real locomotives.db in this folder.\n",
        "flight_data.json": json.dumps({"lastUpdated": iso_now(), "aircraft": []}, indent=2),
        "exports-readme.txt": "Store CSV or JSON exports here.\n",
        "updater-status.json": json.dumps({"lastRun": None, "status": "idle"}, indent=2),
    }

    for name, content in placeholders.items():
        p = STATIC_DATA_DIR / name
        if not p.exists():
            p.write_text(content, encoding="utf-8")


ensure_seed_files()


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
        if admin["username"] == username:
            return "admin", admin
    for guest in users.get("guests", []):
        if guest["username"] == username:
            return "guest", guest
    for flight_user in users.get("flight_only_users", []):
        if flight_user["username"] == username:
            return "flight_only", flight_user
    return None, None


def is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) < utc_now()
    except Exception:
        return False


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


def _is_password_hash(value: str) -> bool:
    if not isinstance(value, str):
        return False
    hash_patterns = ["pbkdf2:", "scrypt$", "bcrypt$", "argon2"]
    return any(value.startswith(pattern) for pattern in hash_patterns)


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


@app.get("/")
def home():
    if session.get("logged_in"):
        if session.get("role") == "admin":
            return redirect(url_for("admin_page"))
        elif session.get("role") == "flight_only":
            return redirect(url_for("flight_page"))
        else:
            return redirect(url_for("dashboard_page"))
    return jsonify(
        {
            "ok": True,
            "hint": "Use /trains.json, /health, /downloads/loco_database.html, /downloads/recently_added.html, /downloads/loco_numbers_only.html, /downloads/loco_database.xlsx, or /downloads/loco_numbers_only.xlsx",
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
            "time": iso_now(),
        }
    )
    return add_cors(resp)


@app.route("/trains.json", methods=["GET", "OPTIONS"])
def public_trains_json():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    if not LIVE_TRAINS_FILE.exists():
        return add_cors(
            make_response(
                json.dumps(
                    {
                        "ok": False,
                        "error": "live trains file not found",
                    }
                ),
                404,
            )
        )

    resp = make_response(send_file(LIVE_TRAINS_FILE, mimetype="application/json"))
    return add_cors(resp)


@app.route("/push_trains", methods=["POST", "OPTIONS"])
def push_trains():
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    push_token = os.getenv("PUSH_TOKEN", "").strip()
    supplied_token = request.headers.get("X-Auth-Token", "").strip()

    if not push_token or supplied_token != push_token:
        return add_cors(make_response(json.dumps({"ok": False, "error": "unauthorized"}), 401))

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return add_cors(make_response(json.dumps({"ok": False, "error": "invalid json"}), 400))

    trains = payload.get("trains")
    if not isinstance(trains, list):
        return add_cors(make_response(json.dumps({"ok": False, "error": "missing trains list"}), 400))

    save_json(LIVE_TRAINS_FILE, payload)
    return add_cors(jsonify({"ok": True, "saved": len(trains)}))


@app.route("/downloads/<path:filename>", methods=["GET", "OPTIONS"])
def public_downloads(filename: str):
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    resp = make_response(send_from_directory(STATIC_DOWNLOADS_DIR, filename, as_attachment=False))
    return add_cors(resp)


@app.get("/login")
def login_page():
    if session.get("logged_in"):
        if session.get("role") == "admin":
            return redirect(url_for("admin_page"))
        elif session.get("role") == "flight_only":
            return redirect(url_for("flight_page"))
        else:
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
                if guest["username"] == username:
                    if guest.get("device_id") and guest["device_id"] != device_id:
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
    elif role == "flight_only":
        return redirect(url_for("flight_page"))
    else:
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
        {"name": "Locomotive Database", "path": "/downloads/loco_database.html"},
        {"name": "Recently Added", "path": "/downloads/recently_added.html"},
        {"name": "Numbers Only", "path": "/downloads/loco_numbers_only.html"},
    ]
    return render_template(
        "admin.html",
        guest_accounts=users.get("guests", []),
        flight_only_accounts=users.get("flight_only_users", []),
        tokens=tokens.get("tokens", []),
        logs=logs.get("events", [])[:20],
        file_links=file_links,
        github_workflow=os.getenv("GITHUB_WORKFLOW_ID", "fast-scraper.yml"),
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
        if guest["username"] == username:
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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
