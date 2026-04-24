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
    print(msg)

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

            print(f"debug method: {debug.get('method')}")
            print(f"debug hasMap: {debug.get('hasMap')}")
            print(f"debug hasOl: {debug.get('hasOl')}")
            print(f"debug raw_count: {raw_count}")
            print(f"debug au_count: {au_count}")

            for source in debug.get("sources_found", []):
                print(
                    f"source {source.get('name')}: "
                    f"exists={source.get('exists')} count={source.get('count')}"
                )

            final_trains = trains
            final_debug = debug

            if raw_count > 0 and au_count > 0 and len(trains) > 0:
                got_live_data = True
                print(f"✅ Live data found on attempt {attempt}: {len(trains)} trains")
                break

            if attempt < MAX_ATTEMPTS:
                print(f"⚠️ Empty live data on attempt {attempt}. Waiting {WAIT_BETWEEN_ATTEMPTS}s and retrying...")
                try:
                    driver.refresh()
                except Exception as exc:
                    print(f"⚠️ Refresh failed: {exc}")
                time.sleep(WAIT_BETWEEN_ATTEMPTS)

        note = "ok" if got_live_data else "ok - kept previous"
        result = write_trains_json(
            final_trains,
            out_file="trains.json",
            note=note,
            preserve_existing_if_empty=True,
        )
        print(result["note"])

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
