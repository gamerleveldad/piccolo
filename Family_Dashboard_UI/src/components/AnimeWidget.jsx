import React from 'react';

export default function AnimeWidget({ shows }) {
  if (!shows || shows.length === 0) return null;

  return (
    <div className="bg-slate-950 border border-purple-950/40 p-3 rounded-2xl shadow-xl flex flex-col justify-between font-mono">
      <span className="text-[9px] font-black uppercase tracking-widest text-purple-400 block mb-2">
        Crunchyroll Active Progress
      </span>
      <div className="space-y-1.5 max-h-[100px] overflow-y-auto custom-scrollbar pr-1">
        {shows.map((show, idx) => {
          const current = show.current || 0;
          const total = show.total || 1;
          const pct = Math.min(Math.round((current / total) * 100), 100);

          return (
            <div key={idx} className="bg-slate-900/40 p-1.5 rounded-lg border border-slate-900 text-[10px]">
              <div className="flex justify-between text-slate-300 font-bold mb-1">
                <span className="truncate max-w-[140px]">{show.name}</span>
                <span className="text-purple-400 font-mono">Ep {current}/{total}</span>
              </div>
              <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-900">
                <div 
                  style={{ width: `${pct}%` }} 
                  className="h-full bg-gradient-to-r from-purple-600 to-indigo-500 transition-all duration-500"
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}