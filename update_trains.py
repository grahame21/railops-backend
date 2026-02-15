import os
import sys
import traceback

print("=" * 60)
print("🚂 RAILOPS - TRAIN SCRAPER (DEBUG MODE)")
print("=" * 60)
print(f"Python version: {sys.version}")
print(f"Current time: {__import__('datetime').datetime.now()}")
print("=" * 60)

try:
    # Import everything
    print("\n📦 Importing modules...")
    import json
    import datetime
    import time
    import math
    import pickle
    import random
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    print("✅ All imports successful")
    
    OUT_FILE = "trains.json"
    COOKIE_FILE = "trainfinder_cookies.pkl"
    TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
    TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
    TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()
    
    print(f"\n🔑 Credentials:")
    print(f"   Username set: {'Yes' if TF_USERNAME else 'No'}")
    print(f"   Password set: {'Yes' if TF_PASSWORD else 'No'}")
    print(f"   Login URL: {TF_LOGIN_URL}")
    
    class TrainScraper:
        def __init__(self):
            self.driver = None
            print("✅ TrainScraper initialized")
            
        def setup_driver(self):
            print("\n🔧 Setting up Chrome driver...")
            try:
                chrome_options = Options()
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_argument('--headless=new')  # Add headless mode
                
                user_agents = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                ]
                chrome_options.add_argument(f'--user-agent={random.choice(user_agents)}')
                
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                self.driver = webdriver.Chrome(options=chrome_options)
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                print("✅ Chrome driver setup successful")
                return True
            except Exception as e:
                print(f"❌ Failed to setup Chrome driver: {e}")
                traceback.print_exc()
                return False
        
        def run(self):
            print("\n🚀 Starting scraper run...")
            
            if not TF_USERNAME or not TF_PASSWORD:
                print("❌ Missing credentials")
                return [], "Missing credentials"
            
            if not self.setup_driver():
                return [], "Failed to setup driver"
            
            print("\n✅ Scraper ready but stopping here for testing")
            print("👋 Browser would close here")
            
            return [], "ok - debug mode"
    
    def write_output(trains, note=""):
        print(f"\n📝 Would write: {len(trains)} trains, status: {note}")
    
    def main():
        print("\n🏁 Starting main function...")
        scraper = TrainScraper()
        trains, note = scraper.run()
        write_output(trains, note)
        print("\n✅ Debug script completed successfully")
    
    if __name__ == "__main__":
        main()
        
except Exception as e:
    print(f"\n❌ CRITICAL ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
