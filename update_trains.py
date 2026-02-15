def extract_trains_direct(self):
    """Direct extraction of train data from OpenLayers sources"""
    print("\n🔍 Extracting trains directly from sources...")
    
    script = """
    var allTrains = [];
    var seenIds = new Set();
    
    // Check ALL sources including arrow markers
    var sources = ['regTrainsSource', 'unregTrainsSource', 'markerSource', 'arrowMarkersSource'];
    
    sources.forEach(function(sourceName) {
        var source = window[sourceName];
        if (!source || !source.getFeatures) return;
        
        try {
            var features = source.getFeatures();
            console.log(sourceName + ' has ' + features.length + ' features');
            
            features.forEach(function(feature, index) {
                try {
                    var props = feature.getProperties();
                    var geom = feature.getGeometry();
                    
                    // Log ALL property names for debugging
                    console.log(sourceName + ' feature ' + index + ' properties:', Object.keys(props));
                    
                    if (geom && geom.getType() === 'Point') {
                        var coords = geom.getCoordinates();
                        
                        // Dump ALL properties for first few features
                        if (index < 3) {
                            console.log(sourceName + ' feature ' + index + ' full props:', JSON.stringify(props, null, 2));
                        }
                        
                        // Extract ALL available properties
                        var trainData = {
                            'id': props.id || props.ID || props.loco || props.Loco || 
                                  props.unit || props.Unit || props.name || sourceName + '_' + index,
                            'train_number': props.train_number || props.service || props.name || '',
                            'loco': props.loco || props.Loco || '',
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
                            'all_props': Object.keys(props),  // Store all available property names
                            'x': coords[0],
                            'y': coords[1]
                        };
                        
                        // Create a unique ID
                        var uniqueId = trainData.id;
                        if (!seenIds.has(uniqueId)) {
                            seenIds.add(uniqueId);
                            allTrains.push(trainData);
                        }
                    }
                } catch(e) {
                    console.log('Error processing feature:', e);
                }
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
