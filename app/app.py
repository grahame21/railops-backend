# app/app.py
import math
import os
import time
import re
from typing import Any, Dict, List, Tuple, Optional

import requests
from flask import Flask, jsonify, request, Response

app = Flask(__name__)

TF_BASE = "https://trainfinder.otenko.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0")

DEFAULT_LAT = -33.8688
DEFAULT_LNG = 151.2093
DEFAULT_ZM  = 12

# Sample scan points and zooms
HOTSPOTS: List[Tuple[str, float, float]] = [
    ("Sydney",   -33.868800, 151.209300),
    ("Melbourne",-37.813600, 144.963100),
    ("Brisbane", -27.469800, 153.025100),
    ("Perth",    -31.952300, 115.861300),
    ("Adelaide", -34.928500, 138.600700),
]
ZOOMS = [11, 12, 13]

VIEW_W, VIEW_H = 1280, 720
TILE_SIZE = 256.0

def _safe_float(s: Any, fallback: float) -> float:
    try:
        return float(s)
    except Exception:
        try:
            # Extract first float-like token if garbage is appended
            m = re.search(r"-?\d+(?:\.\d+)?", str(s))
            return float(m.group(0)) if m else fallback
        except Exception:
            return fallback

def _safe_int(s: Any, fallback: int) -> int:
    try:
        return int(s)
    except Exception:
        # Be tolerant of things like "12https://..." in logs
        m = re.search(r"-?\d+", str(s))
        return int(m.group(0)) if m else fallback

def _new_session(aspx_cookie: Optional[str]) -> requests.Session:
    """Creates a session and optionally injects the .ASPXAUTH cookie.

    Precedence:
      - X-TF-ASPXAUTH header on the inbound request
      - ?cookie= query string on our endpoint
      - TF_AUTH_COOKIE environment variable (Render → Env Vars)
      - function argument (aspx_cookie)
    """
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": UA,
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": TF_BASE,
        "Referer": f"{TF_BASE}/home/nextlevel?lat={DEFAULT_LAT}&lng={DEFAULT_LNG}&zm={DEFAULT_ZM}",
    })

    header_c_
