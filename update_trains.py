import os
import sys

print("=" * 60)
print("🚂 DEBUG - TEST SCRIPT")
print("=" * 60)
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in directory: {os.listdir('.')}")
print("=" * 60)

try:
    from selenium import webdriver
    print("✅ Selenium imported successfully")
except Exception as e:
    print(f"❌ Failed to import selenium: {e}")

try:
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    print("✅ Chrome options set")
except Exception as e:
    print(f"❌ Failed to set Chrome options: {e}")

print("=" * 60)
print("Test complete")
