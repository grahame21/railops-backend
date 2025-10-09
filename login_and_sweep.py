# login_and_sweep.py
# -*- coding: utf-8 -*-

import json, os, random, time
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = Path(__file__).parent
OUT_JSON = ROOT / "trains.json"
COOKIE_TXT = ROOT / "cookie.txt"
DBG_DIR = ROOT / "debug"
DBG_DIR.mkdir(exist_ok=True)

TF_BASE = "https://trainfinder.otenko.com"
TF_LOGIN = f"{TF_BASE}/Home/NextLevel"
TF_VIEWPORT = f"{TF_BASE}/Home/GetViewPortData"

USERNAME = os.environ.get("TRAINFINDER_USERNAME", "").strip()
PASSWORD = os.environ.get("TRAINFINDER_PASSWORD", "").strip()


def save_debug(page, name: str):
    """Save screenshot and HTML to debug folder."""
    png = DBG_DIR / f"{name}.png"
    html = DBG_DIR / f"{name}.html"
    try:
        page.screenshot(path=str(png), full_page=True)
    except Exception:
        pass
    try:
        html.write_text(page.content())
    except Exception:
        pass


def write_json_safely(path: Path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)


def default_empty_payload():
    return {
        "favs": None,
        "alerts": None,
        "places": None,
        "tts": None,
        "webcams": None,
        "atcsGomi": None,
        "atcsObj": None,
    }


def robust_login_and_get_cookie(user: str, pwd: str) -> Optional[str]:
    """Headless login, capture cookie, and return session string."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-gpu"])
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()

        # Optional safe console logging (fixed version)
        def on_console(msg):
            try:
                txt_attr = getattr(msg, "text", None)
                txt = txt_attr() if callable(txt_attr) else txt_attr
                typ_attr = getattr(msg, "type", None)
                typ = typ_attr() if callable(typ_attr) else typ_attr
                prev = (DBG_DIR / "console.log").read_text() if (DBG_DIR / "console.log").exists() else ""
                (DBG_DIR / "console.log").write_text(prev + f"[{typ}] {txt}\n")
            except Exception:
                pass

        page.on("console", on_console)

        try:
            print("🌐 Opening TrainFinder…")
            page.goto(TF_LOGIN, wait_until="domcontentloaded", timeout=30000)

            # Fill in credentials using real IDs
            print("✏️ Filling credentials…")
            try:
                page.locator("#useR_name").fill(user, timeout=5000)
            except PWTimeout:
                page.locator("input[type='text']").first.fill(user)

            try:
                page.locator("#pasS_word").fill(pwd, timeout=5000)
            except PWTimeout:
                page.locator("input[type='password']").first.fill(pwd)

            print("🚪 Submitting…")
            submitted = False
            for sel in [
                "div.button.button-green:has-text('Log In')",
                "div.button:has-text('Log In')",
                "text=Log In",
            ]:
                try:
                    page.locator(sel).first.click(timeout=7000)
                    submitted = True
                    break
                except Exception:
                    continue

            if not submitted:
                page.keyboard.press("Enter")

            page.wait_for_timeout(1500)
            save_debug(page, "debug_after_submit")

            cookies = ctx.cookies()
            token = None
            for c in cookies:
                if c.get("name") and ("auth" in c["name"].lower() or "session" in c["name"].lower()):
                    token = f"{c['name']}={c['value']}"
                    break

            jar = "; ".join([f"{c['name']}={c['value']}" for c in cookies if c.get("name")])
            COOKIE_TXT.write_text(jar)
            print("✅ Cookie saved to cookie.txt")

            return token or jar

        finally:
            ctx.close()
            browser.close()


import urllib.request


def fetch_viewport_json(cookie_header: str) -> dict:
    """Fetch live viewport data."""
    req = urllib.request.Request(
        TF_VIEWPORT,
        data=b"",
        method="POST",
        headers={
            "Cookie": cookie_header,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": TF_LOGIN,
            "Origin": TF_BASE,
            "User-Agent": "Mozilla/5.0 (Playwright headless fetch)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"error": raw}


def main():
    if not USERNAME or not PASSWORD:
        print("❌ Missing TRAINFINDER_USERNAME / TRAINFINDER_PASSWORD.")
        write_json_safely(OUT_JSON, default_empty_payload())
        return

    token = robust_login_and_get_cookie(USERNAME, PASSWORD)
    if not token:
        print("❌ Could not obtain cookie after login.")
        write_json_safely(OUT_JSON, default_empty_payload())
        return

    try:
        data = fetch_viewport_json(token)
        if not isinstance(data, dict) or not data:
            data = default_empty_payload()
        write_json_safely(OUT_JSON, data)
        print("✅ trains.json updated")
    except Exception as e:
        print(f"❌ Fetch failed: {e}")
        write_json_safely(OUT_JSON, default_empty_payload())

    jitter = random.randint(30, 90)
    print(f"⏱️ Done. (Wait {jitter}s before next run)")
    time.sleep(jitter)


if __name__ == "__main__":
    main()
