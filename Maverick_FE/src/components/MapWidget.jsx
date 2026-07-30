import { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

const homeLat = parseFloat(import.meta.env.VITE_HOME_LATITUDE || '28.6611');
const homeLng = parseFloat(import.meta.env.VITE_HOME_LONGITUDE || '-81.3884');

const DEFAULT_CENTER = [homeLng, homeLat];
// Zoomed out to 10.  To see the entire state of FL by default set to 6.5
const DEFAULT_ZOOM = 10; 

export default function MapWidget() {
  const mapContainer = useRef(null);
  const map = useRef(null);

  useEffect(() => {
    if (map.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          'carto-dark': {
            type: 'raster',
            tiles: [
              'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
              'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
              'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
              'https://d.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'
            ],
            tileSize: 256,
          }
        },
        layers: [
          {
            id: 'carto-dark-layer',
            type: 'raster',
            source: 'carto-dark',
            minzoom: 0,
            maxzoom: 22
          }
        ]
      },
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: false
    });

    map.current.addControl(
      new maplibregl.NavigationControl({ showCompass: true, showZoom: true }),
      'top-right'
    );

    map.current.on('load', async () => {
      try {
        const rvResponse = await fetch('https://api.rainviewer.com/public/weather-maps.json');
        const rvData = await rvResponse.json();
        
        // Extract the new 'path' variable instead of the 'time' variable
        const latestPast = rvData.radar.past;
        const latestPath = latestPast[latestPast.length - 1].path;

        map.current.addSource('rainviewer', {
          type: 'raster',
          // Inject the path hash directly into the tile URL
          tiles: [`https://tilecache.rainviewer.com${latestPath}/256/{z}/{x}/{y}/2/1_1.png`],
          tileSize: 256,
          maxzoom: 7
        });


        map.current.addLayer({
          id: 'rainviewer-layer',
          type: 'raster',
          source: 'rainviewer',
          paint: {
            'raster-opacity': 0.65 
          }
        });

        // --- LIVE NWS STORM TRACKS & WARNINGS ---
        
        // Function to fetch and update NWS alerts
        const updateNWSAlerts = async () => {
          try {
            // Fetch active alerts for Florida
            const response = await fetch('https://api.weather.gov/alerts/active?area=FL');
            const data = await response.json();
            
            // Filter to only show severe convective weather
            const severeFeatures = data.features.filter(feature => {
              const event = feature.properties.event;
              return event === 'Severe Thunderstorm Warning' || 
                     event === 'Tornado Warning' || 
                     event === 'Special Weather Statement' ||
                     event === 'Flash Flood Warning';
            });
            
            data.features = severeFeatures;

            // If the source already exists, just update the data. Otherwise, create it.
            if (map.current.getSource('nws-alerts')) {
              map.current.getSource('nws-alerts').setData(data);
            } else {
              map.current.addSource('nws-alerts', {
                type: 'geojson',
                data: data
              });

              // The translucent fill
              map.current.addLayer({
                id: 'nws-alerts-fill',
                type: 'fill',
                source: 'nws-alerts',
                paint: {
                  'fill-color': [
                    'match',
                    ['get', 'event'],
                    'Tornado Warning', '#ef4444', // Red
                    'Severe Thunderstorm Warning', '#eab308', // Yellow
                    'Flash Flood Warning', '#22c55e', // Green
                    '#ffffff' // Default fallback
                  ],
                  'fill-opacity': 0.2
                }
              });

              // The sharp outline
              map.current.addLayer({
                id: 'nws-alerts-outline',
                type: 'line',
                source: 'nws-alerts',
                paint: {
                  'line-color': [
                    'match',
                    ['get', 'event'],
                    'Tornado Warning', '#ef4444',
                    'Severe Thunderstorm Warning', '#eab308',
                    'Flash Flood Warning', '#22c55e',
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

        // Initial fetch
        updateNWSAlerts();
        
        // Refresh the warnings every 2 minutes
        setInterval(updateNWSAlerts, 120000);
      } catch (err) {
        console.error("Failed to load RainViewer radar data:", err);
      }
    });

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  return (
    <div className="w-full h-full min-h-[400px] lg:min-h-[500px] relative rounded-b-xl overflow-hidden">
      <div ref={mapContainer} className="absolute inset-0 w-full h-full" />
    </div>
  );
}