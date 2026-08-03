import React, { useState, useEffect } from 'react';
import HeaderBar from './components/HeaderBar';
import TemperatureWidget from './components/TemperatureWidget';
import ActivityGridWidget from './components/ActivityGridWidget';
import RainGaugeWidget from './components/RainGaugeWidget';
import LightningRadarWidget from './components/LightningRadarWidget';
import ForecastStripWidget from './components/ForecastStripWidget';
import CalendarWidget from './components/CalendarWidget';
import TasksWidget from './components/TasksWidget';
import SleeperWidget from './components/SleeperWidget';
import AnimeWidget from './components/AnimeWidget';
import GooglePhotosWidget from './components/GooglePhotosWidget';

function App() {
  const [dashboardState, setDashboardState] = useState(null);
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);

  const backendHost = import.meta.env.VITE_BACKEND_HOST || window.location.hostname;
  const backendPort = import.meta.env.VITE_BACKEND_PORT || '8000';
  const apiBase = `http://${backendHost}:${backendPort}`;

  const fetchState = async () => {
    try {
      const res = await fetch(`${apiBase}/api/dashboard/state`);
      if (res.ok) {
        const data = await res.json();
        if (data.error) {
          console.error("Backend error payload:", data.error);
          return; 
        }

        // --- SCHEMA MAPPING: Bridge the new weather_api keys to legacy widget keys ---
        if (data.weather) {
           data.weather.temperature_f = data.weather.temp_f;
           data.weather.feels_like_f = data.weather.feels_like_f;
           data.weather.pressure_inhg = data.weather.sea_level_pressure_inhg;
           data.weather.icon_api = data.weather.icon;
           data.weather.rain_accumulation_day_in = data.weather.precip_in;
           data.weather.humidity_pct = data.weather.relative_humidity;
           data.weather.wind_speed_mph = data.weather.wind_avg_mph;
           data.weather.wind_gust_mph = data.weather.wind_gust_mph;
        }

        if (data.forecast_daily && data.forecast_daily.length > 0) {
           // Populate the current rain chance from today's daily forecast
           if (data.weather) {
              data.weather.rain_chance_current = data.forecast_daily[0].precip_probability;
           }

           // Map the daily forecast array
           data.forecast_daily = data.forecast_daily.map(d => ({
              ...d,
              high: d.temp_max_f,
              low: d.temp_min_f,
              rain_pct: d.precip_probability
           }));
        }

        setDashboardState(data);
      }
    } catch (err) {
      console.error("Failed fetching dashboard state:", err);
    }
  };
  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 30000);
    let ws;
    const connectWs = () => {
      ws = new WebSocket(`ws://${backendHost}:${backendPort}/ws`);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        setTimeout(connectWs, 3000);
      };
      ws.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.update_type === 'calendar_sync') {
          setEvents(msg.events);
        }
      };
    };
    connectWs();
    return () => {
      clearInterval(interval);
      if (ws) ws.close();
    };
  }, []);

  if (!dashboardState) {
    return (
      <div className="min-h-screen bg-black text-slate-400 flex items-center justify-center font-mono">
        Connecting to Tactical Dashboard Hub...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-slate-100 p-4 font-sans tracking-tight overflow-hidden select-none">
      <HeaderBar connected={connected} dailyVerse={dashboardState.daily_verse} />

      <div className="grid grid-cols-12 gap-3 h-[calc(100vh-85px)] items-stretch">
        
        <div className="col-span-2 flex flex-col h-full max-w-[100px]">
          <ForecastStripWidget dailyForecast={dashboardState.forecast_daily} />
        </div>

        <div className="col-span-6 flex flex-col gap-3 overflow-y-auto pr-0.5 max-h-full content-start no-scrollbar">
          <div className="grid grid-cols-2 gap-3">
            <TemperatureWidget weather={dashboardState.weather} comfort={dashboardState.comfort} pressureDiag={dashboardState.pressure_diag} />
            <ActivityGridWidget activities={dashboardState.activities} weather={dashboardState.weather} dailyForecast={dashboardState.forecast_daily} />
            <RainGaugeWidget weather={dashboardState.weather} rainStatus={dashboardState.rain_status} />
            <LightningRadarWidget 
              weather={dashboardState.weather} 
              shows={dashboardState.anime_progress}
              flights={dashboardState.active_flights}
            />
          </div>

          <div className="col-span-2 mt-1 h-full min-h-[160px]">
            <GooglePhotosWidget apiBase={apiBase} />
          </div>
        </div>

        <div className="col-span-4 flex flex-col gap-3 h-full min-h-0">
          <div className="flex-[2] min-h-0 relative">
            <CalendarWidget events={events} />
          </div>
          <div className="flex flex-col gap-3 shrink-0 h-[28%] min-h-[160px]">
            <div className="flex-1 h-full relative">
              <TasksWidget apiBase={apiBase} />
            </div>
            <div className="flex-1 h-full relative">
              <SleeperWidget apiBase={apiBase} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;