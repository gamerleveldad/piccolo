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