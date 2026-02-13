# In your update_trains.py, replace the extraction section with this:

def login_and_get_trains():
    # ... [your existing login code stays the same] ...
    
    # STEP 3: ZOOM TO AUSTRALIA
    print("\n🌏 Zooming to Australia...")
    driver.execute_script("""
        if (window.map) {
            var australia = [112, -44, 154, -10];
            var proj = window.map.getView().getProjection();
            var extent = ol.proj.transformExtent(australia, 'EPSG:4326', proj);
            window.map.getView().fit(extent, { duration: 1000, maxZoom: 10 });
        }
    """)
    time.sleep(10)  # Wait for trains to load
    
    # STEP 4: EXTRACT REAL TRAIN DATA
    print("\n🔍 Extracting REAL train data...")
    
    extract_script = """
    var allTrains = [];
    var seenIds = new Set();
    
    function extractFromSource(source, sourceName) {
        if (!source || !source.getFeatures) return;
        
        try {
            var features = source.getFeatures();
            features.forEach(function(f) {
                try {
                    var props = f.getProperties();
                    var geom = f.getGeometry();
                    
                    if (geom) {
                        var coords = geom.getCoordinates();
                        var lon = coords[0];
                        var lat = coords[1];
                        
                        // Only Australian trains
                        if (lat >= -45 && lat <= -10 && lon >= 110 && lon <= 155) {
                            
                            // 🔥 CRITICAL: Get the REAL locomotive number
                            // Try every possible field name for train ID
                            var loco = props.loco || props.Loco || 
                                      props.unit || props.Unit ||
                                      props.id || props.ID ||
                                      props.name || props.Name ||
                                      props.trainId || props.TrainId ||
                                      props.vehicle || props.Vehicle ||
                                      props.locomotive || props.Locomotive ||
                                      '';
                            
                            // If we still don't have a real ID, try to get it from the feature ID
                            if (!loco || loco.includes('Source') || loco.includes('Layer')) {
                                loco = f.getId() || f.id_ || f.id || '';
                                // Clean up OpenLayers internal IDs
                                loco = String(loco).replace(/^(regTrainsSource|unregTrainsSource|markerSource|arrowMarkersSource)[._]/, '');
                                loco = loco.replace(/[._]source$/, '');
                            }
                            
                            // Get heading/direction
                            var heading = props.heading || props.Heading || 
                                         props.rotation || props.Rotation ||
                                         props.bearing || props.Bearing || 0;
                            
                            // Get speed
                            var speed = props.speed || props.Speed ||
                                       props.velocity || props.Velocity || 0;
                            
                            // Get operator
                            var operator = props.operator || props.Operator ||
                                          props.railway || props.Railway || '';
                            
                            // Get service/train number
                            var service = props.service || props.Service ||
                                         props.trainNumber || props.TrainNumber ||
                                         props.run || props.Run || '';
                            
                            // Get destination
                            var destination = props.destination || props.Destination ||
                                             props.to || props.To || props.headsign || '';
                            
                            // Get line/route
                            var line = props.line || props.Line ||
                                      props.route || props.Route || '';
                            
                            // Get timestamp
                            var timestamp = props.timestamp || props.Timestamp ||
                                           props.lastSeen || props.LastSeen ||
                                           props.updated || props.Updated || '';
                            
                            // Only add if we have a valid loco number (not empty and not a source name)
                            if (loco && !loco.includes('Source') && !loco.includes('Layer')) {
                                var id = loco.toString();
                                
                                if (!seenIds.has(id)) {
                                    seenIds.add(id);
                                    allTrains.push({
                                        'id': id,
                                        'loco': loco.toString(),
                                        'lat': lat,
                                        'lon': lon,
                                        'heading': Number(heading),
                                        'speed': Number(speed),
                                        'operator': String(operator),
                                        'service': String(service),
                                        'destination': String(destination),
                                        'line': String(line),
                                        'timestamp': String(timestamp),
                                        'source': sourceName
                                    });
                                }
                            }
                        }
                    }
                } catch(e) {}
            });
        } catch(e) {}
    }
    
    // Extract from ALL train sources
    var sources = [
        { name: 'regTrainsSource', obj: window.regTrainsSource },
        { name: 'unregTrainsSource', obj: window.unregTrainsSource }
    ];
    
    sources.forEach(function(s) {
        if (s.obj) {
            extractFromSource(s.obj, s.name);
            if (s.obj.getSource) {
                extractFromSource(s.obj.getSource(), s.name);
            }
        }
    });
    
    return allTrains;
    """
    
    train_features = driver.execute_script(extract_script)
    print(f"\n✅ Found {len(train_features)} Australian trains with REAL IDs")
    
    # Show sample of what we found
    if train_features:
        print("\n📋 Sample train data:")
        sample = train_features[0]
        print(f"   Loco: {sample.get('loco', 'N/A')}")
        print(f"   Heading: {sample.get('heading', 0)}°")
        print(f"   Speed: {sample.get('speed', 0)} km/h")
        print(f"   Operator: {sample.get('operator', 'N/A')}")
        print(f"   Service: {sample.get('service', 'N/A')}")
        print(f"   Destination: {sample.get('destination', 'N/A')}")
