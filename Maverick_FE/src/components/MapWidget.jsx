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

      // --- 2. WEATHER RADAR & LIGHTNING ---
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
          map.current.addLayer({ 
            id: 'rainviewer-layer', 
            type: 'raster', 
            source: 'rainviewer', 
            paint: { 'raster-opacity': 0.65, 'raster-resampling': 'linear' } 
          });
        }).catch(err => console.error("RainViewer failed:", err));

      const tomorrowKey = import.meta.env.VITE_TOMORROW_API_KEY;
      if (tomorrowKey) {
        map.current.addSource('tomorrow-lightning', { 
          type: 'raster', 
          tiles: [`https://api.tomorrow.io/v4/map/tile/{z}/{x}/{y}/lightning/now.png?apikey=${tomorrowKey}`], 
          tileSize: 256 
        });
        map.current.addLayer({ 
          id: 'tomorrow-lightning-layer', 
          type: 'raster', 
          source: 'tomorrow-lightning', 
          paint: { 'raster-opacity': 0.8 } 
        });
      }

      // --- 3. HTML DOM METAR DOTS ---
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
        } catch (err) { }
      };

      fetchMETARs();
      metarInterval = setInterval(fetchMETARs, 300000); 

      // --- 4. AIRCRAFT POLLING ---
      const updateFlights = async () => {
        try {
          const res = await fetch(`http://${window.location.hostname}:8085/data/aircraft.json`);
          if (!res.ok) return;
          const data = await res.json();
          const currentHexes = new Set();

          data.aircraft.forEach(ac => {
            if (ac.lat != null && ac.lon != null) {
              currentHexes.add(ac.hex);

              const currentLon = parseFloat(ac.lon);
              const currentLat = parseFloat(ac.lat);
              const heading = parseFloat(ac.track) || 0;
              const speed = parseFloat(ac.gs) || 0;
              
              const flightName = ac.flight ? ac.flight.trim() : ac.r || ac.hex;
              const altitude = ac.alt_baro || 0;
              const scale = speed > 300 ? 1.1 : speed > 150 ? 0.9 : 0.75;
              
              // 1. Get readable make/model
              const readableType = ac.desc ? ac.desc.trim() : (ac.t ? ac.t.trim() : "Unknown Aircraft");

              // 2. Determine category via bitwise operation
              let isSpecial = false;
              if (ac.dbFlags) {
                if (ac.dbFlags & 1) {
                  isSpecial = true; // Military
                } else if (ac.dbFlags & 2) {
                  isSpecial = true; // LEO
                }
              }

              // 3. Prepare the SVG Star if applicable
              const starIcon = isSpecial 
                ? `<svg class="inline-block w-3 h-3 text-amber-400 ml-1 mb-0.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>` 
                : '';

              // Build the full label content
              const labelHTML = `${flightName}${starIcon}<br/><span class="text-slate-300 font-normal text-[9px]">${readableType}</span><br/><span class="text-emerald-400">${altitude} ft</span>`;

              if (!planeMarkers.current[ac.hex]) {
                const el = document.createElement('div');
                el.className = 'relative flex items-center justify-center pointer-events-none z-30';
                
                const rotator = document.createElement('div');
                rotator.id = `rotator-${ac.hex}`;
                rotator.className = 'relative flex items-center justify-center';
                rotator.style.transform = `rotate(${heading}deg) scale(${scale})`;
                rotator.style.transition = 'transform 0.5s ease-out';

                const icon = document.createElement('div');
                icon.innerHTML = `<svg width="28" height="28" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><path d="M16 2 L26 28 L16 22 L6 28 Z" fill="#38bdf8" stroke="#0f172a" stroke-width="1.5"/></svg>`;
                icon.className = 'relative z-10'; 

                const label = document.createElement('div');
                label.id = `label-${ac.hex}`;
                label.className = 'absolute left-6 text-[10px] leading-tight text-white font-semibold bg-slate-900/80 px-1.5 py-0.5 rounded border border-slate-700 whitespace-nowrap';
                label.innerHTML = labelHTML;

                rotator.appendChild(icon);
                el.appendChild(rotator);
                el.appendChild(label);

                planeMarkers.current[ac.hex] = new maplibregl.Marker({ element: el })
                  .setLngLat([currentLon, currentLat])
                  .addTo(map.current);

              } else {
                const marker = planeMarkers.current[ac.hex];
                marker.setLngLat([currentLon, currentLat]);

                const el = marker.getElement();
                const rotator = el.querySelector(`#rotator-${ac.hex}`);
                if (rotator) rotator.style.transform = `rotate(${heading}deg) scale(${scale})`;

                const label = el.querySelector(`#label-${ac.hex}`);
                if (label) label.innerHTML = labelHTML;
              }
            }
          });

          // Cleanup stale DOM markers
          Object.keys(planeMarkers.current).forEach(hex => {
            if (!currentHexes.has(hex)) {
              planeMarkers.current[hex].remove();
              delete planeMarkers.current[hex];
            }
          });

        } catch (err) { }
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