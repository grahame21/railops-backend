#!/usr/bin/env python3
"""
sweep_trains.py
Full-Australia tiled sweep of TrainFinder GetViewPortData, aggregate results and write trains.json.

Usage:
  # one sweep (use cookie.txt)
  python sweep_trains.py

  # continuous loop (randomized 30-90s between sweeps)
  python sweep_trains.py --loop
"""
import requests, json, time, random, sys
from pathlib import Path
from math import ceil

BASE = "https://trainfinder.otenko.com"
COOKIE_FILE = Path("cookie.txt")   # should contain ASPX auth cookie value
OUT_FILE = Path("trains.json")

# Australia bounding box (rough)
# lon, lat pairs (west, north, east, south)
AUS_W, AUS_N, AUS_E, AUS_S = 112.0, -9.0, 154.0, -44.0

# tile size in degrees (lon x lat). Tune for fetch granularity.
# smaller tile => more requests. Start with 2.0 (about 200km width) and adjust.
TILE_DEG = 2.5

# POST payload zoom level that works with TrainFinder (6-8 recommended)
DEFAULT_ZOOM = 7

# delay between each tile request (random range in seconds)
TILE_DELAY_MIN = 0.8
TILE_DELAY_MAX = 2.5

# If you do continuous sweeps, sleep between sweeps (random 30-90 s by user's request).
SWEEP_SLEEP_MIN = 30
SWEEP_SLEEP_MAX = 90

HEADERS_BASE = {
    "Accept": "*/*",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Origin": BASE,
    "Referer": f"{BASE}/Home/NextLevel",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "X-Requested-With": "XMLHttpRequest",
}

def load_session_from_cookie():
    if not COOKIE_FILE.exists():
        raise FileNotFoundError("cookie.txt not found. Create cookie.txt with .ASPXAUTH value or use login helper.")
    token = COOKIE_FILE.read_text().strip()
    s = requests.Session()
    # use cookie name used earlier; if different, update accordingly
    s.cookies.set(".ASPXAUTH", token, domain="trainfinder.otenko.com", path="/")
    return s

def tile_grid(west, north, east, south, tile_deg):
    """Yield tile boxes in (nwLat, nwLng, seLat, seLng) form required by endpoint."""
    lon_count = ceil((east - west) / tile_deg)
    lat_count = ceil((north - south) / tile_deg)
    for i in range(lon_count):
        lon0 = west + i * tile_deg
        lon1 = min(east, lon0 + tile_deg)
        for j in range(lat_count):
            lat1 = north - j * tile_deg  # top
            lat0 = max(south, lat1 - tile_deg)  # bottom
            # viewport expects nwLat, nwLng, seLat, seLng (north-west and south-east)
            yield (lat1, lon0, lat0, lon1)

def fetch_viewport(session, nwLat, nwLng, seLat, seLng, zm=DEFAULT_ZOOM):
    payload = {
        "nwLat": float(nwLat),
        "nwLng": float(nwLng),
        "seLat": float(seLat),
        "seLng": float(seLng),
        "zm": int(zm)
    }
    r = session.post(f"{BASE}/Home/GetViewPortData", headers=HEADERS_BASE, data=payload, timeout=30)
    if not r.ok:
        # return None with status code info
        return {"error": f"HTTP {r.status_code}", "text": r.text[:400]}
    try:
        return r.json()
    except Exception as e:
        return {"error": f"JSON decode error: {e}", "text": r.text[:400]}

def merge_results(master, partial):
    """Merge partial response into master dictionary keyed by train id where available."""
    # structure returned by TrainFinder may have lists in different keys; we'll merge by id where present.
    if not isinstance(partial, dict):
        return
    for k,v in partial.items():
        if v is None:
            continue
        if isinstance(v, list):
            if k not in master or master[k] is None:
                master[k] = []
            master_ids = { (x.get("id") or x.get("vehicleId") or json.dumps(x, sort_keys=True)) : x for x in master[k] }
            for item in v:
                key = item.get("id") or item.get("vehicleId") or json.dumps(item, sort_keys=True)
                if key not in master_ids:
                    master[k].append(item)
                    master_ids[key] = item
        elif isinstance(v, dict):
            if k not in master or master[k] is None:
                master[k] = {}
            # shallow merge keys
            master[k].update(v)
        else:
            # primitive - keep existing if exists
            if k not in master or master[k] is None:
                master[k] = v

def do_sweep(session, west=AUS_W, north=AUS_N, east=AUS_E, south=AUS_S, tile_deg=TILE_DEG, verbose=True):
    master = {}
    tiles = list(tile_grid(west,north,east,south,tile_deg))
    if verbose:
        print(f"Starting sweep: {len(tiles)} tiles (tile {tile_deg}°).")
    for idx, (nwLat, nwLng, seLat, seLng) in enumerate(tiles, start=1):
        if verbose:
            print(f"[{idx}/{len(tiles)}] tile nw=({nwLat:.4f},{nwLng:.4f}) se=({seLat:.4f},{seLng:.4f})")
        partial = fetch_viewport(session, nwLat, nwLng, seLat, seLng)
        if isinstance(partial, dict) and partial.get("error"):
            # log but continue
            print(f"  -> tile error: {partial['error']}")
        else:
            merge_results(master, partial)
        # polite delay between tiles
        time.sleep(random.uniform(TILE_DELAY_MIN, TILE_DELAY_MAX))
    # save
    OUT_FILE.write_text(json.dumps(master, indent=2))
    if verbose:
        print(f"Saved {OUT_FILE} ({OUT_FILE.stat().st_size} bytes).")
    return master

def loop_mode(session):
    print("Entering loop mode. Press Ctrl-C to stop.")
    try:
        while True:
            start = time.time()
            do_sweep(session)
            took = time.time() - start
            sleep_for = random.uniform(SWEEP_SLEEP_MIN, SWEEP_SLEEP_MAX)
            print(f"Sweep took {took:.1f}s. Sleeping {sleep_for:.1f}s before next sweep.")
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        print("Loop interrupted by user.")

def main():
    loop = "--loop" in sys.argv or "-l" in sys.argv
    # load session
    session = load_session_from_cookie()
    if loop:
        loop_mode(session)
    else:
        do_sweep(session)

if __name__ == "__main__":
    main()
