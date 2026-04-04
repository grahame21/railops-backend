import os
import json
import datetime
import csv
from typing import Dict, Any, Set

TRAINS_FILE = "trains.json"
LOCOS_FILE = "locos.json"
HISTORY_FILE = "loco_history.json"
EXPORT_FILE = "loco_export.csv"
SUMMARY_FILE = "loco_summary.txt"
BLOCKED_FILE = "blocked_locos.txt"
BLOCKED_DESCRIPTIONS_FILE = "blocked_descriptions.txt"


SKIP_PREFIXES = (
    "ARROWMARKERSSOURCE_",
    "MARKERSOURCE_",
    "REGTRAINSSOURCE_",
    "UNREGTRAINSSOURCE_",
    "TRAINSOURCE_",
)


def is_real_loco_id(value: str) -> bool:
    loco = normalize_loco(value)
    if not loco:
        return False
    return not any(prefix in loco for prefix in SKIP_PREFIXES)


def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Failed to load {filename}: {e}")
            return {}
    return {}


def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Failed to save {filename}: {e}")


def normalize_loco(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_blocked_locos() -> Set[str]:
    blocked: Set[str] = set()
    if not os.path.exists(BLOCKED_FILE):
        return blocked

    with open(BLOCKED_FILE, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            blocked.add(normalize_loco(line))
    return blocked


def load_blocked_descriptions() -> Set[str]:
    blocked: Set[str] = set()
    if not os.path.exists(BLOCKED_DESCRIPTIONS_FILE):
        return blocked

    with open(BLOCKED_DESCRIPTIONS_FILE, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip().lower()
            if not line or line.startswith("#"):
                continue
            blocked.add(line)
    return blocked


def description_is_blocked(description: Any, blocked_descriptions: Set[str]) -> bool:
    desc = clean_text(description).lower()
    if not desc or not blocked_descriptions:
        return False
    return any(term in desc for term in blocked_descriptions)


def extract_vehicle_description(train: Dict[str, Any], previous_data: Dict[str, Any]) -> str:
    return clean_text(
        train.get("vehicle_description")
        or train.get("vehicleDescription")
        or train.get("description")
        or train.get("desc")
        or previous_data.get("vehicle_description")
        or previous_data.get("last_description")
        or ""
    )


def extract_current_operator(train: Dict[str, Any], previous_data: Dict[str, Any]) -> str:
    return clean_text(
        train.get("current_operator")
        or train.get("currentOperator")
        or train.get("operator")
        or previous_data.get("current_operator")
        or ""
    )


def purge_blocked_records(
    locos: Dict[str, Any],
    history: Dict[str, Any],
    blocked: Set[str],
    blocked_descriptions: Set[str],
):
    removed_from_locos = 0
    removed_from_history = 0
    blocked_by_description = set()

    for loco_id in list(locos.keys()):
        data = locos.get(loco_id, {}) if isinstance(locos.get(loco_id), dict) else {}
        description = data.get("vehicle_description") or data.get("last_description") or ""

        if normalize_loco(loco_id) in blocked or description_is_blocked(description, blocked_descriptions):
            if description_is_blocked(description, blocked_descriptions):
                blocked_by_description.add(normalize_loco(loco_id))
            del locos[loco_id]
            removed_from_locos += 1

    history_locos = history.get("locos", {}) if isinstance(history, dict) else {}
    if isinstance(history_locos, dict):
        for loco_id in list(history_locos.keys()):
            if normalize_loco(loco_id) in blocked or normalize_loco(loco_id) in blocked_by_description:
                del history_locos[loco_id]
                removed_from_history += 1

    return removed_from_locos, removed_from_history


def export_to_csv(locos):
    visible_keys = sorted(locos.keys(), key=lambda x: str(x).upper())
    fieldnames = [
        "Loco Number",
        "Current Operator",
        "Vehicle Description",
        "Date/Time Added",
        "First Seen",
        "Last Seen",
        "Last Date",
        "Last Time",
        "Latitude",
        "Longitude",
        "Speed",
        "Origin",
        "Destination",
        "Total Sightings",
        "cId",
        "servId",
        "trKey",
    ]

    try:
        with open(EXPORT_FILE, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for loco_id in visible_keys:
                data = locos[loco_id]
                if not isinstance(data, dict):
                    continue

                writer.writerow(
                    {
                        "Loco Number": loco_id,
                        "Current Operator": data.get("current_operator", ""),
                        "Vehicle Description": data.get("vehicle_description", ""),
                        "Date/Time Added": data.get("date_time_added") or data.get("first_seen", "Unknown"),
                        "First Seen": data.get("first_seen", "Unknown"),
                        "Last Seen": data.get("last_seen", ""),
                        "Last Date": data.get("last_date", ""),
                        "Last Time": data.get("last_time", ""),
                        "Latitude": data.get("last_location", {}).get("lat", ""),
                        "Longitude": data.get("last_location", {}).get("lon", ""),
                        "Speed": data.get("last_speed", 0),
                        "Origin": data.get("last_origin", ""),
                        "Destination": data.get("last_destination", ""),
                        "Total Sightings": data.get("total_sightings", 0),
                        "cId": data.get("cId", ""),
                        "servId": data.get("servId", ""),
                        "trKey": data.get("trKey", ""),
                    }
                )

        print(f"✅ Exported {len(visible_keys)} locos to {EXPORT_FILE}")
        print(f"📁 CSV path: {os.path.abspath(EXPORT_FILE)}")
        return True

    except Exception as e:
        print(f"❌ Failed to export CSV: {e}")
        return False


def create_summary(locos):
    try:
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"LOCO DATABASE SUMMARY - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Total Locomotives Tracked: {len(locos)}\n\n")

            sorted_locos = sorted(
                locos.items(),
                key=lambda x: x[1].get("last_seen", ""),
                reverse=True,
            )

            for loco_id, data in sorted_locos[:50]:
                f.write(f"\n{'=' * 40}\n")
                f.write(f"LOCO: {loco_id}\n")
                f.write(f"{'=' * 40}\n")
                f.write(f"  Date/Time Added: {data.get('date_time_added') or data.get('first_seen', 'Unknown')}\n")
                f.write(f"  First Seen:      {data.get('first_seen', 'Unknown')}\n")
                f.write(f"  Last Seen:       {data.get('last_seen', 'Unknown')}\n")
                if data.get("current_operator"):
                    f.write(f"  Operator:        {data.get('current_operator')}\n")
                if data.get("vehicle_description"):
                    f.write(f"  Description:     {data.get('vehicle_description')}\n")
                f.write(f"  Sightings:       {data.get('total_sightings', 0)}\n")
                f.write(
                    f"  Location:        "
                    f"({data.get('last_location', {}).get('lat', 'N/A')}, "
                    f"{data.get('last_location', {}).get('lon', 'N/A')})\n"
                )
                f.write(f"  Speed:           {data.get('last_speed', 0)} km/h\n")

                if data.get("last_origin") or data.get("last_destination"):
                    f.write(
                        f"  Route:           "
                        f"{data.get('last_origin', '?')} → {data.get('last_destination', '?')}\n"
                    )

        print(f"✅ Summary saved to {SUMMARY_FILE}")
        print(f"📁 Summary path: {os.path.abspath(SUMMARY_FILE)}")

    except Exception as e:
        print(f"❌ Failed to create summary: {e}")


def update_loco_database():
    print("=" * 60)
    print("🚂 LOCO DATABASE UPDATER")
    print("=" * 60)

    if not os.path.exists(TRAINS_FILE):
        print(f"❌ {TRAINS_FILE} not found")
        return

    try:
        with open(TRAINS_FILE, "r", encoding="utf-8") as f:
            train_data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read {TRAINS_FILE}: {e}")
        return

    trains = train_data.get("trains", [])
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    date = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    print(f"\n📊 Processing {len(trains)} trains...")

    locos = load_json(LOCOS_FILE)
    history = load_json(HISTORY_FILE)
    blocked = load_blocked_locos()
    blocked_descriptions = load_blocked_descriptions()
    print(f"🚫 Blocked locos loaded: {len(blocked)}")
    print(f"🚫 Blocked descriptions loaded: {len(blocked_descriptions)}")

    if not isinstance(locos, dict):
        locos = {}

    if not history or not isinstance(history, dict):
        history = {"locos": {}, "updates": []}

    if "locos" not in history or not isinstance(history["locos"], dict):
        history["locos"] = {}
    if "updates" not in history or not isinstance(history["updates"], list):
        history["updates"] = []

    removed_locos, removed_history = purge_blocked_records(locos, history, blocked, blocked_descriptions)
    if removed_locos or removed_history:
        print(f"🧹 Removed blocked records: {removed_locos} from locos.json, {removed_history} from history")

    new_locos = 0
    updated_locos = 0
    skipped_blocked = 0

    for train in trains:
        raw_loco_id = train.get("train_name") or train.get("train_number") or train.get("id")
        loco_id = normalize_loco(raw_loco_id)
        if not is_real_loco_id(loco_id):
            continue

        previous_data = locos.get(loco_id, {}) if isinstance(locos.get(loco_id), dict) else {}

        vehicle_description = extract_vehicle_description(train, previous_data)
        current_operator = extract_current_operator(train, previous_data)

        if loco_id in blocked or description_is_blocked(vehicle_description, blocked_descriptions):
            skipped_blocked += 1
            continue

        first_seen = previous_data.get("first_seen", timestamp)
        date_time_added = previous_data.get("date_time_added", first_seen)
        total_sightings = int(previous_data.get("total_sightings", 0) or 0) + 1

        loco_data = {
            "date_time_added": date_time_added,
            "first_seen": first_seen,
            "last_seen": timestamp,
            "last_date": date,
            "last_time": time_str,
            "last_location": {
                "lat": train.get("lat"),
                "lon": train.get("lon"),
            },
            "last_speed": train.get("speed", 0),
            "last_origin": clean_text(train.get("origin")),
            "last_destination": clean_text(train.get("destination")),
            "last_description": vehicle_description,
            "vehicle_description": vehicle_description,
            "current_operator": current_operator,
            "last_train_number": clean_text(train.get("train_number")),
            "cId": clean_text(train.get("cId")),
            "servId": clean_text(train.get("servId")),
            "trKey": clean_text(train.get("trKey")),
            "total_sightings": total_sightings,
        }

        if loco_id in locos:
            updated_locos += 1
        else:
            new_locos += 1

        locos[loco_id] = loco_data

        if loco_id not in history["locos"]:
            history["locos"][loco_id] = []

        history["locos"][loco_id].append(
            {
                "timestamp": timestamp,
                "lat": train.get("lat"),
                "lon": train.get("lon"),
                "speed": train.get("speed", 0),
            }
        )

        if len(history["locos"][loco_id]) > 100:
            history["locos"][loco_id] = history["locos"][loco_id][-100:]

    history["updates"].append(
        {
            "timestamp": timestamp,
            "trains_seen": len(trains),
            "locos_seen": len(locos),
            "blocked_skipped": skipped_blocked,
        }
    )

    if len(history["updates"]) > 1000:
        history["updates"] = history["updates"][-1000:]

    save_json(LOCOS_FILE, dict(sorted(locos.items(), key=lambda x: x[0])))
    save_json(HISTORY_FILE, history)

    print(f"\n📊 Statistics:")
    print(f"   New locos: {new_locos}")
    print(f"   Updated locos: {updated_locos}")
    print(f"   Skipped blocked sightings: {skipped_blocked}")
    print(f"   Total visible locos tracked: {len(locos)}")

    print("\n📝 Updating export files...")
    export_to_csv(locos)
    create_summary(locos)

    print("\n✅ Done")
    print("📁 Updated files:")
    print(f"   - {os.path.abspath(LOCOS_FILE)}")
    print(f"   - {os.path.abspath(HISTORY_FILE)}")
    print(f"   - {os.path.abspath(EXPORT_FILE)}")
    print(f"   - {os.path.abspath(SUMMARY_FILE)}")


if __name__ == "__main__":
    update_loco_database()
