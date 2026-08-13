import { useEffect, useState } from "react";

export default function HeaderBar({ connected, dailyVerse }) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());

  // Clock tick effect
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <>
      {/* Target the specific NLT API HTML elements to make them fit the dashboard theme */}
      <style>{`
        .nlt-verse-container .bk_ch_vs_header { display: none; }
        .nlt-verse-container .vn { font-size: 0.6em; vertical-align: super; margin-right: 0.2rem; color: #94a3b8; font-weight: bold; }
        .nlt-verse-container p { margin-bottom: 0.5rem; }
        .nlt-verse-container .poet2 { padding-left: 1.5rem; }
      `}</style>

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

        {/* Right Side: Clock & Status Pill */}
        <div className="flex items-center gap-4 shrink-0">
          <div className="text-right font-mono uppercase tracking-widest hidden sm:block">
            <div className="text-[10px] text-slate-400 font-bold">
              {currentTime.toLocaleDateString("en-US", {
                weekday: "short",
                month: "short",
                day: "numeric",
              })}
            </div>
            <div className="text-[11px] text-slate-200 font-black">
              {currentTime.toLocaleTimeString("en-US", {
                hour12: true,
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </div>
          </div>

          <div className="flex items-center gap-2 bg-slate-950 border border-purple-900/30 px-3 py-1 rounded-full shrink-0">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              {connected ? "Active" : "Offline"}
            </span>
            <span
              className={`h-2.5 w-2.5 rounded-full ${connected ? "bg-blue-500 shadow-[0_0_8px_#3b82f6]" : "bg-rose-500 shadow-[0_0_8px_#f43f5e]"}`}
            />
          </div>
        </div>
      </header>

      {/* Verse Modal Overlay */}
      {isModalOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4"
          onClick={() => setIsModalOpen(false)}
        >
          <div
            className="bg-slate-950 border border-purple-900/40 w-full max-w-md p-6 rounded-2xl shadow-2xl font-mono text-slate-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center border-b border-slate-900 pb-3 mb-4">
              <h4 className="text-sm font-black uppercase tracking-wider text-purple-400 flex items-center gap-2">
                Daily Scripture
              </h4>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-slate-500 hover:text-slate-300 text-lg"
              >
                X
              </button>
            </div>

            {/* Inject the NLT API HTML directly */}
            <div
              className="text-lg font-serif italic text-slate-300 leading-relaxed mb-4 max-h-[50vh] overflow-y-auto custom-scrollbar pr-2 nlt-verse-container"
              dangerouslySetInnerHTML={{
                __html: dailyVerse?.html || `"${dailyVerse?.text}"`,
              }}
            />

            <p className="text-right text-sm font-bold text-slate-400">
              — {dailyVerse?.reference}
            </p>
            <button
              onClick={() => setIsModalOpen(false)}
              className="mt-6 w-full py-2.5 bg-slate-900 text-slate-400 font-bold text-xs rounded-xl border border-slate-800 uppercase hover:bg-slate-800 transition-colors tracking-widest"
            >
              Close Passage
            </button>
          </div>
        </div>
      )}
    </>
  );
}
