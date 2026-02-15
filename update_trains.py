def extract_trains_direct(self):
    """Extract train data with real IDs prioritized"""
    print("\n🔍 Extracting trains directly from sources...")
    
    script = """
    var allTrains = [];
    var seenIds = new Set();
    
    // Get all train sources
    var sources = ['regTrainsSource', 'unregTrainsSource', 'markerSource'];
    
    sources.forEach(function(sourceName) {
        var source = window[sourceName];
        if (!source || !source.getFeatures) return;
        
        try {
            var features = source.getFeatures();
            
            features.forEach(function(feature, index) {
                try {
                    var props = feature.getProperties();
                    var geom = feature.getGeometry();
                    
                    if (geom && geom.getType() === 'Point') {
                        var coords = geom.getCoordinates();
                        
                        // Capture ALL possible identifiers
                        var locoNumber = props.loco || props.Loco || props.unit || props.Unit || '';
                        var trainId = props.train_id || props.trainId || props.train_number || props.trainNumber || 
                                     props.service || props.Service || props.name || props.NAME || '';
                        
                        // Use loco as primary ID if available, otherwise use train ID
                        var primaryId = locoNumber || trainId || sourceName + '_' + index;
                        
                        // Extract ALL available properties
                        var trainData = {
                            'id': primaryId,
                            'loco': locoNumber,
                            'train_id': trainId,
                            'train_number': props.train_number || props.trainNumber || '',
                            'unit': props.unit || props.Unit || '',
                            'operator': props.operator || props.Operator || '',
                            'origin': props.origin || props.from || '',
                            'destination': props.destination || props.to || '',
                            'speed': props.speed || props.Speed || 0,
                            'heading': props.heading || props.Heading || 0,
                            'eta': props.eta || props.ETA || '',
                            'status': props.status || props.Status || '',
                            'type': props.type || props.Type || '',
                            'cars': props.cars || props.Cars || 0,
                            'line': props.line || props.Line || props.route || '',
                            'length': props.length || props.Length || '',
                            'weight': props.weight || props.Weight || '',
                            'x': coords[0],
                            'y': coords[1]
                        };
                        
                        // Skip markerSource trains without real identifiers
                        if (sourceName === 'markerSource' && !locoNumber && !trainId) {
                            return;
                        }
                        
                        // Create a unique ID to avoid duplicates
                        var uniqueId = primaryId;
                        if (!seenIds.has(uniqueId)) {
                            seenIds.add(uniqueId);
                            allTrains.push(trainData);
                        }
                    }
                } catch(e) {}
            });
        } catch(e) {}
    });
    
    return allTrains;
    """
    
    try:
        trains = self.driver.execute_script(script)
        print(f"   ✅ Extracted {len(trains)} trains from OpenLayers sources")
        return trains
    except Exception as e:
        print(f"   ❌ Error extracting trains: {e}")
        return []
