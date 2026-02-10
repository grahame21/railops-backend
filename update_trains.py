"""
RailOps Backend Scraper - Production Version
Dynamically logs into TrainFinder, handles warning pages, exports cookies properly.
"""
import os
import json
import datetime
import time
import tempfile
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests
from requests.cookies import RequestsCookieJar

# Configuration
OUT_FILE = "trains.json"
TF_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
TF_REFERER = "https://trainfinder.otenko.com/home/nextlevel"

# Credentials from environment
TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

def write_output(trains, note=""):
    """Always write valid JSON output."""
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains or []
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OUTPUT] Wrote {len(trains or [])} trains. Status: {note}")

def extract_list(data):
    """Robust extraction of train data from various JSON structures."""
    if not data:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["trains", "Trains", "markers", "Markers", "features"]:
            if isinstance(data.get(key), list):
                return data[key]
        if data.get("type") == "FeatureCollection":
            return data.get("features", [])
    return []

def to_float(x):
    """Safe float conversion."""
    try:
        return float(x) if x is not None else None
    except (ValueError, TypeError):
        return None

def norm_item(item, i):
    """Normalize train object to consistent format."""
    if not isinstance(item, dict):
        return None
    
    # Handle GeoJSON Feature
    if item.get("type") == "Feature" and item.get("geometry", {}).get("type") == "Point":
        coords = item.get("geometry", {}).get("coordinates", [])
        props = item.get("properties", {})
        return {
            "id": str(props.get("id") or props.get("ID") or props.get("Name") or f"train_{i}"),
            "lat": to_float(coords[1] if len(coords) > 1 else None),
            "lon": to_float(coords[0] if len(coords) > 0 else None),
            "operator": props.get("operator") or props.get("Operator") or "",
            "heading": to_float(props.get("heading") or props.get("Heading") or 0)
        }
    
    # Standard object
    return {
        "id": str(item.get("id") or item.get("ID") or item.get("Name") or f"train_{i}"),
        "lat": to_float(item.get("lat") or item.get("latitude") or item.get("Latitude")),
        "lon": to_float(item.get("lon") or item.get("longitude") or item.get("Longitude")),
        "operator": item.get("operator") or item.get("Operator") or "",
        "heading": to_float(item.get("heading") or item.get("Heading") or 0)
    }

def find_element_by_text(driver, tag_name, text_contains):
    """Find element by visible text without :contains selector."""
    elements = driver.find_elements(By.TAG_NAME, tag_name)
    for element in elements:
        if text_contains.lower() in (element.text or "").lower():
            return element
    return None

def login_with_selenium():
    """
    Core login function following your exact requirements.
    Returns cookie jar or None on failure.
    """
    if not TF_USERNAME or not TF_PASSWORD:
        print("[ERROR] Missing TF_USERNAME or TF_PASSWORD environment variables")
        return None
    
    print("[SELENIUM] Starting login process...")
    
    # Configure browser - start NON-headless for reliability
    options = uc.ChromeOptions()
    # Start with visible browser for debugging, can switch to headless later
    # options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    driver = None
    try:
        # Initialize driver
        driver = uc.Chrome(options=options)
        driver.set_page_load_timeout(30)
        
        # Step 1: Load login page
        print(f"[SELENIUM] Loading {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        time.sleep(3)  # Initial page load
        
        # Step 2: Find and fill credentials
        print("[SELENIUM] Looking for login form...")
        
        # Try multiple possible username field selectors
        username = None
        for selector in ['input[name="username"]', 'input[name="user"]', 
                        'input[type="text"]', '#username', '#user']:
            try:
                username = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"[SELENIUM] Found username field: {selector}")
                break
            except TimeoutException:
                continue
        
        if not username:
            # Fallback: find first text input
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                if inp.get_attribute("type") in ["text", "email"]:
                    username = inp
                    break
        
        if not username:
            driver.save_screenshot("login_form_missing.png")
            print("[ERROR] Could not find username field")
            return None
        
        username.clear()
        username.send_keys(TF_USERNAME)
        print("[SELENIUM] Username entered")
        
        # Find password field
        password = None
        for selector in ['input[name="password"]', 'input[type="password"]', '#password']:
            try:
                password = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"[SELENIUM] Found password field: {selector}")
                break
            except TimeoutException:
                continue
        
        if not password:
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                if inp.get_attribute("type") == "password":
                    password = inp
                    break
        
        if not password:
            print("[ERROR] Could not find password field")
            return None
        
        password.clear()
        password.send_keys(TF_PASSWORD)
        print("[SELENIUM] Password entered")
        
        # Step 3: Find and click login button
        login_button = None
        
        # Method 1: Look for submit buttons
        for selector in ['button[type="submit"]', 'input[type="submit"]', 
                        'button', 'input[value*="Login"]', 'input[value*="Sign"]']:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    if elem.is_displayed() and elem.is_enabled():
                        login_button = elem
                        print(f"[SELENIUM] Found login button: {selector}")
                        break
                if login_button:
                    break
            except:
                continue
        
        # Method 2: Find by button text
        if not login_button:
            login_button = find_element_by_text(driver, "button", "login")
            if login_button:
                print("[SELENIUM] Found login button by text")
        
        # Method 3: Find by input value text
        if not login_button:
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                value = inp.get_attribute("value") or ""
                if any(word in value.lower() for word in ["login", "sign", "submit"]):
                    login_button = inp
                    print("[SELENIUM] Found login button by input value")
                    break
        
        if not login_button:
            print("[ERROR] Could not find login button")
            driver.save_screenshot("no_login_button.png")
            return None
        
        # Click login
        login_button.click()
        print("[SELENIUM] Login button clicked")
        time.sleep(5)  # Wait for login processing
        
        # Step 4: Handle warning/confirmation page
        print("[SELENIUM] Checking for warning/confirmation page...")
        
        # Check page content for warning indicators
        page_text = driver.page_source.lower()
        warning_indicators = ["warning", "confirm", "acknowledge", "proceed", "continue", "accept"]
        
        if any(indicator in page_text for indicator in warning_indicators):
            print("[SELENIUM] Warning page detected")
            
            # Find and click continue button
            continue_button = None
            
            # Look for buttons with continue/proceed text
            continue_button = find_element_by_text(driver, "button", "continue")
            if not continue_button:
                continue_button = find_element_by_text(driver, "button", "proceed")
            if not continue_button:
                continue_button = find_element_by_text(driver, "a", "continue")
            if not continue_button:
                # Try any clickable element that might dismiss the warning
                buttons = driver.find_elements(By.TAG_NAME, "button")
                if buttons:
                    continue_button = buttons[0]  # First button
            
            if continue_button:
                continue_button.click()
                print("[SELENIUM] Warning page button clicked")
                time.sleep(3)
            else:
                print("[WARNING] Could not find warning page button, proceeding anyway")
        
        # Step 5: Verify login success
        print("[SELENIUM] Verifying login success...")
        time.sleep(3)
        
        # Check current URL - should not be login page
        current_url = driver.current_url
        if "login" in current_url.lower() or "signin" in current_url.lower():
            print("[ERROR] Still on login page after authentication attempt")
            return None
        
        # Try a test request to verify we're logged in
        try:
            driver.get(TF_URL)
            time.sleep(2)
            page_source = driver.page_source
            
            # Check if we got JSON response
            if page_source.strip().startswith(("{", "[")):
                print("[SELENIUM] Login successful - JSON response received")
            else:
                print("[WARNING] May not have full access, but proceeding")
        except Exception as e:
            print(f"[WARNING] Test request failed: {e}")
        
        # Step 6: Export cookies to Requests-compatible format
        print("[SELENIUM] Exporting cookies...")
        selenium_cookies = driver.get_cookies()
        
        # Convert to RequestsCookieJar
        cookie_jar = RequestsCookieJar()
        for cookie in selenium_cookies:
            cookie_jar.set(
                name=cookie['name'],
                value=cookie['value'],
                domain=cookie.get('domain', ''),
                path=cookie.get('path', '/')
            )
        
        print(f"[SELENIUM] Exported {len(selenium_cookies)} cookies")
        return cookie_jar
        
    except Exception as e:
        print(f"[SELENIUM ERROR] {type(e).__name__}: {str(e)}")
        # Save screenshot for debugging
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            driver.save_screenshot(f"selenium_error_{timestamp}.png")
            print(f"[DEBUG] Screenshot saved: selenium_error_{timestamp}.png")
        except:
            pass
        return None
    finally:
        if driver:
            driver.quit()
            print("[SELENIUM] Browser closed")

def fetch_train_data(cookie_jar):
    """Fetch train data using authenticated session."""
    if not cookie_jar:
        return [], "No valid cookies"
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": TF_REFERER
    })
    
    # Apply cookies from Selenium
    session.cookies.update(cookie_jar)
    
    try:
        # Disable redirects to catch login failures
        response = session.get(TF_URL, timeout=30, allow_redirects=False)
        
        # Check for redirect (login failure)
        if response.status_code in (301, 302, 303, 307, 308):
            redirect_to = response.headers.get("Location", "")
            print(f"[FETCH] Redirect detected to: {redirect_to}")
            return [], f"Redirected to login: {redirect_to}"
        
        # Check content type
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" not in content_type:
            snippet = response.text[:200] if response.text else ""
            print(f"[FETCH] Non-JSON response: {snippet}")
            return [], f"Non-JSON response: {response.status_code}"
        
        # Parse JSON
        try:
            data = response.json()
        except ValueError as e:
            print(f"[FETCH] JSON parse error: {e}")
            return [], "JSON parse error"
        
        # Extract and normalize trains
        raw_list = extract_list(data)
        trains = []
        
        for i, item in enumerate(raw_list):
            train = norm_item(item, i)
            if train and train.get("lat") is not None and train.get("lon") is not None:
                trains.append(train)
        
        return trains, "ok"
        
    except requests.RequestException as e:
        print(f"[FETCH ERROR] Request failed: {e}")
        return [], f"Request error: {type(e).__name__}"

def main():
    """Main execution flow."""
    print("=" * 60)
    print(f"RailOps Backend Scraper - {datetime.datetime.utcnow().isoformat()}Z")
    print("=" * 60)
    
    # Step 1: Login with Selenium
    print("\n[MAIN] Phase 1: Authentication")
    cookie_jar = login_with_selenium()
    
    if not cookie_jar:
        print("[MAIN] Login failed - writing empty output")
        write_output([], "Login failed")
        return
    
    # Step 2: Fetch data with authenticated session
    print("\n[MAIN] Phase 2: Data Fetch")
    trains, note = fetch_train_data(cookie_jar)
    
    # Step 3: Write output (always succeeds)
    print("\n[MAIN] Phase 3: Output")
    write_output(trains, note)
    
    print(f"\n[MAIN] Complete. Trains: {len(trains)}, Status: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()