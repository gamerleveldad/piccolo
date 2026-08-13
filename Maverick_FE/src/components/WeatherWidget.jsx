import { CloudRain, Droplets, Wind, X, Zap } from "lucide-react";
import mqtt from "mqtt";
import { useEffect, useState } from "react";

const ICON_MAP = {
  "clear-day": "wi wi-day-sunny",
  "clear-night": "wi wi-night-clear",
  "partly-cloudy-day": "wi wi-day-cloudy",
  "partly-cloudy-night": "wi wi-night-alt-cloudy",
  cloudy: "wi wi-cloudy",
  "possibly-thunderstorm-day": "wi wi-day-thunderstorm",
  "possibly-thunderstorm-night": "wi wi-night-alt-thunderstorm",
  thunderstorm: "wi wi-thunderstorm",
  rain: "wi wi-rain",
  "chance-rain": "wi wi-day-rain",
  foggy: "wi wi-fog",
  windy: "wi wi-strong-wind",
};

const getMiseryDotColor = (val) => {
  if (val == null) return "bg-slate-700";
  if (val <= 2) return "bg-emerald-400 shadow-[0_0_6px_#34d399]";
  if (val <= 5) return "bg-amber-400 shadow-[0_0_6px_#fbbf24]";
  if (val <= 8) return "bg-orange-500 shadow-[0_0_6px_#f97316]";
  return "bg-red-500 shadow-[0_0_6px_#ef4444] animate-pulse";
};

const getAlertStyling = (eventStr) => {
  const lowerEvent = eventStr.toLowerCase();
  let icon = "wi wi-info-circle"; // Fallback icon
  let color = "text-slate-300";
  let animation = "";

  if (lowerEvent.includes("special weather statement")) {
    icon = "wi wi-thunderstorm";
    color = "text-yellow-400";
  } else if (lowerEvent.includes("severe thunderstorm warning")) {
    icon = "wi wi-thunderstorm";
    color = "text-red-500";
    animation = "animate-pulse";
  } else if (lowerEvent.includes("tornado watch")) {
    icon = "wi wi-tornado";
    color = "text-yellow-400";
  } else if (lowerEvent.includes("tornado warning")) {
    icon = "wi wi-tornado";
    color = "text-red-500";
    animation = "animate-pulse";
  } else if (lowerEvent.includes("tropical storm watch")) {
    icon = "wi wi-storm-warning";
    color = "text-yellow-400";
  } else if (lowerEvent.includes("tropical storm warning")) {
    icon = "wi wi-storm-warning";
    color = "text-red-500";
  } else if (lowerEvent.includes("hurricane watch")) {
    icon = "wi wi-hurricane-warning";
    color = "text-yellow-400";
  } else if (lowerEvent.includes("hurricane warning")) {
    icon = "wi wi-hurricane-warning";
    color = "text-red-500";
    animation = "animate-pulse";
  } else if (lowerEvent.includes("extreme heat watch")) {
    icon = "wi wi-hot";
    color = "text-yellow-400";
  } else if (lowerEvent.includes("extreme heat warning")) {
    icon = "wi wi-hot";
    color = "text-red-500";
    animation = "animate-pulse";
  } else if (lowerEvent.includes("heat advisory")) {
    icon = "wi wi-hot";
    color = "text-yellow-400";
  } else if (lowerEvent.includes("dense fog")) {
    icon = "wi wi-fog";
    color = "text-slate-400";
  } else if (lowerEvent.includes("freeze watch")) {
    icon = "wi wi-snowflake-cold";
    color = "text-blue-400";
  } else if (lowerEvent.includes("freeze warning")) {
    icon = "wi wi-snowflake-cold";
    color = "text-cyan-300";
  } else if (lowerEvent.includes("cold weather advisory")) {
    icon = "wi wi-thermometer-exterior";
    color = "text-blue-400";
  } else if (lowerEvent.includes("extreme cold warning")) {
    icon = "wi wi-thermometer-exterior";
    color = "text-cyan-300";
  } else if (lowerEvent.includes("high wind watch")) {
    icon = "wi wi-strong-wind";
    color = "text-yellow-400";
  } else if (lowerEvent.includes("high wind warning")) {
    icon = "wi wi-strong-wind";
    color = "text-red-500";
  } else if (lowerEvent.includes("red flag")) {
    icon = "wi wi-fire";
    color = "text-red-500";
  } else if (lowerEvent.includes("flash flood warning")) {
    icon = "wi wi-flood";
    color = "text-red-500";
    animation = "animate-pulse";
  } else if (lowerEvent.includes("flood warning")) {
    icon = "wi wi-flood";
    color = "text-red-500";
  } else if (lowerEvent.includes("flood watch")) {
    icon = "wi wi-flood";
    color = "text-yellow-400";
  } else if (lowerEvent.includes("flood advisory")) {
    icon = "wi wi-raindrops";
    color = "text-cyan-400";
  } else if (lowerEvent.includes("frost advisory")) {
    icon = "wi wi-snowflake-cold";
    color = "text-blue-300";
  } else if (lowerEvent.includes("wind advisory")) {
    icon = "wi wi-windy";
    color = "text-slate-400";
  } else if (lowerEvent.includes("fire weather watch")) {
    icon = "wi wi-fire";
    color = "text-amber-500";
  } else if (lowerEvent.includes("air quality")) {
    icon = "wi wi-smog";
    color = "text-slate-400";
  }
  // Generic fallbacks just in case NWS throws a curveball
  else if (lowerEvent.includes("warning")) {
    color = "text-red-500";
    animation = "animate-pulse";
  } else if (lowerEvent.includes("watch") || lowerEvent.includes("advisory")) {
    color = "text-yellow-400";
  }

  return { icon, color, animation };
};

export default function WeatherWidget() {
  const [current, setCurrent] = useState(null);
  const [hourlyForecast, setHourlyForecast] = useState([]);
  const [dailyForecast, setDailyForecast] = useState([]);
  const [activeAlerts, setActiveAlerts] = useState([]);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const USE_BUTTON_BORDERS = true; // Set to false to remove the borders around icons
  const [loading, setLoading] = useState(true);
  const [tropicsOutlook, setTropicsOutlook] = useState(null);
  const [activeStorms, setActiveStorms] = useState([]);

  // Real-time telemetry via MQTT WebSockets
  const [liveTelemetry, setLiveTelemetry] = useState({
    temp_f: null,
    humidity: null,
    wind_avg_mph: null,
    wind_gust_mph: null,
    wind_direction_deg: null,
    rain_rate_in_hr: 0,
  });

  // Tab state for the forecast section
  const [forecastTab, setForecastTab] = useState("hourly"); // 'hourly' | 'daily' | 'tropics'

  const host = window.location.hostname;
  const CURRENT_URL = `http://${host}:8004/api/weather/current`;
  const HOURLY_URL = `http://${host}:8004/api/weather/forecast/hourly`;
  const ADVANCED_HOURLY_URL = `http://${host}:8004/api/weather/advanced/hourly`;
  const DAILY_URL = `http://${host}:8004/api/weather/forecast/daily`;
  const ACCURACY_URL = `http://${host}:8004/api/weather/forecast/accuracy`;
  const NWS_ALERTS_URL = `https://api.weather.gov/alerts/active?point=28.6611,-81.3884`;

  // MQTT Listener for Tempest UDP Broadcast Stream
  useEffect(() => {
    const client = mqtt.connect(`ws://${host}:9001`);

    client.on("connect", () => {
      client.subscribe("weather/tempest/live");
    });

    client.on("message", (topic, message) => {
      try {
        const data = JSON.parse(message.toString());
        setLiveTelemetry((prev) => {
          if (data.update_type === "rapid_wind") {
            return {
              ...prev,
              wind_avg_mph: data.wind_speed_mph,
              wind_direction_deg: data.wind_direction_deg,
            };
          }
          if (data.update_type === "sensor_snapshot") {
            return {
              ...prev,
              temp_f: data.temp_f,
              humidity: data.humidity,
              wind_gust_mph: data.wind_gust_mph,
              rain_rate_in_hr: data.rain_rate_in_hr,
            };
          }
          return prev;
        });
      } catch (err) {
        console.warn("MQTT Parse Error:", err);
      }
    });

    return () => {
      if (client) client.end();
    };
  }, [host]);

  const fetchWeatherData = async () => {
    try {
      // 1. Fetch Current REST State
      const curRes = await fetch(CURRENT_URL);
      if (curRes.ok) setCurrent(await curRes.json());

      // 2. Fetch Hourly & Daily concurrently
      const [hourRes, advHourRes, dailyRes, accRes] = await Promise.all([
        fetch(HOURLY_URL),
        fetch(ADVANCED_HOURLY_URL),
        fetch(DAILY_URL),
        fetch(ACCURACY_URL),
      ]);

      // Parse Hourly
      if (hourRes.ok) {
        const data = await hourRes.json();
        let advData = [];
        if (advHourRes.ok) advData = await advHourRes.json();

        const parsedHours = data.slice(0, 6).map((item) => {
          const match = advData.find((a) => a.time === item.time) || {};
          return {
            time: new Date(item.time).toLocaleTimeString([], {
              hour: "numeric",
              hour12: true,
            }),
            temp: Math.round(item.temp_f),
            condition: item.conditions,
            pop: item.precip_probability ?? 0,
            iconClass: ICON_MAP[item.icon] || "wi wi-day-sunny",
            heatMisery: match.heat_misery_index ?? 0,
            humidityMisery: match.humidity_misery_index ?? 0,
          };
        });
        setHourlyForecast(parsedHours);
      }

      // Parse Daily + Accuracy
      if (dailyRes.ok) {
        const dailyData = await dailyRes.json();
        let accData = [];
        if (accRes.ok) accData = await accRes.json();

        const parsedDaily = dailyData.slice(0, 10).map((day, idx) => {
          const accuracy = accData.find((a) => a.lead_days === idx);
          return {
            ...day,
            dateObj: new Date(day.date),
            iconClass: ICON_MAP[day.icon] || "wi wi-day-sunny",
            tempMae: accuracy ? accuracy.temp_mae_f : null,
          };
        });
        setDailyForecast(parsedDaily);
      }

      // 3. Fetch NWS Alerts
      const alertsRes = await fetch(NWS_ALERTS_URL);
      if (alertsRes.ok) {
        const alertData = await alertsRes.json();
        const features = alertData.features || [];

        const parsedAlerts = features.map((feature) => {
          const event = feature.properties.event;
          const description = feature.properties.description;
          const instruction = feature.properties.instruction;
          const styling = getAlertStyling(event);

          return {
            id: feature.id || Math.random().toString(36).substring(2, 9),
            event,
            description,
            instruction,
            ...styling,
          };
        });
        setActiveAlerts(parsedAlerts);
      }
    } catch (err) {
      console.error("Failed to fetch weather telemetry:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTropics = async () => {
    try {
      const outlookRes = await fetch(
        `http://${host}:8004/api/weather/tropics/outlook`,
      );
      if (outlookRes.ok) setTropicsOutlook(await outlookRes.json());

      const activeRes = await fetch(
        `http://${host}:8004/api/weather/tropics/active`,
      );
      if (activeRes.ok) setActiveStorms(await activeRes.json());
    } catch (err) {
      console.warn("Tropics fetch failed:", err);
    }
  };

  useEffect(() => {
    fetchWeatherData();
    fetchTropics();
    const interval = setInterval(() => {
      fetchWeatherData();
      fetchTropics();
    }, 60000);
    return () => clearInterval(interval);
  }, []);

  if (loading || !current) {
    return (
      <div className="bg-cardBg border border-borderSlate rounded-xl p-5 animate-pulse text-slate-500">
        Loading weather telemetry...
      </div>
    );
  }

  // Value resolution prioritizing UDP live stream over API polling
  const displayTemp = liveTelemetry.temp_f ?? current.temp_f;
  const displayHumidity = liveTelemetry.humidity ?? current.relative_humidity;
  const displayWindAvg = liveTelemetry.wind_avg_mph ?? current.wind_avg_mph;
  const displayWindGust = liveTelemetry.wind_gust_mph ?? current.wind_gust_mph;
  const currentIconClass = ICON_MAP[current.icon] || "wi wi-day-sunny";

  return (
    <div className="bg-cardBg border border-borderSlate rounded-xl p-5 shadow-lg flex flex-col gap-6 relative overflow-hidden">
      {/* CURRENT CONDITIONS HEADER */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <div>
            <div className="flex items-center gap-2">
              {/* ALERTS ICON BAR */}
              {activeAlerts.length > 0 && (
                <div className="bg-[#1e293b] border border-slate-700/50 rounded-lg p-2 flex flex-wrap gap-2 items-center shadow-inner">
                  {activeAlerts.map((alert) => (
                    <button
                      key={alert.id}
                      onClick={() => setSelectedAlert(alert)}
                      title={alert.event}
                      className={`p-1.5 flex items-center justify-center transition-all ${alert.animation}
                          ${USE_BUTTON_BORDERS ? "border border-slate-600 rounded bg-slate-800 hover:bg-slate-700 shadow-sm" : "hover:scale-110"}
                        `}
                    >
                      <i className={`${alert.icon} text-xl ${alert.color}`} />
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="flex items-center gap-3 mt-1">
              <span className="text-4xl font-bold text-slate-100">
                {Math.round(displayTemp)}°F
              </span>

              <div className="flex items-center gap-2 pl-2 border-l border-slate-700">
                <i className={`${currentIconClass} text-3xl text-amber-400`} />
                <div className="flex flex-col">
                  <span className="text-xs font-semibold text-slate-200">
                    {current.conditions}
                  </span>
                  <span className="text-[11px] text-slate-400">
                    Feels {Math.round(current.feels_like_f)}°F
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Telemetry Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <Droplets className="w-4 h-4 text-blue-400 shrink-0" />
            <div>
              <p className="text-slate-500">Humidity / Dew</p>
              <p className="font-semibold text-slate-200">
                {displayHumidity}% / {Math.round(current.dew_point_f)}°F
              </p>
            </div>
          </div>

          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <Wind className="w-4 h-4 text-slate-400 shrink-0" />
            <div>
              <p className="text-slate-500">Wind / Gust</p>
              <p className="font-semibold text-slate-200">
                {displayWindAvg}{" "}
                <span className="text-slate-400">({displayWindGust})</span> mph
              </p>
            </div>
          </div>

          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <CloudRain className="w-4 h-4 text-cyan-400 shrink-0" />
            <div>
              <p className="text-slate-500">Rain (Today / Rate)</p>
              <p className="font-semibold text-slate-200">
                {current?.precip_in?.toFixed(2) ?? "0.00"} in
                <span className="text-slate-400 text-xs font-normal">
                  {" "}
                  / {liveTelemetry.rain_rate_in_hr ?? 0} in/hr
                </span>
              </p>
            </div>
          </div>

          <div className="bg-[#111827] p-2.5 rounded-lg border border-borderSlate flex items-center gap-2">
            <Zap
              className={`w-4 h-4 shrink-0 ${current.lightning_strike_count > 0 ? "text-yellow-400 animate-pulse" : "text-slate-600"}`}
            />
            <div>
              <p className="text-slate-500">Lightning (1h)</p>
              <p className="font-semibold text-slate-200">
                {current.lightning_strike_count > 0
                  ? `${current.lightning_strike_count} strikes`
                  : "None"}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* FORECAST TABS & GRID */}
      <div className="border-t border-borderSlate pt-4">
        <div className="flex justify-between items-center mb-4">
          <div className="flex bg-[#111827] p-1 rounded-lg border border-borderSlate gap-1 text-xs">
            <button
              onClick={() => setForecastTab("hourly")}
              className={`px-3 py-1 rounded-md transition-all ${
                forecastTab === "hourly"
                  ? "bg-slate-700 text-slate-100 font-medium"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              6-Hour
            </button>
            <button
              onClick={() => setForecastTab("daily")}
              className={`px-3 py-1 rounded-md transition-all ${
                forecastTab === "daily"
                  ? "bg-slate-700 text-slate-100 font-medium"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              10-Day
            </button>
            <button
              onClick={() => setForecastTab("tropics")}
              className={`px-3 py-1 rounded-md transition-all ${
                forecastTab === "tropics"
                  ? "bg-slate-700 text-slate-100 font-medium"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Tropics
            </button>
          </div>

          {forecastTab === "hourly" && (
            <div className="flex items-center gap-3 text-[10px] text-slate-500">
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> Heat
              </span>
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />{" "}
                Humidity
              </span>
            </div>
          )}
        </div>

        {/* 6-HOUR GRID */}
        {forecastTab === "hourly" && (
          <div className="grid grid-cols-6 gap-2 text-center">
            {hourlyForecast.map((hour, idx) => (
              <div
                key={idx}
                className="bg-[#111827] p-2 rounded-lg border border-borderSlate flex flex-col items-center justify-between relative min-h-[110px]"
              >
                <span className="text-[11px] text-slate-400">{hour.time}</span>
                <i
                  className={`${hour.iconClass} text-xl my-1 text-amber-400`}
                />
                <span className="text-sm font-bold text-slate-100">
                  {hour.temp}°
                </span>
                <div className="text-[10px] text-cyan-400 font-medium mb-2">
                  {hour.pop > 0 ? `${hour.pop}%` : "0%"}
                </div>
                <div
                  title={`Heat Misery: ${hour.heatMisery}/10`}
                  className={`absolute bottom-1.5 left-1.5 w-2 h-2 rounded-full ${getMiseryDotColor(hour.heatMisery)}`}
                />
                <div
                  title={`Humidity Misery: ${hour.humidityMisery}/10`}
                  className={`absolute bottom-1.5 right-1.5 w-2 h-2 rounded-full ${getMiseryDotColor(hour.humidityMisery)}`}
                />
              </div>
            ))}
          </div>
        )}

        {/* 10-DAY GRID */}
        {forecastTab === "daily" && (
          <div className="grid grid-cols-5 gap-2 text-center">
            {dailyForecast.map((day, idx) => (
              <div
                key={idx}
                className="bg-[#111827] p-2 rounded-lg border border-borderSlate flex flex-col items-center justify-between min-h-[120px]"
              >
                <div className="flex flex-col mb-1">
                  <span className="text-xs font-bold text-slate-200">
                    {day.day_name}
                  </span>
                  <span className="text-[9px] text-slate-400">
                    {day.dateObj.toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </div>

                <i className={`${day.iconClass} text-xl my-1 text-amber-400`} />

                <div className="flex flex-col items-center leading-tight w-full">
                  <div className="flex items-center justify-center gap-0.5">
                    <span className="text-sm font-bold text-slate-100">
                      {Math.round(day.temp_max_f)}°
                    </span>
                    {day.tempMae != null && (
                      <span
                        className="text-[9px] text-slate-400"
                        title={`Model Error: ±${day.tempMae}°F`}
                      >
                        ±{day.tempMae}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-slate-400">
                    {Math.round(day.temp_min_f)}°
                  </span>
                </div>

                <div className="mt-1.5 flex flex-col text-[9px] text-slate-400 leading-tight w-full">
                  {day.precip_probability > 0 ? (
                    <span className="text-cyan-400 font-medium">
                      {day.precip_probability}% • {day.precip_accum_in}"
                    </span>
                  ) : (
                    <span>0% Rain</span>
                  )}
                  <span>{day.max_wind_speed_mph} mph</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* TROPICS TAB */}
        {forecastTab === "tropics" && tropicsOutlook && (
          <div className="flex flex-col gap-4 mt-4 overflow-y-auto pr-2">
            <div className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-3">
              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                Development Probability
              </h4>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="bg-slate-900/50 rounded p-2 text-center">
                  <span className="block text-[10px] text-slate-400 uppercase">
                    48-Hour
                  </span>
                  <span className="text-lg font-bold text-accentBlue">
                    {tropicsOutlook.development_probabilities["48_hour_pct"]}%
                  </span>
                </div>
                <div className="bg-slate-900/50 rounded p-2 text-center">
                  <span className="block text-[10px] text-slate-400 uppercase">
                    7-Day
                  </span>
                  <span className="text-lg font-bold text-accentBlue">
                    {tropicsOutlook.development_probabilities["7_day_pct"]}%
                  </span>
                </div>
              </div>

              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                Regional Favorability
              </h4>
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-slate-300">Atlantic</span>
                  <span
                    className={`font-bold ${tropicsOutlook.regional_favorability.atlantic === "High" ? "text-red-400" : "text-slate-400"}`}
                  >
                    {tropicsOutlook.regional_favorability.atlantic}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-300">Gulf of Mexico</span>
                  <span
                    className={`font-bold ${tropicsOutlook.regional_favorability.gulf_of_mexico === "High" ? "text-red-400" : "text-slate-400"}`}
                  >
                    {tropicsOutlook.regional_favorability.gulf_of_mexico}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-300">Caribbean</span>
                  <span
                    className={`font-bold ${tropicsOutlook.regional_favorability.caribbean === "High" ? "text-red-400" : "text-slate-400"}`}
                  >
                    {tropicsOutlook.regional_favorability.caribbean}
                  </span>
                </div>
              </div>
            </div>

            {activeStorms.length > 0 && (
              <div className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-3">
                <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                  Active Systems
                </h4>
                <div className="space-y-3">
                  {activeStorms.map((storm) => (
                    <div
                      key={storm.id}
                      className="bg-slate-900/50 rounded p-3 border-l-2 border-red-500"
                    >
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <span className="font-bold text-slate-200">
                            {storm.name}
                          </span>
                          <span className="text-xs text-slate-400 ml-2">
                            {storm.category}
                          </span>
                        </div>
                        <span className="text-xs font-mono text-slate-400">
                          {storm.intensity.wind_speed_mph} mph
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 flex justify-between">
                        <span>
                          Lat: {storm.location.lat} | Lon: {storm.location.lon}
                        </span>
                        <span>
                          Moving: {storm.movement.heading_deg}° at{" "}
                          {storm.movement.speed_mph} mph
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      {/* ALERT DETAILS MODAL */}
      {selectedAlert && (
        <div className="fixed inset-0 z-[9999] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#162032] border border-slate-600 rounded-lg shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center gap-3 p-4 border-b border-slate-700 bg-slate-800/50 rounded-t-lg shrink-0">
              <i
                className={`${selectedAlert.icon} text-2xl ${selectedAlert.color}`}
              />
              <h3
                className={`font-bold text-lg uppercase tracking-wide ${selectedAlert.color}`}
              >
                {selectedAlert.event}
              </h3>
              <button
                onClick={() => setSelectedAlert(null)}
                className="ml-auto p-1 hover:bg-slate-700 rounded text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 overflow-auto space-y-5 text-sm text-slate-300">
              {selectedAlert.description && (
                <div>
                  <h4 className="font-bold text-slate-400 uppercase text-xs mb-1">
                    Details
                  </h4>
                  <p className="whitespace-pre-wrap leading-relaxed">
                    {selectedAlert.description}
                  </p>
                </div>
              )}
              {selectedAlert.instruction && (
                <div>
                  <h4 className="font-bold text-slate-400 uppercase text-xs mb-1">
                    Instructions
                  </h4>
                  <p className="whitespace-pre-wrap leading-relaxed border-l-2 border-amber-500 pl-3 italic">
                    {selectedAlert.instruction}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
