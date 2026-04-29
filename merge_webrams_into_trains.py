import os
import re
import json
from datetime import datetime, timezone


DATA_DIR = "data"
LIVE_TRAINS_FILE = os.path.join(DATA_DIR, "trains.json")
WEBRAMS_FILE = os.path.join(DATA_DIR, "webrams_consists.json")
OUT_FILE = os.path.join(DATA_DIR, "trains_enriched.json")


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_id(value):
    return clean_text(value).upper()


def candidate_train_ids(train):
    vals = [
        train.get("train_number"),
        train.get("trainNumber"),
        train.get("train_id"),
        train.get("trainId"),
        train.get("service_number"),
        train.get("serviceNumber"),
        train.get("id"),
        train.get("ID"),
        train.get("trKey"),
        train.get("train_name"),
        train.get("trainName"),
    ]
    out = []
    for v in vals:
        nv = normalize_id(v)
        if nv:
            out.append(nv)
    return list(dict.fromkeys(out))


def best_loco_string(consist_rows):
    if not consist_rows:
        return ""

    loco_classes = {"NR", "81", "82", "90", "AN", "DL", "6000", "6020", "SCT", "G", "GT", "CLF", "CLP"}

    parts = []
    for row in consist_rows:
        cls = clean_text(row.get("class"))
        num = clean_text(row.get("number"))
        if not cls and not num:
            continue

        # Keep it broad; if it looks like rollingstock, still include it in raw list
        item = f"{cls}{num}".strip()
        item = item.replace(" ", "")
        if item:
            parts.append(item)

    return " ".join(parts)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    if not os.path.exists(LIVE_TRAINS_FILE):
        raise FileNotFoundError(f"Missing live trains file: {LIVE_TRAINS_FILE}")

    if not os.path.exists(WEBRAMS_FILE):
        raise FileNotFoundError(f"Missing WebRAMS file: {WEBRAMS_FILE}")

    live = load_json(LIVE_TRAINS_FILE)
    wr = load_json(WEBRAMS_FILE)

    live_trains = live.get("trains", [])
    wr_trains = wr.get("trains", [])

    wr_index = {}
    for item in wr_trains:
        tid = normalize_id(item.get("train_id"))
        if tid:
            wr_index[tid] = item

    enriched = []
    matched = 0

    for train in live_trains:
        tcopy = dict(train)
        ids = candidate_train_ids(train)
        wr_match = None

        for tid in ids:
            if tid in wr_index:
                wr_match = wr_index[tid]
                break

        if wr_match:
            matched += 1
            tcopy["webrams"] = {
                "matched": True,
                "train_id": wr_match.get("train_id", ""),
                "train_date": wr_match.get("train_date", ""),
                "operator": wr_match.get("operator", ""),
                "origin": wr_match.get("origin", ""),
                "destination": wr_match.get("destination", ""),
                "account_label": wr_match.get("account_label", ""),
                "incidents_total_delay": wr_match.get("incidents_total_delay", ""),
                "progress": wr_match.get("progress", []),
                "consist": wr_match.get("consist", []),
                "incidents": wr_match.get("incidents", []),
                "consist_string": best_loco_string(wr_match.get("consist", [])),
            }
        else:
            tcopy["webrams"] = {
                "matched": False,
                "train_id": "",
                "consist": [],
                "incidents": [],
                "progress": [],
                "consist_string": "",
            }

        enriched.append(tcopy)

    output = {
        "lastUpdated": live.get("lastUpdated", utc_now_iso()),
        "mergedAt": utc_now_iso(),
        "matchedWebRAMSCount": matched,
        "totalLiveTrains": len(live_trains),
        "trains": enriched
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved {OUT_FILE}")
    print(f"Matched {matched} / {len(live_trains)} live trains")


if __name__ == "__main__":
    main()