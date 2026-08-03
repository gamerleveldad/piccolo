import React from 'react';
import WeatherIcon from './WeatherIcon';

export default function TemperatureWidget({ weather, comfort, pressureDiag }) {
  if (!weather) return null;

  const minT = 0; const maxT = 120;
  const airTemp = parseFloat(weather.temperature_f) || 70.0;
  const feelsTemp = parseFloat(weather.feels_like_f) || 70.0;
  
  // Calculate visual offsets for the temperature gauge
  const airPct = Math.min(Math.max(((airTemp - minT) / (maxT - minT)) * 100, 0), 100);
  const feelsPct = Math.min(Math.max(((feelsTemp - minT) / (maxT - minT)) * 100, 0), 100);
  const tempDelta = Math.abs(airTemp - feelsTemp);
  const isHeatIndex = feelsTemp > airTemp;
  
  const overlayColor = isHeatIndex ? 'bg-red-500/20' : 'bg-blue-500/20';
  const pulseClass = tempDelta >= 2.0 ? 'animate-pulse' : '';
  const feelsColorClass = isHeatIndex ? 'text-rose-500' : 'text-cyan-400';
  
  // Pressure Math for Vertical Gauge
  const minP = 28.5; const maxP = 30.5;
  const pVal = parseFloat(weather.pressure_inhg) || 29.92;
  const pPct = Math.min(Math.max(((pVal - minP) / (maxP - minP)) * 100, 0), 100);

  const activeIconKey = weather.icon_api || 'clear-day';
  const currentAsset = `/assets/weather/${activeIconKey}.gif`;

  return (
    <div className="col-span-2 bg-slate-950 border border-blue-950/40 p-4 rounded-2xl flex flex-col justify-between shadow-2xl relative overflow-hidden">
      <div className="grid grid-cols-12 gap-2 items-center">
        
        {/* Text Metrics */}
        <div className="col-span-4 flex flex-col justify-center gap-2 text-left pl-1">
          <div>
            <span className="text-[9px] font-bold uppercase tracking-widest text-slate-500 block">Air Temp</span>
            <div className="flex items-baseline gap-0.5">
              <span className="text-2xl font-black font-mono tracking-tighter text-slate-100">{airTemp.toFixed(1)}</span>
              <span className="text-xs font-bold text-slate-400">°F</span>
            </div>
          </div>
          <div>
            <span className="text-[9px] font-bold uppercase tracking-widest text-slate-500 block">Feels Like</span>
            <div className="flex items-baseline gap-0.5">
              <span className={`text-2xl font-black font-mono tracking-tighter ${feelsColorClass}`}>{feelsTemp.toFixed(1)}</span>
              <span className="text-xs font-bold text-slate-400">°F</span>
            </div>
          </div>
        </div>

        {/* Temperature Gauge */}
        <div className="col-span-2 flex justify-center items-center h-28 relative">
          <div className="w-5 h-full rounded-full bg-gradient-to-t from-blue-600 via-emerald-500 via-amber-500 to-red-600 relative border border-slate-800 shadow-[0_0_8px_rgba(0,0,0,0.5)]">
            {tempDelta > 0 && (
              <div 
                style={{ bottom: `${Math.min(airPct, feelsPct)}%`, height: `${tempDelta}%` }}
                className={`absolute left-0 right-0 w-full rounded-sm transition-all duration-1000 ease-out ${overlayColor} ${pulseClass}`}
              />
            )}
            <div style={{ bottom: `${airPct}%` }} className="absolute left-1/2 -translate-x-1/2 mb-[-1px] w-6 h-0.5 bg-white rounded-full shadow-[0_0_4px_white] border border-black/40 transition-all duration-1000 z-20" />
            <div style={{ bottom: `${feelsPct}%` }} className={`absolute left-1/2 -translate-x-1/2 mb-[-1px] w-6 h-0.5 rounded-full shadow-lg border border-black/40 transition-all duration-1000 z-10 ${isHeatIndex ? 'bg-red-500' : 'bg-blue-400'}`} />
          </div>
        </div>

        {/* Pressure Gauge */}
        <div className="col-span-2 flex flex-col justify-center items-center h-28 relative gap-1">
          <div className="w-1.5 h-full rounded-full bg-gradient-to-t from-rose-900/60 via-amber-900/60 via-slate-700/60 to-cyan-900/60 relative border border-slate-900/80 shadow-inner flex items-center">
            {[28.94, 29.23, 29.53, 29.71, 29.80, 30.20].map((val, idx) => {
              const tickPct = Math.min(Math.max(((val - 28.5) / (30.5 - 28.5)) * 100, 0), 100);
              return (
                <div 
                  key={idx}
                  style={{ bottom: `${tickPct}%` }}
                  className="absolute -left-[2px] w-2.5 h-[1.5px] bg-slate-950 z-10"
                  title={`${val} inHg`}
                />
              );
            })}
            <div style={{ bottom: `${pPct}%` }} className="absolute left-1/2 -translate-x-1/2 mb-[-2px] w-2.5 h-1.5 bg-white rounded-full shadow-[0_0_4px_black] border border-slate-900 transition-all duration-1000 z-20" />
          </div>
        </div>
        
        {/* GIF Icon Container */}
        <div className="col-span-4 flex flex-col items-center justify-center relative pr-1">
          <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-full bg-slate-950 relative overflow-hidden flex items-center justify-center border border-slate-900/40 shadow-xl">
            <img 
              src={currentAsset} 
              alt="Condition" 
              className="w-full h-full object-cover opacity-90 select-none pointer-events-none"
              style={{ WebkitMaskImage: 'radial-gradient(circle, rgba(0,0,0,1) 60%, rgba(0,0,0,0) 100%)' }}
              onError={(e) => { e.target.src = '/assets/weather/clear-day.gif'; }}
            />
            <div className="absolute inset-0 w-full h-full rounded-full shadow-[inset_0_0_10px_rgba(2,6,23,0.9)]" />
          </div>
          <div className="flex flex-col items-center justify-center mt-1.5 w-full px-1">
            <div className="flex items-center justify-center gap-1 w-full">
              <WeatherIcon icon={activeIconKey} className="w-4 h-4 shrink-0" />
              <span className="text-[9px] font-black uppercase tracking-wider text-slate-300 text-center leading-tight break-words" style={{ textWrap: 'balance' }}>
                {weather.conditions || 'Steady'}
              </span>
            </div>
          </div>
        </div>

      </div>

      <div className="mt-2 pt-2 border-t border-slate-900 text-[11px] font-semibold uppercase tracking-wider text-slate-500 flex justify-between items-center">
        <div>Comfort: <span className={`font-bold ml-1 ${comfort?.color}`}>{comfort?.text}</span></div>
        <div className="text-[10px] font-mono text-slate-400">
          <span className={pressureDiag?.tierColor}>{parseFloat(weather.pressure_inhg).toFixed(2)} inHg</span> ({weather.pressure_trend_api})
        </div>
      </div>
    </div>
  );
}