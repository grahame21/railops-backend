def env_bounds():
    """Read TF_BOUNDS='south,west,north,east' or fall back to Australia-wide box."""
    raw = os.getenv("TF_BOUNDS", "").strip()
    if raw:
        try:
            s, w, n, e = [x.strip() for x in raw.split(",")]
            return s, w, n, e
        except Exception:
            pass
    # AU-wide default: south, west, north, east
    return "-44.0", "112.0", "-10.0", "154.0"

def fetch_raw():
    warmup()
    lat, lng, zm = parse_view_from_url(API_WARM)
    s, w, n, e = env_bounds()

    # Build a generous form with common key variants many map backends accept.
    form = {
        # exact-centre + zoom (from referer)
        "lat": lat or "-33.86",
        "lng": lng or "151.21",
        "zm":  zm or "7",

        # viewport rectangle (multiple aliases to be safe)
        "south": s, "west": w, "north": n, "east": e,
        "s": s, "w": w, "n": n, "e": e,
        "minLat": s, "minLng": w, "maxLat": n, "maxLng": e,
        "swLat": s, "swLng": w, "neLat": n, "neLng": e,

        # sometimes a combined bbox string is accepted
        "bbox": f"{s},{w},{n},{e}",
    }

    try:
        r = S.post(API_POST, data=form, timeout=30)
        log.info("POST %s (form=%s) -> %s", API_POST, {k: form[k] for k in ['lat','lng','zm','south','west','north','east']}, r.status_code)
        try:
            js = r.json()
        except Exception:
            log.error("Non-JSON response: %s", r.text[:500])
            return None
        if isinstance(js, dict):
            log.info("Sample JSON keys: %s", list(js.keys())[:8])
        with open(RAW_PATH, "w", encoding="utf-8") as f:
            json.dump(js, f, ensure_ascii=False)
        return js
    except Exception as e:
        log.exception("fetch_raw error: %s", e)
        return None
