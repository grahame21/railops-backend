import os
import json
import datetime
import requests

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

def login_direct():
    """Try direct form POST to login endpoint"""
    
    print("🔄 Attempting direct login POST...")
    
    # First, get the login page to extract any CSRF tokens
    session = requests.Session()
    
    # Set realistic headers
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    })
    
    try:
        # Get the login page first to get any cookies
        print("🔄 Getting login page...")
        response = session.get(TF_LOGIN_URL, timeout=30)
        print(f"✅ Login page loaded: {response.status_code}")
        
        # Try different possible login endpoints
        login_endpoints = [
            "https://trainfinder.otenko.com/Account/Login",
            "https://trainfinder.otenko.com/Home/Login",
            "https://trainfinder.otenko.com/Account/SignIn",
            "https://trainfinder.otenko.com/Home/SignIn",
            "https://trainfinder.otenko.com/login",
            "https://trainfinder.otenko.com/Account/LogOn",
            "https://trainfinder.otenko.com/Home/LogOn"
        ]
        
        # Try different form data formats
        form_data_variations = [
            {"username": TF_USERNAME, "password": TF_PASSWORD},
            {"Username": TF_USERNAME, "Password": TF_PASSWORD},
            {"user": TF_USERNAME, "pass": TF_PASSWORD},
            {"email": TF_USERNAME, "password": TF_PASSWORD},
            {"UserName": TF_USERNAME, "Password": TF_PASSWORD},
            {"login": TF_USERNAME, "password": TF_PASSWORD},
            {"name": TF_USERNAME, "pwd": TF_PASSWORD}
        ]
        
        for endpoint in login_endpoints:
            for form_data in form_data_variations:
                try:
                    print(f"🔄 Trying POST to {endpoint}")
                    print(f"   Form data keys: {list(form_data.keys())}")
                    
                    login_response = session.post(
                        endpoint, 
                        data=form_data,
                        timeout=30,
                        allow_redirects=False
                    )
                    
                    print(f"   Response: {login_response.status_code}")
                    
                    if login_response.status_code in [302, 303, 307]:
                        location = login_response.headers.get("Location", "")
                        print(f"   Redirect to: {location}")
                        
                        # If redirected away from login page, we might be successful
                        if "login" not in location.lower() and "signin" not in location.lower():
                            print("✅ Possible successful login!")
                            
                            # Now try to get train data
                            train_response = session.get(
                                TF_URL, 
                                timeout=30, 
                                allow_redirects=False
                            )
                            
                            print(f"   Train data response: {train_response.status_code}")
                            
                            if train_response.status_code == 200:
                                try:
                                    data = train_response.json()
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
                    continue
        
        return [], "Login failed - no working endpoint found"
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        return [], f"Error: {type(e).__name__}"

def main():
    print("=" * 60)
    print(f"🚂 DIRECT POST ATTEMPT - {datetime.datetime.utcnow().isoformat()}")
    print("=" * 60)
    
    if not TF_USERNAME or not TF_PASSWORD:
        print("❌ Missing credentials")
        write_output([], "Missing credentials")
        return
    
    trains, note = login_direct()
    write_output(trains, note)
    
    print(f"🏁 Complete: {len(trains)} trains")
    print("=" * 60)

if __name__ == "__main__":
    main()
