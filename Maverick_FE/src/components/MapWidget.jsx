import { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { LocateFixed, Map as MapIcon } from 'lucide-react';

const rawLng = import.meta.env.VITE_HOME_LONGITUDE || '-81.3884';
const rawLat = import.meta.env.VITE_HOME_LATITUDE || '28.6611';
const homeLng = parseFloat(rawLng.toString().replace(/['"]/g, ''));
const homeLat = parseFloat(rawLat.toString().replace(/['"]/g, ''));
const HOME_COORDS = [homeLng, homeLat];
const DEFAULT_ZOOM = 10;

export default function MapWidget() {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const flightTrails = useRef({});

  const handleRecenter = () => {
    if (map.current) {
      map.current.flyTo({ center: HOME_COORDS, zoom: DEFAULT_ZOOM, essential: true });
    }
  };

  useEffect(() => {
    // If the map already exists, don't recreate it
    if (map.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      center: HOME_COORDS,
      zoom: DEFAULT_ZOOM,
      style: {
        version: 8,
        glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
        sources: {
          'carto-dark': {
            type: 'raster',
            tiles: [
              'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
              'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
              'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
              'https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'
            ],
            tileSize: 256,
            attribution: '&copy; CARTO'
          }
        },
        layers: [
          {
            id: 'carto-dark-layer',
            type: 'raster',
            source: 'carto-dark',
            paint: { 'raster-opacity': 1 }
          }
        ]
      }
    });

    // Fix for the flexbox sizing issue
    setTimeout(() => { if (map.current) map.current.resize(); }, 250);
    map.current.addControl(new maplibregl.NavigationControl(), 'top-right');

    let flightInterval;

    map.current.on('load', () => {
      
      // 1. HOME ICON
      const homeEl = document.createElement('div');
      homeEl.className = 'flex items-center justify-center w-5 h-5 bg-blue-600 border-2 border-white rounded-full shadow-lg';
      new maplibregl.Marker({ element: homeEl }).setLngLat(HOME_COORDS).addTo(map.current);

      // 2. RADAR LAYER
      fetch('https://api.rainviewer.com/public/weather-maps.json')
        .then(res => res.json())
        .then(rvData => {
          const latestPath = rvData.radar.past[rvData.radar.past.length - 1].path;
          map.current.addSource('rainviewer', { type: 'raster', tiles: [`https://tilecache.rainviewer.com${latestPath}/256/{z}/{x}/{y}/2/1_1.png`], tileSize: 256 });
          map.current.addLayer({ id: 'rainviewer-layer', type: 'raster', source: 'rainviewer', paint: { 'raster-opacity': 0.65 } }, 'carto-dark-layer'); // Ensure radar is below flights
        }).catch(err => console.error("RainViewer failed:", err));

      // 3. FLIGHT SOURCES & LAYERS (Pure Native Rendering)
      
      // Trail Layer
      map.current.addSource('flight-trails', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.current.addLayer({ 
        id: 'flight-trails-layer', 
        type: 'line', 
        source: 'flight-trails', 
        paint: { 'line-color': '#38bdf8', 'line-width': 2, 'line-opacity': 0.5 } 
      });

      // Aircraft Points
      map.current.addSource('flights', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      
      // Simple Dots for Aircraft
      map.current.addLayer({
        id: 'flights-dots', 
        type: 'circle', 
        source: 'flights',
        paint: { 
          'circle-color': '#38bdf8', 
          'circle-radius': 5, 
          'circle-stroke-width': 1.5, 
          'circle-stroke-color': '#ffffff' 
        }
      });

      // Text Labels for Aircraft
      map.current.addLayer({
        id: 'flights-labels', 
        type: 'symbol', 
        source: 'flights',
        layout: {
          'text-field': ['concat', ['get', 'flight'], '\n', ['get', 'alt_baro'], ' ft'],
          'text-font': ['Open Sans Regular'],
          'text-size': 11,
          'text-offset': [1, 0], 
          'text-anchor': 'left',
        },
        paint: { 'text-color': '#ffffff', 'text-halo-color': '#000000', 'text-halo-width': 2 }
      });

      // 4. THE POLLING LOOP
      const updateFlights = async () => {
        try {
          const res = await fetch(`http://${window.location.hostname}:8085/data/aircraft.json`);
          if (!res.ok) return;
          const data = await res.json();

          const activeHexes = new Set();
          const pointFeatures = [];
          const trailFeatures = [];

          data.aircraft.forEach(ac => {
            // Only process aircraft with valid coordinates
            if (ac.lat != null && ac.lon != null) {
              activeHexes.add(ac.hex);

              // Trail Logic
              if (!flightTrails.current[ac.hex]) flightTrails.current[ac.hex] = [];
              const trail = flightTrails.current[ac.hex];
              
              if (trail.length === 0) {
                trail.push([ac.lon, ac.lat]);
              } else {
                const lastPos = trail[trail.length - 1];
                // Only add a new point to the trail if the plane actually moved
                if (lastPos[0] !== ac.lon || lastPos[1] !== ac.lat) {
                  trail.push([ac.lon, ac.lat]);
                }
              }

              // Keep last 45 movements to prevent memory bloat
              if (trail.length > 45) trail.shift();

              // Setup the Point feature
              pointFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [ac.lon, ac.lat] },
                properties: {
                  hex: ac.hex,
                  flight: ac.flight ? ac.flight.trim() : ac.r || 'N/A',
                  alt_baro: ac.alt_baro != null ? ac.alt_baro.toString() : '0'
                }
              });

              // Setup the Trail feature
              if (trail.length > 1) {
                trailFeatures.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: trail } });
              }
            }
          });

          // Cleanup stale trails for planes that flew away
          Object.keys(flightTrails.current).forEach(hex => {
            if (!activeHexes.has(hex)) delete flightTrails.current[hex];
          });

          // Push to MapLibre
          if (map.current && map.current.getSource('flights')) {
            map.current.getSource('flights').setData({ type: 'FeatureCollection', features: pointFeatures });
            map.current.getSource('flight-trails').setData({ type: 'FeatureCollection', features: trailFeatures });
          }
        } catch (err) {
          console.error("Flight poll failed:", err);
        }
      };

      // Start the loop
      updateFlights();
      flightInterval = setInterval(updateFlights, 1000);
    });

    // CRITICAL: Cleanup function to kill the loop and map instance when React unmounts
    return () => {
      if (flightInterval) clearInterval(flightInterval);
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg flex-1 min-h-[450px] lg:min-h-[600px] flex flex-col overflow-hidden">
      <div className="bg-[#161f33] p-4 border-b border-borderSlate flex items-center justify-between z-10">
        <div className="flex items-center gap-2">
          <MapIcon className="text-accentBlue w-5 h-5" />
          <h2 className="text-lg font-semibold text-textSilver">Airspace & Radar</h2>
        </div>
        
        <button
          onClick={handleRecenter}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-[#0b0f19] hover:bg-slate-800 text-slate-300 border border-borderSlate rounded-lg transition-all shadow"
          title="Recenter to Home"
        >
          <LocateFixed className="w-3.5 h-3.5 text-blue-400" />
          <span>Recenter</span>
        </button>
      </div>
      <div ref={mapContainer} className="w-full flex-1 relative bg-[#0b0f19]" />
    </div>
  );
}