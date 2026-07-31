import { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

// Using your specific coordinates another change
const HOME_COORDS = [-81.3884, 28.6611];

export default function MapWidget() {
  const mapContainer = useRef(null);
  const map = useRef(null);

  useEffect(() => {
    // 1. Initialize Map
    if (map.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      center: HOME_COORDS,
      zoom: 8, // Zoomed out slightly to ensure we capture planes in the wider area
      style: {
        version: 8,
        sources: {
          'carto-dark': {
            type: 'raster',
            tiles: [
              'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
              'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'
            ],
            tileSize: 256
          }
        },
        layers: [{ id: 'carto-dark-layer', type: 'raster', source: 'carto-dark' }]
      }
    });

    let flightInterval;

    map.current.on('load', () => {
      console.log("MAP DIAGNOSTIC: Canvas loaded successfully.");

      // 2. Add Empty Data Source
      map.current.addSource('flights', { 
        type: 'geojson', 
        data: { type: 'FeatureCollection', features: [] } 
      });
      
      // 3. Add Simple Red Dot Layer (No fonts, no images, no complexity)
      map.current.addLayer({
        id: 'flights-dots', 
        type: 'circle', 
        source: 'flights',
        paint: { 
          'circle-color': '#ff0000', // Bright Red
          'circle-radius': 6, 
          'circle-stroke-width': 2, 
          'circle-stroke-color': '#ffffff' 
        }
      });

      // 4. Polling Function
      const updateFlights = async () => {
        try {
          // Hardcoded to your exact Docker host IP
          const res = await fetch(`http://192.168.4.55:8085/data/aircraft.json`);
          if (!res.ok) {
            console.error("MAP DIAGNOSTIC: Fetch failed with status", res.status);
            return;
          }
          
          const data = await res.json();
          const pointFeatures = [];

          // Parse valid coordinates
          data.aircraft.forEach(ac => {
            if (ac.lat != null && ac.lon != null) {
              pointFeatures.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [ac.lon, ac.lat] },
                properties: { flight: ac.flight || ac.hex }
              });
            }
          });

          console.log(`MAP DIAGNOSTIC: Parsed ${pointFeatures.length} valid aircraft.`);

          // Inject into map
          if (map.current && map.current.getSource('flights')) {
            map.current.getSource('flights').setData({ 
              type: 'FeatureCollection', 
              features: pointFeatures 
            });
            console.log("MAP DIAGNOSTIC: MapLibre source updated.");
          }
        } catch (err) {
          console.error("MAP DIAGNOSTIC: Polling error:", err);
        }
      };

      // Run once, then loop every 2 seconds
      updateFlights();
      flightInterval = setInterval(updateFlights, 2000);
    });

    // Cleanup
    return () => {
      if (flightInterval) clearInterval(flightInterval);
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg flex-1 min-h-[450px] lg:min-h-[600px] flex flex-col overflow-hidden">
      <div className="bg-[#161f33] p-4 border-b border-borderSlate">
        <h2 className="text-lg font-semibold text-textSilver">Airspace & Radar (Diagnostic Mode)</h2>
      </div>
      <div ref={mapContainer} className="w-full flex-1 relative bg-[#0b0f19]" />
    </div>
  );
}