import React, { useState } from 'react';

const iconMapping = {
  'Airbrushing': 'airbrush.svg',
  'Swimming': 'swimming.svg',
  'Yard Work': 'yard_work.svg',
  'Basketball': 'basketball.svg',
  'Football': 'football.svg',
  'Walking': 'walking.svg',
  'Video Games': 'video_game.svg',
  'Driving': 'driving.svg'
};

const getGradientClass = (score) => {
  const val = parseFloat(score) || 0;
  if (val >= 7.5) return "from-emerald-600 to-teal-950 border-emerald-500/40";
  if (val >= 4.5) return "from-amber-500 to-orange-950 border-amber-500/30";
  return "from-rose-700 to-slate-950 border-rose-600/30";
};

const getStatusGradient = (status) => {
  if (status === 'optimal') return "bg-gradient-to-r from-emerald-600 to-emerald-900 text-emerald-100 border-emerald-500/50 shadow-inner";
  if (status === 'warning') return "bg-gradient-to-r from-amber-500 to-amber-700 text-amber-50 border-amber-500/50 shadow-inner";
  return "bg-gradient-to-r from-rose-600 to-red-900 text-rose-100 border-rose-500/50 shadow-[0_0_8px_rgba(225,29,72,0.6)]";
};

function ActivityCard({ act, weather, dailyForecast }) {
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState('current');

  const fileName = iconMapping[act.name] || 'default.svg';
  const iconPath = `/assets/activities/${fileName}`;

  const generateDiagnostics = () => {
    const isFc = mode === 'forecast';
    const curTemp = parseFloat(weather?.temperature_f) || 72;
    const curFeels = parseFloat(weather?.feels_like_f) || curTemp;
    const curWind = parseFloat(weather?.wind_speed_mph) || 0;
    const curHum = parseFloat(weather?.humidity_pct) || 50;
    const rainAccum = parseFloat(weather?.rain_accumulation_day_in) || 0.0;
    const fcDay = (dailyForecast && dailyForecast.length > 0) ? dailyForecast[0] : {};
    const fcTemp = (parseFloat(fcDay.high || curTemp) + parseFloat(fcDay.low || curTemp)) / 2;
    const fcRainPct = parseInt(fcDay.rain_pct) || 0;
    
    const temp = isFc ? fcTemp : curTemp;
    const wind = curWind; 
    const hum = curHum; 
    const minsSinceStrike = weather?.last_strike_time ? Math.floor((Date.now() - weather.last_strike_time) / 60000) : 999;
    const lightningDist = weather?.last_strike_distance !== null ? parseFloat(weather.last_strike_distance) : 999;

    let metrics = {};
    const add = (label, val, status) => { metrics[label] = { value: val, status }; };

    switch (act.name) {
      case 'Airbrushing':
        add("Temperature", `${temp.toFixed(1)}°F`, temp < 60 || temp > 75 ? "critical" : temp < 64 || temp > 72 ? "warning" : "optimal");
        add("Humidity", `${hum.toFixed(0)}%`, hum > 75 ? "critical" : hum > 65 ? "warning" : "optimal");
        add("Wind speed", `${wind.toFixed(1)} mph`, wind > 8 ? "critical" : wind > 5 ? "warning" : "optimal");
        break;
      case 'Swimming':
        add("Temperature", `${temp.toFixed(1)}°F`, temp < 70 ? "critical" : temp < 75 ? "warning" : "optimal");
        if (lightningDist <= 30) add("Lightning", `${lightningDist} mi`, "critical");
        break;
      case 'Yard Work':
        add("Temperature", `${temp.toFixed(1)}°F`, temp > 90 ? "critical" : temp > 78 || temp < 58 ? "warning" : "optimal");
        add("Wind speed", `${wind.toFixed(1)} mph`, wind > 25 ? "critical" : wind > 18 ? "warning" : "optimal");
        add("Recent Rainfall", `${rainAccum.toFixed(2)} in`, rainAccum > 0.15 ? "critical" : rainAccum > 0 ? "warning" : "optimal");
        break;
      case 'Basketball':
      case 'Football':
        add("Temperature", `${temp.toFixed(1)}°F`, temp > 93 || temp < 55 ? "critical" : temp > 85 || temp < 62 ? "warning" : "optimal");
        add("Wind speed", `${wind.toFixed(1)} mph`, wind > 15 ? "critical" : wind > 10 ? "warning" : "optimal");
        add("Field Conditions", `${rainAccum.toFixed(2)} in`, rainAccum > 0.3 ? "critical" : rainAccum > 0.1 ? "warning" : "optimal");
        break;
      case 'Walking':
        add("Temperature", `${temp.toFixed(1)}°F`, temp > 85 || temp < 50 ? "critical" : temp > 80 || temp < 60 ? "warning" : "optimal");
        add("Humidity", `${hum.toFixed(0)}%`, hum > 85 ? "critical" : hum > 75 ? "warning" : "optimal");
        add("Wind speed", `${wind.toFixed(1)} mph`, wind > 22 ? "critical" : wind > 15 ? "warning" : "optimal");
        break;
      case 'Video Games':
        add("Temperature", `${temp.toFixed(1)}°F`, temp > 90 || temp < 40 ? "optimal" : "warning");
        add("Feels Like", `${curFeels.toFixed(1)}°F`, curFeels >= 95 || curFeels <= 35 ? "optimal" : "warning");
        break;
      case 'Driving':
        add("Rain Impact", `${parseFloat(weather?.rain_rate_in_hr || 0).toFixed(2)} in/hr`, parseFloat(weather?.rain_rate_in_hr || 0) > 0.5 ? "critical" : parseFloat(weather?.rain_rate_in_hr || 0) > 0 ? "warning" : "optimal");
        break;
      default:
        add("Temperature", `${temp.toFixed(1)}°F`, "optimal");
    }
    
    if (isFc) add("Precip Chance", `${fcRainPct}%`, fcRainPct > 40 ? "warning" : "optimal");
    return metrics;
  };

  const activeScore = mode === 'current' ? act.currentScore : act.forecastScore;
  const diagnostics = isOpen ? generateDiagnostics() : {};

  return (
    <>
      <div 
        onClick={() => setIsOpen(true)}
        className={`h-[48px] bg-gradient-to-r ${getGradientClass(act.currentScore)} px-2 flex items-center justify-between cursor-pointer rounded-lg shadow-md hover:brightness-110 active:scale-[0.98] transition-all border`}
      >
        <img src={iconPath} alt={act.name} className="w-7 h-7 drop-shadow-md" />
        <div className="flex flex-col items-end leading-none">
          <span className="text-[14px] font-black text-white drop-shadow">{act.currentScore}</span>
          <div className="w-6 border-t-2 border-white/30 my-[2px]"></div>
          <span className="text-[10px] font-bold text-white/80 drop-shadow">{act.forecastScore}</span>
        </div>
      </div>

      {isOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4" onClick={() => setIsOpen(false)}>
          <div className="bg-slate-950 border border-slate-800 w-full max-w-xs p-4 rounded-2xl font-mono text-slate-200 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center border-b border-slate-900 pb-2 mb-3">
              <div>
                <h4 className="text-xs font-black uppercase tracking-wider text-slate-100 flex items-center gap-1.5">
                  {act.name} 
                  <span className={`text-[8px] px-1.5 py-0.5 rounded border ${mode === 'current' ? 'bg-blue-950/50 text-blue-400 border-blue-900/50' : 'bg-purple-950/50 text-purple-400 border-purple-900/50'}`}>
                    {mode}
                  </span>
                </h4>
              </div>
              <button onClick={() => setIsOpen(false)} className="text-slate-500 hover:text-slate-300 text-sm p-1">✕</button>
            </div>
            <div className="space-y-2">
              <div className="bg-slate-900/20 border border-slate-900 p-2 rounded-lg flex justify-between items-center">
                <span className="text-[10px] font-bold text-slate-400">Index Score:</span>
                <span className="text-sm font-black text-slate-200">{activeScore} / 10</span>
              </div>
              {Object.entries(diagnostics).map(([metric, detail]) => (
                <div key={metric} className="bg-slate-900/40 border border-slate-900/60 rounded-xl px-3 py-1.5 flex justify-between items-center">
                  <span className="text-[10px] font-medium text-slate-400">{metric}</span>
                  <span className={`text-[10px] font-black px-2 py-0.5 rounded border ${getStatusGradient(detail.status)}`}>{detail.value}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button onClick={() => setMode('current')} className={`py-1.5 font-bold text-[10px] rounded-lg border uppercase ${mode === 'current' ? 'bg-blue-950/40 text-blue-400 border-blue-900/50' : 'bg-slate-900 text-slate-500 border-slate-800'}`}>Current</button>
              <button onClick={() => setMode('forecast')} className={`py-1.5 font-bold text-[10px] rounded-lg border uppercase ${mode === 'forecast' ? 'bg-purple-950/40 text-purple-400 border-purple-900/50' : 'bg-slate-900 text-slate-500 border-slate-800'}`}>Forecast</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default function ActivityGridWidget({ activities, weather, dailyForecast }) {
  if (!activities) return null;
  return (
    <div className="col-span-2 bg-slate-950 border border-purple-950/40 p-3 rounded-2xl shadow-2xl flex flex-col justify-between">
      <div className="grid grid-cols-4 gap-2 overflow-y-auto max-h-[160px] custom-scrollbar">
        {activities.map((act) => (
          <ActivityCard key={act.name} act={act} weather={weather} dailyForecast={dailyForecast} />
        ))}
      </div>
      <div className="flex justify-between border-t border-slate-900 pt-2 mt-2 text-[8px] font-semibold uppercase font-mono text-slate-600">
        <span>Activity Planner</span>
        <span>Matrix v3.1</span>
      </div>
    </div>
  );
}