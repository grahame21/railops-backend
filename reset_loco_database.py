import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ============================================================
# RailOps database reset script
#
# What this does:
# 1. Clones your GitHub backend repo into /tmp
# 2. Resets the locomotive database files
# 3. Commits the reset
# 4. Pushes it back to GitHub
#
# It does NOT reset:
# - trains.json
# - blocklist.json
# - cookie.txt
# - scraper scripts
# ============================================================


GITHUB_TOKEN = (
    os.getenv("GITHUB_TOKEN")
    or os.getenv("GH_TOKEN")
    or os.getenv("RAILOPS_GITHUB_TOKEN")
    or ""
).strip()

GITHUB_REPO = os.getenv("GITHUB_REPO", "grahame21/railops-backend").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()

WORK_DIR = Path(os.getenv("RESET_WORK_DIR", "/tmp/railops-reset-work")).resolve()

RESTART_LOCAL_TEXT = "1/5/2026 00:00 Adelaide time"
RESTART_ISO = "2026-05-01T00:00:00+09:30"

COMMIT_MESSAGE = f"Reset RailOps locomotive database - {RESTART_ISO}"


def redacted(text: str) -> str:
    if GITHUB_TOKEN:
        return text.replace(GITHUB_TOKEN, "[hidden]")
    return text


def run(cmd, cwd=None, allow_fail=False):
    print(f"\n=== RUNNING: {redacted(' '.join(cmd))} ===", flush=True)

    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    output = redacted(result.stdout or "")
    if output.strip():
        print(output, flush=True)

    print(f"=== FINISHED with code {result.returncode} ===", flush=True)

    if result.returncode != 0 and not allow_fail:
        raise SystemExit(result.returncode)

    return result


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"Wrote: {path}", flush=True)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote: {path}", flush=True)


def remove_if_exists(path: Path):
    if path.exists():
        path.unlink()
        print(f"Deleted: {path}", flush=True)
    else:
        print(f"Already missing: {path}", flush=True)


def reset_page(title: str, message: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
*{{box-sizing:border-box}}
html,body{{
  margin:0;
  padding:0;
  background:#071222;
  color:#eaf2ff;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
}}
body{{padding:24px}}
.card{{
  background:linear-gradient(180deg,#102039,#0d1a2f);
  border:1px solid #274569;
  border-radius:22px;
  padding:24px;
  max-width:920px;
  margin:auto;
  box-shadow:0 16px 36px rgba(0,0,0,.25);
}}
h1{{
  margin:0 0 12px;
  font-size:clamp(32px,6vw,56px);
  line-height:1.05;
}}
p{{
  color:#9fb3d3;
  font-size:20px;
  line-height:1.45;
}}
.pill{{
  display:inline-block;
  background:#113f2d;
  border:1px solid #2f8f61;
  border-radius:999px;
  padding:10px 14px;
  margin:6px 6px 6px 0;
  font-weight:800;
}}
</style>
</head>
<body>
<div class="card">
  <h1>{title}</h1>
  <span class="pill">Database reset</span>
  <span class="pill">Restart: {RESTART_LOCAL_TEXT}</span>
  <p>{message}</p>
</div>
</body>
</html>
"""


def clone_repo() -> Path:
    if not GITHUB_TOKEN:
        print("ERROR: Missing GitHub token.", flush=True)
        print("Add Railway variable: GITHUB_TOKEN", flush=True)
        raise SystemExit(1)

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)

    clone_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"

    print("=== CLONING GITHUB REPO ===", flush=True)
    print(f"Repo: {GITHUB_REPO}", flush=True)
    print(f"Branch: {GITHUB_BRANCH}", flush=True)
    print("Token: [hidden]", flush=True)

    run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            GITHUB_BRANCH,
            clone_url,
            str(WORK_DIR),
        ]
    )

    run(["git", "config", "user.name", "RailOps Reset Bot"], cwd=WORK_DIR)
    run(["git", "config", "user.email", "railops-reset@users.noreply.github.com"], cwd=WORK_DIR)

    return WORK_DIR


def reset_files(repo_dir: Path):
    downloads_dir = repo_dir / "static" / "downloads"

    locos_file = repo_dir / "locos.json"
    locos_master_file = repo_dir / "locos_master.json"
    history_file = repo_dir / "loco_history.json"
    export_file = repo_dir / "loco_export.csv"
    summary_file = repo_dir / "loco_summary.txt"

    database_html = downloads_dir / "loco_database.html"
    recently_added_html = downloads_dir / "recently_added.html"
    numbers_only_html = downloads_dir / "loco_numbers_only.html"

    database_xlsx = downloads_dir / "loco_database.xlsx"
    numbers_xlsx = downloads_dir / "loco_numbers_only.xlsx"

    print("\n=== RESETTING DATABASE FILES ===", flush=True)

    # Main database reset
    write_json(locos_file, [])

    # If you later use a master database, this resets it too.
    # If you do not use it, this harmlessly creates an empty master file.
    write_json(locos_master_file, [])

    write_json(
        history_file,
        [
            {
                "generated": RESTART_ISO,
                "source_trains": 0,
                "seen_this_run": 0,
                "existing_before": 0,
                "new_added": 0,
                "final_count": 0,
                "new_loco_numbers": [],
                "note": f"Locomotive database reset. Restart time set to {RESTART_LOCAL_TEXT}."
            }
        ],
    )

    write_text(
        export_file,
        "loco_number,current_operator,vehicle_description,train_id,route,date_time_added,last_seen,lat,lon,source\n",
    )

    write_text(
        summary_file,
        f"""RailOps Loco Database Summary
Generated Local: {RESTART_LOCAL_TEXT}
Generated ISO: {RESTART_ISO}

Database has been reset.

Source trains this run: 0
Locos seen this run: 0
Existing locos before merge: 0
New locos added this run: 0
Final visible/master locos: 0

Storage mode: GitHub committed database files
Rule: Existing locos are kept even if missing from a scrape.
Blocklist file: blocklist.json
""",
    )

    write_text(
        database_html,
        reset_page(
            "RailOps Loco Database",
            "The locomotive database has been reset. The next Railway cron run will rebuild this page from the next good scrape.",
        ),
    )

    write_text(
        recently_added_html,
        reset_page(
            "RailOps Recently Added Locos",
            "No recently added locos yet. The next Railway cron run will rebuild this from the next good scrape.",
        ),
    )

    write_text(
        numbers_only_html,
        reset_page(
            "RailOps Loco Numbers Only",
            "No loco numbers yet. The next Railway cron run will rebuild this from the next good scrape.",
        ),
    )

    # Remove old workbooks so stale downloads do not hang around.
    # Your normal database cron will recreate them on the next successful run.
    remove_if_exists(database_xlsx)
    remove_if_exists(numbers_xlsx)


def commit_and_push(repo_dir: Path):
    print("\n=== COMMITTING RESET TO GITHUB ===", flush=True)

    run(["git", "status", "--short"], cwd=repo_dir, allow_fail=True)

    run(["git", "add", "-A"], cwd=repo_dir)

    diff_result = run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_dir,
        allow_fail=True,
    )

    if diff_result.returncode == 0:
        print("No changes to commit. Database may already be reset.", flush=True)
        return

    run(["git", "commit", "-m", COMMIT_MESSAGE], cwd=repo_dir)

    push_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
    run(["git", "remote", "set-url", "origin", push_url], cwd=repo_dir)
    run(["git", "push", "origin", GITHUB_BRANCH], cwd=repo_dir)

    print("\n=== RESET PUSHED TO GITHUB ===", flush=True)


def main():
    print("=== RAILOPS LOCOMOTIVE DATABASE RESET START ===", flush=True)
    print(f"Restart time: {RESTART_LOCAL_TEXT}", flush=True)
    print(f"Restart ISO: {RESTART_ISO}", flush=True)

    repo_dir = clone_repo()
    reset_files(repo_dir)
    commit_and_push(repo_dir)

    print("\n=== RAILOPS LOCOMOTIVE DATABASE RESET DONE ===", flush=True)
    print("Now change Railway start command back to: python railway_all_in_one_cron.py", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
