const getScoreColor = (score) => {
  if (score >= 8) return "stroke-emerald-500";
  if (score >= 4) return "stroke-amber-400";
  return "stroke-rose-500";
};

const getTextColor = (score) => {
  if (score >= 8) return "text-emerald-400";
  if (score >= 4) return "text-amber-400";
  return "text-rose-400";
};

// Generic fallback icons - you can swap these SVG paths for your specific ones
const getIcon = (name) => {
  const isSilver = name === "Walking" || name === "Airbrushing";
  const colorClass = isSilver
    ? "text-slate-300 drop-shadow-[0_0_4px_rgba(203,213,225,0.6)]"
    : "text-slate-400";

  let path = (
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M13 10V3L4 14h7v7l9-11h-7z"
    />
  ); // Default lightning bolt

  if (name === "Walking")
    path = (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M14.639 9.361a4.978 4.978 0 01-2.278-3.921V4a2 2 0 10-4 0v1.44a4.978 4.978 0 01-2.278 3.921L4 10.5V16a2 2 0 104 0v-4.5h4V16a2 2 0 104 0v-5.5l-1.361-1.139z"
      />
    );
  if (name === "Airbrushing")
    path = (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"
      />
    );
  if (name === "Video Games")
    path = (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
      />
    );
  if (name === "Swimming")
    path = (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"
      />
    );
  if (name === "Yard Work")
    path = (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3"
      />
    );
  if (name === "Football")
    path = (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    );
  if (name === "Basketball")
    path = (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z M9 12a3 3 0 116 0 3 3 0 01-6 0z"
      />
    );
  if (name === "Driving")
    path = (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
      />
    );

  return (
    <svg
      className={`w-5 h-5 ${colorClass}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      {path}
    </svg>
  );
};

const DialActivity = ({ activity }) => {
  const current = activity.currentScore || 0;
  const forecast = activity.forecastScore || 0;

  // SVG Geometry
  const center = 24;
  const radiusOuter = 20;
  const radiusInner = 14;
  const circOuter = 2 * Math.PI * radiusOuter;
  const circInner = 2 * Math.PI * radiusInner;

  // Calculate stroke dash offsets based on score out of 10
  const offsetOuter = circOuter - (forecast / 10) * circOuter;
  const offsetInner = circInner - (current / 10) * circInner;

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-2 flex items-center justify-between">
      {/* Left: Double SVG Dial */}
      <div className="relative w-12 h-12 flex items-center justify-center">
        <svg
          className="absolute w-full h-full transform -rotate-90"
          viewBox="0 0 48 48"
        >
          {/* Background Tracks */}
          <circle
            cx={center}
            cy={center}
            r={radiusOuter}
            fill="none"
            className="stroke-slate-800"
            strokeWidth="2"
          />
          <circle
            cx={center}
            cy={center}
            r={radiusInner}
            fill="none"
            className="stroke-slate-800"
            strokeWidth="4"
          />

          {/* Outer Forecast Dial (Thinner) */}
          <circle
            cx={center}
            cy={center}
            r={radiusOuter}
            fill="none"
            className={`${getScoreColor(forecast)} transition-all duration-1000 ease-out`}
            strokeWidth="2"
            strokeDasharray={circOuter}
            strokeDashoffset={offsetOuter}
            strokeLinecap="round"
          />
          {/* Inner Current Dial (Twice as thick) */}
          <circle
            cx={center}
            cy={center}
            r={radiusInner}
            fill="none"
            className={`${getScoreColor(current)} transition-all duration-1000 ease-out`}
            strokeWidth="4"
            strokeDasharray={circInner}
            strokeDashoffset={offsetInner}
            strokeLinecap="round"
          />
        </svg>

        {/* Center SVG Icon */}
        <div className="absolute z-10 flex items-center justify-center w-full h-full">
          {getIcon(activity.name)}
        </div>
      </div>

      {/* Right: Data Labels */}
      <div className="flex flex-col items-end justify-center h-full gap-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[8px] text-slate-500 font-bold uppercase">
            N
          </span>
          <span
            className={`text-xs font-black font-mono w-4 text-right ${getTextColor(current)}`}
          >
            {current}
          </span>
        </div>
        <div className="w-full border-t border-slate-800/80"></div>
        <div className="flex items-center gap-1.5">
          <span className="text-[8px] text-slate-500 font-bold uppercase">
            F
          </span>
          <span
            className={`text-xs font-black font-mono w-4 text-right ${getTextColor(forecast)}`}
          >
            {forecast}
          </span>
        </div>
      </div>
    </div>
  );
};

export default function ActivityPlannerWidget({ activities }) {
  if (!activities || activities.length === 0) return null;

  return (
    <div className="bg-slate-950 border border-slate-900/60 p-4 rounded-3xl shadow-xl flex flex-col w-full h-full">
      <div className="w-full flex justify-between items-end border-b border-slate-900 pb-2 mb-3">
        <span className="text-[8px] font-bold text-slate-500 uppercase tracking-widest">
          Activity Matrix
        </span>
        <span className="text-[8px] font-bold text-slate-600 uppercase tracking-widest">
          V4.0 DIALS
        </span>
      </div>

      <div className="grid grid-cols-4 gap-2 h-full">
        {activities.map((act, idx) => (
          <DialActivity key={idx} activity={act} />
        ))}
      </div>
    </div>
  );
}
