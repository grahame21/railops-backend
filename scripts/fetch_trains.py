# scripts/fetch_trains.py
# Fetch live TrainFinder viewport data and publish to deploy/trains.json

import os, sys, json
from pathlib import Path
import requests

# ---- Config from GitHub Actions secrets ----
URL = os.environ["TRAINFINDER_VIEWPORT_URL"]              # e.g. https://trainfinder.otenko.com/Home/GetViewPortData
METHOD = os.environ.get("TRAINFINDER_METHOD", "POST").upper()
POST_BODY_RAW = (os.environ.get("TRAINFINDER_POST_BODY") or "").strip()  # "{}" or "" for empty-body POST
HEADERS_JSON = os.environ.get("TRAINFINDER_HEADERS_JSON", "")
COOKIE_RAW = (os.environ.get("TRAINFINDER_COOKIE_RAW") or "").strip()
ASPX = (os.environ.get("TRAINFINDER_ASPXAUTH") or "").strip()

DEFAULT_HEADERS = {
    "accept": "*/*",
    "x-requested-with": "XMLHttpRequest",
    "user-agent": "Mozilla/5.0 (compatible; TrainTracker/2.0; +https://github.com/)",
    "referer": "https://trainfinder.otenko.com/home/nextlevel",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-fetch-dest": "empty",
}

def merged_headers():
    h = DEFAULT_HEADERS.copy()
    if HEADERS_JSON:
        try:
            extra = json.loads(HEADERS_JSON)
            for k, v in extra.items():
                if v is not None:
                    h[str(k).lower()] = str(v)
        except Exception as e:
            print(f"[WARN] Could not parse TRAINFINDER_HEADERS_JSON: {e}", file=sys.stderr)

    # Remove problematic headers
    for bad in ("content-length", "host"):
        h.pop(bad, None)

    # Ensure content-type only when sending real JSON body
    if METHOD == "POST" and POST_BODY_RAW and POST_BODY_RAW not in ("{}", "null"):
        h.setdefault("content-type", "application/json")

    # Title-case for requests
    return {"-".join(p.capitalize() for p in k.split("-")): v for k, v in h.items()}

def build_auth(headers):
    # Prefer full raw Cookie string if provided
    if COOKIE_RAW:
        headers["Cookie"] = COOKIE_RAW
        return None, headers
    if ASPX:
        return {".ASPXAUTH": ASPX}, headers
    raise RuntimeError("Missing auth: set TRAINFINDER_COOKIE_RAW or TRAINFINDER_ASPXAUTH")

def fetch_once():
    headers = merged_headers()
    cookies_dict, headers = build_auth(headers)

    if METHOD == "POST":
        # If captured curl showed content-length: 0 -> send no body
        if not POST_BODY_RAW or POST_BODY_RAW in ("{}", "null"):
            r = requests.post(URL, headers=headers, cookies=cookies_dict, timeout=45)
        else:
            try:
                payload = json.loads(POST_BODY_RAW)
            except Exception:
                payload = None
            if isinstance(payload, (dict, list)):
                r = requests.post(URL, headers=headers, cookies=cookies_dict, json=payload, timeout=45)
            else:
                r = requests.post(URL, headers=headers, cookies=cookies_dict, data=POST_BODY_RAW, timeout=45)
    else:
        r = requests.get(URL, headers=headers, cookies=cookies_dict, timeout=45)

    if r.status_code >= 400:
        snippet = r.text[:800].replace("\n", " ")
        print(f"[DEBUG] HTTP {r.status_code}. Body: {snippet}", file=sys.stderr)
    r.raise_for_status()

    try:
        return r.json()
    except requests.JSONDecodeError:
        txt = r.text[:800].replace("\n", " ")
        raise RuntimeError(f"Non-JSON response. Status {r.status_code}. Body: {txt}")

def write_no_cache_headers(out_dir: Path):
    # Netlify headers for CORS + no-cache
    (out_dir / "_headers").write_text(
        "/trains.json\n"
        "  Cache-Control: no-store, no-cache, must-revalidate, max-age=0\n"
        "  Pragma: no-cache\n"
        "  Expires: 0\n"
        "  Access-Control-Allow-Origin: *\n"
        "  Access-Control-Allow-Methods: GET, OPTIONS\n"
        "  Access-Control-Allow-Headers: *\n",
        encoding="utf-8"
    )

def main():
    out_dir = Path("deploy")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "trains.json"

    try:
        data = fetch_once()

        # Optional: log likely arrays to help debug shape
        def list_arrays(obj, path="$", out=[]):
            if isinstance(obj, list):
                out.append((path, len(obj)))
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    list_arrays(v, f"{path}.{k}", out)
            return out
        cands = sorted(list_arrays(data), key=lambda x: (-x[1], x[0]))[:8]
        if cands:
            print("[INFO] Top arrays by length:")
            for p, ln in cands:
                print(f"  len={ln:5d} path={p}")

        out_file.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8"
        )
        write_no_cache_headers(out_dir)
        print(f"[OK] Wrote {out_file} ({out_file.stat().st_size} bytes)")
        return 0

    except Exception as e:
        print(f"[WARN] fetch failed: {e}", file=sys.stderr)
        if out_file.exists():
            print("[INFO] Keeping previous trains.json")
            write_no_cache_headers(out_dir)
            return 0
        print("[ERROR] No previous trains.json exists to keep", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
