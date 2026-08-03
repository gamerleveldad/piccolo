import React from 'react';

export default function RainGaugeWidget({ weather, rainStatus }) {
  if (!weather) return null;

  const currentRainAccum = parseFloat(weather.rain_accumulation_day_in) || 0.0;
  const currentRainChance = parseInt(weather.rain_chance_current) || 0;
  const currentRainRate = parseFloat(weather.rain_rate_in_hr) || 0.0;

  // Forecast time-blocks array for mapping
  const timeBlocks = [
    { label: "Morning", pct: parseInt(weather.rain_chance_morning) || 0 },
    { label: "Afternoon", pct: parseInt(weather.rain_chance_afternoon) || 0 },
    { label: "Evening", pct: parseInt(weather.rain_chance_evening) || 0 },
    { label: "Overnight", pct: parseInt(weather.rain_chance_overnight) || 0 }
  ];

  return (
    <div className="bg-slate-950 border border-slate-900 p-4 rounded-2xl shadow-2xl flex flex-col justify-between col-span-2">
      <div className="grid grid-cols-12 gap-3 items-center">
        
        {/* Today's Rain Accumulation */}
        <div className="col-span-3 text-left">
          <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500 block">Todays Rain</span>
          <div className="flex items-baseline gap-0.5 mt-0.5">
            <span className="text-2xl font-black font-mono tracking-tighter text-slate-100">
              {currentRainAccum.toFixed(2)}
            </span>
            <span className="text-xs font-bold text-slate-500 font-mono">in</span>
          </div>
        </div>

        {/* Graphical Rain Accumulation Cylinder */}
        <div className="col-span-3 flex items-center justify-center">
          <div className="flex items-center gap-1 h-14 select-none relative">
            <div className="flex flex-col justify-between h-full text-[8px] font-mono font-black text-slate-600 text-right w-4 leading-none pr-0.5">
              <span>2.0</span>
              <span>1.0</span>
              <span>0.0</span>
            </div>
            <div className="w-5 h-full bg-slate-950 rounded border border-slate-900 overflow-hidden relative shadow-inner">
              <div 
                style={{ height: `${Math.min((currentRainAccum / 2.0) * 100, 100)}%` }} 
                className="absolute bottom-0 left-0 right-0 w-full bg-gradient-to-t from-blue-600 to-blue-400 transition-all duration-500"
              />
            </div>
          </div>
        </div>

        {/* Current Chance of Rain */}
        <div className="col-span-3 text-left">
          <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500 block">Current Rain Chance</span>
          <div className="flex items-baseline gap-0.5 mt-0.5">
            <span className="text-2xl font-black font-mono tracking-tight text-blue-400">
              {currentRainChance}
            </span>
            <span className="text-xs font-bold text-blue-600 font-mono">%</span>
          </div>
        </div>

        {/* Hourly Forecast Time-Blocks */}
        <div className="col-span-3 flex flex-col gap-0.5 text-[8px] font-mono">
          {timeBlocks.map((block) => (
            <div key={block.label} className="flex items-center justify-between bg-slate-900/30 border border-slate-900/60 rounded px-1 py-0.5 relative overflow-hidden h-[15px]">
              <div 
                style={{ width: `${block.pct}%` }} 
                className="absolute left-0 top-0 bottom-0 bg-blue-500/20 transition-all duration-500 pointer-events-none"
              />
              <span className="text-slate-300 relative z-10 font-bold">{block.label}</span>
              <span className={`relative z-10 font-black ${block.pct > 0 ? 'text-blue-400' : 'text-slate-600'}`}>
                {block.pct}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Sensor Diagnostics Footer */}
      <div className="border-t border-slate-900 pt-1.5 mt-2 flex justify-between items-center text-[8px] font-black uppercase font-mono tracking-wider">
        <span className="text-slate-600">
          Sensor: <span className={rainStatus?.color || 'text-slate-500'}>{rainStatus?.text || 'Loading'}</span>
        </span>
        <span className="text-slate-400">
          Rate: <span className="text-slate-200">{currentRainRate.toFixed(2)}</span> in/h
        </span>
      </div>
    </div>
  );
}