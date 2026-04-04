import os
import sys
import datetime

print("=" * 60)
print("✅ TEST SCRIPT - VERIFYING PYTHON ENVIRONMENT")
print("=" * 60)
print(f"Python version: {sys.version}")
print(f"Current time: {datetime.datetime.now()}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in directory: {os.listdir('.')}")
print("=" * 60)
print("Test completed successfully!")
