from trainfinder_backend import (
    ensure_session,
    scrape_trains_from_endpoint,
    write_trains_json,
    write_debug_json,
)


def main():
    driver, ok, msg = ensure_session(headless=True)
    print(msg)

    try:
        if not ok:
            raise RuntimeError(msg)

        trains, debug = scrape_trains_from_endpoint(driver)
        write_debug_json(debug, out_file="debug_sources.json")

        print(f"debug method: {debug.get('method')}")
        print(f"debug requests: {len(debug.get('requests', []))}")
        print(f"debug total trains found: {debug.get('total_trains_found', 0)}")

        for i, req in enumerate(debug.get("requests", [])[:20], start=1):
            print(
                f"request {i}: parsed={req.get('parsed')} "
                f"new_trains_found={req.get('new_trains_found')} "
                f"keys={req.get('dict_keys', [])[:10]}"
            )

        result = write_trains_json(
            trains,
            out_file="trains.json",
            note="ok",
            preserve_existing_if_empty=True,
        )
        print(result["note"])
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
