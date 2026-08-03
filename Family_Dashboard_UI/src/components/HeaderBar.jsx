import React, { useState } from 'react';

export default function HeaderBar({ connected, dailyVerse }) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  return (
    <>
      <header className="flex justify-between items-center border-b border-purple-950/40 pb-3 mb-4">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 w-full">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-lg font-black uppercase tracking-wider text-slate-100 font-mono cursor-pointer transition-colors hover:text-purple-400">
                Howls Moving Dashboard
              </h1>
            </div>
            <div className="flex items-center gap-2 text-[10px] font-mono font-bold text-slate-500 uppercase mt-0.5 flex-wrap">
              <span>Live Station Feed</span>
              <span className="text-slate-800">|</span>
              <div 
                className="flex items-center gap-1 cursor-pointer hover:bg-purple-900/20 px-1.5 py-0.5 rounded transition-colors"
                onClick={() => setIsModalOpen(true)}
              >
                <span className="text-purple-500/90 font-black">[VERSE]</span>
                <span className="text-slate-300 normal-case font-semibold truncate max-w-[200px] sm:max-w-[300px]">
                  {dailyVerse?.reference} NLT: "{dailyVerse?.text}"
                </span>
              </div>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2 bg-slate-950 border border-purple-900/30 px-3 py-1 rounded-full shrink-0">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            {connected ? 'Active' : 'Offline'}
          </span>
          <span className={`h-2.5 w-2.5 rounded-full ${connected ? 'bg-blue-500 shadow-[0_0_8px_#3b82f6]' : 'bg-rose-500 shadow-[0_0_8px_#f43f5e]'}`} />
        </div>
      </header>  

      {/* Verse Modal Overlay */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4" onClick={() => setIsModalOpen(false)}>
          <div className="bg-slate-950 border border-purple-900/40 w-full max-w-md p-6 rounded-2xl shadow-2xl font-mono text-slate-200" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center border-b border-slate-900 pb-3 mb-4">
              <h4 className="text-sm font-black uppercase tracking-wider text-purple-400 flex items-center gap-2">Daily Scripture</h4>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-500 hover:text-slate-300 text-lg">X</button>
            </div>
            <p className="text-lg font-serif italic text-slate-300 leading-relaxed mb-4 max-h-[50vh] overflow-y-auto custom-scrollbar pr-2">"{dailyVerse?.text}"</p>
            <p className="text-right text-sm font-bold text-slate-400">— {dailyVerse?.reference}</p>
            <button onClick={() => setIsModalOpen(false)} className="mt-6 w-full py-2.5 bg-slate-900 text-slate-400 font-bold text-xs rounded-xl border border-slate-800 uppercase hover:bg-slate-800 transition-colors tracking-widest">Close Passage</button>
          </div>
        </div>
      )}
    </>
  );
}