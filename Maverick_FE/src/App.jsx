import { useState, useEffect } from 'react';
import { Activity, CloudRain, Gamepad2, Tv, Map as MapIcon } from 'lucide-react';
import MapWidget from '@/components/MapWidget';
import MediaWidget from './components/MediaWidget';
import WeatherWidget from './components/WeatherWidget'; 
import AdvancedWeatherWidget from './components/AdvancedWeatherWidget'; 
import InfrastructureWidget from './components/InfrastructureWidget';
import AircraftTable from './components/AircraftTable';

function App() {
  // Data state variables
  const [weather, setWeather] = useState(null);
  const [error, setError] = useState(null);

  const host = window.location.hostname;
  const WEATHER_URL = `http://${host}:8004/api/weather/current`;

  // Unit Conversion Helpers (Note: These might also be dead code if handled inside your Weather widgets now!)
  const toFahrenheit = (c) => c != null ? ((c * 9/5) + 32).toFixed(1) : '--';
  const toMPH = (ms) => ms != null ? (ms * 2.23694).toFixed(1) : '--';
  const toInches = (mm) => mm != null ? (mm / 25.4).toFixed(2) : '0.00';

  useEffect(() => {
    fetch(WEATHER_URL)
      .then(async res => {
        if (!res.ok) throw new Error(`Weather API: ${res.status}`);
        return res.json();
      })
      .then(data => setWeather(data))
      .catch(err => setError(prev => (prev ? `${prev} | ${err.message}` : err.message)));
  }, [WEATHER_URL]);

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
          <MapWidget />
        </div>

        {/* LEFT COLUMN: Weather & Health (Shifts to Left on Tablet) */}
        <div className="lg:col-span-5 xl:col-span-4 2xl:col-span-3 order-2 lg:order-1 flex flex-col gap-6">
          
          {/* Weather Widget */}
          <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg p-5">
            <WeatherWidget/>
            <AdvancedWeatherWidget/>
          </div>

          {/* System Health Widget */}
          <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg p-5 flex flex-col min-h-[300px]">
            <InfrastructureWidget />
          </div>
        </div>

        {/* RIGHT COLUMN: Media & Tasks (Drops to Row 2 on Tablet) */}
        {/* Added 2xl constraints to bring it back to a third column on desktop */}
        <div className="lg:col-span-12 2xl:col-span-3 order-3 flex flex-col gap-6">
          
          <MediaWidget />
          
        </div>

      </div>
      {/* NEW: Phase 2 Aircraft Table */}
      <div className="mt-6 w-full">
        <AircraftTable />
      </div>
    </div>
  );
}

export default App;