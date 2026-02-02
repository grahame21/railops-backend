import os
import json
import datetime
import requests

OUT_FILE = "trains.json"

# You said this XHR works in your browser:
TF_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

# Map page (used as Referer)
TF_REFERER = "https://trainfinder.otenko.com/home/nextlevel"


def write_output(trains, note=""):
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"Wrote {len(trains)} trains to {OUT_FILE} ({note})")


def get_proxies_from_env():
    """
    Optional ProxyMesh support.
    Add these repo secrets to enable:
      PROXYMESH_USER
      PROXYMESH_PASS
      PROXYMESH_HOST   (example: au.proxymesh.com:31280)
    """
    pm_user = (os.environ.get("PROXYMESH_USER") or "").strip()
    pm_pass = (os.environ.get("PROXYMESH_PASS") or "").strip()
    pm_host = (os.environ.get("PROXYMESH_HOST") or "").strip()

    if not (pm_user and pm_pass and pm_host):
        return None

    proxy_url = f"http://{pm_user}:{pm_pass}@{pm_host}"
    return {"http": proxy_url, "https": proxy_url}


def extract_list(data):
    """Try to find the array that contains train objects in unknown JSON shapes."""
    if not data:
        return []

    # if already a list
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        # common keys
        for k in ["trains", "Trains", "markers", "Markers", "items", "Items", "results", "Results", "data", "Data"]:
            v = data.get(k)
            if isinstance(v, list):
                return v

        # GeoJSON feature collection
        if data.get("type") == "FeatureCollection" and isinstance(data.get("features"), list):
            return data["features"]

        # sometimes nested
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v

    return []


def to_float(x):
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def norm_item(item, i):
    """
    Normalize to what your map layer accepts:
      id, lat, lon (+optional)
    Supports a few likely variations.
    """
    # GeoJSON Feature -> Point
    if isinstance(item, dict) and item.get("type") == "Feature":
        geom = item.get("geometry") or {}
        props = item.get("properties") or {}
        if geom.get("type") == "Point":
            coords = geom.get("coordinates") or []
            lon = to_float(coords[0]) if len(coords) > 0 else None
            lat = to_float(coords[1]) if len(coords) > 1 else None
            tid = props.get("id") or props.get("ID") or props.get("Name") or props.get("Unit") or f"train_{i}"
            return {
                "id": str(tid),
                "lat": lat,
                "lon": lon,
                "operator": props.get("operator") or props.get("Operator") or "",
                "heading": props.get("heading") or props.get("Heading") or 0,
                "timestamp": props.get("timestamp") or props.get("Timestamp") or None,
            }

    # Plain dict
    if not isinstance(item, dict):
        return None

    tid = item.get("id") or item.get("ID") or item.get("Name") or item.get("Unit") or item.get("Loco") or f"train_{i}"
    lat = to_float(item.get("lat") or item.get("Lat") or item.get("latitude") or item.get("Latitude") or item.get("y") or item.get("Y"))
    lon = to_float(item.get("lon") or item.get("Lon") or item.get("longitude") or item.get("Longitude") or item.get("x") or item.get("X"))

    return {
        "id": str(tid),
        "lat": lat,
        "lon": lon,
        "operator": item.get("operator") or item.get("Operator") or item.get("company") or item.get("Company") or "",
        "heading": item.get("heading") or item.get("Heading") or item.get("bearing") or item.get("Bearing") or 0,
        "timestamp": item.get("timestamp") or item.get("Timestamp") or item.get("updated") or item.get("Updated") or None,
    }


def main():
    cookie = (os.environ.get("TRAINFINDER_COOKIE") or "").strip()
    if not cookie:
        raise SystemExit("Missing TRAINFINDER_COOKIE secret")

    proxies = get_proxies_from_env()
    if proxies:
        print("Proxy: ENABLED")
    else:
        print("Proxy: not set (OK)")

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": TF_REFERER,
    })

    # Put cookie in header exactly as browser sends it
    s.headers["Cookie"] = cookie

    # IMPORTANT: don't follow redirects; TrainFinder will redirect you to /?ReturnUrl=...
    r = s.get(TF_URL, timeout=30, allow_redirects=False, proxies=proxies)

    ct = (r.headers.get("content-type") or "").lower()
    print("HTTP:", r.status_code)
    print("URL:", TF_URL)
    print("Content-Type:", ct)

    # Redirect = not logged in / blocked
    if r.status_code in (301, 302, 303, 307, 308):
        loc = r.headers.get("Location", "")
        print("Redirected to:", loc)
        write_output([], note=f"TrainFinder redirect (not logged in / blocked): {loc}")
        return

    # If not JSON, show snippet for debugging
    if "application/json" not in ct:
        snippet = (r.text or "")[:500].replace("\n", "\\n")
        print("Non-JSON response snippet:", snippet)
        write_output([], note=f"TrainFinder non-JSON (HTTP {r.status_code})")
        return

    # Parse JSON
    try:
        data = r.json()
    except Exception as e:
        print("JSON parse error:", repr(e))
        snippet = (r.text or "")[:500].replace("\n", "\\n")
        print("Body snippet:", snippet)
        write_output([], note="TrainFinder JSON parse error")
        return

    raw_list = extract_list(data)

    trains = []
    for i, item in enumerate(raw_list):
        n = norm_item(item, i)
        if not n:
            continue
        if n["lat"] is None or n["lon"] is None:
            continue
        trains.append(n)

    write_output(trains, note="ok")


if __name__ == "__main__":
    main()
