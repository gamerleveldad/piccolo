// Fantasy_Draft_UI/src/LiveDraftView.jsx
import { useEffect, useState } from "react";

const LiveDraftView = () => {
  const [username, setUsername] = useState("");
  const [leagues, setLeagues] = useState([]);
  const [selectedLeague, setSelectedLeague] = useState("");
  const [draftId, setDraftId] = useState("");
  const [rosterId, setRosterId] = useState("");
  const [draftFormat, setDraftFormat] = useState("snake");
  const [isLiveSync, setIsLiveSync] = useState(false);

  const [positionFilter, setPositionFilter] = useState("ALL");
  const [board, setBoard] = useState([]);
  const [draftState, setDraftState] = useState(null);
  const [draftIntel, setDraftIntel] = useState(null); // Draft Room Spying Intel
  const [rosterByes, setRosterByes] = useState({});
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8005";

  // Helper to extract draft ID if user pastes full Sleeper URL
  const cleanDraftId = (input) => {
    if (!input) return "";
    const parts = input.trim().split("/");
    return parts[parts.length - 1];
  };

  const TAG_OPTIONS = [
    {
      value: "PPR Monster",
      label: "PPR Monster",
      icon: "/icons/ppr.svg",
      color: "#F1C27D",
    },
    {
      value: "Injury Risk",
      label: "Injury Risk",
      icon: "/icons/injury.svg",
      color: "#E60000",
      outline: "#FFFFFF",
    },
    {
      value: "Breakout",
      label: "Breakout Potential",
      icon: "/icons/breakout.svg",
      color: "#87CEFA",
    },
    {
      value: "Rookie",
      label: "Rookie",
      icon: "/icons/rookie.svg",
      color: "#32CD32",
    },
    {
      value: "Handcuff",
      label: "Premium Handcuff",
      icon: "/icons/handcuff.svg",
      color: "#C0C0C0",
    },
    {
      value: "DND",
      label: "Do Not Draft",
      icon: "/icons/dnd.svg",
      color: "#FF2400",
    },
    { value: "Star", label: "Star", icon: "/icons/star.svg", color: "#FFD700" },
    {
      value: "Regression",
      label: "Regression Candidate",
      icon: "/icons/regression.svg",
      color: "#B22222",
    },
    {
      value: "Hidden Gem",
      label: "Hidden Gem",
      icon: "/icons/gem.svg",
      color: "#9966CC",
    },
    {
      value: "Goalline",
      label: "Goalline Back",
      icon: "/icons/goalline.svg",
      color: "#4682B4",
    },
  ];

  const SvgIcon = ({ icon, color, outline }) => {
    const filterStyle = outline
      ? `drop-shadow(1px 0px 0px ${outline}) drop-shadow(0px 1px 0px ${outline}) drop-shadow(-1px 0px 0px ${outline}) drop-shadow(0px -1px 0px ${outline})`
      : "none";

    return (
      <div
        style={{
          filter: filterStyle,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            width: "18px",
            height: "18px",
            backgroundColor: color,
            WebkitMaskImage: `url(${icon})`,
            WebkitMaskSize: "contain",
            WebkitMaskRepeat: "no-repeat",
            WebkitMaskPosition: "center",
            maskImage: `url(${icon})`,
            maskSize: "contain",
            maskRepeat: "no-repeat",
            maskPosition: "center",
          }}
        />
      </div>
    );
  };

  const handleFetchLeagues = async () => {
    if (!username) return;
    setLoading(true);
    setErrorMsg("");
    try {
      const res = await fetch(`${apiBase}/api/sleeper/leagues/${username}`);
      if (res.ok) {
        const data = await res.json();
        setLeagues(data);
        if (data.length > 0) {
          setSelectedLeague(data[0].league_id);
          setDraftId(data[0].draft_id || "");
        } else {
          setErrorMsg("No leagues found for this Sleeper user.");
        }
      } else {
        setErrorMsg("Failed to fetch Sleeper leagues.");
      }
    } catch (err) {
      console.error("Error fetching leagues:", err);
      setErrorMsg("Error connecting to backend.");
    } finally {
      setLoading(false);
    }
  };

  const fetchDraftRecommendations = async () => {
    const activeDraftId = cleanDraftId(draftId);
    if (!activeDraftId) return;

    try {
      const res = await fetch(
        `${apiBase}/api/draft/recommendations?draft_id=${activeDraftId}&user_id=${username}&format=${draftFormat}&roster_id=${rosterId}`,
      );
      if (res.ok) {
        const data = await res.json();
        setBoard(data.board || []);
        setDraftState(data.draft_state || null);
        setDraftIntel(data.draft_intel || null);
        setRosterByes(data.my_roster_byes || {});
        setErrorMsg("");
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || "Failed to sync draft data.");
      }
    } catch (err) {
      console.error("Error polling draft:", err);
      setErrorMsg("Live sync connection error.");
    }
  };

  const handleLeagueChange = (e) => {
    const leagueId = e.target.value;
    setSelectedLeague(leagueId);
    const lg = leagues.find((item) => item.league_id === leagueId);
    if (lg && lg.draft_id) {
      setDraftId(lg.draft_id);
    }
  };

  useEffect(() => {
    let interval = null;
    if (isLiveSync) {
      fetchDraftRecommendations();
      interval = setInterval(() => {
        fetchDraftRecommendations();
      }, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isLiveSync, draftId, username, draftFormat, rosterId]);

  const filteredBoard = board.filter((player) => {
    if (positionFilter === "ALL") return true;
    return player.position?.toUpperCase() === positionFilter;
  });

  const getLogoUrl = (teamAbbr) => {
    if (!teamAbbr) return "";
    const cleanTeam = teamAbbr === "WAS" ? "wsh" : teamAbbr.toLowerCase();
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
                {loading ? "..." : "Load"}
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
            <select
              value={draftFormat}
              onChange={(e) => setDraftFormat(e.target.value)}
            >
              <option value="snake">Snake</option>
              <option value="auction">Auction</option>
            </select>
          </div>

          <div className="control-group">
            <label>My Team #</label>
            <input
              type="number"
              placeholder="e.g. 2"
              value={rosterId}
              onChange={(e) => setRosterId(e.target.value)}
              style={{ width: "80px" }}
            />
          </div>

          <div className="control-group sync-toggle-group">
            <label>Live Polling</label>
            <button
              className={`sync-btn ${isLiveSync ? "sync-on" : "sync-off"}`}
              onClick={() => setIsLiveSync(!isLiveSync)}
            >
              {isLiveSync ? "● SYNC ON" : "○ PAUSED"}
            </button>
          </div>
        </div>

        {/* Manual Refresh & Error Bar */}
        <div className="control-subrow">
          <button
            className="manual-fetch-btn"
            onClick={fetchDraftRecommendations}
          >
            Manual Refresh
          </button>
          {errorMsg && <span className="draft-error-text">{errorMsg}</span>}
        </div>
      </div>

      {/* Auction & Roster Summary Banner */}
      {draftState && (
        <div className="draft-summary-banner">
          {draftFormat === "auction" && (
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
            <span>{rosterByes.QB?.join(", ") || "None"}</span>
          </div>
          <div className="summary-stat">
            <label>Drafted TE Byes</label>
            <span>{rosterByes.TE?.join(", ") || "None"}</span>
          </div>
        </div>
      )}

      {/* Position Filter Tabs */}
      <div className="position-filter-bar">
        {["ALL", "QB", "RB", "WR", "TE", "DEF", "K"].map((pos) => (
          <button
            key={pos}
            className={`pos-tab ${positionFilter === pos ? "active" : ""}`}
            onClick={() => setPositionFilter(pos)}
          >
            {pos}
          </button>
        ))}
      </div>

      {/* NEW: Draft Room Radar / Opponent Needs Banner */}
      {draftIntel && draftFormat === "snake" && (
        <div
          className="intel-radar-banner"
          style={{
            backgroundColor: "#0A1526",
            border: "1px solid #00B5C1",
            borderRadius: "8px",
            padding: "12px 18px",
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div>
            <span style={{ color: "#8BB2C9", fontSize: "0.85rem" }}>
              NEXT SELECTION
            </span>
            <div
              style={{
                fontSize: "1.1rem",
                fontWeight: 800,
                color: "#00B5C1",
              }}
            >
              Pick #{draftIntel.next_user_pick_no} (
              {draftIntel.picks_until_turn} picks away)
            </div>
          </div>

          <div>
            <span style={{ color: "#8BB2C9", fontSize: "0.85rem" }}>
              INTERVENING OPPONENT NEEDS
            </span>
            <div style={{ display: "flex", gap: "8px", marginTop: "3px" }}>
              <span
                className="badge"
                style={{
                  backgroundColor: "#12223D",
                  border: "1px solid #00B5C1",
                  color: "#FFFFFF",
                }}
              >
                QB: {draftIntel.intervening_needs?.QB || 0}
              </span>
              <span
                className="badge"
                style={{
                  backgroundColor: "#12223D",
                  border: "1px solid #00B5C1",
                  color: "#FFFFFF",
                }}
              >
                RB: {draftIntel.intervening_needs?.RB || 0}
              </span>
              <span
                className="badge"
                style={{
                  backgroundColor: "#12223D",
                  border: "1px solid #00B5C1",
                  color: "#FFFFFF",
                }}
              >
                WR: {draftIntel.intervening_needs?.WR || 0}
              </span>
              <span
                className="badge"
                style={{
                  backgroundColor: "#12223D",
                  border: "1px solid #00B5C1",
                  color: "#FFFFFF",
                }}
              >
                TE: {draftIntel.intervening_needs?.TE || 0}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Recommended Player Cards List */}
      <div className="live-board-grid">
        {filteredBoard.map((player, idx) => (
          <div
            key={player.player_id}
            className={`live-player-card ${player.bye_status === "BLOCKED" ? "card-blocked" : ""}`}
          >
            <div className="card-header">
              <div className="header-left">
                <span className="grid-rank">#{idx + 1}</span>
                {player.team && (
                  <img
                    src={getLogoUrl(player.team)}
                    alt={player.team}
                    className="team-logo-large"
                  />
                )}
                <div className="header-names">
                  <h3>{player.player_name}</h3>
                  <span>
                    {player.position} - {player.team || "Free Agent"}
                  </span>
                </div>
              </div>

              <div className="header-right">
                {/* 1. Tag Icon Bar */}
                <div
                  className="tag-icon-bar"
                  style={{
                    display: "flex",
                    gap: "5px",
                    alignItems: "center",
                    marginRight: "8px",
                  }}
                >
                  {(player.custom_tags || []).map((tagVal) => {
                    const opt = TAG_OPTIONS.find((o) => o.value === tagVal);
                    if (!opt) return null;
                    return (
                      <div
                        key={tagVal}
                        title={opt.label}
                        style={{ display: "flex", alignItems: "center" }}
                      >
                        <SvgIcon
                          icon={opt.icon}
                          color={opt.color}
                          outline={opt.outline}
                        />
                      </div>
                    );
                  })}
                </div>

                {/* 2. Tier Scarcity Alarm */}
                {player.scarcity_alert && (
                  <span
                    className="badge scarcity-badge"
                    style={{
                      backgroundColor:
                        player.tier_remaining === 1 ? "#FC4C02" : "#FFD700",
                      color: "#0A1526",
                      fontWeight: 900,
                      animation:
                        player.tier_remaining === 1
                          ? "pulse 1.5s infinite"
                          : "none",
                    }}
                  >
                    ⚠️ {player.scarcity_alert}
                  </span>
                )}

                {/* 3. Pick Predictor / Reach Odds */}
                {draftFormat === "snake" &&
                  player.survival_odds !== undefined && (
                    <span
                      className="badge odds-badge"
                      title={`Estimated ${player.survival_odds}% chance of being available at your next pick.`}
                      style={{
                        backgroundColor:
                          player.survival_odds >= 70
                            ? "rgba(50, 205, 50, 0.15)"
                            : player.survival_odds <= 25
                              ? "rgba(252, 76, 2, 0.2)"
                              : "rgba(255, 215, 0, 0.15)",
                        border: `1px solid ${
                          player.survival_odds >= 70
                            ? "#32CD32"
                            : player.survival_odds <= 25
                              ? "#FC4C02"
                              : "#FFD700"
                        }`,
                        color:
                          player.survival_odds >= 70
                            ? "#32CD32"
                            : player.survival_odds <= 25
                              ? "#FC4C02"
                              : "#FFD700",
                        fontWeight: 700,
                      }}
                    >
                      🎲 {player.survival_odds}% Reach Odds
                    </span>
                  )}

                {/* 4. Positional Tier Badge */}
                {player.pos_tier && (
                  <span className="badge tier-badge">{player.pos_tier}</span>
                )}

                {/* 5. Depth, Age, Bye Badges */}
                {player.depth_chart_order && (
                  <span className="badge depth-badge">
                    Depth: {player.position}
                    {player.depth_chart_order}
                  </span>
                )}
                <span className="badge">Age: {player.age || "-"}</span>
                <span className="badge">Bye: {player.bye_week || "-"}</span>
              </div>
            </div>

            {/* Card Body */}
            <div className="card-body">
              <div className="stat-box main-stat">
                <label>TI Score</label>
                <div>{player.ti_score}</div>
              </div>

              <div className="stat-box highlight-stat">
                <label>Value Above Base (VORP)</label>
                <div
                  style={{
                    color: player.vorp_score >= 0 ? "#28a745" : "#dc3545",
                    fontWeight: "bold",
                  }}
                >
                  {player.vorp_score >= 0
                    ? `+${player.vorp_score}`
                    : player.vorp_score}
                </div>
              </div>

              {player.fp_rank && (
                <>
                  <div className="stat-box">
                    <label>FP Rank</label>
                    <div>#{player.fp_rank}</div>
                  </div>
                  <div className="stat-box">
                    <label>Upside / Bust</label>
                    <div>
                      {player.fp_upside || 0}/5 · {player.fp_bust || 0}/5
                    </div>
                  </div>
                  <div className="stat-box">
                    <label>SoS</label>
                    <div style={{ color: "#FFD700" }}>
                      {"★".repeat(player.fp_sos || 0)}
                      {"☆".repeat(Math.max(0, 5 - (player.fp_sos || 0)))}
                    </div>
                  </div>
                </>
              )}

              <div className="stat-box">
                <label>Dynasty TI</label>
                <div>{player.ti_score_dynasty || "-"}</div>
              </div>

              <div className="stat-box">
                <label>Consistency</label>
                <div>{player.consistency_label || "-"}</div>
              </div>

              {draftFormat === "auction" && (
                <div className="stat-box auction-stat">
                  <label>Max Bid ("Don't Go Over")</label>
                  <div>${player.auction_max_bid}</div>
                </div>
              )}
            </div>

            {/* Status / Bye Constraint Alert Banner */}
            {player.bye_status !== "CLEAR" && (
              <div
                className={`bye-alert-banner alert-${player.bye_status.toLowerCase()}`}
              >
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
