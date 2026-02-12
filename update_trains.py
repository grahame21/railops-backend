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

def debug_page_structure():
    """Debug function to print all buttons and their text"""
    
    print("🔄 Starting debug investigation...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print(f"🔄 Loading page: {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Print page title and URL
        print(f"📌 Page title: {driver.title}")
        print(f"📌 Current URL: {driver.current_url}")
        
        # Find ALL buttons and print their text
        print("\n🔍 ALL BUTTONS ON PAGE:")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for i, btn in enumerate(buttons):
            btn_text = btn.text.strip()
            btn_id = btn.get_attribute("id") or "no-id"
            btn_class = btn.get_attribute("class") or "no-class"
            btn_type = btn.get_attribute("type") or "no-type"
            print(f"   Button {i}: text='{btn_text}', id='{btn_id}', class='{btn_class[:30]}...', type='{btn_type}'")
        
        # Find ALL input elements
        print("\n🔍 ALL INPUT ELEMENTS:")
        inputs = driver.find_elements(By.TAG_NAME, "input")
        for i, inp in enumerate(inputs):
            inp_type = inp.get_attribute("type") or "text"
            inp_id = inp.get_attribute("id") or "no-id"
            inp_name = inp.get_attribute("name") or "no-name"
            inp_value = inp.get_attribute("value") or ""
            print(f"   Input {i}: type='{inp_type}', id='{inp_id}', name='{inp_name}', value='{inp_value}'")
        
        # Find ALL form elements
        print("\n🔍 ALL FORM ELEMENTS:")
        forms = driver.find_elements(By.TAG_NAME, "form")
        print(f"   Found {len(forms)} forms")
        
        # Look specifically for login-related elements
        print("\n🔍 SEARCHING FOR LOGIN BUTTON:")
        
        # Method 1: By text containing common login words
        login_keywords = ["log in", "login", "sign in", "submit", "enter", "go"]
        for btn in buttons:
            btn_text_lower = btn.text.strip().lower()
            for keyword in login_keywords:
                if keyword in btn_text_lower:
                    print(f"   ✅ Found potential login button: '{btn.text}' (matches '{keyword}')")
        
        # Method 2: By input type submit
        for inp in inputs:
            if inp.get_attribute("type") == "submit":
                print(f"   ✅ Found submit input: value='{inp.get_attribute('value')}'")
        
        # Method 3: By common class names
        login_classes = ["btn-login", "login-btn", "submit-btn", "btn-primary"]
        for btn in buttons:
            btn_class = btn.get_attribute("class") or ""
            for login_class in login_classes:
                if login_class in btn_class:
                    print(f"   ✅ Found button with login class: '{btn.text}' (class: {login_class})")
        
        # Try to find the form that contains the username field
        print("\n🔍 FINDING FORM CONTAINING USERNAME:")
        try:
            username = driver.find_element(By.ID, "useR_name")
            # Find parent form
            parent_form = username.find_element(By.XPATH, "./ancestor::form")
            print(f"   ✅ Found parent form: {parent_form.get_attribute('id') or 'no-id'}")
            print(f"   Form action: {parent_form.get_attribute('action') or 'no-action'}")
            print(f"   Form method: {parent_form.get_attribute('method') or 'no-method'}")
        except:
            print("   ❌ Could not find parent form for username")
        
        # Save screenshot for visual debugging
        driver.save_screenshot("debug_page.png")
        print("\n📸 Screenshot saved: debug_page.png")
        
        return "Debug completed"
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        return f"Error: {type(e).__name__}"
    finally:
        if driver:
            driver.quit()
            print("✅ Browser closed")

def main():
    print("=" * 60)
    print(f"🚂 DEBUG MODE - Finding Login Button")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    result = debug_page_structure()
    write_output([], result)
    
    print("\n" + "=" * 60)
    print("🏁 Debug complete")
    print("=" * 60)

if __name__ == "__main__":
    main()
