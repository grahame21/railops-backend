import subprocess
import sys


def run_step(label, cmd):
    print(f"\n=== {label} ===")
    result = subprocess.run(cmd, shell=False)
    if result.returncode != 0:
        raise SystemExit(f"{label} failed with exit code {result.returncode}")


def main():
    py = sys.executable
    run_step("SCRAPE WEBRAMS", [py, "webrams_scraper.py"])
    run_step("MERGE INTO LIVE TRAINS", [py, "merge_webrams_into_trains.py"])
    print("\nAll done.")


if __name__ == "__main__":
    main()