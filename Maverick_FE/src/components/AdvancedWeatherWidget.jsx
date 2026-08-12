import { Compass, Droplet, Flame, Gauge, Plane, Sun } from "lucide-react";
import { useEffect, useState } from "react";

// Color mapping for text values on 0-10 gradient
const getGradientColor = (score) => {
  if (score == null) return "text-slate-200";
  if (score <= 2) return "text-emerald-400";
  if (score <= 5) return "text-amber-400";
  if (score <= 8) return "text-orange-500";
  return "text-red-500 font-bold animate-pulse";
};

export default function AdvancedWeatherWidget() {
  const [activeTab, setActiveTab] = useState("current"); // 'current' | 'aviation'
  const [advCurrent, setAdvCurrent] = useState(null);
  const [aviation, setAviation] = useState(null);
  const [loading, setLoading] = useState(true);

  const host = window.location.hostname;
  const ADV_CURRENT_URL = `http://${host}:8004/api/weather/advanced/current`;
  const AVIATION_URL = `http://${host}:8004/api/weather/aviation`;

  const fetchAdvancedData = async () => {
    try {
      const [advRes, avRes] = await Promise.all([
        fetch(ADV_CURRENT_URL),
        fetch(AVIATION_URL),
      ]);

      if (advRes.ok) setAdvCurrent(await advRes.json());
      if (avRes.ok) setAviation(await avRes.json());
    } catch (err) {
      console.error("Failed to fetch advanced telemetry:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAdvancedData();
    const interval = setInterval(fetchAdvancedData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="bg-cardBg border border-borderSlate rounded-xl p-5 animate-pulse text-slate-500">
        Loading advanced telemetry...
      </div>
    );
  }

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl p-5 shadow-lg flex flex-col gap-4">
      {/* TAB NAVIGATION HEADER */}
      <div className="flex justify-between items-center border-b border-borderSlate pb-3">
        <h2 className="text-sm font-semibold text-slate-300">
          Advanced Environmental Metrics
        </h2>

        <div className="flex bg-[#111827] p-1 rounded-lg border border-borderSlate gap-1 text-xs">
          <button
            onClick={() => setActiveTab("current")}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all ${
              activeTab === "current"
                ? "bg-slate-700 text-slate-100 font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Gauge className="w-3.5 h-3.5" />
            Current
          </button>

          <button
            onClick={() => setActiveTab("aviation")}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all ${
              activeTab === "aviation"
                ? "bg-slate-700 text-slate-100 font-medium"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Plane className="w-3.5 h-3.5" />
            Aviation
          </button>
        </div>
      </div>

      {/* TAB 1: CURRENT ADVANCED */}
      {activeTab === "current" && advCurrent && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {/* WBGT (Colored by heat_misery_index) */}
          <div className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex flex-col gap-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>WBGT Index</span>
              <Flame className="w-3.5 h-3.5 text-amber-500" />
            </div>
            <span
              className={`text-xl font-bold ${getGradientColor(advCurrent.heat_misery_index)}`}
            >
              {advCurrent.wbgt_f}°F
            </span>
            <span className="text-[10px] text-slate-500">
              Heat Misery: {advCurrent.heat_misery_index}/10
            </span>
          </div>

          {/* VPD (Colored by humidity_misery_index) */}
          <div className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex flex-col gap-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>VPD Deficit</span>
              <Droplet className="w-3.5 h-3.5 text-blue-400" />
            </div>
            <span
              className={`text-xl font-bold ${getGradientColor(advCurrent.humidity_misery_index)}`}
            >
              {advCurrent?.vpd_kpa?.toFixed(2) ?? "N/A"}{" "}
              <span className="text-xs font-normal">kPa</span>
            </span>
            <span className="text-[10px] text-slate-500">
              Humidity Misery: {advCurrent.humidity_misery_index}/10
            </span>
          </div>

          {/* Delta T & Air Density */}
          <div className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex flex-col gap-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>Delta T</span>
              <span className="text-[10px] text-slate-500">Evaporation</span>
            </div>
            <span className="text-xl font-bold text-slate-200">
              {advCurrent.delta_t_c}°C
            </span>
            <span className="text-[10px] text-slate-500">
              Air Density: {advCurrent.air_density_kg_m3} kg/m³
            </span>
          </div>

          {/* Illuminance */}
          <div className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex flex-col gap-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>Solar Lux</span>
              <Sun className="w-3.5 h-3.5 text-yellow-400" />
            </div>
            <span className="text-xl font-bold text-slate-200">
              {advCurrent.illuminance_lux}{" "}
              <span className="text-xs font-normal">Lux</span>
            </span>
            <span className="text-[10px] text-slate-500">Solar Radiation</span>
          </div>
        </div>
      )}

      {/* TAB 2: AVIATION TELEMETRY */}
      {activeTab === "aviation" && aviation && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {/* Density Altitude */}
          <div className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex flex-col gap-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>Density Altitude</span>
              <Plane className="w-3.5 h-3.5 text-cyan-400" />
            </div>
            <span className="text-xl font-bold text-cyan-300">
              {aviation.density_altitude_ft.toLocaleString()}{" "}
              <span className="text-xs font-normal">ft</span>
            </span>
            <span className="text-[10px] text-slate-500">
              Density Perf Height
            </span>
          </div>

          {/* Altimeter / Station Pressure */}
          <div className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex flex-col gap-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>Altimeter (SLP)</span>
              <Gauge className="w-3.5 h-3.5 text-slate-400" />
            </div>
            <span className="text-xl font-bold text-slate-200">
              {aviation.sea_level_pressure_inhg}{" "}
              <span className="text-xs font-normal">inHg</span>
            </span>
            <span className="text-[10px] text-slate-500">
              Station: {aviation.station_pressure_inhg} inHg
            </span>
          </div>

          {/* Wind Telemetry */}
          <div className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex flex-col gap-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>Wind / Direction</span>
              <Compass className="w-3.5 h-3.5 text-slate-400" />
            </div>
            <span className="text-xl font-bold text-slate-200">
              {aviation.wind_avg_mph}{" "}
              <span className="text-xs font-normal">mph</span>
            </span>
            <span className="text-[10px] text-slate-500">
              {aviation.wind_direction ? `${aviation.wind_direction} °` : "VRB"}{" "}
              (Gusts: {aviation.wind_gust_mph} mph)
            </span>
          </div>

          {/* Visibility Index */}
          <div className="bg-[#111827] p-3 rounded-lg border border-borderSlate flex flex-col gap-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>Visibility Index</span>
              <span className="text-[10px] text-slate-500">Calculated</span>
            </div>
            <span className="text-xl font-bold text-slate-200">
              {aviation?.visibility_index?.toFixed(1) ?? "N/A"}
            </span>
            <span className="text-[10px] text-slate-500">
              Atmospheric Clarity
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
