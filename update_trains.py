def extract_trains(self):
    """Extract train data from OpenLayers sources with ALL available details"""
    script = """
    var allTrains = [];
    var seenIds = new Set();
    
    // Only look at real train sources, ignore arrowMarkersSource
    var sources = ['regTrainsSource', 'unregTrainsSource'];
    
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
                        
                        // Collect ALL available properties
                        var trainData = {
                            'id': props.id || props.ID || '',
                            'loco': props.loco || props.Loco || '',
                            'unit': props.unit || props.Unit || '',
                            'train_number': props.train_number || props.trainNumber || props.service || props.Service || '',
                            'name': props.name || props.NAME || '',
                            'operator': props.operator || props.Operator || '',
                            'origin': props.origin || props.Origin || props.from || props.From || '',
                            'destination': props.destination || props.Destination || props.to || props.To || '',
                            'speed': props.speed || props.Speed || 0,
                            'heading': props.heading || props.Heading || props.direction || props.Direction || 0,
                            'eta': props.eta || props.ETA || '',
                            'distance': props.distance || props.Distance || '',
                            'service': props.service_code || props.serviceNumber || props.trainNumber || '',
                            'consist': props.consist || props.Consist || '',
                            'length': props.length || props.Length || '',
                            'weight': props.weight || props.Weight || '',
                            'source': sourceName,
                            'x': coords[0],
                            'y': coords[1]
                        };
                        
                        // Create a unique ID from available data
                        var uniqueId = trainData.loco || trainData.unit || trainData.train_number || trainData.id || sourceName + '_' + index;
                        
                        if (!seenIds.has(uniqueId)) {
                            seenIds.add(uniqueId);
                            trainData.display_id = uniqueId;
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
    
    return self.driver.execute_script(script)
