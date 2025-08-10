# scripts/update_trains.py
import os, sys, json
from pathlib import Path
import requests

# Required env vars (added as GitHub Secrets)
TRAINFINDER_VIEWPORT_URL = os.environ["TRAINFINDER_VIEWPORT_URL"]  # full URL from DevTools
TRAINFINDER_ASPXAUTH = os.environ["TRAINFINDER_ASPXAUTH"]          # cookie value only

# Optional
HTTP_PROXY_URL = os.environ.get("HTTP_PROXY_URL")                  # e.g. http://user:pass@host:31280
TRAINFINDER_METHOD = os.environ.get("TRAINFINDER_METHOD", "GET").upper()  # "GET" or "POST"
TRAINFINDER_POST_BODY = os.environ.get("TRAINFINDER_POST_BODY")    # JSON string if POST

DEFAULT_HEADERS = {
    "accept": "*/*",
    "x-requested-with": "XMLHttpRequest",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 TrainTracker/2.0 (GitHub Actions)",
    "referer": "https://trainfinder.otenko.com/home/nextlevel",
}

def fetch_once():
    proxies = {"http": HTTP_PROXY_URL, "https": HTTP_PROXY_URL} if HTTP_PROXY_URL else None
    cookies = {".ASPXAUTH": TRAINFINDER_ASPXAUTH}

    if TRAINFINDER_METHOD == "POST":
        # If TrainFinder uses POST with a JSON body for your account, put the raw JSON in the secret TRAINFINDER_POST_BODY
        json_body = None
        if TRAINFINDER_POST_BODY:
            try:
                json_body = json.loads(TRAINFINDER_POST_BODY)
            except Exception as e:
                raise RuntimeError(f"Invalid TRAINFINDER_POST_BODY JSON: {e}")
        r = requests.post(
            TRAINFINDER_VIEWPORT_URL,
            headers={**DEFAULT_HEADERS, "content-type": "application/json"},
            cookies=cookies,
            json=json_body,
            timeout=40,
            proxies=proxies,
        )
    else:
        r = requests.get(
            TRAINFINDER_VIEWPORT_URL,
            headers=DEFAULT_HEADERS,
            cookies=cookies,
            timeout=40,
            proxies=proxies,
        )

    r.raise_for_status()
    return r.json()  # will raise if not JSON

def write_no_cache_headers(out_dir: Path):
    # Netlify _headers file to disable caching for trains.json
    # https://docs.netlify.com/routing/headers/#custom-headers
    headers_file = out_dir / "_headers"
    headers_file.write_text(
        "/trains.json\n"
        "  Cache-Control: no-store, no-cache, must-revalidate, max-age=0\n"
        "  Pragma: no-cache\n"
        "  Expires: 0\n"
    , encoding="utf-8")

def main():
    out_dir = Path("deploy")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "trains.json"

    try:
        data = fetch_once()
        # If you need to transform the payload for your frontend, do it here before writing.
        out_file.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        write_no_cache_headers(out_dir)
        print(f"[OK] Wrote {out_file} ({out_file.stat().st_size} bytes)")
        return 0
    except Exception as e:
        print(f"[WARN] fetch failed: {e}", file=sys.stderr)
        # keep last good file if present
        if out_file.exists():
            print("[INFO] Keeping previous trains.json")
            write_no_cache_headers(out_dir)
            return 0
        print("[ERROR] No previous trains.json exists to keep", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
