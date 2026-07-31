import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { LocateFixed, Map as MapIcon } from 'lucide-react';

const rawLng = import.meta.env.VITE_HOME_LONGITUDE || '-81.3884';
const rawLat = import.meta.env.VITE_HOME_LATITUDE || '28.6611';
const homeLng = parseFloat(rawLng.toString().replace(/['"]/g, ''));
const homeLat = parseFloat(rawLat.toString().replace(/['"]/g, ''));
const HOME_COORDS = [homeLat, homeLng]; // Leaflet uses [Lat, Lng]
const DEFAULT_ZOOM = 10;

export default function MapWidget() {
  const mapContainer = useRef(null);
  const map = useRef(null);
  
  // State Tracking
  const planeMarkers = useRef({});
  const trailLines = useRef({});
  const metarMarkers = useRef({});
  const flightTrails = useRef({});
  const radarLayer = useRef(null);

  const handleRecenter = () => {
    if (map.current) {
      map.current.setView(HOME_COORDS, DEFAULT_ZOOM);
    }
  };

  useEffect(() => {
    if (map.current) return;

    // --- 1. INITIALIZE LEAFLET MAP ---
    map.current = L.map(mapContainer.current, {
      center: HOME_COORDS,
      zoom: DEFAULT_ZOOM,
      zoomControl: false, 
      attributionControl: false
    });

    L.control.zoom({ position: 'topright' }).addTo(map.current);

    // FIX FOR THE GREY VOID: Force Leaflet to recalculate its container size 
    // after the DOM has finished painting the flexbox layout.
    setTimeout(() => {
      if (map.current) map.current.invalidateSize();
    }, 400);

    // --- 2. CREATE STRICT Z-INDEX PANES ---
    map.current.createPane('radarPane');
    map.current.getPane('radarPane').style.zIndex = 250;
    
    map.current.createPane('lightningPane');
    map.current.getPane('lightningPane').style.zIndex = 260;
    
    map.current.createPane('trailsPane');
    map.current.getPane('trailsPane').style.zIndex = 270;
    
    map.current.createPane('metarPane');
    map.current.getPane('metarPane').style.zIndex = 290;

    // --- 3. BASEMAP ---
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd',
      maxZoom: 19
    }).addTo(map.current);

    // --- 4. HOME ICON ---
    const homeIconHtml = `<div class="flex items-center justify-center w-7 h-7 bg-blue-600 border-2 border-white rounded-full shadow-lg text-white">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
    </div>`;
    
    const homeIcon = L.divIcon({ html: homeIconHtml, className: '', iconSize: [28, 28], iconAnchor: [14, 14] });
    L.marker(HOME_COORDS, { icon: homeIcon }).addTo(map.current);

    let flightInterval;
    let metarInterval;
    let radarInterval;

    // --- 5. WEATHER RADAR (10-Min Auto Refresh) ---
    const updateRadar = async () => {
      try {
        const res = await fetch('https://api.rainviewer.com/public/weather-maps.json');
        if (!res.ok) return;
        const rvData = await res.json();
        const latestPath = rvData.radar.past[rvData.radar.past.length - 1].path;
        
        if (radarLayer.current) map.current.removeLayer(radarLayer.current);
        
        radarLayer.current = L.tileLayer(`https://tilecache.rainviewer.com${latestPath}/256/{z}/{x}/{y}/4/1_1.png`, {
          pane: 'radarPane',
          opacity: 0.65,
          maxNativeZoom: 7
        }).addTo(map.current);
      } catch (err) {
        console.error("RainViewer failed:", err);
      }
    };
    updateRadar();
    radarInterval = setInterval(updateRadar, 600000); 

    // --- 6. TOMORROW.IO LIGHTNING ---
    const tomorrowKey = import.meta.env.VITE_TOMORROW_API_KEY;
    if (tomorrowKey) {
      L.tileLayer(`https://api.tomorrow.io/v4/map/tile/{z}/{x}/{y}/lightning/now.png?apikey=${tomorrowKey}`, {
        pane: 'lightningPane',
        opacity: 0.8
      }).addTo(map.current);
    }

    // --- 7. METAR DOTS ---
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

            const iconHtml = `
              <div class="relative flex items-center justify-center pointer-events-none">
                <div class="w-3.5 h-3.5 rounded-full border-[1.5px] border-slate-900 shadow-md" style="background-color: ${color}"></div>
                <div class="absolute left-4 text-[10px] font-bold text-slate-100 drop-shadow-md bg-slate-900/60 px-1 rounded">${obs.icaoId}</div>
              </div>`;

            if (!metarMarkers.current[obs.icaoId]) {
              const mIcon = L.divIcon({ html: iconHtml, className: '', iconSize: [0, 0], iconAnchor: [0, 0] });
              metarMarkers.current[obs.icaoId] = L.marker([obs.lat, obs.lon], { icon: mIcon, pane: 'metarPane' }).addTo(map.current);
            } else {
              const el = metarMarkers.current[obs.icaoId].getElement();
              if (el) el.innerHTML = iconHtml;
            }
          }
        });
      } catch (err) { }
    };
    fetchMETARs();
    metarInterval = setInterval(fetchMETARs, 300000); 

    // --- 8. AIRCRAFT POLLING ---
    const updateFlights = async () => {
      try {
        const res = await fetch(`http://${window.location.hostname}:8085/data/aircraft.json`);
        if (!res.ok) return;
        const data = await res.json();
        const currentHexes = new Set();

        data.aircraft.forEach(ac => {
          if (ac.lat != null && ac.lon != null) {
            currentHexes.add(ac.hex);

            const currentLat = parseFloat(ac.lat);
            const currentLon = parseFloat(ac.lon);
            const heading = parseFloat(ac.track) || 0;
            const speed = parseFloat(ac.gs) || 0;
            
            const flightName = ac.flight ? ac.flight.trim() : ac.r || ac.hex;
            const altitude = ac.alt_baro || 0;
            const scale = speed > 300 ? 1.1 : speed > 150 ? 0.9 : 0.75;
            
            const readableType = ac.desc ? ac.desc.trim() : (ac.t ? ac.t.trim() : "Unknown Aircraft");

            let isSpecial = false;
            if (ac.dbFlags) {
              if (ac.dbFlags & 1) isSpecial = true; 
              else if (ac.dbFlags & 2) isSpecial = true; 
            }

            const starIcon = isSpecial 
              ? `<svg class="inline-block w-3 h-3 text-amber-400 ml-1 mb-0.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>` 
              : '';

            // Cleanly integrated ground speed beside the altitude
            const labelHTML = `${flightName}${starIcon}<br/>
              <span class="text-slate-300 font-normal text-[9px]">${readableType}</span><br/>
              <span class="text-emerald-400">${altitude} ft</span> <span class="text-slate-500 mx-0.5">|</span> <span class="text-sky-300">${speed} kts</span>`;

            // --- Historical Trails ---
            if (!flightTrails.current[ac.hex]) flightTrails.current[ac.hex] = [];
            const trail = flightTrails.current[ac.hex];
            
            if (trail.length === 0 || (trail[trail.length - 1][0] !== currentLat || trail[trail.length - 1][1] !== currentLon)) {
              trail.push([currentLat, currentLon]);
              if (trail.length > 45) trail.shift(); 
            }

            if (trail.length > 1) {
              if (!trailLines.current[ac.hex]) {
                trailLines.current[ac.hex] = L.polyline(trail, { color: '#38bdf8', weight: 1.5, opacity: 0.35, pane: 'trailsPane' }).addTo(map.current);
              } else {
                trailLines.current[ac.hex].setLatLngs(trail);
              }
            }

            // --- HTML DOM Markers ---
            const iconHtml = `
              <div class="relative flex items-center justify-center pointer-events-none z-30">
                <div id="rotator-${ac.hex}" class="relative flex items-center justify-center" style="transform: rotate(${heading}deg) scale(${scale}); transition: transform 0.5s ease-out;">
                  <div class="relative z-10">
                    <svg width="28" height="28" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><path d="M16 2 L26 28 L16 22 L6 28 Z" fill="#38bdf8" stroke="#0f172a" stroke-width="1.5"/></svg>
                  </div>
                </div>
                <div id="label-${ac.hex}" class="absolute left-4 text-[10px] leading-tight text-white font-semibold bg-slate-900/80 px-1.5 py-0.5 rounded border border-slate-700 whitespace-nowrap">
                  ${labelHTML}
                </div>
              </div>`;

            if (!planeMarkers.current[ac.hex]) {
              const acIcon = L.divIcon({ html: iconHtml, className: '', iconSize: [0, 0], iconAnchor: [0, 0] });
              planeMarkers.current[ac.hex] = L.marker([currentLat, currentLon], { icon: acIcon }).addTo(map.current);
            } else {
              planeMarkers.current[ac.hex].setLatLng([currentLat, currentLon]);
              const el = planeMarkers.current[ac.hex].getElement();
              if (el) el.innerHTML = iconHtml;
            }
          }
        });

        // Cleanup stale data
        Object.keys(planeMarkers.current).forEach(hex => {
          if (!currentHexes.has(hex)) {
            if (planeMarkers.current[hex]) { map.current.removeLayer(planeMarkers.current[hex]); delete planeMarkers.current[hex]; }
            if (trailLines.current[hex]) { map.current.removeLayer(trailLines.current[hex]); delete trailLines.current[hex]; }
            delete flightTrails.current[hex];
          }
        });

      } catch (err) { }
    };

    updateFlights();
    flightInterval = setInterval(updateFlights, 1000);

    return () => {
      if (flightInterval) clearInterval(flightInterval);
      if (metarInterval) clearInterval(metarInterval);
      if (radarInterval) clearInterval(radarInterval);
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg flex-1 min-h-[450px] lg:min-h-[600px] flex flex-col overflow-hidden">
      <div className="bg-[#161f33] p-4 border-b border-borderSlate flex items-center justify-between z-10 relative">
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
      <div ref={mapContainer} className="w-full flex-1 relative bg-[#0b0f19] z-0" />
    </div>
  );
}