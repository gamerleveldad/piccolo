import React from 'react';
import WeatherIcon from './WeatherIcon';

export default function ForecastStripWidget({ dailyForecast }) {
  // Graceful fallback if InfluxDB is empty on local startup
  const dailyForecasts = (dailyForecast && dailyForecast.length > 0) ? dailyForecast : [
    { icon: 'clear-day', high: 92, low: 75, rain_pct: 10 },
    { icon: 'partly-cloudy-day', high: 90, low: 76, rain_pct: 25 },
    { icon: 'rainy', high: 86, low: 74, rain_pct: 80 },
    { icon: 'thunderstorm', high: 85, low: 73, rain_pct: 95 },
    { icon: 'partly-cloudy-day', high: 89, low: 75, rain_pct: 40 },
    { icon: 'clear-day', high: 93, low: 77, rain_pct: 5 },
    { icon: 'clear-day', high: 94, low: 76, rain_pct: 0 }
  ];

  const getDynamicDateFields = (offset) => {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    return { dayName: days[d.getDay()], dateString: `${d.getMonth() + 1}/${d.getDate()}` };
  };

  return (
    <div className="bg-slate-950/40 border border-slate-900 h-full p-2 rounded-2xl flex flex-col justify-between shadow-2xl backdrop-blur-sm">
      <div className="flex flex-col justify-between h-full gap-0.5">
        {dailyForecasts.slice(0, 7).map((day, idx) => {
          const { dayName, dateString } = getDynamicDateFields(idx);
          const rainPct = parseInt(day.rain_pct) || 0;
          const isToday = idx === 0;

          return (
            <div key={idx} className={`flex flex-col justify-center py-1 border-b border-slate-900/60 last:border-0 ${isToday ? 'bg-blue-950/10 border-l-2 border-blue-500 pl-1' : ''}`}>
              <div className="flex items-center gap-1">
                <span className={`text-[20px] font-black uppercase font-mono ${isToday ? 'text-blue-400' : 'text-slate-200'}`}>{dayName}</span>
                <span className="text-[16px] font-bold text-slate-500 font-mono">{dateString}</span>
              </div>
              <div className="flex items-baseline gap-1 font-mono leading-none my-0.5">
                <span className="text-2xl font-black text-slate-100">{Math.round(day.high)}°</span>
                <span className="text-[20px] font-bold text-slate-500">{Math.round(day.low)}°</span>
              </div>
              <div className="flex items-center justify-between text-[18px] font-mono mt-1 pr-1">
                <WeatherIcon icon={day.icon} className="w-10 h-10 shrink-0" />
                <span className={rainPct > 15 ? 'text-cyan-400 font-extrabold' : 'text-slate-700'}>{rainPct}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}