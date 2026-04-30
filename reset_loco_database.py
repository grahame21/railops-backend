import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "static" / "downloads"

RESTART_LOCAL = "1/5/2026 00:00 Adelaide time"
RESTART_ISO = "2026-05-01T00:00:00+09:30"

FILES = {
    "locos": BASE_DIR / "locos.json",
    "history": BASE_DIR / "loco_history.json",
    "export": BASE_DIR / "loco_export.csv",
    "summary": BASE_DIR / "loco_summary.txt",
    "database_html": DOWNLOADS_DIR / "loco_database.html",
    "recent_html": DOWNLOADS_DIR / "recently_added.html",
    "numbers_html": DOWNLOADS_DIR / "loco_numbers_only.html",
}

def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

def reset_page(title: str, message: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{margin:0;padding:24px;background:#071222;color:#eaf2ff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}}
.card{{background:#102039;border:1px solid #274569;border-radius:18px;padding:22px;max-width:900px;margin:auto}}
h1{{margin-top:0}}
p{{color:#9fb3d3;font-size:18px;line-height:1.45}}
.pill{{display:inline-block;background:#113f2d;border:1px solid #2f8f61;border-radius:999px;padding:10px 14px;margin:6px 6px 6px 0;font-weight:800}}
</style>
</head>
<body>
<div class="card">
<h1>{title}</h1>
<span class="pill">Database reset</span>
<span class="pill">Restart: {RESTART_LOCAL}</span>
<p>{message}</p>
</div>
</body>
</html>
"""

def main() -> int:
    print("=== RAILOPS LOCO DATABASE RESET START ===")

    write_json(FILES["locos"], [])

    write_json(
        FILES["history"],
        [
            {
                "generated": RESTART_ISO,
                "source_trains": 0,
                "seen_this_run": 0,
                "existing_before": 0,
                "new_added": 0,
                "final_count": 0,
                "new_loco_numbers": [],
                "note": f"Locomotive database reset. Restart time set to {RESTART_LOCAL}."
            }
        ],
    )

    write_text(
        FILES["export"],
        "loco_number,current_operator,vehicle_description,train_id,route,date_time_added,last_seen,lat,lon,source\n",
    )

    write_text(
        FILES["summary"],
        f"""RailOps Loco Database Summary
Generated Local: {RESTART_LOCAL}
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
        FILES["database_html"],
        reset_page(
            "RailOps Loco Database",
            "The locomotive database has been reset. The next Railway cron run will rebuild this page from the next good scrape.",
        ),
    )

    write_text(
        FILES["recent_html"],
        reset_page(
            "RailOps Recently Added Locos",
            "No recently added locos yet. The next Railway cron run will rebuild this from the next good scrape.",
        ),
    )

    write_text(
        FILES["numbers_html"],
        reset_page(
            "RailOps Loco Numbers Only",
            "No loco numbers yet. The next Railway cron run will rebuild this from the next good scrape.",
        ),
    )

    print("Reset files written:")
    for name, path in FILES.items():
        print(f"- {name}: {path}")

    print("=== RAILOPS LOCO DATABASE RESET DONE ===")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
