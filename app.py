import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
STATIC_DATA_DIR = BASE_DIR / 'static' / 'data'
USERS_FILE = DATA_DIR / 'users.json'
TOKENS_FILE = DATA_DIR / 'guest_tokens.json'
LOGS_FILE = DATA_DIR / 'activity_log.json'

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'change-this-secret-key-now')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

for folder in [DATA_DIR, STATIC_DATA_DIR]:
    folder.mkdir(parents=True, exist_ok=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def ensure_seed_files() -> None:
    if not USERS_FILE.exists():
        save_json(
            USERS_FILE,
            {
                'admins': [
                    {
                        'username': 'admin',
                        'password': 'change-me-now',
                        'display_name': 'RailOps Admin'
                    }
                ],
                'guests': [
                    {
                        'username': 'guest',
                        'password': 'guest123',
                        'display_name': 'Guest User',
                        'disabled': False,
                        'expires_at': None,
                        'device_lock': False,
                        'device_id': None,
                    }
                ]
            },
        )

    if not TOKENS_FILE.exists():
        save_json(TOKENS_FILE, {'tokens': []})

    if not LOGS_FILE.exists():
        save_json(LOGS_FILE, {'events': []})

    if not (STATIC_DATA_DIR / 'trains.json').exists():
        save_json(
            STATIC_DATA_DIR / 'trains.json',
            {
                'lastUpdated': iso_now(),
                'note': 'Replace this file with your live trains feed.',
                'trains': []
            },
        )

    placeholders = {
        'locomotives.db': 'Put your real locomotives.db in this folder.\n',
        'flight_data.json': json.dumps({'lastUpdated': iso_now(), 'aircraft': []}, indent=2),
        'exports-readme.txt': 'Store CSV or JSON exports here.\n',
        'updater-status.json': json.dumps({'lastRun': None, 'status': 'idle'}, indent=2),
    }
    for name, content in placeholders.items():
        p = STATIC_DATA_DIR / name
        if not p.exists():
            p.write_text(content, encoding='utf-8')


ensure_seed_files()


def log_event(action: str, details: dict | None = None) -> None:
    payload = load_json(LOGS_FILE, {'events': []})
    payload['events'].insert(
        0,
        {
            'time': iso_now(),
            'user': session.get('username', 'anonymous'),
            'role': session.get('role', 'anonymous'),
            'action': action,
            'details': details or {},
        },
    )
    payload['events'] = payload['events'][:200]
    save_json(LOGS_FILE, payload)


def get_users():
    return load_json(USERS_FILE, {'admins': [], 'guests': []})


def find_user(username: str):
    users = get_users()
    for admin in users.get('admins', []):
        if admin['username'] == username:
            return 'admin', admin
    for guest in users.get('guests', []):
        if guest['username'] == username:
            return 'guest', guest
    return None, None


def is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) < utc_now()
    except Exception:
        return False


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login_page'))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login_page'))
        if session.get('role') != 'admin':
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


@app.get('/')
def home():
    if session.get('logged_in'):
        return redirect(url_for('admin_page' if session.get('role') == 'admin' else 'dashboard_page'))
    return redirect(url_for('login_page'))


@app.get('/login')
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('admin_page' if session.get('role') == 'admin' else 'dashboard_page'))
    return render_template('login.html')


@app.post('/login')
def login_submit():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    device_id = request.form.get('device_id', '').strip() or None

    role, user = find_user(username)
    if not user or user.get('password') != password:
        flash('Invalid username or password.', 'error')
        return redirect(url_for('login_page'))

    if role == 'guest':
        if user.get('disabled'):
            flash('This guest account is blocked.', 'error')
            return redirect(url_for('login_page'))
        if is_expired(user.get('expires_at')):
            flash('This guest account has expired.', 'error')
            return redirect(url_for('login_page'))

        if user.get('device_lock'):
            users = get_users()
            for guest in users.get('guests', []):
                if guest['username'] == username:
                    if guest.get('device_id') and guest['device_id'] != device_id:
                        flash('This guest account is locked to another device.', 'error')
                        return redirect(url_for('login_page'))
                    guest['device_id'] = device_id
                    save_json(USERS_FILE, users)
                    break

    session.permanent = True
    session['logged_in'] = True
    session['username'] = username
    session['display_name'] = user.get('display_name', username)
    session['role'] = role
    session['device_id'] = device_id
    log_event('login', {'target': username})
    return redirect(url_for('admin_page' if role == 'admin' else 'dashboard_page'))


@app.get('/logout')
def logout():
    log_event('logout')
    session.clear()
    return redirect(url_for('login_page'))


@app.get('/dashboard')
@login_required
def dashboard_page():
    return render_template('dashboard.html')


@app.get('/admin')
@admin_required
def admin_page():
    users = get_users()
    tokens = load_json(TOKENS_FILE, {'tokens': []})
    logs = load_json(LOGS_FILE, {'events': []})
    file_links = [
        {'name': 'Live Train Data', 'path': '/admin/files/trains.json'},
        {'name': 'Locomotive Database', 'path': '/admin/files/locomotives.db'},
        {'name': 'Flight Tracker Data', 'path': '/admin/files/flight_data.json'},
        {'name': 'Exports Folder Note', 'path': '/admin/files/exports-readme.txt'},
        {'name': 'Updater Status', 'path': '/admin/files/updater-status.json'},
    ]
    return render_template(
        'admin.html',
        guest_accounts=users.get('guests', []),
        tokens=tokens.get('tokens', []),
        logs=logs.get('events', [])[:20],
        file_links=file_links,
        github_workflow=os.getenv('GITHUB_WORKFLOW_ID', 'fast-scraper.yml'),
        github_repo=os.getenv('GITHUB_REPO', 'grahame21/railops-backend'),
    )


@app.get('/session')
def session_info():
    return jsonify(
        {
            'logged_in': bool(session.get('logged_in')),
            'username': session.get('username'),
            'display_name': session.get('display_name'),
            'role': session.get('role'),
        }
    )


@app.post('/admin/create-guest')
@admin_required
def create_guest():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    display_name = request.form.get('display_name', '').strip() or username
    expires_days = request.form.get('expires_days', '').strip()
    device_lock = request.form.get('device_lock') == 'on'

    if not username or not password:
        flash('Guest username and password are required.', 'error')
        return redirect(url_for('admin_page'))

    role, _ = find_user(username)
    if role:
        flash('That username already exists.', 'error')
        return redirect(url_for('admin_page'))

    expires_at = None
    if expires_days:
        try:
            expires_at = (utc_now() + timedelta(days=int(expires_days))).isoformat()
        except ValueError:
            flash('Expiry days must be a number.', 'error')
            return redirect(url_for('admin_page'))

    users = get_users()
    users['guests'].append(
        {
            'username': username,
            'password': password,
            'display_name': display_name,
            'disabled': False,
            'expires_at': expires_at,
            'device_lock': device_lock,
            'device_id': None,
        }
    )
    save_json(USERS_FILE, users)
    log_event('create_guest', {'guest': username})
    flash(f'Guest account {username} created.', 'success')
    return redirect(url_for('admin_page'))


@app.post('/admin/toggle-guest/<username>')
@admin_required
def toggle_guest(username: str):
    users = get_users()
    for guest in users.get('guests', []):
        if guest['username'] == username:
            guest['disabled'] = not guest.get('disabled', False)
            save_json(USERS_FILE, users)
            log_event('toggle_guest', {'guest': username, 'disabled': guest['disabled']})
            flash(f'Guest {username} updated.', 'success')
            break
    return redirect(url_for('admin_page'))


@app.post('/admin/generate-token')
@admin_required
def generate_token():
    label = request.form.get('label', '').strip() or 'Guest token'
    expires_days = request.form.get('expires_days', '').strip()
    token = secrets.token_urlsafe(18)
    expires_at = None
    if expires_days:
        try:
            expires_at = (utc_now() + timedelta(days=int(expires_days))).isoformat()
        except ValueError:
            flash('Token expiry must be a number.', 'error')
            return redirect(url_for('admin_page'))

    payload = load_json(TOKENS_FILE, {'tokens': []})
    payload['tokens'].insert(
        0,
        {
            'token': token,
            'label': label,
            'created_at': iso_now(),
            'expires_at': expires_at,
            'disabled': False,
        },
    )
    save_json(TOKENS_FILE, payload)
    log_event('create_token', {'label': label})
    flash(f'Token created: {token}', 'success')
    return redirect(url_for('admin_page'))


@app.post('/admin/run-fast-scraper')
@admin_required
def run_fast_scraper():
    github_token = os.getenv('GITHUB_PAT')
    github_repo = os.getenv('GITHUB_REPO')
    workflow_id = os.getenv('GITHUB_WORKFLOW_ID')
    branch = os.getenv('GITHUB_WORKFLOW_REF', 'main')

    if not github_token or not github_repo or not workflow_id:
        flash('GitHub workflow trigger is not configured yet. Add GITHUB_PAT, GITHUB_REPO, and GITHUB_WORKFLOW_ID.', 'error')
        return redirect(url_for('admin_page'))

    url = f'https://api.github.com/repos/{github_repo}/actions/workflows/{workflow_id}/dispatches'
    headers = {
        'Authorization': f'Bearer {github_token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    payload = {'ref': branch}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code == 204:
            log_event('run_fast_scraper', {'workflow': workflow_id, 'repo': github_repo})
            flash('Fast scraper workflow triggered successfully.', 'success')
        else:
            flash(f'GitHub trigger failed: HTTP {response.status_code} - {response.text[:180]}', 'error')
    except requests.RequestException as exc:
        flash(f'GitHub trigger failed: {exc}', 'error')

    return redirect(url_for('admin_page'))


@app.get('/admin/files/<path:filename>')
@admin_required
def admin_files(filename: str):
    return send_from_directory(STATIC_DATA_DIR, filename, as_attachment=False)


@app.get('/access')
def token_access():
    token = request.args.get('token', '').strip()
    payload = load_json(TOKENS_FILE, {'tokens': []})
    for item in payload.get('tokens', []):
        if item['token'] == token:
            if item.get('disabled'):
                abort(403)
            if is_expired(item.get('expires_at')):
                abort(403)
            session.permanent = True
            session['logged_in'] = True
            session['username'] = item.get('label', 'token-guest')
            session['display_name'] = item.get('label', 'Guest Access')
            session['role'] = 'guest'
            log_event('token_login', {'label': item.get('label')})
            return redirect(url_for('dashboard_page'))
    abort(403)


@app.get('/flight-tracker')
@login_required
def flight_tracker_placeholder():
    return render_template('simple_page.html', title='Flight Tracker', message='Hook your ADS-B page or route in here.')


@app.get('/loco-db')
@login_required
def locomotive_db_placeholder():
    return render_template('simple_page.html', title='Locomotive Database', message='Point this route to your locomotive database viewer.')


@app.errorhandler(403)
def forbidden(_):
    return render_template('simple_page.html', title='Access denied', message='You do not have permission to open this page.'), 403


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
