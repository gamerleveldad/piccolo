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
        // 1. Fetch System CPU (Not just the Netdata container CPU)
        const cpuRes = await fetch(`${NETDATA_API_BASE}?chart=system.cpu&format=json&points=1`);
        const cpuData = await cpuRes.json();
        const idleIndex = cpuData.labels.indexOf('idle');
        const idleValue = cpuData.data[0][idleIndex];
        const cpuUsage = 100 - idleValue;

        // 2. Fetch RAM
        const ramRes = await fetch(`${NETDATA_API_BASE}?chart=system.ram&format=json&points=1`);
        const ramData = await ramRes.json();
        const freeIndex = ramData.labels.indexOf('free');
        const usedIndex = ramData.labels.indexOf('used');
        const cachedIndex = ramData.labels.indexOf('cached');
        const buffersIndex = ramData.labels.indexOf('buffers');
        
        const free = ramData.data[0][freeIndex] || 0;
        const used = ramData.data[0][usedIndex] || 0;
        const cached = ramData.data[0][cachedIndex] || 0;
        const buffers = ramData.data[0][buffersIndex] || 0;
        
        const totalRam = free + used + cached + buffers;
        const ramUsage = totalRam > 0 ? (used / totalRam) * 100 : 0;

        // 3. Fetch Root Disk Space
        let diskUsage = 0;
        try {
          const diskRes = await fetch(`${NETDATA_API_BASE}?chart=disk_space._&format=json&points=1`);
          if (diskRes.ok) {
            const diskData = await diskRes.json();
            const availIdx = diskData.labels.indexOf('avail');
            const usedIdx = diskData.labels.indexOf('used');
            const reservedIdx = diskData.labels.indexOf('reserved_for_root');

            const avail = diskData.data[0][availIdx] || 0;
            const diskUsed = diskData.data[0][usedIdx] || 0;
            const reserved = diskData.data[0][reservedIdx] || 0;

            const totalDisk = avail + diskUsed + reserved;
            if (totalDisk > 0) {
              diskUsage = (diskUsed / totalDisk) * 100;
            }
          }
        } catch (e) { console.warn("Disk space metric missing"); }

        // 4. Fetch System Uptime
        let formattedUptime = '--';
        try {
          const upRes = await fetch(`${NETDATA_API_BASE}?chart=system.uptime&format=json&points=1`);
          if (upRes.ok) {
            const upData = await upRes.json();
            const seconds = upData.data[0][1];
            
            const days = Math.floor(seconds / (3600 * 24));
            const hours = Math.floor((seconds % (3600 * 24)) / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            
            formattedUptime = `${days}d ${hours}h ${minutes}m`;
          }
        } catch (e) { console.warn("Uptime metric missing"); }

        // Update State
        setNetdata({
          cpu: cpuUsage.toFixed(1),
          ram: ramUsage.toFixed(1),
          disk: diskUsage > 0 ? diskUsage.toFixed(1) : '--',
          uptime: formattedUptime
        });
        setError(null);

      } catch (err) {
        console.error("Netdata fetch error:", err);
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