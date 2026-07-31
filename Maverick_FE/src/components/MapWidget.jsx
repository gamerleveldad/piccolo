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

    map.current.on('load', () => {
      
      // --- 1. HOME ICON MARKER ---
      const homeEl = document.createElement('div');
      homeEl.className = 'flex items-center justify-center w-7 h-7 bg-blue-600 border-2 border-white rounded-full shadow-lg text-white';
      homeEl.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`;
      new maplibregl.Marker({ element: homeEl }).setLngLat(HOME_COORDS).addTo(map.current);

      // --- 2. NON-BLOCKING WEATHER & RADAR ---
      // We use .then() so slow internet APIs don't hold up the local aircraft layers
      fetch('https://api.rainviewer.com/public/weather-maps.json')
        .then(res => res.json())
        .then(rvData => {
          const latestPath = rvData.radar.past[rvData.radar.past.length - 1].path;
          map.current.addSource('rainviewer', { type: 'raster', tiles: [`https://tilecache.rainviewer.com${latestPath}/256/{z}/{x}/{y}/2/1_1.png`], tileSize: 256, maxzoom: 7 });
          map.current.addLayer({ id: 'rainviewer-layer', type: 'raster', source: 'rainviewer', paint: { 'raster-opacity': 0.65 } });
        }).catch(err => console.error("RainViewer failed:", err));

      const tomorrowKey = import.meta.env.VITE_TOMORROW_API_KEY;
      if (tomorrowKey) {
        map.current.addSource('tomorrow-lightning', { type: 'raster', tiles: [`https://api.tomorrow.io/v4/map/tile/{z}/{x}/{y}/lightning/now.png?apikey=${tomorrowKey}`], tileSize: 256 });
        map.current.addLayer({ id: 'tomorrow-lightning-layer', type: 'raster', source: 'tomorrow-lightning', paint: { 'raster-opacity': 0.8 } });
      }

      const updateNWSAlerts = () => {
        fetch('https://api.weather.gov/alerts/active?area=FL')
          .then(res => res.json())
          .then(data => {
            const severeFeatures = data.features?.filter(f => f.geometry !== null && ['Severe Thunderstorm Warning', 'Tornado Warning', 'Flash Flood Warning', 'Special Weather Statement'].includes(f.properties.event)) || [];
            data.features = severeFeatures;
            if (map.current.getSource('nws-alerts')) {
              map.current.getSource('nws-alerts').setData(data);
            } else {
              map.current.addSource('nws-alerts', { type: 'geojson', data });
              map.current.addLayer({ id: 'nws-alerts-fill', type: 'fill', source: 'nws-alerts', paint: { 'fill-color': ['match', ['get', 'event'], 'Tornado Warning', '#ef4444', 'Severe Thunderstorm Warning', '#eab308', 'Flash Flood Warning', '#22c55e', 'Special Weather Statement', '#94a3b8', '#ffffff'], 'fill-opacity': 0.2 } });
              map.current.addLayer({ id: 'nws-alerts-outline', type: 'line', source: 'nws-alerts', paint: { 'line-color': ['match', ['get', 'event'], 'Tornado Warning', '#ef4444', 'Severe Thunderstorm Warning', '#eab308', 'Flash Flood Warning', '#22c55e', 'Special Weather Statement', '#94a3b8', '#ffffff'], 'line-width': 2, 'line-dasharray': [2, 2] } });
            }
          }).catch(err => console.error("NWS alerts failed:", err));
      };
      updateNWSAlerts();
      setInterval(updateNWSAlerts, 120000);

      // --- 3. AIRCRAFT SVG ICON LOAD ---
      const chevronSvg = `<svg width="32" height="32" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"><path d="M16 2 L26 28 L16 22 L6 28 Z" fill="#38bdf8" stroke="#0f172a" stroke-width="2"/></svg>`;
      const img = new Image(32, 32);
      img.onload = () => { if (!map.current.hasImage('aircraft-chevron')) map.current.addImage('aircraft-chevron', img); };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(chevronSvg);

      // --- 4. AIRCRAFT SOURCES & LAYERS ---
      map.current.addSource('flight-trails', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.current.addLayer({ id: 'flight-trails-layer', type: 'line', source: 'flight-trails', paint: { 'line-color': '#38bdf8', 'line-width': 1.5, 'line-opacity': 0.4 } });

      map.current.addSource('flights', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      
      // Fallback Dot Layer (Guarantees we see traffic even if fonts/SVGs fail)
      map.current.addLayer({
        id: 'flights-dots', type: 'circle', source: 'flights',
        paint: { 'circle-color': '#38bdf8', 'circle-radius': 4, 'circle-stroke-width': 1, 'circle-stroke-color': '#0f172a' }
      });

      // Primary Symbol Layer
      map.current.addLayer({
        id: 'flights-layer', type: 'symbol', source: 'flights',
        layout: {
          'icon-image': 'aircraft-chevron',
          'icon-rotate': ['coalesce', ['get', 'track'], 0],
          'icon-allow-overlap': true,
          'icon-ignore-placement': true, // Forces drawing regardless of collisions
          'icon-size': ['interpolate', ['linear'], ['coalesce', ['get', 'gs'], 0], 0, 0.3, 400, 1.0],
          'text-field': ['concat', ['get', 'flight'], '\n', ['get', 'alt_baro'], ' ft'],
          'text-font': ['Open Sans Regular'],
          'text-size': 11,
          'text-offset': [1.2, 0], 
          'text-anchor': 'left',
          'text-allow-overlap': false,
          'text-optional': true // Protects the chevron if the font is missing
        },
        paint: { 'text-color': '#f8fafc', 'text-halo-color': '#0f172a', 'text-halo-width': 2 }
      });

      // --- 5. FLIGHT POLLING LOOP ---
      const updateFlights = async () => {
        try {
          const res = await fetch(`http://192.168.4.55:8085/data/aircraft.json`);
          if (!res.ok) return;
          const data = await res.json();

          const activeHexes = new Set();
          const pointFeatures = [];
          const trailFeatures = [];

          data.aircraft.forEach(ac => {
            if (ac.lat && ac.lon) {
              activeHexes.add(ac.hex);

              if (!flightTrails.current[ac.hex]) flightTrails.current[ac.hex] = [];
              const trail = flightTrails.current[ac.hex];
              
              if (trail.length === 0) {
                trail.push([ac.lon, ac.lat]);
              } else {
                const lastPos = trail[trail.length - 1];
                if (lastPos[0] !== ac.lon || lastPos[1] !== ac.lat) {
                  trail.push([ac.lon, ac.lat]);
                }
              }

              if (trail.length > 60) trail.shift();

              pointFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [ac.lon, ac.lat] },
                properties: {
                  hex: ac.hex,
                  flight: ac.flight ? ac.flight.trim() : ac.r || 'N/A',
                  alt_baro: ac.alt_baro != null ? ac.alt_baro.toString() : '0', 
                  gs: ac.gs || 0,
                  track: ac.track || 0
                }
              });

              if (trail.length > 1) {
                trailFeatures.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: trail } });
              }
            }
          });

          Object.keys(flightTrails.current).forEach(hex => {
            if (!activeHexes.has(hex)) delete flightTrails.current[hex];
          });

          if (map.current.getSource('flights')) {
            map.current.getSource('flights').setData({ type: 'FeatureCollection', features: pointFeatures });
            map.current.getSource('flight-trails').setData({ type: 'FeatureCollection', features: trailFeatures });
          }
        } catch (err) { console.error("Flight poll failed:", err); }
      };

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