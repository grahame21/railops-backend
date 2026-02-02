import os, json, datetime
import requests

OUT_FILE = "trains.json"
TF_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

def write_output(trains, note=""):
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"Wrote {len(trains)} trains to {OUT_FILE}")

def main():
    cookie = os.environ.get("TRAINFINDER_COOKIE", "").strip()
    if not cookie:
        raise SystemExit("Missing TRAINFINDER_COOKIE secret")

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://trainfinder.otenko.com/home/nextlevel",
    })

    # Put cookie in the correct place
    s.headers["Cookie"] = cookie

    r = s.get(TF_URL, timeout=30, allow_redirects=True)

    ct = (r.headers.get("content-type") or "").lower()
    print("HTTP:", r.status_code)
    print("Final URL:", r.url)
    print("Content-Type:", ct)

    # If it isn't JSON, save a snippet to help diagnose (login page / block page etc)
    if "application/json" not in ct:
        snippet = (r.text or "")[:400].replace("\n", "\\n")
        print("Non-JSON response snippet:", snippet)
        # Still write an output so your site doesn't break
        write_output([], note=f"TrainFinder returned non-JSON (HTTP {r.status_code}). Likely login/block.")
        return

    # Try parse JSON
    data = r.json()

    # Try common list shapes
    trains_raw = None
    for key in ["trains", "Trains", "markers", "Markers", "items", "Items", "results", "Results", "data"]:
        if isinstance(data, dict) and isinstance(data.get(key), list):
            trains_raw = data[key]
            break
    if trains_raw is None and isinstance(data, list):
        trains_raw = data
    if trains_raw is None:
        trains_raw = []

    trains = []
    for i, t in enumerate(trains_raw):
        if not isinstance(t, dict):
            continue

        tid = t.get("id") or t.get("ID") or t.get("Name") or t.get("Loco") or t.get("Unit") or f"train_{i}"
        lat = t.get("lat") or t.get("Lat") or t.get("Latitude") or t.get("y") or t.get("Y")
        lon = t.get("lon") or t.get("Lon") or t.get("Longitude") or t.get("x") or t.get("X")

        try:
            lat = float(lat) if lat is not None else None
            lon = float(lon) if lon is not None else None
        except:
            lat = None
            lon = None

        if lat is None or lon is None:
            continue

        trains.append({
            "id": str(tid),
            "lat": lat,
            "lon": lon,
            "operator": t.get("Operator") or t.get("operator") or ""
        })

    write_output(trains, note="ok")

if __name__ == "__main__":
    main()
