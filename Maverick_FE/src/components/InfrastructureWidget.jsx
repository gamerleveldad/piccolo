import { useState, useEffect } from 'react';
import { Activity, Cpu, Server, HardDrive, Clock } from 'lucide-react';

export default function InfrastructureWidget() {
  const [netdata, setNetdata] = useState({ cpu: '--', ram: '--', disk: '--', uptime: '--' });
  const [error, setError] = useState(null);

  const host = window.location.hostname;
  const NETDATA_API_BASE = `http://${host}:19999/api/v1/data`;

  useEffect(() => {
    const fetchNetdata = async () => {
      try {
        // HELPER FUNCTION: The Secret Sauce
        // By adding '&after=-10&group=average', we give Netdata a 10-second lookback window.
        // This guarantees it will find a data point instead of returning an empty array.
        const fetchMetric = async (chart) => {
          const url = `${NETDATA_API_BASE}?chart=${chart}&format=json&points=1&after=-10&group=average`;
          const res = await fetch(url);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return await res.json();
        };

        // 1. Fetch System CPU (Sums all active non-idle CPU states)
        let cpuUsage = 0;
        try {
          const cpuData = await fetchMetric('system.cpu');
          if (cpuData.data && cpuData.data.length > 0) {
            // Slice off index 0 (timestamp) and sum up all active CPU state percentages
            const activeValues = cpuData.data[0].slice(1);
            cpuUsage = activeValues.reduce((sum, val) => sum + (val || 0), 0);
          }
        } catch (e) { console.warn("CPU fetch error:", e); }

        // 2. Fetch RAM
        let ramUsage = 0;
        try {
          const ramData = await fetchMetric('system.ram');
          const freeIndex = ramData.labels.indexOf('free');
          const usedIndex = ramData.labels.indexOf('used');
          const cachedIndex = ramData.labels.indexOf('cached');
          const buffersIndex = ramData.labels.indexOf('buffers');
          
          if (usedIndex !== -1 && ramData.data && ramData.data.length > 0) {
            const free = ramData.data[0][freeIndex] || 0;
            const used = ramData.data[0][usedIndex] || 0;
            const cached = (cachedIndex !== -1 ? ramData.data[0][cachedIndex] : 0);
            const buffers = (buffersIndex !== -1 ? ramData.data[0][buffersIndex] : 0);
            
            const totalRam = free + used + cached + buffers;
            if (totalRam > 0) ramUsage = (used / totalRam) * 100;
          }
        } catch (e) { console.warn("RAM fetch error:", e); }

        // 3. Fetch Root Disk Space (Using disk_space.*)
        let diskUsage = 0;
        try {
          const diskData = await fetchMetric('disk_space.*');
          const availIdx = diskData.labels.indexOf('avail');
          const usedIdx = diskData.labels.indexOf('used');
          const reservedIdx = diskData.labels.indexOf('reserved for root');

          if (availIdx !== -1 && usedIdx !== -1 && diskData.data && diskData.data.length > 0) {
            const avail = diskData.data[0][availIdx] || 0;
            const diskUsed = diskData.data[0][usedIdx] || 0;
            const reserved = (reservedIdx !== -1 ? diskData.data[0][reservedIdx] : 0);
            
            const totalDisk = avail + diskUsed + reserved;
            if (totalDisk > 0) diskUsage = (diskUsed / totalDisk) * 100;
          }
        } catch (e) { console.warn("Disk space fetch error:", e); }

        // 4. Fetch System Uptime
        let formattedUptime = '--';
        try {
          const upData = await fetchMetric('system.uptime');
          if (upData.data && upData.data.length > 0) {
            const seconds = upData.data[0][1]; // In the uptime chart, index 1 is usually the value
            const days = Math.floor(seconds / (3600 * 24));
            const hours = Math.floor((seconds % (3600 * 24)) / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            formattedUptime = `${days}d ${hours}h ${minutes}m`;
          }
        } catch (e) { console.warn("Uptime fetch error:", e); }

        // Update State (will gracefully fallback to '--' if a metric failed)
        setNetdata({
          cpu: cpuUsage > 0 ? cpuUsage.toFixed(1) : '--',
          ram: ramUsage > 0 ? ramUsage.toFixed(1) : '--',
          disk: diskUsage > 0 ? diskUsage.toFixed(1) : '--',
          uptime: formattedUptime
        });
        setError(null);

      } catch (err) {
        console.error("Netdata global fetch error:", err);
        setError("Netdata unreachable. Check if port 19999 is exposed.");
      }
    };

    // Run immediately, then poll every 10 seconds
    fetchNetdata();
    const interval = setInterval(fetchNetdata, 10000);
    return () => clearInterval(interval);
  }, [NETDATA_API_BASE]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 mb-5">
        <Activity className="text-accentBlue w-5 h-5" />
        <h2 className="text-lg font-semibold text-textSilver">Infrastructure</h2>
      </div>

      {error ? (
        <div className="text-xs text-red-400 mb-3 bg-red-900/20 p-2 rounded border border-red-900/50">
          {error}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 flex-1">
          {/* CPU Tile */}
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 flex flex-col items-center justify-center shadow-inner">
            <Cpu className="w-5 h-5 text-slate-400 mb-1.5" />
            <span className="text-xs text-slate-500 font-bold uppercase tracking-wider mb-1">CPU Load</span>
            <span className="text-xl font-bold text-sky-400">{netdata.cpu}%</span>
          </div>

          {/* RAM Tile */}
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 flex flex-col items-center justify-center shadow-inner">
            <Server className="w-5 h-5 text-slate-400 mb-1.5" />
            <span className="text-xs text-slate-500 font-bold uppercase tracking-wider mb-1">RAM Usage</span>
            <span className="text-xl font-bold text-emerald-400">{netdata.ram}%</span>
          </div>

          {/* Disk Tile */}
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 flex flex-col items-center justify-center shadow-inner">
            <HardDrive className="w-5 h-5 text-slate-400 mb-1.5" />
            <span className="text-xs text-slate-500 font-bold uppercase tracking-wider mb-1">Disk Used</span>
            <span className="text-xl font-bold text-amber-400">{netdata.disk}%</span>
          </div>

          {/* Uptime Tile */}
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 flex flex-col items-center justify-center shadow-inner">
            <Clock className="w-5 h-5 text-slate-400 mb-1.5" />
            <span className="text-xs text-slate-500 font-bold uppercase tracking-wider mb-1">Uptime</span>
            <span className="text-lg font-bold text-slate-200 text-center leading-none">{netdata.uptime}</span>
          </div>
        </div>
      )}
    </div>
  );
}