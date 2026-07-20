import { useEffect, useState } from 'react';

export default function App() {
  const [schedule, setSchedule] = useState([]);
  const [history, setHistory] = useState([]);
  
  // State for the "Add New Show" form
  const [newName, setNewName] = useState('');
  const [newStatus, setNewStatus] = useState('Watching');
  const [newRating, setNewRating] = useState('Liked');

  const currentDayIndex = new Date().getDay();
  const daysOfWeek = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
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
      body: JSON.stringify({ anime_name: newName, status: newStatus, user_rating: newRating })
    });
    setNewName('');
    fetchData();
  };

  const handleUpdate = async (anime_name, status, user_rating) => {
    await fetch(`${API_BASE}/api/history/${encodeURIComponent(anime_name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, user_rating })
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
    <div className="min-h-screen bg-crbase text-gray-100 p-8 font-sans">
      
      <header className="mb-12 border-b border-craqua/30 pb-4">
        <h1 className="text-4xl font-bold tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-craqua to-crorange">
          TRACKER WIDGET
        </h1>
        <p className="text-sm text-gray-400 uppercase tracking-widest mt-1">Active Season Matrix</p>
      </header>

      {/* --- SCHEDULE CALENDAR --- */}
      <div className="grid grid-cols-7 gap-4 mb-16">
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
                  <div key={show.name} className="bg-gray-800/50 p-2 rounded text-xs border border-gray-700/50">
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

      {/* --- WATCH HISTORY MANAGEMENT --- */}
      <div className="bg-crpanel p-6 rounded-lg border border-gray-800 shadow-xl">
        <h2 className="text-2xl font-bold text-craqua mb-6 border-b border-gray-700 pb-2">Watch History Roster</h2>
        
        {/* Add New Show Form */}
        <form onSubmit={handleAdd} className="flex gap-4 mb-8 bg-crbase p-4 rounded-lg border border-gray-700">
          <input 
            type="text" 
            placeholder="Anime Title..." 
            value={newName} 
            onChange={e => setNewName(e.target.value)}
            className="flex-1 bg-gray-800 text-white px-4 py-2 rounded focus:outline-none focus:ring-1 focus:ring-craqua border border-gray-700"
          />
          <select value={newStatus} onChange={e => setNewStatus(e.target.value)} className="bg-gray-800 text-white px-4 py-2 rounded border border-gray-700 focus:outline-none focus:ring-1 focus:ring-craqua">
            <option value="Watching">Watching</option>
            <option value="Dormant">Dormant</option>
            <option value="Completed">Completed</option>
            <option value="Dropped">Dropped</option>
          </select>
          <select value={newRating} onChange={e => setNewRating(e.target.value)} className="bg-gray-800 text-white px-4 py-2 rounded border border-gray-700 focus:outline-none focus:ring-1 focus:ring-craqua">
            <option value="Liked">Liked</option>
            <option value="Disliked">Disliked</option>
            <option value="Neutral">Neutral</option>
          </select>
          <button type="submit" className="bg-gradient-to-r from-craqua to-cyan-600 hover:to-cyan-500 text-white px-6 py-2 rounded font-bold transition-all">
            Add Title
          </button>
        </form>

        {/* History List */}
        <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
          {history.map(item => (
            <div key={item.name} className="flex items-center justify-between bg-crbase p-3 rounded border border-gray-800 hover:border-gray-600 transition-colors">
              <span className="font-semibold text-gray-200 flex-1">{item.name}</span>
              
              <div className="flex gap-3 items-center">
                <select 
                  value={item.status} 
                  onChange={(e) => handleUpdate(item.name, e.target.value, item.rating)}
                  className="bg-gray-800 text-xs text-gray-300 px-3 py-1.5 rounded border border-gray-700 focus:outline-none focus:border-craqua"
                >
                  <option value="Watching">Watching</option>
                  <option value="Dormant">Dormant</option>
                  <option value="Completed">Completed</option>
                  <option value="Dropped">Dropped</option>
                </select>

                <select 
                  value={item.rating} 
                  onChange={(e) => handleUpdate(item.name, item.status, e.target.value)}
                  className="bg-gray-800 text-xs text-gray-300 px-3 py-1.5 rounded border border-gray-700 focus:outline-none focus:border-crorange"
                >
                  <option value="Liked">Liked</option>
                  <option value="Disliked">Disliked</option>
                  <option value="Neutral">Neutral</option>
                </select>

                <button 
                  onClick={() => handleDelete(item.name)}
                  className="text-gray-500 hover:text-red-500 transition-colors px-2 font-bold"
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