import { useState, useEffect } from 'react';
import { Activity, Server, Cpu, HardDrive, Thermometer } from 'lucide-react';

export default function InfrastructureWidget() {
  const [monitors, setMonitors] = useState([]);
  const [netdata, setNetdata] = useState({ cpu: 0, ram: 0, temp: 0 });
  const [error, setError] = useState(null);

  const host = window.location.hostname;
  const KUMA_METRICS_URL = `http://${host}:3001/metrics`;
  const KUMA_TOKEN = import.meta.env.VITE_KUMA_API_KEY || 'your_api_key_here';
  const NETDATA_API_BASE = `http://${host}:19999/api/v1/data`;

  useEffect(() => {
    // --- UPTIME KUMA POLLING ---
    const fetchKuma = async () => {
      try {
        const res = await fetch(KUMA_METRICS_URL, {
          headers: {
            'Authorization': `Bearer ${KUMA_TOKEN}`
          }
        });
        if (!res.ok) throw new Error("Kuma Metrics unreachable");
        const text = await res.text();

        // Parse Prometheus text format: monitor_status{monitor_name="Weather API"} 1
        const parsedMonitors = [];
        const lines = text.split('\n');
        
        lines.forEach(line => {
          if (line.startsWith('monitor_status{')) {
            const nameMatch = line.match(/monitor_name="([^"]+)"/);
            const statusMatch = line.match(/}\s([0-9]+)/);
            
            if (nameMatch && statusMatch) {
              parsedMonitors.push({
                name: nameMatch[1],
                isUp: statusMatch[1] === '1'
              });
            }
          }
        });

        // Filter out Kuma's internal self-check if it exists
        setMonitors(parsedMonitors.filter(m => m.name !== 'Uptime Kuma'));
      } catch (err) {
        console.error("Kuma fetch error:", err);
      }
    };

    // --- NETDATA POLLING ---
    const fetchNetdata = async () => {
      try {
        // 1. Fetch CPU (Returns array, we find the 'idle' index to calculate usage)
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
        
        const free = ramData.data[0][freeIndex];
        const used = ramData.data[0][usedIndex];
        const cached = ramData.data[0][cachedIndex];
        const buffers = ramData.data[0][buffersIndex];
        
        const totalRam = free + used + cached + buffers;
        const ramUsage = (used / totalRam) * 100;

        // 3. Fetch Temperature 
        // Note: Raspberry Pi thermal charts are dynamically named. Usually 'cpu.temperature' or 'sensors.cpu_thermal-virtual-0_temp'
        // If this stays at 0, check your Netdata dashboard to find the exact chart name for your Pi's thermal zone.
        let tempValue = 0;
        try {
          const tempRes = await fetch(`${NETDATA_API_BASE}?chart=cpu.temperature&format=json&points=1`);
          if (tempRes.ok) {
            const tempData = await tempRes.json();
            tempValue = tempData.data[0][1]; 
          }
        } catch (e) { /* Ignore missing temp sensor */ }

        setNetdata({
          cpu: cpuUsage.toFixed(1),
          ram: ramUsage.toFixed(1),
          temp: tempValue ? tempValue.toFixed(1) : '--'
        });

      } catch (err) {
        console.error("Netdata fetch error:", err);
        setError("Netdata unreachable");
      }
    };

    // Run immediately, then poll every 10 seconds
    fetchKuma();
    fetchNetdata();
    const interval = setInterval(() => {
      fetchKuma();
      fetchNetdata();
    }, 10000);

    return () => clearInterval(interval);
  }, [KUMA_METRICS_URL, NETDATA_API_BASE]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 mb-5">
        <Activity className="text-accentBlue w-5 h-5" />
        <h2 className="text-lg font-semibold text-textSilver">Infrastructure</h2>
      </div>

      {error && <div className="text-xs text-red-400 mb-3">{error}</div>}

      {/* Hardware Telemetry (Netdata) */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50 flex flex-col items-center justify-center">
          <Cpu className="w-4 h-4 text-slate-400 mb-1" />
          <span className="text-xs text-slate-500 font-bold uppercase tracking-wider mb-0.5">CPU</span>
          <span className="text-sm font-bold text-sky-400">{netdata.cpu}%</span>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50 flex flex-col items-center justify-center">
          <Server className="w-4 h-4 text-slate-400 mb-1" />
          <span className="text-xs text-slate-500 font-bold uppercase tracking-wider mb-0.5">RAM</span>
          <span className="text-sm font-bold text-sky-400">{netdata.ram}%</span>
        </div>
        <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50 flex flex-col items-center justify-center">
          <Thermometer className="w-4 h-4 text-slate-400 mb-1" />
          <span className="text-xs text-slate-500 font-bold uppercase tracking-wider mb-0.5">Temp</span>
          <span className="text-sm font-bold text-emerald-400">{netdata.temp}°C</span>
        </div>
      </div>

      <div className="h-px bg-slate-700/60 w-full mb-4" />

      {/* Service Monitors (Uptime Kuma) */}
      <div className="flex flex-col gap-3 overflow-y-auto pr-1 flex-1">
        {monitors.length === 0 ? (
          <div className="text-xs text-slate-500 italic text-center mt-2">No monitors found in Kuma</div>
        ) : (
          monitors.map((monitor, idx) => (
            <div key={idx} className="flex items-center justify-between bg-slate-900/40 p-2.5 rounded border border-slate-800">
              <span className="text-sm text-slate-300 font-medium truncate pr-4">{monitor.name}</span>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-[10px] font-bold uppercase tracking-wider ${monitor.isUp ? 'text-emerald-500' : 'text-red-500'}`}>
                  {monitor.isUp ? 'Online' : 'Offline'}
                </span>
                <span className={`flex h-2.5 w-2.5 rounded-full shadow-sm ${monitor.isUp ? 'bg-emerald-500 shadow-emerald-500/50' : 'bg-red-500 shadow-red-500/50 animate-pulse'}`}></span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}