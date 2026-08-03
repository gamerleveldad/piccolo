import React, { useState, useEffect } from 'react';

export default function SleeperWidget({ apiBase }) {
  const [data, setData] = useState(null);
  const [activeMatchup, setActiveMatchup] = useState(null);

  useEffect(() => {
    const fetchSleeperData = async () => {
      try {
        const res = await fetch(`${apiBase}/api/sleeper`);
        if (res.ok) {
          setData(await res.json());
        }
      } catch (err) {
        console.error("Failed fetching Sleeper payload", err);
      }
    };
    fetchSleeperData();
    const interval = setInterval(fetchSleeperData, 300000);
    return () => clearInterval(interval);
  }, [apiBase]);

  if (!data || data.mode === "disabled") return null;

  if (data.mode === "draft") {
    const draftDate = new Date(data.draft_start);
    const daysLeft = Math.max(0, Math.floor((data.draft_start - Date.now()) / (1000 * 60 * 60 * 24)));
    return (
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-2.5 flex flex-col justify-center items-center text-center font-mono absolute inset-0 w-full h-full">
        <h4 className="text-[10px] font-black uppercase text-slate-400 truncate w-full">{data.name}</h4>
        <div className="text-xl font-black text-cyan-400 mt-1 mb-0.5">{daysLeft} Days</div>
        <div className="text-[9px] text-slate-300 font-bold mb-1">
          {draftDate.toLocaleDateString()} @ {draftDate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
        </div>
        <p className="text-[8px] text-slate-500 uppercase tracking-widest font-bold">Until Live Draft</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-2.5 flex flex-col absolute inset-0 w-full h-full">
      <h3 className="text-[11px] font-black font-mono uppercase tracking-wider text-slate-400 mb-2 flex justify-between shrink-0">
        <span>[FF] Sleeper W{data.week}</span>
      </h3>
      <div className="flex-1 overflow-y-auto space-y-1 pr-0.5 custom-scrollbar text-[11px] relative">
        {data.matchups?.map((match, idx) => {
          const teamA = match[0]; const teamB = match[1];
          return (
            <div key={idx} onClick={() => setActiveMatchup({ teamA, teamB })} className="p-1.5 bg-slate-950/50 border border-slate-900 rounded-lg cursor-pointer space-y-0.5 hover:bg-slate-900 transition-colors">
              <div className="flex justify-between">
                <span className="font-bold text-slate-200 truncate max-w-[120px]">{teamA.owner_name}</span>
                <span className="font-mono text-slate-400 font-bold">{teamA.points.toFixed(1)}</span>
              </div>
              <div className="text-[7px] text-center text-slate-700 font-black leading-none">— VS —</div>
              <div className="flex justify-between">
                <span className="font-bold text-slate-200 truncate max-w-[120px]">{teamB.owner_name}</span>
                <span className="font-mono text-slate-400 font-bold">{teamB.points.toFixed(1)}</span>
              </div>
            </div>
          );
        })}
      </div>

      {activeMatchup && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setActiveMatchup(null)}>
          <div className="bg-slate-950 border border-slate-800 p-3 rounded-xl max-w-sm w-full h-[60vh] flex flex-col font-mono text-[10px]" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center border-b border-slate-900 pb-1 mb-2">
              <span className="font-black text-blue-400 uppercase">Head-to-Head</span>
              <button onClick={() => setActiveMatchup(null)} className="text-slate-500 font-bold hover:text-slate-300">X</button>
            </div>
            <div className="flex-1 grid grid-cols-2 gap-2 overflow-hidden">
              <div className="flex flex-col overflow-y-auto space-y-1 custom-scrollbar pr-1">
                <div className="font-black text-slate-200 bg-slate-900 p-1 rounded text-center truncate">{activeMatchup.teamA.owner_name}</div>
                {activeMatchup.teamA.starters?.map((pId, i) => (
                  <div key={i} className="bg-slate-900/30 p-1 rounded flex justify-between items-center">
                    <span className="text-slate-500 truncate max-w-[50px] text-[8px]">ID:{pId}</span>
                    <span className="font-bold text-slate-300">{(activeMatchup.teamA.custom_roster_points_map?.[pId] || 0.0).toFixed(1)}</span>
                  </div>
                ))}
              </div>
              <div className="flex flex-col overflow-y-auto space-y-1 custom-scrollbar pl-1">
                <div className="font-black text-slate-200 bg-slate-900 p-1 rounded text-center truncate">{activeMatchup.teamB.owner_name}</div>
                {activeMatchup.teamB.starters?.map((pId, i) => (
                  <div key={i} className="bg-slate-900/30 p-1 rounded flex justify-between items-center">
                    <span className="text-slate-500 truncate max-w-[50px] text-[8px]">ID:{pId}</span>
                    <span className="font-bold text-slate-300">{(activeMatchup.teamB.custom_roster_points_map?.[pId] || 0.0).toFixed(1)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}