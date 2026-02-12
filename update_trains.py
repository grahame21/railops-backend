import os
import json
import datetime
import requests
from urllib.parse import urlparse

OUT_FILE = "trains.json"
TF_URL = "https://trainfinder.otenko.com/Home/GetViewPortData"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"

TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

def write_output(trains, note=""):
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains or []
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"📝 Output: {len(trains or [])} trains, status: {note}")

def extract_list(data):
    if not data: return []
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for k in ["trains", "Trains", "markers", "Markers", "features", "data"]:
            if isinstance(data.get(k), list):
                return data[k]
    return []

def to_float(x):
    try: return float(x) if x is not None else None
    except: return None

def norm_item(item, i):
    if not isinstance(item, dict): return None
    return {
        "id": str(item.get("id") or item.get("ID") or f"train_{i}"),
        "lat": to_float(item.get("lat") or item.get("latitude")),
        "lon": to_float(item.get("lon") or item.get("longitude")),
        "operator": item.get("operator") or "",
        "heading": to_float(item.get("heading") or 0)
    }

def investigate_login():
    """Investigate the login page to find the correct form action"""
    
    print("=" * 60)
    print("🔍 INVESTIGATION MODE - Finding Login Endpoint")
    print("=" * 60)
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    
    # Step 1: Get the login page and analyze it
    print(f"\n1️⃣ Fetching login page: {TF_LOGIN_URL}")
    try:
        response = session.get(TF_LOGIN_URL, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"   Response length: {len(response.text)} characters")
        
        # Look for form tags in the response
        html = response.text.lower()
        
        # Find all form actions
        import re
        form_actions = re.findall(r'<form[^>]*action=[\'"]([^\'"]*)[\'"]', html)
        print(f"\n2️⃣ Found {len(form_actions)} form actions:")
        for i, action in enumerate(form_actions[:5]):  # Show first 5
            # Convert relative URLs to absolute
            if action.startswith('/'):
                action = 'https://trainfinder.otenko.com' + action
            print(f"   Form {i+1}: {action}")
        
        # Find input field names
        input_names = re.findall(r'<input[^>]*name=[\'"]([^\'"]*)[\'"]', html)
        print(f"\n3️⃣ Found {len(input_names)} input field names:")
        unique_names = set(input_names)
        for name in unique_names:
            print(f"   - {name}")
        
        # Look for password fields specifically
        password_fields = re.findall(r'<input[^>]*type=[\'"]password[\'"][^>]*name=[\'"]([^\'"]*)[\'"]', html)
        print(f"\n4️⃣ Password field names: {set(password_fields) if password_fields else 'None found'}")
        
        # Look for the actual login form
        if 'login' in html or 'signin' in html:
            print("\n5️⃣ Page contains 'login' or 'signin' keywords")
        
        # Try to find the most likely login endpoint
        if form_actions:
            # Try the first form action
            test_action = form_actions[0]
            if test_action.startswith('/'):
                test_action = 'https://trainfinder.otenko.com' + test_action
            
            print(f"\n6️⃣ Testing form action: {test_action}")
            
            # Try different credential combinations
            test_data = {}
            if 'username' in unique_names or 'user' in unique_names:
                test_data['username'] = TF_USERNAME
                test_data['password'] = TF_PASSWORD
            elif 'email' in unique_names:
                test_data['email'] = TF_USERNAME
                test_data['password'] = TF_PASSWORD
            elif 'UserName' in unique_names:
                test_data['UserName'] = TF_USERNAME
                test_data['Password'] = TF_PASSWORD
            
            if test_data:
                print(f"   Testing with fields: {list(test_data.keys())}")
                try:
                    login_resp = session.post(test_action, data=test_data, timeout=30, allow_redirects=False)
                    print(f"   Response status: {login_resp.status_code}")
                    if login_resp.status_code in (302, 303, 307):
                        location = login_resp.headers.get('Location', '')
                        print(f"   Redirect to: {location}")
                        
                        # Follow the redirect and try to get train data
                        if 'login' not in location.lower() and 'signin' not in location.lower():
                            print("   ✅ Possible successful login!")
                            
                            # Try to get train data
                            train_resp = session.get(TF_URL, timeout=30, allow_redirects=False)
                            print(f"   Train data response: {train_resp.status_code}")
                            
                            if train_resp.status_code == 200:
                                try:
                                    data = train_resp.json()
                                    raw_list = extract_list(data)
                                    trains = []
                                    for i, item in enumerate(raw_list):
                                        train = norm_item(item, i)
                                        if train and train.get("lat") and train.get("lon"):
                                            trains.append(train)
                                    return trains, "ok"
                                except:
                                    pass
                except Exception as e:
                    print(f"   Error: {type(e).__name__}")
        
    except Exception as e:
        print(f"❌ Investigation error: {type(e).__name__}: {str(e)}")
    
    return [], "Login endpoint not found"

def main():
    print("=" * 60)
    print(f"🚂 TRAINFINDER LOGIN INVESTIGATION")
    print(f"📅 {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = investigate_login()
    write_output(trains, note)
    
    print("\n" + "=" * 60)
    print(f"🏁 Complete: {len(trains)} trains")
    print(f"📝 Status: {note}")
    print("=" * 60)

if __name__ == "__main__":
    main()
