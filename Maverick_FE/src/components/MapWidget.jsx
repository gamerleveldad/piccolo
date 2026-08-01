import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { LocateFixed, Map as MapIcon, X } from 'lucide-react';

const rawLng = import.meta.env.VITE_HOME_LONGITUDE || '-81.3884';
const rawLat = import.meta.env.VITE_HOME_LATITUDE || '28.6611';
const homeLng = parseFloat(rawLng.toString().replace(/['"]/g, ''));
const homeLat = parseFloat(rawLat.toString().replace(/['"]/g, ''));
const HOME_COORDS = [homeLat, homeLng];
const DEFAULT_ZOOM = 10;

// HELPER: Determine Chevron Colors
const getAircraftStyle = (ac, isMilitary, isLEO, flightName) => {
  if (isLEO) return { fill: '#16a34a', stroke: '#fbbf24' }; // Sheriff Green & Gold
  if (isMilitary) return { fill: '#94a3b8', stroke: '#3f6212' }; // Grey & Army Green

  const airlineCode = flightName.substring(0, 3).toUpperCase();
  const airlineColors = {
    'SWA': { fill: '#0230c4', stroke: '#ffbf00' }, // Southwest (Blue/Yellow)
    'JBU': { fill: '#0033a0', stroke: '#ffffff' }, // JetBlue
    'DAL': { fill: '#e51420', stroke: '#002554' }, // Delta
    'UAL': { fill: '#005da6', stroke: '#ffffff' }, // United
    'AAL': { fill: '#dfdfdf', stroke: '#00467f' }, // American
    'FFT': { fill: '#006643', stroke: '#ffffff' }, // Frontier
    'NKS': { fill: '#ffc40f', stroke: '#000000' }  // Spirit
  };

  if (airlineColors[airlineCode]) return airlineColors[airlineCode];

  return { fill: '#f8fafc', stroke: '#0284c7' }; // General Aviation (White & Light Blue)
};

export default function MapWidget() {
  const mapContainer = useRef(null);
  const map = useRef(null);
  
  const planeMarkers = useRef({});
  const trailLines = useRef({});
  const metarMarkers = useRef({});
  const flightTrails = useRef({});
  const radarLayer = useRef(null);
  const stormLayer = useRef(null);

  // State for Advanced Stats Tail Panel
  const [selectedFlight, setSelectedFlight] = useState(null);
  const selectedHexRef = useRef(null); // Used to track selection inside the async polling loop

  const handleRecenter = () => {
    if (map.current) {
      map.current.setView(HOME_COORDS, DEFAULT_ZOOM);
    }
  };

  const closePanel = () => {
    setSelectedFlight(null);
    selectedHexRef.current = null;
  };

  useEffect(() => {
    if (map.current) return;

    map.current = L.map(mapContainer.current, {
      center: HOME_COORDS,
      zoom: DEFAULT_ZOOM,
      zoomControl: false, 
      attributionControl: false
    });

    L.control.zoom({ position: 'topright' }).addTo(map.current);

    // Clicking empty map space closes the panel
    map.current.on('click', closePanel);

    setTimeout(() => {
      if (map.current) map.current.invalidateSize();
    }, 400);

    map.current.createPane('radarPane');
    map.current.getPane('radarPane').style.zIndex = 250;
    map.current.createPane('lightningPane');
    map.current.getPane('lightningPane').style.zIndex = 260;
    map.current.createPane('stormPane');
    map.current.getPane('stormPane').style.zIndex = 265;
    map.current.createPane('trailsPane');
    map.current.getPane('trailsPane').style.zIndex = 270;
    map.current.createPane('metarPane');
    map.current.getPane('metarPane').style.zIndex = 290;

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd',
      maxZoom: 19
    }).addTo(map.current);

    const homeIconHtml = `<div class="flex items-center justify-center w-7 h-7 bg-blue-600 border-2 border-white rounded-full shadow-lg text-white">
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
    </div>`;
    const homeIcon = L.divIcon({ html: homeIconHtml, className: '', iconSize: [28, 28], iconAnchor: [14, 14] });
    L.marker(HOME_COORDS, { icon: homeIcon }).addTo(map.current);

    let flightInterval;
    let metarInterval;
    let radarInterval;
    let stormInterval;

    // --- Weather & Radar Fetches ---
    const updateRadar = async () => {
      try {
        const res = await fetch('https://api.rainviewer.com/public/weather-maps.json');
        if (!res.ok) return;
        const rvData = await res.json();
        const latestPath = rvData.radar.past[rvData.radar.past.length - 1].path;
        if (radarLayer.current) map.current.removeLayer(radarLayer.current);
        radarLayer.current = L.tileLayer(`https://tilecache.rainviewer.com${latestPath}/256/{z}/{x}/{y}/4/1_1.png`, {
          pane: 'radarPane', opacity: 0.65, maxNativeZoom: 7
        }).addTo(map.current);
      } catch (err) {}
    };
    updateRadar();
    radarInterval = setInterval(updateRadar, 600000); 

    const tomorrowKey = import.meta.env.VITE_TOMORROW_API_KEY;
    if (tomorrowKey) {
      L.tileLayer(`https://api.tomorrow.io/v4/map/tile/{z}/{x}/{y}/lightning/now.png?apikey=${tomorrowKey}`, {
        pane: 'lightningPane', opacity: 0.8
      }).addTo(map.current);
    }

    const updateStormTracks = async () => {
      try {
        const res = await fetch('https://api.weather.gov/alerts/active?area=FL');
        if (!res.ok) return;
        const data = await res.json();
        const severeAlerts = {
          ...data,
          features: data.features.filter(f => f.geometry && ['Severe Thunderstorm Warning', 'Tornado Warning', 'Flash Flood Warning', 'Special Marine Warning'].includes(f.properties.event))
        };
        if (stormLayer.current) map.current.removeLayer(stormLayer.current);
        stormLayer.current = L.geoJSON(severeAlerts, {
          pane: 'stormPane',
          style: () => ({ color: '#a855f7', weight: 2, opacity: 0.6, fillOpacity: 0.15 })
        }).addTo(map.current);
      } catch (err) {}
    };
    updateStormTracks();
    stormInterval = setInterval(updateStormTracks, 300000);

    const fetchMETARs = async () => {
      try {
        const airports = 'KSFB,KMCO,KORL,KLEE,KISM,KDAB,KTIX,KDED';
        const res = await fetch(`https://api.allorigins.win/raw?url=${encodeURIComponent(`https://aviationweather.gov/api/data/metar?ids=${airports}&format=json`)}`);
        if (!res.ok) return;
        const data = await res.json();
        data.forEach(obs => {
          if (obs.lat != null && obs.lon != null) {
            const cat = obs.fltCat || 'VFR';
            let color = '#64748b'; 
            if (cat === 'VFR') color = '#22c55e'; else if (cat === 'MVFR') color = '#3b82f6'; else if (cat === 'IFR') color = '#ef4444'; else if (cat === 'LIFR') color = '#d946ef'; 
            const iconHtml = `<div class="relative flex items-center justify-center pointer-events-none"><div class="w-3.5 h-3.5 rounded-full border-[1.5px] border-slate-900 shadow-md" style="background-color: ${color}"></div><div class="absolute left-4 text-[10px] font-bold text-slate-100 drop-shadow-md bg-slate-900/60 px-1 rounded">${obs.icaoId}</div></div>`;
            if (!metarMarkers.current[obs.icaoId]) {
              metarMarkers.current[obs.icaoId] = L.marker([obs.lat, obs.lon], { icon: L.divIcon({ html: iconHtml, className: '', iconSize: [0, 0] }), pane: 'metarPane' }).addTo(map.current);
            } else {
              metarMarkers.current[obs.icaoId].getElement().innerHTML = iconHtml;
            }
          }
        });
      } catch (err) {}
    };
    fetchMETARs();
    metarInterval = setInterval(fetchMETARs, 300000); 

    // --- Aircraft Polling ---
    const updateFlights = async () => {
      try {
        const res = await fetch(`http://${window.location.hostname}:8085/data/aircraft.json`);
        if (!res.ok) return;
        const data = await res.json();
        const currentHexes = new Set();

        data.aircraft.forEach(ac => {
          if (ac.lat != null && ac.lon != null) {
            currentHexes.add(ac.hex);

            // If this aircraft is actively selected, continuously update the Side Panel React State
            if (selectedHexRef.current === ac.hex) {
              setSelectedFlight(ac);
            }

            const currentLat = parseFloat(ac.lat);
            const currentLon = parseFloat(ac.lon);
            const heading = parseFloat(ac.track) || 0;
            const speed = parseFloat(ac.gs) || 0;
            
            const flightName = ac.flight ? ac.flight.trim() : ac.r || ac.hex;
            const altitude = ac.alt_baro || 0;
            const scale = speed > 300 ? 1.1 : speed > 150 ? 0.9 : 0.75;
            const readableType = ac.desc ? ac.desc.trim() : (ac.t ? ac.t.trim() : "Unknown Aircraft");

            let isMilitary = false;
            let isLEO = false;
            if (ac.dbFlags) {
              if (ac.dbFlags & 1) isMilitary = true; 
              else if (ac.dbFlags & 2) isLEO = true; 
            }

            // Get dynamic chevron styling
            const style = getAircraftStyle(ac, isMilitary, isLEO, flightName);

            const starIcon = (isMilitary || isLEO) 
              ? `<svg class="inline-block w-3 h-3 text-amber-400 ml-1 mb-0.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>` 
              : '';

            const labelHTML = `${flightName}${starIcon}<br/>
              <span class="text-slate-300 font-normal text-[9px]">${readableType}</span><br/>
              <span class="text-emerald-400">${altitude} ft</span> <span class="text-slate-500 mx-0.5">|</span> <span class="text-sky-300">${speed} kts</span>`;

            if (!flightTrails.current[ac.hex]) flightTrails.current[ac.hex] = [];
            const trail = flightTrails.current[ac.hex];
            if (trail.length === 0 || (trail[trail.length - 1][0] !== currentLat || trail[trail.length - 1][1] !== currentLon)) {
              trail.push([currentLat, currentLon]);
              if (trail.length > 45) trail.shift(); 
            }
            if (trail.length > 1) {
              if (!trailLines.current[ac.hex]) {
                trailLines.current[ac.hex] = L.polyline(trail, { color: style.fill, weight: 1.5, opacity: 0.4, pane: 'trailsPane' }).addTo(map.current);
              } else {
                trailLines.current[ac.hex].setLatLngs(trail);
              }
            }

            const iconHtml = `
              <div class="relative w-[28px] h-[28px] cursor-pointer z-30 group">
                <div id="rotator-${ac.hex}" class="absolute inset-0 flex items-center justify-center" style="transform: rotate(${heading}deg) scale(${scale}); transition: transform 0.5s ease-out;">
                  <div class="relative z-10 drop-shadow-md">
                    <svg width="28" height="28" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">
                      <path d="M16 2 L26 28 L16 22 L6 28 Z" fill="${style.fill}" stroke="${style.stroke}" stroke-width="2"/>
                    </svg>
                  </div>
                </div>
                <div id="label-${ac.hex}" class="absolute left-8 top-1/2 -translate-y-1/2 text-[10px] leading-tight text-white font-semibold bg-slate-900/80 px-1.5 py-0.5 rounded border border-slate-700 whitespace-nowrap group-hover:bg-slate-800 transition-colors">
                  ${labelHTML}
                </div>
              </div>`;

            if (!planeMarkers.current[ac.hex]) {
              const acIcon = L.divIcon({ html: iconHtml, className: '', iconSize: [28, 28], iconAnchor: [14, 14] });
              const marker = L.marker([currentLat, currentLon], { icon: acIcon }).addTo(map.current);
              
              // Bind Leaflet click event to trigger React state
              marker.on('click', () => {
                selectedHexRef.current = ac.hex;
                setSelectedFlight(ac);
                L.DomEvent.stopPropagation(new Event('click')); // Prevent map click from immediately closing it
              });

              planeMarkers.current[ac.hex] = marker;
            } else {
              planeMarkers.current[ac.hex].setLatLng([currentLat, currentLon]);
              const el = planeMarkers.current[ac.hex].getElement();
              if (el) {
                const rotator = el.querySelector(`#rotator-${ac.hex}`);
                if (rotator) rotator.style.transform = `rotate(${heading}deg) scale(${scale})`;
                const label = el.querySelector(`#label-${ac.hex}`);
                if (label) label.innerHTML = labelHTML;
              }
            }
          }
        });

        Object.keys(planeMarkers.current).forEach(hex => {
          if (!currentHexes.has(hex)) {
            if (planeMarkers.current[hex]) { map.current.removeLayer(planeMarkers.current[hex]); delete planeMarkers.current[hex]; }
            if (trailLines.current[hex]) { map.current.removeLayer(trailLines.current[hex]); delete trailLines.current[hex]; }
            delete flightTrails.current[hex];
            
            if (selectedHexRef.current === hex) closePanel();
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
      if (stormInterval) clearInterval(stormInterval);
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  // --- Sub-component Rendering Helpers for the Tail Panel ---
  const renderTailGraphic = () => {
    if (!selectedFlight) return null;
    const flightName = selectedFlight.flight ? selectedFlight.flight.trim() : "";
    const airlineCode = flightName.substring(0, 3).toUpperCase();
    
    // Fallback gradients if local image isn't found
    let gradient = "bg-gradient-to-br from-slate-600 to-slate-800";
    if (selectedFlight.dbFlags & 1) gradient = "bg-gradient-to-br from-slate-400 to-slate-500"; // Mil
    if (selectedFlight.dbFlags & 2) gradient = "bg-gradient-to-br from-green-700 to-green-900"; // LEO
    
    return (
      <div className={`relative w-full h-28 ${gradient} overflow-hidden border-b-4 border-slate-900`}>
        {/* Placeholder instruction: Drop SVG logos in /public/tails/ named SWA.svg, etc. */}
        {flightName && (
          <img 
            src={`/tails/${airlineCode}.svg`} 
            alt={airlineCode} 
            className="absolute inset-0 w-full h-full object-contain p-4 opacity-80"
            onError={(e) => e.target.style.display = 'none'} 
          />
        )}
        <div className="absolute bottom-2 left-8 text-xl font-black text-white/90 drop-shadow-md">
          {flightName || selectedFlight.r || selectedFlight.hex}
        </div>
      </div>
    );
  };

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg flex-1 min-h-[450px] lg:min-h-[600px] flex flex-col overflow-hidden relative">
      <div className="bg-[#161f33] p-4 border-b border-borderSlate flex items-center justify-between z-10">
        <div className="flex items-center gap-2">
          <MapIcon className="text-accentBlue w-5 h-5" />
          <h2 className="text-lg font-semibold text-textSilver">Airspace & Radar</h2>
        </div>
        <button
          onClick={handleRecenter}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-[#0b0f19] hover:bg-slate-800 text-slate-300 border border-borderSlate rounded-lg transition-all shadow"
        >
          <LocateFixed className="w-3.5 h-3.5 text-blue-400" />
          <span>Recenter</span>
        </button>
      </div>

      <div className="relative flex-1 w-full h-full">
        <div ref={mapContainer} className="absolute inset-0 bg-[#0b0f19] z-0" />
        
        {/* ADVANCED STATS TAIL PANEL */}
        {selectedFlight && (
          <div 
            className="absolute right-6 bottom-6 z-[1000] w-72 bg-slate-800 shadow-2xl transition-all duration-300 pointer-events-auto"
            style={{ 
              // Custom polygon mimicking a swept vertical stabilizer facing right
              clipPath: 'polygon(0 100%, 25% 0, 100% 0, 100% 100%)',
              paddingLeft: '15%' // Pushes content right to avoid the slanted cut
            }}
          >
            <button onClick={closePanel} className="absolute top-2 right-2 p-1 bg-slate-900/50 rounded-full text-slate-300 hover:text-white hover:bg-red-500/80 z-50 transition-colors">
              <X className="w-4 h-4" />
            </button>

            {renderTailGraphic()}

            <div className="p-4 flex flex-col gap-3 text-xs">
              <div className="grid grid-cols-2 gap-2 text-slate-300">
                <div className="flex flex-col">
                  <span className="text-slate-500 font-bold uppercase tracking-wider text-[9px]">Aircraft Type</span>
                  <span className="font-semibold text-white truncate" title={selectedFlight.desc || selectedFlight.t}>
                    {selectedFlight.desc || selectedFlight.t || 'Unknown'}
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-slate-500 font-bold uppercase tracking-wider text-[9px]">Registration</span>
                  <span className="font-semibold text-sky-400">{selectedFlight.r || 'N/A'}</span>
                </div>
              </div>

              <div className="h-px bg-slate-700 w-full" />

              <div className="grid grid-cols-2 gap-2 text-slate-300">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Squawk</span>
                  <span className="text-amber-400 font-mono">{selectedFlight.squawk || '----'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Wake Cat</span>
                  <span>{selectedFlight.category || '--'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Msg Count</span>
                  <span>{selectedFlight.messages || 0}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Signal (RSSI)</span>
                  <span className={selectedFlight.rssi < -20 ? "text-emerald-400" : "text-red-400"}>
                    {selectedFlight.rssi ? selectedFlight.rssi.toFixed(1) : '--'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">NIC</span>
                  <span>{selectedFlight.nic || '-'}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">SIL</span>
                  <span>{selectedFlight.sil || '-'}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}