import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

DATABASE_FILES = [
    "trains.json",
    "live_trains.json",
    "locos.json",
    "loco_history.json",
    "loco_export.csv",
    "loco_summary.txt",
    "blocklist.json",
    "static/downloads/loco_database.html",
    "static/downloads/recently_added.html",
    "static/downloads/loco_numbers_only.html",
    "static/downloads/loco_database.xlsx",
    "static/downloads/loco_numbers_only.xlsx",
]


def log(message: str) -> None:
    print(message, flush=True)


def run(command: list[str], label: str, allow_fail: bool = False) -> int:
    log("")
    log(f"=== RUNNING {label} ===")
    log("Command: " + " ".join(command))

    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        text=True,
    )

    log(f"=== FINISHED {label} with code {result.returncode} ===")

    if result.returncode != 0 and not allow_fail:
        raise RuntimeError(f"{label} failed with code {result.returncode}")

    return result.returncode


def git_config() -> None:
    name = os.getenv("GIT_COMMIT_NAME", "RailOps Railway Bot")
    email = os.getenv("GIT_COMMIT_EMAIL", "railops-bot@users.noreply.github.com")

    run(["git", "config", "user.name", name], "git config user.name", allow_fail=True)
    run(["git", "config", "user.email", email], "git config user.email", allow_fail=True)


def setup_github_auth() -> bool:
    token = os.getenv("GITHUB_TOKEN_PUSH", "").strip()
    repo = os.getenv("GITHUB_REPO", "grahame21/railops-backend").strip()
    branch = os.getenv("GITHUB_BRANCH", "main").strip()

    if not token:
        log("Missing GITHUB_TOKEN_PUSH. Cannot push database files to GitHub.")
        return False

    authed_url = f"https://x-access-token:{token}@github.com/{repo}.git"

    run(["git", "remote", "set-url", "origin", authed_url], "set authenticated git remote", allow_fail=True)
    run(["git", "fetch", "origin", branch], "git fetch", allow_fail=True)
    run(["git", "checkout", branch], "git checkout branch", allow_fail=True)
    run(["git", "pull", "--rebase", "origin", branch], "git pull rebase", allow_fail=True)

    return True


def load_json_file(path: Path):
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_train_count() -> int:
    """
    Counts trains from trains.json.
    Supports:
    - {"trains": [...]}
    - [...]
    - {"data": [...]}
    - {"items": [...]}
    """
    trains_file = BASE_DIR / "trains.json"
    payload = load_json_file(trains_file)

    if isinstance(payload, list):
        return len(payload)

    if isinstance(payload, dict):
        for key in ["trains", "data", "items", "features"]:
            if isinstance(payload.get(key), list):
                return len(payload[key])

    return 0


def get_loco_count() -> int:
    locos_file = BASE_DIR / "locos.json"
    payload = load_json_file(locos_file)

    if isinstance(payload, list):
        return len(payload)

    if isinstance(payload, dict):
        for key in ["locos", "data", "items"]:
            if isinstance(payload.get(key), list):
                return len(payload[key])

    return 0


def run_scraper() -> bool:
    scraper_script = os.getenv("SCRAPER_SCRIPT", "").strip()

    if scraper_script:
        candidates = [scraper_script]
    else:
        candidates = ["fast_scraper.py", "update_trains.py"]

    for script in candidates:
        script_path = BASE_DIR / script

        if script_path.exists():
            code = run([sys.executable, script], script, allow_fail=True)

            if code != 0:
                log(f"Scraper returned non-zero code: {code}")
                return False

            return True

    log("No scraper found. Expected fast_scraper.py or update_trains.py")
    return False


def run_database_generator() -> bool:
    generator = os.getenv("DATABASE_GENERATOR_SCRIPT", "railops_loco_database.py").strip()
    generator_path = BASE_DIR / generator

    if not generator_path.exists():
        log(f"Database generator not found: {generator}")
        return False

    code = run([sys.executable, generator], generator, allow_fail=True)

    if code != 0:
        log(f"Database generator returned non-zero code: {code}")
        return False

    return True


def add_database_files() -> None:
    for file_path in DATABASE_FILES:
        path = BASE_DIR / file_path

        if path.exists():
            run(["git", "add", file_path], f"git add {file_path}", allow_fail=True)
        else:
            log(f"Skipping missing file: {file_path}")


def commit_and_push() -> bool:
    repo = os.getenv("GITHUB_REPO", "grahame21/railops-backend").strip()
    branch = os.getenv("GITHUB_BRANCH", "main").strip()

    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=BASE_DIR,
    )

    if status.returncode == 0:
        log("No database changes to commit.")
        return True

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = os.getenv("GIT_COMMIT_MESSAGE", f"Update RailOps database files - {timestamp}")

    commit_code = run(["git", "commit", "-m", message], "git commit", allow_fail=True)

    if commit_code != 0:
        log("Git commit failed.")
        return False

    run(["git", "pull", "--rebase", "origin", branch], "git pull before push", allow_fail=True)

    push_code = run(["git", "push", "origin", branch], f"git push {repo} {branch}", allow_fail=True)

    if push_code != 0:
        log("Git push failed.")
        return False

    return True


def show_file_summary() -> None:
    log("")
    log("=== GENERATED FILE SUMMARY ===")

    for file_path in DATABASE_FILES:
        path = BASE_DIR / file_path

        if path.exists():
            log(f"{file_path} - {path.stat().st_size} bytes")
        else:
            log(f"{file_path} - missing")

    log(f"Current trains.json train count: {get_train_count()}")
    log(f"Current locos.json loco count: {get_loco_count()}")


def main() -> int:
    start = time.time()

    log("=== RAILOPS RAILWAY ALL-IN-ONE CRON START ===")
    log("UTC: " + datetime.now(timezone.utc).isoformat())

    git_config()

    git_ready = setup_github_auth()

    if not git_ready:
        log("GitHub auth is not ready. Stopping without crash.")
        return 0

    old_train_count = get_train_count()
    old_loco_count = get_loco_count()

    log(f"Before scrape trains count: {old_train_count}")
    log(f"Before scrape locos count: {old_loco_count}")

    scraper_ok = run_scraper()

    new_train_count = get_train_count()

    log(f"After scrape trains count: {new_train_count}")

    if not scraper_ok:
        log("Scraper failed. Not rebuilding database. Not committing. Exiting cleanly.")
        return 0

    if new_train_count <= 0:
        log("Scraper produced 0 trains. Not rebuilding database. Not committing. Exiting cleanly.")
        return 0

    minimum_train_count = int(os.getenv("MIN_TRAIN_COUNT_TO_ACCEPT", "100"))

    if new_train_count < minimum_train_count:
        log(
            f"Scraper produced only {new_train_count} trains, below minimum "
            f"{minimum_train_count}. Not rebuilding database. Not committing."
        )
        return 0

    generator_ok = run_database_generator()

    if not generator_ok:
        log("Database generator failed. Not committing. Exiting cleanly.")
        return 0

    final_loco_count = get_loco_count()

    log(f"After database generation locos count: {final_loco_count}")

    if old_loco_count > 0 and final_loco_count < old_loco_count:
        allow_smaller = os.getenv("ALLOW_SMALLER_LOCO_DATABASE", "false").lower() == "true"

        if not allow_smaller:
            log(
                f"WARNING: New loco database is smaller: {final_loco_count} < {old_loco_count}. "
                "Not committing to GitHub."
            )
            return 0

    show_file_summary()

    add_database_files()
    commit_and_push()

    elapsed = round(time.time() - start, 2)
    log(f"=== RAILOPS RAILWAY ALL-IN-ONE CRON DONE in {elapsed}s ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())