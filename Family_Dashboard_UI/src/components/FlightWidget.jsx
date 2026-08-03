import React from 'react';

export default function FlightWidget({ flights }) {
  if (!flights) return null;

  return (
    <div className="bg-slate-950 border border-cyan-950/40 p-3 rounded-2xl shadow-xl flex flex-col justify-between font-mono">
      <div className="flex justify-between items-center mb-2">
        <span className="text-[9px] font-black uppercase tracking-widest text-cyan-500 block">
          Overhead Traffic
        </span>
        <span className="text-[8px] font-bold text-cyan-700 bg-cyan-950/30 px-1.5 py-0.5 rounded">
          {flights.length} TRK
        </span>
      </div>
      
      <div className="space-y-1.5 max-h-[100px] overflow-y-auto custom-scrollbar pr-1">
        {flights.length === 0 ? (
          <div className="text-center text-slate-600 text-[9px] italic mt-4">Airspace clear</div>
        ) : (
          flights.map((flight, idx) => {
            return (
              <div key={idx} className="bg-slate-900/40 p-1.5 rounded-lg border border-slate-900 text-[9px] flex justify-between items-center">
                <div className="flex flex-col">
                  <span className="text-slate-300 font-bold">{flight.flight || flight.hex}</span>
                  <span className="text-slate-500">ALT: {flight.alt_baro || '---'} ft</span>
                </div>
                <div className="flex flex-col text-right">
                  <span className="text-cyan-400 font-bold">{flight.gs || '---'} kts</span>
                  <span className="text-slate-500">{flight.category || 'UNK'}</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}