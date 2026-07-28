import { useEffect, useState } from 'react';

export default function App() {
  const [schedule, setSchedule] = useState([]);
  const [history, setHistory] = useState([]);
  
  // State for the "Add New Show" form
  const [newName, setNewName] = useState('');
  const [newStatus, setNewStatus] = useState('Watching');
  const [newRating, setNewRating] = useState('Liked');
  const [newCurrent, setNewCurrent] = useState(0);
  const [newTotal, setNewTotal] = useState(0);

  // Map JavaScript's Sunday-start to Python's Monday-start indexing
  const jsDay = new Date().getDay(); 
  const currentDayIndex = jsDay === 0 ? 6 : jsDay - 1; 
  
  // Align the header array to match the 0-6 Python index
  const daysOfWeek = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const API_BASE = import.meta.env.VITE_API_BASE_URL;

  const fetchData = () => {
    fetch(`${API_BASE}/api/schedule`)
      .then(res => res.json())
      .then(data => setSchedule(data))
      .catch(err => console.error(err));

    fetch(`${API_BASE}/api/history`)
      .then(res => res.json())
      .then(data => setHistory(data))
      .catch(err => console.error(err));
  };

  useEffect(() => {
    fetchData();
  }, []);

  // --- CRUD Handlers ---
  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;

    await fetch(`${API_BASE}/api/history`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        anime_name: newName, 
        status: newStatus, 
        user_rating: newRating,
        current_episode: parseInt(newCurrent) || 0,
        total_episodes: parseInt(newTotal) || 0
      })
    });
    setNewName('');
    setNewCurrent(0);
    setNewTotal(0);
    fetchData();
  };

  const handleUpdate = async (anime_name, status, user_rating, current_episode, total_episodes) => {
    // Ensure strict integer parsing before sending to PostgreSQL
    const safeCurrent = parseInt(current_episode) || 0;
    const safeTotal = parseInt(total_episodes) || 0;

    await fetch(`${API_BASE}/api/history/${encodeURIComponent(anime_name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        status, 
        user_rating, 
        current_episode: safeCurrent, 
        total_episodes: safeTotal 
      })
    });
    fetchData();
  };

  const handleDelete = async (anime_name) => {
    if (!window.confirm(`Are you sure you want to delete ${anime_name}?`)) return;
    await fetch(`${API_BASE}/api/history/${encodeURIComponent(anime_name)}`, {
      method: 'DELETE'
    });
    fetchData();
  };

  return (
    <div className="min-h-screen bg-crbase text-gray-100 p-4 lg:p-8 font-sans overflow-x-hidden">
      
      <header className="mb-8 lg:mb-12 border-b border-craqua/30 pb-4">
        <h1 className="text-3xl lg:text-4xl font-bold tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-craqua to-crorange">
          TRACKER WIDGET
        </h1>
        <p className="text-xs lg:text-sm text-gray-400 uppercase tracking-widest mt-1">Active Season Matrix</p>
      </header>

      {/* --- SCHEDULE CALENDAR --- */}
      {/* Updated to wrap on mobile (1 col), tablet (2 col), and desktop (7 col) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-7 gap-4 mb-12 lg:mb-16">
        {daysOfWeek.map((day, index) => {
          const isToday = index === currentDayIndex;
          const dayShows = schedule.filter(show => show.weekday === index);

          return (
            <div key={day} className={`rounded-lg p-4 border transition-all ${
                isToday ? "bg-crpanel border-crorange shadow-[0_0_15px_rgba(252,76,2,0.2)]" : "bg-crbase border-gray-800"
              }`}>
              <h2 className={`text-center font-bold mb-4 uppercase text-sm ${isToday ? "text-crorange" : "text-craqua"}`}>
                {day}
              </h2>
              <div className="space-y-3">
                {dayShows.length > 0 ? dayShows.map(show => (
                  <div key={show.name} className="bg-gray-800/50 p-2 rounded text-xs border border-gray-700/50 text-center lg:text-left">
                    {show.name}
                  </div>
                )) : (
                  <div className="text-gray-600 text-xs text-center italic">No drops</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {/* --- ACTIVE PROGRESS WIDGET --- */}
      {history.filter(item => item.status === 'Watching').length > 0 && (
        <div className="bg-crpanel p-4 lg:p-6 rounded-lg border border-gray-800 shadow-xl mb-12 lg:mb-16">
          <h2 className="text-xl lg:text-2xl font-bold text-craqua mb-6 border-b border-gray-700 pb-2">Active Watch Progress</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {history
              .filter(item => item.status === 'Watching')
              .map(item => {
                const current = item.current_episode || 0;
                const total = item.total_episodes || 0;
                // Calculate percentage, preventing division by zero if total isn't set yet
                const percent = total > 0 ? Math.min(Math.round((current / total) * 100), 100) : 0;
                
                return (
                  <div key={item.name} className="bg-crbase p-4 rounded border border-gray-700 hover:border-gray-500 transition-colors">
                    <div className="flex justify-between items-end mb-2">
                      <span className="font-bold text-gray-200 truncate pr-2">{item.name}</span>
                      <span className="text-xs font-mono text-crorange whitespace-nowrap">
                        {current} / {total > 0 ? total : '?'}
                      </span>
                    </div>
                    
                    {/* The Progress Bar */}
                    <div className="w-full bg-gray-900 rounded-full h-2 mt-2 overflow-hidden border border-gray-800">
                      <div 
                        className="bg-gradient-to-r from-craqua to-cyan-400 h-2 rounded-full transition-all duration-500 ease-out shadow-[0_0_10px_rgba(0,142,151,0.5)]" 
                        style={{ width: `${percent}%` }}
                      ></div>
                    </div>
                  </div>
                );
            })}
          </div>
        </div>
      )}
      {/* --- WATCH HISTORY MANAGEMENT --- */}
      <div className="bg-crpanel p-4 lg:p-6 rounded-lg border border-gray-800 shadow-xl">
        <h2 className="text-xl lg:text-2xl font-bold text-craqua mb-6 border-b border-gray-700 pb-2">Watch History Roster</h2>
        
        {/* Add New Show Form */}
        {/* Flex layout now stacks vertically on small screens and aligns horizontally on extra-large screens */}
        <form onSubmit={handleAdd} className="flex flex-col xl:flex-row gap-4 mb-8 bg-crbase p-4 rounded-lg border border-gray-700">
          <input 
            type="text" 
            placeholder="Anime Title..." 
            value={newName} 
            onChange={e => setNewName(e.target.value)}
            className="flex-1 w-full bg-gray-800 text-white px-4 py-2 rounded focus:outline-none focus:ring-1 focus:ring-craqua border border-gray-700"
          />
          <div className="flex gap-2 items-center justify-center bg-gray-800 px-3 py-2 rounded border border-gray-700 w-full xl:w-auto">
             <span className="text-xs text-gray-400">Ep:</span>
             <input 
                type="number" min="0" value={newCurrent} 
                onChange={e => {
                    const val = parseInt(e.target.value) || 0;
                    setNewCurrent(val);
                    if (val > newTotal) setNewTotal(val); // Logic Constraint #1
                }} 
                className="w-12 bg-transparent text-white text-center focus:outline-none" 
             />
             <span className="text-xs text-gray-400">/</span>
             <input 
                type="number" min="0" value={newTotal} 
                onChange={e => {
                    const val = parseInt(e.target.value) || 0;
                    setNewTotal(val);
                    if (val < newCurrent) setNewCurrent(val); // Logic Constraint #2
                }} 
                className="w-12 bg-transparent text-white text-center focus:outline-none" 
             />
          </div>
          <div className="flex gap-2 w-full xl:w-auto">
            <select value={newStatus} onChange={e => setNewStatus(e.target.value)} className="flex-1 bg-gray-800 text-white px-2 py-2 rounded border border-gray-700 focus:outline-none focus:ring-1 focus:ring-craqua">
              <option value="Watching">Watching</option>
              <option value="Pending">Pending</option>
              <option value="Dormant">Dormant</option>
              <option value="Completed">Completed</option>
              <option value="Dropped">Dropped</option>
            </select>
            <select value={newRating} onChange={e => setNewRating(e.target.value)} className="flex-1 bg-gray-800 text-white px-2 py-2 rounded border border-gray-700 focus:outline-none focus:ring-1 focus:ring-craqua">
              <option value="Liked">Liked</option>
              <option value="Disliked">Disliked</option>
              <option value="Neutral">Neutral</option>
            </select>
          </div>
          <button type="submit" className="w-full xl:w-auto bg-gradient-to-r from-craqua to-cyan-600 hover:to-cyan-500 text-white px-6 py-2 rounded font-bold transition-all">
            Add Title
          </button>
        </form>

        {/* History List */}
        <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
          {history.map(item => (
            <div key={item.name} className="flex flex-col lg:flex-row items-start lg:items-center justify-between bg-crbase p-3 lg:p-4 rounded border border-gray-800 hover:border-gray-600 transition-colors gap-3">
              <span className="font-semibold text-gray-200 flex-1 w-full lg:w-auto text-lg lg:text-base break-words">{item.name}</span>
              
              <div className="flex flex-wrap lg:flex-nowrap gap-3 items-center w-full lg:w-auto justify-between lg:justify-end">
                
                {/* Progress Tracking Inputs */}
                <div className="flex gap-1 items-center bg-gray-800 px-2 py-1.5 rounded border border-gray-700">
                  <input 
                    type="number" 
                    min="0"
                    value={item.current_episode ?? 0} 
                    onChange={(e) => {
                        const newCurr = parseInt(e.target.value) || 0;
                        const currentTotal = item.total_episodes || 0;
                        // Constraint Logic #1 for existing items
                        const safeTotal = newCurr > currentTotal ? newCurr : currentTotal; 
                        handleUpdate(item.name, item.status, item.rating, newCurr, safeTotal);
                    }}
                    className="w-12 bg-transparent text-sm text-craqua text-center font-bold focus:outline-none"
                  />
                  <span className="text-xs text-gray-500">/</span>
                  <input 
                    type="number" 
                    min="0"
                    value={item.total_episodes ?? 0} 
                    onChange={(e) => {
                        const newTot = parseInt(e.target.value) || 0;
                        const currentCurr = item.current_episode || 0;
                        // Constraint Logic #2 for existing items
                        const safeCurr = newTot < currentCurr ? newTot : currentCurr;
                        handleUpdate(item.name, item.status, item.rating, safeCurr, newTot);
                    }}
                    className="w-12 bg-transparent text-sm text-gray-300 text-center focus:outline-none"
                  />
                </div>

                <div className="flex gap-2 flex-1 lg:flex-none">
                  <select 
                    value={item.status} 
                    onChange={(e) => handleUpdate(item.name, e.target.value, item.rating, item.current_episode, item.total_episodes)}
                    className="flex-1 lg:flex-none bg-gray-800 text-xs text-gray-300 px-2 lg:px-3 py-2 lg:py-1.5 rounded border border-gray-700 focus:outline-none focus:border-craqua"
                  >
                    <option value="Watching">Watching</option>
                    <option value="Pending">Pending</option>
                    <option value="Dormant">Dormant</option>
                    <option value="Completed">Completed</option>
                    <option value="Dropped">Dropped</option>
                  </select>

                  <select 
                    value={item.rating} 
                    onChange={(e) => handleUpdate(item.name, item.status, e.target.value, item.current_episode, item.total_episodes)}
                    className="flex-1 lg:flex-none bg-gray-800 text-xs text-gray-300 px-2 lg:px-3 py-2 lg:py-1.5 rounded border border-gray-700 focus:outline-none focus:border-crorange"
                  >
                    <option value="Liked">Liked</option>
                    <option value="Disliked">Disliked</option>
                    <option value="Neutral">Neutral</option>
                  </select>
                </div>

                <button 
                  onClick={() => handleDelete(item.name)}
                  className="text-gray-500 hover:text-red-500 transition-colors px-2 font-bold text-xl lg:text-base ml-auto lg:ml-0"
                  title="Remove from history"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}