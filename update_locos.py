import os
import json
import datetime

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
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

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
    time_str = now.strftime('%H:%M:%S')
    
    print(f"\n📊 Processing {len(trains)} trains...")
    
    locos = load_json(LOCOS_FILE)
    history = load_json(HISTORY_FILE)
    if not history:
        history = {'locos': {}, 'updates': []}
    
    new_locos = 0
    updated_locos = 0
    
    for train in trains:
        loco_id = train.get('train_name') or train.get('train_number') or train.get('id')
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

if __name__ == "__main__":
    update_loco_database()
