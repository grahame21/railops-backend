import os
import time
import json
import itertools
import requests
from datetime import datetime

# === CONFIG ===
URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

# Put either the raw value or the whole ".ASPXAUTH=..." string here or use env var ASPXAUTH
COOKIE_VALUE = os.getenv("ASPXAUTH", ".ASPXAUTH=YOUR_COOKIE_HERE")

# Optional: force a single referer via env var TRAINFINDER_REFERER
FORCED_REFERER = os.getenv("TRAINFINDER_REFERER")

# How often to poll (seconds)
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))

# Common Australian viewports (lat/lng = map center); we’ll rotate until we get data
VIEWPORTS = [
    # name, lat, lng
    ("Australia_centre", -25.2744, 133.7751),  # wide AU
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

ZOOMS = [6, 7, 8]  # Trainfinder tends to return data around 6–7; trying 8 too

# === HEADERS / COOKIES ===
def parse_cookie(val: str) -> str:
    return val.replace(".ASPXAUTH=", "").strip()

ASPXAUTH = parse_cookie(COOKIE_VALUE)
if not ASPXAUTH or ASPXAUTH == "YOUR_COOKIE_HERE":
    print("❌ Please set a valid .ASPXAUTH cookie in ASPXAUTH env var or inside this file.")
    raise SystemExit(1)

BASE_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "origin": "https://trainfinder.otenko.com",
    # referer is set dynamically per attempt
    "sec-ch-ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "
