import os
import json
import time
import math
import pickle
import random
import datetime
import signal

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By


OUT_FILE = os.environ.get("OUT_FILE", "trains.json")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "trainfinder_cookies.pkl")
TF_LOGIN_URL = os.environ.get("TF_LOGIN_URL", "https://trainfinder.otenko.com/home/nextlevel")

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

BASE_MIN_SECONDS = int(os.environ.get("BASE_MIN_SECONDS", "15"))
BASE_MAX_SECONDS = int(os.environ.get("BASE_MAX_SECONDS", "30"))

MIN_TRAINS_OK = int(os.environ.get("MIN_TRAINS_OK", "10"))  # XHR may return smaller/variable sets

MAX_BACKOFF_SECONDS = int(os.environ.get("MAX_BACKOFF_SECONDS", "120"))
INITIAL_BACKOFF_SECONDS = int(os.environ.get("INITIAL_BACKOFF_SECONDS", "15"))
BACKOFF_MULTIPLIER = float(os.environ.get("BACKOFF_MULTIPLIER", "1.6"))

PUSH_URL = os.environ.get("PUSH_URL", "https://railops-live-au.fly.dev/push")
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "").strip()

PUBLIC_TRAINS_JSON_URL = os.environ.get("PUBLIC_TRAINS_JSON_URL", "https://railops-live-au.fly.dev/trains.json")

CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")

STOP = False


def handle_stop(sig, frame):
    global STOP
    STOP = True


signal.signal(signal.SIGINT, handle_stop)
signal.signal(signal.SIGTERM, handle_stop)


def utc_now_z():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def build_payload(trains, note):
    return {"lastUpdated": utc_now_z(), "note": note, "trains": trains or []}


def write_local(payload):
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def push_to_web(payload):
    if not PUSH_URL or not PUSH_TOKEN:
        print("⚠️ PUSH_URL / PUSH_TOKEN not set (skipping push)")
        return False
    try:
        r = requests.post(
            PUSH_URL,
            json=payload,
            headers={"X-Auth-Token": PUSH_TOKEN},
            timeout=20,
        )
        if 200 <= r.status_code < 300:
            return True
        print(f"⚠️ Push failed: HTTP {r.status_code} {r.text[:200]}")
        return False
    except Exception:
        print("⚠️ Push exception")
        return False


def webmercator_to_latlon(x, y):
    try:
        x = float(x)
        y = float(y)

        # WebMercator meters heuristic
        if abs(x) > 1000 and abs(y) > 1000:
            lon = (x / 20037508.34) * 180.0
            lat = (y / 20037508.34) * 180.0
            lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
            return round(lat, 6), round(lon, 6)

        # lon/lat degrees fallback
        if -180 <= x <= 180 and -90 <= y <= 90:
            return round(y, 6), round(x, 6)

        return None, None
    except Exception:
        return None, None


def load_seed_trains():
    try:
        if os.path.exists(OUT_FILE):
            with open(OUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            trains = data.get("trains") or []
            if isinstance(trains, list) and trains:
                print(f"✅ Seeded last-good trains from local {OUT_FILE}: {len(trains)} trains")
                return trains
    except Exception:
        pass

    try:
        r = requests.get(PUBLIC_TRAINS_JSON_URL, timeout=10, headers={"Cache-Control": "no-cache"})
        if r.ok:
            data = r.json()
            trains = data.get("trains") or []
            if isinstance(trains, list) and trains:
                print(f"✅ Seeded last-good trains from {PUBLIC_TRAINS_JSON_URL}: {len(trains)} trains")
                return trains
    except Exception:
        pass

    print("ℹ️ No seed trains available yet")
    return []


def make_driver():
    chrome_options = Options()
    chrome_options.binary_location = CHROME_BIN

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=en-AU")

    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    service = webdriver.ChromeService(executable_path=CHROMEDRIVER_BIN)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.set_page_load_timeout(180)
    driver.set_script_timeout(120)

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
    except Exception:
        pass

    return driver


def safe_get(driver, url):
    try:
        driver.get(url)
        return True
    except TimeoutException:
        print("⚠️ Page load timeout on GET — stopping load and continuing")
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        return False


def safe_refresh(driver):
    try:
        driver.refresh()
        return True
    except TimeoutException:
        print("⚠️ Page load timeout on REFRESH — stopping load and continuing")
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        return False


def close_warning(driver):
    try:
        driver.execute_script(
            """
            var paths = document.getElementsByTagName('path');
            for(var i = 0; i < paths.length; i++) {
                var d = paths[i].getAttribute('d') || '';
                if(d.includes('M13.7,11l6.1-6.1')) {
                    var parent = paths[i].parentElement;
                    while(parent && parent.tagName !== 'BUTTON' && parent.tagName !== 'DIV' && parent.tagName !== 'A') {
                        parent = parent.parentElement;
                    }
                    if(parent) parent.click();
                }
            }
            """
        )
        print("✅ Warning close attempted")
    except Exception:
        pass


def element_visible(el):
    try:
        return el.is_displayed() and el.is_enabled()
    except Exception:
        return False


def find_username_field(driver):
    candidates = []
    try:
        candidates += driver.find_elements(By.CSS_SELECTOR, "input[type='email']")
        candidates += driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
    except Exception:
        pass

    scored = []
    for el in candidates:
        try:
            if not element_visible(el):
                continue
            attrs = {
                "id": (el.get_attribute("id") or "").lower(),
                "name": (el.get_attribute("name") or "").lower(),
                "placeholder": (el.get_attribute("placeholder") or "").lower(),
                "aria": (el.get_attribute("aria-label") or "").lower(),
            }
            blob = " ".join(attrs.values())
            score = 0
            if "email" in blob:
                score += 5
            if "user" in blob or "username" in blob:
                score += 4
            if "login" in blob:
                score += 2
            if score > 0:
                scored.append((score, el))
        except Exception:
            continue

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    for el in candidates:
        if element_visible(el):
            return el

    return None


def find_password_field(driver):
    try:
        els = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        for el in els:
            if element_visible(el):
                return el
    except Exception:
        pass
    return None


def click_login_button(driver):
    selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button",
        "input[type='button']",
        "div.button-green",
        "div[class*='button']",
    ]
    for sel in selectors:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for b in btns:
                if not element_visible(b):
                    continue
                txt = (b.get_attribute("value") or b.text or "").strip().lower()
                if any(k in txt for k in ["log in", "login", "sign in", "submit", "continue"]):
                    try:
                        b.click()
                        return True
                    except Exception:
                        continue
        except Exception:
            continue
    return False


def ensure_logged_in(driver):
    safe_get(driver, TF_LOGIN_URL)
    time.sleep(6)

    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "rb") as f:
                cookies = pickle.load(f)
            for c in cookies:
                try:
                    driver.add_cookie(c)
                except Exception:
                    pass
            safe_get(driver, TF_LOGIN_URL)
            time.sleep(5)
            print("✅ Loaded saved cookies")
        except Exception:
            pass

    page_lower = (driver.page_source or "").lower()
    password_inputs = []
    try:
        password_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    except Exception:
        pass

    login_needed = ("password" in page_lower and ("log in" in page_lower or "login" in page_lower)) or any(
        element_visible(p) for p in password_inputs
    )

    if not login_needed:
        print("✅ Session appears logged-in (no login form detected).")
        close_warning(driver)
        return

    if not TF_USERNAME or not TF_PASSWORD:
        raise RuntimeError("Missing TF_USERNAME / TF_PASSWORD")

    print("🔐 Login form detected — attempting login…")

    user_el = find_username_field(driver)
    pass_el = find_password_field(driver)

    if user_el is None or pass_el is None:
        snippet = (driver.page_source or "")[:2000].replace("\n", " ")
        print("❌ Login fields not found. HTML snippet:", snippet)
        raise RuntimeError("Could not find login fields")

    try:
        user_el.clear()
    except Exception:
        pass
    user_el.send_keys(TF_USERNAME)

    try:
        pass_el.clear()
    except Exception:
        pass
    pass_el.send_keys(TF_PASSWORD)

    clicked = click_login_button(driver)
    if not clicked:
        try:
            pass_el.send_keys("\n")
        except Exception:
            pass

    time.sleep(10)

    try:
        with open(COOKIE_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print("✅ Cookies saved")
    except Exception:
        pass

    close_warning(driver)


# --- XHR capture + replay ------------------------------------------------------

HOOK_XHR_JS = r"""
try {
  window.__railops = window.__railops || {};
  window.__railops.last = null;

  // Hook fetch
  if (!window.__railops._fetchHooked) {
    window.__railops._fetchHooked = true;
    const origFetch = window.fetch;
    window.fetch = function() {
      try {
        const url = arguments[0];
        const opts = arguments[1] || {};
        if (String(url).includes('GetViewPortData')) {
          window.__railops.last = {
            kind: 'fetch',
            url: String(url),
            method: (opts.method || 'GET'),
            body: opts.body || null
          };
        }
      } catch(e) {}
      return origFetch.apply(this, arguments);
    };
  }

  // Hook XHR
  if (!window.__railops._xhrHooked) {
    window.__railops._xhrHooked = true;

    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function(method, url) {
      this.__railops = { method: method, url: url };
      return origOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function(body) {
      try {
        if (this.__railops && String(this.__railops.url).includes('GetViewPortData')) {
          window.__railops.last = {
            kind: 'xhr',
            url: String(this.__railops.url),
            method: String(this.__railops.method || 'POST'),
            body: body || null
          };
        }
      } catch(e) {}
      return origSend.apply(this, arguments);
    };
  }

  return { ok: true };
} catch(e) {
  return { ok: false, err: String(e) };
}
"""

# Make the page trigger viewport data
TRIGGER_VIEWPORT_JS = r"""
try {
  // Try to force the map to request data: zoom/pan nudge
  if (window.map && map.getView) {
    var v = map.getView();
    var z = v.getZoom();
    v.setZoom(z + 0.0001);
    setTimeout(function(){ v.setZoom(z); }, 250);
  } else {
    window.scrollTo(0, 200);
    setTimeout(function(){ window.scrollTo(0, 0); }, 250);
  }
  return true;
} catch(e) { return false; }
"""

def capture_viewport_request(driver, timeout_s=90):
    print("🪝 Installing XHR hooks…")
    driver.execute_script(HOOK_XHR_JS)

    end = time.time() + timeout_s
    while time.time() < end:
        try:
            driver.execute_script(TRIGGER_VIEWPORT_JS)
            time.sleep(1.2)
            last = driver.execute_script("return (window.__railops && window.__railops.last) ? window.__railops.last : null;")
            if isinstance(last, dict) and last.get("url") and "GetViewPortData" in last.get("url", ""):
                print(f"✅ Captured GetViewPortData request: {last.get('method')} {last.get('url')}")
                body_preview = last.get("body")
                if body_preview:
                    s = str(body_preview)
                    print(f"✅ Captured body length: {len(s)}")
                else:
                    print("⚠️ Captured request has no body (GET?) — still usable")
                return last
        except Exception:
            pass

    print("❌ Failed to capture GetViewPortData request within timeout")
    return None


def fetch_viewport_data(driver, req):
    """
    Replays the captured GetViewPortData request INSIDE the page context,
    so session/cookies are automatically applied.
    """
    url = req.get("url")
    method = (req.get("method") or "POST").upper()
    body = req.get("body")

    # Build absolute URL if needed
    if url.startswith("/"):
        url = "https://trainfinder.otenko.com" + url

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }

    script = """
    const cb = arguments[arguments.length - 1];
    const url = arguments[0];
    const method = arguments[1];
    const headers = arguments[2];
    const body = arguments[3];

    fetch(url, {
      method: method,
      headers: headers,
      body: body,
      credentials: 'include'
    }).then(r => r.text())
      .then(t => cb({ok:true, text:t}))
      .catch(e => cb({ok:false, err:String(e)}));
    """
    try:
        res = driver.execute_async_script(script, url, method, headers, body)
        return res
    except Exception as e:
        return {"ok": False, "err": f"{type(e).__name__}"}


def deep_find_points(obj, found):
    """
    Recursively finds dict-like items containing coordinates.
    Accepts x/y or lon/lat keys (various spellings).
    """
    if obj is None:
        return
    if isinstance(obj, dict):
        keys = {k.lower(): k for k in obj.keys()}
        # Possible coordinate keys
        xk = keys.get("x") or keys.get("lon") or keys.get("longitude")
        yk = keys.get("y") or keys.get("lat") or keys.get("latitude")
        if xk and yk:
            found.append(obj)

        for v in obj.values():
            deep_find_points(v, found)
    elif isinstance(obj, list):
        for v in obj:
            deep_find_points(v, found)


def normalize_candidates(cands):
    trains = []
    for t in cands:
        # Try many possible coordinate key names
        x = t.get("x", t.get("lon", t.get("longitude")))
        y = t.get("y", t.get("lat", t.get("latitude")))
        lat, lon = webmercator_to_latlon(x, y)
        if lat is None or lon is None:
            continue
        if not (-45 <= lat <= -9 and 110 <= lon <= 155):
            continue

        # Pull likely train keys, but keep it tolerant
        train = {
            "id": t.get("id") or t.get("ID") or t.get("trKey") or t.get("key") or "",
            "train_number": t.get("train_number") or t.get("trainNumber") or t.get("trainNo") or t.get("train") or "",
            "train_name": t.get("train_name") or t.get("trainName") or t.get("name") or "",
            "loco": t.get("loco") or t.get("Loco") or t.get("locomotive") or "",
            "origin": t.get("origin") or t.get("serviceFrom") or t.get("from") or "",
            "destination": t.get("destination") or t.get("serviceTo") or t.get("to") or "",
            "speed": t.get("speed") or 0,
            "heading": t.get("heading") or 0,
            "description": t.get("description") or t.get("serviceDesc") or "",
            "trKey": t.get("trKey") or "",
            "cId": t.get("cId") or "",
            "servId": t.get("servId") or "",
            "lat": lat,
            "lon": lon,
        }

        # If speed appears as "trainSpeed": "88 km/h"
        if not train["speed"] and t.get("trainSpeed"):
            s = str(t.get("trainSpeed"))
            digits = "".join([ch for ch in s if ch.isdigit()])
            if digits:
                try:
                    train["speed"] = int(digits)
                except Exception:
                    pass

        trains.append(train)

    # Dedup by (lat,lon,id-ish) to avoid repeats from nested objects
    seen = set()
    out = []
    for tr in trains:
        key = (round(tr["lat"], 5), round(tr["lon"], 5), tr.get("id") or tr.get("train_number") or tr.get("trKey") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(tr)
    return out


def next_backoff(current):
    if current <= 0:
        return min(MAX_BACKOFF_SECONDS, max(1, INITIAL_BACKOFF_SECONDS))
    grown = int(max(current + 1, current * BACKOFF_MULTIPLIER))
    return min(MAX_BACKOFF_SECONDS, max(1, grown))


def main():
    if not TF_USERNAME or not TF_PASSWORD:
        raise RuntimeError("Missing TF_USERNAME/TF_PASSWORD (Fly secrets)")

    print("=" * 60)
    print("🚂 RAILOPS - FAST WORKER (GetViewPortData replay)")
    print("=" * 60)

    backoff = 0
    consecutive_failures = 0
    driver = None

    last_good_trains = load_seed_trains()
    last_good_note = "Seeded from previous trains.json" if last_good_trains else "No good data yet"

    try:
        driver = make_driver()
        ensure_logged_in(driver)

        print("⏳ Warmup: waiting 20s for map page JS…")
        time.sleep(20)

        # Capture the live request body TrainFinder uses
        req = capture_viewport_request(driver, timeout_s=120)
        if not req:
            raise RuntimeError("Could not capture GetViewPortData request")

        print("🚦 Worker loop started")

        while not STOP:
            try:
                res = fetch_viewport_data(driver, req)
                if not isinstance(res, dict) or not res.get("ok"):
                    raise RuntimeError(f"Viewport fetch failed: {res.get('err')}")

                text = res.get("text") or ""
                try:
                    data = json.loads(text)
                except Exception:
                    # Sometimes servers return HTML on auth errors
                    if "<html" in text.lower():
                        raise RuntimeError("Non-JSON response (likely logged out)")
                    raise

                candidates = []
                deep_find_points(data, candidates)
                print(f"🔎 Candidate point objects found: {len(candidates)}")

                trains = normalize_candidates(candidates)
                print(f"🚂 Normalized train count: {len(trains)}")

                if len(trains) < MIN_TRAINS_OK:
                    backoff = next_backoff(backoff)

                    payload = build_payload(
                        last_good_trains,
                        f"Low train count ({len(trains)}). Keeping last good. Retry in {backoff}s | prev: {last_good_note}"
                    )

                    # If we got some trains, accept them as last-good
                    if trains:
                        last_good_trains = trains
                        last_good_note = f"Low but usable ({len(trains)})"

                    write_local(payload)
                    push_to_web(payload)
                    print(f"📝 Output: {len(payload.get('trains') or [])} trains | LOW -> backoff {backoff}s")

                    time.sleep(backoff)
                    continue

                backoff = 0
                consecutive_failures = 0

                payload = build_payload(trains, "OK")
                last_good_trains = trains
                last_good_note = payload["note"]

                write_local(payload)
                push_to_web(payload)
                print(f"📝 Output: {len(trains)} trains | OK")

                time.sleep(random.randint(BASE_MIN_SECONDS, BASE_MAX_SECONDS))

            except Exception as e:
                consecutive_failures += 1
                backoff = next_backoff(backoff)

                payload = build_payload(
                    last_good_trains,
                    f"Error: {type(e).__name__}. Keeping last good. Retry in {backoff}s | prev: {last_good_note}"
                )
                write_local(payload)
                push_to_web(payload)
                print(f"📝 Output: {len(payload.get('trains') or [])} trains | ERROR {type(e).__name__} -> backoff {backoff}s")

                time.sleep(backoff)

                # If it looks like we got logged out, re-login
                if consecutive_failures >= 3:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = make_driver()
                    ensure_logged_in(driver)
                    time.sleep(15)

                    req = capture_viewport_request(driver, timeout_s=120) or req
                    consecutive_failures = 0

        payload = build_payload(last_good_trains, "Stopping gracefully (keeping last good)")
        write_local(payload)
        push_to_web(payload)

    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
