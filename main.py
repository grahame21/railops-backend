import re

ANTI_COOKIE_HINTS = ["__RequestVerificationToken", "Antiforgery", "XSRF", "CSRF"]

def _extract_verification_token_from_html(html: str) -> tuple[str | None, str]:
    """
    Returns (form_token, source). Looks for the hidden field commonly used by ASP.NET.
    """
    if not html:
        return None, ""
    # hidden input
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html, re.I)
    if m:
        return m.group(1), "hidden-input"
    # meta variants some apps use
    m = re.search(r'<meta[^>]+name="__RequestVerificationToken"[^>]+content="([^"]+)"', html, re.I)
    if m:
        return m.group(1), "meta"
    # inline script var (rare)
    m = re.search(r'__RequestVerificationToken"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1), "script"
    return None, ""

def _extract_anti_cookie(session_cookies) -> tuple[str | None, str, list[str]]:
    """
    Returns (cookie_token, cookie_name, seen_cookie_names)
    """
    seen = []
    best_val, best_name = None, ""
    for c in session_cookies:
        seen.append(c.name)
        if any(hint.lower() in c.name.lower() for hint in ANTI_COOKIE_HINTS):
            best_val, best_name = c.value, c.name
    return best_val, best_name, seen

def _verification_header_candidates(form_token: str | None, cookie_token: str | None, cookie_name: str | None):
    """
    Yield header dictionaries to try with the POST. Order matters.
    """
    # Nothing (some endpoints don't actually require it)
    yield {}

    # Classic ASP.NET MVC: header with the form token; cookie is already sent by the session
    if form_token:
        yield {"RequestVerificationToken": form_token}
        yield {"X-RequestVerificationToken": form_token}

    # Pair form:cookie (some older ASP.NET expect this format)
    if form_token and cookie_token:
        yield {"RequestVerificationToken": f"{form_token}:{cookie_token}"}

    # Angular style: cookie used as header
    if cookie_token:
        yield {"X-XSRF-TOKEN": cookie_token}
        # Some apps also read the cookie name as header key (least likely, but cheap to try)
        if cookie_name:
            yield {cookie_name: cookie_token}
