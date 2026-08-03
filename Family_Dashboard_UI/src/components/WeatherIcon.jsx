import React from 'react';

// Maps string conditions to specific SVG files and tailwind colors
export default function WeatherIcon({ icon, className = "w-4 h-4" }) {
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
    
    if (key === 'alien') return mapping['alien']; 
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
    return mapping['cloudy']; 
  };
  
  const meta = getSafeMeta(icon);
  
  // Custom thunderstorm rendering logic
  if (meta.file === 'wi-thunderstorm.svg') {
    return (
      <div 
        className={`${className} animate-pulse`}
        style={{
          WebkitMaskImage: `url(/assets/weather/weather-icons-master/svg/${meta.file})`,
          WebkitMaskSize: 'contain',
          WebkitMaskRepeat: 'no-repeat',
          WebkitMaskPosition: 'center',
          backgroundImage: 'linear-gradient(to bottom, #94a3b8 55%, #fbbf24 60%)'
        }}
      />
    );
  }
  
  // Custom partly-cloudy rendering logic
  if (meta.file === 'wi-day-cloudy.svg') {
    return (
      <div 
        className={`${className}`}
        style={{
          WebkitMaskImage: `url(/assets/weather/weather-icons-master/svg/${meta.file})`,
          WebkitMaskSize: 'contain',
          WebkitMaskRepeat: 'no-repeat',
          WebkitMaskPosition: 'center',
          backgroundImage: 'linear-gradient(225deg, #fbbf24 35%, #94a3b8 40%)'
        }}
      />
    );
  }

  // Standard icon rendering
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
}