<script>
    (function() {
      console.log('🚂 RailOps starting...');

      // Create map
      const map = new ol.Map({
        target: 'map',
        layers: [new ol.layer.Tile({ source: new ol.source.OSM() })],
        view: new ol.View({
          center: ol.proj.fromLonLat([133.7751, -25.2744]),
          zoom: 5
        })
      });

      // Railway layers
      const railLayer = new ol.layer.Tile({
        source: new ol.source.XYZ({ url: 'https://{a-c}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png' }),
        visible: true
      });
      const stationsLayer = new ol.layer.Tile({
        source: new ol.source.XYZ({ url: 'https://{a-c}.tiles.openrailwaymap.org/stations/{z}/{x}/{y}.png' }),
        visible: true
      });
      map.addLayer(railLayer);
      map.addLayer(stationsLayer);

      // Coverage layers
      const ACCC_URL = 'https://spatial.infrastructure.gov.au/server/rest/services/ACCC_Mobile_Sites_and_Coverages/MapServer';
      function covLayer(id) {
        return new ol.layer.Tile({
          source: new ol.source.TileArcGISRest({ url: ACCC_URL, params: { layers: `show:${id}`, transparent: true, format: 'png32' } }),
          opacity: 0.45,
          visible: false
        });
      }
      const covTelstra = covLayer(25);
      const covOptus = covLayer(15);
      const covTPG = covLayer(33);
      const covAll = covLayer(4);
      map.addLayer(covTelstra);
      map.addLayer(covOptus);
      map.addLayer(covTPG);
      map.addLayer(covAll);

      // Controls
      document.getElementById('zoomSelect').addEventListener('change', (e) => {
        if (e.target.value === 'current') {
          if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(pos => {
              map.getView().animate({
                center: ol.proj.fromLonLat([pos.coords.longitude, pos.coords.latitude]),
                zoom: 12
              });
            });
          }
        } else {
          map.getView().animate({ center: ol.proj.fromLonLat([133.7751, -25.2744]), zoom: 5 });
        }
      });

      document.getElementById('resetBtn').addEventListener('click', () => {
        map.getView().animate({ center: ol.proj.fromLonLat([133.7751, -25.2744]), zoom: 5 });
        [covTelstra, covOptus, covTPG, covAll].forEach(l => l.setVisible(false));
        document.querySelectorAll('#layersPanel input').forEach(c => c.checked = false);
        railLayer.setVisible(true);
        stationsLayer.setVisible(true);
        document.getElementById('railChk').checked = true;
        document.getElementById('stationsChk').checked = true;
      });

      document.getElementById('layersBtn').addEventListener('click', () => {
        const p = document.getElementById('layersPanel');
        p.style.display = p.style.display === 'none' ? 'block' : 'none';
      });

      document.getElementById('covTelstra').addEventListener('change', e => covTelstra.setVisible(e.target.checked));
      document.getElementById('covOptus').addEventListener('change', e => covOptus.setVisible(e.target.checked));
      document.getElementById('covTPG').addEventListener('change', e => covTPG.setVisible(e.target.checked));
      document.getElementById('covAll').addEventListener('change', e => covAll.setVisible(e.target.checked));
      document.getElementById('railChk').addEventListener('change', e => railLayer.setVisible(e.target.checked));
      document.getElementById('stationsChk').addEventListener('change', e => stationsLayer.setVisible(e.target.checked));

      document.getElementById('zoomInBtn').addEventListener('click', () => {
        map.getView().animate({ zoom: map.getView().getZoom() + 1 });
      });
      document.getElementById('zoomOutBtn').addEventListener('click', () => {
        map.getView().animate({ zoom: map.getView().getZoom() - 1 });
      });
      document.getElementById('locBtn').addEventListener('click', () => {
        if (navigator.geolocation) {
          navigator.geolocation.getCurrentPosition(pos => {
            map.getView().animate({
              center: ol.proj.fromLonLat([pos.coords.longitude, pos.coords.latitude]),
              zoom: 12
            });
          });
        }
      });

      // Clock
      function updateClock() {
        document.getElementById('clock').textContent = new Date().toLocaleTimeString();
      }
      updateClock();
      setInterval(updateClock, 1000);

      // Train layer
      const trainSource = new ol.source.Vector();
      const trainLayer = new ol.layer.Vector({ source: trainSource, zIndex: 20 });
      map.addLayer(trainLayer);

      // Popup
      const popupEl = document.createElement('div');
      popupEl.className = 'tt-popup';
      const popup = new ol.Overlay({ element: popupEl, positioning: 'bottom-center', offset: [0, -15] });
      map.addOverlay(popup);

      map.on('singleclick', (evt) => {
        const feature = map.forEachFeatureAtPixel(evt.pixel, f => f);
        if (feature) {
          const props = feature.getProperties();
          console.log('Clicked train:', props); // DEBUG
          
          if (props.train_number) {
            popupEl.innerHTML = props.train_number;
            popup.setPosition(evt.coordinate);
          } else {
            popup.setPosition(undefined);
          }
        } else {
          popup.setPosition(undefined);
        }
      });

      // Load trains
      async function loadTrains() {
        try {
          const url = 'https://grahame21.github.io/railops-backend/trains.json?t=' + Date.now();
          console.log('Fetching:', url); // DEBUG
          
          const res = await fetch(url);
          console.log('Response status:', res.status); // DEBUG
          
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          
          const data = await res.json();
          console.log('Data received:', data); // DEBUG
          console.log('Number of trains:', data.trains?.length); // DEBUG
          
          trainSource.clear();
          
          if (data.trains && data.trains.length > 0) {
            console.log('First train:', data.trains[0]); // DEBUG
            
            data.trains.forEach((t, index) => {
              if (t.lat && t.lon) {
                console.log(`Adding train ${index}:`, t); // DEBUG
                
                const feature = new ol.Feature({
                  geometry: new ol.geom.Point(ol.proj.fromLonLat([t.lon, t.lat]))
                });
                
                feature.set('id', t.id);
                feature.set('train_number', t.train_number);
                feature.set('speed', t.speed || 0);
                feature.set('heading', t.heading || 0);
                
                const heading = t.heading || 0;
                const speed = t.speed || 0;
                const color = speed > 0 ? [46, 204, 113, 0.9] : [0, 120, 255, 0.9];
                
                feature.setStyle(new ol.style.Style({
                  image: new ol.style.RegularShape({
                    points: 3,
                    radius: 12,
                    rotation: (heading * Math.PI) / 180,
                    fill: new ol.style.Fill({ color }),
                    stroke: new ol.style.Stroke({ color: [0,0,0,0.8], width: 1.5 })
                  })
                }));
                
                trainSource.addFeature(feature);
              } else {
                console.log('Skipping train with no lat/lon:', t); // DEBUG
              }
            });
            
            console.log('Total features added:', trainSource.getFeatures().length); // DEBUG
            document.getElementById('lastUpdated').innerHTML = `${trainSource.getFeatures().length} trains • ${new Date().toLocaleTimeString()}`;
          } else {
            console.log('No trains in data'); // DEBUG
          }
        } catch (e) {
          console.error('Error:', e); // DEBUG
          document.getElementById('lastUpdated').innerHTML = '❌ Failed to load';
        }
      }

      loadTrains();
      setInterval(loadTrains, 30000);

      // Search
      document.getElementById('searchBtn').addEventListener('click', () => {
        const query = document.getElementById('searchBox').value.trim().toLowerCase();
        if (!query) return;
        
        trainSource.forEachFeature(f => {
          const props = f.getProperties();
          if ((props.train_number && props.train_number.toLowerCase().includes(query)) ||
              (props.id && props.id.toLowerCase().includes(query))) {
            map.getView().animate({
              center: f.getGeometry().getCoordinates(),
              zoom: 14
            });
          }
        });
      });

      console.log('✅ RailOps ready');
    })();
  </script>
