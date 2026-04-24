import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SCRIPTS = []

if os.environ.get("RESET_OUTPUTS_ONCE", "").strip() == "1":
    SCRIPTS.append("reset_loco_outputs.py")

SCRIPTS.extend([
    "fast_scraper.py",
    "update_locos.py",
    "export_locos_to_excel.py",
    "sync_outputs_to_web.py",
])

def run_step(script_name: str) -> None:
    script_path = BASE_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")

    print(f"\n=== RUNNING {script_name} ===", flush=True)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(f"{script_name} failed with exit code {result.returncode}")

def main() -> None:
    print("=== RAILWAY ALL-IN-ONE START ===", flush=True)

    for script in SCRIPTS:
        run_step(script)

    print("=== RAILWAY ALL-IN-ONE COMPLETE ===", flush=True)

if __name__ == "__main__":
    main()
