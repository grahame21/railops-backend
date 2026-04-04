#!/usr/bin/env python3
"""
Test script to verify the environment is working
"""

import os
import sys
import platform

print("=" * 50)
print("🔍 ENVIRONMENT CHECK")
print("=" * 50)
print(f"Python version: {sys.version}")
print(f"Platform: {platform.platform()}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in directory: {os.listdir('.')}")
print("=" * 50)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    print("✅ Selenium imported successfully")
except ImportError as e:
    print(f"❌ Failed to import selenium: {e}")
    sys.exit(1)

try:
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=chrome_options)
    print("✅ Chrome driver started successfully")
    
    driver.get("https://www.google.com")
    print(f"✅ Page loaded: {driver.title}")
    
    driver.quit()
    print("✅ Chrome driver closed")
    
except Exception as e:
    print(f"❌ Chrome test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 50)
print("✅ ALL TESTS PASSED")
print("=" * 50)
