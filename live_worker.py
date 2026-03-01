EXTRACT_SCRIPT = r"""
(function() {

  function collectFromSource(src) {
    if (!src || !src.getFeatures) return [];
    var feats = src.getFeatures() || [];
    var out = [];
    for (var i = 0; i < feats.length; i++) {
      try {
        var f = feats[i];
        var props = f.getProperties ? f.getProperties() : {};
        var geom = f.getGeometry ? f.getGeometry() : null;
        if (!geom || !geom.getCoordinates) continue;
        var coords = geom.getCoordinates();
        if (!coords || coords.length < 2) continue;
        out.push({ props: props, x: coords[0], y: coords[1] });
      } catch(e) {}
    }
    return out;
  }

  var rows = [];

  // 1) Try known TrainFinder globals first
  var globals = [
    'regTrainsSource','unregTrainsSource','markerSource',
    'arrowMarkersSource','trainSource','trainMarkers'
  ];
  for (var g = 0; g < globals.length; g++) {
    try {
      rows = rows.concat(collectFromSource(window[globals[g]]));
    } catch(e) {}
  }

  // 2) If still empty, traverse any OpenLayers map layers we can find
  if (rows.length === 0) {
    try {
      var maps = [];

      // common names
      if (window.map && window.map.getLayers) maps.push(window.map);
      if (window.tfMap && window.tfMap.getLayers) maps.push(window.tfMap);

      // try to discover any map-like object on window
      for (var k in window) {
        try {
          var v = window[k];
          if (v && v.getLayers && v.getView && typeof v.getLayers === 'function') {
            maps.push(v);
          }
        } catch(e) {}
      }

      // walk layers
      var seen = new Set();
      maps.forEach(function(m) {
        try {
          var layers = m.getLayers().getArray();
          layers.forEach(function(layer) {
            try {
              var src = layer.getSource ? layer.getSource() : null;
              if (!src || !src.getFeatures) return;
              collectFromSource(src).forEach(function(r) {
                var id = (r.props && (r.props.id || r.props.ID)) || '';
                var key = String(id) + '|' + String(r.x) + '|' + String(r.y);
                if (seen.has(key)) return;
                seen.add(key);
                rows.push(r);
              });
            } catch(e) {}
          });
        } catch(e) {}
      });
    } catch(e) {}
  }

  // 3) Normalize to train-like objects
  return rows.map(function(r, idx) {
    var p = r.props || {};
    return {
      id: p.id || p.ID || ('feat_' + idx),
      train_number: p.trainNumber || p.train_number || '',
      train_name: p.trainName || p.train_name || '',
      loco: p.loco || p.trKey || '',
      operator: p.operator || '',
      origin: p.serviceFrom || p.origin || '',
      destination: p.serviceTo || p.destination || '',
      heading: p.heading || 0,
      km: p.trainKM || '',
      time: p.trainTime || '',
      date: p.trainDate || '',
      speed_raw: p.trainSpeed || '',
      x: r.x,
      y: r.y
    };
  });

})();
"""
