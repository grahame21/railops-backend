from trainfinder_backend import (
    ensure_session,
    scrape_trains_from_page,
    write_trains_json,
    write_debug_json,
)


def main():
    driver, ok, msg = ensure_session(headless=True)
    print(msg)

    try:
        if not ok:
            raise RuntimeError(msg)

        trains, debug = scrape_trains_from_page(driver)
        write_debug_json(debug, out_file="debug_sources.json")

        globals_info = debug.get("globals", [])
        nonzero = [
            g for g in globals_info
            if isinstance(g, dict) and (g.get("featureCount") or 0) > 0
        ]

        print(f"debug globals checked: {len(globals_info)}")
        print(f"debug globals with features: {len(nonzero)}")

        for g in nonzero[:20]:
            print(f"source {g.get('name')} -> {g.get('featureCount')} features")

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
