import { useState, useEffect } from 'react';
import { Thermometer, Wind, Droplets, CloudRain, Zap } from 'lucide-react';

// Map WeatherFlow API icon strings to Erik Flowers Weather Icons CSS classes
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
  const [loading, setLoading] = useState(true);

  const host = window.location.hostname;
  const CURRENT_URL = `http://${host}:8004/api/weather/current`;
  const HOURLY_URL = `http://${host}:8004/api/weather/forecast/hourly`;

  // Helper conversions for current live telemetry
  const toF = (c) => (c != null ? Math.round((c * 9) / 5 + 32) : '--');
  const toMph = (ms) => (ms != null ? (ms * 2.23694).toFixed(1) : '--');
  const toInches = (mm) => (mm != null ? (mm / 25.4).toFixed(2) : '0.00');
  const toMiles = (km) => (km != null ? Math.round(km * 0.621371) : '--');

  const fetchWeatherData = async () => {
    try {
      // 1. Fetch Live Current Telemetry
      const curRes = await fetch(CURRENT_URL);
      if (curRes.ok) {
        const curData = await curRes.json();
        setCurrent(curData);
      }

      // 2. Fetch Hourly Forecast (using new simplified schema)
      const hourRes = await fetch(HOURLY_URL);
      if (hourRes.ok) {
        const data = await hourRes.json();

        // Process directly without complex grouping loops
        const parsedHours = data.slice(0, 6).map((item) => ({
          time: new Date(item.time).toLocaleTimeString([], { hour: 'numeric', hour12: true }),
          temp: Math.round(item.temp_f),
          condition: item.conditions,
          pop: item.precip_probability ?? 0,
          iconClass: ICON_MAP[item.icon] || 'wi wi-day-sunny'
        }));

        setHourlyForecast(parsedHours);
      }
    } catch (err) {
      console.error('Failed to fetch weather data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWeatherData();

    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchWeatherData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading || !current) {
    return (
      <div className="bg-cardBg border border-borderSlate rounded-xl p-5 animate-pulse text-slate-500">
        Loading weather telemetry...
      </div>
    );
  }

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl p-5 shadow-lg flex flex-col gap-6">
      
      {/* --- LIVE CURRENT CONDITIONS --- */}
      <div>
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-sm font-medium text-slate-400">Local Telemetry</h2>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-4xl font-bold text-slate-100">{toF(current.air_temperature)}°F</span>
              <span className="text-xs text-slate-400">
                Feels like {toF(current.feels_like || current.heat_index)}°F
              </span>
            </div>
          </div>
          <div className="text-right flex flex-col items-end gap-1">
            <span className="text-xs px-2 py-1 bg-slate-800 text-slate-300 rounded-md border border-slate-700">
              Live (30s)
            </span>
          </div>
        </div>

        {/* Telemetry Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <Droplets className="w-4 h-4 text-blue-400 shrink-0" />
            <div>
              <p className="text-slate-500">Humidity / Dew</p>
              <p className="font-semibold text-slate-200">
                {current.relative_humidity}% / {toF(current.dew_point)}°F
              </p>
            </div>
          </div>

          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <Wind className="w-4 h-4 text-slate-400 shrink-0" />
            <div>
              <p className="text-slate-500">Wind / Gust</p>
              <p className="font-semibold text-slate-200">
                {toMph(current.wind_avg)} <span className="text-slate-400">({toMph(current.wind_gust)})</span> mph
              </p>
            </div>
          </div>

          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <CloudRain className="w-4 h-4 text-cyan-400 shrink-0" />
            <div>
              <p className="text-slate-500">Rain Rate</p>
              <p className="font-semibold text-slate-200">{toInches(current.precip_total_1h)} in/hr</p>
            </div>
          </div>

          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <Zap className={`w-4 h-4 shrink-0 ${current.strike_count_1h > 0 ? 'text-yellow-400 animate-pulse' : 'text-slate-600'}`} />
            <div>
              <p className="text-slate-500">Lightning (1h)</p>
              <p className="font-semibold text-slate-200">
                {current.strike_count_1h > 0 ? `${current.strike_count_1h} strikes (${toMiles(current.strike_last_dist)} mi)` : 'None'}
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
              
              {/* Weather Icon Render */}
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