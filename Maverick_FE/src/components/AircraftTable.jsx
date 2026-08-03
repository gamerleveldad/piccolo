import { useState, useEffect } from 'react';
import { Plane, X } from 'lucide-react';

export default function AircraftTable() {
  const [aircraft, setAircraft] = useState([]);
  const [selectedRawData, setSelectedRawData] = useState(null);

  useEffect(() => {
    const fetchTableData = async () => {
      try {
        const res = await fetch(`http://${window.location.hostname}:8085/data/aircraft.json`);
        if (!res.ok) return;
        const data = await res.json();
        
        // Filter out records that are empty or just ground stations
        const validAircraft = (data.aircraft || []).filter(ac => ac.hex && ac.hex.indexOf('~') === -1);
        
        // Sort by altitude descending (optional, just makes the table look organized)
        validAircraft.sort((a, b) => (b.alt_baro || 0) - (a.alt_baro || 0));
        
        setAircraft(validAircraft);
      } catch (err) {
        console.warn("Aircraft table fetch error:", err);
      }
    };

    fetchTableData();
    const interval = setInterval(fetchTableData, 1000); // 1-second poll to match map speed
    return () => clearInterval(interval);
  }, []);

  // Helper to extract the 3-letter airline code for the SVG logo
  const getAirlineCode = (flight) => {
    if (!flight) return null;
    const trimmed = flight.trim();
    // Most commercial callsigns start with 3 letters
    if (/^[A-Z]{3}/.test(trimmed)) {
      return trimmed.substring(0, 3);
    }
    return null;
  };

  return (
    <div className="bg-[#162032] border border-slate-700/50 rounded-lg p-4 mt-6 shadow-lg flex flex-col h-96">
      <div className="flex items-center gap-2 mb-4 shrink-0">
        <Plane className="text-accentBlue w-5 h-5" />
        <h2 className="text-lg font-semibold text-textSilver">Local Traffic (Raw Feed)</h2>
        <span className="ml-auto text-xs font-bold bg-slate-800 text-slate-400 px-2 py-1 rounded">
          {aircraft.length} Aircraft
        </span>
      </div>

      <div className="overflow-auto flex-1 border border-slate-800 rounded">
        <table className="w-full text-left text-sm text-slate-300">
          <thead className="text-xs text-slate-400 bg-slate-800/80 sticky top-0 uppercase z-10 shadow-sm">
            <tr>
              <th className="px-4 py-3 font-semibold">Airline</th>
              <th className="px-4 py-3 font-semibold">Callsign</th>
              <th className="px-4 py-3 font-semibold">Reg (N-Num)</th>
              <th className="px-4 py-3 font-semibold">Type</th>
              <th className="px-4 py-3 font-semibold">Altitude</th>
              <th className="px-4 py-3 font-semibold">Lat / Lon</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {aircraft.map((ac) => {
              const airlineCode = getAirlineCode(ac.flight);
              return (
                <tr 
                  key={ac.hex} 
                  onClick={() => setSelectedRawData(ac)}
                  className="hover:bg-slate-700/30 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-2 w-16">
                    {airlineCode ? (
                      <img 
                        src={`/tails/${airlineCode}.svg`} 
                        alt={airlineCode}
                        className="h-6 w-auto object-contain bg-slate-100 rounded px-1"
                        onError={(e) => e.target.style.display = 'none'}
                      />
                    ) : (
                      <span className="text-slate-600 text-xs">N/A</span>
                    )}
                  </td>
                  <td className="px-4 py-2 font-bold text-slate-200">{ac.flight?.trim() || '---'}</td>
                  <td className="px-4 py-2">{ac.r || '---'}</td>
                  <td className="px-4 py-2 text-amber-400">{ac.t || '---'}</td>
                  <td className="px-4 py-2">
                    {ac.alt_baro !== undefined ? (ac.alt_baro === 'ground' ? 'GND' : `${ac.alt_baro} ft`) : '---'}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-slate-400">
                    {ac.lat && ac.lon ? `${ac.lat.toFixed(4)}, ${ac.lon.toFixed(4)}` : 'Hidden'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* RAW DATA MODAL (Standard Box style, not slanted) */}
      {selectedRawData && (
        <div className="fixed inset-0 z-[9999] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#162032] border border-slate-600 rounded-lg shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-slate-700 bg-slate-800/50 rounded-t-lg">
              <h3 className="font-bold text-slate-200">
                Raw JSON: {selectedRawData.flight?.trim() || selectedRawData.hex}
              </h3>
              <button 
                onClick={() => setSelectedRawData(null)}
                className="p-1 hover:bg-slate-700 rounded text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 overflow-auto">
              <pre className="text-xs text-green-400 font-mono bg-black/50 p-4 rounded border border-slate-800">
                {JSON.stringify(selectedRawData, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}