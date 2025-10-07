# trainfinder_fetch_pw.py
# Headless login to trainfinder.otenko.com and dump live trains -> trains.json
# Usage (locally):  python trainfinder_fetch_pw.py
# In GitHub Actions, add a step that installs playwright + chromium and runs this file.

import os, sys, json, asyncio, re, time
from pathlib import Path

try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout
except ImportError:
    print("❌ Playwright not installed. Run: pip install playwright && python -m playwright install --with-deps chromium")
    sys.exit(1)

HOME_URL = "https://trainfinder.otenko.com/"
FETCH_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

OUT_JSON = Path("trains.json")
DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)

USERNAME = os.getenv("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.getenv("TRAINFINDER_PASSWORD", "").strip()

if not USERNAME or not PASSWORD:
    print("❌ Missing env vars TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD")
    sys.exit(1)

# ---- helper: save debug artifacts
async def dump_debug(page, tag):
    ts = time.strftime("%Y%m%d-%H%M%S")
    png = DEBUG_DIR / f"{ts}_{tag}.png"
    html = DEBUG_DIR / f"{ts}_{tag}.html"
    try:
        await page.screenshot(path=str(png), full_page=True)
    except Exception:
        pass
    try:
        html_text = await page.content()
        html.write_text(html_text, encoding="utf-8")
    except Exception:
        pass

# ---- helper: fill the first selector that exists
async def fill_first(page, selectors, value):
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if await loc.first.count() > 0:
                await loc.first.fill(value)
                return True
        except Exception:
            continue
    return False

# ---- main
async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
        )
        page = await context.new_page()

        try:
            # 1) Open homepage (shows map UI with "LOGIN" link)
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)

            # If a cookie/consent dialog exists, best-effort dismiss
            for text in ["Accept", "Agree", "OK", "I agree"]:
                try:
                    await page.get_by_role("button", name=re.compile(text, re.I)).click(timeout=2000)
                except Exception:
                    pass

            # 2) Open the login panel
            # Try explicit LOGIN link, otherwise fallback to direct /Account/Login if available
            opened = False
            try:
                await page.get_by_text(re.compile(r"\bLOGIN\b", re.I)).first.click(timeout=4000)
                opened = True
            except Exception:
                pass

            if not opened:
                try:
                    await page.goto(HOME_URL + "Account/Login", wait_until="domcontentloaded", timeout=20000)
                    opened = True
                except Exception:
                    pass

            # 3) Fill credentials (selectors resilient to dynamic markup)
            user_sels = [
                "input[placeholder*='User' i]",
                "input[aria-label*='User' i]",
                "input[aria-label*='Username' i]",
                "input[aria-label*='Email' i]",
                "input[name*='User' i]",
                "input[id*='User' i]",
                "input[type='text']"
            ]
            pass_sels = [
                "input[type='password']",
                "input[placeholder*='Pass' i]",
                "input[aria-label*='Pass' i]",
                "input[name*='Pass' i]",
                "input[id*='Pass' i]"
            ]

            # Wait a moment in case the window animates in
            await page.wait_for_timeout(500)

            filled_user = await fill_first(page, user_sels, USERNAME)
            filled_pass = await fill_first(page, pass_sels, PASSWORD)

            if not (filled_user and filled_pass):
                await dump_debug(page, "no-username-or-password-field")
                print("❌ Headless fetch failed: username/password inputs not found")
                await context.close(); await browser.close()
                sys.exit(1)

            # 4) Submit
            clicked = False
            for name in [r"^log ?in$", r"^sign ?in$", r"^submit$", r"^ok$"]:
                try:
                    await page.get_by_role("button", name=re.compile(name, re.I)).first.click(timeout=2500)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                # Fallback: press Enter in password field
                try:
                    await page.keyboard.press("Enter")
                    clicked = True
                except Exception:
                    pass

            # 5) Wait for either an indication of being logged in, or the login window to disappear
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeout:
                pass

            # Heuristic success checks: logout link present OR GetViewPortData returns 200
            logged_in = False
            try:
                # Some UIs show LOGOUT link/button after auth
                if await page.get_by_text(re.compile(r"\bLOGOUT\b", re.I)).count() > 0:
                    logged_in = True
            except Exception:
                pass

            # If not obvious, try the data endpoint directly in the page context
            if not logged_in:
                try:
                    # Will throw if not authorized
                    res = await page.evaluate(
                        """async (url) => {
                            const r = await fetch(url, {method:'POST', headers:{'x-requested-with':'XMLHttpRequest'}});
                            return {ok: r.ok, status: r.status};
                        }""",
                        FETCH_URL
                    )
                    if res and res.get("ok"):
                        logged_in = True
                except Exception:
                    pass

            if not logged_in:
                await dump_debug(page, "login-not-confirmed")
                print("❌ Could not verify login")
                await context.close(); await browser.close()
                sys.exit(1)

            print("✅ Logged in successfully")

            # 6) Fetch trains JSON (same Ajax the site uses)
            data = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url, {method:'POST', headers:{'x-requested-with':'XMLHttpRequest'}});
                    if (!r.ok) return {error: `HTTP ${r.status}`};
                    try { return await r.json(); } catch(e) { return {error:'bad-json'}; }
                }""",
                FETCH_URL
            )

            # 7) Write output
            OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"✅ trains.json updated ({OUT_JSON.resolve()})")

        except Exception as e:
            await dump_debug(page, "unhandled-exception")
            print(f"❌ Unhandled error: {e}")
            sys.exit(1)
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
