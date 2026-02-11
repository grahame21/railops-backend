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
from webdriver_manager.chrome import ChromeDriverManager
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
    print(f"📝 Output: {len(trains or [])} trains, status: {note}")

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

def get_train_data_direct():
    """DIRECT APPROACH: Just load the page and get cookies, no form filling needed"""
    
    print("🔄 Starting direct cookie extraction...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = None
    try:
        # Install driver and launch
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Just load the page - no login needed if already authenticated?
        print(f"🔄 Loading: {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Get ALL cookies from the session
        cookies = driver.get_cookies()
        print(f"✅ Got {len(cookies)} cookies")
        
        # Convert to cookie string for requests
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        # Try to fetch train data with these cookies
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": TF_LOGIN_URL,
            "Cookie": cookie_str
        })
        
        print(f"🔄 Fetching: {TF_URL}")
        r = session.get(TF_URL, timeout=30, allow_redirects=False)
        print(f"✅ Response: {r.status_code}")
        
        if r.status_code == 200 and "application/json" in r.headers.get("content-type", "").lower():
            data = r.json()
            raw_list = extract_list(data)
            trains = []
            for i, item in enumerate(raw_list):
                train = norm_item(item, i)
                if train and train.get("lat") and train.get("lon"):
                    trains.append(train)
            return trains, "ok"
        else:
            return [], f"HTTP {r.status_code}"
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return [], f"Error: {type(e).__name__}"
    finally:
        if driver:
            driver.quit()
            print("✅ Browser closed")

def main():
    print("=" * 60)
    print(f"🚂 DIRECT COOKIE EXTRACTION - {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    trains, note = get_train_data_direct()
    write_output(trains, note)
    
    print(f"🏁 Complete: {len(trains)} trains")
    print("=" * 60)

if __name__ == "__main__":
    main()
