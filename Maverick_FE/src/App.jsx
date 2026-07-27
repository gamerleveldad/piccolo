import { useState, useEffect } from 'react';

function App() {
  const [weather, setWeather] = useState(null);
  const [flights, setFlights] = useState([]);
  const [error, setError] = useState(null);

  // Dynamically resolve the IP or hostname of the server loading the UI
  const host = window.location.hostname;
  const WEATHER_URL = `http://${host}:8004/api/weather/current`;
  const FLIGHT_URL = `http://${host}:8003/api/flights/active`;

  useEffect(() => {
    fetch(WEATHER_URL)
      .then(res => {
        if (!res.ok) throw new Error(`Weather API return code ${res.status}`);
        return res.json();
      })
      .then(data => setWeather(data))
      .catch(err => setError(prev => (prev ? `${prev} | Weather: ${err.message}` : `Weather: ${err.message}`)));

    fetch(FLIGHT_URL)
      .then(res => {
        if (!res.ok) throw new Error(`Flight API return code ${res.status}`);
        return res.json();
      })
      .then(data => setFlights(data))
      .catch(err => setError(prev => (prev ? `${prev} | Flights: ${err.message}` : `Flights: ${err.message}`)));
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
              <li><strong>Temperature:</strong> {weather.temperature ?? 'N/A'}</li>
              <li><strong>Wind Speed:</strong> {weather.wind_speed ?? 'N/A'}</li>
              <li><strong>Wind Gust:</strong> {weather.wind_gust ?? 'N/A'}</li>
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
                  <strong>Callsign:</strong> {flight.callsign} <br />
                  <strong>Altitude:</strong> {flight.altitude} ft <br />
                  <strong>Distance:</strong> {flight.distance}
                </li>
              ))}
            </ul>
          ) : (
            <p>No active flights found or loading...</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;