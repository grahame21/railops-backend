import os
import json
import datetime
import time
import math
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

OUT_FILE = "trains.json"
COOKIE_FILE = "trainfinder_cookies.pkl"
TF_LOGIN_URL = "https://trainfinder.otenko.com/home/nextlevel"
TF_USERNAME = os.environ.get("TF_USERNAME", "").strip()
TF_PASSWORD = os.environ.get("TF_PASSWORD", "").strip()

class TrainScraper:
    def __init__(self):
        self.driver = None
        self.trains = []
        
    def setup_driver(self):
        """Configure Chrome driver for optimal performance"""
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Add these for faster loading
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--disable-extensions')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Hide webdriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
    def save_cookies(self):
        """Save cookies for future sessions"""
        if self.driver:
            with open(COOKIE_FILE, "wb") as f:
                pickle.dump(self.driver.get_cookies(), f)
            print("✅ Cookies saved")
    
    def load_cookies(self):
        """Load saved cookies to skip login"""
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "rb") as f:
                    cookies = pickle.load(f)
                
                # First navigate to domain
                self.driver.get("https://trainfinder.otenko.com")
                time.sleep(2)
                
                # Add cookies
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except:
                        pass
                
                print("✅ Cookies loaded")
                return True
            except Exception as e:
                print(f"⚠️ Couldn't load cookies: {e}")
        return False
    
    def login(self):
        """Handle login with retry logic"""
        print("\n📌 Attempting login...")
        
        try:
            self.driver.get(TF_LOGIN_URL)
            time.sleep(3)
            
            # Check if already logged in
            if "home/nextlevel" in self.driver.current_url and "login" not in self.driver.current_url.lower():
                print("✅ Already logged in")
                return True
            
            # Find and fill login form
            username = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "useR_name"))
            )
            username.clear()
            username.send_keys(TF_USERNAME)
            
            password = self.driver.find_element(By.ID, "pasS_word")
            password.clear()
            password.send_keys(TF_PASSWORD)
            
            # Click login button via JavaScript (more reliable)
            self.driver.execute_script("""
                var buttons = document.querySelectorAll('input[type="button"], button');
                for(var i = 0; i < buttons.length; i++) {
                    if(buttons[i].value === 'Log In' || buttons[i].textContent.includes('Log In')) {
                        buttons[i].click();
                        return true;
                    }
                }
                return false;
            """)
            
            time.sleep(5)
            
            # Check login success
            if "home/nextlevel" in self.driver.current_url:
                print("✅ Login successful")
                self.save_cookies()
                return True
            else:
                print("❌ Login failed")
                return False
                
        except TimeoutException:
            print("❌ Login timeout")
            return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def close_warning(self):
        """Close any warning popups"""
        try:
            self.driver.execute_script("""
                // Try multiple methods to close warning
                var closeButtons = document.querySelectorAll('button[aria-label="Close"], .close-button, .modal-close, .popup-close');
                for(var i = 0; i < closeButtons.length; i++) {
                    closeButtons[i].click();
                }
                
                // Try the path method from your original code
                var paths = document.getElementsByTagName('path');
                for(var i = 0; i < paths.length; i++) {
                    var d = paths[i].getAttribute('d') || '';
                    if(d.includes('M13.7,11l6.1-6.1')) {
                        var parent = paths[i].parentElement;
                        while(parent && parent.tagName !== 'BUTTON' && parent.tagName !== 'DIV' && parent.tagName !== 'A') {
                            parent = parent.parentElement;
                        }
                        if(parent) parent.click();
                    }
                }
            """)
            print("✅ Warning popups closed")
            time.sleep(2)
        except:
            pass  # No warning to close
    
    def zoom_to_australia(self):
        """Zoom map to show all Australian trains"""
        try:
            self.driver.execute_script("""
                if (window.map) {
                    var australia = [112, -44, 154, -10];
                    try {
                        var proj = window.map.getView().getProjection();
                        var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
                        window.map.getView().fit(extent, { duration: 1000, maxZoom: 8 });
                        return true;
                    } catch(e) {
                        console.log('Map zoom error:', e);
                        return false;
                    }
                }
                return false;
            """)
            print("🌏 Zoomed to Australia")
            time.sleep(5)  # Increased wait time
        except:
            print("⚠️ Couldn't zoom map")
    
    def diagnose_page_state(self):
        """Run diagnostics to understand what's on the page"""
        print("\n🔍 Running page diagnostics...")
        
        script = """
        var diagnostics = {
            'sources_found': [],
            'feature_counts': {},
            'map_exists': false,
            'view_exists': false,
            'projection': null,
            'current_zoom': null,
            'current_center': null,
            'page_url': window.location.href,
            'page_title': document.title,
            'has_train_elements': false,
            'train_element_count': 0,
            'ol_loaded': false,
            'all_global_vars': [],
            'script_tags_with_json': 0
        };
        
        // Check if OpenLayers is loaded
        diagnostics.ol_loaded = typeof ol !== 'undefined';
        
        // Check if map exists
        if (window.map) {
            diagnostics.map_exists = true;
            diagnostics.view_exists = !!window.map.getView();
            if (diagnostics.view_exists) {
                var view = window.map.getView();
                diagnostics.projection = view.getProjection().getCode();
                diagnostics.current_zoom = view.getZoom();
                diagnostics.current_center = view.getCenter();
            }
        }
        
        // List all global variables that might contain train data
        for (var key in window) {
            if (key.includes('train') || key.includes('Train') || key.includes('marker') || 
                key.includes('Marker') || key.includes('source') || key.includes('Source')) {
                diagnostics.all_global_vars.push(key);
            }
        }
        
        // Look for known source names
        var sourceNames = [
            'regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource',
            'trainSource', 'markers', 'trainMarkers', 'trainLayerSource', 'vectorSource',
            'trainVectorSource', 'liveTrainsSource', 'trainsSource', 'locomotiveSource',
            'trainPositions', 'trainFeatures', 'pointSource'
        ];
        
        sourceNames.forEach(function(name) {
            if (window[name]) {
                diagnostics.sources_found.push(name);
                try {
                    if (window[name].getFeatures) {
                        var count = window[name].getFeatures().length;
                        diagnostics.feature_counts[name] = count;
                    } else if (window[name].getSource && window[name].getSource().getFeatures) {
                        var count = window[name].getSource().getFeatures().length;
                        diagnostics.feature_counts[name + '_source'] = count;
                    } else {
                        diagnostics.feature_counts[name] = 'exists but not a feature source';
                    }
                } catch(e) {
                    diagnostics.feature_counts[name] = 'error: ' + e.toString();
                }
            }
        });
        
        // Look for any elements that might be train markers
        var trainElements = document.querySelectorAll('[class*="train"], [class*="marker"], [class*="locomotive"], [class*="pin"], [class*="point"]');
        diagnostics.has_train_elements = trainElements.length > 0;
        diagnostics.train_element_count = trainElements.length;
        
        // Count script tags that might contain JSON data
        var scripts = document.querySelectorAll('script[type="application/json"], script[data-train-data]');
        diagnostics.script_tags_with_json = scripts.length;
        
        return diagnostics;
        """
        
        try:
            diagnostics = self.driver.execute_script(script)
            print("\n📊 Page Diagnostics:")
            print(f"   URL: {diagnostics.get('page_url', 'unknown')}")
            print(f"   Title: {diagnostics.get('page_title', 'unknown')}")
            print(f"   OpenLayers loaded: {diagnostics.get('ol_loaded', False)}")
            print(f"   Map object exists: {diagnostics.get('map_exists', False)}")
            if diagnostics.get('current_zoom'):
                print(f"   Current zoom: {diagnostics['current_zoom']}")
            if diagnostics.get('current_center'):
                print(f"   Current center: {diagnostics['current_center']}")
            print(f"   Train-related DOM elements: {diagnostics.get('train_element_count', 0)}")
            print(f"   JSON script tags: {diagnostics.get('script_tags_with_json', 0)}")
            
            if diagnostics.get('all_global_vars'):
                print(f"\n   🔍 Train-related global variables found:")
                for var in diagnostics['all_global_vars'][:10]:  # Show first 10
                    print(f"      - {var}")
            
            if diagnostics['sources_found']:
                print(f"\n   ✅ Found OpenLayers sources: {', '.join(diagnostics['sources_found'])}")
                for source, count in diagnostics['feature_counts'].items():
                    print(f"      - {source}: {count} features")
            else:
                print("\n   ❌ No OpenLayers sources found")
            
            return diagnostics
        except Exception as e:
            print(f"❌ Error during diagnostics: {e}")
            return None

    def extract_from_dom(self):
        """Fallback: extract train data directly from DOM elements"""
        print("\n🔍 Attempting DOM-based extraction...")
        
        script = """
        var trains = [];
        var seenIds = new Set();
        
        // Look for any elements that might be train markers
        var markerElements = document.querySelectorAll('[class*="marker"], [class*="train"], [class*="pin"], [class*="point"], [class*="icon"]');
        
        markerElements.forEach(function(el, index) {
            // Check for data attributes
            var lat = el.getAttribute('data-lat') || el.getAttribute('data-latitude') || 
                     el.getAttribute('lat') || el.getAttribute('latitude');
            var lon = el.getAttribute('data-lng') || el.getAttribute('data-longitude') || 
                     el.getAttribute('data-lon') || el.getAttribute('lng') || el.getAttribute('longitude');
            var id = el.getAttribute('data-id') || el.getAttribute('data-train-id') || 
                    el.getAttribute('id') || 'dom_' + index;
            var title = el.getAttribute('title') || el.getAttribute('alt') || 
                       el.textContent.trim();
            
            // Check for inline style positioning (sometimes used for markers)
            if (!lat && !lon) {
                var style = window.getComputedStyle(el);
                var left = style.left;
                var top = style.top;
                // This would need conversion - complex, so skipping for now
            }
            
            if (lat && lon && !seenIds.has(id)) {
                seenIds.add(id);
                trains.push({
                    'id': id,
                    'train_number': title || id,
                    'x': parseFloat(lon),
                    'y': parseFloat(lat),
                    'heading': 0,
                    'speed': 0
                });
            }
        });
        
        // Also check for any script tags with JSON data
        var scripts = document.querySelectorAll('script[type="application/json"], script[data-train-data], script:not([src])');
        scripts.forEach(function(script) {
            try {
                var content = script.textContent.trim();
                if (content && (content.includes('lat') || content.includes('lon') || 
                    content.includes('train') || content.includes('locomotive'))) {
                    var data = JSON.parse(content);
                    
                    // Handle different possible structures
                    if (Array.isArray(data)) {
                        data.forEach(function(item) {
                            if ((item.lat || item.latitude) && (item.lon || item.longitude)) {
                                var id = item.id || item.train_id || item.loco || 'json_' + trains.length;
                                if (!seenIds.has(id)) {
                                    seenIds.add(id);
                                    trains.push({
                                        'id': id,
                                        'train_number': item.train_number || item.name || item.service || id,
                                        'x': parseFloat(item.lon || item.longitude),
                                        'y': parseFloat(item.lat || item.latitude),
                                        'heading': parseFloat(item.heading || item.bearing || 0),
                                        'speed': parseFloat(item.speed || 0)
                                    });
                                }
                            }
                        });
                    } else if (data && (data.lat || data.latitude) && (data.lon || data.longitude)) {
                        var id = data.id || data.train_id || 'json_single';
                        if (!seenIds.has(id)) {
                            seenIds.add(id);
                            trains.push({
                                'id': id,
                                'train_number': data.train_number || data.name || id,
                                'x': parseFloat(data.lon || data.longitude),
                                'y': parseFloat(data.lat || data.latitude),
                                'heading': parseFloat(data.heading || data.bearing || 0),
                                'speed': parseFloat(data.speed || 0)
                            });
                        }
                    }
                }
            } catch(e) {
                // Not JSON or invalid JSON - ignore
            }
        });
        
        return trains;
        """
        
        try:
            dom_trains = self.driver.execute_script(script)
            print(f"✅ Found {len(dom_trains)} trains via DOM extraction")
            return dom_trains
        except Exception as e:
            print(f"❌ DOM extraction failed: {e}")
            return []

    def extract_trains(self):
        """Extract all train data from map sources with enhanced detection"""
        script = """
        function extractFromSource(source, sourceName) {
            var trains = [];
            if (!source) return trains;
            
            try {
                // Handle different source types
                var features = [];
                if (typeof source.getFeatures === 'function') {
                    features = source.getFeatures();
                } else if (source.getSource && typeof source.getSource().getFeatures === 'function') {
                    features = source.getSource().getFeatures();
                } else if (source.getLayers) {
                    // It might be a layer group
                    var layers = source.getLayers();
                    layers.forEach(function(layer) {
                        if (layer.getSource && typeof layer.getSource().getFeatures === 'function') {
                            features = features.concat(layer.getSource().getFeatures());
                        }
                    });
                }
                
                console.log('Found ' + features.length + ' features in ' + sourceName);
                
                features.forEach(function(feature, index) {
                    try {
                        var props = feature.getProperties();
                        var geom = feature.getGeometry();
                        
                        if (geom && geom.getType() === 'Point') {
                            var coords = geom.getCoordinates();
                            
                            // Extract ID from various possible property names
                            var id = props.id || props.ID || props.loco || props.Loco || 
                                    props.unit || props.Unit || props.name || props.NAME ||
                                    props.trainName || props.trainNumber || props.train_id ||
                                    props.OBJECTID || props.fid || sourceName + '_' + index;
                            
                            // Extract train number/name
                            var trainNumber = props.service || props.Service || 
                                             props.trainNumber || props.train_number ||
                                             props.train || props.Train || props.name || 
                                             props.NAME || props.loco || props.Loco || '';
                            
                            // Extract heading/direction
                            var heading = props.heading || props.Heading || props.direction || 
                                         props.Direction || props.bearing || props.Bearing || 0;
                            
                            // Extract speed
                            var speed = props.speed || props.Speed || props.velocity || 
                                       props.Velocity || 0;
                            
                            trains.push({
                                'id': String(id).trim(),
                                'train_number': String(trainNumber).trim(),
                                'x': coords[0],
                                'y': coords[1],
                                'heading': heading,
                                'speed': speed
                            });
                        }
                    } catch(e) {
                        console.log('Error processing feature:', e);
                    }
                });
            } catch(e) {
                console.log('Error accessing source:', e);
            }
            return trains;
        }
        
        var allTrains = [];
        var seenIds = new Set();
        
        // Comprehensive list of possible source names
        var sourceCandidates = [
            // Direct source variables
            'regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource',
            'trainSource', 'markers', 'trainMarkers', 'trainLayerSource', 'vectorSource',
            'trainVectorSource', 'liveTrainsSource', 'trainsSource', 'locomotiveSource',
            'trainPositions', 'trainFeatures', 'pointSource', 'featureSource',
            'railTrains', 'trainPoints', 'trainMarkersLayer',
            
            // Common layer names
            'trainLayer', 'markerLayer', 'pointLayer', 'vectorLayer',
            
            // Check window properties dynamically
        ];
        
        // Add any window properties that might be sources
        for (var key in window) {
            if ((key.includes('train') || key.includes('Train') || key.includes('marker') || 
                 key.includes('Marker') || key.includes('source') || key.includes('Source')) &&
                !sourceCandidates.includes(key)) {
                sourceCandidates.push(key);
            }
        }
        
        sourceCandidates.forEach(function(sourceName) {
            if (window[sourceName]) {
                var trains = extractFromSource(window[sourceName], sourceName);
                trains.forEach(function(train) {
                    if (!seenIds.has(train.id)) {
                        seenIds.add(train.id);
                        allTrains.push(train);
                    }
                });
            }
        });
        
        // Also check if there's a map with layers
        if (window.map && window.map.getLayers) {
            try {
                var layers = window.map.getLayers();
                layers.forEach(function(layer, index) {
                    var source = layer.getSource();
                    if (source) {
                        var trains = extractFromSource(source, 'map_layer_' + index);
                        trains.forEach(function(train) {
                            if (!seenIds.has(train.id)) {
                                seenIds.add(train.id);
                                allTrains.push(train);
                            }
                        });
                    }
                });
            } catch(e) {
                console.log('Error accessing map layers:', e);
            }
        }
        
        return allTrains;
        """
        
        try:
            all_trains = self.driver.execute_script(script)
            print(f"✅ Extracted {len(all_trains)} raw trains")
            return all_trains
        except Exception as e:
            print(f"❌ Error extracting trains: {e}")
            return []
    
    def webmercator_to_latlon(self, x, y):
        """Convert Web Mercator coordinates to lat/lon"""
        try:
            x = float(x)
            y = float(y)
            lon = (x / 20037508.34) * 180
            lat = (y / 20037508.34) * 180
            lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
            return round(lat, 6), round(lon, 6)
        except (ValueError, TypeError):
            return None, None
    
    def filter_australian_trains(self, raw_trains):
        """Filter trains to Australia and convert coordinates"""
        australian_trains = []
        seen_ids = set()
        
        for t in raw_trains:
            # Try to get coordinates - they might be in lat/lon already
            x = t.get('x')
            y = t.get('y')
            
            # Check if coordinates might already be in lat/lon
            if x is not None and y is not None:
                # If values are within reasonable lat/lon ranges, treat as lat/lon
                if -180 <= float(x) <= 180 and -90 <= float(y) <= 90:
                    lat, lon = float(y), float(x)
                else:
                    # Otherwise treat as Web Mercator
                    lat, lon = self.webmercator_to_latlon(x, y)
            else:
                lat, lon = None, None
            
            if lat and lon:
                # Australia bounds (slightly expanded)
                if -45 <= lat <= -9 and 110 <= lon <= 155:
                    train_id = t.get('id', 'unknown')
                    
                    # Avoid duplicates
                    if train_id not in seen_ids:
                        seen_ids.add(train_id)
                        
                        train = {
                            'id': train_id,
                            'train_number': t.get('train_number', train_id),
                            'lat': lat,
                            'lon': lon,
                            'heading': round(float(t.get('heading', 0)), 1),
                            'speed': round(float(t.get('speed', 0)), 1)
                        }
                        australian_trains.append(train)
        
        return australian_trains
    
    def run(self):
        """Main execution method"""
        print("=" * 60)
        print("🚂 RAILOPS - TRAIN SCRAPER")
        print(f"📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        if not TF_USERNAME or not TF_PASSWORD:
            print("❌ Missing credentials in environment")
            return [], "error: missing credentials"
        
        try:
            # Setup
            self.setup_driver()
            
            # Try cookie login first
            cookie_login = self.load_cookies()
            
            if cookie_login:
                # Navigate to main page with cookies
                self.driver.get(TF_LOGIN_URL)
                time.sleep(3)
                
                # Check if login worked
                if "login" in self.driver.current_url.lower():
                    print("⚠️ Cookies expired, doing full login")
                    if not self.login():
                        return [], "error: login failed"
            else:
                # Do full login
                if not self.login():
                    return [], "error: login failed"
            
            # Close any warning popups
            self.close_warning()
            
            # Wait for map to initialize
            print("\n⏳ Waiting for map to load...")
            time.sleep(5)
            
            # Zoom to Australia
            self.zoom_to_australia()
            
            # Run diagnostics to understand page structure
            diagnostics = self.diagnose_page_state()
            
            # Wait for trains to load
            print("⏳ Waiting for trains to populate...")
            time.sleep(10)  # Increased wait time
            
            # Try primary extraction method
            raw_trains = self.extract_trains()
            
            # If no trains found, try DOM extraction
            if len(raw_trains) == 0:
                print("⚠️ No trains found via OpenLayers sources, trying DOM extraction...")
                raw_trains = self.extract_from_dom()
            
            # If still no trains, try one more time after a longer delay
            if len(raw_trains) == 0:
                print("⚠️ Still no trains, waiting longer and retrying...")
                time.sleep(15)
                raw_trains = self.extract_trains()
                if len(raw_trains) == 0:
                    raw_trains = self.extract_from_dom()
            
            # Filter to Australia
            australian_trains = self.filter_australian_trains(raw_trains)
            
            print(f"\n✅ Australian trains: {len(australian_trains)}")
            
            # Return results
            note = f"ok - {len(australian_trains)} trains"
            return australian_trains, note
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return [], f"error: {type(e).__name__}"
        
        finally:
            if self.driver:
                self.driver.quit()
                print("👋 Browser closed")

def write_output(trains, note=""):
    """Write trains to JSON file"""
    payload = {
        "lastUpdated": datetime.datetime.utcnow().isoformat() + "Z",
        "note": note,
        "trains": trains or []
    }
    
    # Create backup if file exists
    if os.path.exists(OUT_FILE):
        backup_name = f"trains_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(OUT_FILE, 'r') as src:
                with open(backup_name, 'w') as dst:
                    dst.write(src.read())
            print(f"💾 Backup created: {backup_name}")
        except:
            pass
    
    # Write new data
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    
    print(f"📝 Output: {len(trains or [])} trains, status: {note}")
    
    # Clean up old backups (keep last 5)
    backups = sorted([f for f in os.listdir('.') if f.startswith('trains_backup_')])
    for old_backup in backups[:-5]:
        try:
            os.remove(old_backup)
        except:
            pass

def main():
    scraper = TrainScraper()
    trains, note = scraper.run()
    write_output(trains, note)
    
    # Exit with appropriate code
    if "error" in note:
        exit(1)
    else:
        exit(0)

if __name__ == "__main__":
    main()
