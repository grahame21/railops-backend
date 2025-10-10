def login(page, user: str, pwd: str):
    log("🌐 Opening NextLevel…")
    page.goto(NEXTLEVEL, wait_until="load", timeout=60000)
    page.wait_for_timeout(2000)

    # 1️⃣ Open the login modal
    try:
        page.click("div.nav_btn:has-text('Login')", timeout=3000)
        log("🪟 Login modal opened")
    except Exception as e:
        log(f"⚠️ Could not click Login nav_btn: {e}")

    # 2️⃣ Wait for inputs to appear
    try:
        page.wait_for_selector("input#useR_name", timeout=8000)
        page.wait_for_selector("input#pasS_word", timeout=8000)
        log("🧾 Found username & password inputs")
    except Exception as e:
        dump_debug(page, "debug_login_not_found")
        raise SystemExit("❌ Login fields not found (see debug_login_not_found.html/png)")

    # 3️⃣ Fill credentials
    page.fill("input#useR_name", user)
    page.fill("input#pasS_word", pwd)
    log("✏️ Credentials entered")

    # 4️⃣ Click the green 'Log In' button
    try:
        page.click("div.button.button-green:has-text('Log In')", timeout=5000)
    except Exception:
        page.evaluate("attemptAuthentication();")  # fallback JS call
    log("🚪 Submitted login form")

    # 5️⃣ Wait for auth cookie
    for _ in range(10):
        cookies = page.context.cookies(BASE)
        if any(c.get("name","").lower().startswith(".aspxauth") for c in cookies):
            log("✅ Auth cookie detected")
            break
        time.sleep(1)
    else:
        dump_debug(page, "debug_no_cookie_after_login")
        raise SystemExit("❌ No auth cookie created after login (see debug_no_cookie_after_login.html/png)")

    log(f"⏳ Sleeping {PAUSE_AFTER_LOGIN_SEC}s after login…")
    time.sleep(PAUSE_AFTER_LOGIN_SEC)
