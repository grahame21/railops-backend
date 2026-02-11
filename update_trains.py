import os
import json
import datetime
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests

OUT_FILE = "trains.json"
TF_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

def write_output(trains, note=""):
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains or []
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Output: {len(trains or [])} trains, status: {note}")

def extract_list(data):
    if not data: return []
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for k in ["trains", "Trains", "markers", "Markers", "features"]:
            if isinstance(data.get(k), list):
                return data[k]
    return []

def to_float(x):
    try: return float(x) if x is not None else None
    except: return None

def norm_item(item, i):
    if not isinstance(item, dict): return None
    return {
        "id": str(item.get("id") or item.get("ID") or f"train_{i}"),
        "lat": to_float(item.get("lat") or item.get("latitude")),
        "lon": to_float(item.get("lon") or item.get("longitude")),
        "operator": item.get("operator") or "",
        "heading": to_float(item.get("heading") or 0)
    }

def login_and_get_cookies():
    """Simplified login for GitHub Actions"""
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("Missing credentials")
        return None
    
    print("Setting up Chrome...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36')
    
    driver = None
    try:
        # Use webdriver_manager to handle chromedriver
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print("Loading login page...")
        driver.get(TF_LOGIN_URL)
        time.sleep(3)
        
        # Find and fill username
        username = None
        for selector in ['input[name="username"]', 'input[type="text"]', '#username']:
            try:
                username = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                break
            except:
                continue
        
        if not username:
            print("Could not find username field")
            return None
        
        username.clear()
        username.send_keys(TF_USERNAME)
        print("Username entered")
        
        # Find and fill password
        password = None
        for selector in ['input[name="password"]', 'input[type="password"]', '#password']:
            try:
                password = driver.find_element(By.CSS_SELECTOR, selector)
                break
            except:
                continue
        
        if not password:
            print("Could not find password field")
            return None
        
        password.clear()
        password.send_keys(TF_PASSWORD)
        print("Password entered")
        
        # Find and click login button
        login_button = None
        try:
            # Try submit button
            login_button = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
        except:
            # Try any button with login text
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "login" in btn.text.lower() or "sign" in btn.text.lower():
                    login_button = btn
                    break
        
        if not login_button:
            print("Could not find login button")
            return None
        
        login_button.click()
        print("Login clicked")
        time.sleep(5)
        
        # Handle warning page if present
        if "warning" in driver.page_source.lower() or "continue" in driver.page_source.lower():
            print("Warning page detected")
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "continue" in btn.text.lower() or "proceed" in btn.text.lower():
                    btn.click()
                    print("Warning dismissed")
                    time.sleep(3)
                    break
        
        # Get cookies
        cookies = driver.get_cookies()
        print(f"Got {len(cookies)} cookies")
        
        # Convert to cookie string
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        return cookie_str
        
    except Exception as e:
        print(f"Login error: {str(e)}")
        return None
    finally:
        if driver:
            driver.quit()

def fetch_train_data(cookie_str):
    if not cookie_str:
        return [], "No cookies"
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Cookie": cookie_str,
        "Referer": TF_LOGIN_URL
    })
    
    try:
        r = session.get(TF_URL, timeout=30, allow_redirects=False)
        
        if r.status_code in (301, 302, 303, 307, 308):
            return [], "Redirected"
        
        if "application/json" not in r.headers.get("content-type", "").lower():
            return [], "Non-JSON response"
        
        data = r.json()
        raw_list = extract_list(data)
        trains = []
        
        for i, item in enumerate(raw_list):
            train = norm_item(item, i)
            if train and train["lat"] and train["lon"]:
                trains.append(train)
        
        return trains, "ok"
        
    except Exception as e:
        return [], f"Error: {type(e).__name__}"

def main():
    print(f"Starting train update at {datetime.datetime.utcnow().isoformat()}")
    
    cookie = login_and_get_cookies()
    if not cookie:
        write_output([], "Login failed")
        return
    
    trains, note = fetch_train_data(cookie)
    write_output(trains, note)
    print(f"Complete: {len(trains)} trains")

if __name__ == "__main__":
    main()
