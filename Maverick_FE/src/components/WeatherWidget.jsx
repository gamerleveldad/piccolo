import { useState, useEffect } from 'react';
import { Wind, Droplets, CloudRain, Zap, TriangleAlert, Info } from 'lucide-react';
import '../public/assets/weather/weather-icons/css/weather-icons.min.css';

const ICON_MAP = {
  'clear-day': 'wi wi-day-sunny',
  'clear-night': 'wi wi-night-clear',
  'partly-cloudy-day': 'wi wi-day-cloudy',
  'partly-cloudy-night': 'wi wi-night-alt-cloudy',
  'cloudy': 'wi wi-cloudy',
  'possibly-thunderstorm-day': 'wi wi-day-thunderstorm',
  'possibly-thunderstorm-night': 'wi wi-night-alt-thunderstorm',
  'thunderstorm': 'wi wi-thunderstorm',
  'rain': 'wi wi-rain',
  'chance-rain': 'wi wi-day-rain',
  'foggy': 'wi wi-fog',
  'windy': 'wi wi-strong-wind'
};

export default function WeatherWidget() {
  const [current, setCurrent] = useState(null);
  const [hourlyForecast, setHourlyForecast] = useState([]);
  const [localAlert, setLocalAlert] = useState(null);
  const [loading, setLoading] = useState(true);

  const host = window.location.hostname;
  const CURRENT_URL = `http://${host}:8004/api/weather/current`;
  const HOURLY_URL = `http://${host}:8004/api/weather/forecast/hourly`;
  
  // NWS Point query for Altamonte Springs
  const NWS_ALERTS_URL = `https://api.weather.gov/alerts/active?point=28.6611,-81.3884`;

  const fetchWeatherData = async () => {
    try {
      // 1. Fetch Current Telemetry
      const curRes = await fetch(CURRENT_URL);
      if (curRes.ok) setCurrent(await curRes.json());

      // 2. Fetch Hourly Forecast
      const hourRes = await fetch(HOURLY_URL);
      if (hourRes.ok) {
        const data = await hourRes.json();
        const parsedHours = data.slice(0, 6).map((item) => ({
          time: new Date(item.time).toLocaleTimeString([], { hour: 'numeric', hour12: true }),
          temp: Math.round(item.temp_f),
          condition: item.conditions,
          pop: item.precip_probability ?? 0,
          iconClass: ICON_MAP[item.icon] || 'wi wi-day-sunny'
        }));
        setHourlyForecast(parsedHours);
      }

      // 3. Fetch NWS Check Engine Light
      const alertsRes = await fetch(NWS_ALERTS_URL);
      if (alertsRes.ok) {
        const alertData = await alertsRes.json();
        if (alertData.features && alertData.features.length > 0) {
          // Grab the most severe alert
          const activeEvent = alertData.features[0].properties.event;
          const isWarning = activeEvent.toLowerCase().includes('warning');
          setLocalAlert({ event: activeEvent, isWarning });
        } else {
          setLocalAlert(null);
        }
      }
    } catch (err) {
      console.error('Failed to fetch weather data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWeatherData();
    const interval = setInterval(fetchWeatherData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading || !current) {
    return <div className="bg-cardBg border border-borderSlate rounded-xl p-5 animate-pulse text-slate-500">Loading weather telemetry...</div>;
  }

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl p-5 shadow-lg flex flex-col gap-6 relative overflow-hidden">
      
      {/* CHECK ENGINE LIGHT BANNER */}
      {localAlert && (
        <div className={`absolute top-0 left-0 w-full p-2 flex items-center justify-center gap-2 text-sm font-bold shadow-md
          ${localAlert.isWarning ? 'bg-red-600/90 text-white animate-pulse' : 'bg-yellow-500/90 text-slate-900'}
        `}>
          {localAlert.isWarning ? <TriangleAlert className="w-4 h-4" /> : <Info className="w-4 h-4" />}
          {localAlert.event.toUpperCase()}
        </div>
      )}

      {/* Push content down if banner is active */}
      <div className={localAlert ? 'mt-6' : ''}>
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-sm font-medium text-slate-400">Local Telemetry</h2>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-4xl font-bold text-slate-100">{Math.round(current.temp_f)}°F</span>
              <span className="text-xs text-slate-400">
                Feels like {Math.round(current.feels_like_f)}°F
              </span>
            </div>
          </div>
          <div className="text-right flex flex-col items-end gap-1">
            <span className="text-xs px-2 py-1 bg-slate-800 text-slate-300 rounded-md border border-slate-700">
              Live (30s)
            </span>
          </div>
        </div>

        {/* Telemetry Grid (Updated to new API keys) */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <Droplets className="w-4 h-4 text-blue-400 shrink-0" />
            <div>
              <p className="text-slate-500">Humidity / Dew</p>
              <p className="font-semibold text-slate-200">
                {current.relative_humidity}% / {Math.round(current.dew_point_f)}°F
              </p>
            </div>
          </div>

          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <Wind className="w-4 h-4 text-slate-400 shrink-0" />
            <div>
              <p className="text-slate-500">Wind / Gust</p>
              <p className="font-semibold text-slate-200">
                {current.wind_avg_mph} <span className="text-slate-400">({current.wind_gust_mph})</span> mph
              </p>
            </div>
          </div>

          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <CloudRain className="w-4 h-4 text-cyan-400 shrink-0" />
            <div>
              <p className="text-slate-500">Rain Rate</p>
              <p className="font-semibold text-slate-200">{current.precip_in.toFixed(2)} in/hr</p>
            </div>
          </div>

          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <Zap className={`w-4 h-4 shrink-0 ${current.lightning_strike_count > 0 ? 'text-yellow-400 animate-pulse' : 'text-slate-600'}`} />
            <div>
              <p className="text-slate-500">Lightning (1h)</p>
              <p className="font-semibold text-slate-200">
                {current.lightning_strike_count > 0 ? `${current.lightning_strike_count} strikes` : 'None'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* --- 6-HOUR HOURLY FORECAST BAR --- */}
      <div className="border-t border-borderSlate pt-4">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">6-Hour Outlook</h3>
        <div className="grid grid-cols-6 gap-2 text-center">
          {hourlyForecast.map((hour, idx) => (
            <div key={idx} className="bg-[#111827] p-2 rounded-lg border border-borderSlate flex flex-col items-center justify-between">
              <span className="text-[11px] text-slate-400">{hour.time}</span>
              <i className={`${hour.iconClass} text-xl my-2 text-amber-400`} />
              <span className="text-sm font-bold text-slate-100">{hour.temp}°</span>
              <div className="text-[10px] text-cyan-400 font-medium mt-1">
                {hour.pop > 0 ? `${hour.pop}%` : '0%'}
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}