# --- Playwright train capture (full function) ---
import asyncio, json, math, os, time
from datetime import datetime, timezone

PLACE_WORDS = (
    "station","siding","loop","yard","depot","junction","platform","crossing",
    "halt","terminal","shelter","works","mine","loader","silo"
)

def _num(v):
    try: 
        if v is None: return None
        x = float(v)
        if math.isnan(x): return None
        return x
    except Exception:
        return None

def _get(o, keys):
    for k in keys:
        if isinstance(o, dict) and k in o: 
            return o[k]
    return None

def _latlon(rec):
    # direct
    lat = _get(rec, ["lat","Lat","latitude","Latitude","LatDD","LatitudeDD","y","Y"])
    lon = _get(rec, ["lon","Lon","lng","Lng","longitude","Longitude","LonDD","LongitudeDD","long","Long","x","X"])
    lat, lon = _num(lat), _num(lon)
    if lat is not None and lon is not None: 
        return lat, lon
    # nested
    for key in ("position","pos","coords","coord","location","geo","Geo","geometry"):
        v = rec.get(key) if isinstance(rec, dict) else None
        if not isinstance(v, (dict, list)): 
            continue
        if isinstance(v, dict):
            la = _num(_get(v, ["lat","Lat","latitude","Latitude","LatDD","LatitudeDD"]))
            lo = _num(_get(v, ["lon","Lon","lng","Lng","longitude","Longitude","LonDD","LongitudeDD","long","Long"]))
            if la is not None and lo is not None: 
                return la, lo
            if v.get("type") == "Point" and isinstance(v.get("coordinates"), (list, tuple)) and len(v["coordinates"]) >= 2:
                lo, la = v["coordinates"][0], v["coordinates"][1]
                return _num(la), _num(lo)
        if isinstance(v, list) and len(v) >= 2:
            a, b = _num(v[0]), _num(v[1])
            if a is not None and b is not None:
                # heuristics: arrays could be [lon,lat] or [lat,lon]
                looks_lon = abs(a) >= 60 and abs(a) <= 180
                return (b, a) if looks_lon else (a, b)
    # GeoJSON Feature
    if rec.get("type") == "Feature" and rec.get("geometry", {}).get("type") == "Point":
        coords = rec["geometry"].get("coordinates") or []
        if len(coords) >= 2:
            lo, la = coords[0], coords[1]
            return _num(la), _num(lo)
    return None, None

def _parse_ts(v):
    if v is None: return None
    try:
        # ISO or numeric
        return int(datetime.fromisoformat(str(v).replace("Z","+00:00")).timestamp()*1000)
    except Exception:
        try:
            n = int(float(v))
            # assume seconds if too small
            if n < 10_000_000_000: n = n * 1000
            return n
        except Exception:
            return None

def _looks_place_text(s: str) -> bool:
    if not s: return False
    s = str(s).lower()
    return any(w in s for w in PLACE_WORDS)

def _is_train_like(rec):
    # Any dynamic hint counts as train-like
    speed = _num(_get(rec, ["speed","Speed","KPH","kph","kmh","velocity","Velocity"]))
    head  = _num(_get(rec, ["heading","Heading","Direction","bearing","course"]))
    ts    = _parse_ts(_get(rec, ["timestamp","Timestamp","Time","time","Updated","LastSeen","lastSeen"]))
    if speed is not None or head is not None or ts is not None:
        return True
    # Obvious static locations
    name = _get(rec, ["label","Label","title","Title","Name","name","Unit","Train"])
    oper = _get(rec, ["operator","Operator","company","Company","owner","Owner"])
    if _looks_place_text(name) or _looks_place_text(oper):
        return False
    # ID with letters+digits often a headcode/run
    idv = _get(rec, ["id","ID","Id","ServiceNumber","Headcode","HeadCode","TrainId","Run","Unit","Name"])
    if idv and any(c.isalpha() for c in str(idv)) and any(c.isdigit() for c in str(idv)):
        return True
    return False

def _build_key(rec, idx):
    for k in ["id","ID","Id","ServiceNumber","Headcode","HeadCode","TrainId","Run","Name","Unit","Consist"]:
        v = _get(rec, [k])
        if v: return str(v)
    # fallback
    return f"row_{idx}"

def _bearing(lon1, lat1, lon2, lat2):
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δλ = math.radians(lon2 - lon1)
    y = math.sin(Δλ) * math.cos(φ2)
    x = math.cos(φ1)*math.sin(φ2) - math.sin(φ1)*math.cos(φ2)*math.cos(Δλ)
    br = (math.degrees(math.atan2(y, x)) + 360) % 360
    return br

_last_pos = {}  # id -> (lon,lat)

def _normalize(rec, idx):
    lat, lon = _latlon(rec)
    if lat is None or lon is None:
        return None
    idv = _build_key(rec, idx)
    label = _get(rec, ["label","Label","Headcode","HeadCode","ServiceNumber","Train","Name","Unit"]) or idv
    oper  = _get(rec, ["operator","Operator","company","Company","owner","Owner"]) or ""
    head  = _num(_get(rec, ["heading","Heading","Direction","bearing","course"]))
    if head is None and idv in _last_pos:
        plon, plat = _last_pos[idv]
        head = _bearing(plon, plat, lon, lat)
    speed = _num(_get(rec, ["speed","Speed","KPH","kph","kmh","velocity","Velocity"]))
    ts    = _parse_ts(_get(rec, ["timestamp","Timestamp","Time","time","Updated","LastSeen","lastSeen"]))
    _last_pos[idv] = (lon, lat)
    return {
        "id": idv, "label": label, "operator": oper,
        "lat": lat, "lon": lon, "heading": head or 0, "speed": speed,
        "ts": ts
    }

def _rows_from_payload(payload):
    # Try obvious shapes
    if isinstance(payload, list): 
        return payload
    if isinstance(payload, dict):
        for k in ("trains","positions","vehicles","data","results","items","features"):
            if isinstance(payload.get(k), list):
                return payload[k]
        # FeatureCollection
        if payload.get("type") == "FeatureCollection" and isinstance(payload.get("features"), list):
            return payload["features"]
        # object of objects
        vals = list(payload.values())
        if vals and isinstance(vals[0], dict):
            return vals
    return None

async def fetch_trains_with_browser_once(referer: str, cookie_value: str, timeout_ms=15000):
    """
    Opens the referer in a real browser, captures JSON responses,
    picks one that looks like trains, normalizes, returns list.
    """
    from playwright.async_api import async_playwright

    trains = None
    UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"

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
                "name": "ASPXAUTH",
                "value": cookie_value,
                "domain": "trainfinder.otenko.com",
                "path": "/",
                "httpOnly": True,
                "secure": True
            }])

        page = await context.new_page()
        candidates = []

        page.on("response", lambda resp: None)  # just to register

        async def tap_response(resp):
            try:
                if resp.request.resource_type not in ("xhr","fetch"): 
                    return
                if resp.status != 200: 
                    return
                # only same-site or JSON content
                ctype = (resp.headers or {}).get("content-type","")
                if "json" not in ctype.lower():
                    # try to parse anyway if small
                    if int(resp.headers.get("content-length","0") or 0) > 1_000_000:
                        return
                data = await resp.json()
            except Exception:
                return

            rows = _rows_from_payload(data)
            if not rows or len(rows) < 3:
                return

            # how many look like trains?
            sampled = rows[:50]
            ll = 0; dyn = 0; places = 0
            for r in sampled:
                la, lo = _latlon(r)
                if la is not None and lo is not None:
                    ll += 1
                if _is_train_like(r):
                    dyn += 1
                name = _get(r, ["label","Label","Title","title","Name","Train","Unit"])
                if _looks_place_text(name): 
                    places += 1

            score = (dyn * 3) + (ll * 1) - (places * 2)
            candidates.append((score, rows))

        page.on("response", lambda resp: asyncio.create_task(tap_response(resp)))

        await page.goto(referer, wait_until="domcontentloaded", timeout=timeout_ms)
        # give network a moment to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(3)

        await context.close()
        await browser.close()

    # pick best candidate
    if candidates:
        candidates.sort(key=lambda t: t[0], reverse=True)
        raw_rows = candidates[0][1]

        # latest per train (by id/timestamp)
        now = int(time.time()*1000)
        latest = {}
        for i, r in enumerate(raw_rows):
            if not _is_train_like(r): 
                continue
            la, lo = _latlon(r)
            if la is None or lo is None: 
                continue
            k  = _build_key(r, i)
            ts = _parse_ts(_get(r, ["timestamp","Timestamp","Time","time","Updated","LastSeen","lastSeen"])) or 0
            if ts and (now - ts) > 45*60*1000: 
                continue
            prev = latest.get(k)
            if (not prev) or (ts >= prev.get("ts", 0)):
                latest[k] = {"rec": r, "ts": ts, "i": i}

        trains = []
        for v in latest.values():
            t = _normalize(v["rec"], v["i"])
            if t: trains.append(t)

    return trains or []