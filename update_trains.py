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

def login_and_get_trains():
    """Complete login flow and fetch train data directly"""
    
    print("🔄 Starting complete login flow...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Step 1: Load the login/map page
        print(f"🔄 Loading page: {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        
        # Step 2: Find and fill username field
        try:
            username = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            print("✅ Found username field")
            username.clear()
            username.send_keys(TF_USERNAME)
            print("✅ Username entered")
        except Exception as e:
            print(f"❌ Could not find username field: {str(e)}")
            return [], "Username field not found"
        
        # Step 3: Find and fill password field
        try:
            password = driver.find_element(By.ID, "pasS_word")
            print("✅ Found password field")
            password.clear()
            password.send_keys(TF_PASSWORD)
            print("✅ Password entered")
        except Exception as e:
            print(f"❌ Could not find password field: {str(e)}")
            return [], "Password field not found"
        
        # Step 4: Check Remember Me
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
                print("✅ Checked Remember Me")
        except:
            print("⚠️ Could not find Remember Me checkbox")
        
        # Step 5: Find and click the form submit button
        print("🔍 Looking for login form...")
        
        # Look for any form and submit it
        forms = driver.find_elements(By.TAG_NAME, "form")
        if forms:
            print(f"✅ Found {len(forms)} form(s), submitting the first one")
            driver.execute_script("arguments[0].submit();", forms[0])
            print("✅ Form submitted via JavaScript")
        else:
            print("❌ No forms found")
            return [], "No login form found"
        
        # Wait for login to process and warning page to appear
        print("⏳ Waiting for warning page...")
        time.sleep(8)
        
        # Step 6: Handle the warning page - click the X/Close button
        print("🔍 Looking for warning page close button...")
        
        # Look for SVG path with the close icon
        svg_paths = driver.find_elements(By.TAG_NAME, "path")
        close_clicked = False
        for path in svg_paths:
            d_attr = path.get_attribute("d") or ""
            if "M13.7,11l6.1-6.1" in d_attr:
                try:
                    driver.execute_script("arguments[0].click();", path)
                    print("✅ Clicked warning page close button (SVG path)")
                    close_clicked = True
                    break
                except:
                    pass
        
        if not close_clicked:
            # Try alternative close buttons
            close_selectors = [".close", ".btn-close", "[aria-label='Close']", "button:contains('×')"]
            for selector in close_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    btn.click()
                    print(f"✅ Clicked close button with selector: {selector}")
                    close_clicked = True
                    break
                except:
                    pass
        
        # Wait for map to load
        print("⏳ Waiting for map to load...")
        time.sleep(5)
        
        # Step 7: DIRECTLY FETCH THE TRAIN DATA
        print(f"🔄 Fetching train data directly from API...")
        driver.get(TF_URL)
        time.sleep(3)
        
        # Get the JSON response
        page_source = driver.page_source
        print(f"📄 Response length: {len(page_source)} characters")
        
        # Check if we got JSON
        if page_source.strip().startswith(("{", "[")):
            print("✅ Successfully received JSON data!")
            
            try:
                import json
                data = json.loads(page_source)
                raw_list = extract_list(data)
                
                trains = []
                for i, item in enumerate(raw_list):
                    train = norm_item(item, i)
                    if train and train.get("lat") and train.get("lon"):
                        trains.append(train)
                
                print(f"✅ Extracted {len(trains)} trains")
                
                # Save screenshot of success
                driver.save_screenshot("login_success.png")
                print("📸 Success screenshot saved")
                
                return trains, "ok"
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse error: {str(e)}")
                return [], "JSON parse error"
        else:
            # If not JSON, save the response for debugging
            with open("debug_response.html", "w") as f:
                f.write(page_source[:5000])
            print("⚠️ Response is not JSON - saved first 5000 chars to debug_response.html")
            return [], "Non-JSON response"
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        try:
            driver.save_screenshot("error.png")
            print("📸 Error screenshot saved")
        except:
            pass
        return [], f"Error: {type(e).__name__}"
    finally:
        if driver:
            driver.quit()
            print("✅ Browser closed")

def main():
    print("=" * 60)
    print(f"🚂 FINAL VERSION - Direct Train Data Fetch")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = login_and_get_trains()
    write_output(trains, note)
    
    print(f"\n🏁 Complete: {len(trains)} trains")
    print(f"📝 Status: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()
