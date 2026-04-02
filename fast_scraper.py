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

        print(f"debug method: {debug.get('method')}")
        print(f"debug hasMap: {debug.get('hasMap')}")
        print(f"debug hasOl: {debug.get('hasOl')}")
        print(f"debug raw_count: {debug.get('raw_count')}")
        print(f"debug au_count: {debug.get('au_count')}")

        for source in debug.get("sources_found", []):
            print(
                f"source {source.get('name')}: "
                f"exists={source.get('exists')} count={source.get('count')}"
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
