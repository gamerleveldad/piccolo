import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import * as maplibregl from 'maplibre-gl';
import { LocateFixed } from 'lucide-react';


const homeLat = parseFloat(import.meta.env.VITE_HOME_LATITUDE || '28.6611');
const homeLng = parseFloat(import.meta.env.VITE_HOME_LONGITUDE || '-81.3884');
const HOME_COORDS = [homeLng, homeLat]; // Altamonte Springs
const DEFAULT_ZOOM = 10;

export default function MapWidget() {
  const mapContainer = useRef(null);
  const map = useRef(null);

  // Recenter Handler
  const handleRecenter = () => {
    if (map.current) {
      map.current.flyTo({
        center: HOME_COORDS,
        zoom: DEFAULT_ZOOM,
        essential: true
      });
    }
  };

  useEffect(() => {
    if (map.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
      center: HOME_COORDS,
      zoom: DEFAULT_ZOOM
    });

    map.current.addControl(new maplibregl.NavigationControl(), 'top-right');

    map.current.on('load', async () => {
      // --- ADD HOME ICON MARKER ---
      const homeEl = document.createElement('div');
      homeEl.className = 'flex items-center justify-center w-7 h-7 bg-blue-600 border-2 border-white rounded-full shadow-lg text-white';
      homeEl.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`;

      new maplibregl.Marker({ element: homeEl })
        .setLngLat(HOME_COORDS)
        .addTo(map.current);

      // --- RAINVIEWER RADAR LAYER ---
      try {
        const rvResponse = await fetch('https://api.rainviewer.com/public/weather-maps.json');
        const rvData = await rvResponse.json();
        const latestPast = rvData.radar.past;
        const latestPath = latestPast[latestPast.length - 1].path;

        map.current.addSource('rainviewer', {
          type: 'raster',
          tiles: [`https://tilecache.rainviewer.com${latestPath}/256/{z}/{x}/{y}/2/1_1.png`],
          tileSize: 256,
          maxzoom: 7
        });

        map.current.addLayer({
          id: 'rainviewer-layer',
          type: 'raster',
          source: 'rainviewer',
          paint: { 'raster-opacity': 0.65 }
        });
      } catch (err) {
        console.error("Failed to load RainViewer radar data:", err);
      }

      // --- TOMORROW.IO LIGHTNING LAYER ---
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

      // --- NWS STORM TRACKS & WARNINGS ---
      const updateNWSAlerts = async () => {
        try {
          const response = await fetch('https://api.weather.gov/alerts/active?area=FL');
          const data = await response.json();
          
          const severeFeatures = data.features?.filter(feature => {
            const event = feature.properties.event;
            const hasGeometry = feature.geometry !== null;
            const isTargetEvent = event === 'Severe Thunderstorm Warning' || 
                                  event === 'Tornado Warning' || 
                                  event === 'Flash Flood Warning' ||
                                  event === 'Special Weather Statement';
            return isTargetEvent && hasGeometry;
          }) || [];

          data.features = severeFeatures;

          if (map.current.getSource('nws-alerts')) {
            map.current.getSource('nws-alerts').setData(data);
          } else {
            map.current.addSource('nws-alerts', { type: 'geojson', data: data });

            map.current.addLayer({
              id: 'nws-alerts-fill',
              type: 'fill',
              source: 'nws-alerts',
              paint: {
                'fill-color': [
                  'match', ['get', 'event'],
                  'Tornado Warning', '#ef4444', 
                  'Severe Thunderstorm Warning', '#eab308', 
                  'Flash Flood Warning', '#22c55e', 
                  'Special Weather Statement', '#94a3b8',
                  '#ffffff'
                ],
                'fill-opacity': 0.2
              }
            });

            map.current.addLayer({
              id: 'nws-alerts-outline',
              type: 'line',
              source: 'nws-alerts',
              paint: {
                'line-color': [
                  'match', ['get', 'event'],
                  'Tornado Warning', '#ef4444',
                  'Severe Thunderstorm Warning', '#eab308',
                  'Flash Flood Warning', '#22c55e',
                  'Special Weather Statement', '#94a3b8',
                  '#ffffff'
                ],
                'line-width': 2,
                'line-dasharray': [2, 2]
              }
            });
          }
        } catch (err) {
          console.error("Failed to load NWS alerts:", err);
        }
      };

      updateNWSAlerts();
      setInterval(updateNWSAlerts, 120000);
    });

    return () => map.current?.remove();
  }, []);

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl p-4 shadow-lg flex flex-col h-full min-h-[450px]">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
          <span>Airspace & Radar</span>
        </h2>
        
        {/* Recenter Map Button */}
        <button
          onClick={handleRecenter}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-[#111827] hover:bg-slate-800 text-slate-300 border border-borderSlate rounded-lg transition-all shadow"
          title="Recenter to Home"
        >
          <LocateFixed className="w-3.5 h-3.5 text-blue-400" />
          <span>Recenter</span>
        </button>
      </div>

      <div ref={mapContainer} className="w-full flex-1 rounded-lg overflow-hidden border border-borderSlate" />
    </div>
  );
}