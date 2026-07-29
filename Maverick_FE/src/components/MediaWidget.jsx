import { useState, useEffect } from 'react';
import { Tv, Gamepad2, Calendar } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const CircularProgress = ({ current, total }) => {
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const isOngoing = total === 0;
  
  const percent = isOngoing ? 100 : Math.min((current / total) * 100, 100);
  const strokeDashoffset = circumference - (percent / 100) * circumference;
  const isCaughtUp = !isOngoing && current >= total;

  return (
    <div className="relative flex items-center justify-center w-10 h-10 group-hover:scale-110 transition-transform">
      <svg className="w-full h-full -rotate-90">
        <circle cx="20" cy="20" r={radius} stroke="currentColor" strokeWidth="2.5" fill="none" className="text-slate-800" />
        <circle
          cx="20" cy="20" r={radius}
          stroke="currentColor" strokeWidth="2.5" fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          className={`${
            isCaughtUp ? 'text-green-500' : isOngoing ? 'text-slate-500' : 'text-accentBlue'
          } transition-all duration-1000 ease-out`}
        />
      </svg>
      <span className="absolute text-[9px] font-bold text-slate-300">
        {isOngoing ? '?' : `${Math.round(percent)}%`}
      </span>
    </div>
  );
};

export default function MediaWidget() {
  const [animeList, setAnimeList] = useState([]);
  const [animeLoading, setAnimeLoading] = useState(true);
  const [animeError, setAnimeError] = useState(null);

  const [gameList, setGameList] = useState([]);
  const [gamesLoading, setGamesLoading] = useState(true);
  const [gamesError, setGamesError] = useState(null);
  const [hasUpcomingGame, setHasUpcomingGame] = useState(false);

  const host = window.location.hostname;
  const ANIME_API_URL = `http://${host}:8002/api/active-shows`;
  const GAMES_API_URL = `http://${host}:8001/games/upcoming`;

  // Fetch Anime Queue
  useEffect(() => {
    const fetchAnime = async () => {
      try {
        const res = await fetch(ANIME_API_URL);
        if (!res.ok) throw new Error(`API Error: ${res.status}`);
        const data = await res.json();
        
        if (Array.isArray(data)) setAnimeList(data);
        else if (data && Array.isArray(data.data)) setAnimeList(data.data);
        else throw new Error("API did not return a valid array");
      } catch (err) {
        setAnimeError(err.message);
      } finally {
        setAnimeLoading(false);
      }
    };
    fetchAnime();
  }, [ANIME_API_URL]);

  // Fetch Game Tracker
  useEffect(() => {
    const fetchGames = async () => {
      try {
        const res = await fetch(GAMES_API_URL);
        if (!res.ok) throw new Error(`API Error: ${res.status}`);
        let data = await res.json();
        
        // Extract array if wrapped
        if (!Array.isArray(data) && data && Array.isArray(data.data)) {
          data = data.data;
        } else if (!Array.isArray(data)) {
          throw new Error("API did not return a valid array");
        }

        // Sort by closest release date first
        data.sort((a, b) => new Date(a.release_date) - new Date(b.release_date));
        setGameList(data);

        // Check if any game releases within the next 7 days
        // Strip the time component so we only compare the calendar days
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        const nextWeek = new Date(today);
        nextWeek.setDate(today.getDate() + 7);

        const releasingSoon = data.some(game => {
          if (!game.release_date) return false;
          const releaseDate = new Date(game.release_date);
          releaseDate.setHours(0, 0, 0, 0); // Strip time from database date
          
          return releaseDate >= today && releaseDate <= nextWeek;
        });

        setHasUpcomingGame(releasingSoon);
      } catch (err) {
        setGamesError(err.message);
      } finally {
        setGamesLoading(false);
      }
    };
    fetchGames();
  }, [GAMES_API_URL]);

  const formatDate = (dateStr) => {
    if (!dateStr) return 'TBA';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg p-5 flex-1 flex flex-col h-full min-h-[400px]">
      <Tabs defaultValue="anime" className="w-full h-full flex flex-col">
        
        <TabsList className="grid w-full grid-cols-2 bg-[#0d1320] text-slate-400 border border-borderSlate mb-4">
          <TabsTrigger value="anime" className="data-[state=active]:bg-[#161f33] data-[state=active]:text-accentBlue">
            <Tv className="w-4 h-4 mr-2" />
            Anime Queue
          </TabsTrigger>
          <TabsTrigger value="games" className="data-[state=active]:bg-[#161f33] data-[state=active]:text-purple-400">
            {/* Pulsing purple icon if a game drops this week */}
            <Gamepad2 className={`w-4 h-4 mr-2 ${hasUpcomingGame ? 'text-purple-400 animate-pulse' : ''}`} />
            Game Tracker
          </TabsTrigger>
        </TabsList>

        <TabsContent value="anime" className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
          {animeLoading ? (
            <div className="flex justify-center items-center h-32">
               <p className="text-sm text-slate-500 animate-pulse">Loading queue...</p>
            </div>
          ) : animeError ? (
            <div className="bg-red-900/20 border border-red-900/50 p-3 rounded text-sm text-red-400">{animeError}</div>
          ) : (
            <div className="flex flex-col gap-3">
              {animeList.map((anime, index) => (
                <div key={index} className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex justify-between items-center group">
                  <div className="flex flex-col">
                    <span className="font-medium text-slate-200">{anime.name}</span>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded-full">
                        Ep. {anime.current_episode} {anime.total_episodes > 0 ? `/ ${anime.total_episodes}` : ''}
                      </span>
                    </div>
                  </div>
                  <CircularProgress current={anime.current_episode} total={anime.total_episodes} />
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="games" className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
          {gamesLoading ? (
             <div className="flex justify-center items-center h-32">
                 <p className="text-sm text-slate-500 animate-pulse">Loading tracker...</p>
              </div>
          ) : gamesError ? (
             <div className="bg-red-900/20 border border-red-900/50 p-3 rounded text-sm text-red-400">{gamesError}</div>
          ) : gameList.length === 0 ? (
              <div className="flex justify-center items-center h-32">
                  <p className="text-sm text-slate-500">No games forecasted within 7 days</p>
              </div>
          ) : (
             <div className="flex flex-col gap-3">
              {gameList.map((game, index) => (
                <div key={index} className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex justify-between items-center">
                  <div className="flex flex-col">
                    <span className="font-medium text-slate-200">{game.title}</span>
                    <span className="text-xs text-accentPurple flex items-center gap-1 mt-1">
                      <Calendar className="w-3 h-3" /> {formatDate(game.release_date)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
        
      </Tabs>
    </div>
  );
}