import os
import json
import datetime
import csv

LOCOS_FILE = "locos.json"
EXPORT_FILE = "loco_export.csv"
SUMMARY_FILE = "loco_summary.txt"

def load_locos():
    if not os.path.exists(LOCOS_FILE):
        print(f"❌ {LOCOS_FILE} not found")
        return None
    try:
        with open(LOCOS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Failed to load locos.json: {e}")
        return None

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
        return True
    except Exception as e:
        print(f"❌ Failed to export: {e}")
        return False

def create_summary(locos):
    try:
        with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"LOCO DATABASE SUMMARY - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Total Locomotives Tracked: {len(locos)}\n\n")
            sorted_locos = sorted(locos.items(), key=lambda x: x[1].get('last_seen', ''), reverse=True)
            for loco_id, data in sorted_locos[:50]:
                f.write(f"\n{'=' * 40}\n")
                f.write(f"LOCO: {loco_id}\n")
                f.write(f"{'=' * 40}\n")
                f.write(f"  First Seen:    {data.get('first_seen', 'Unknown')}\n")
                f.write(f"  Last Seen:     {data.get('last_seen', 'Unknown')}\n")
                f.write(f"  Sightings:     {data.get('total_sightings', 0)}\n")
                f.write(f"  Location:      ({data.get('last_location', {}).get('lat', 'N/A')}, {data.get('last_location', {}).get('lon', 'N/A')})\n")
                f.write(f"  Speed:         {data.get('last_speed', 0)} km/h\n")
                if data.get('last_origin') or data.get('last_destination'):
                    f.write(f"  Route:         {data.get('last_origin', '?')} → {data.get('last_destination', '?')}\n")
        print(f"✅ Summary saved to {SUMMARY_FILE}")
    except Exception as e:
        print(f"❌ Failed to create summary: {e}")

def main():
    print("=" * 60)
    print("📊 LOCO EXPORTER")
    print("=" * 60)
    locos = load_locos()
    if not locos:
        return
    print(f"\n📊 Loaded {len(locos)} locos")
    export_to_csv(locos)
    create_summary(locos)
    print(f"\n📁 Files updated:")
    print(f"   - {EXPORT_FILE}")
    print(f"   - {SUMMARY_FILE}")
    print(f"   - {LOCOS_FILE} (database)")

if __name__ == "__main__":
    main()
