# ---- STRICT train extractor (drop-in) ----
import math, time, json
from datetime import datetime, timezone

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
    for k in (keys if isinstance(keys,(list,tuple)) else [keys]):
        if isinstance(o, dict) and k in o: return o[k]
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
            n = int(float(v));  # secs?
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
    return False  # be strict: no dynamics => not a train

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
    # higher = more train-like
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
        return []  # nothing train-like
    # latest per id and fresh
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
        if (k not in latest) or (t >= latest[k].get("ts", 0)):
            latest[k] = _normalize(r, i)
    return [v for v in latest.values() if v]