import os, re, math, json, asyncio
from flask import Flask, request, jsonify
import requests

# Optional: Playwright is only imported when /snapshot is called
from playwright.async_api import async_playwright

UP = "https://trainfinder.otenko.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"

app = Flask(__name__)
ASPXAUTH = os.environ.get("ASPXAUTH", "").strip()

def set_cookie(val: str) -> None:
    global ASPXAUTH
    ASPXAUTH = (val or "").strip()

# ---------- basic helpers ----------
def new_session(lat: float, lng: float, zm: int):
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8,en-AU;q=0.7",
        "Accept": "*/*",
    })
    if ASPXAUTH:
        s.cookies.set(".ASPXAUTH", ASPXAUTH, domain="trainfinder.otenko.com", secure=True)
    return s

def try_viewport_forms(s, lat, lng, zm, token=""):
    def _hdr():
        h = {
            "Origin": UP,
            "Referer": f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": UA,
        }
        if token:
            h["RequestVerificationToken"] = token
        return h

    forms = [
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zm": str(zm)},
        {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "zoomLevel": str(zm)},
    ]
    out = []
    for form in forms:
        r = s.post(f"{UP}/Home/GetViewPortData", headers=_hdr(), data=form, timeout=20)
        txt = (r.text or "")[:200]
        looks_html = txt.strip().startswith("<!DOCTYPE") or txt.strip().startswith("<html")
        rec = {"status": r.status_code, "bytes": len(r.content), "looks_like_html": looks_html, "preview": txt}
        try:
            j = r.json()
        except Exception:
            j = None
        if isinstance(j, dict):
            rec["keys"] = list(j.keys())
            rec["json"] = j
        out.append(rec)
    return out

# ---------- endpoints ----------
@app.get("/")
def root():
    return "RailOps JSON is up", 200

@app.get("/set-aspxauth")
def set_aspxauth():
    val = request.args.get("value","").strip()
    set_cookie(val)
    return jsonify({"ok": True, "len": len(val)}), 200

@app.get("/authcheck")
def authcheck():
    s = new_session(-33.8688, 151.2093, 12)
    r = s.post(f"{UP}/Home/IsLoggedIn",
               headers={"X-Requested-With":"XMLHttpRequest",
                        "Origin": UP,
                        "Referer": f"{UP}/Home/NextLevel?lat=-33.868800&lng=151.209300&zm=12"},
               data={},
               timeout=20)
    try:
        data = r.json()
    except Exception:
        data = {"error":"bad json","text": r.text[:200]}
    return jsonify({
        "status": r.status_code,
        "text": json.dumps(data),
        "cookie_present": bool(ASPXAUTH),
        "email": (data.get("email_address") if isinstance(data, dict) else "") or "",
        "is_logged_in": bool(data.get("is_logged_in")) if isinstance(data, dict) else False,
        "bytes": len(r.content)
    })

@app.get("/diag")
def diag():
    lat = float(request.args.get("lat","-33.8688"))
    lng = float(request.args.get("lng","151.2093"))
    zm = int(float(request.args.get("zm","12")))
    s = new_session(lat, lng, zm)
    warm = s.get(f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}", timeout=20)
    html = warm.text or ""
    token = ""
    for p in [
        r'name="__RequestVerificationToken"\s+value="([^"]+)"',
        r'RequestVerificationToken["\']\s*[:=]\s*["\']([^"\']+)["\']',
    ]:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            token = m.group(1); break
    cookie_token = any(c.name.lower().startswith("__requestverificationtoken") for c in s.cookies)
    vp = try_viewport_forms(s, lat, lng, zm, token)
    return jsonify({
        "cookie_present": bool(ASPXAUTH),
        "token_detected": {"cookie": cookie_token, "header_token": bool(token)},
        "warmup_bytes": len(html),
        "warmup_preview": html[:400],
        "viewport": vp
    })

@app.get("/trains")
def trains():
    lat = float(request.args.get("lat","-33.8688"))
    lng = float(request.args.get("lng","151.2093"))
    zm = int(float(request.args.get("zm","12")))
    s = new_session(lat, lng, zm)
    # Basic attempt (what you’re seeing today = tiny JSON)
    out = try_viewport_forms(s, lat, lng, zm)
    for rec in out:
        if isinstance(rec.get("json"), dict):
            return jsonify(rec["json"])
    return jsonify({"favs":None,"alerts":None,"places":None,"tts":None,"webcams":None,"atcsGomi":None,"atcsObj":None})

# ---------- headless browser probe ----------
async def _snapshot_async(lat: float, lng: float, zm: int):
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = await browser.new_context(user_agent=UA)
        if ASPXAUTH:
            await ctx.add_cookies([{
                "name": ".ASPXAUTH",
                "value": ASPXAUTH,
                "domain": "trainfinder.otenko.com",
                "path": "/",
                "secure": True,
                "httpOnly": False
            }])
        page = await ctx.new_page()

        # Collect any XHR/Fetch responses the page makes
        async def on_response(resp):
            url = resp.url
            if "trainfinder.otenko.com" in url and ("/Home/" in url or "/api/" in url):
                try:
                    txt = await resp.text()
                    looks_html = (txt.strip().startswith("<!DOCTYPE") or txt.strip().startswith("<html"))
                    rec = {
                        "url": url,
                        "status": resp.status,
                        "bytes": len(txt.encode("utf-8", errors="ignore")),
                        "looks_like_html": looks_html,
                        "preview": txt[:300]
                    }
                    # Try JSON parse
                    try:
                        j = json.loads(txt)
                        rec["json_keys"] = list(j.keys()) if isinstance(j, dict) else None
                        rec["is_nonempty_json"] = bool(j) and (isinstance(j, list) or (isinstance(j, dict) and any(j.values())))
                    except Exception:
                        pass
                    results.append(rec)
                except Exception:
                    pass

        page.on("response", on_response)

        url = f"{UP}/Home/NextLevel?lat={lat:.6f}&lng={lng:.6f}&zm={zm}"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Try to trigger the site’s own viewport call from inside the page
        fetch_js = """
        (lat, lng, zm) => fetch('/Home/GetViewPortData', {
          method: 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
          },
          body: new URLSearchParams({ lat: lat.toFixed(6), lng: lng.toFixed(6), zoomLevel: String(zm) })
        }).then(r => r.text()).then(t => ({ ok: true, text: t.substring(0, 500) })).catch(e => ({ ok: false, error: String(e) }))
        """
        try:
            resp = await page.evaluate(fetch_js, lat, lng, zm)
            results.append({"url": "/Home/GetViewPortData (page.fetch)", **resp})
        except Exception as e:
            results.append({"url": "/Home/GetViewPortData (page.fetch)", "ok": False, "error": str(e)})

        # small idle wait to let any other XHRs fire
        await page.wait_for_timeout(1200)

        await ctx.close()
        await browser.close()
    return results

@app.get("/snapshot")
def snapshot():
    lat = float(request.args.get("lat","-33.8688"))
    lng = float(request.args.get("lng","151.2093"))
    zm = int(float(request.args.get("zm","12")))
    try:
        data = asyncio.run(_snapshot_async(lat, lng, zm))
        return jsonify({"ok": True, "count": len(data), "items": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","10000")))
