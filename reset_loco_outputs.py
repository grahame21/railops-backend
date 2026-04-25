import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "static" / "downloads"

FILES_TO_DELETE = [
    BASE_DIR / "locos.json",
    BASE_DIR / "loco_history.json",
    BASE_DIR / "loco_export.csv",
    BASE_DIR / "loco_summary.txt",
    BASE_DIR / "debug_sources.json",
    BASE_DIR / "trains.json",
    DOWNLOADS_DIR / "loco_database.html",
    DOWNLOADS_DIR / "recently_added.html",
    DOWNLOADS_DIR / "loco_numbers_only.html",
    DOWNLOADS_DIR / "loco_database.xlsx",
    DOWNLOADS_DIR / "loco_numbers_only.xlsx",
]

def main():
    print("=== RESET LOCO OUTPUTS START ===", flush=True)

    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    deleted = 0
    for path in FILES_TO_DELETE:
        try:
            if path.exists():
                path.unlink()
                print(f"Deleted: {path}", flush=True)
                deleted += 1
            else:
                print(f"Not found, skipped: {path}", flush=True)
        except Exception as exc:
            print(f"Failed deleting {path}: {exc}", flush=True)

    (BASE_DIR / "locos.json").write_text("{}\n", encoding="utf-8")
    (BASE_DIR / "loco_history.json").write_text('{"locos": {}, "updates": []}\n', encoding="utf-8")
    (BASE_DIR / "loco_export.csv").write_text("", encoding="utf-8")
    (BASE_DIR / "loco_summary.txt").write_text("Fresh reset completed.\n", encoding="utf-8")

    print(f"Reset complete. Deleted {deleted} existing files.", flush=True)
    print("=== RESET LOCO OUTPUTS COMPLETE ===", flush=True)

if __name__ == "__main__":
    main()
