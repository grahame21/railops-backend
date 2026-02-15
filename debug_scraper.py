import os
import sys
import traceback

print("=" * 60)
print("🔍 DEBUG SCRAPER - CHECKING IMPORTS")
print("=" * 60)

try:
    print("Checking imports...")
    import selenium
    print(f"✅ selenium version: {selenium.__version__}")
except Exception as e:
    print(f"❌ selenium import failed: {e}")

try:
    from selenium import webdriver
    print("✅ webdriver imported")
except Exception as e:
    print(f"❌ webdriver import failed: {e}")

try:
    import requests
    print("✅ requests imported")
except Exception as e:
    print(f"❌ requests import failed: {e}")

print("\nChecking environment:")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Files: {os.listdir('.')}")

print("\nChecking credentials:")
TF_USERNAME = os.environ.get("TF_USERNAME", "")
TF_PASSWORD = os.environ.get("TF_PASSWORD", "")
print(f"Username set: {'Yes' if TF_USERNAME else 'No'}")
print(f"Password set: {'Yes' if TF_PASSWORD else 'No'}")

print("\n" + "=" * 60)
print("✅ Debug check complete")
