import os
import json
import datetime
from collections import defaultdict

TRAINS_FILE = "trains.json"
LOCOS_FILE = "locos.json"
HISTORY_FILE = "loco_history.json"

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_loco_database():
    print("=" * 60)
    print("🚂 LOCO DATABASE UPDATER")
    print("=" * 60)
    
    if not os.path.exists(TRAINS_FILE):
        print(f"❌ {TRAINS_FILE} not found")
        return
    
    with open(TRAINS_FILE, 'r') as f:
        train_data = json.load(f)
    
    trains = train_data.get('trains', [])
    now = datetime.datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    date = now.strftime('%Y-%m-%d')
    
    print(f"\n📊 Processing {len(trains)} trains...")
    
    locos = load_json(LOCOS_FILE)
    history = load_json(HISTORY_FILE)
    if not history:
        history = {'locos': {}, 'updates': []}
    
    new = updated = 0
    
    for train in trains:
        loco_id = train.get('train_name') or train.get('train_number') or train.get('id')
        if not loco_id or any(x in loco_id.lower() for x in ['marker', 'arrow']):
            continue
        
        data = {
            'last_seen': timestamp,
            'last_date': date,
            'last_time': now.strftime('%H:%M:%S'),
            'last_location': {'lat': train.get('lat'), 'lon': train.get('lon')},
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
            data['total_sightings'] = locos[loco_id].get('total_sightings', 1) + 1
            updated += 1
        else:
            new += 1
        
        locos[loco_id] = data
        
        if loco_id not in history['locos']:
            history['locos'][loco_id] = []
        history['locos'][loco_id].append({
            'timestamp': timestamp,
            'lat': train.get('lat'),
            'lon': train.get('lon'),
            'speed': train.get('speed', 0),
            'origin': train.get('origin', ''),
            'destination': train.get('destination', '')
        })
        if len(history['locos'][loco_id]) > 100:
            history['locos'][loco_id] = history['locos'][loco_id][-100:]
    
    history['updates'].append({'timestamp': timestamp, 'trains_seen': len(trains), 'locos_seen': len(locos)})
    if len(history['updates']) > 1000:
        history['updates'] = history['updates'][-1000:]
    
    save_json(LOCOS_FILE, locos)
    save_json(HISTORY_FILE, history)
    
    print(f"\n📊 Statistics:")
    print(f"   New locos: {new}")
    print(f"   Updated locos: {updated}")
    print(f"   Total locos: {len(locos)}")
    
    with open("loco_summary.txt", 'w') as f:
        f.write(f"LOCO DATABASE SUMMARY - {timestamp}\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Total Locomotives Tracked: {len(locos)}\n\n")
        for loco_id, data in sorted(locos.items(), key=lambda x: x[1]['last_seen'], reverse=True)[:50]:
            f.write(f"{loco_id}:\n")
            f.write(f"  Last Seen: {data['last_seen']}\n")
            f.write(f"  Location: ({data['last_location']['lat']:.4f}, {data['last_location']['lon']:.4f})\n")
            f.write(f"  Speed: {data['last_speed']} km/h\n")
            if data['last_origin'] or data['last_destination']:
                f.write(f"  Route: {data['last_origin']} → {data['last_destination']}\n")
            f.write(f"  Sightings: {data['total_sightings']}\n")
            f.write("-" * 40 + "\n")
    
    print(f"\n✅ Summary saved")
    print(f"✅ Loco database: {LOCOS_FILE}")
    print(f"✅ History: {HISTORY_FILE}")

if __name__ == "__main__":
    update_loco_database()
