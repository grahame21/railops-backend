import os, json, datetime
import requests

OUT_FILE = "trains.json"

# TrainFinder endpoint you previously confirmed works in your browser XHR:
TF_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"

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
        "Cookie": cookie,
    })

    r = s.get(TF_URL, timeout=30)
    r.raise_for_status()
    data = r.json()

    # TrainFinder response format can vary; this tries common shapes.
    # We'll output only what your map needs: id, lat, lon (+ optional extras).
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
            "operator": t.get("Operator") or t.get("operator") or "",
            "heading": t.get("Heading") or t.get("heading") or 0,
            "timestamp": t.get("Timestamp") or t.get("timestamp") or None,
        })

    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "trains": trains
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    print(f"Wrote {len(trains)} trains to {OUT_FILE}")

if __name__ == "__main__":
    main()
