import React, { useState, useEffect } from 'react';

const getWindColor = (mph) => {
  if (mph < 12) return 'text-emerald-400';
  if (mph < 25) return 'text-amber-400';
  return 'text-rose-500 animate-pulse drop-shadow-[0_0_8px_rgba(225,29,72,0.6)]';
};

export default function LightningRadarWidget({ weather }) {
  const [minutesSince, setMinutesSince] = useState(null);
  const [pulseTrigger, setPulseTrigger] = useState(false);

  useEffect(() => {
    if (weather?.lightning_strike_id > 0) {
      setPulseTrigger(true);
      const timer = setTimeout(() => setPulseTrigger(false), 800);
      return () => clearTimeout(timer);
    }
  }, [weather?.lightning_strike_id]);

  useEffect(() => {
    const updateTime = () => {
      if (!weather?.last_strike_time) {
        setMinutesSince(null);
        return;
      }
      const elapsedMins = Math.floor((Date.now() - weather.last_strike_time) / 60000);
      setMinutesSince(elapsedMins);
    };

    updateTime();
    const interval = setInterval(updateTime, 10000);
    return () => clearInterval(interval);
  }, [weather?.last_strike_time]);

  if (!weather) return null;

  const activeStorm = minutesSince !== null && minutesSince <= 30;
  const recentCloseStrike = minutesSince !== null && minutesSince <= 15 && weather.last_strike_distance <= 5;
  const activeRing = weather.strike_trigger_ring;

  return (
    <div className="col-span-2 bg-slate-950 border border-slate-900/60 p-4 rounded-3xl shadow-xl flex flex-col items-center justify-between min-h-[220px] relative overflow-hidden">
      
      <div className="w-full text-left flex justify-between items-start z-10">
        <div>
          <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 block">Atmosphere Radar</span>
        </div>
        {activeStorm && (
          <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase tracking-widest animate-pulse">
            Active Storm
          </span>
        )}
      </div>

      <div className="relative w-40 h-40 my-2 flex items-center justify-center">
        {/* Wind Vector Ring */}
        <svg className="absolute w-full h-full transform -rotate-90 z-20" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="48" fill="none" className="stroke-slate-900/80 stroke-[2px]" />
          <g style={{ transform: `rotate(${parseFloat(weather.wind_direction_deg || 0)}deg)`, transformOrigin: '50px 50px' }} className="transition-transform duration-700 ease-out">
            <polygon points="50,2 53,7 50,6 47,7" className="fill-cyan-400 drop-shadow-[0_0_4px_#22d3ee]" />
          </g>
        </svg>

        {/* Distance Rings */}
        <svg className="w-full h-full transform -rotate-90 z-10" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="46" fill="none" className="stroke-slate-900/60 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="39" fill="none" className="stroke-slate-900/50 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="32" fill="none" className="stroke-slate-900/40 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="25" fill="none" className="stroke-slate-900/30 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="18" fill="none" className="stroke-slate-900/20 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="11" fill="none" className="stroke-slate-950/80 stroke-[1px]" />

          {/* Dynamic Flash Triggers */}
          <circle cx="50" cy="50" r="42.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 30 ? "rgba(16, 185, 129, 0.25)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 30 ? "7" : "0"} />
          <circle cx="50" cy="50" r="35.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 25 ? "rgba(132, 204, 22, 0.25)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 25 ? "7" : "0"} />
          <circle cx="50" cy="50" r="28.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 20 ? "rgba(234, 179, 8, 0.3)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 20 ? "7" : "0"} />
          <circle cx="50" cy="50" r="21.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 15 ? "rgba(249, 115, 22, 0.3)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 15 ? "7" : "0"} />
          <circle cx="50" cy="50" r="14.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 10 ? "rgba(239, 68, 68, 0.35)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 10 ? "7" : "0"} />
          <circle cx="50" cy="50" r="5.5"  fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 5 ? "rgba(225, 29, 72, 0.4)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 5 ? "11" : "0"} />

          <line x1="50" y1="4" x2="50" y2="96" className="stroke-slate-900/20 stroke-[0.5px]" strokeDasharray="2 2" />
          <line x1="4" y1="50" x2="96" y2="50" className="stroke-slate-900/20 stroke-[0.5px]" strokeDasharray="2 2" />
        </svg>

        {/* SVG Bolt replacing the emoji */}
        <div className={`absolute w-6 h-6 rounded-full flex items-center justify-center transition-all duration-500 z-30 ${recentCloseStrike ? 'bg-rose-600/20 border border-rose-500 text-rose-400' : 'bg-slate-900 text-slate-500'}`}>
          <svg className={`w-3 h-3 fill-current select-none ${recentCloseStrike ? 'text-rose-400 scale-110 animate-pulse' : ''}`} viewBox="0 0 20 20">
            <path d="M11 0L3 10h6l-2 10 8-12H9l2-8z"/>
          </svg>
        </div>
      </div>

      <div className="w-full grid grid-cols-3 items-end text-center mt-1 z-10">
        <div className="flex flex-col items-center justify-end">
          <span className="text-[8px] font-bold text-slate-500 uppercase">Wind</span>
          <span className={`text-xs font-black font-mono tracking-tighter ${getWindColor(weather.wind_speed_mph)}`}>{weather.wind_speed_mph}</span>
        </div>
        
        <div className="flex flex-col items-center justify-end">
          {activeStorm ? (
            <div className="flex flex-col items-center justify-center">
              <span className="text-[11px] font-black tracking-tight text-amber-400 font-mono">TRACKED</span>
              <span className="text-[8px] text-slate-500 font-mono mt-0.5">{weather.last_strike_distance} mi ({minutesSince}m)</span>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center">
              <span className="text-[8px] font-bold text-slate-400 uppercase">{minutesSince === null ? 'No Strikes' : 'Last Strike'}</span>
              <span className="text-xs font-black font-mono text-slate-200 mt-0.5 tracking-tighter">{minutesSince === null ? '--' : `${minutesSince} MIN`}</span>
            </div>
          )}
        </div>

        <div className="flex flex-col items-center justify-end">
          <span className="text-[8px] font-bold text-slate-500 uppercase">Gust</span>
          <span className="text-xs font-black font-mono tracking-tighter text-rose-400">{weather.wind_gust_mph}</span>
        </div>
      </div>
    </div>
  );
}