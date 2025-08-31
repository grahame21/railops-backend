# ---- replace these helpers in main.py ----
import re
import json
import requests

TF_BASE = "https://trainfinder.otenko.com"
ASPXAUTH_VALUE = None  # (unchanged)

def _extract_verification_token(html: str) -> str | None:
    """
    Try multiple patterns: hidden input, meta tags, or JS vars.
    """
    patterns = [
        r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
        r'name="RequestVerificationToken"[^>]*value="([^"]+)"',
        r'<meta[^>]+name="__RequestVerificationToken"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="RequestVerificationToken"[^>]+content="([^"]+)"',
        r'window\.__RequestVerificationToken\s*=\s*"([^"]+)"',
        r'var\s+__RequestVerificationToken\s*=\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.I | re.S)
        if m:
            return m.group(1)
    return None

def _extract_token_from_cookies(cookiejar) -> tuple[str | None, list[str]]:
    """
    Some ASP.NET apps set antiforgery cookies. We record what we found
    and optionally try the cookie value as the header token if needed.
    """
    names = []
    token = None
    for c in cookiejar:
        if ("Antiforgery" in c.name) or (c.name.startswith("__RequestVerificationToken")):
            names.append(c.name)
            # fallback: try cookie value as token (works on some stacks)
            token = token or c.value
    return token, names

def _looks_like_html(s: str) -> bool:
    t = (s or "").lstrip()
    return t.startswith("<!DOCTYPE") or t.startswith("<html") or t.startswith("<")

def _session_with_cookie() -> requests.Session:
    if not ASPXAUTH_VALUE:
        raise RuntimeError("No .ASPXAUTH cookie set. Call /set-aspxauth first.")
    s = requests.Session()
    s.cookies.set(".ASPXAUTH", ASPXAUTH_VALUE, domain="trainfinder.otenko.com", secure=True)
    return s

def fetch_viewport(lat: float, lng: float, zm: int) -> dict:
    """
    1) GET /Home/NextLevel (note the caps) to receive HTML + antiforgery cookie(s)
    2) Extract token from HTML (or fallback to cookie value)
    3) POST /home/GetViewPortData with token in BOTH form + header
    """
    s = _session_with_cookie()

    # 1) Warmup (try canonical casing)
    warmup_url = f"{TF_BASE}/Home/NextLevel"
    warmup = s.get(warmup_url, params={"lat": lat, "lng": lng, "zm": zm}, timeout=20)
    warmup_html = warmup.text or ""
    token_html = _extract_verification_token(warmup_html)
    token_cookie, anti_cookie_names = _extract_token_from_cookies(s.cookies)
    token = token_html or token_cookie

    diag: dict = {
        "used_cookie": True,
        "verification_token_present": bool(token),
        "token_source": "html" if token_html else ("cookie" if token_cookie else ""),
        "anti_cookie_names": anti_cookie_names,
        "warmup": {
            "status": warmup.status_code,
            "bytes": len(warmup_html),
            "preview": warmup_html[:500],  # help when debugging
        },
        "viewport": {},
    }

    if not token:
        # No token found anywhere -> upstream will return the 98B nulls
        diag["viewport"] = {
            "status": 0,
            "bytes": 0,
            "looks_like_html": False,
            "preview": "",
            "note": "no_verification_token_in_warmup_html_or_cookies",
        }
        return diag

    # 2) POST, keep both header + form token
    form = {
        "lat": f"{lat:.6f}",
        "lng": f"{lng:.6f}",
        "zoomLevel": str(zm),
        "__RequestVerificationToken": token,
    }
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{TF_BASE}/Home/NextLevel?lat={lat}&lng={lng}&zm={zm}",
        "RequestVerificationToken": token,
    }

    vp = s.post(f"{TF_BASE}/home/GetViewPortData", data=form, headers=headers, timeout=30)
    body = vp.text or ""
    diag["viewport"] = {
        "status": vp.status_code,
        "bytes": len(body),
        "looks_like_html": _looks_like_html(body),
        "preview": body[:2000],
    }
    return diag
# ---- end replacements ----
