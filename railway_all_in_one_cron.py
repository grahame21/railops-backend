import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
WORK_DIR = Path("/tmp/railops-work")


DATABASE_FILES = [
    "trains.json",
    "live_trains.json",

    # Locomotive database files
    "locos.json",
    "locos_master.json",
    "loco_history.json",
    "loco_export.csv",
    "loco_summary.txt",
    "blocklist.json",
    "static/downloads/loco_database.html",
    "static/downloads/recently_added.html",
    "static/downloads/loco_numbers_only.html",
    "static/downloads/loco_database.xlsx",
    "static/downloads/loco_numbers_only.xlsx",

    # V/Line regional passenger service database files
    "vline_services.json",
    "vline_services.csv",
    "static/downloads/vline_services.html",
]


def log(message: str) -> None:
    print(message, flush=True)


def run(
    command: list[str],
    label: str,
    cwd: Path,
    allow_fail: bool = False,
    show_command: bool = True,
) -> int:
    log("")
    log(f"=== RUNNING {label} ===")

    if show_command:
        log("Command: " + " ".join(command))
    else:
        log("Command: [hidden/redacted]")

    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
    )

    log(f"=== FINISHED {label} with code {result.returncode} ===")

    if result.returncode != 0 and not allow_fail:
        raise RuntimeError(f"{label} failed with code {result.returncode}")

    return result.returncode


def clone_repo() -> Path:
    token = os.getenv("GITHUB_TOKEN_PUSH", "").strip()
    repo = os.getenv("GITHUB_REPO", "grahame21/railops-backend").strip()
    branch = os.getenv("GITHUB_BRANCH", "main").strip()

    if not token:
        raise RuntimeError("Missing Railway variable GITHUB_TOKEN_PUSH")

    if repo.endswith(".git"):
        repo = repo[:-4]

    if "/" not in repo:
        raise RuntimeError(f"GITHUB_REPO looks wrong: {repo}")

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)

    authed_url = f"https://x-access-token:{token}@github.com/{repo}.git"

    log("")
    log("=== CLONING GITHUB REPO ===")
    log(f"Repo: {repo}")
    log(f"Branch: {branch}")
    log("Token: [hidden]")

    clone_result = subprocess.run(
        ["git", "clone", "--branch", branch, "--depth", "1", authed_url, str(WORK_DIR)],
        cwd=Path("/tmp"),
        text=True,
    )

    if clone_result.returncode != 0:
        raise RuntimeError(
            "git clone failed. Check GITHUB_TOKEN_PUSH, GITHUB_REPO, branch name, and repo token permissions."
        )

    if not (WORK_DIR / ".git").exists():
        raise RuntimeError("Clone finished but .git folder is missing.")

    return WORK_DIR


def git_config(repo_dir: Path) -> None:
    name = os.getenv("GIT_COMMIT_NAME", "RailOps Railway Bot")
    email = os.getenv("GIT_COMMIT_EMAIL", "railops-bot@users.noreply.github.com")

    run(["git", "config", "user.name", name], "git config user.name", cwd=repo_dir)
    run(["git", "config", "user.email", email], "git config user.email", cwd=repo_dir)


def load_json_file(path: Path):
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def count_records(path: Path, possible_keys: list[str]) -> int:
    payload = load_json_file(path)

    if isinstance(payload, list):
        return len(payload)

    if isinstance(payload, dict):
        for key in possible_keys:
            if isinstance(payload.get(key), list):
                return len(payload[key])

    return 0


def get_train_count(repo_dir: Path) -> int:
    return count_records(
        repo_dir / "trains.json",
        ["trains", "data", "items", "features"],
    )


def get_loco_count(repo_dir: Path) -> int:
    return count_records(
        repo_dir / "locos.json",
        ["locos", "data", "items"],
    )


def get_vline_count(repo_dir: Path) -> int:
    return count_records(
        repo_dir / "vline_services.json",
        ["services", "vline_services", "data", "items"],
    )


def run_scraper(repo_dir: Path) -> bool:
    scraper_script = os.getenv("SCRAPER_SCRIPT", "").strip()

    if scraper_script:
        candidates = [scraper_script]
    else:
        candidates = ["fast_scraper.py", "update_trains.py"]

    for script in candidates:
        script_path = repo_dir / script

        if script_path.exists():
            code = run(
                [sys.executable, script],
                script,
                cwd=repo_dir,
                allow_fail=True,
            )

            if code != 0:
                log(f"Scraper returned non-zero code: {code}")
                return False

            return True

    log("No scraper found. Expected fast_scraper.py or update_trains.py")
    return False


def run_vline_generator(repo_dir: Path) -> bool:
    """
    Builds the separate V/Line regional passenger service database before
    the loco database applies its blocklist.

    This lets VLINE* be blocked from locos.json while still being saved into:
    - vline_services.json
    - vline_services.csv
    - static/downloads/vline_services.html
    """
    generator = os.getenv("VLINE_GENERATOR_SCRIPT", "vline_database.py").strip()
    generator_path = repo_dir / generator

    if not generator_path.exists():
        log(f"V/Line database generator not found: {generator}. Skipping V/Line database.")
        return True

    code = run(
        [sys.executable, generator],
        generator,
        cwd=repo_dir,
        allow_fail=True,
    )

    if code != 0:
        log(f"V/Line database generator returned non-zero code: {code}")
        return False

    return True


def run_database_generator(repo_dir: Path) -> bool:
    generator = os.getenv("DATABASE_GENERATOR_SCRIPT", "railops_loco_database.py").strip()
    generator_path = repo_dir / generator

    if not generator_path.exists():
        log(f"Database generator not found: {generator}")
        return False

    code = run(
        [sys.executable, generator],
        generator,
        cwd=repo_dir,
        allow_fail=True,
    )

    if code != 0:
        log(f"Database generator returned non-zero code: {code}")
        return False

    return True


def show_file_summary(repo_dir: Path) -> None:
    log("")
    log("=== GENERATED FILE SUMMARY ===")

    for file_path in DATABASE_FILES:
        path = repo_dir / file_path

        if path.exists():
            log(f"{file_path} - {path.stat().st_size} bytes")
        else:
            log(f"{file_path} - missing")

    log(f"Current trains.json train count: {get_train_count(repo_dir)}")
    log(f"Current locos.json loco count: {get_loco_count(repo_dir)}")
    log(f"Current vline_services.json service count: {get_vline_count(repo_dir)}")


def add_database_files(repo_dir: Path) -> None:
    """
    Force-add generated database files even if .gitignore ignores static/downloads,
    xlsx files, csv files, or generated outputs.
    """
    for file_path in DATABASE_FILES:
        path = repo_dir / file_path

        if path.exists():
            run(
                ["git", "add", "-f", file_path],
                f"git add -f {file_path}",
                cwd=repo_dir,
                allow_fail=True,
            )
        else:
            log(f"Skipping missing file: {file_path}")


def commit_and_push(repo_dir: Path) -> bool:
    branch = os.getenv("GITHUB_BRANCH", "main").strip()

    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_dir,
    )

    if status.returncode == 0:
        log("No database changes to commit.")
        return True

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = os.getenv("GIT_COMMIT_MESSAGE", f"Update RailOps database files - {timestamp}")

    commit_code = run(
        ["git", "commit", "-m", message],
        "git commit",
        cwd=repo_dir,
        allow_fail=True,
    )

    if commit_code != 0:
        log("Git commit failed.")
        return False

    push_code = run(
        ["git", "push", "origin", branch],
        f"git push origin {branch}",
        cwd=repo_dir,
        allow_fail=True,
    )

    if push_code != 0:
        log("Git push failed.")
        return False

    return True


def main() -> int:
    start = time.time()

    log("=== RAILOPS RAILWAY ALL-IN-ONE CRON START ===")
    log("UTC: " + datetime.now(timezone.utc).isoformat())

    repo_dir = clone_repo()
    git_config(repo_dir)

    old_train_count = get_train_count(repo_dir)
    old_loco_count = get_loco_count(repo_dir)
    old_vline_count = get_vline_count(repo_dir)

    log(f"Before scrape trains count: {old_train_count}")
    log(f"Before scrape locos count: {old_loco_count}")
    log(f"Before scrape V/Line services count: {old_vline_count}")

    scraper_ok = run_scraper(repo_dir)

    new_train_count = get_train_count(repo_dir)

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

    vline_ok = run_vline_generator(repo_dir)

    if not vline_ok:
        log("V/Line database generator failed. Not committing. Exiting cleanly.")
        return 0

    generator_ok = run_database_generator(repo_dir)

    if not generator_ok:
        log("Database generator failed. Not committing. Exiting cleanly.")
        return 0

    final_loco_count = get_loco_count(repo_dir)
    final_vline_count = get_vline_count(repo_dir)

    log(f"After database generation locos count: {final_loco_count}")
    log(f"After V/Line database generation services count: {final_vline_count}")

    if old_loco_count > 0 and final_loco_count < old_loco_count:
        allow_smaller = os.getenv("ALLOW_SMALLER_LOCO_DATABASE", "false").lower() == "true"

        if not allow_smaller:
            log(
                f"WARNING: New loco database is smaller: {final_loco_count} < {old_loco_count}. "
                "Not committing to GitHub."
            )
            return 0

    show_file_summary(repo_dir)

    add_database_files(repo_dir)

    commit_ok = commit_and_push(repo_dir)

    elapsed = round(time.time() - start, 2)

    if commit_ok:
        log(f"=== RAILOPS RAILWAY ALL-IN-ONE CRON DONE in {elapsed}s ===")
    else:
        log(f"=== RAILOPS RAILWAY ALL-IN-ONE CRON FINISHED WITH COMMIT/PUSH ISSUE in {elapsed}s ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
