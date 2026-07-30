import { useState, useEffect } from 'react';
import { Activity, CloudRain, Gamepad2, Tv, Map as MapIcon } from 'lucide-react';
import MapWidget from '@/components/MapWidget';
import MediaWidget from './components/MediaWidget';
import WeatherWidget from './components/WeatherWidget'; 
import AdvancedWeatherWidget from './components/AdvancedWeatherWidget'; 

function App() {
  // Data state variables
  const [weather, setWeather] = useState(null);
  const [flights, setFlights] = useState([]);
  const [error, setError] = useState(null);

  const host = window.location.hostname;
  const WEATHER_URL = `http://${host}:8004/api/weather/current`;
  const FLIGHT_URL = `http://${host}:8003/api/flights/active`;

  // Unit Conversion Helpers
  const toFahrenheit = (c) => c != null ? ((c * 9/5) + 32).toFixed(1) : '--';
  const toMPH = (ms) => ms != null ? (ms * 2.23694).toFixed(1) : '--';
  const toInches = (mm) => mm != null ? (mm / 25.4).toFixed(2) : '0.00';

  // Fetch logic remains exactly the same as your previous working version
  useEffect(() => {
    fetch(WEATHER_URL)
      .then(async res => {
        if (!res.ok) throw new Error(`Weather API: ${res.status}`);
        return res.json();
      })
      .then(data => setWeather(data))
      .catch(err => setError(prev => (prev ? `${prev} | ${err.message}` : err.message)));

    fetch(FLIGHT_URL)
      .then(async res => {
        if (!res.ok) throw new Error(`Flight API: ${res.status}`);
        return res.json();
      })
      .then(data => setFlights(data))
      .catch(err => setError(prev => (prev ? `${prev} | ${err.message}` : err.message)));
  }, [WEATHER_URL, FLIGHT_URL]);

  return (
    <div className="min-h-screen bg-[#0b0f19] text-slate-100 p-4 md:p-6">
      
      {/* Header */}
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Maverick Dashboard</h1>
        {error && (
          <div className="bg-slate-800 border-l-4 border-accentPurple text-slate-100 p-2 text-sm rounded shadow-md">
            {error}
          </div>
        )}
      </header>

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 2xl:grid-cols-12 gap-6">
        
        {/* CENTER COLUMN: Map & Flights (Shifts to Right on Tablet) */}
        <div className="lg:col-span-7 xl:col-span-8 2xl:col-span-6 order-1 lg:order-2 flex flex-col gap-6">
          <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg flex-1 min-h-[450px] lg:min-h-[600px] flex flex-col overflow-hidden">
            <div className="bg-[#161f33] p-4 border-b border-borderSlate flex items-center gap-2">
              <MapIcon className="text-accentBlue w-5 h-5" />
              <h2 className="text-lg font-semibold text-textSilver">Airspace & Radar</h2>
            </div>
            
            {/* MapLibre Base Map */}
            <div className="flex-1 relative">
              <MapWidget />
            </div>
          </div>
        </div>

        {/* LEFT COLUMN: Weather & Health (Shifts to Left on Tablet) */}
        <div className="lg:col-span-5 xl:col-span-4 2xl:col-span-3 order-2 lg:order-1 flex flex-col gap-6">
          
          {/* Weather Widget */}
          <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg p-5">
            <WeatherWidget/>
            <AdvancedWeatherWidget/>
          </div>

          {/* System Health Widget */}
          <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg p-5">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="text-accentBlue w-5 h-5" />
              <h2 className="text-lg font-semibold text-textSilver">Infrastructure</h2>
            </div>
            {/* Hardcoded placeholders for the green/red bubbles until the Uptime Kuma API bridge is built */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Weather API</span>
                <span className="flex h-3 w-3 rounded-full bg-green-500"></span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Flight API</span>
                <span className="flex h-3 w-3 rounded-full bg-green-500"></span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-400">Netdata Core</span>
                <span className="flex h-3 w-3 rounded-full bg-green-500"></span>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Media & Tasks (Drops to Row 2 on Tablet) */}
        {/* Added 2xl constraints to bring it back to a third column on desktop */}
        <div className="lg:col-span-12 2xl:col-span-3 order-3 flex flex-col gap-6">
          
          <MediaWidget />
          
        </div>

      </div>
    </div>
  );
}

export default App;