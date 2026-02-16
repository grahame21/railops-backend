<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>RailOps — AU Live Map</title>

  <!-- OpenLayers -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ol@7.5.2/ol.css">
  <script src="https://cdn.jsdelivr.net/npm/ol@7.5.2/dist/ol.js"></script>

  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; width: 100%; overflow: hidden; font-family: 'Segoe UI', system-ui, sans-serif; }
    #map { height: 100%; width: 100%; background: #0a1a2a; }
    
    /* Top Toolbar */
    .toolbar {
      position: absolute; top: 12px; left: 12px; z-index: 1000;
      background: rgba(10, 26, 42, 0.95); backdrop-filter: blur(8px);
      color: white; padding: 10px 16px; border-radius: 40px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.5);
      display: flex; gap: 12px; align-items: center;
      border: 1px solid #2a4a7a;
      font-size: 14px; font-weight: 500;
    }
    .toolbar button, .toolbar select {
      background: #1e3a5f; color: white;
      border: 1px solid #3a6a9a; border-radius: 30px;
      padding: 6px 16px; font-size: 13px; font-weight: 600;
      cursor: pointer; transition: all 0.2s;
    }
    .toolbar button:hover {
      background: #2a4a7a; border-color: #5a8aca;
    }
    
    /* Search Bar */
    .search-container {
      position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
      z-index: 1000; width: 380px;
    }
    .search-box {
      background: rgba(10, 26, 42, 0.95); backdrop-filter: blur(8px);
      border-radius: 40px; border: 1px solid #2a4a7a;
      display: flex; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }
    .search-box input {
      flex: 1; background: #1e3a5f; border: 1px solid #3a6a9a;
      border-radius: 40px 0 0 40px; padding: 10px 20px;
      color: white; font-size: 14px; outline: none;
    }
    .search-box input::placeholder { color: #9ab0d0; }
    .search-box button {
      background: #0b57cf; border: none; border-radius: 0 40px 40px 0;
      padding: 10px 24px; color: white; font-weight: 600;
      cursor: pointer; transition: 0.2s;
    }
    
    /* Autocomplete */
    .autocomplete-items {
      position: absolute; top: 100%; left: 0; right: 0;
      background: rgba(10, 26, 42, 0.95); backdrop-filter: blur(8px);
      border: 1px solid #2a4a7a; border-top: none;
      border-radius: 0 0 20px 20px; max-height: 300px;
      overflow-y: auto; z-index: 1001; margin-top: 2px;
    }
    .autocomplete-item {
      padding: 12px 20px; color: white; cursor: pointer;
      border-bottom: 1px solid #1e3a5f; font-size: 13px;
      display: flex; justify-content: space-between;
    }
    .autocomplete-item:hover {
      background: #1e3a5f;
    }
    .autocomplete-item .train-id {
      font-weight: 600; color: #9ab0d0;
    }
    .autocomplete-item .train-loc {
      color: #ffaa00;
    }
    
    /* Status Bar */
    .status-bar {
      position: absolute; top: 12px; right: 12px; z-index: 1000;
      background: rgba(10, 26, 42, 0.95); backdrop-filter: blur(8px);
      color: white; padding: 8px 20px; border-radius: 40px;
      font-size: 13px; border: 1px solid #2a4a7a;
      display: flex; gap: 12px; align-items: center;
    }
    .train-count {
      background: #0b57cf; padding: 2px 12px;
      border-radius: 30px; font-weight: 700;
    }
    
    /* Layers Panel */
    .layers-panel {
      position: absolute; left: 12px; bottom: 12px; z-index: 1000;
      background: rgba(10, 26, 42, 0.95); backdrop-filter: blur(8px);
      color: white; border-radius: 20px; padding: 16px;
      border: 1px solid #2a4a7a; width: 260px;
    }
    .layer-row {
      display: flex; align-items: center; gap: 10px;
      padding: 8px 0; border-bottom: 1px solid #1e3a5f;
    }
    .layer-row:last-child { border-bottom: none; }
    .section-title {
      color: #9ab0d0; font-size: 12px; margin: 12px 0 4px 0;
    }
    
    /* Train Marker Style - Shows number without hovering */
    .train-label {
      background: rgba(0, 0, 0, 0.7);
      color: white;
      padding: 2px 6px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: bold;
      border: 1px solid #ffaa00;
      white-space: nowrap;
      pointer-events: none;
      text-shadow: 1px 1px 1px black;
    }
    
    /* TrainFinder-style Popup */
    .train-popup {
      position: absolute;
      background: rgba(10, 26, 42, 0.98);
      backdrop-filter: blur(8px);
      color: white;
      padding: 16px;
      border-radius: 16px;
      border: 2px solid #2a4a7a;
      box-shadow: 0 8px 30px rgba(0,0,0,0.9);
      pointer-events: none;
      transform: translate(-50%, -100%);
      min-width: 340px;
      z-index: 10000;
      font-family: 'Segoe UI', sans-serif;
    }
    .train-popup::after {
      content: '';
      position: absolute;
      top: 100%;
      left: 50%;
      transform: translateX(-50%);
      border-width: 10px;
      border-style: solid;
      border-color: #2a4a7a transparent transparent transparent;
    }
    .popup-header {
      font-size: 20px;
      font-weight: 700;
      color: #ffaa00;
      margin-bottom: 8px;
      border-bottom: 1px solid #2a4a7a;
      padding-bottom: 4px;
    }
    .popup-subheader {
      font-size: 14px;
      color: #9ab0d0;
      margin-bottom: 12px;
      font-style: italic;
    }
    .popup-row {
      display: flex;
      margin: 8px 0;
      font-size: 13px;
    }
    .popup-label {
      width: 90px;
      color: #9ab0d0;
      font-weight: 600;
    }
    .popup-value {
      flex: 1;
      color: white;
      font-weight: 500;
    }
    .popup-badge {
      background: #1e3a5f;
      padding: 4px 12px;
      border-radius: 30px;
      font-size: 12px;
      display: inline-block;
      margin-right: 6px;
      margin-top: 4px;
      color: #9ab0d0;
    }
    .popup-speed {
      font-size: 24px;
      font-weight: 700;
      color: #ffaa00;
      text-align: center;
      margin: 12px 0 8px;
      padding: 8px;
      background: rgba(0,0,0,0.3);
      border-radius: 30px;
    }
    .popup-footer {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 8px;
      justify-content: center;
      font-size: 11px;
      color: #9ab0d0;
    }
  </style>
</head>
<body>
  <div class="toolbar">
    <span style="font-weight:700; color:#9ab0d0">🚂 RailOps</span>
    <select id="stateSelect">
      <option value="au">🇦🇺 Australia</option>
      <option value="nsw">📍 NSW</option>
      <option value="vic">📍 VIC</option>
      <option value="qld">📍 QLD</option>
      <option value="sa">📍 SA</option>
      <option value="wa">📍 WA</option>
      <option value="tas">📍 TAS</option>
      <option value="nt">📍 NT</option>
    </select>
    <button id="locateBtn">📍 My Location</button>
    <button id="layersToggleBtn">🗺️ Layers</button>
  </div>

  <div class="search-container">
    <div class="search-box">
      <input type="text" id="searchInput" placeholder="Search train number, loco, or destination...">
      <button id="searchBtn">🔍 Search</button>
    </div>
    <div id="autocompleteList" class="autocomplete-items" style="display: none;"></div>
  </div>

  <div class="status-bar">
    <span id="lastUpdate">Loading...</span>
    <span class="train-count" id="trainCount">0</span>
  </div>

  <div class="layers-panel" id="layersPanel" style="display: none;">
    <h3>🗺️ MAP LAYERS</h3>
    <div class="layer-row"><label><input type="checkbox" id="trainLayerChk" checked> 🚆 Live Trains</label></div>
    <div class="layer-row"><label><input type="checkbox" id="railLayerChk" checked> 🛤️ Rail Lines (Blue)</label></div>
    <div class="layer-row"><label><input type="checkbox" id="stationsLayerChk" checked> 🏢 Stations</label></div>
    <div class="section-title">📱 MOBILE COVERAGE</div>
    <div class="layer-row"><label><input type="checkbox" id="covTelstraChk"> 📶 Telstra</label></div>
    <div class="layer-row"><label><input type="checkbox" id="covOptusChk"> 📶 Optus</label></div>
    <div class="layer-row"><label><input type="checkbox" id="covTPGChk"> 📶 Vodafone/TPG</label></div>
    <div class="layer-row"><label><input type="checkbox" id="covAllChk"> 📶 All Networks</label></div>
  </div>

  <div id="map"></div>

  <script>
    const map = new ol.Map({
      target: 'map',
      layers: [new ol.layer.Tile({ source: new ol.source.OSM() })],
      view: new ol.View({
        center: ol.proj.fromLonLat([133.7751, -25.2744]),
        zoom: 4,
        maxZoom: 18
      })
    });

    map.getView().on('change:rotation', () => map.getView().setRotation(0));

    // Rail layers with blue filter
    const railLayer = new ol.layer.Tile({
      source: new ol.source.XYZ({ url: 'https://{a-c}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png' }),
      visible: true,
      zIndex: 1
    });
    
    railLayer.on('prerender', function(event) {
      event.context.filter = 'hue-rotate(200deg) brightness(0.9) saturate(1.5)';
    });
    railLayer.on('postrender', function(event) {
      event.context.filter = 'none';
    });
    
    const stationsLayer = new ol.layer.Tile({
      source: new ol.source.XYZ({ url: 'https://{a-c}.tiles.openrailwaymap.org/stations/{z}/{x}/{y}.png' }),
      visible: true,
      zIndex: 2
    });
    
    map.addLayer(railLayer);
    map.addLayer(stationsLayer);

    // ACCC coverage layers
    const ACCC_URL = 'https://spatial.infrastructure.gov.au/server/rest/services/ACCC_Mobile_Sites_and_Coverages/MapServer';
    function createAcccLayer(id) {
      return new ol.layer.Tile({
        source: new ol.source.TileArcGISRest({
          url: ACCC_URL,
          params: { layers: `show:${id}`, dpi: 96, transparent: true, format: 'png32' }
        }),
        opacity: 0.45,
        visible: false,
        zIndex: 3
      });
    }
    
    const covTelstra = createAcccLayer(25);
    const covOptus = createAcccLayer(15);
    const covTPG = createAcccLayer(33);
    const covAll = createAcccLayer(4);
    [covTelstra, covOptus, covTPG, covAll].forEach(l => map.addLayer(l));

    // Train layer with custom style showing numbers
    const trainSource = new ol.source.Vector();
    const trainLayer = new ol.layer.Vector({
      source: trainSource,
      visible: true,
      zIndex: 10,
      style: function(feature) {
        const train = feature.get('train_data') || {};
        const trainNumber = train.train_number || train.id || '';
        const trainName = train.train_name || '';
        const speed = train.speed || 0;
        
        // Determine color based on speed
        let dotColor = '#ffaa00'; // default orange
        if (speed > 80) dotColor = '#ff4444'; // red for fast
        else if (speed > 30) dotColor = '#00cc00'; // green for moving
        
        // Create style with label
        return [
          // The dot
          new ol.style.Style({
            image: new ol.style.Circle({
              radius: 8,
              fill: new ol.style.Fill({ color: dotColor }),
              stroke: new ol.style.Stroke({ color: '#ffffff', width: 2 })
            })
          }),
          // The label (train number)
          new ol.style.Style({
            text: new ol.style.Text({
              text: trainName || trainNumber,
              font: 'bold 11px monospace',
              fill: new ol.style.Fill({ color: '#ffffff' }),
              stroke: new ol.style.Stroke({ color: '#000000', width: 3 }),
              offsetY: -18,
              backgroundFill: new ol.style.Fill({ color: 'rgba(0,0,0,0.7)' }),
              backgroundStroke: new ol.style.Stroke({ color: '#ffaa00', width: 1 }),
              padding: [2, 6, 2, 6]
            })
          })
        ];
      }
    });
    map.addLayer(trainLayer);

    let allTrains = [];
    
    async function loadRealTrains() {
      const url = 'https://raw.githubusercontent.com/grahame21/railops-backend/main/trains.json';
      
      try {
        document.getElementById('lastUpdate').innerHTML = 'Loading...';
        
        const response = await fetch(url, { cache: 'no-cache' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        let trains = data.trains || [];
        
        console.log(`✅ Loaded ${trains.length} trains`);
        allTrains = trains;
        
        document.getElementById('trainCount').textContent = trains.length;
        document.getElementById('lastUpdate').innerHTML = 
          `Last: ${new Date(data.lastUpdated).toLocaleTimeString()}`;
        
        trainSource.clear();
        
        trains.forEach(train => {
          if (train.lat && train.lon) {
            try {
              const feature = new ol.Feature({
                geometry: new ol.geom.Point(ol.proj.fromLonLat([train.lon, train.lat]))
              });
              
              // Store ALL train data
              feature.set('train_data', train);
              trainSource.addFeature(feature);
            } catch (e) {
              console.error('Error adding feature:', e);
            }
          }
        });
        
        console.log(`✅ Added ${trainSource.getFeatures().length} trains to map`);
        
      } catch (error) {
        console.error('❌ Failed to load trains:', error);
        document.getElementById('lastUpdate').innerHTML = '⚠️ Update failed';
      }
    }

    // TrainFinder-style hover popup with ALL details
    let popupElement = null;
    
    map.on('pointermove', function(evt) {
      const feature = map.forEachFeatureAtPixel(evt.pixel, function(feature, layer) {
        return layer === trainLayer ? feature : null;
      });
      
      if (popupElement) {
        map.removeOverlay(popupElement);
        popupElement = null;
      }
      
      if (feature) {
        const coords = feature.getGeometry().getCoordinates();
        const train = feature.get('train_data') || {};
        const lonLat = ol.proj.toLonLat(coords);
        
        // Extract all the rich data
        const trainNumber = train.train_number || train.id || 'Unknown';
        const trainName = train.train_name || '';
        const speed = train.speed || 0;
        const origin = train.origin || 'Unknown';
        const destination = train.destination || 'Unknown';
        const description = train.description || '';
        const km = train.km || '';
        const time = train.time || '';
        const date = train.date || '';
        const trKey = train.trKey || '';
        const cId = train.cId ? train.cId.substring(0, 8) + '...' : '';
        
        // Format the header
        let header = trainNumber;
        if (trainName && trainName !== trainNumber) {
          header = `${trainName} [${trainNumber}]`;
        }
        
        const popupDiv = document.createElement('div');
        popupDiv.className = 'train-popup';
        
        popupDiv.innerHTML = `
          <div class="popup-header">
            ${header} - ${speed}km/h
          </div>
          ${description ? `<div class="popup-subheader">${description}</div>` : ''}
          <div class="popup-row">
            <span class="popup-label">Origin:</span>
            <span class="popup-value">${origin}</span>
          </div>
          <div class="popup-row">
            <span class="popup-label">Destination:</span>
            <span class="popup-value">${destination}</span>
          </div>
          ${time || km ? `
          <div class="popup-row">
            <span class="popup-label">ETA/Dist:</span>
            <span class="popup-value">${time || '--:--'} ${km ? `- ${km}` : ''}</span>
          </div>
          ` : ''}
          <div class="popup-speed">
            ⚡ ${speed} km/h
          </div>
          <div class="popup-footer">
            ${trainName ? `<span class="popup-badge">Loco: ${trainName}</span>` : ''}
            ${trKey ? `<span class="popup-badge">Key: ${trKey}</span>` : ''}
            <span class="popup-badge">📍 ${lonLat[1].toFixed(4)}°, ${lonLat[0].toFixed(4)}°</span>
          </div>
        `;
        
        popupElement = new ol.Overlay({
          element: popupDiv,
          position: coords,
          positioning: 'bottom-center',
          offset: [0, -15]
        });
        
        map.addOverlay(popupElement);
      }
    });

    // Enhanced autocomplete
    const searchInput = document.getElementById('searchInput');
    const autocompleteList = document.getElementById('autocompleteList');
    
    function updateAutocomplete() {
      const query = searchInput.value.trim().toLowerCase();
      if (query.length < 2) {
        autocompleteList.style.display = 'none';
        return;
      }
      
      const matches = [];
      const seen = new Set();
      
      allTrains.forEach(train => {
        const searchable = [
          train.train_number,
          train.train_name,
          train.trKey,
          train.origin,
          train.destination,
          train.id
        ].filter(Boolean).map(s => s.toLowerCase());
        
        const matchesQuery = searchable.some(s => s.includes(query));
        
        if (matchesQuery && !seen.has(train.id)) {
          seen.add(train.id);
          matches.push({
            id: train.train_name || train.train_number || train.id,
            full: train,
            lat: train.lat,
            lon: train.lon
          });
        }
      });
      
      if (matches.length > 0) {
        autocompleteList.innerHTML = '';
        matches.slice(0, 8).forEach(match => {
          const item = document.createElement('div');
          item.className = 'autocomplete-item';
          item.innerHTML = `
            <span class="train-id">${match.id}</span>
            <span class="train-loc">${match.full.origin || ''} → ${match.full.destination || ''}</span>
          `;
          item.addEventListener('click', () => {
            searchInput.value = match.id;
            autocompleteList.style.display = 'none';
            flyToTrain(match.lat, match.lon, match.id);
          });
          autocompleteList.appendChild(item);
        });
        autocompleteList.style.display = 'block';
      } else {
        autocompleteList.style.display = 'none';
      }
    }
    
    let debounceTimer;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(updateAutocomplete, 300);
    });
    
    document.addEventListener('click', (e) => {
      if (!searchInput.contains(e.target) && !autocompleteList.contains(e.target)) {
        autocompleteList.style.display = 'none';
      }
    });

    function flyToTrain(lat, lon, trainId) {
      map.getView().animate({
        center: ol.proj.fromLonLat([lon, lat]),
        zoom: 12,
        duration: 1000
      });
    }

    function searchTrains() {
      const query = searchInput.value.trim().toLowerCase();
      if (!query) return;
      
      for (const train of allTrains) {
        const searchable = [
          train.train_number,
          train.train_name,
          train.trKey,
          train.id
        ].filter(Boolean).map(s => s.toLowerCase());
        
        if (searchable.some(s => s.includes(query))) {
          flyToTrain(train.lat, train.lon, train.train_name || train.train_number);
          autocompleteList.style.display = 'none';
          return;
        }
      }
      
      alert('No trains found matching: ' + query);
    }

    // Zoom functions
    const stateBounds = {
      au: [112, -44, 154, -10], nsw: [141, -38, 154, -28], vic: [141, -40, 150, -34],
      qld: [138, -30, 154, -9], sa: [129, -40, 141, -25], wa: [112, -36, 129, -13],
      tas: [143, -44, 149, -39], nt: [129, -27, 138, -10]
    };

    function zoomTo(region) {
      const bounds = stateBounds[region] || stateBounds.au;
      const extent = ol.proj.transformExtent(bounds, 'EPSG:4326', 'EPSG:3857');
      map.getView().fit(extent, { duration: 1000, maxZoom: 10 });
    }

    function zoomToCurrent() {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition(pos => {
        const center = ol.proj.fromLonLat([pos.coords.longitude, pos.coords.latitude]);
        map.getView().animate({ center, zoom: 12, duration: 1000 });
      });
    }

    // Event listeners
    document.getElementById('stateSelect').addEventListener('change', e => zoomTo(e.target.value));
    document.getElementById('locateBtn').addEventListener('click', zoomToCurrent);
    document.getElementById('layersToggleBtn').addEventListener('click', () => {
      const panel = document.getElementById('layersPanel');
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    });
    document.getElementById('searchBtn').addEventListener('click', searchTrains);
    searchInput.addEventListener('keypress', e => { if (e.key === 'Enter') searchTrains(); });

    // Layer toggles
    document.getElementById('trainLayerChk').addEventListener('change', e => trainLayer.setVisible(e.target.checked));
    document.getElementById('railLayerChk').addEventListener('change', e => railLayer.setVisible(e.target.checked));
    document.getElementById('stationsLayerChk').addEventListener('change', e => stationsLayer.setVisible(e.target.checked));
    document.getElementById('covTelstraChk').addEventListener('change', e => covTelstra.setVisible(e.target.checked));
    document.getElementById('covOptusChk').addEventListener('change', e => covOptus.setVisible(e.target.checked));
    document.getElementById('covTPGChk').addEventListener('change', e => covTPG.setVisible(e.target.checked));
    document.getElementById('covAllChk').addEventListener('change', e => covAll.setVisible(e.target.checked));

    // Initial load
    loadRealTrains();
    setInterval(loadRealTrains, 30000);
    zoomTo('au');
  </script>
</body>
</html>
