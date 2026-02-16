import os
import json
import datetime
from collections import defaultdict

# Files
TRAINS_FILE = "trains.json"
LOCOS_FILE = "locos.json"
HISTORY_FILE = "loco_history.json"  # For full historical tracking

def load_json_file(filename):
    """Load JSON file if it exists"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json_file(filename, data):
    """Save data to JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_loco_database():
    """Update loco database with latest train positions"""
    
    print("=" * 60)
    print("🚂 LOCO DATABASE UPDATER")
    print("=" * 60)
    
    # Load current trains
    if not os.path.exists(TRAINS_FILE):
        print(f"❌ {TRAINS_FILE} not found")
        return
    
    with open(TRAINS_FILE, 'r') as f:
        train_data = json.load(f)
    
    trains = train_data.get('trains', [])
    current_time = datetime.datetime.now()
    timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')
    date = current_time.strftime('%Y-%m-%d')
    
    print(f"\n📊 Processing {len(trains)} trains...")
    
    # Load existing loco database
    locos = load_json_file(LOCOS_FILE)
    
    # Load history
    history = load_json_file(HISTORY_FILE)
    if not history:
        history = {'locos': {}, 'updates': []}
    
    # Track new sightings
    new_sightings = 0
    updated_locos = 0
    
    for train in trains:
        # Get loco identifier (prioritize train_name, then train_number, then id)
        loco_id = train.get('train_name') or train.get('train_number') or train.get('id')
        
        if not loco_id:
            continue
            
        # Skip obvious non-loco entries
        if 'marker' in loco_id.lower() or 'arrow' in loco_id.lower():
            continue
        
        # Prepare loco data
        loco_data = {
            'last_seen': timestamp,
            'last_date': date,
            'last_time': current_time.strftime('%H:%M:%S'),
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
        
        # If we've seen this loco before, update it
        if loco_id in locos:
            # Count this as another sighting
            locos[loco_id]['total_sightings'] = locos[loco_id].get('total_sightings', 1) + 1
            locos[loco_id]['last_seen'] = timestamp
            locos[loco_id]['last_location'] = loco_data['last_location']
            locos[loco_id]['last_speed'] = loco_data['last_speed']
            locos[loco_id]['last_origin'] = loco_data['last_origin']
            locos[loco_id]['last_destination'] = loco_data['last_destination']
            updated_locos += 1
        else:
            # New loco!
            locos[loco_id] = loco_data
            new_sightings += 1
        
        # Add to history (keep last 30 days of positions)
        if loco_id not in history['locos']:
            history['locos'][loco_id] = []
        
        # Add current position to history (limit to last 100 positions per loco)
        history['locos'][loco_id].append({
            'timestamp': timestamp,
            'lat': train.get('lat'),
            'lon': train.get('lon'),
            'speed': train.get('speed', 0),
            'origin': train.get('origin', ''),
            'destination': train.get('destination', '')
        })
        
        # Keep only last 100 positions
        if len(history['locos'][loco_id]) > 100:
            history['locos'][loco_id] = history['locos'][loco_id][-100:]
    
    # Record this update
    history['updates'].append({
        'timestamp': timestamp,
        'trains_seen': len(trains),
        'locos_seen': len(locos)
    })
    
    # Keep only last 1000 updates
    if len(history['updates']) > 1000:
        history['updates'] = history['updates'][-1000:]
    
    # Save files
    save_json_file(LOCOS_FILE, locos)
    save_json_file(HISTORY_FILE, history)
    
    print(f"\n📊 Statistics:")
    print(f"   New locos found: {new_sightings}")
    print(f"   Existing locos updated: {updated_locos}")
    print(f"   Total locos in database: {len(locos)}")
    print(f"   History entries: {sum(len(h) for h in history['locos'].values())}")
    
    # Save a human-readable summary
    summary_file = "loco_summary.txt"
    with open(summary_file, 'w') as f:
        f.write(f"LOCO DATABASE SUMMARY - {timestamp}\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Total Locomotives Tracked: {len(locos)}\n\n")
        
        # Sort by last seen (most recent first)
        sorted_locos = sorted(locos.items(), key=lambda x: x[1]['last_seen'], reverse=True)
        
        for loco_id, data in sorted_locos[:50]:  # Show top 50 most recent
            f.write(f"{loco_id}:\n")
            f.write(f"  Last Seen: {data['last_seen']}\n")
            f.write(f"  Location: ({data['last_location']['lat']:.4f}, {data['last_location']['lon']:.4f})\n")
            f.write(f"  Speed: {data['last_speed']} km/h\n")
            if data['last_origin'] or data['last_destination']:
                f.write(f"  Route: {data['last_origin']} → {data['last_destination']}\n")
            f.write(f"  Sightings: {data['total_sightings']}\n")
            f.write("-" * 40 + "\n")
    
    print(f"\n✅ Summary saved to {summary_file}")
    print(f"✅ Loco database saved to {LOCOS_FILE}")
    print(f"✅ History saved to {HISTORY_FILE}")

if __name__ == "__main__":
    update_loco_database()
