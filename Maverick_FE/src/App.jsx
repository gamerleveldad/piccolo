import { useState, useEffect } from 'react';

function App() {
  const [weather, setWeather] = useState(null);
  const [flights, setFlights] = useState([]);
  const [error, setError] = useState(null);

  const host = window.location.hostname;
  const WEATHER_URL = `http://${host}:8004/api/weather/current`;
  const FLIGHT_URL = `http://${host}:8003/api/flights/active`;

  useEffect(() => {
    fetch(WEATHER_URL)
      .then(async res => {
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(`Weather API: ${errData.detail || res.status}`);
        }
        return res.json();
      })
      .then(data => setWeather(data))
      .catch(err => setError(prev => (prev ? `${prev} | ${err.message}` : err.message)));

    fetch(FLIGHT_URL)
      .then(async res => {
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(`Flight API: ${errData.detail || res.status}`);
        }
        return res.json();
      })
      .then(data => setFlights(data))
      .catch(err => setError(prev => (prev ? `${prev} | ${err.message}` : err.message)));
  }, [WEATHER_URL, FLIGHT_URL]);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-300 p-8 font-sans">
      <h1 className="text-3xl font-bold text-blue-500 mb-8">Maverick Data Test</h1>
      
      {error && (
        <div className="bg-slate-800 border border-slate-600 text-slate-100 p-4 rounded mb-6">
          Error loading data: {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Weather Section */}
        <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
          <h2 className="text-xl font-semibold text-purple-400 mb-4">Current Weather</h2>
          {weather ? (
            <ul className="space-y-2 text-sm">
              <li><strong>Temperature:</strong> {weather.air_temperature ?? 'N/A'}</li>
              <li><strong>Humidity:</strong> {weather.relative_humidity ?? 'N/A'}%</li>
              <li><strong>Dew Point:</strong> {weather.dew_point ?? 'N/A'}</li>
              <li><strong>Heat Index:</strong> {weather.heat_index ?? 'N/A'}</li>
              <li><strong>Wind Speed:</strong> {weather.wind_avg ?? 'N/A'}</li>
              <li><strong>Wind Gust:</strong> {weather.wind_gust ?? 'N/A'}</li>
              <li><strong>Rain Rate:</strong> {weather.precip_total_1h ?? 'N/A'}</li>
              <li><strong>Lightning (Last 1hr):</strong> {weather.strike_count_1h ?? '0'} strikes</li>
              <li><strong>Lightning (Last Dist):</strong> {weather.strike_last_dist ?? 'N/A'}</li>
            </ul>
          ) : (
            <p>Loading weather data...</p>
          )}
        </div>

        {/* Flights Section */}
        <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
          <h2 className="text-xl font-semibold text-purple-400 mb-4">Active Flights</h2>
          {flights && flights.length > 0 ? (
            <ul className="space-y-3 text-sm">
              {flights.map((flight, index) => (
                <li key={index} className="border-b border-slate-700 pb-2">
                  <strong>Callsign:</strong> {flight.callsign || 'N/A'} <span className="text-slate-500">({flight.aircraft_type || 'Unknown'})</span><br />
                  <strong>Altitude:</strong> {flight.altitude_ft} ft <br />
                  <strong>Speed:</strong> {flight.ground_speed_kts} kts <br />
                  <strong>Distance:</strong> {flight.distance_nm} nm
                </li>
              ))}
            </ul>
          ) : (
            <p>No active flights found within the time window or loading...</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;