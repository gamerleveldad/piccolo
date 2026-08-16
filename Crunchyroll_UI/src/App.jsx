import { useEffect, useState } from "react";

// --- SUB-COMPONENT: Manages local state so changes pend until "Save" is clicked ---
function HistoryRow({ item, onSave, onDelete }) {
  const [current, setCurrent] = useState(item.current_episode || 0);
  const [total, setTotal] = useState(item.total_episodes || 0);
  const [status, setStatus] = useState(item.status);
  const [rating, setRating] = useState(item.rating);

  // Re-sync if backend data changes
  useEffect(() => {
    setCurrent(item.current_episode || 0);
    setTotal(item.total_episodes || 0);
    setStatus(item.status);
    setRating(item.rating);
  }, [item]);

  const hasChanges =
    current !== (item.current_episode || 0) ||
    total !== (item.total_episodes || 0) ||
    status !== item.status ||
    rating !== item.rating;

  // Logic Constraints
  const adjustCurrent = (delta) => {
    const newVal = Math.max(0, current + delta);
    setCurrent(newVal);
    if (newVal > total) setTotal(newVal);
  };

  const adjustTotal = (delta) => {
    const newVal = Math.max(0, total + delta);
    setTotal(newVal);
    if (newVal < current) setCurrent(newVal);
  };

  return (
    <div
      className={`flex flex-col lg:flex-row items-start lg:items-center justify-between p-4 rounded border transition-all gap-4 ${hasChanges ? "bg-[#1a1a2e] border-crviolet shadow-[0_0_8px_rgba(139,92,246,0.2)]" : "bg-crbase border-gray-800 hover:border-gray-600"}`}
    >
      <span className="font-bold text-crsilver flex-1 w-full lg:w-auto text-lg lg:text-base break-words">
        {item.name}
      </span>

      <div className="flex flex-col md:flex-row flex-wrap lg:flex-nowrap gap-3 items-start md:items-center w-full lg:w-auto justify-between lg:justify-end">
        {/* +/- Episode Controls */}
        <div className="flex gap-4 items-center bg-gray-900 px-3 py-1.5 rounded border border-gray-800 w-full md:w-auto justify-center">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 w-6">Ep</span>
            <button
              onClick={() => adjustCurrent(-1)}
              className="bg-crpanel text-crsilver hover:bg-crpurple px-2 rounded font-bold"
            >
              -
            </button>
            <span className="w-6 text-center font-bold text-crviolet">
              {current}
            </span>
            <button
              onClick={() => adjustCurrent(1)}
              className="bg-crpanel text-crsilver hover:bg-crpurple px-2 rounded font-bold"
            >
              +
            </button>
          </div>
          <span className="text-gray-600">/</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 w-6">Tot</span>
            <button
              onClick={() => adjustTotal(-1)}
              className="bg-crpanel text-crsilver hover:bg-crpurple px-2 rounded font-bold"
            >
              -
            </button>
            <span className="w-6 text-center text-gray-300">{total}</span>
            <button
              onClick={() => adjustTotal(1)}
              className="bg-crpanel text-crsilver hover:bg-crpurple px-2 rounded font-bold"
            >
              +
            </button>
          </div>
        </div>

        {/* Status & Rating Dropdowns */}
        <div className="flex gap-2 w-full md:w-auto">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="flex-1 md:flex-none bg-gray-900 text-xs text-crsilver px-2 py-2 rounded border border-gray-800 focus:outline-none focus:border-crviolet"
          >
            <option value="Watching">Watching</option>
            <option value="Pending">Pending</option>
            <option value="Dormant">Dormant</option>
            <option value="Completed">Completed</option>
            <option value="Dropped">Dropped</option>
          </select>
          <select
            value={rating}
            onChange={(e) => setRating(e.target.value)}
            className="flex-1 md:flex-none bg-gray-900 text-xs text-crsilver px-2 py-2 rounded border border-gray-800 focus:outline-none focus:border-crpurple"
          >
            <option value="Liked">Liked</option>
            <option value="Disliked">Disliked</option>
            <option value="Neutral">Neutral</option>
          </select>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2 w-full md:w-auto justify-end">
          {hasChanges && (
            <button
              onClick={() => onSave(item.name, status, rating, current, total)}
              className="bg-crviolet hover:bg-crpurple text-white text-xs px-4 py-2 rounded font-bold transition-colors animate-pulse"
            >
              SAVE
            </button>
          )}
          <button
            onClick={() => onDelete(item.name)}
            className="text-gray-600 hover:text-red-500 transition-colors px-2 font-bold text-xl lg:text-base"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}

// --- MAIN APPLICATION ---
export default function App() {
  const [schedule, setSchedule] = useState([]);
  const [history, setHistory] = useState([]);
  const [filter, setFilter] = useState("All"); // Status Filter

  const [newName, setNewName] = useState("");
  const [newStatus, setNewStatus] = useState("Watching");

  const jsDay = new Date().getDay();
  const currentDayIndex = jsDay === 0 ? 6 : jsDay - 1;
  const daysOfWeek = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
  ];
  const API_BASE = import.meta.env.VITE_API_BASE_URL;

  const fetchData = () => {
    fetch(`${API_BASE}/api/schedule`)
      .then((res) => res.json())
      .then(setSchedule)
      .catch(console.error);
    fetch(`${API_BASE}/api/history`)
      .then((res) => res.json())
      .then(setHistory)
      .catch(console.error);
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;
    await fetch(`${API_BASE}/api/history`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        anime_name: newName,
        status: newStatus,
        user_rating: "Neutral",
        current_episode: 0,
        total_episodes: 0,
      }),
    });
    setNewName("");
    fetchData();
  };

  const handleUpdate = async (
    anime_name,
    status,
    user_rating,
    current_episode,
    total_episodes,
  ) => {
    await fetch(`${API_BASE}/api/history/${encodeURIComponent(anime_name)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status,
        user_rating,
        current_episode,
        total_episodes,
      }),
    });
    fetchData();
  };

  const handleDelete = async (anime_name) => {
    if (!window.confirm(`Are you sure you want to delete ${anime_name}?`))
      return;
    await fetch(`${API_BASE}/api/history/${encodeURIComponent(anime_name)}`, {
      method: "DELETE",
    });
    fetchData();
  };

  const filteredHistory = history.filter(
    (item) => filter === "All" || item.status === filter,
  );

  return (
    <div className="min-h-screen bg-crbase text-gray-100 p-4 lg:p-8 font-sans overflow-x-hidden">
      <header className="mb-8 lg:mb-12 border-b border-crpurple/30 pb-4">
        <h1 className="text-3xl lg:text-4xl font-bold tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-crviolet to-crsilver">
          TRACKER WIDGET
        </h1>
      </header>

      {/* --- ACTIVE PROGRESS WIDGET --- */}
      {history.filter((item) => item.status === "Watching").length > 0 && (
        <div className="bg-crpanel p-4 lg:p-6 rounded-lg border border-gray-800 shadow-xl mb-12">
          <h2 className="text-xl lg:text-2xl font-bold text-crsilver mb-6 border-b border-gray-800 pb-2">
            Active Watch Progress
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {history
              .filter((item) => item.status === "Watching")
              .map((item) => {
                const current = item.current_episode || 0;
                const total = item.total_episodes || 0;
                const percent =
                  total > 0
                    ? Math.min(Math.round((current / total) * 100), 100)
                    : 0;

                // Emphasize shows with pending unwatched episodes
                const isBehind = current < total && total > 0;
                const cardHighlight = isBehind
                  ? "border-crviolet shadow-[0_0_12px_rgba(139,92,246,0.15)] bg-[#131320]"
                  : "border-gray-800 bg-crbase";

                return (
                  <div
                    key={item.name}
                    className={`p-4 rounded border transition-colors relative ${cardHighlight}`}
                  >
                    {isBehind && (
                      <span className="absolute -top-2 -right-2 bg-crviolet text-white text-[10px] font-bold px-2 py-0.5 rounded-full">
                        NEW EP
                      </span>
                    )}
                    <div className="flex justify-between items-end mb-2">
                      <span
                        className={`font-bold truncate pr-2 ${isBehind ? "text-white" : "text-gray-300"}`}
                      >
                        {item.name}
                      </span>
                      <span className="text-xs font-mono text-crsilver whitespace-nowrap">
                        {current} / {total > 0 ? total : "?"}
                      </span>
                    </div>
                    <div className="w-full bg-gray-900 rounded-full h-2 mt-2 border border-gray-800">
                      <div
                        className="bg-gradient-to-r from-crpurple to-crviolet h-2 rounded-full transition-all"
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
        <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-6 border-b border-gray-800 pb-4 gap-4">
          <h2 className="text-xl lg:text-2xl font-bold text-crsilver">
            Watch History Roster
          </h2>

          {/* Status Filter Tabs */}
          <div className="flex flex-wrap gap-2 bg-crbase p-1 rounded border border-gray-800">
            {[
              "All",
              "Watching",
              "Pending",
              "Dormant",
              "Completed",
              "Dropped",
            ].map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`text-xs px-3 py-1.5 rounded font-bold transition-colors ${filter === f ? "bg-crpurple text-white" : "text-gray-500 hover:text-crsilver"}`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        {/* Add New Show Form */}
        <form
          onSubmit={handleAdd}
          className="flex flex-col md:flex-row gap-3 mb-8 bg-crbase p-4 rounded-lg border border-gray-800"
        >
          <input
            type="text"
            placeholder="Add Anime Title..."
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="flex-1 bg-gray-900 text-crsilver px-4 py-2 rounded focus:outline-none border border-gray-800 focus:border-crpurple"
          />
          <select
            value={newStatus}
            onChange={(e) => setNewStatus(e.target.value)}
            className="bg-gray-900 text-crsilver px-4 py-2 rounded border border-gray-800 focus:outline-none focus:border-crpurple"
          >
            <option value="Watching">Watching</option>
            <option value="Pending">Pending</option>
            <option value="Dormant">Dormant</option>
          </select>
          <button
            type="submit"
            className="bg-gradient-to-r from-crpurple to-crviolet text-white px-6 py-2 rounded font-bold"
          >
            Add Title
          </button>
        </form>

        {/* History List */}
        <div className="space-y-3 max-h-[700px] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-crpurple scrollbar-track-crbase">
          {filteredHistory.map((item) => (
            <HistoryRow
              key={item.name}
              item={item}
              onSave={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
          {filteredHistory.length === 0 && (
            <div className="text-center text-gray-600 py-8 italic">
              No entries found for this filter.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
