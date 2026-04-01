from trainfinder_backend import ensure_session, make_driver, save_cookies

if __name__ == "__main__":
    driver = make_driver(headless=True)
    try:
        ok, note = ensure_session(driver)
        save_cookies(driver)
        if ok:
            print(f"✅ Cookie/session refreshed: {note}")
        else:
            print(f"❌ Could not refresh cookie/session: {note}")
            raise SystemExit(1)
    finally:
        driver.quit()
