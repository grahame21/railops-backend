import os
import json
import datetime
import csv

TRAINS_FILE = "trains.json"
LOCOS_FILE = "locos.json"
HISTORY_FILE = "loco_history.json"
EXPORT_FILE = "loco_export.csv"
SUMMARY_FILE = "loco_summary.txt"

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Failed to load {filename}: {e}")
            return {}
    return {}

def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to save {filename}: {e}")

def export_to_csv(locos):
    fieldnames = [
        'Loco ID', 'First Seen', 'Last Seen', 'Last Date', 'Last Time',
        'Latitude', 'Longitude', 'Speed', 'Origin', 'Destination',
        'Description', 'Total Sightings', 'cId', 'servId', 'trKey'
    ]

    try:
        with open(EXPORT_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for loco_id in sorted(locos.keys()):
                data = locos[loco_id]
                if not isinstance(data, dict):
                    continue

                writer.writerow({
                    'Loco ID': loco_id,
                    'First Seen': data.get('first_seen', 'Unknown'),
                    'Last Seen': data.get('last_seen', ''),
                    'Last Date': data.get('last_date', ''),
                    'Last Time': data.get('last_time', ''),
                    'Latitude': data.get('last_location', {}).get('lat', ''),
                    'Longitude': data.get('last_location', {}).get('lon', ''),
                    'Speed': data.get('last_speed', 0),
                    'Origin': data.get('last_origin', ''),
                    'Destination': data.get('last_destination', ''),
                    'Description': data.get('last_description', ''),
                    'Total Sightings': data.get('total_sightings', 0),
                    'cId': data.get('cId', ''),
                    'servId': data.get('servId', ''),
                    'trKey': data.get('trKey', '')
                })

        print(f"✅ Exported {len(locos)} locos to {EXPORT_FILE}")
        print(f"📁 CSV path: {os.path.abspath(EXPORT_FILE)}")
        return True

    except Exception as e:
        print(f"❌ Failed to export CSV: {e}")
        return False

def create_summary(locos):
    try:
        with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"LOCO DATABASE SUMMARY - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Total Locomotives Tracked: {len(locos)}\n\n")

            sorted_locos = sorted(
                locos.items(),
                key=lambda x: x[1].get('last_seen', ''),
                reverse=True
            )

            for loco_id, data in sorted_locos[:50]:
                f.write(f"\n{'=' * 40}\n")
                f.write(f"LOCO: {loco_id}\n")
                f.write(f"{'=' * 40}\n")
                f.write(f"  First Seen:    {data.get('first_seen', 'Unknown')}\n")
                f.write(f"  Last Seen:     {data.get('last_seen', 'Unknown')}\n")
                f.write(f"  Sightings:     {data.get('total_sightings', 0)}\n")
                f.write(
                    f"  Location:      "
                    f"({data.get('last_location', {}).get('lat', 'N/A')}, "
                    f"{data.get('last_location', {}).get('lon', 'N/A')})\n"
                )
                f.write(f"  Speed:         {data.get('last_speed', 0)} km/h\n")

                if data.get('last_origin') or data.get('last_destination'):
                    f.write(
                        f"  Route:         "
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
        with open(TRAINS_FILE, 'r', encoding='utf-8') as f:
            train_data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read {TRAINS_FILE}: {e}")
        return

    trains = train_data.get('trains', [])
    now = datetime.datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    date = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')

    print(f"\n📊 Processing {len(trains)} trains...")

    locos = load_json(LOCOS_FILE)
    history = load_json(HISTORY_FILE)

    if not isinstance(locos, dict):
        locos = {}

    if not history or not isinstance(history, dict):
        history = {'locos': {}, 'updates': []}

    if 'locos' not in history:
        history['locos'] = {}
    if 'updates' not in history:
        history['updates'] = []

    new_locos = 0
    updated_locos = 0

    for train in trains:
        loco_id = train.get('train_name') or train.get('train_number') or train.get('id')
        if not loco_id:
            continue

        loco_id = str(loco_id).strip()
        if not loco_id:
            continue

        loco_data = {
            'last_seen': timestamp,
            'last_date': date,
            'last_time': time_str,
            'last_location': {
                'lat': train.get('lat'),
                'lon': train.get('lon')
            },
            'last_speed': train.get('speed', 0),
            'last_origin': train.get('origin', ''),
            'last_destination': train.get('destination', ''),
            'last_description': train.get('description', ''),
            'last_train_number': train.get('train_number', ''),
            'cId': train.get('cId', ''),
            'servId': train.get('servId', ''),
            'trKey': train.get('trKey', ''),
            'total_sightings': 1
        }

        if loco_id in locos:
            loco_data['total_sightings'] = locos[loco_id].get('total_sightings', 1) + 1
            loco_data['first_seen'] = locos[loco_id].get('first_seen', timestamp)
            updated_locos += 1
        else:
            loco_data['first_seen'] = timestamp
            new_locos += 1

        locos[loco_id] = loco_data

        if loco_id not in history['locos']:
            history['locos'][loco_id] = []

        history['locos'][loco_id].append({
            'timestamp': timestamp,
            'lat': train.get('lat'),
            'lon': train.get('lon'),
            'speed': train.get('speed', 0)
        })

        if len(history['locos'][loco_id]) > 100:
            history['locos'][loco_id] = history['locos'][loco_id][-100:]

    history['updates'].append({
        'timestamp': timestamp,
        'trains_seen': len(trains),
        'locos_seen': len(locos)
    })

    if len(history['updates']) > 1000:
        history['updates'] = history['updates'][-1000:]

    save_json(LOCOS_FILE, locos)
    save_json(HISTORY_FILE, history)

    print(f"\n📊 Statistics:")
    print(f"   New locos: {new_locos}")
    print(f"   Updated locos: {updated_locos}")
    print(f"   Total locos tracked: {len(locos)}")

    print("\n📝 Updating export files...")
    export_to_csv(locos)
    create_summary(locos)

    print("\n✅ Done")
    print(f"📁 Updated files:")
    print(f"   - {os.path.abspath(LOCOS_FILE)}")
    print(f"   - {os.path.abspath(HISTORY_FILE)}")
    print(f"   - {os.path.abspath(EXPORT_FILE)}")
    print(f"   - {os.path.abspath(SUMMARY_FILE)}")

if __name__ == "__main__":
    update_loco_database()