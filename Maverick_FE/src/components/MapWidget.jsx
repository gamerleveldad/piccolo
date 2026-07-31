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
  
  // Store the flight trails (history of coordinates per aircraft hex)
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
        // REQUIRED: Glyphs URL so the map can render aircraft text labels
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

      // --- DYNAMIC AIRCRAFT CHEVRON ---
      // We generate a sleek SVG dart/chevron and add it to the map engine
      const chevronSvg = `<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><path d="M16 4 L24 24 L16 20 L8 24 Z" fill="#06b6d4" stroke="#ffffff" stroke-width="1.5"/></svg>`;
      const img = new Image(32, 32);
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(chevronSvg);
      img.onload = () => map.current.addImage('aircraft-chevron', img);

      // --- ADD FLIGHT DATA SOURCES & LAYERS ---
      
      // 1. The Faint Trails
      map.current.addSource('flight-trails', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.current.addLayer({
        id: 'flight-trails-layer',
        type: 'line',
        source: 'flight-trails',
        paint: {
          'line-color': '#06b6d4',
          'line-width': 1.5,
          'line-opacity': 0.35
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
          
          // Interpolate icon size based on Ground Speed (0 kts = 30% size, 400+ kts = 100% size)
          'icon-size': ['interpolate', ['linear'], ['get', 'gs'], 0, 0.3, 400, 1.0],
          
          // Data Block: Callsign \n Altitude
          'text-field': ['concat', ['get', 'flight'], '\n', ['get', 'alt_baro'], ' ft'],
          'text-font': ['Open Sans Regular'],
          'text-size': 11,
          'text-offset': [1.2, 0], // Pushes the text to the right of the aircraft
          'text-anchor': 'left',
          'text-allow-overlap': false
        },
        paint: {
          'text-color': '#f8fafc',
          'text-halo-color': '#0f172a',
          'text-halo-width': 2
        }
      });

      // --- 1-SECOND POLLING LOOP ---
      const updateFlights = async () => {
        try {
          // Poll your local Ultrafeeder container
          const res = await fetch(`http://${window.location.hostname}:8085/data/aircraft.json`);
          if (!res.ok) return;
          const data = await res.json();

          const activeHexes = new Set();
          const pointFeatures = [];
          const trailFeatures = [];

          data.aircraft.forEach(ac => {
            if (ac.lat && ac.lon) {
              activeHexes.add(ac.hex);

              // Initialize or update the trail history array
              if (!flightTrails.current[ac.hex]) flightTrails.current[ac.hex] = [];
              flightTrails.current[ac.hex].push([ac.lon, ac.lat]);

              // Keep only the last 60 seconds (60 points) of track history to prevent memory leaks
              if (flightTrails.current[ac.hex].length > 60) {
                flightTrails.current[ac.hex].shift();
              }

              // Create the aircraft vector point
              pointFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [ac.lon, ac.lat] },
                properties: {
                  hex: ac.hex,
                  flight: ac.flight ? ac.flight.trim() : ac.r || 'N/A',
                  alt_baro: ac.alt_baro || 0,
                  gs: ac.gs || 0,
                  track: ac.track || 0
                }
              });

              // Create the trailing line segment if we have more than 1 point
              if (flightTrails.current[ac.hex].length > 1) {
                trailFeatures.push({
                  type: 'Feature',
                  geometry: { type: 'LineString', coordinates: flightTrails.current[ac.hex] }
                });
              }
            }
          });

          // Cleanup stale trails (planes that landed or flew out of antenna range)
          Object.keys(flightTrails.current).forEach(hex => {
            if (!activeHexes.has(hex)) {
              delete flightTrails.current[hex];
            }
          });

          // Push the new geometry to the MapLibre engine
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