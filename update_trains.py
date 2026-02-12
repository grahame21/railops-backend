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

def debug_complete_flow():
    """Complete debug of login flow including warning page"""
    
    print("=" * 60)
    print("🔍 COMPLETE LOGIN FLOW DEBUG")
    print("=" * 60)
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # STEP 1: Initial page load
        print("\n📌 STEP 1: Loading login page")
        print(f"   URL: {TF_LOGIN_URL}")
        driver.get(TF_LOGIN_URL)
        time.sleep(5)
        print(f"   Page title: {driver.title}")
        print(f"   Current URL: {driver.current_url}")
        
        # STEP 2: Find username and password fields
        print("\n📌 STEP 2: Looking for login form")
        try:
            username = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            print("   ✅ Found username field (ID: useR_name)")
            username.clear()
            username.send_keys(TF_USERNAME)
            print("   ✅ Username entered")
        except Exception as e:
            print(f"   ❌ Could not find username field: {e}")
        
        try:
            password = driver.find_element(By.ID, "pasS_word")
            print("   ✅ Found password field (ID: pasS_word)")
            password.clear()
            password.send_keys(TF_PASSWORD)
            print("   ✅ Password entered")
        except Exception as e:
            print(f"   ❌ Could not find password field: {e}")
        
        try:
            remember = driver.find_element(By.ID, "rem_ME")
            if not remember.is_selected():
                remember.click()
                print("   ✅ Checked Remember Me")
        except:
            print("   ⚠️ Remember Me checkbox not found")
        
        # STEP 3: Find ALL possible login triggers
        print("\n📌 STEP 3: Searching for login button/trigger")
        
        # Check all buttons
        print("\n   --- ALL BUTTONS ON PAGE ---")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for i, btn in enumerate(buttons):
            btn_text = btn.text.strip()
            btn_id = btn.get_attribute("id") or "no-id"
            btn_class = btn.get_attribute("class") or "no-class"
            btn_type = btn.get_attribute("type") or "no-type"
            btn_onclick = btn.get_attribute("onclick") or ""
            print(f"   Button {i}:")
            print(f"     Text: '{btn_text}'")
            print(f"     ID: '{btn_id}'")
            print(f"     Class: '{btn_class[:50]}'")
            print(f"     Type: '{btn_type}'")
            print(f"     Onclick: '{btn_onclick[:50]}'")
        
        # Check all input type submit
        print("\n   --- SUBMIT INPUTS ---")
        submit_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='submit']")
        for i, inp in enumerate(submit_inputs):
            inp_value = inp.get_attribute("value") or ""
            inp_id = inp.get_attribute("id") or "no-id"
            print(f"   Submit input {i}: value='{inp_value}', id='{inp_id}'")
        
        # Check for any element with login-related attributes
        print("\n   --- ELEMENTS WITH LOGIN ATTRIBUTES ---")
        login_elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'login') or contains(@class, 'Login') or contains(@id, 'login') or contains(@id, 'Login')]")
        for i, elem in enumerate(login_elements[:10]):  # Limit to first 10
            elem_tag = elem.tag_name
            elem_text = elem.text.strip()[:50]
            elem_id = elem.get_attribute("id") or "no-id"
            elem_class = elem.get_attribute("class") or "no-class"
            print(f"   Element {i}: <{elem_tag}> id='{elem_id}', class='{elem_class[:30]}', text='{elem_text}'")
        
        # STEP 4: Try to find the form containing username
        print("\n📌 STEP 4: Looking for form containing username")
        try:
            username = driver.find_element(By.ID, "useR_name")
            form = username.find_element(By.XPATH, "./ancestor::form")
            print(f"   ✅ Found form:")
            print(f"     Action: {form.get_attribute('action') or 'none'}")
            print(f"     Method: {form.get_attribute('method') or 'none'}")
            print(f"     ID: {form.get_attribute('id') or 'none'}")
            print(f"     Class: {form.get_attribute('class') or 'none'}")
            
            # Try to submit the form directly
            print("\n   🔄 Attempting form submission...")
            driver.execute_script("arguments[0].submit();", form)
            print("   ✅ Form submitted via JavaScript")
            time.sleep(5)
        except Exception as e:
            print(f"   ❌ Could not find form: {e}")
            
            # If no form, try to find any login button by common text
            print("\n   🔄 Attempting to find login button by common text...")
            login_texts = ["log in", "login", "sign in", "submit", "enter", "continue", "go"]
            for btn in buttons:
                btn_text_lower = btn.text.strip().lower()
                for login_text in login_texts:
                    if login_text in btn_text_lower:
                        print(f"   ✅ Found button with text '{btn.text}'")
                        btn.click()
                        print("   ✅ Button clicked")
                        time.sleep(5)
                        break
                else:
                    continue
                break
        
        # STEP 5: Check for warning page
        print("\n📌 STEP 5: Looking for warning page")
        current_url = driver.current_url
        print(f"   Current URL: {current_url}")
        
        page_source = driver.page_source.lower()
        warning_indicators = ["warning", "confirm", "acknowledge", "proceed", "continue", "accept"]
        for indicator in warning_indicators:
            if indicator in page_source:
                print(f"   ⚠️ Warning page detected (contains '{indicator}')")
                
                # Try to close warning page
                print("\n   🔄 Attempting to close warning page...")
                
                # Method 1: Click SVG close button
                close_script = """
                var paths = document.getElementsByTagName('path');
                for(var i = 0; i < paths.length; i++) {
                    var d = paths[i].getAttribute('d') || '';
                    if(d.includes('M13.7,11l6.1-6.1')) {
                        var parent = paths[i].parentElement;
                        while(parent && parent.tagName !== 'BUTTON' && parent.tagName !== 'DIV' && parent.tagName !== 'A') {
                            parent = parent.parentElement;
                        }
                        if(parent) {
                            parent.click();
                            return 'Clicked SVG close button';
                        }
                    }
                }
                return 'No close button found';
                """
                result = driver.execute_script(close_script)
                print(f"   ✅ {result}")
                time.sleep(3)
                break
        
        # STEP 6: Check if we're logged in by trying to access the API
        print("\n📌 STEP 6: Testing API access")
        print(f"   🔄 Fetching: {TF_URL}")
        driver.get(TF_URL)
        time.sleep(3)
        
        response = driver.page_source
        print(f"   Response length: {len(response)} characters")
        
        if response.strip().startswith(("{", "[")):
            print("   ✅ SUCCESS! Received JSON data")
            try:
                import json
                data = json.loads(response)
                print(f"   📊 Data preview: {str(data)[:200]}...")
            except:
                print("   ❌ Could not parse JSON")
        else:
            print("   ❌ Response is not JSON")
            print(f"   Response preview: {response[:200]}")
        
        # STEP 7: Save screenshot
        driver.save_screenshot("debug_final_state.png")
        print("\n📸 Final screenshot saved: debug_final_state.png")
        
        return "Debug complete - check logs above"
        
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {str(e)}")
        try:
            driver.save_screenshot("debug_error.png")
            print("📸 Error screenshot saved")
        except:
            pass
        return f"Error: {type(e).__name__}"
    finally:
        if driver:
            driver.quit()
            print("\n✅ Browser closed")

def main():
    print("=" * 60)
    print("🚂 COMPLETE DEBUG - Login + Warning + API")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    result = debug_complete_flow()
    write_output([], result)
    
    print("\n" + "=" * 60)
    print("🏁 Debug complete - check the logs above!")
    print("=" * 60)

if __name__ == "__main__":
    main()
