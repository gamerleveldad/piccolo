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
            attribution: '&copy; OpenStreetMap &copy; CARTO'
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

    setTimeout(() => { if (map.current) map.current.resize(); }, 250);
    map.current.addControl(new maplibregl.NavigationControl(), 'top-right');

    map.current.on('load', async () => {
      
      // --- ADD HOME ICON MARKER ---
      const homeEl = document.createElement('div');
      homeEl.className = 'flex items-center justify-center w-7 h-7 bg-blue-600 border-2 border-white rounded-full shadow-lg text-white';
      homeEl.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`;
      new maplibregl.Marker({ element: homeEl }).setLngLat(HOME_COORDS).addTo(map.current);

      // --- DYNAMIC AIRCRAFT CHEVRON & LAYERS ---
      const chevronSvg = `<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><path d="M16 2 L26 28 L16 22 L6 28 Z" fill="#38bdf8" stroke="#0f172a" stroke-width="2"/></svg>`;
      const img = new Image(32, 32);
      
      // Wait for image to load BEFORE adding layers to prevent race conditions
      img.onload = () => {
        if (!map.current.hasImage('aircraft-chevron')) {
          map.current.addImage('aircraft-chevron', img);
        }

        // 1. The Faint Trails
        map.current.addSource('flight-trails', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.current.addLayer({
          id: 'flight-trails-layer',
          type: 'line',
          source: 'flight-trails',
          paint: {
            'line-color': '#38bdf8',
            'line-width': 1.5,
            'line-opacity': 0.4
          }
        });

        // 2. The Aircraft Vectors & Data Blocks
        map.current.addSource('flights', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.current.addLayer({
          id: 'flights-layer',
          type: 'symbol',
          source: 'flights',
          layout: {
            'icon-image': 'aircraft-chevron',
            'icon-rotate': ['get', 'track'],
            'icon-allow-overlap': true,
            'icon-size': ['interpolate', ['linear'], ['get', 'gs'], 0, 0.3, 400, 1.0],
            // Concatenate strings directly
            'text-field': ['concat', ['get', 'flight'], '\n', ['get', 'alt_baro'], ' ft'],
            'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'],
            'text-size': 11,
            'text-offset': [1.2, 0], 
            'text-anchor': 'left',
            'text-allow-overlap': false
          },
          paint: {
            'text-color': '#f8fafc',
            'text-halo-color': '#0f172a',
            'text-halo-width': 2
          }
        });
      };
      
      // Trigger the image load
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(chevronSvg);

      // --- 1-SECOND POLLING LOOP ---
      const updateFlights = async () => {
        try {
          // Explicitly targets the IP you provided for the Ultrafeeder backend
          const res = await fetch(`http://192.168.4.55:8085/data/aircraft.json`);
          if (!res.ok) return;
          const data = await res.json();

          const activeHexes = new Set();
          const pointFeatures = [];
          const trailFeatures = [];

          data.aircraft.forEach(ac => {
            if (ac.lat && ac.lon) {
              activeHexes.add(ac.hex);

              // 1. Manage Trail History & Deduplication
              if (!flightTrails.current[ac.hex]) flightTrails.current[ac.hex] = [];
              const trail = flightTrails.current[ac.hex];
              
              if (trail.length === 0) {
                trail.push([ac.lon, ac.lat]);
              } else {
                // Only push a new coordinate if the aircraft actually moved
                const lastPos = trail[trail.length - 1];
                if (lastPos[0] !== ac.lon || lastPos[1] !== ac.lat) {
                  trail.push([ac.lon, ac.lat]);
                }
              }

              // Keep the last 60 movements
              if (trail.length > 60) trail.shift();

              // 2. Create Aircraft Point
              pointFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [ac.lon, ac.lat] },
                properties: {
                  hex: ac.hex,
                  flight: ac.flight ? ac.flight.trim() : ac.r || 'N/A',
                  // CONVERT TO STRING HERE to prevent MapLibre validation errors
                  alt_baro: ac.alt_baro != null ? ac.alt_baro.toString() : '0', 
                  gs: ac.gs || 0,
                  track: ac.track || 0
                }
              });

              // 3. Create Trail Line
              if (trail.length > 1) {
                trailFeatures.push({
                  type: 'Feature',
                  geometry: { type: 'LineString', coordinates: trail }
                });
              }
            }
          });

          // Cleanup stale trails
          Object.keys(flightTrails.current).forEach(hex => {
            if (!activeHexes.has(hex)) delete flightTrails.current[hex];
          });

          // Update Map Data
          if (map.current.getSource('flights')) {
            map.current.getSource('flights').setData({ type: 'FeatureCollection', features: pointFeatures });
            map.current.getSource('flight-trails').setData({ type: 'FeatureCollection', features: trailFeatures });
          }
        } catch (err) {
          console.error("Flight poll failed:", err);
        }
      };

      // Fire immediately, then every 1000ms
      updateFlights();
      setInterval(updateFlights, 1000);
    });

    return () => map.current?.remove();
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