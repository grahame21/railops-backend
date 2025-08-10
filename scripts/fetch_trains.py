import os, sys, json
from pathlib import Path
import requests

URL = os.environ["TRAINFINDER_VIEWPORT_URL"]
ASPX = os.environ.get("TRAINFINDER_ASPXAUTH")
METHOD = os.environ.get("TRAINFINDER_METHOD", "GET").upper()
POST_BODY_RAW = os.environ.get("TRAINFINDER_POST_BODY")
HEADERS_JSON = os.environ.get("TRAINFINDER_HEADERS_JSON")
COOKIE_RAW = os.environ.get("TRAINFINDER_COOKIE_RAW")

DEFAULT_HEADERS = {
    "accept": "*/*",
    "x-requested-with": "XMLHttpRequest",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 TrainTracker/2.0 (GitHub Actions)",
    "referer": "https://trainfinder.otenko.com/home/nextlevel",
}

def merged_headers():
    h = DEFAULT_HEADERS.copy()
    if HEADERS_JSON:
        try:
            extra = json.loads(HEADERS_JSON)
            for k, v in extra.items():
                if v is not None:
                    h[str(k).lower()] = str(v)
            h = {"-".join(p.capitalize() for p in k.split("-")): v for k, v in h.items()}
        except Exception as e:
            print(f"[WARN] Bad TRAINFINDER_HEADERS_JSON: {e}", file=sys.stderr)
    return h

def build_cookies_and_headers(headers):
    if COOKIE_RAW:
        headers["Cookie"] = COOKIE_RAW
        return None, headers
    if not ASPX:
        raise RuntimeError("Provide TRAINFINDER_COOKIE_RAW or TRAINFINDER_ASPXAUTH")
    return {".ASPXAUTH": ASPX}, headers

def fetch_once():
    headers = merged_headers()
    cookies_dict, headers = build_cookies_and_headers(headers)

    if METHOD == "POST":
        json_body = json.loads(POST_BODY_RAW) if POST_BODY_RAW else None
        headers.setdefault("Content-Type", "application/json")
        r = requests.post(URL, headers=headers, cookies=cookies_dict, json=json_body, timeout=45)
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
        out_file.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
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
