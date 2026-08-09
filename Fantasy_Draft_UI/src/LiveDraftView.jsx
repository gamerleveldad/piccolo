// Fantasy_Draft_UI/src/LiveDraftView.jsx
import React, { useState, useEffect } from 'react';

const LiveDraftView = () => {
  const [username, setUsername] = useState('');
  const [leagues, setLeagues] = useState([]);
  const [selectedLeague, setSelectedLeague] = useState('');
  const [draftId, setDraftId] = useState('');
  const [draftFormat, setDraftFormat] = useState('snake');
  const [isLiveSync, setIsLiveSync] = useState(false);
  
  const [positionFilter, setPositionFilter] = useState('ALL');
  const [board, setBoard] = useState([]);
  const [draftState, setDraftState] = useState(null);
  const [rosterByes, setRosterByes] = useState({});
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8005';

  // Helper to extract draft ID if user pastes full Sleeper URL
  const cleanDraftId = (input) => {
    if (!input) return '';
    const parts = input.trim().split('/');
    return parts[parts.length - 1];
  };

  // Fetch leagues for entered username
  const handleFetchLeagues = async () => {
    if (!username) return;
    setLoading(true);
    setErrorMsg('');
    try {
      const res = await fetch(`${apiBase}/api/sleeper/leagues/${username}`);
      if (res.ok) {
        const data = await res.json();
        setLeagues(data);
        if (data.length > 0) {
          setSelectedLeague(data[0].league_id);
          setDraftId(data[0].draft_id || '');
        } else {
          setErrorMsg('No leagues found for this Sleeper user.');
        }
      } else {
        setErrorMsg('Failed to fetch Sleeper leagues.');
      }
    } catch (err) {
      console.error('Error fetching leagues:', err);
      setErrorMsg('Error connecting to backend.');
    } finally {
      setLoading(false);
    }
  };

  // Primary function to fetch live recommendations & draft state
  const fetchDraftRecommendations = async () => {
    const activeDraftId = cleanDraftId(draftId);
    if (!activeDraftId) return;

    try {
      const res = await fetch(
        `${apiBase}/api/draft/recommendations?draft_id=${activeDraftId}&user_id=${username}&format=${draftFormat}`
      );
      if (res.ok) {
        const data = await res.json();
        setBoard(data.board || []);
        setDraftState(data.draft_state || null);
        setRosterByes(data.my_roster_byes || {});
        setErrorMsg('');
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'Failed to sync draft data.');
      }
    } catch (err) {
      console.error('Error polling draft:', err);
      setErrorMsg('Live sync connection error.');
    }
  };

  // Handle dropdown league selection change
  const handleLeagueChange = (e) => {
    const leagueId = e.target.value;
    setSelectedLeague(leagueId);
    const lg = leagues.find((item) => item.league_id === leagueId);
    if (lg && lg.draft_id) {
      setDraftId(lg.draft_id);
    }
  };

  // Poll Sleeper every 3 seconds ONLY if Live Sync is ON
  useEffect(() => {
    let interval = null;
    if (isLiveSync) {
      fetchDraftRecommendations(); // Immediate initial pull
      interval = setInterval(() => {
        fetchDraftRecommendations();
      }, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isLiveSync, draftId, username, draftFormat]);

  // Position filter logic
  const filteredBoard = board.filter((player) => {
    if (positionFilter === 'ALL') return true;
    return player.position?.toUpperCase() === positionFilter;
  });

  const getLogoUrl = (teamAbbr) => {
    if (!teamAbbr) return '';
    const cleanTeam = teamAbbr === 'WAS' ? 'wsh' : teamAbbr.toLowerCase();
    return `https://a.espncdn.com/i/teamlogos/nfl/500/${cleanTeam}.png`;
  };

  return (
    <div className="live-draft-container">
      {/* Top Header Control Panel */}
      <div className="draft-control-panel">
        <div className="control-row">
          <div className="control-group">
            <label>Sleeper Username</label>
            <div className="input-with-btn">
              <input
                type="text"
                placeholder="Enter Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              <button onClick={handleFetchLeagues} disabled={loading}>
                {loading ? '...' : 'Load'}
              </button>
            </div>
          </div>

          <div className="control-group">
            <label>League</label>
            <select value={selectedLeague} onChange={handleLeagueChange}>
              {leagues.map((lg) => (
                <option key={lg.league_id} value={lg.league_id}>
                  {lg.name} ({lg.season})
                </option>
              ))}
            </select>
          </div>

          <div className="control-group override-group">
            <label>Draft ID / Mock URL Override</label>
            <input
              type="text"
              placeholder="Paste Draft ID or Mock Link"
              value={draftId}
              onChange={(e) => setDraftId(e.target.value)}
            />
          </div>

          <div className="control-group">
            <label>Format</label>
            <select value={draftFormat} onChange={(e) => setDraftFormat(e.target.value)}>
              <option value="snake">Snake</option>
              <option value="auction">Auction</option>
            </select>
          </div>

          <div className="control-group sync-toggle-group">
            <label>Live Polling</label>
            <button
              className={`sync-btn ${isLiveSync ? 'sync-on' : 'sync-off'}`}
              onClick={() => setIsLiveSync(!isLiveSync)}
            >
              {isLiveSync ? '● SYNC ON' : '○ PAUSED'}
            </button>
          </div>
        </div>

        {/* Manual Refresh & Error Bar */}
        <div className="control-subrow">
          <button className="manual-fetch-btn" onClick={fetchDraftRecommendations}>
            Manual Refresh
          </button>
          {errorMsg && <span className="draft-error-text">{errorMsg}</span>}
        </div>
      </div>

      {/* Auction & Roster Summary Banner */}
      {draftState && (
        <div className="draft-summary-banner">
          {draftFormat === 'auction' && (
            <div className="summary-stat highlight">
              <label>Remaining Budget</label>
              <span>${draftState.remaining_budget}</span>
            </div>
          )}
          <div className="summary-stat">
            <label>Players Taken</label>
            <span>{draftState.drafted_player_ids?.length || 0}</span>
          </div>
          <div className="summary-stat">
            <label>My Roster Count</label>
            <span>{draftState.my_roster?.ALL?.length || 0}</span>
          </div>
          <div className="summary-stat">
            <label>Drafted QB Byes</label>
            <span>{rosterByes.QB?.join(', ') || 'None'}</span>
          </div>
          <div className="summary-stat">
            <label>Drafted TE Byes</label>
            <span>{rosterByes.TE?.join(', ') || 'None'}</span>
          </div>
        </div>
      )}

      {/* Position Filter Tabs */}
      <div className="position-filter-bar">
        {['ALL', 'QB', 'RB', 'WR', 'TE', 'DEF', 'K'].map((pos) => (
          <button
            key={pos}
            className={`pos-tab ${positionFilter === pos ? 'active' : ''}`}
            onClick={() => setPositionFilter(pos)}
          >
            {pos}
          </button>
        ))}
      </div>

      {/* Recommended Player Cards List */}
      <div className="live-board-grid">
        {filteredBoard.map((player, idx) => (
          <div
            key={player.player_id}
            className={`live-player-card ${player.bye_status === 'BLOCKED' ? 'card-blocked' : ''}`}
          >
            <div className="card-header">
              <div className="header-left">
                <span className="grid-rank">#{idx + 1}</span>
                {player.team && <img src={getLogoUrl(player.team)} alt={player.team} className="team-logo-large" />}
                <div className="header-names">
                  <h3>{player.player_name}</h3>
                  <span>{player.position} - {player.team || 'Free Agent'}</span>
                </div>
              </div>
              
              <div className="header-right">
                {player.depth_chart_order && (
                  <span className="badge depth-badge">
                    Depth: {player.position}{player.depth_chart_order}
                  </span>
                )}
                <span className="badge">Age: {player.age || '-'}</span>
                <span className="badge">Bye: {player.bye_week || '-'}</span>
              </div>
            </div>

            {/* Inside LiveDraftView.jsx card-body */}
            <div className="card-body">
              <div className="stat-box main-stat">
                <label>TI Score</label>
                <div>{player.ti_score}</div>
              </div>

              <div className="stat-box highlight-stat">
                <label>Value Above Base (VORP)</label>
                <div style={{ color: player.vorp_score >= 0 ? '#28a745' : '#dc3545', fontWeight: 'bold' }}>
                  {player.vorp_score >= 0 ? `+${player.vorp_score}` : player.vorp_score}
                </div>
              </div>

              <div className="stat-box">
                <label>Dynasty TI</label>
                <div>{player.ti_score_dynasty || '-'}</div>
              </div>

              <div className="stat-box">
                <label>Consistency</label>
                <div>{player.consistency_label || '-'}</div>
              </div>

              {draftFormat === 'auction' && (
                <div className="stat-box auction-stat">
                  <label>Max Bid ("Don't Go Over")</label>
                  <div>${player.auction_max_bid}</div>
                </div>
              )}
            </div>

            {/* Status / Bye Constraint Alert Banner */}
            {player.bye_status !== 'CLEAR' && (
              <div className={`bye-alert-banner alert-${player.bye_status.toLowerCase()}`}>
                {player.bye_message}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default LiveDraftView;