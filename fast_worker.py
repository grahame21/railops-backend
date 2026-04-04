from trainfinder_backend import ensure_session, scrape_trains_from_page, write_trains_json


def main():
    driver, ok, msg = ensure_session(headless=True)
    print(msg)

    try:
        if not ok:
            raise RuntimeError(msg)

        trains = scrape_trains_from_page(driver)
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
