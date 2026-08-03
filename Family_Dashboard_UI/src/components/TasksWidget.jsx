import React, { useState, useEffect } from 'react';

export default function TasksWidget({ apiBase }) {
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);

  const fetchTasks = async () => {
    try {
      const res = await fetch(`${apiBase}/api/tasks`);
      if (res.ok) {
        const data = await res.json();
        setTasks(data);
      }
    } catch (err) {
      console.error("Failed fetching chores", err);
    }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 300000); // 5 mins
    return () => clearInterval(interval);
  }, [apiBase]);

  const handleCompleteTask = async (taskId, e) => {
    e.stopPropagation();
    try {
      const res = await fetch(`${apiBase}/api/tasks/complete/${taskId}`, { method: 'POST' });
      if (res.ok) fetchTasks();
    } catch (err) {
      console.error("Failed completing task", err);
    }
  };

  const getTaskTag = (task) => {
    if (!task.due_date_str) return null;
    const [year, month, day] = task.due_date_str.split('-').map(Number);
    const localDue = new Date(year, month - 1, day);
    const today = new Date();
    today.setHours(0,0,0,0); localDue.setHours(0,0,0,0);
    const diffDays = Math.round((localDue.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
    let label = diffDays <= 0 ? "Today" : diffDays === 1 ? "Tomor" : localDue.toLocaleDateString('en-US', { weekday: 'short' });
    let styleClass = diffDays <= 0 ? "bg-sky-950/60 border-sky-500/50 text-sky-400" : "bg-purple-950/60 border-purple-500/50 text-purple-400";
    return <span className={`text-[8px] font-mono font-black uppercase px-1 py-0.5 rounded border ${styleClass} shrink-0`}>{label}</span>;
  };

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-2.5 flex flex-col absolute inset-0 w-full h-full">
      <h3 className="text-[11px] font-black font-mono uppercase tracking-wider text-slate-400 mb-2 shrink-0">[TASK] List</h3>
      <div className="flex-1 overflow-y-auto space-y-1 pr-0.5 custom-scrollbar text-[11px] relative">
        {tasks.length === 0 ? (
          <div className="text-center text-slate-600 mt-6 italic text-[10px]">House clean!</div>
        ) : (
          tasks.map(t => (
            <div key={t.id} onClick={() => setSelectedTask(t)} className="flex items-center justify-between p-1.5 bg-slate-950/50 border border-slate-900 rounded-lg cursor-pointer">
              <div className="flex items-center gap-2 min-w-0">
                <button onClick={(e) => handleCompleteTask(t.id, e)} className="w-3 h-3 rounded-full border border-slate-700 flex items-center justify-center shrink-0">
                  <span className="w-1 h-1 rounded-full bg-transparent hover:bg-green-500" />
                </button>
                <span className="text-slate-200 truncate max-w-[120px] font-medium">{t.title}</span>
              </div>
              {getTaskTag(t)}
            </div>
          ))
        )}
      </div>

      {selectedTask && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setSelectedTask(null)}>
          <div className="bg-slate-950 border border-slate-800 p-4 rounded-xl max-w-xs w-full font-mono text-[11px]" onClick={e => e.stopPropagation()}>
            <h4 className="font-black text-slate-100 mb-2 truncate">{selectedTask.title}</h4>
            <p className="text-slate-400 bg-slate-900/60 p-2 rounded-lg border border-slate-900 min-h-[40px] whitespace-pre-wrap">{selectedTask.notes || "No description provided."}</p>
            <button onClick={() => setSelectedTask(null)} className="mt-3 w-full py-1 bg-slate-900 text-slate-300 rounded-lg font-bold border border-slate-800">Close</button>
          </div>
        </div>
      )}
    </div>
  );
}