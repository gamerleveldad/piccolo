import { useState, useEffect } from 'react';
import { Tv, Gamepad2, CheckCircle2 } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

export default function MediaWidget() {
  const [animeList, setAnimeList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Use the host IP to ensure the browser routes to the Pi, matching port 8000
  const host = window.location.hostname;
  const ANIME_API_URL = `http://${host}:8000/api/active-shows`;

  useEffect(() => {
    const fetchAnime = async () => {
      try {
        const res = await fetch(ANIME_API_URL);
        if (!res.ok) throw new Error(`API Error: ${res.status}`);

        const data = await res.json();
        setAnimeList(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchAnime();
  }, [ANIME_API_URL]);

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl shadow-lg p-5 flex-1 flex flex-col h-full min-h-[400px]">
      <Tabs defaultValue="anime" className="w-full h-full flex flex-col">
        
        {/* Tab Headers */}
        <TabsList className="grid w-full grid-cols-2 bg-[#0d1320] text-slate-400 border border-borderSlate mb-4">
          <TabsTrigger value="anime" className="data-[state=active]:bg-[#161f33] data-[state=active]:text-accentBlue">
            <Tv className="w-4 h-4 mr-2" />
            Anime Queue
          </TabsTrigger>
          <TabsTrigger value="games" className="data-[state=active]:bg-[#161f33] data-[state=active]:text-accentPurple">
            <Gamepad2 className="w-4 h-4 mr-2" />
            Game Backlog
          </TabsTrigger>
        </TabsList>

        {/* Anime Content Pane */}
        <TabsContent value="anime" className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
          {loading ? (
            <div className="flex justify-center items-center h-32">
               <p className="text-sm text-slate-500 animate-pulse">Loading queue...</p>
            </div>
          ) : error ? (
            <div className="bg-red-900/20 border border-red-900/50 p-3 rounded text-sm text-red-400">
              {error}
            </div>
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
                  {/* Action button ready to be wired to a POST/PUT request to update your DB */}
                  <button className="text-slate-600 hover:text-green-500 transition-colors p-2" title="Mark Next Episode Watched">
                    <CheckCircle2 className="w-5 h-5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Games Content Pane */}
        <TabsContent value="games" className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
           <div className="flex justify-center items-center h-32">
               <p className="text-sm text-slate-500 animate-pulse">Awaiting Game API implementation...</p>
            </div>
        </TabsContent>
        
      </Tabs>
    </div>
  );
}