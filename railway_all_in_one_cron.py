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

    run(["git", "config", "user.name", name], "git config user.name")
    run(["git", "config", "user.email", email], "git config user.email")


def setup_github_auth() -> None:
    """
    Uses a GitHub fine-grained token stored in Railway variable GITHUB_TOKEN_PUSH.
    The token needs Contents: Read and write access to grahame21/railops-backend.
    """
    token = os.getenv("GITHUB_TOKEN_PUSH", "").strip()
    repo = os.getenv("GITHUB_REPO", "grahame21/railops-backend").strip()
    branch = os.getenv("GITHUB_BRANCH", "main").strip()

    if not token:
        raise RuntimeError("Missing Railway variable GITHUB_TOKEN_PUSH")

    authed_url = f"https://x-access-token:{token}@github.com/{repo}.git"

    run(["git", "remote", "set-url", "origin", authed_url], "set authenticated git remote")
    run(["git", "fetch", "origin", branch], "git fetch")
    run(["git", "checkout", branch], "git checkout branch")
    run(["git", "pull", "--rebase", "origin", branch], "git pull rebase", allow_fail=True)


def run_scraper() -> None:
    """
    Runs your existing scraper.

    It checks SCRAPER_SCRIPT first. If not set, it tries:
    - fast_scraper.py
    - update_trains.py
    """
    scraper_script = os.getenv("SCRAPER_SCRIPT", "").strip()

    if scraper_script:
        candidates = [scraper_script]
    else:
        candidates = ["fast_scraper.py", "update_trains.py"]

    for script in candidates:
        script_path = BASE_DIR / script
        if script_path.exists():
            run([sys.executable, script], script)
            return

    raise RuntimeError("No scraper found. Expected fast_scraper.py or update_trains.py")


def run_database_generator() -> None:
    generator = os.getenv("DATABASE_GENERATOR_SCRIPT", "railops_loco_database.py").strip()
    generator_path = BASE_DIR / generator

    if not generator_path.exists():
        raise RuntimeError(f"Database generator not found: {generator}")

    run([sys.executable, generator], generator)


def add_database_files() -> None:
    for file_path in DATABASE_FILES:
        path = BASE_DIR / file_path
        if path.exists():
            run(["git", "add", file_path], f"git add {file_path}", allow_fail=True)
        else:
            log(f"Skipping missing file: {file_path}")


def commit_and_push() -> None:
    repo = os.getenv("GITHUB_REPO", "grahame21/railops-backend").strip()
    branch = os.getenv("GITHUB_BRANCH", "main").strip()

    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=BASE_DIR,
    )

    if status.returncode == 0:
        log("No database changes to commit.")
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = os.getenv("GIT_COMMIT_MESSAGE", f"Update RailOps database files - {timestamp}")

    run(["git", "commit", "-m", message], "git commit")

    # Rebase once more in case something changed while scraping.
    run(["git", "pull", "--rebase", "origin", branch], "git pull before push", allow_fail=True)

    # If rebase changed the index, attempt to continue safely.
    run(["git", "push", "origin", branch], f"git push {repo} {branch}")


def show_file_summary() -> None:
    log("")
    log("=== GENERATED FILE SUMMARY ===")

    for file_path in DATABASE_FILES:
        path = BASE_DIR / file_path
        if path.exists():
            log(f"{file_path} - {path.stat().st_size} bytes")
        else:
            log(f"{file_path} - missing")


def main() -> int:
    start = time.time()

    log("=== RAILOPS RAILWAY ALL-IN-ONE CRON START ===")
    log("UTC: " + datetime.now(timezone.utc).isoformat())

    git_config()
    setup_github_auth()

    run_scraper()
    run_database_generator()
    show_file_summary()

    add_database_files()
    commit_and_push()

    elapsed = round(time.time() - start, 2)
    log(f"=== RAILOPS RAILWAY ALL-IN-ONE CRON DONE in {elapsed}s ===")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log("")
        log("=== RAILOPS RAILWAY ALL-IN-ONE CRON FAILED ===")
        log(str(exc))
        raise