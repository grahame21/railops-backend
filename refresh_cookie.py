from trainfinder_backend import ensure_session, save_cookies


def main():
    driver, ok, msg = ensure_session(headless=True)
    print(msg)

    try:
        if not ok:
            raise RuntimeError(msg)

        save_cookies(driver)
        print("Cookie refresh complete")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
