import { useState, useEffect } from 'react';

function App() {
  const [games, setGames] = useState([]);
  const [newGameTitle, setNewGameTitle] = useState('');
  const [newGamePlatform, setNewGamePlatform] = useState('PC');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const fetchGames = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8000/games');
      const data = await response.json();
      setGames(data);
    } catch (error) {
      console.error("Error fetching games:", error);
    }
  };

  useEffect(() => {
    fetchGames();
  }, []);

  const handleAddGame = async (e) => {
    e.preventDefault();
    setLoading(true);
    setMessage('ESTABLISHING UPLINK TO RAWG DATABANKS...');

    try {
      const response = await fetch('http://127.0.0.1:8000/games/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newGameTitle, platform: newGamePlatform }),
      });

      const data = await response.json();
      setMessage(data.message || 'TRACKING ESTABLISHED.');
      setNewGameTitle('');
      fetchGames();
    } catch (error) {
      setMessage('SYSTEM ERROR. CONNECTION TERMINATED.');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteGame = async (id, title) => {
    if (!window.confirm(`WARNING: Terminate tracking protocol for ${title}?`)) return;
    
    try {
      await fetch(`http://127.0.0.1:8000/games/${id}`, {
        method: 'DELETE',
      });
      fetchGames();
      setMessage(`TARGET TERMINATED: ${title}`);
    } catch (error) {
      console.error("Error deleting game:", error);
    }
  };

  return (
    <div className="min-h-screen bg-black text-cyan-400 font-mono relative overflow-hidden selection:bg-cyan-900">
      {/* Background Tron Grid Effect */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(0,255,255,0.07)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,255,0.07)_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none z-0"></div>
      
      {/* Radial Gradient to fade out the grid at the edges */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_20%,black_80%)] pointer-events-none z-0"></div>

      <div className="relative z-10 max-w-6xl mx-auto p-8 space-y-12">
        
        {/* Header Section */}
        <header className="border-b-2 border-cyan-500 pb-4 shadow-[0_4px_15px_rgba(0,255,255,0.2)]">
          <h1 className="text-5xl font-black uppercase tracking-[0.2em] text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 to-blue-600 drop-shadow-[0_0_15px_rgba(0,255,255,0.5)]">
            The Grid // Scanner
          </h1>
          <p className="text-cyan-600 mt-2 text-sm tracking-widest">SYSTEM VER_3.1.4 // NETWORK SECURE</p>
        </header>

        {/* Control Console (Add Game) */}
        <section className="bg-black/60 border border-cyan-800 p-8 backdrop-blur-sm relative group">
          {/* Decorative Corner Borders */}
          <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-cyan-400"></div>
          <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-cyan-400"></div>
          <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-cyan-400"></div>
          <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-cyan-400"></div>

          <h2 className="text-lg font-bold text-cyan-200 mb-6 uppercase tracking-[0.15em] flex items-center gap-2">
            <span className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse"></span>
            Initialize Target
          </h2>
          
          <form onSubmit={handleAddGame} className="flex flex-col md:flex-row gap-6 items-end">
            <div className="flex-grow">
              <label className="block text-xs text-cyan-700 mb-2 uppercase tracking-widest">Target Designation</label>
              <input 
                type="text" 
                value={newGameTitle}
                onChange={(e) => setNewGameTitle(e.target.value)}
                required
                className="w-full bg-cyan-950/20 border-b-2 border-cyan-800 text-cyan-300 px-4 py-3 focus:outline-none focus:border-cyan-400 focus:bg-cyan-900/30 transition-all uppercase placeholder-cyan-800/50"
                placeholder="INPUT TITLE..."
              />
            </div>
            
            <div className="w-full md:w-72">
              <label className="block text-xs text-cyan-700 mb-2 uppercase tracking-widest">Architecture</label>
              <select 
                value={newGamePlatform}
                onChange={(e) => setNewGamePlatform(e.target.value)}
                className="w-full bg-cyan-950/20 border-b-2 border-cyan-800 text-cyan-300 px-4 py-3 focus:outline-none focus:border-cyan-400 focus:bg-cyan-900/30 transition-all uppercase appearance-none"
              >
                <option className="bg-black text-cyan-300" value="PC">PC</option>
                <option className="bg-black text-cyan-300" value="Nintendo Switch">Nintendo Switch</option>
                <option className="bg-black text-cyan-300" value="Nintendo Switch 2">Nintendo Switch 2</option>
                <option className="bg-black text-cyan-300" value="PlayStation 5">PlayStation 5</option>
                <option className="bg-black text-cyan-300" value="Xbox Series X">Xbox Series X</option>
              </select>
            </div>
            
            <button 
              type="submit" 
              disabled={loading}
              className="w-full md:w-auto bg-cyan-500/10 border-2 border-cyan-500 text-cyan-400 hover:bg-cyan-500 hover:text-black px-10 py-3 font-bold uppercase tracking-[0.2em] disabled:opacity-50 transition-all hover:shadow-[0_0_20px_rgba(0,255,255,0.6)]"
            >
              {loading ? 'Executing...' : 'Execute'}
            </button>
          </form>
          
          {message && (
            <div className="mt-6 border-l-4 border-cyan-500 pl-4 bg-cyan-950/30 py-2 animate-pulse">
              <p className="text-sm text-cyan-300 tracking-widest uppercase">{message}</p>
            </div>
          )}
        </section>

        {/* Database Roster Table */}
        <section className="bg-black/60 border border-cyan-900 backdrop-blur-sm relative">
          <div className="p-4 border-b border-cyan-900 flex justify-between items-center bg-cyan-950/20">
            <h2 className="text-sm font-bold text-cyan-500 uppercase tracking-widest">Active Data Stream</h2>
            <span className="text-xs text-cyan-700">{games.length} RECORDS FOUND</span>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-cyan-950/40 text-xs text-cyan-600 uppercase tracking-widest">
                  <th className="px-6 py-4 font-normal">Program Name</th>
                  <th className="px-6 py-4 font-normal">Network ID</th>
                  <th className="px-6 py-4 font-normal">Launch Cycle</th>
                  <th className="px-6 py-4 font-normal text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-cyan-900/50">
                {games.length === 0 ? (
                  <tr>
                    <td colSpan="4" className="px-6 py-12 text-center text-cyan-800 text-sm tracking-widest">
                      [ NO ACTIVE PROGRAMS DETECTED ]
                    </td>
                  </tr>
                ) : (
                  games.map((game) => (
                    <tr key={game.id} className="hover:bg-cyan-900/20 transition-colors group">
                      <td className="px-6 py-4 font-bold text-cyan-300 uppercase tracking-wider">
                        {game.title}
                      </td>
                      <td className="px-6 py-4 text-xs text-cyan-700">
                        {game.rawg_id === 'custom_search' ? '[OFF-GRID]' : game.rawg_id}
                      </td>
                      <td className="px-6 py-4 text-sm text-cyan-500">
                        {game.release_date || 'UNKNOWN_CYCLE'}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button 
                          onClick={() => handleDeleteGame(game.id, game.title)}
                          className="text-orange-500 border border-orange-500/50 hover:bg-orange-500 hover:text-black px-4 py-1 text-xs tracking-widest uppercase transition-all hover:shadow-[0_0_15px_rgba(249,115,22,0.6)] opacity-50 group-hover:opacity-100 rounded-sm"
                        >
                          Derez
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

      </div>
    </div>
  );
}

export default App;