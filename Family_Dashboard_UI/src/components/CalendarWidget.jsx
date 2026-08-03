import React from 'react';

export default function CalendarWidget({ events }) {
  // Format ISO strings into human-readable 12-hour AM/PM timestamps
  const formatEventTime = (isoString) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
  };

  // Group headers to denote Today, Tomorrow, or specific dates
  const formatAgendaGroupDate = (dateStr) => {
    const d = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date();
    tomorrow.setDate(today.getDate() + 1);
    if (d.toDateString() === today.toDateString()) return 'Today';
    if (d.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
    return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
  };

  // Generate the array of dates for the 28-day micro calendar header
  const getMicroCalendarDays = () => {
    const days = [];
    const today = new Date();
    const startSunday = new Date(today);
    startSunday.setDate(today.getDate() - today.getDay());
    startSunday.setHours(0, 0, 0, 0);
    for (let i = 0; i < 28; i++) {
      const nextDay = new Date(startSunday);
      nextDay.setDate(startSunday.getDate() + i);
      days.push(nextDay);
    }
    return days;
  };

  const microDays = getMicroCalendarDays();
  const todayStr = new Date().toDateString();
  const sortedEvents = [...events].sort((a, b) => new Date(a.start) - new Date(b.start));
  
  // Filter out any events that occurred strictly before 12:00 AM today
  const activeUpcomingEvents = sortedEvents.filter(e => new Date(e.start) >= new Date().setHours(0,0,0,0));

  return (
    <div className="h-full w-full overflow-y-auto custom-scrollbar bg-slate-950 border border-slate-900/60 p-3 rounded-2xl shadow-xl flex flex-col absolute inset-0">
      
      {/* Header */}
      <div className="flex justify-between items-center border-b border-slate-900 pb-2 mb-2 shrink-0">
        <div>
          <span className="text-[9px] font-black uppercase tracking-widest text-blue-400">Schedule Horizon (28-Day)</span>
        </div>
        <span className="text-[8px] font-mono bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full border border-blue-500/20 font-bold">
          {activeUpcomingEvents.length} Entries
        </span>
      </div>

      {/* 28-Day Micro Calendar Grid */}
      <div className="grid grid-cols-7 gap-0.5 bg-slate-900/20 p-1 rounded-xl border border-slate-900/50 mb-2 text-center text-[9px] shrink-0">
        {microDays.map((date, idx) => {
          const dateStr = date.toDateString();
          const isToday = dateStr === todayStr;
          const dayEvents = events.filter(e => new Date(e.start).toDateString() === dateStr);

          return (
            <div key={idx} className={`flex flex-col items-center py-0.5 rounded ${isToday ? 'bg-blue-500 font-black shadow-md' : 'hover:bg-slate-900/60'}`}>
              <span className={isToday ? 'text-blue-100' : 'text-slate-500'}>{date.toLocaleDateString([], { weekday: 'narrow' })}</span>
              <span className={`font-mono font-bold ${isToday ? 'text-white' : 'text-slate-300'}`}>{date.getDate()}</span>
              <div className="flex gap-0.5 justify-center items-center h-1 w-full overflow-hidden">
                {dayEvents.slice(0, 2).map((ev, eIdx) => (
                  <span key={eIdx} style={{ backgroundColor: isToday ? '#white' : (ev.color || '#3b82f6') }} className="w-1 h-1 rounded-full shrink-0" />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Agenda Event List */}
      <div className="flex-1 overflow-y-auto pr-0.5 space-y-2 custom-scrollbar text-xs relative">
        {activeUpcomingEvents.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 py-6 text-[10px]">No upcoming entries listed</div>
        ) : (
          Object.entries(
            // Reduce the flat array of events into an object grouped by date strings
            activeUpcomingEvents.reduce((groups, event) => {
              const dateKey = new Date(event.start).toDateString();
              if (!groups[dateKey]) groups[dateKey] = [];
              groups[dateKey].push(event);
              return groups;
            }, {})
          ).map(([dateStr, dayEvents]) => (
            <div key={dateStr} className="space-y-1">
              <div className="sticky top-0 bg-slate-950/90 py-0.5 flex items-center gap-1 z-10 text-[9px] font-mono text-slate-400">
                <span>{formatAgendaGroupDate(dateStr)}</span>
                <div className="h-px bg-slate-900 flex-1" />
              </div>
              <div className="grid gap-1">
                {dayEvents.map((ev) => (
                  <div key={ev.id} style={{ borderLeftColor: ev.color || '#3b82f6' }} className="border-l-2 bg-slate-900/20 border border-slate-900 p-2 rounded-lg flex items-center justify-between gap-2">
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="font-bold text-slate-200 truncate text-[11px]">{ev.summary}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0 text-[10px]">
                      {ev.forecast && (
                        <div className="flex items-center gap-1 font-mono font-black text-slate-400">
                          <span>{ev.forecast.temp}°</span>
                          {ev.forecast.rain_pct > 0 && <span className="text-blue-400">{ev.forecast.rain_pct}%</span>}
                        </div>
                      )}
                      {ev.is_all_day ? (
                        <span className="text-[8px] bg-slate-950 text-slate-500 px-1 rounded border border-slate-900 font-mono">ALL</span>
                      ) : (
                        <span className="font-mono text-blue-400 font-bold">{formatEventTime(ev.start).replace(':00', '')}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}