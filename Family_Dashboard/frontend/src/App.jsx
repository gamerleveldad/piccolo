import React, { useState, useEffect } from 'react';

const weatherAssets = {
  'clear-day': '/assets/weather/clear-day.gif',
  'clear-night': '/assets/weather/clear-night.gif',
  'cloudy': '/assets/weather/cloudy.gif',
  'fog': '/assets/weather/fog.gif',
  'partly-cloudy-day': '/assets/weather/partly-cloudy-day.gif',
  'partly-cloudy-night': '/assets/weather/partly-cloudy-night.gif',
  'rainy': '/assets/weather/rainy.gif',
  'snow': '/assets/weather/snow.gif',
  'thunderstorm': '/assets/weather/thunderstorm.gif',
  'windy': '/assets/weather/windy.gif',
  'default': '/assets/weather/clear-day.gif',
  'alien': '/assets/weather/weather-icons-master/svg/wi-alien.svg' // Easter egg fallback asset
};

// HELPER: SvgWeatherIcon rebuilt with aggressive string matching so unknown APIs don't trigger the alien
const SvgWeatherIcon = ({ icon, className = "w-4 h-4" }) => {
  const mapping = {
    'clear-day': { file: 'wi-day-sunny.svg', color: 'text-yellow-400' },
    'clear-night': { file: 'wi-night-clear.svg', color: 'text-blue-300' },
    'cloudy': { file: 'wi-cloudy.svg', color: 'text-slate-400' },
    'partly-cloudy-day': { file: 'wi-day-cloudy.svg', color: 'text-yellow-200' },
    'partly-cloudy-night': { file: 'wi-night-alt-cloudy.svg', color: 'text-slate-300' },
    'rainy': { file: 'wi-rain.svg', color: 'text-blue-400' },
    'snow': { file: 'wi-snow.svg', color: 'text-white' },
    'thunderstorm': { file: 'wi-thunderstorm.svg', color: 'text-blue-400 animate-pulse' }, 
    'fog': { file: 'wi-fog.svg', color: 'text-slate-400' },
    'windy': { file: 'wi-strong-wind.svg', color: 'text-slate-300' },
    'alien': { file: 'wi-alien.svg', color: 'text-emerald-400 animate-bounce' }
  };

  const getSafeMeta = (rawIcon) => {
    if (!rawIcon) return mapping['clear-day'];
    const key = rawIcon.toLowerCase();
    
    if (key === 'alien') return mapping['alien']; // Hardcode trigger for easter egg
    if (key.includes('clear') && key.includes('night')) return mapping['clear-night'];
    if (key.includes('clear') || key.includes('sun')) return mapping['clear-day'];
    if (key.includes('partly') && key.includes('night')) return mapping['partly-cloudy-night'];
    if (key.includes('partly')) return mapping['partly-cloudy-day'];
    if (key.includes('cloud') || key.includes('overcast')) return mapping['cloudy'];
    if (key.includes('thunder') || key.includes('storm')) return mapping['thunderstorm'];
    if (key.includes('rain') || key.includes('drizzle') || key.includes('shower')) return mapping['rainy'];
    if (key.includes('snow') || key.includes('ice') || key.includes('flurr') || key.includes('sleet')) return mapping['snow'];
    if (key.includes('fog') || key.includes('mist')) return mapping['fog'];
    if (key.includes('wind')) return mapping['windy'];
    
    return mapping['cloudy']; // Failsafe to a normal cloud instead of an alien
  };
  
  const meta = getSafeMeta(icon);
  if (meta.file === 'wi-thunderstorm.svg') {
    return (
      <div 
        className={`${className} animate-pulse`}
        style={{
          WebkitMaskImage: `url(/assets/weather/weather-icons-master/svg/${meta.file})`,
          WebkitMaskSize: 'contain',
          WebkitMaskRepeat: 'no-repeat',
          WebkitMaskPosition: 'center',
          // Paint the top 55% slate-400 (grey) and the bottom amber-400 (yellow)
          backgroundImage: 'linear-gradient(to bottom, #94a3b8 55%, #fbbf24 60%)'
        }}
      />
    );
  }
  return (
    <div 
      className={`${className} ${meta.color}`}
      style={{
        WebkitMaskImage: `url(/assets/weather/weather-icons-master/svg/${meta.file})`,
        WebkitMaskSize: 'contain',
        WebkitMaskRepeat: 'no-repeat',
        WebkitMaskPosition: 'center',
        backgroundColor: 'currentColor'
      }}
    />
  );
};

// HELPER: Wind Color Scaling
const getWindColor = (mph) => {
  if (mph < 12) return 'text-emerald-400';
  if (mph < 25) return 'text-amber-400';
  return 'text-rose-500 animate-pulse drop-shadow-[0_0_8px_rgba(225,29,72,0.6)]';
};

// HELPER: Pressure Trend Arrows
const getPressureTrendIcon = (trend) => {
  const basePath = "/assets/weather/weather-icons-master/svg";
  if (trend === 'Rising') return `${basePath}/wi-direction-up-right.svg`;
  if (trend === 'Falling') return `${basePath}/wi-direction-down-right.svg`;
  return `${basePath}/wi-direction-right.svg`;
};

// COMPONENT: Google Photos Display Widget
export function GooglePhotosWidget() {
  const [photos, setPhotos] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    const fetchPhotos = async () => {
      try {
        const host = window.location.hostname || '192.168.4.183';
        const res = await fetch(`http://${host}:8000/api/photos`);
        if (res.ok) {
          const data = await res.json();
          // FIX: Add the backend IP address to the start of the image paths
          const fullUrls = (data.urls || []).map(url => `http://${host}:8000${encodeURI(url)}`);
          setPhotos(fullUrls);
        }
      } catch (err) {
        console.error("Photos API Fetch Blocked/Failed", err);
      }
    };
    fetchPhotos();
    const interval = setInterval(fetchPhotos, 45 * 60 * 1000); 
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (photos.length <= 1) return;
    const timer = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % photos.length);
    }, 15000);
    return () => clearInterval(timer);
  }, [photos]);

  if (photos.length === 0) {
    return (
      <div className="h-full min-h-[160px] flex items-center justify-center border border-slate-900/40 rounded-2xl bg-slate-950 shadow-2xl">
        <span className="text-[10px] text-slate-600 font-mono uppercase tracking-widest animate-pulse">
          Awaiting Photo Stream...
        </span>
      </div>
    );
  }

  return (
    <div className="h-full min-h-[160px] w-full rounded-2xl overflow-hidden border border-slate-900/40 shadow-2xl relative bg-slate-950">
      <img 
        key={photos[currentIndex]}
        src={photos[currentIndex]}
        className="w-full h-full object-cover transition-opacity duration-1000" 
        alt="Family Display Board" 
      />
      <div className="absolute bottom-2 right-2 px-2 py-0.5 bg-black/50 backdrop-blur-sm rounded text-[8px] font-mono text-slate-400">
        {currentIndex + 1} / {photos.length}
      </div>
    </div>
  );
}

function App() {
  const [weather, setWeather] = useState({
    temperature_f: '--.-',
    feels_like_f: '--.-',
    humidity_pct: '--',
    dew_point_f: '--.-',
    pressure_inhg: '--.--',
    wind_speed_mph: 0.0,
    wind_direction_deg: 0,
    wind_gust_mph: 0.0,
    uv_index: 0,
    lightning_count: 0,
    last_strike_distance: null,
    last_strike_time: null, 
    strike_trigger_ring: null,
    lightning_strike_id: 0,
    high_temp: -999,
    low_temp: 999,
    high_wind: 0,
    high_gust: 0,
    pressure_trend_api: 'Steady',
    rain_rate_in_hr: 0.0,
    rain_accumulation_day_in: 0.0,
    rain_chance_current: 0,
    rain_chance_morning: 0,
    rain_chance_afternoon: 0,
    rain_chance_evening: 0,
    rain_chance_overnight: 0,
    daily_verse: {
      reference: "Loading...",
      text: "Connecting to server..."
    }
  });
  
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const [easterEggActive, setEasterEggActive] = useState(false);
  
  // CORRECT PLACEMENT FOR THE VERSE MODAL STATE
  const [isVerseModalOpen, setIsVerseModalOpen] = useState(false);

  const ALERT_CONFIGS = {
    "Hurricane Warning": { icon: "/assets/weather/weather-icons-master/svg/wi-hurricane.svg", color: "text-rose-500", bg: "bg-rose-950/40", border: "border-rose-500/50", pulse: true },
    "Hurricane Watch": { icon: "/assets/weather/weather-icons-master/svg/wi-hurricane.svg", color: "text-amber-500", bg: "bg-amber-950/40", border: "border-amber-500/30", pulse: false },
    "Tropical Storm Warning": { icon: "/assets/weather/weather-icons-master/svg/wi-hurricane-warning.svg", color: "text-rose-500", bg: "bg-rose-950/40", border: "border-rose-500/50", pulse: true },
    "Tropical Storm Watch": { icon: "/assets/weather/weather-icons-master/svg/wi-hurricane-warning.svg", color: "text-amber-500", bg: "bg-amber-950/30", border: "border-amber-500/20", pulse: false },
    "Tornado Warning": { icon: "/assets/weather/weather-icons-master/svg/wi-tornado.svg", color: "text-rose-500", bg: "bg-rose-950/40", border: "border-rose-500/50", pulse: true },
    "Tornado Watch": { icon: "/assets/weather/weather-icons-master/svg/wi-tornado.svg", color: "text-amber-500", bg: "bg-amber-950/40", border: "border-amber-500/30", pulse: false },
    "Severe Thunderstorm Warning": { icon: "/assets/weather/weather-icons-master/svg/wi-thunderstorm.svg", color: "text-rose-500", bg: "bg-rose-950/40", border: "border-rose-500/50", pulse: true },
    "Severe Thunderstorm Watch": { icon: "/assets/weather/weather-icons-master/svg/wi-thunderstorm.svg", color: "text-amber-500", bg: "bg-amber-950/40", border: "border-amber-500/30", pulse: false },
    "Severe Weather Statement": { icon: "/assets/weather/weather-icons-master/svg/wi-lightning.svg", color: "text-amber-400", bg: "bg-slate-900/60", border: "border-amber-500/20", pulse: false },
    "Heat Advisory": { icon: "/assets/weather/weather-icons-master/svg/wi-hot.svg", color: "text-rose-600", bg: "bg-rose-950/30", border: "border-rose-600/30", pulse: false },
    "Excessive Heat Warning": { icon: "/assets/weather/weather-icons-master/svg/wi-hot.svg", color: "text-rose-500", bg: "bg-rose-950/50", border: "border-rose-500/60", pulse: true },
    "Flood Warning": { icon: "/assets/weather/weather-icons-master/svg/wi-flood.svg", color: "text-rose-500", bg: "bg-rose-950/40", border: "border-rose-500/40", pulse: true },
    "Flood Watch": { icon: "/assets/weather/weather-icons-master/svg/wi-flood.svg", color: "text-amber-500", bg: "bg-amber-950/30", border: "border-amber-500/20", pulse: false },
    "Special Weather Statement": { icon: "/assets/weather/weather-icons-master/svg/wi-cloudy-gusts.svg", color: "text-amber-400", bg: "bg-slate-900/60", border: "border-amber-400/20", pulse: false },
    "Default": { icon: "/assets/weather/weather-icons-master/svg/wi-alien.svg", color: "text-slate-400", bg: "bg-slate-900/40", border: "border-slate-800", pulse: false }
  };

useEffect(() => {
    let ws;
    let reconnectTimeout;

    const connectWebSocket = () => {
      const host = window.location.hostname || '192.168.4.183';
      ws = new WebSocket(`ws://${host}:8000/ws`);

      ws.onopen = () => {
        console.log("WebSocket Connected!");
        setConnected(true);
      };

      ws.onclose = () => {
        console.log("WebSocket Disconnected. Attempting to reconnect in 3 seconds...");
        setConnected(false);
        // Auto-reconnect automatically revives the dashboard after deployments/restarts
        reconnectTimeout = setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = (err) => {
        console.error("WebSocket Error!", err);
        ws.close();
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.update_type === 'calendar_sync') {
          setEvents(data.events);
          return;
        }
        setWeather((prev) => {
          if (data.update_type === 'lightning_strike') {
            const distance = parseFloat(data.distance_miles);
            let targetRing = 30;
            if (distance <= 5) targetRing = 5;
            else if (distance <= 10) targetRing = 10;
            else if (distance <= 15) targetRing = 15;
            else if (distance <= 20) targetRing = 20;
            else if (distance <= 25) targetRing = 25;

            return {
              ...prev,
              last_strike_distance: distance,
              last_strike_time: Date.now(),
              strike_trigger_ring: targetRing,
              lightning_strike_id: prev.lightning_strike_id + 1
            };
          }
          const next = { ...prev, ...data };
          if (data.update_type !== 'lightning_strike') {
            next.strike_trigger_ring = prev.strike_trigger_ring;
            next.lightning_strike_id = prev.lightning_strike_id;
          }
          const currentTemp = parseFloat(next.temperature_f);
          const currentWind = parseFloat(next.wind_speed_mph);
          const currentGust = parseFloat(next.wind_gust_mph);

          if (!isNaN(currentTemp)) {
            if (prev.high_temp === -999 || currentTemp > prev.high_temp) next.high_temp = currentTemp;
            if (prev.low_temp === 999 || currentTemp < prev.low_temp) next.low_temp = currentTemp;
          }
          if (!isNaN(currentWind) && currentWind > prev.high_wind) next.high_wind = currentWind;
          if (!isNaN(currentGust) && currentGust > prev.high_gust) next.high_gust = currentGust;
          
          return next;
        });
      };
    };

    connectWebSocket();

    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) {
        ws.onclose = null; // Prevent a loop if the component unmounts
        ws.close();
      }
    };
  }, []);
  useEffect(() => {
    if (weather.strike_trigger_ring) {
      const timer = setTimeout(() => {
        setWeather(prev => ({ ...prev, strike_trigger_ring: null }));
      }, 1200);
      return () => clearTimeout(timer);
    }
  }, [weather.strike_trigger_ring]);

  const getComfortLevel = (dewPointF) => {
    if (dewPointF === '--.-') return { text: 'Analyzing Air...', color: 'text-slate-500' };
    const dp = parseFloat(dewPointF);
    if (dp < 30)  return { text: 'L1: Welcome to the Desert', color: 'text-cyan-300' };
    if (dp < 40)  return { text: 'L2: Need Moisturizer', color: 'text-teal-400' };
    if (dp < 50)  return { text: 'L3: Finally Comfortable', color: 'text-emerald-400' };
    if (dp < 55)  return { text: 'L4: Wait is it nice out?', color: 'text-green-400' };
    if (dp < 60)  return { text: 'L5: Dry for Florida', color: 'text-yellow-300' };
    if (dp < 65)  return { text: 'L6: Actually not bad', color: 'text-amber-400' };
    if (dp < 70)  return { text: 'L7: Typical Florida', color: 'text-orange-400' };
    if (dp < 75)  return { text: 'L8: Shrek Swamp', color: 'text-orange-600' };
    if (dp < 80)  return { text: 'L9: Too Humid for Shrek', color: 'text-red-500' };
    return               { text: 'L10: Misery Soup', color: 'text-purple-500 font-extrabold animate-pulse' };
  };
  const comfort = getComfortLevel(weather.dew_point_f);

  const correctedArrowRotation = (parseFloat(weather.wind_direction_deg) + 180) % 360;

  const getActivityRatings = () => {
    const currentTemp = parseFloat(weather.temperature_f) || 72;
    const currentFeels = parseFloat(weather.feels_like_f) || currentTemp;
    const currentHumidity = parseFloat(weather.humidity_pct) || 50;
    const currentWind = parseFloat(weather.wind_speed_mph) || 0;
    const currentGust = parseFloat(weather.wind_gust_mph) || 0;
    const currentRainAccum = parseFloat(weather.rain_accumulation_day_in) || 0.0;
    const currentLightningDist = weather.last_strike_distance !== null ? parseFloat(weather.last_strike_distance) : 999;
    const currentMinsSinceStrike = weather.last_strike_time ? Math.floor((Date.now() - weather.last_strike_time) / 60000) : 999;

    const todayForecast = weather.forecast_daily_api?.[0] || { high: currentTemp, low: currentTemp, rain_pct: 0, icon: 'clear-day' };
    const fcTemp = (parseFloat(todayForecast.high) + parseFloat(todayForecast.low)) / 2;
    const fcRainChance = parseInt(todayForecast.rain_pct) || 0;

    const evaluateActivity = (temp, feels, humidity, wind, gust, rainAccum, lightningDist, minsSinceStrike, isForecast = false) => {
      let scores = { Walking: 10, Airbrushing: 10, "Yard Work": 10, Basketball: 10, Football: 10, Swimming: 10 };
      const hasRecentRain = rainAccum > 0 && rainAccum <= 0.15;
      const hasHeavyRecentRain = rainAccum > 0.15;
      const isLightningThreat = lightningDist <= 20 && minsSinceStrike <= 45;

      if (temp < 65) scores.Football -= Math.min((65 - temp) / 4, 3);
      if (temp > 75) scores.Football -= Math.min((temp - 75) / 3, 4);
      if (temp > 93) scores.Football -= 3;
      if (feels > 100) scores.Football = 0;
      if (wind > 15 || gust > 22) scores.Football -= 3;
      else if (temp > 82 && wind >= 4 && wind <= 12) scores.Football += 1;
      if (hasRecentRain) scores.Football -= 1;
      if (hasHeavyRecentRain) scores.Football -= 2.5;
      if (isForecast && fcRainChance > 60) scores.Football -= (fcRainChance / 20);

      if (temp < 62) scores.Basketball -= Math.min((62 - temp) / 3, 4);
      if (temp > 75) scores.Basketball -= Math.min((temp - 75) / 3, 4);
      if (temp > 91) scores.Basketball -= 3;
      if (feels > 98) scores.Basketball = 0;
      if (wind > 8) scores.Basketball -= 2;
      if (wind > 14 || gust > 18) scores.Basketball -= 4;
      if (hasRecentRain) scores.Basketball -= 2;
      if (rainAccum > 0.30) scores.Basketball = 0;
      if (isForecast && fcRainChance > 60) scores.Basketball -= (fcRainChance / 15);

      if (temp < 58) scores["Yard Work"] -= Math.min((58 - temp) / 4, 3);
      if (temp > 78) scores["Yard Work"] -= Math.min((temp - 78) / 3, 4);
      if (feels > 102) scores["Yard Work"] = 0;
      if (wind > 18 || gust > 25) scores["Yard Work"] -= 2;
      if (hasHeavyRecentRain) scores["Yard Work"] -= 3;
      if (isForecast && fcRainChance > 40) scores["Yard Work"] -= 4;

      if (temp < 60 || temp > 75) scores.Airbrushing -= Math.min(Math.abs(temp - 67) / 3, 4);
      if (humidity > 65) scores.Airbrushing -= 2;
      if (humidity > 75) scores.Airbrushing -= 3.5;
      if (humidity > 85) scores.Airbrushing -= 4.5;
      if (wind > 5 || gust > 8) scores.Airbrushing = 0;
      if (hasRecentRain || hasHeavyRecentRain) scores.Airbrushing -= 2;
      if (isForecast && fcRainChance > 15) scores.Airbrushing -= 5;

      if (temp < 60) scores.Walking -= Math.min((60 - temp) / 4, 3);
      if (temp > 85) scores.Walking -= Math.min((temp - 85) / 2, 6);
      if (feels > 98) scores.Walking -= 2;
      if (humidity > 80) scores.Walking -= 1.5;
      if (wind > 22) scores.Walking -= 3;
      if (rainAccum > 0.02) scores.Walking = 0;
      if (hasRecentRain) scores.Walking -= 2;
      if (isForecast && fcRainChance > 40) scores.Walking = 0;

      if (temp < 70) {
        scores.Swimming = 0;
      } else {
        scores.Swimming = Math.min(2 + ((temp - 70) * 0.4), 10);
      }
      if (isLightningThreat) scores.Swimming = 0;
      if (isForecast && fcRainChance > 60) scores.Swimming -= 4;

      const clamp = (val) => Math.min(Math.max(Math.round(val), 0), 10);
      return Object.keys(scores).reduce((acc, key) => {
        acc[key] = clamp(scores[key]);
        return acc;
      }, {});
    };

    const currentMetrics = evaluateActivity(currentTemp, currentFeels, currentHumidity, currentWind, currentGust, currentRainAccum, currentLightningDist, currentMinsSinceStrike, false);
    const forecastMetrics = evaluateActivity(fcTemp, fcTemp, currentHumidity, currentWind, currentGust, currentRainAccum, currentLightningDist, currentMinsSinceStrike, true);

    return Object.keys(currentMetrics).map(name => ({
      name,
      currentScore: currentMetrics[name],
      forecastScore: forecastMetrics[name]
    }));
  };

  const activityRatings = getActivityRatings();

  const getPressureDiagnostics = () => {
    const current = parseFloat(weather.pressure_inhg) || 29.92;
    let tier = 'Normal Range';
    let tierColor = 'text-slate-300';
    
    if (current >= 30.20) { 
      tier = 'High System'; 
      tierColor = 'text-cyan-400'; 
    } else if (current < 29.80) {
      if (current < 28.94) { 
        tier = 'Major Hurricane'; 
        tierColor = 'text-red-500 font-black animate-pulse'; 
      } else if (current < 29.23) {
        tier = 'Hurricane Depr.'; 
        tierColor = 'text-orange-500 font-extrabold'; 
      } else if (current < 29.53) {
        tier = 'Tropical Storm'; 
        tierColor = 'text-amber-500 font-bold'; 
      } else if (current < 29.71) {
        tier = 'Tropical Depr.'; 
        tierColor = 'text-yellow-400'; 
      } else { 
        tier = 'Low Pressure'; 
        tierColor = 'text-purple-400'; 
      }
    }
    return { tier, tierColor };
  };
  const getRainStatus = (rate) => {
    const r = parseFloat(rate) || 0.0;
    if (r === 0) return { text: "Not Raining", color: "text-emerald-500" };
    if (r < 0.1) return { text: "Light Rain", color: "text-blue-300" };
    if (r < 0.3) return { text: "Moderate Rain", color: "text-blue-400" };
    return { text: "Heavy Rain", color: "text-blue-500 font-bold animate-pulse" };
  };
  
  const rainStatus = getRainStatus(weather.rain_rate_in_hr);
  
  const [dashboardTasksArray, setDashboardTasksArray] = useState([]);
  const [sleeperPayloadState, setSleeperPayloadState] = useState({ mode: "disabled" });

  const fetchTasks = async () => {
    try {
      const host = window.location.hostname || '192.168.4.183';
      const res = await fetch(`http://${host}:8000/api/tasks`);
      if (res.ok) {
        const data = await res.json();
        setDashboardTasksArray(data);
      }
    } catch (err) {
      console.error("❌ Failed syncing chores matrix", err);
    }
  };

  const fetchSleeperData = async () => {
    try {
      const host = window.location.hostname || '192.168.4.183';
      const res = await fetch(`http://${host}:8000/api/sleeper`);
      if (res.ok) {
        const data = await res.json();
        setSleeperPayloadState(data);
      }
    } catch (err) {
      console.error("❌ Failed syncing Sleeper payload", err);
    }
  };

  useEffect(() => {
    const initializeDashboardModules = async () => {
      await fetchTasks();
      await fetchSleeperData();
    };
    initializeDashboardModules();
    
    const interval = setInterval(() => {
      fetchTasks();
      fetchSleeperData();
    }, 300000);
    
    return () => clearInterval(interval);
  }, []);

  const triggerManualSocketPull = () => {
    fetchTasks();
  };

  const pressDiag = getPressureDiagnostics();

  return (
    <div className="min-h-screen bg-black text-slate-100 p-4 font-sans tracking-tight overflow-hidden select-none">
      
      {/* HEADER STATUS BAR */}
      <header className="flex justify-between items-center border-b border-purple-950/40 pb-3 mb-4">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 w-full">
          <div>
            <div className="flex items-center gap-3">
              <h1 
                className="text-lg font-black uppercase tracking-wider text-slate-100 font-mono cursor-pointer transition-colors hover:text-purple-400"
                onClick={() => setEasterEggActive(!easterEggActive)}
                title="Tap to toggle system overrides"
              >
                Howls Moving Dashboard
              </h1>
              <div className="flex items-center gap-2 overflow-x-auto pl-2 py-0.5 max-w-[250px] sm:max-w-[400px] no-scrollbar">
                {weather?.alerts && weather.alerts.length > 0 ? (
                  weather.alerts.map((alert, idx) => {
                    const config = ALERT_CONFIGS[alert.event.trim()] || ALERT_CONFIGS["Default"];
                    return (
                      <WeatherAlertBadge 
                        key={alert.id || idx} 
                        alert={alert} 
                        config={config} 
                      />
                    );
                  })
                ) : (
                  <span className="text-[9px] font-mono font-black tracking-widest text-emerald-500/80 bg-emerald-950/20 border border-emerald-900/40 rounded-full px-2.5 py-0.5 uppercase flex items-center gap-1.5 animate-pulse">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                    No Active Hazards
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 text-[10px] font-mono font-bold text-slate-500 uppercase mt-0.5 flex-wrap">
              <span>Live Station Feed</span>
              <span className="text-slate-800">|</span>
              <div 
                className="flex items-center gap-1 cursor-pointer hover:bg-purple-900/20 px-1.5 py-0.5 rounded transition-colors"
                onClick={() => setIsVerseModalOpen(true)}
                title="Tap to read full passage"
              >
                <span className="text-purple-500/90 font-black">Verse:</span>
                <span className="text-slate-300 normal-case font-semibold truncate max-w-[200px] sm:max-w-[300px]">
                  {weather.daily_verse?.reference} NLT: "{weather.daily_verse?.text}"
                </span>
              </div>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2 bg-slate-950 border border-purple-900/30 px-3 py-1 rounded-full shrink-0">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            {connected ? 'Active' : 'Offline'}
          </span>
          <span className={`h-2.5 w-2.5 rounded-full ${
            connected ? 'bg-blue-500 shadow-[0_0_8px_#3b82f6]' : 'bg-rose-500 shadow-[0_0_8px_#f43f5e]'
          }`} />
        </div>
      </header>  

      <div className="grid grid-cols-12 gap-3 h-[calc(100vh-85px)] items-stretch">
        
        {/* COL 1: DAILY OUTLOOK */}
        <div className="col-span-2 flex flex-col h-full max-w-[100px]">
          <ForecastStripWidget weather={weather} />
        </div>

        {/* COL 2: MAIN CENTER METRICS */}
        <div className="col-span-6 flex flex-col gap-3 overflow-y-auto pr-0.5 max-h-full content-start no-scrollbar">
          
          <div className="grid grid-cols-2 gap-3">
            {/* TEMPERATURE BLOCK */}
            <div className="col-span-2 bg-slate-950 border border-blue-950/40 p-4 rounded-2xl flex flex-col justify-between shadow-2xl relative overflow-hidden">
              <div className="grid grid-cols-12 gap-2 items-center">
                {(() => {
                  const minT = 0; const maxT = 120;
                  const airTemp = parseFloat(weather.temperature_f) || 70.0;
                  const feelsTemp = parseFloat(weather.feels_like_f) || 70.0;
                  const airPct = Math.min(Math.max(((airTemp - minT) / (maxT - minT)) * 100, 0), 100);
                  const feelsPct = Math.min(Math.max(((feelsTemp - minT) / (maxT - minT)) * 100, 0), 100);
                  const tempDelta = Math.abs(airTemp - feelsTemp);
                  const isHeatIndex = feelsTemp > airTemp;
                  const overlayColor = isHeatIndex ? 'bg-red-500/20' : 'bg-blue-500/20';
                  const pulseClass = tempDelta >= 2.0 ? 'animate-pulse' : '';
                  const feelsColorClass = isHeatIndex ? 'text-rose-500' : 'text-cyan-400';
                  const activeIconKey = easterEggActive ? 'alien' : (weather.icon_api || 'clear-day');
                  const currentAsset = easterEggActive ? weatherAssets['alien'] : (weatherAssets[activeIconKey] || weatherAssets['default']);
                  const humanConditions = weather.conditions || 'Steady';

                  return (
                    <>
                      <div className="col-span-4 flex flex-col justify-center gap-2 text-left pl-1">
                        <div>
                          <span className="text-[9px] font-bold uppercase tracking-widest text-slate-500 block">Air Temp</span>
                          <div className="flex items-baseline gap-0.5">
                            <span className="text-2xl font-black font-mono tracking-tighter text-slate-100">{airTemp.toFixed(1)}</span>
                            <span className="text-xs font-bold text-slate-400">°F</span>
                          </div>
                        </div>
                        <div>
                          <span className="text-[9px] font-bold uppercase tracking-widest text-slate-500 block">Feels Like</span>
                          <div className="flex items-baseline gap-0.5">
                            <span className={`text-2xl font-black font-mono tracking-tighter ${feelsColorClass}`}>{feelsTemp.toFixed(1)}</span>
                            <span className="text-xs font-bold text-slate-400">°F</span>
                          </div>
                        </div>
                      </div>

                      <div className="col-span-3 flex justify-center items-center h-28 relative">
                        <div className="w-4 h-full rounded-full bg-gradient-to-t from-blue-950 via-blue-800 via-emerald-950 via-amber-950 to-red-950/60 relative border border-slate-900/80 shadow-inner">
                          {tempDelta > 0 && (
                            <div 
                              style={{ bottom: `${Math.min(airPct, feelsPct)}%`, height: `${tempDelta}%` }}
                              className={`absolute left-0 right-0 w-full rounded-sm transition-all duration-1000 ease-out ${overlayColor} ${pulseClass}`}
                            />
                          )}
                          <div style={{ bottom: `${airPct}%` }} className="absolute left-1/2 -translate-x-1/2 mb-[-1px] w-5 h-0.5 bg-white rounded-full shadow-[0_0_4px_white] border border-black/40 transition-all duration-1000 z-20" />
                          <div style={{ bottom: `${feelsPct}%` }} className={`absolute left-1/2 -translate-x-1/2 mb-[-1px] w-5 h-0.5 rounded-full shadow-lg border border-black/40 transition-all duration-1000 z-10 ${isHeatIndex ? 'bg-red-500' : 'bg-blue-400'}`} />
                        </div>
                      </div>
                      
                      <div className="col-span-5 flex flex-col items-center justify-center relative pr-1">
                        <div className="w-20 h-20 rounded-full bg-slate-950 relative overflow-hidden flex items-center justify-center border border-slate-900/40 shadow-xl">
                          {easterEggActive ? (
                            <SvgWeatherIcon icon="alien" className="w-14 h-14" />
                          ) : (
                            <img 
                              src={currentAsset} 
                              alt={humanConditions} 
                              className="w-full h-full object-cover opacity-90 select-none pointer-events-none"
                              style={{ WebkitMaskImage: 'radial-gradient(circle, rgba(0,0,0,1) 60%, rgba(0,0,0,0) 100%)' }}
                            />
                          )}
                          <div className="absolute inset-0 w-full h-full rounded-full shadow-[inset_0_0_10px_rgba(2,6,23,0.9)]" />
                        </div>
                        
                        <div className="flex flex-col items-center justify-center mt-1.5 w-full px-2">
                          <div className="flex items-center justify-center gap-1.5 w-full">
                            <SvgWeatherIcon icon={activeIconKey} className="w-5 h-5 shrink-0" />
                            <span 
                              className="text-[10px] font-black uppercase tracking-wider text-slate-300 text-center leading-tight break-words" 
                              style={{ textWrap: 'balance' }}
                            >
                              {easterEggActive ? "ALIEN INVASION" : humanConditions}
                            </span>
                          </div>
                        </div>
                      </div>
                    </>
                  );
                })()}

              </div>

              <div className="mt-2 pt-2 border-t border-slate-900 text-[11px] font-semibold uppercase tracking-wider text-slate-500 flex justify-between items-center">
                <div>Comfort: <span className={`font-bold ml-1 ${comfort.color}`}>{comfort.text}</span></div>
                <div className="text-[9px] font-mono text-slate-600">0° - 120°</div>
              </div>
            </div>

            {/* WIND VECTOR */}
            <div className="bg-slate-950 border border-purple-950/40 p-3 rounded-2xl flex flex-col items-center justify-center relative shadow-2xl">
              <span className="absolute top-2 left-3 text-[9px] font-bold uppercase tracking-widest text-purple-400">Wind</span>
              
              <svg className="w-24 h-24 relative mt-2" viewBox="0 0 200 200">
                <circle cx="100" cy="100" r="84" className="stroke-purple-950/20" strokeWidth="2" fill="transparent" />
                <circle cx="100" cy="100" r="80" className="stroke-slate-900" strokeWidth="4" fill="transparent" />
                
                <text x="100" y="32" textAnchor="middle" className="fill-purple-400 text-[16px] font-black">N</text>
                <text x="174" y="104" textAnchor="middle" className="fill-slate-600 text-[11px] font-bold">E</text>
                <text x="100" y="178" textAnchor="middle" className="fill-slate-600 text-[11px] font-bold">S</text>
                <text x="26" y="104" textAnchor="middle" className="fill-slate-600 text-[11px] font-bold">W</text>

                <g style={{ transform: `rotate(${correctedArrowRotation}deg)`, transformOrigin: '100px 100px' }} className="transition-transform duration-700 ease-out">
                  <polygon points="100,6 108,24 100,20 92,24" className="fill-cyan-400 drop-shadow-[0_0_6px_#22d3ee]" />
                </g>
              </svg>

              <div className="absolute text-center mt-3">
                <div className="leading-none">
                  <span className={`text-xl font-black tracking-tighter ${getWindColor(weather.wind_speed_mph)}`}>
                    {weather.wind_speed_mph}
                  </span>
                  <span className="text-[8px] font-bold text-slate-500 uppercase ml-0.5">mph</span>
                </div>
                <div className="text-[7px] font-semibold text-slate-400 tracking-tight mt-0.5">
                  G: <span className="text-rose-400 font-bold">{weather.wind_gust_mph}</span>
                </div>
              </div>
            </div>

            {/* BAROMETER */}
            <div className="bg-slate-950 border border-purple-950/40 p-3 rounded-2xl flex flex-col items-center justify-center relative shadow-2xl">
              <span className="absolute top-2 left-3 text-[9px] font-bold uppercase tracking-widest text-purple-400">Pressure</span>
              
              <svg className="w-24 h-24 mt-2" viewBox="0 0 200 200">
                <defs>
                  <linearGradient id="wunderGradCompact" x1="0%" y1="100%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#a855f7" />
                    <stop offset="50%" stopColor="#2563eb" />
                    <stop offset="100%" stopColor="#06b6d4" />
                  </linearGradient>
                </defs>
                <circle 
                  cx="100" cy="100" r="75" 
                  stroke="url(#wunderGradCompact)" strokeWidth="12" fill="transparent"
                  transform="rotate(135 100 100)"
                  strokeDasharray={`${2 * Math.PI * 75 * 0.75} ${2 * Math.PI * 75 * 0.25}`}
                  strokeLinecap="round"
                />
                
                {[
                  { value: 28.94, color: 'stroke-red-500' },
                  { value: 29.23, color: 'stroke-orange-500' },
                  { value: 29.53, color: 'stroke-yellow-400' },
                  { value: 29.71, color: 'stroke-purple-400' },
                  { value: 29.80, color: 'stroke-slate-400' },
                  { value: 30.20, color: 'stroke-cyan-400' }
                ].map((t, idx) => {
                  const pct = (t.value - 28.0) / (31.0 - 28.0);
                  const angle = 135 + (pct * 270);
                  return (
                    <line key={idx} x1="160" y1="100" x2="177" y2="100" className={`${t.color} shadow-lg`} strokeWidth="4" transform={`rotate(${angle} 100 100)`} />
                  );
                })}

                {(() => {
                  const pVal = parseFloat(weather.pressure_inhg) || 29.92;
                  const pct = Math.min(Math.max((pVal - 28.0) / (31.0 - 28.0), 0), 1);
                  const bubbleAngle = 135 + (pct * 270);
                  const bubbleRad = (bubbleAngle * Math.PI) / 180;
                  return (
                    <circle 
                      cx={100 + 75 * Math.cos(bubbleRad)} 
                      cy={100 + 75 * Math.sin(bubbleRad)} 
                      r="9" className="fill-white stroke-slate-950" strokeWidth="3"
                    />
                  );
                })()}
              </svg>

              <div className="absolute text-center mt-13 flex flex-col items-center">
                <span className="text-base font-black font-mono tracking-tighter text-slate-100 block leading-tight">
                  {parseFloat(weather.pressure_inhg).toFixed(2)}
                </span>
                
                <div className="flex justify-center mt-0.5">
                  <img 
                    src={getPressureTrendIcon(weather.pressure_trend_api)} 
                    alt={weather.pressure_trend_api} 
                    className="w-4 h-4 invert opacity-70"
                  />
                </div>

                <span className={`text-[7px] font-black uppercase tracking-wider ${pressDiag.tierColor} mt-0.5`}>
                  {pressDiag.tier.split(' ')[0]}
                </span>
              </div>
            </div>

            {/* ACTIVITY PLANNER */}
            <div className="col-span-2 bg-slate-950 border border-purple-950/40 p-3 rounded-2xl shadow-2xl flex flex-col justify-between">
              <div className="grid grid-cols-3 gap-2 overflow-y-auto max-h-[140px] custom-scrollbar">
                {activityRatings.map((activity) => (
                  <ActivityStatusWidget 
                    key={activity.name}
                    name={activity.name}
                    currentScore={activity.currentScore}
                    forecastScore={activity.forecastScore}
                    weather={weather}
                  />
                ))}
              </div>
              <div className="flex justify-between border-t border-slate-900 pt-2 mt-2 text-[8px] font-semibold uppercase font-mono text-slate-600">
                <span>Tap cells for diagnostics</span>
                <span>Matrix v2.2</span>
              </div>
            </div>

            {/* RAIN GAUGE */}
            <div className="bg-slate-950 border border-slate-900 p-4 rounded-2xl shadow-2xl flex flex-col justify-between col-span-2">
              <div className="grid grid-cols-12 gap-3 items-center">
                <div className="col-span-3 text-left">
                  <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500 block">Todays Rain</span>
                  <div className="flex items-baseline gap-0.5 mt-0.5">
                    <span className="text-2xl font-black font-mono tracking-tighter text-slate-100">
                      {(parseFloat(weather.rain_accumulation_day_in) || 0.0).toFixed(2)}
                    </span>
                    <span className="text-xs font-bold text-slate-500 font-mono">in</span>
                  </div>
                </div>

                <div className="col-span-3 flex items-center justify-center">
                  <div className="flex items-center gap-1 h-14 select-none relative">
                    <div className="flex flex-col justify-between h-full text-[8px] font-mono font-black text-slate-600 text-right w-4 leading-none pr-0.5">
                      <span>2.0</span>
                      <span>1.0</span>
                      <span>0.0</span>
                    </div>
                    <div className="w-5 h-full bg-slate-950 rounded border border-slate-900 overflow-hidden relative shadow-inner">
                      <div 
                        style={{ height: `${Math.min(((parseFloat(weather.rain_accumulation_day_in) || 0) / 2.0) * 100, 100)}%` }} 
                        className="absolute bottom-0 left-0 right-0 w-full bg-gradient-to-t from-blue-600 to-blue-400 transition-all duration-500"
                      />
                    </div>
                  </div>
                </div>

                <div className="col-span-3 text-left">
                  <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500 block">Current Rain Chance</span>
                  <div className="flex items-baseline gap-0.5 mt-0.5">
                    <span className="text-2xl font-black font-mono tracking-tight text-blue-400">
                      {parseInt(weather.rain_chance_current) || 0}
                    </span>
                    <span className="text-xs font-bold text-blue-600 font-mono">%</span>
                  </div>
                </div>

                <div className="col-span-3 flex flex-col gap-0.5 text-[8px] font-mono">
                  {[
                    { label: "Morning", pct: parseInt(weather.rain_chance_morning) || 0 },
                    { label: "Afternoon", pct: parseInt(weather.rain_chance_afternoon) || 0 },
                    { label: "Evening", pct: parseInt(weather.rain_chance_evening) || 0 },
                    { label: "Overnight", pct: parseInt(weather.rain_chance_overnight) || 0 }
                  ].map((block) => (
                    <div key={block.label} className="flex items-center justify-between bg-slate-900/30 border border-slate-900/60 rounded px-1 py-0.5 relative overflow-hidden h-[15px]">
                      <div 
                        style={{ width: `${block.pct}%` }} 
                        className="absolute left-0 top-0 bottom-0 bg-blue-500/20 transition-all duration-500 pointer-events-none"
                      />
                      <span className="text-slate-300 relative z-10 font-bold">{block.label}</span>
                      <span className={`relative z-10 font-black ${block.pct > 0 ? 'text-blue-400' : 'text-slate-600'}`}>{block.pct}%</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="border-t border-slate-900 pt-1.5 mt-2 flex justify-between items-center text-[8px] font-black uppercase font-mono tracking-wider">
                <span className="text-slate-600">Sensor: <span className={rainStatus.color}>{rainStatus.text}</span></span>
                <span className="text-slate-400">Rate: <span className="text-slate-200">{(parseFloat(weather.rain_rate_in_hr) || 0.0).toFixed(2)}</span> in/h</span>
              </div>
            </div>

            {/* LIGHTNING RADAR */}
            <div className="col-span-2">
              <LightningRadarWidget weather={weather} />
            </div>

          </div>

          {/* DISPLAY BOARD - GOOGLE PHOTOS PORTAL */}
          <div className="flex-1 w-full mt-2 relative">
            <GooglePhotosWidget />
          </div>

        </div>

        {/* COL 3: RIGHT SIDE COMMAND CHANNELS */}
        <div className="col-span-4 flex flex-col gap-3 h-full min-h-0">
          
          <CompactChronoHeader />

          <div className="flex-1 min-h-0 relative">
            <DashboardCalendarWidget events={events} />
          </div>
              
          {/* STACKED AGENDA & SLEEPER WIDGETS */}
          <div className="flex flex-col gap-3 shrink-0 h-[48%]">
            <div className="flex-1 h-full relative">
              <LowerModuleTasks tasks={dashboardTasksArray} onRefresh={triggerManualSocketPull} />
            </div>
            <div className="flex-1 h-full relative">
              <LowerModuleSleeper data={sleeperPayloadState} />
            </div>
          </div>
        </div>
        
      </div>

      {/* FULL SCRIPTURE MODAL OVERLAY */}
      {isVerseModalOpen && (
        <div 
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4"
          onClick={() => setIsVerseModalOpen(false)}
        >
          <div 
            className="bg-slate-950 border border-purple-900/40 w-full max-w-md p-6 rounded-2xl shadow-2xl font-mono text-slate-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center border-b border-slate-900 pb-3 mb-4">
              <h4 className="text-sm font-black uppercase tracking-wider text-purple-400 flex items-center gap-2">
                📖 Daily Scripture • NLT
              </h4>
              <button onClick={() => setIsVerseModalOpen(false)} className="text-slate-500 hover:text-slate-300 text-lg">✕</button>
            </div>
            
            <p className="text-lg font-serif italic text-slate-300 leading-relaxed mb-4 max-h-[50vh] overflow-y-auto custom-scrollbar pr-2">
              "{weather.daily_verse?.text}"
            </p>
            
            <p className="text-right text-sm font-bold text-slate-400">
              — {weather.daily_verse?.reference}
            </p>
            
            <button
              onClick={() => setIsVerseModalOpen(false)}
              className="mt-6 w-full py-2.5 bg-slate-900 text-slate-400 font-bold text-xs rounded-xl border border-slate-800 uppercase hover:bg-slate-800 transition-colors tracking-widest"
            >
              Close Passage
            </button>
          </div>
        </div>
      )}

    </div>
  );
}

// =======================================================================
// WIDGET SUBSYSTEMS
// =======================================================================
function ForecastStripWidget({ weather }) {
  const dailyForecasts = weather.forecast_daily_api || [
    { icon: 'clear-day', high: 92, low: 75, rain_pct: 10 },
    { icon: 'partly-cloudy-day', high: 90, low: 76, rain_pct: 25 },
    { icon: 'rainy', high: 86, low: 74, rain_pct: 80 },
    { icon: 'thunderstorm', high: 85, low: 73, rain_pct: 95 },
    { icon: 'partly-cloudy-day', high: 89, low: 75, rain_pct: 40 },
    { icon: 'clear-day', high: 93, low: 77, rain_pct: 5 },
    { icon: 'clear-day', high: 94, low: 76, rain_pct: 0 }
  ];

  const getDynamicDateFields = (offset) => {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    return { dayName: days[d.getDay()], dateString: `${d.getMonth() + 1}/${d.getDate()}` };
  };

  return (
    <div className="bg-slate-950/40 border border-slate-900 h-full p-2 rounded-2xl flex flex-col justify-between shadow-2xl backdrop-blur-sm">
      <div className="flex flex-col justify-between h-full gap-0.5">
        {dailyForecasts.slice(0, 7).map((day, idx) => {
          const { dayName, dateString } = getDynamicDateFields(idx);
          const rainPct = parseInt(day.rain_pct) || 0;
          const isToday = idx === 0;

          return (
            <div 
              key={idx} 
              className={`flex flex-col justify-center py-1 border-b border-slate-900/60 last:border-0 ${
                isToday ? 'bg-blue-950/10 border-l-2 border-blue-500 pl-1' : ''
              }`}
            >
              <div className="flex items-center gap-1">
                <span className={`text-[20px] font-black uppercase font-mono ${isToday ? 'text-blue-400' : 'text-slate-200'}`}>
                  {dayName}
                </span>
                <span className="text-[16px] font-bold text-slate-500 font-mono">{dateString}</span>
              </div>
              <div className="flex items-baseline gap-1 font-mono leading-none my-0.5">
                <span className="text-2xl font-black text-slate-100">{Math.round(day.high)}°</span>
                <span className="text-[20px] font-bold text-slate-500">{Math.round(day.low)}°</span>
              </div>
              <div className="flex items-center justify-between text-[18px] font-mono mt-1 pr-1">
                <SvgWeatherIcon icon={day.icon} className="w-10 h-10 shrink-0" />
                <span className={rainPct > 15 ? 'text-cyan-400 font-extrabold' : 'text-slate-700'}>{rainPct}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DashboardCalendarWidget({ events }) {
  const formatEventTime = (isoString) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
  };

  const formatAgendaGroupDate = (dateStr) => {
    const d = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date();
    tomorrow.setDate(today.getDate() + 1);
    if (d.toDateString() === today.toDateString()) return 'Today';
    if (d.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
    return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
  };

  const getMicroCalendarDays = () => {
    const days = [];
    const today = new Date();
    const startSunday = new Date(today);
    startSunday.setDate(today.getDate() - today.getDay());
    startSunday.setHours(0, 0, 0, 0);
    for (let i = 0; i < 14; i++) {
      const nextDay = new Date(startSunday);
      nextDay.setDate(startSunday.getDate() + i);
      days.push(nextDay);
    }
    return days;
  };

  const microDays = getMicroCalendarDays();
  const todayStr = new Date().toDateString();
  const sortedEvents = [...events].sort((a, b) => new Date(a.start) - new Date(b.start));
  const activeUpcomingEvents = sortedEvents.filter(e => new Date(e.start) >= new Date().setHours(0,0,0,0));

  return (
    <div className="h-full w-full overflow-y-auto custom-scrollbar bg-slate-950 border border-slate-900/60 p-3 rounded-2xl shadow-xl flex flex-col absolute inset-0">
      <div className="flex justify-between items-center border-b border-slate-900 pb-2 mb-2 shrink-0">
        <div>
          <span className="text-[9px] font-black uppercase tracking-widest text-blue-400">Schedule Horizon</span>
        </div>
        <span className="text-[8px] font-mono bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full border border-blue-500/20 font-bold">
          {activeUpcomingEvents.length} Entries
        </span>
      </div>

      <div className="grid grid-cols-7 gap-0.5 bg-slate-900/20 p-1 rounded-xl border border-slate-900/50 mb-2 text-center text-[9px] shrink-0">
        {microDays.map((date, idx) => {
          const dateStr = date.toDateString();
          const isToday = dateStr === todayStr;
          const dayEvents = events.filter(e => new Date(e.start).toDateString() === dateStr);

          return (
            <div key={idx} className={`flex flex-col items-center py-0.5 rounded ${isToday ? 'bg-blue-500 font-black shadow-md' : 'hover:bg-slate-900/60'}`}>
              <span className={isToday ? 'text-blue-100' : 'text-slate-500'}>{date.toLocaleDateString([], { weekday: 'narrow' })}</span>
              <span className={`font-mono font-bold ${isToday ? 'text-white' : 'text-slate-300'}`}>{date.getDate()}</span>
              <div className="flex gap-0.5 justify-center items-center h-1 w-full overflow-hidden">
                {dayEvents.slice(0, 2).map((ev, eIdx) => (
                  <span key={eIdx} style={{ backgroundColor: isToday ? '#white' : (ev.color || '#3b82f6') }} className="w-1 h-1 rounded-full shrink-0" />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto pr-0.5 space-y-2 custom-scrollbar text-xs relative">
        {activeUpcomingEvents.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-600 py-6 text-[10px]">No upcoming entries listed</div>
        ) : (
          Object.entries(
            activeUpcomingEvents.reduce((groups, event) => {
              const dateKey = new Date(event.start).toDateString();
              if (!groups[dateKey]) groups[dateKey] = [];
              groups[dateKey].push(event);
              return groups;
            }, {})
          ).map(([dateStr, dayEvents]) => (
            <div key={dateStr} className="space-y-1">
              <div className="sticky top-0 bg-slate-950/90 py-0.5 flex items-center gap-1 z-10 text-[9px] font-mono text-slate-400">
                <span>{formatAgendaGroupDate(dateStr)}</span>
                <div className="h-px bg-slate-900 flex-1" />
              </div>
              <div className="grid gap-1">
                {dayEvents.map((ev) => (
                  <div key={ev.id} style={{ borderLeftColor: ev.color || '#3b82f6' }} className="border-l-2 bg-slate-900/20 border border-slate-900 p-2 rounded-lg flex items-center justify-between gap-2">
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="font-bold text-slate-200 truncate text-[11px]">{ev.summary}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0 text-[10px]">
                      {ev.forecast && <span className="font-mono font-black text-slate-400">{ev.forecast.temp}°</span>}
                      {ev.is_all_day ? (
                        <span className="text-[8px] bg-slate-950 text-slate-500 px-1 rounded border border-slate-900 font-mono">ALL</span>
                      ) : (
                        <span className="font-mono text-blue-400 font-bold">{formatEventTime(ev.start).replace(':00', '')}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function CompactChronoHeader() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="bg-slate-950 border border-slate-900/60 px-4 py-2 rounded-xl flex items-center justify-between shadow-lg shrink-0">
      <div className="flex flex-col">
        <span className="text-[8px] font-black tracking-widest text-slate-500 uppercase">System Time</span>
        <span className="text-[20px] font-mono font-black text-violet-600 leading-none mt-0.5">
          {time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })}
        </span>
      </div>
      <div className="flex flex-col text-right">
        <span className="text-[8px] font-black tracking-widest text-blue-400 uppercase">Date</span>
        <span className="text-xs font-bold text-purple-400 mt-0.5">
          {time.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}
        </span>
      </div>
    </div>
  );
}

export function LowerModuleTasks({ tasks, onRefresh }) {
  const [selectedTask, setSelectedTask] = useState(null);

  const handleCompleteTask = async (taskId, e) => {
    e.stopPropagation();
    try {
      const host = window.location.hostname || '192.168.4.183';
      const res = await fetch(`http://${host}:8000/api/tasks/complete/${taskId}`, { method: 'POST' });
      if (res.ok) onRefresh();
    } catch (err) {
      console.error("Failed executing chore complete action", err);
    }
  };

  const getTaskTag = (task) => {
    if (!task.due_date_str) return null;
    const [year, month, day] = task.due_date_str.split('-').map(Number);
    const localDue = new Date(year, month - 1, day);
    const today = new Date();
    today.setHours(0,0,0,0); localDue.setHours(0,0,0,0);
    const diffDays = Math.round((localDue.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

    let label = diffDays <= 0 ? "Today" : diffDays === 1 ? "Tomor" : localDue.toLocaleDateString('en-US', { weekday: 'short' });
    let styleClass = diffDays <= 0 ? "bg-sky-950/60 border-sky-500/50 text-sky-400" : "bg-purple-950/60 border-purple-500/50 text-purple-400";

    return <span className={`text-[8px] font-mono font-black uppercase px-1 py-0.5 rounded border ${styleClass} shrink-0`}>{label}</span>;
  };

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-2.5 flex flex-col absolute inset-0 w-full h-full">
      <h3 className="text-[11px] font-black font-mono uppercase tracking-wider text-slate-400 mb-2 shrink-0">📋 Tasks</h3>
      <div className="flex-1 overflow-y-auto space-y-1 pr-0.5 custom-scrollbar text-[11px] relative">
        {tasks.length === 0 ? (
          <div className="text-center text-slate-600 mt-6 italic text-[10px]">House clean!</div>
        ) : (
          tasks.map(t => (
            <div key={t.id} onClick={() => setSelectedTask(t)} className="flex items-center justify-between p-1.5 bg-slate-950/50 border border-slate-900 rounded-lg cursor-pointer">
              <div className="flex items-center gap-2 min-w-0">
                <button onClick={(e) => handleCompleteTask(t.id, e)} className="w-3 h-3 rounded-full border border-slate-700 flex items-center justify-center shrink-0">
                  <span className="w-1 h-1 rounded-full bg-transparent hover:bg-green-500" />
                </button>
                <span className="text-slate-200 truncate max-w-[120px] font-medium">{t.title}</span>
              </div>
              {getTaskTag(t)}
            </div>
          ))
        )}
      </div>

      {selectedTask && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setSelectedTask(null)}>
          <div className="bg-slate-950 border border-slate-800 p-4 rounded-xl max-w-xs w-full font-mono text-[11px]" onClick={e => e.stopPropagation()}>
            <h4 className="font-black text-slate-100 mb-2 truncate">{selectedTask.title}</h4>
            <p className="text-slate-400 bg-slate-900/60 p-2 rounded-lg border border-slate-900 min-h-[40px] whitespace-pre-wrap">{selectedTask.notes || "No description provided."}</p>
            <button onClick={() => setSelectedTask(null)} className="mt-3 w-full py-1 bg-slate-900 text-slate-300 rounded-lg font-bold border border-slate-800">Close</button>
          </div>
        </div>
      )}
    </div>
  );
}

export function LowerModuleSleeper({ data }) {
  const [activeMatchup, setActiveMatchup] = useState(null);
  if (!data || data.mode === "disabled") return null;

  if (data.mode === "draft") {
    const draftDate = new Date(data.draft_start);
    const daysLeft = Math.max(0, Math.floor((data.draft_start - Date.now()) / (1000 * 60 * 60 * 24)));
    return (
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-2.5 flex flex-col justify-center items-center text-center font-mono absolute inset-0 w-full h-full">
        <h4 className="text-[10px] font-black uppercase text-slate-400 truncate w-full">{data.name}</h4>
        <div className="text-xl font-black text-cyan-400 mt-1 mb-0.5">{daysLeft} Days</div>
        <div className="text-[9px] text-slate-300 font-bold mb-1">
          {draftDate.toLocaleDateString()} @ {draftDate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
        </div>
        <p className="text-[8px] text-slate-500 uppercase tracking-widest font-bold">Until Live Draft</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-2.5 flex flex-col absolute inset-0 w-full h-full">
      <h3 className="text-[11px] font-black font-mono uppercase tracking-wider text-slate-400 mb-2 flex justify-between shrink-0">
        <span>🏆 Sleeper W{data.week}</span>
      </h3>
      <div className="flex-1 overflow-y-auto space-y-1 pr-0.5 custom-scrollbar text-[11px] relative">
        {data.matchups?.map((match, idx) => {
          const teamA = match[0]; const teamB = match[1];
          return (
            <div key={idx} onClick={() => setActiveMatchup({ teamA, teamB })} className="p-1.5 bg-slate-950/50 border border-slate-900 rounded-lg cursor-pointer space-y-0.5">
              <div className="flex justify-between">
                <span className="font-bold text-slate-200 truncate max-w-[120px]">{teamA.owner_name}</span>
                <span className="font-mono text-slate-400 font-bold">{teamA.points.toFixed(1)}</span>
              </div>
              <div className="text-[7px] text-center text-slate-700 font-black leading-none">— VS —</div>
              <div className="flex justify-between">
                <span className="font-bold text-slate-200 truncate max-w-[120px]">{teamB.owner_name}</span>
                <span className="font-mono text-slate-400 font-bold">{teamB.points.toFixed(1)}</span>
              </div>
            </div>
          );
        })}
      </div>

      {activeMatchup && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setActiveMatchup(null)}>
          <div className="bg-slate-950 border border-slate-800 p-3 rounded-xl max-w-sm w-full h-[60vh] flex flex-col font-mono text-[10px]" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center border-b border-slate-900 pb-1 mb-2">
              <span className="font-black text-blue-400 uppercase">Head-to-Head</span>
              <button onClick={() => setActiveMatchup(null)} className="text-slate-500 font-bold">✕</button>
            </div>
            <div className="flex-1 grid grid-cols-2 gap-2 overflow-hidden">
              <div className="flex flex-col overflow-y-auto space-y-1">
                <div className="font-black text-slate-200 bg-slate-900 p-1 rounded text-center truncate">{activeMatchup.teamA.owner_name}</div>
                {activeMatchup.teamA.starters?.map((pId, i) => (
                  <div key={i} className="bg-slate-900/30 p-1 rounded flex justify-between">
                    <span className="text-slate-500 truncate max-w-[50px]">ID:{pId}</span>
                    <span className="font-bold text-slate-300">{(activeMatchup.teamA.custom_roster_points_map?.[pId] || 0.0).toFixed(1)}</span>
                  </div>
                ))}
              </div>
              <div className="flex flex-col overflow-y-auto space-y-1">
                <div className="font-black text-slate-200 bg-slate-900 p-1 rounded text-center truncate">{activeMatchup.teamB.owner_name}</div>
                {activeMatchup.teamB.starters?.map((pId, i) => (
                  <div key={i} className="bg-slate-900/30 p-1 rounded flex justify-between">
                    <span className="text-slate-500 truncate max-w-[50px]">ID:{pId}</span>
                    <span className="font-bold text-slate-300">{(activeMatchup.teamB.custom_roster_points_map?.[pId] || 0.0).toFixed(1)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ActivityStatusWidget({ name, currentScore, forecastScore, weather }) {
  const [modalState, setModalState] = React.useState({ isOpen: false, mode: 'current' });

  const getGradientClass = (score) => {
    const val = parseFloat(score) || 0;
    if (val >= 7.5) return "from-emerald-600 to-teal-950 border-emerald-500/40";
    if (val >= 4.5) return "from-amber-500 to-orange-950 border-amber-500/30";
    return "from-rose-700 to-slate-950 border-rose-600/30";
  };

  // NEW: Gradient logic based on constraint violations
  const getStatusGradient = (status) => {
    if (status === 'optimal') return "bg-gradient-to-r from-emerald-600 to-emerald-900 text-emerald-100 border-emerald-500/50 shadow-inner";
    if (status === 'warning') return "bg-gradient-to-r from-amber-500 to-amber-700 text-amber-50 border-amber-500/50 shadow-inner";
    return "bg-gradient-to-r from-rose-600 to-red-900 text-rose-100 border-rose-500/50 shadow-[0_0_8px_rgba(225,29,72,0.6)]";
  };

  const generateDiagnostics = (mode) => {
    const isFc = mode === 'forecast';
    
    // Extract base metrics
    const curTemp = parseFloat(weather.temperature_f) || 72;
    const curWind = parseFloat(weather.wind_speed_mph) || 0;
    const curHum = parseFloat(weather.humidity_pct) || 50;
    const rainAccum = parseFloat(weather.rain_accumulation_day_in) || 0.0;
    
    const fcDay = weather.forecast_daily_api?.[0] || {};
    const fcTemp = (parseFloat(fcDay.high || curTemp) + parseFloat(fcDay.low || curTemp)) / 2;
    const fcRainPct = parseInt(fcDay.rain_pct) || 0;
    
    // Set active variables based on which half was clicked
    const temp = isFc ? fcTemp : curTemp;
    const wind = curWind; 
    const hum = curHum; 
    
    // FIX: Calculate time decay so lightning expires after 45 minutes
    const minsSinceStrike = weather.last_strike_time ? Math.floor((Date.now() - weather.last_strike_time) / 60000) : 999;
    const lightningDist = weather.last_strike_distance !== null ? parseFloat(weather.last_strike_distance) : 999;
    const isLightningThreat = lightningDist <= 30 && minsSinceStrike <= 45;

    let metrics = {};
    const add = (label, val, status) => { metrics[label] = { value: val, status }; };

    // FIX: Activity-specific constraints
    switch (name) {
      case 'Airbrushing':
        add("Temperature", `${temp.toFixed(1)}°F`, temp < 60 || temp > 75 ? "critical" : temp < 64 || temp > 72 ? "warning" : "optimal");
        add("Humidity", `${hum.toFixed(0)}%`, hum > 75 ? "critical" : hum > 65 ? "warning" : "optimal");
        add("Wind speed", `${wind.toFixed(1)} mph`, wind > 8 ? "critical" : wind > 5 ? "warning" : "optimal");
        if (isFc) add("Precip Chance", `${fcRainPct}%`, fcRainPct > 15 ? "critical" : fcRainPct > 0 ? "warning" : "optimal");
        break;
      case 'Swimming':
        add("Temperature", `${temp.toFixed(1)}°F`, temp < 70 ? "critical" : temp < 75 ? "warning" : "optimal");
        if (isLightningThreat) add("Lightning", `${lightningDist} mi (${minsSinceStrike}m ago)`, "critical");
        if (isFc) add("Precip Chance", `${fcRainPct}%`, fcRainPct > 60 ? "critical" : fcRainPct > 30 ? "warning" : "optimal");
        break;
      case 'Yard Work':
        add("Temperature", `${temp.toFixed(1)}°F`, temp > 90 ? "critical" : temp > 78 || temp < 58 ? "warning" : "optimal");
        add("Wind speed", `${wind.toFixed(1)} mph`, wind > 25 ? "critical" : wind > 18 ? "warning" : "optimal");
        add("Recent Rainfall", `${rainAccum.toFixed(2)} in`, rainAccum > 0.15 ? "critical" : rainAccum > 0 ? "warning" : "optimal");
        if (isFc) add("Precip Chance", `${fcRainPct}%`, fcRainPct > 40 ? "critical" : fcRainPct > 20 ? "warning" : "optimal");
        if (isLightningThreat) add("Lightning", `${lightningDist} mi`, "critical");
        break;
      case 'Basketball':
      case 'Football':
        add("Temperature", `${temp.toFixed(1)}°F`, temp > 93 || temp < 55 ? "critical" : temp > 85 || temp < 62 ? "warning" : "optimal");
        add("Wind speed", `${wind.toFixed(1)} mph`, wind > 15 ? "critical" : wind > 10 ? "warning" : "optimal");
        add("Field Conditions", `${rainAccum.toFixed(2)} in`, rainAccum > 0.3 ? "critical" : rainAccum > 0.1 ? "warning" : "optimal");
        if (isFc) add("Precip Chance", `${fcRainPct}%`, fcRainPct > 70 ? "critical" : fcRainPct > 15 ? "warning" : "optimal");
        if (isLightningThreat) add("Lightning", `${lightningDist} mi`, "critical");
        break;
      case 'Walking':
        add("Temperature", `${temp.toFixed(1)}°F`, temp > 85 || temp < 50 ? "critical" : temp > 80 || temp < 60 ? "warning" : "optimal");
        add("Humidity", `${hum.toFixed(0)}%`, hum > 85 ? "critical" : hum > 75 ? "warning" : "optimal");
        add("Wind speed", `${wind.toFixed(1)} mph`, wind > 22 ? "critical" : wind > 15 ? "warning" : "optimal");
        if (isFc) add("Precip Chance", `${fcRainPct}%`, fcRainPct > 40 ? "critical" : fcRainPct > 20 ? "warning" : "optimal");
        if (isLightningThreat) add("Lightning", `${lightningDist} mi`, "critical");
        break;
      default:
        add("Temperature", `${temp.toFixed(1)}°F`, "optimal");
    }
    
    return metrics;
  };

  const diagnostics = generateDiagnostics(modalState.mode);
  const activeScore = modalState.mode === 'current' ? currentScore : forecastScore;

  return (
    <>
      <div className="h-[52px] grid grid-rows-2 gap-px font-mono tracking-tight border border-slate-900 rounded-lg overflow-hidden shadow-md">
        {/* FIX: Independent click handlers for Current vs Forecast */}
        <div 
          onClick={() => setModalState({ isOpen: true, mode: 'current' })}
          className={`bg-gradient-to-r ${getGradientClass(currentScore)} px-2 flex items-center justify-between cursor-pointer hover:brightness-110 active:scale-[0.98] transition-all`}
        >
          <span className="text-[10px] font-black text-white uppercase truncate max-w-[85px] drop-shadow">{name}</span>
          <span className="text-xs font-black text-white drop-shadow">{currentScore}</span>
        </div>
        <div 
          onClick={() => setModalState({ isOpen: true, mode: 'forecast' })}
          className={`bg-gradient-to-r ${getGradientClass(forecastScore)} px-2 flex items-center justify-between cursor-pointer hover:brightness-110 active:scale-[0.98] transition-all`}
        >
          <span className="text-[8px] font-bold text-white/70 uppercase">Forecast</span>
          <span className="text-xs font-black text-white drop-shadow">{forecastScore}</span>
        </div>
      </div>

      {modalState.isOpen && (
        <div 
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4"
          onClick={() => setModalState({ isOpen: false, mode: 'current' })}
        >
          <div 
            className="bg-slate-950 border border-slate-800 w-full max-w-xs p-4 rounded-2xl font-mono text-slate-200 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center border-b border-slate-900 pb-2 mb-3">
              <div>
                <h4 className="text-xs font-black uppercase tracking-wider text-slate-100 flex items-center gap-1.5">
                  📋 {name} 
                  <span className={`text-[8px] px-1.5 py-0.5 rounded border ${
                    modalState.mode === 'current' ? 'bg-blue-950/50 text-blue-400 border-blue-900/50' : 'bg-purple-950/50 text-purple-400 border-purple-900/50'
                  }`}>
                    {modalState.mode}
                  </span>
                </h4>
              </div>
              <button onClick={() => setModalState({ isOpen: false, mode: 'current' })} className="text-slate-500 hover:text-slate-300 text-sm p-1">✕</button>
            </div>

            <div className="space-y-2">
              <div className="bg-slate-900/20 border border-slate-900 p-2 rounded-lg flex justify-between items-center">
                <span className="text-[10px] font-bold text-slate-400">Index Score:</span>
                <span className="text-sm font-black text-slate-200">{activeScore} / 10</span>
              </div>
              
              {Object.entries(diagnostics).map(([metric, detail]) => (
                <div key={metric} className="bg-slate-900/40 border border-slate-900/60 rounded-xl px-3 py-1.5 flex justify-between items-center">
                  <span className="text-[10px] font-medium text-slate-400">{metric}</span>
                  {/* FIX: Applied the dynamic Red/Yellow/Green gradient background here */}
                  <span className={`text-[10px] font-black px-2 py-0.5 rounded border ${getStatusGradient(detail.status)}`}>
                    {detail.value}
                  </span>
                </div>
              ))}
            </div>

            <button
              onClick={() => setModalState({ isOpen: false, mode: 'current' })}
              className="mt-4 w-full py-1.5 bg-slate-900 text-slate-400 font-bold text-[10px] rounded-xl border border-slate-800 uppercase"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function LightningRadarWidget({ weather }) {
  const [minutesSince, setMinutesSince] = React.useState(null);
  const [pulseTrigger, setPulseTrigger] = React.useState(false);

  React.useEffect(() => {
    if (weather.lightning_strike_id > 0) {
      setPulseTrigger(true);
      const timer = setTimeout(() => setPulseTrigger(false), 800);
      return () => clearTimeout(timer);
    }
  }, [weather.lightning_strike_id]);

  React.useEffect(() => {
    const updateTime = () => {
      if (!weather.last_strike_time) {
        setMinutesSince(null);
        return;
      }
      const elapsedMins = Math.floor((Date.now() - weather.last_strike_time) / 60000);
      setMinutesSince(elapsedMins);
    };

    updateTime();
    const interval = setInterval(updateTime, 10000);
    return () => clearInterval(interval);
  }, [weather.last_strike_time]);

  const activeStorm = minutesSince !== null && minutesSince <= 30;
  const recentCloseStrike = minutesSince !== null && minutesSince <= 15 && weather.last_strike_distance <= 5;
  const activeRing = weather.strike_trigger_ring;

  return (
    <div className="bg-slate-950 border border-slate-900/60 p-4 rounded-3xl shadow-xl flex flex-col items-center justify-between min-h-[220px]">
      
      <div className="w-full text-left flex justify-between items-start">
        <div>
          <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 block">Lightning Indicator</span>
        </div>
        {activeStorm && (
          <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase tracking-widest animate-pulse">
            Active Storm
          </span>
        )}
      </div>

      <div className="relative w-40 h-40 my-2 flex items-center justify-center">
        <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
          
          <circle cx="50" cy="50" r="46" fill="none" className="stroke-slate-900/60 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="39" fill="none" className="stroke-slate-900/50 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="32" fill="none" className="stroke-slate-900/40 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="25" fill="none" className="stroke-slate-900/30 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="18" fill="none" className="stroke-slate-900/20 stroke-[0.75px]" />
          <circle cx="50" cy="50" r="11" fill="none" className="stroke-slate-950/80 stroke-[1px]" />

          <circle cx="50" cy="50" r="42.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 30 ? "rgba(16, 185, 129, 0.25)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 30 ? "7" : "0"} />
          <circle cx="50" cy="50" r="35.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 25 ? "rgba(132, 204, 22, 0.25)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 25 ? "7" : "0"} />
          <circle cx="50" cy="50" r="28.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 20 ? "rgba(234, 179, 8, 0.3)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 20 ? "7" : "0"} />
          <circle cx="50" cy="50" r="21.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 15 ? "rgba(249, 115, 22, 0.3)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 15 ? "7" : "0"} />
          <circle cx="50" cy="50" r="14.5" fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 10 ? "rgba(239, 68, 68, 0.35)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 10 ? "7" : "0"} />
          <circle cx="50" cy="50" r="5.5"  fill="none" className="transition-all duration-150" stroke={pulseTrigger && activeRing === 5 ? "rgba(225, 29, 72, 0.4)" : "transparent"} strokeWidth={pulseTrigger && activeRing === 5 ? "11" : "0"} />

          <line x1="50" y1="4" x2="50" y2="96" className="stroke-slate-900/20 stroke-[0.5px]" strokeDasharray="2 2" />
          <line x1="4" y1="50" x2="96" y2="50" className="stroke-slate-900/20 stroke-[0.5px]" strokeDasharray="2 2" />
        </svg>

        <div className={`absolute w-6 h-6 rounded-full flex items-center justify-center transition-all duration-500 ${
          recentCloseStrike ? 'bg-rose-600/20 border border-rose-500 text-rose-400' : 'bg-slate-900 text-slate-500'
        }`}>
          <span className={`text-[10px] font-black select-none ${recentCloseStrike ? 'text-rose-400 scale-110 animate-pulse' : ''}`}>⚡</span>
        </div>

        <span className="absolute right-0 text-[7px] font-mono font-bold text-slate-700">30m</span>
        <span className="absolute left-4 text-[7px] font-mono font-bold text-slate-700">15m</span>
      </div>

      <div className="w-full text-center mt-1">
        {activeStorm ? (
          <div className="flex flex-col items-center justify-center">
            <span className="text-[11px] font-black tracking-tight text-amber-400 font-mono">STORM TRACKED</span>
            <span className="text-[9px] text-slate-500 font-mono mt-0.5">
              Closest hit: {weather.last_strike_distance} miles ({minutesSince}m ago)
            </span>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center">
            <span className="text-[9px] font-bold text-slate-400 uppercase">
              {minutesSince === null ? 'No Strikes Detected' : 'Time Since Last Strike'}
            </span>
            <span className="text-xs font-black font-mono text-slate-200 mt-0.5 tracking-tighter">
              {minutesSince === null ? '--' : `${minutesSince} MINS`}
            </span>
          </div>
        )}
      </div>

    </div>
  );
}

function WeatherAlertBadge({ alert, config }) {
  const [isOpen, setIsOpen] = React.useState(false);

  const getFilterClass = (textColor) => {
    if (textColor.includes('rose-500')) return "brightness-0 invert sepia percent-100 saturate-[5000%] hue-rotate-[340deg] brightness-[95%] contrast-[95%]"; 
    if (textColor.includes('rose-600')) return "brightness-0 invert sepia percent-100 saturate-[4000%] hue-rotate-[335deg] brightness-[80%] contrast-[90%]"; 
    if (textColor.includes('amber-500') || textColor.includes('amber-400')) return "brightness-0 invert sepia percent-100 saturate-[3000%] hue-rotate-[15deg] brightness-[100%] contrast-[100%]"; 
    return "opacity-60"; 
  };

  return (
    <>
      <div
        onClick={() => setIsOpen(true)}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border cursor-pointer font-mono select-none transition-all active:scale-95 ${config.bg} ${config.border} ${
          config.pulse ? "animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.2)]" : "hover:border-slate-700"
        }`}
        title={`${alert.event}: Click for details`}
      >
        <img 
          src={config.icon} 
          alt="" 
          className={`h-4 w-4 object-contain ${getFilterClass(config.color)}`} 
          onError={(e) => { e.target.style.display = 'none'; }}
        />
        <span className={`text-[9px] font-black uppercase tracking-tight hidden md:inline ${config.color}`}>
          {alert.event}
        </span>
      </div>

      {isOpen && (
        <div 
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4 font-mono text-slate-300"
          onClick={() => setIsOpen(false)}
        >
          <div 
            className="bg-slate-950 border border-slate-900 w-full max-w-lg p-6 rounded-2xl shadow-2xl relative overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${config.pulse ? "from-rose-600 to-red-500" : "from-amber-500 to-orange-400"}`} />

            <div className="flex justify-between items-start border-b border-slate-900 pb-4 mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <img 
                    src={config.icon} 
                    alt="" 
                    className={`h-5 w-5 object-contain ${getFilterClass(config.color)}`} 
                  />
                  <h3 className="text-sm font-black uppercase tracking-wide text-slate-100">
                    {alert.event}
                  </h3>
                </div>
                <p className="text-[10px] text-slate-500 uppercase font-bold tracking-tight mt-1">
                  Issued By: {alert.senderName || "National Weather Service"}
                </p>
              </div>
              <button onClick={() => setIsOpen(false)} className="text-slate-500 hover:text-slate-300 text-sm p-1 transition-colors">✕</button>
            </div>

            <div className="grid grid-cols-2 gap-2 mb-4 text-[10px] uppercase font-bold text-slate-400">
              <div className="bg-slate-900/50 p-2 rounded-lg border border-slate-900">
                <span className="block text-slate-600 text-[8px] tracking-wider">Severity Rating</span>
                <span className={config.pulse ? "text-rose-400" : "text-amber-400"}>{alert.severity || "Moderate"}</span>
              </div>
              <div className="bg-slate-900/50 p-2 rounded-lg border border-slate-900">
                <span className="block text-slate-600 text-[8px] tracking-wider">Urgency Status</span>
                <span className="text-slate-200">{alert.urgency || "Immediate"}</span>
              </div>
            </div>

            <div className="bg-slate-900/30 border border-slate-900 p-4 rounded-xl max-h-[240px] overflow-y-auto text-xs text-slate-400 font-sans leading-relaxed custom-scrollbar">
              <div className="whitespace-pre-line font-mono text-[11px] leading-normal text-slate-300">
                {alert.description || "No specific narrative text provided in the direct broadcast payload."}
              </div>
            </div>

            {alert.ends && (
              <div className="mt-3 text-[9px] text-right text-slate-600 font-semibold uppercase tracking-wider">
                Expires: {new Date(alert.ends).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            )}

            <button
              onClick={() => setIsOpen(false)}
              className="mt-4 w-full py-2.5 bg-slate-900 hover:bg-slate-800 text-slate-400 font-bold text-[10px] rounded-xl border border-slate-800/80 transition-colors uppercase tracking-widest"
            >
              Close Hazard Readout
            </button>
          </div>
        </div>
      )}
    </>
  );
}

export default App;