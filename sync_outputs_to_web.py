import base64
import json
import os
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "static" / "downloads"

PUSH_FILES_URL = os.environ.get(
    "PUSH_FILES_URL",
    "https://railops-backend-web-production.up.railway.app/push_files"
).strip()
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "").strip()

FILES_TO_PUSH = [
    ("locos.json", BASE_DIR / "locos.json"),
    ("loco_history.json", BASE_DIR / "loco_history.json"),
    ("loco_export.csv", BASE_DIR / "loco_export.csv"),
    ("loco_summary.txt", BASE_DIR / "loco_summary.txt"),
    ("downloads/loco_database.html", DOWNLOADS_DIR / "loco_database.html"),
    ("downloads/recently_added.html", DOWNLOADS_DIR / "recently_added.html"),
    ("downloads/loco_numbers_only.html", DOWNLOADS_DIR / "loco_numbers_only.html"),
    ("downloads/loco_database.xlsx", DOWNLOADS_DIR / "loco_database.xlsx"),
    ("downloads/loco_numbers_only.xlsx", DOWNLOADS_DIR / "loco_numbers_only.xlsx"),
]


def main():
    if not PUSH_FILES_URL or not PUSH_TOKEN:
        print("⚠️ PUSH_FILES_URL or PUSH_TOKEN missing; skipping file sync", flush=True)
        return

    files_payload = []

    for relative_path, local_path in FILES_TO_PUSH:
        if not local_path.exists():
            print(f"⚠️ Missing, skipping: {local_path}", flush=True)
            continue

        raw = local_path.read_bytes()
        files_payload.append(
            {
                "path": relative_path,
                "content_base64": base64.b64encode(raw).decode("utf-8"),
            }
        )
        print(f"Prepared for sync: {relative_path} ({len(raw)} bytes)", flush=True)

    if not files_payload:
        print("⚠️ No files found to sync", flush=True)
        return

    payload = {"files": files_payload}

    response = requests.post(
        PUSH_FILES_URL,
        headers={
            "Content-Type": "application/json",
            "X-Auth-Token": PUSH_TOKEN,
        },
        data=json.dumps(payload),
        timeout=180,
    )

    print(f"📤 Push files status: HTTP {response.status_code}", flush=True)
    print(f"📤 Push files response: {response.text[:1000]}", flush=True)

    response.raise_for_status()


if __name__ == "__main__":
    main()
