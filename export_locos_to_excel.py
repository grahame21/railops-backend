import os
import json
import datetime
import csv

def export_locos_to_excel():
    """Export loco database to Excel-compatible CSV"""
    
    print("=" * 60)
    print("📊 EXPORTING LOCO DATABASE TO EXCEL")
    print("=" * 60)
    
    # Load loco database
    if not os.path.exists('locos.json'):
        print("❌ locos.json not found")
        return
    
    try:
        with open('locos.json', 'r') as f:
            locos = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load locos.json: {e}")
        return
    
    # Create timestamped filename
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'loco_export_{timestamp}.csv'
    
    # Define CSV columns
    fieldnames = [
        'Loco ID', 'Train Number', 'Last Seen', 'Last Date', 'Last Time',
        'Latitude', 'Longitude', 'Speed', 'Origin', 'Destination',
        'Description', 'Total Sightings', 'cId', 'servId', 'trKey'
    ]
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for loco_id, data in locos.items():
                # Skip if not a dict (shouldn't happen, but just in case)
                if not isinstance(data, dict):
                    continue
                    
                writer.writerow({
                    'Loco ID': loco_id,
                    'Train Number': data.get('last_train_number', ''),
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
        
        print(f"✅ Exported {len(locos)} locos to {filename}")
        
        # Also create a master file that gets overwritten
        master_file = 'loco_export_latest.csv'
        with open(master_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for loco_id, data in locos.items():
                if not isinstance(data, dict):
                    continue
                    
                writer.writerow({
                    'Loco ID': loco_id,
                    'Train Number': data.get('last_train_number', ''),
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
        
        print(f"✅ Also saved to {master_file} (always latest)")
        
    except Exception as e:
        print(f"❌ Failed to export: {e}")

if __name__ == "__main__":
    export_locos_to_excel()
