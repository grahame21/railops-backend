# fetch_trains_cdp.py
import os
import json
import time
import re
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ---------- CONFIG ----------
ASPXAUTH = os.getenv("ASPXAUTH", "").replace(".ASPXAUTH=", "").strip()
if not ASPXAUTH:
    raise SystemExit("❌ Set ASPXAUTH env var to your .ASPXAUTH value")

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))

# You can force a single referer by setting TRAINFINDER_REFERER env var
FORCED_REFERER = os.getenv("TRAINFINDER_REFERER")

VIEWPORTS = [
    ("Australia_centre", -25.2744, 133.7751),
    ("Adelaide", -34.9285, 138.6007),
    ("Melbourne", -37.8136, 144.9631),
    ("Sydney", -33.8688, 151.2093),
    ("Brisbane", -27.4698, 153.0251),
    ("Perth", -31.9523, 115.8613),
    ("Newcastle", -32.9283, 151.7817),
    ("Wagga", -35.1080, 147.3694),
    ("Port_Augusta", -32.4922, 137.7650),
    ("Kalgoorlie", -30.7494, 121.4650),
]
ZOOMS = [6, 7, 8]

BASE = "https://trainfinder.otenko.com"
NEXTLEVEL = f"{BASE}/home/nextlevel"
TARGET_PATH = "/Home/GetViewPortData"  # match_
