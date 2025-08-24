# ---- server.py (full) ----
import os, json, time, math, asyncio, threading
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, send_file, Response
try:
    from flask_cors import CORS
    HAVE_CORS = True
except Exception:
    HAVE_CORS = False

# ---------- Config ----------
OUT_DIR = Path("/app/static")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "trains.json"

DEFAULT_REFERERS = (
    # Feel free to tweak/append; you can also set TRAINFINDER_REFERER in Render
    "https://trainfinder.otenko.com/home/nextlevel?lat=-30.0&lng=136.0&zm=6;"
    "https://trainfinder.otenko.com/home/nextlevel?lat=-25.5&lng=134.5&zm=6"
)

FETCH_INTERVAL_SEC = int(os.getenv("FETCH_INTERVAL_SEC", "60"))

# ---------- Utilities / Extractor (strict: only trains) ----------
PLACE_WORDS = {"station","siding","loop","yard","depot","junction","platform","crossing",
               "halt","terminal","shelter","works","mine","loader","silo"}

def _num(v):
    try:
        if v is None: return None
        x = float(v)
        if math.isnan(x): return None
        return x
    except Exception:
        return None

def _get(o, keys):
    if isinstance(keys, (list, tuple)):
        for k in keys:
            if isinstance(o, dict) and k in o: return o[k]
    else:
        if isinstance(o, dict) and keys in o: return o[keys]
    return None

def _latlon(r):
    lat = _num(_get(r, ["lat","Lat","latitude","Latitude","LatDD"]))
    lon = _num(_get(r, ["lon","Lon","lng","Lng","longitude","Longitude","LonDD","Long"]))
    if lat is not None and lon is not None: return lat, lon
    g = r.get("geometry") if isinstance(r,dict) else None
    if isinstance(g, dict) and g.get("type")=="Point" and isinstance(g.get("coordinates"), (list,tuple)) and len(g["coordinates"])>=2:
        lo, la = g["coordinates"][:2]; return _num(la), _num(lo)
    return None, None

def _parse_ts(v):
    if v is None: return None
    s = str(v)
    try:
        if s.endswith("Z"): s = s.replace("Z","+00:00")
        return int(datetime.fromisoformat(s).timestamp()*1000)
    except Exception:
        try:
            n = int(float(v))
            if n < 10_000_000_000: n *= 1000
            return n
        except Exception:
            return None

def _looks_place_text(s):
    if not s: return False
    s = str(s).lower()
    return any(w in s for w in PLACE_WORDS)

def _is_train_like(r):
    spd = _num(_get(r, ["speed","Speed","KPH","kph","kmh","velocity","Velocity"]))
    hdg = _num(_get(r, ["heading","Heading","Direction","bearing","course"]))
    ts  = _parse_ts(_get(r, ["timestamp","Timestamp","time","Time","Updated","LastSeen","lastSeen"]))
    if (spd is not None) or (hdg is not None) or (ts is not None):
        return True
    # obvious location text -> not a train
    name = _get(r, ["label","Label","title","Title","Name","Train","Unit"])
    oper = _get(r, ["operator","Operator","company","Company","owner","Owner"])
    if _looks_place_text(name) or _looks_place_text(oper): 
        return False
    return False  # strict: no dynamics => not a train

def _train_id(r, idx):
    for k in ["id","ID","Id","ServiceNumber","Headcode","HeadCode","TrainId","Run","Name","Unit","Consist"]:
        v = _get(r, k)
        if v: return str(v)
    return f"row_{idx}"

def _normalize(r, idx):
    la, lo = _latlon(r)
    if la is None or lo is None: return None
    return {
        "id": _train_id(r, idx),
        "label": _get(r, ["label","Label","Headcode","HeadCode","ServiceNumber","Train","Name","Unit"]) or _train_id(r, idx),
        "operator": _get(r, ["operator","Operator","company","Company","owner","Owner"]) or "",
        "lat": la, "lon": lo,
        "heading": _num(_get(r, ["heading","Heading","Direction","bearing","course"])) or 0,
        "speed": _num(_get(r, ["speed","Speed","KPH","kph","kmh","velocity","Velocity"])),
        "ts": _parse_ts(_get(r, ["timestamp","Timestamp","time","Time","Updated","LastSeen","lastSeen"]))
    }

def _all_arrays(obj, out=None):
    if out is None: out = []
    if isinstance(obj, list): 
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values(): _all_arrays(v, out)
    return out

def _score_array(rows):
    if not rows: return -1
    smp = rows[:80]
    dyn = plc = have_ll = 0
    for r in smp:
        if _is_train_like(r): dyn += 1
        name = _get(r, ["label","Label","title","Title","Name","Train","Unit"])
        if _looks_place_text(name): plc += 1
        la, lo = _latlon(r)
        if la is not None and lo is not None: have_ll += 1
    return (dyn*5) + (have_ll*1) - (plc*4)

def extract_trains_from_payload(payload, max_age_min=60):
    arrays = _all_arrays(payload)
    arrays.sort(key=_score_array, reverse=True)
    best = arrays[0] if arrays else None
    if not best or _score_array(best) < 10:
        return []
    now = int(time.time()*1000)
    latest = {}
    for i, r in enumerate(best):
        if not _is_train_like(r): 
            continue
        la, lo = _latlon(r)
        if la is None or lo is None: 
            continue
        t = _parse_ts(_get(r, ["timestamp","Timestamp","time","Time","Updated","LastSeen","lastSeen"])) or 0
        if t and (now - t) > max_age_min*60*1000: 
            continue
        k = _train_id(r, i)
        n = _normalize(r, i)
        if n and ((k not in latest) or ((n["ts"] or 0) >= (latest[k]["ts"] or 0))):
            latest[k] = n
    return list(latest.values())

# ---------- Playwright capture ----------
async def fetch_trains_with_browser_once(referer: str, cookie_value: str, timeout_ms=15000):
    from playwright.async_api import async_playwright
    UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    candidates = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 430, "height": 860},
            locale="en-AU",
            timezone_id="Australia/Adelaide"
        )
        if cookie_value:
            await context.add_cookies([{
                "name":"ASPXAUTH","value":cookie_value,
                "domain":"trainfinder.otenko.com","path":"/",
                "httpOnly":True,"secure":True
            }])
        page = await context.new_page()

        async def tap_response(resp):
            try:
                if resp.request.resource_type not in ("xhr","fetch"): 
                    return
                if resp.status != 200: 
                    return
                ctype = (resp.headers or {}).get("content-type","")
                if "json" not in ctype.lower():
                    if int(resp.headers.get("content-length","0") or 0) > 1_000_000:
                        return
                data = await resp.json()
            except Exception:
                return
            rows = extract_trains_from_payload(data)
            if rows and len(rows) >= 3:
                # score by count (simple)
                candidates.append((len(rows), rows))

        page.on("response", lambda resp: asyncio.create_task(tap_response(resp)))

        await page.goto(referer, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(3)

        await context.close()
        await browser.close()

    if candidates:
        candidates.sort(key=lambda t: t[0], reverse=True)
        return candidates[0][1]
    return []

# ---------- Periodic writer ----------
def _write_trains_file(trains):
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "trains": trains
    }
    OUT_PATH.write_text(json.dumps(payload), encoding="utf-8")
    print(f"{datetime.now(timezone.utc).isoformat()} wrote trains.json with {len(trains)} trains", flush=True)

async def fetch_and_write_once_async():
    referers = (os.getenv("TRAINFINDER_REFERER") or DEFAULT_REFERERS).split(";")
    cookie   = os.getenv("ASPXAUTH", "")
    for ref in map(str.strip, referers):
        if not ref: continue
        trains = await fetch_trains_with_browser_once(ref, cookie)
        if trains:
            _write_trains_file(trains)
            return
    # If nothing captured, keep previous file but log:
    print(f"{datetime.now(timezone.utc).isoformat()} no trains captured (check cookie/referer).", flush=True)

def background_loop():
    # create a placeholder file if missing
    if not OUT_PATH.exists():
        _write_trains_file([])
    # periodic run
    while True:
        try:
            asyncio.run(fetch_and_write_once_async())
        except Exception as e:
            print("Fetch cycle error:", e, flush=True)
        time.sleep(FETCH_INTERVAL_SEC)

# ---------- Flask app ----------
app = Flask(__name__, static_folder=str(OUT_DIR), static_url_path="")
if HAVE_CORS:
    CORS(app)  # allow your Netlify/any origin to GET /trains.json

@app.route("/")
def home():
    return jsonify({"ok": True, "message": "RailOps backend. GET /trains.json for live data."})

@app.route("/trains.json")
def trains_json():
    if not OUT_PATH.exists():
        _write_trains_file([])
    return send_file(str(OUT_PATH), mimetype="application/json")

@app.route("/healthz")
def health():
    return Response("ok", mimetype="text/plain")

# optional manual fetch trigger
@app.route("/force")
def force():
    try:
        asyncio.run(fetch_and_write_once_async())
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# start background on import
threading.Thread(target=background_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))