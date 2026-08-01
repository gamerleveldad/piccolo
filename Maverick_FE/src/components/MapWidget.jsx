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
const getAircraftStyle = (ac, isMilitary, isLEO) => {
  if (isLEO) return { fill: '#16a34a', stroke: '#fbbf24' }; 
  if (isMilitary) return { fill: '#94a3b8', stroke: '#3f6212' }; 

  // Safely extract flight to check if it's commercial vs GA
  const rawFlight = ac.flight ? ac.flight.trim() : '';
  const airlineCode = rawFlight.substring(0, 3).toUpperCase();
  
  const airlineColors = {
    'SWA': { fill: '#0230c4', stroke: '#ffbf00' }, 
    'JBU': { fill: '#0033a0', stroke: '#ffffff' }, 
    'DAL': { fill: '#e51420', stroke: '#002554' }, 
    'UAL': { fill: '#005da6', stroke: '#ffffff' }, 
    'AAL': { fill: '#dfdfdf', stroke: '#00467f' }, 
    'FFT': { fill: '#006643', stroke: '#ffffff' }, 
    'NKS': { fill: '#ffc40f', stroke: '#000000' }, 
    'ROU': { fill: '#c8102e', stroke: '#ffffff' }, 
    'AAY': { fill: '#01579B', stroke: '#F48820' },
    'ABX': { fill: '#CB0024', stroke: '#2E2E2E' }, 
    'EJA': { fill: '#f8fafc', stroke: '#4e058a' }  
  };

  // 1. Known Airline
  if (rawFlight && airlineColors[airlineCode]) return airlineColors[airlineCode];

  // 2. Unknown Commercial / Charter (Has a flight number, but no color defined)
  if (rawFlight) return { fill: '#f8fafc', stroke: '#4e058a' }; 

  // 3. True General Aviation (No flight number broadcast)
  return { fill: '#f8fafc', stroke: '#0284c7' }; 
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

  const [selectedFlight, setSelectedFlight] = useState(null);
  const selectedHexRef = useRef(null);

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

    const updateFlights = async () => {
      try {
        const res = await fetch(`http://${window.location.hostname}:8085/data/aircraft.json`);
        if (!res.ok) return;
        const data = await res.json();
        const currentHexes = new Set();

        data.aircraft.forEach(ac => {
          if (ac.lat != null && ac.lon != null) {
            currentHexes.add(ac.hex);

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

            const style = getAircraftStyle(ac, isMilitary, isLEO);
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
              
              marker.on('click', () => {
                selectedHexRef.current = ac.hex;
                setSelectedFlight(ac);
                L.DomEvent.stopPropagation(new Event('click'));
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

  const getIdentifiers = () => {
    if (!selectedFlight) return { primary: '', secondary: '' };
    const flightText = selectedFlight.flight ? selectedFlight.flight.trim() : '';
    const regText = selectedFlight.r ? selectedFlight.r.trim() : '';
    const hexText = selectedFlight.hex;

    const primary = flightText || regText || hexText;
    const secondary = (regText && regText !== primary) ? regText : '';

    return { primary, secondary };
  };

  const getPanelStyle = () => {
    if (!selectedFlight) return { fill: '#162032', stroke: '#0f172a' };
    let isMilitary = false;
    let isLEO = false;
    if (selectedFlight.dbFlags) {
      if (selectedFlight.dbFlags & 1) isMilitary = true;
      else if (selectedFlight.dbFlags & 2) isLEO = true;
    }
    return getAircraftStyle(selectedFlight, isMilitary, isLEO);
  };

  const { primary, secondary } = getIdentifiers();
  const panelStyle = getPanelStyle();

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
        
        {/* ADVANCED STATS TAIL PANEL WRAPPER - Handles Drop Shadows over the Clip-Path */}
        {selectedFlight && (
          <div 
            className="absolute z-[1000] bottom-0 left-0 w-full md:bottom-6 md:left-6 md:w-[450px] pointer-events-none transition-all duration-300"
            style={{
              // First shadow mimics a solid 2px border matching the plane body
              // Second shadow provides a soft ambient glow matching the plane trim
              filter: `drop-shadow(0px 0px 2px ${panelStyle.fill}) drop-shadow(0px 0px 15px ${panelStyle.stroke})`
            }}
          >
            <div 
              className={`bg-[#162032] w-full pointer-events-auto flex flex-col overflow-hidden 
                rounded-t-2xl md:rounded-none md:[clip-path:polygon(0%_0%,65%_0%,100%_100%,15%_100%)]
                md:min-h-[400px]`}
            >
              {/* Close Button */}
              <button 
                onClick={closePanel} 
                className="absolute p-1 bg-slate-800/80 rounded-full text-slate-300 hover:text-white hover:bg-red-500/80 z-50 transition-colors
                  top-3 right-4 md:top-4 md:left-6 md:right-auto"
                title="Close Panel"
              >
                <X className="w-3 h-3" />
              </button>

              {/* Content Wrapper */}
              <div className="flex-1 flex flex-col w-full text-slate-100 p-5 md:p-0 md:pt-14 md:pr-4">
                
                {/* 1. TOP: Pilot Telemetry Stats */}
                <div className="flex flex-col text-xs border-b border-slate-700/60 pb-3 md:pr-2">
                  
                  {/* Row 1 */}
                  <div className="grid grid-cols-2 gap-2 md:ml-10">
                    <div>
                      <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block">Altitude</span>
                      <span className="text-sm font-bold text-emerald-400">
                        {selectedFlight.alt_baro != null ? `${selectedFlight.alt_baro.toLocaleString()} ft` : 'Ground'}
                      </span>
                    </div>
                    <div>
                      <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block">Speed</span>
                      <span className="text-sm font-bold text-sky-400">
                        {selectedFlight.gs != null ? `${Math.round(selectedFlight.gs)} kts` : '0 kts'}
                      </span>
                    </div>
                  </div>

                  {/* Row 2 */}
                  <div className="grid grid-cols-2 gap-2 mt-3 md:ml-14">
                    <div>
                      <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block">Climb / Descent</span>
                      <span className="font-semibold text-slate-200">
                        {selectedFlight.baro_rate 
                          ? `${selectedFlight.baro_rate > 0 ? '↑ ' : '↓ '}${Math.abs(selectedFlight.baro_rate).toLocaleString()} fpm`
                          : 'Level'}
                      </span>
                    </div>
                    <div>
                      <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block">Squawk</span>
                      <span className="font-mono font-bold text-amber-400">
                        {selectedFlight.squawk || '----'}
                      </span>
                    </div>
                  </div>

                  {/* Row 3 */}
                  {selectedFlight.track != null && (
                    <div className="grid grid-cols-2 gap-2 mt-3 md:ml-20">
                      <div>
                        <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block">Heading</span>
                        <span className="font-semibold text-slate-200">{Math.round(selectedFlight.track)}°</span>
                      </div>
                      {selectedFlight.category && (
                        <div>
                          <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block">Category</span>
                          <span className="font-semibold text-slate-200">{selectedFlight.category}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* 2. MIDDLE: Aircraft Type (Staggered Right) */}
                <div className="py-3 md:ml-24 md:pr-4">
                  <div className="text-sm font-bold text-slate-100 leading-snug break-words">
                    {selectedFlight.desc || selectedFlight.t || 'Unknown Aircraft'}
                  </div>
                </div>

                {/* 3. LOWER MIDDLE: Callsign & Registration */}
                <div className="pt-3 pb-4 border-t border-slate-700/60 flex items-baseline justify-between md:ml-28 md:mr-24">
                  <span className="text-2xl font-black tracking-tight text-white leading-none truncate">
                    {primary}
                  </span>
                  <span className="text-sm font-bold text-sky-400 font-mono ml-4 shrink-0 text-right">
                    {secondary}
                  </span>
                </div>
              </div>

              {/* 4. BOTTOM: Airline Logo / Tail Graphic */}
              <div className="w-full h-16 md:h-24 bg-slate-900/60 flex items-center justify-center relative mt-auto border-t border-slate-800 md:pl-[15%]">
                {selectedFlight.flight ? (
                  <img 
                    src={`/tails/${selectedFlight.flight.trim().substring(0, 3).toUpperCase()}.svg`} 
                    alt={selectedFlight.flight.trim().substring(0, 3)} 
                    className="w-full h-full object-contain p-2"
                    onError={(e) => {
                      e.target.style.display = 'none';
                      if (e.target.nextSibling) e.target.nextSibling.style.display = 'block';
                    }} 
                  />
                ) : null}
                <div className="hidden text-sm font-black text-slate-400 tracking-wider uppercase">
                  {selectedFlight.flight ? selectedFlight.flight.trim().substring(0, 3) : 'GA / Private'}
                </div>
              </div>

            </div>
          </div>
        )}
      </div>
    </div>
  );
}