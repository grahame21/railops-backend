from trainfinder_backend import (
    ensure_session,
    scrape_trains_from_page,
    write_trains_json,
    write_debug_json,
)

import time


MAX_ATTEMPTS = 3
WAIT_BETWEEN_ATTEMPTS = 20


def main():
    driver, ok, msg = ensure_session(headless=True)
    print(msg, flush=True)

    try:
        if not ok:
            raise RuntimeError(msg)

        final_trains = []
        final_debug = {}
        got_live_data = False

        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"\n=== SCRAPE ATTEMPT {attempt}/{MAX_ATTEMPTS} ===", flush=True)

            trains, debug = scrape_trains_from_page(driver)
            write_debug_json(debug, out_file="debug_sources.json")

            raw_count = int(debug.get("raw_count") or 0)
            au_count = int(debug.get("au_count") or 0)

            print(f"debug method: {debug.get('method')}", flush=True)
            print(f"debug hasMap: {debug.get('hasMap')}", flush=True)
            print(f"debug hasOl: {debug.get('hasOl')}", flush=True)
            print(f"debug raw_count: {raw_count}", flush=True)
            print(f"debug au_count: {au_count}", flush=True)
            print(f"debug refresh_attempts_used: {debug.get('refresh_attempts_used')}", flush=True)
            print(f"debug poll_attempt: {debug.get('poll_attempt')}", flush=True)

            for source in debug.get("sources_found", []):
                print(
                    f"source {source.get('name')}: "
                    f"exists={source.get('exists')} count={source.get('count')}",
                    flush=True,
                )

            final_trains = trains
            final_debug = debug

            if raw_count > 0 and au_count > 0 and len(trains) > 0:
                got_live_data = True
                print(f"✅ Live data found on attempt {attempt}: {len(trains)} trains", flush=True)
                break

            if attempt < MAX_ATTEMPTS:
                print(
                    f"⚠️ Empty or unusable live data on attempt {attempt}. "
                    f"Waiting {WAIT_BETWEEN_ATTEMPTS}s and retrying whole scrape...",
                    flush=True,
                )
                try:
                    driver.refresh()
                except Exception as exc:
                    print(f"⚠️ Driver refresh failed: {exc}", flush=True)
                time.sleep(WAIT_BETWEEN_ATTEMPTS)

        note = "ok" if got_live_data else "ok - kept previous"
        result = write_trains_json(
            final_trains,
            out_file="trains.json",
            note=note,
            preserve_existing_if_empty=True,
        )

        print(result["note"], flush=True)

        if not got_live_data:
            print("⚠️ No fresh live data found after all attempts. Previous trains file was preserved if available.", flush=True)

    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
