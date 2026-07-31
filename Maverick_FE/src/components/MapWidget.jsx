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

// HELPER: Strictly parses all inputs to floats to prevent GeoJSON corruption
const getProjectedCoordinate = (lon, lat, track, gsKts, minutes = 1.5) => {
  const l = parseFloat(lon);
  const t = parseFloat(lat);
  const distDegrees = (parseFloat(gsKts) / 60) * (minutes / 60);
  const brngRad = parseFloat(track) * (Math.PI / 180);
  const latRad = t * (Math.PI / 180);

  const deltaLat = distDegrees * Math.cos(brngRad);
  const deltaLon = (distDegrees * Math.sin(brngRad)) / Math.cos(latRad);

  return [l + deltaLon, t + deltaLat];
};

export default function MapWidget() {
  const mapContainer = useRef(null);
  const map = useRef(null);
  
  const planeMarkers = useRef({});
  const metarMarkers = useRef({});
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

    let flightInterval;
    let metarInterval;

    map.current.on('load', () => {
      
      // --- 1. HOME ICON MARKER ---
      const homeEl = document.createElement('div');
      homeEl.className = 'flex items-center justify-center w-7 h-7 bg-blue-600 border-2 border-white rounded-full shadow-lg text-white z-20';
      homeEl.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`;
      new maplibregl.Marker({ element: homeEl }).setLngLat(HOME_COORDS).addTo(map.current);

      // --- 2. ADD FLIGHT GEOJSON LAYERS FIRST (Sync) ---
      map.current.addSource('flight-trails', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.current.addLayer({ 
        id: 'flight-trails-layer', 
        type: 'line', 
        source: 'flight-trails', 
        paint: { 'line-color': '#38bdf8', 'line-width': 2, 'line-opacity': 0.6 } 
      });

      map.current.addSource('flight-vectors', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.current.addLayer({ 
        id: 'flight-vectors-layer', 
        type: 'line', 
        source: 'flight-vectors', 
        paint: { 'line-color': '#0ea5e9', 'line-width': 2.5, 'line-opacity': 0.9 } 
      });

      // --- 3. WEATHER RADAR & LIGHTNING (Async - Slipped UNDER trails) ---
      fetch('https://api.rainviewer.com/public/weather-maps.json')
        .then(res => res.json())
        .then(rvData => {
          const latestPath = rvData.radar.past[rvData.radar.past.length - 1].path;
          map.current.addSource('rainviewer', { 
            type: 'raster', 
            tiles: [`https://tilecache.rainviewer.com${latestPath}/256/{z}/{x}/{y}/4/1_1.png`], 
            tileSize: 256,
            maxzoom: 7 
          });
          
          const beforeLayer = map.current.getLayer('flight-trails-layer') ? 'flight-trails-layer' : undefined;
          map.current.addLayer({ 
            id: 'rainviewer-layer', 
            type: 'raster', 
            source: 'rainviewer', 
            paint: { 'raster-opacity': 0.65, 'raster-resampling': 'linear' } 
          }, beforeLayer);
        }).catch(err => console.error("RainViewer failed:", err));

      const tomorrowKey = import.meta.env.VITE_TOMORROW_API_KEY;
      if (tomorrowKey) {
        map.current.addSource('tomorrow-lightning', { 
          type: 'raster', 
          tiles: [`https://api.tomorrow.io/v4/map/tile/{z}/{x}/{y}/lightning/now.png?apikey=${tomorrowKey}`], 
          tileSize: 256 
        });
        
        const beforeLayer = map.current.getLayer('flight-trails-layer') ? 'flight-trails-layer' : undefined;
        map.current.addLayer({ 
          id: 'tomorrow-lightning-layer', 
          type: 'raster', 
          source: 'tomorrow-lightning', 
          paint: { 'raster-opacity': 0.8 } 
        }, beforeLayer);
      }

      // --- 4. HTML DOM METAR DOTS ---
      const fetchMETARs = async () => {
        try {
          const airports = 'KSFB,KMCO,KORL,KLEE,KISM,KDAB,KTIX,KDED';
          const targetUrl = encodeURIComponent(`https://aviationweather.gov/api/data/metar?ids=${airports}&format=json`);
          const res = await fetch(`https://api.allorigins.win/raw?url=${targetUrl}`);
          
          if (!res.ok) return;
          const data = await res.json();
          
          data.forEach(obs => {
            if (obs.lat != null && obs.lon != null) {
              const cat = obs.fltCat || 'VFR';
              
              let color = '#64748b'; 
              if (cat === 'VFR') color = '#22c55e'; 
              else if (cat === 'MVFR') color = '#3b82f6'; 
              else if (cat === 'IFR') color = '#ef4444'; 
              else if (cat === 'LIFR') color = '#d946ef'; 

              if (!metarMarkers.current[obs.icaoId]) {
                const el = document.createElement('div');
                el.className = 'flex items-center justify-center pointer-events-none relative z-10';

                const dot = document.createElement('div');
                dot.id = `metar-dot-${obs.icaoId}`;
                dot.className = 'w-3.5 h-3.5 rounded-full border-[1.5px] border-slate-900 shadow-md transition-colors duration-500';
                dot.style.backgroundColor = color;

                const label = document.createElement('div');
                label.className = 'absolute left-4 text-[10px] font-bold text-slate-100 drop-shadow-md bg-slate-900/60 px-1 rounded';
                label.innerText = obs.icaoId;

                el.appendChild(dot);
                el.appendChild(label);

                metarMarkers.current[obs.icaoId] = new maplibregl.Marker({ element: el })
                  .setLngLat([obs.lon, obs.lat])
                  .addTo(map.current);
                  
              } else {
                const el = metarMarkers.current[obs.icaoId].getElement();
                const dot = el.querySelector(`#metar-dot-${obs.icaoId}`);
                if (dot) dot.style.backgroundColor = color;
              }
            }
          });
        } catch (err) {
          console.error("METAR fetch failed:", err);
        }
      };

      fetchMETARs();
      metarInterval = setInterval(fetchMETARs, 300000); 

      // --- 5. AIRCRAFT POLLING ---
      const updateFlights = async () => {
        try {
          const res = await fetch(`http://${window.location.hostname}:8085/data/aircraft.json`);
          if (!res.ok) return;
          const data = await res.json();
          const currentHexes = new Set();
          
          const trailFeatures = [];
          const vectorFeatures = [];

          data.aircraft.forEach(ac => {
            if (ac.lat != null && ac.lon != null) {
              currentHexes.add(ac.hex);

              // STRICT PARSING FOR GEOMETRY ENGINE
              const currentLon = parseFloat(ac.lon);
              const currentLat = parseFloat(ac.lat);
              const heading = parseFloat(ac.track) || 0;
              const speed = parseFloat(ac.gs) || 0;
              
              const flightName = ac.flight ? ac.flight.trim() : ac.r || ac.hex;
              const altitude = ac.alt_baro || 0;
              const scale = speed > 300 ? 1.1 : speed > 150 ? 0.9 : 0.75;

              // --- Process Predictive Vectors ---
              if (speed > 10) { 
                const projected = getProjectedCoordinate(currentLon, currentLat, heading, speed, 1.5);
                vectorFeatures.push({
                  type: 'Feature',
                  geometry: { type: 'LineString', coordinates: [[currentLon, currentLat], projected] },
                  properties: {}
                });
              }

              // --- Process Historical Trails ---
              if (!flightTrails.current[ac.hex]) flightTrails.current[ac.hex] = [];
              const trail = flightTrails.current[ac.hex];
              
              if (trail.length === 0) {
                trail.push([currentLon, currentLat]);
              } else {
                const lastPos = trail[trail.length - 1];
                if (lastPos[0] !== currentLon || lastPos[1] !== currentLat) {
                  trail.push([currentLon, currentLat]);
                }
              }

              if (trail.length > 45) trail.shift(); 

              if (trail.length > 1) {
                trailFeatures.push({ 
                  type: 'Feature', 
                  geometry: { type: 'LineString', coordinates: trail },
                  properties: {}
                });
              }

              // --- Process HTML DOM Markers (Instant Snap) ---
              if (!planeMarkers.current[ac.hex]) {
                const el = document.createElement('div');
                el.className = 'relative flex items-center justify-center pointer-events-none z-30';
                
                const icon = document.createElement('div');
                icon.id = `icon-${ac.hex}`;
                icon.innerHTML = `<svg width="28" height="28" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><path d="M16 2 L26 28 L16 22 L6 28 Z" fill="#38bdf8" stroke="#0f172a" stroke-width="1.5"/></svg>`;
                icon.style.transform = `rotate(${heading}deg) scale(${scale})`;
                icon.style.transition = 'transform 0.5s ease-out';

                const label = document.createElement('div');
                label.id = `label-${ac.hex}`;
                label.className = 'absolute left-6 text-[10px] leading-tight text-white font-semibold bg-slate-900/80 px-1.5 py-0.5 rounded border border-slate-700 whitespace-nowrap';
                label.innerHTML = `${flightName}<br/><span class="text-emerald-400">${altitude} ft</span>`;

                el.appendChild(icon);
                el.appendChild(label);

                planeMarkers.current[ac.hex] = new maplibregl.Marker({ element: el })
                  .setLngLat([currentLon, currentLat])
                  .addTo(map.current);

              } else {
                const marker = planeMarkers.current[ac.hex];
                
                marker.setLngLat([currentLon, currentLat]);

                const el = marker.getElement();
                const icon = el.querySelector(`#icon-${ac.hex}`);
                if (icon) icon.style.transform = `rotate(${heading}deg) scale(${scale})`;

                const label = el.querySelector(`#label-${ac.hex}`);
                if (label) label.innerHTML = `${flightName}<br/><span class="text-emerald-400">${altitude} ft</span>`;
              }
            }
          });

          // Cleanup stale DOM markers and GeoJSON arrays
          Object.keys(planeMarkers.current).forEach(hex => {
            if (!currentHexes.has(hex)) {
              planeMarkers.current[hex].remove();
              delete planeMarkers.current[hex];
              delete flightTrails.current[hex];
            }
          });

          // Update MapLibre GeoJSON Sources
          if (map.current.getSource('flight-trails')) {
            map.current.getSource('flight-trails').setData({ type: 'FeatureCollection', features: trailFeatures });
          }
          if (map.current.getSource('flight-vectors')) {
            map.current.getSource('flight-vectors').setData({ type: 'FeatureCollection', features: vectorFeatures });
          }

        } catch (err) { 
          // Silently fail if SDR feed is temporarily down
        }
      };

      updateFlights();
      flightInterval = setInterval(updateFlights, 1000);
    });

    return () => {
      if (flightInterval) clearInterval(flightInterval);
      if (metarInterval) clearInterval(metarInterval);
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