// Fantasy_Draft_UI/src/WeeklyManagerView.jsx
import { useEffect, useState } from "react";

const GEM_COLORS = {
  Lunchpail: { bg: "#4682B4", label: "💼 Lunchpail" },
  Breakout: { bg: "#32CD32", label: "🚀 Breakout" },
  Underperformer: { bg: "#FC4C02", label: "📉 Underperformer" },
  Sleeper: { bg: "#9966CC", label: "💤 Sleeper" },
};

const WeeklyManagerView = () => {
  const [leagues, setLeagues] = useState([]);
  const [selectedLeague, setSelectedLeague] = useState("");
  const [username, setUsername] = useState(
    localStorage.getItem("sleeperUsername") || "",
  );
  const [week, setWeek] = useState(1);
  const [analysis, setAnalysis] = useState(null);
  const [awardsData, setAwardsData] = useState(null);
  const awardsConfig = JSON.parse(localStorage.getItem("awardsConfig")) || {};
  const awardsEnabled = awardsConfig[selectedLeague] !== false; // Defaults to true
  const [discordWebhook, setDiscordWebhook] = useState("");
  const [discordStatus, setDiscordStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [csvFile, setCsvFile] = useState(null);
  const [csvStatus, setCsvStatus] = useState("");

  const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8005";

  // 1. Fetch User Leagues
  const handleFetchLeagues = async () => {
    if (!username) return;
    try {
      const res = await fetch(`${apiBase}/api/sleeper/leagues/${username}`);
      if (res.ok) {
        const data = await res.json();
        setLeagues(data);
        if (data.length > 0) setSelectedLeague(data[0].league_id);
      }
    } catch (err) {
      console.error(err);
    }
  };

  // 2. Fetch Weekly Matchup & Roster Analysis
  const fetchWeeklyData = async () => {
    if (!selectedLeague || !username) return;
    setLoading(true);
    try {
      const res = await fetch(
        `${apiBase}/api/weekly/roster-analysis?league_id=${selectedLeague}&week=${week}&user_id=${username}`,
      );
      if (res.ok) {
        const data = await res.json();
        setAnalysis(data);
      }
    } catch (err) {
      console.error("Failed to load weekly analysis", err);
    } finally {
      setLoading(false);
    }
  };

  // 3. Upload FantasyPros Weekly Projections
  const handleUploadWeeklyCsv = async () => {
    if (!csvFile) return;
    setCsvStatus("Uploading...");
    const formData = new FormData();
    formData.append("file", csvFile);
    formData.append("week", week);

    try {
      const res = await fetch(`${apiBase}/api/weekly-projections/upload`, {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setCsvStatus(
          `Success! Processed ${data.processed_records} weekly projections.`,
        );
        fetchWeeklyData();
      } else {
        setCsvStatus("Upload failed.");
      }
    } catch (err) {
      setCsvStatus("Error connecting to server.");
    }
  };

  // 4. Calculate & Post Awards
  const handleCalculateAwards = async () => {
    try {
      const res = await fetch(
        `${apiBase}/api/weekly/calculate-awards?league_id=${selectedLeague}&week=${week}`,
        { method: "POST" },
      );
      if (res.ok) {
        const data = await res.json();
        setAwardsData(data.awards);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handlePostToDiscord = async () => {
    if (!discordWebhook || !awardsData) return;
    setDiscordStatus("Posting to Discord...");
    try {
      const res = await fetch(
        `${apiBase}/api/discord/post-awards?webhook_url=${encodeURIComponent(discordWebhook)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ week, awards: awardsData }),
        },
      );
      if (res.ok) setDiscordStatus("Posted successfully to Discord! 🚀");
      else setDiscordStatus("Failed to post to Discord.");
    } catch (err) {
      setDiscordStatus("Webhook connection error.");
    }
  };

  useEffect(() => {
    if (selectedLeague && username) fetchWeeklyData();
  }, [selectedLeague, week]);

  return (
    <div
      className="live-draft-container"
      style={{ padding: "20px", color: "#FFFFFF" }}
    >
      {/* Top Header Control Bar */}
      <div className="draft-control-panel">
        <div className="control-row">
          <div className="control-group">
            <label>Sleeper Username</label>
            <div className="input-with-btn">
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              <button onClick={handleFetchLeagues}>Load</button>
            </div>
          </div>

          <div className="control-group">
            <label>League</label>
            <select
              value={selectedLeague}
              onChange={(e) => setSelectedLeague(e.target.value)}
            >
              {leagues.map((lg) => (
                <option key={lg.league_id} value={lg.league_id}>
                  {lg.name} ({lg.season})
                </option>
              ))}
            </select>
          </div>

          <div className="control-group">
            <label>Matchup Week</label>
            <select
              value={week}
              onChange={(e) => setWeek(Number(e.target.value))}
            >
              {[...Array(18).keys()].map((w) => (
                <option key={w + 1} value={w + 1}>
                  Week {w + 1}
                </option>
              ))}
            </select>
          </div>

          <button
            className="manual-fetch-btn"
            onClick={fetchWeeklyData}
            disabled={loading}
          >
            {loading ? "Refreshing..." : "Sync Week Data"}
          </button>
        </div>
      </div>

      {/* FantasyPros Weekly Projections Ingestion Bar */}
      <div
        className="draft-control-panel"
        style={{ marginTop: "12px", border: "1px solid #00B5C1" }}
      >
        <h4 style={{ color: "#00B5C1", marginBottom: "8px" }}>
          Upload FantasyPros Week {week} Projections
        </h4>
        <div className="control-row upload-row">
          <input
            type="file"
            accept=".csv,.tsv"
            onChange={(e) => setCsvFile(e.target.files[0])}
          />
          <button
            className="manual-fetch-btn upload-btn"
            onClick={handleUploadWeeklyCsv}
            style={{ backgroundColor: "#00B5C1" }}
          >
            Upload Projections
          </button>
        </div>
        {csvStatus && (
          <div
            style={{ fontSize: "0.85rem", color: "#32CD32", marginTop: "6px" }}
          >
            {csvStatus}
          </div>
        )}
      </div>

      {/* Head-to-Head Matchup Summary Banner */}
      {analysis && (
        <div
          className="draft-summary-banner"
          style={{
            display: "flex",
            justifyContent: "space-around",
            marginTop: "16px",
          }}
        >
          <div className="summary-stat highlight">
            <label>MY PROJECTED SCORE</label>
            <span style={{ fontSize: "1.6rem", color: "#00B5C1" }}>
              {analysis.my_team.total_projected}
            </span>
          </div>
          <div className="summary-stat">
            <label>PROJECTED SPREAD</label>
            <span
              style={{
                fontSize: "1.4rem",
                color: analysis.projected_diff >= 0 ? "#32CD32" : "#FC4C02",
              }}
            >
              {analysis.projected_diff >= 0
                ? `+${analysis.projected_diff}`
                : analysis.projected_diff}
            </span>
          </div>
          <div className="summary-stat highlight">
            <label>OPPONENT ({analysis.opponent_team.owner_name})</label>
            <span style={{ fontSize: "1.6rem", color: "#FC4C02" }}>
              {analysis.opponent_team.total_projected}
            </span>
          </div>
        </div>
      )}

      {/* Starters Head-to-Head Comparison Grid */}
      {analysis && (
        <div style={{ marginTop: "20px" }}>
          <h3 style={{ color: "#00B5C1", marginBottom: "12px" }}>
            ⚔️ Head-to-Head Starting Lineup Comparison
          </h3>
          <div className="live-board-grid">
            {analysis.my_team.starters.map((player, idx) => {
              const oppPlayer = analysis.opponent_team.starters[idx] || {};
              return (
                <div
                  key={player.sleeper_id || idx}
                  className="live-player-card"
                  style={{ marginBottom: "12px" }}
                >
                  <div
                    className="card-header"
                    style={{ display: "flex", justifyContent: "space-between" }}
                  >
                    <div>
                      <span className="badge tier-badge">{player.slot}</span>
                      <strong
                        style={{ marginLeft: "8px", fontSize: "1.05rem" }}
                      >
                        {player.player_name}
                      </strong>
                      <span style={{ color: "#8BB2C9", marginLeft: "6px" }}>
                        ({player.team} - {player.pos_rank_label})
                      </span>
                      {player.is_on_bye && (
                        <span
                          className="badge"
                          style={{
                            backgroundColor: "#FC4C02",
                            marginLeft: "6px",
                          }}
                        >
                          ON BYE
                        </span>
                      )}
                      {player.injury_status !== "Active" && (
                        <span
                          className="badge"
                          style={{
                            backgroundColor: "#E60000",
                            marginLeft: "6px",
                          }}
                        >
                          {player.injury_status}
                        </span>
                      )}
                    </div>
                    <div style={{ display: "flex", gap: "6px" }}>
                      {player.gems.map((g) => (
                        <span
                          key={g}
                          className="badge"
                          style={{
                            backgroundColor: GEM_COLORS[g]?.bg || "#12223D",
                          }}
                        >
                          {GEM_COLORS[g]?.label || g}
                        </span>
                      ))}
                      <span
                        className="badge"
                        title={player.favorability_desc}
                        style={{
                          cursor: "help",
                          backgroundColor: "#0A1526",
                          border: "1px solid #FFD700",
                          color: "#FFD700",
                        }}
                      >
                        {"★".repeat(player.favorability_stars)}
                        {"☆".repeat(5 - player.favorability_stars)}
                      </span>
                    </div>
                  </div>

                  <div
                    className="card-body"
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div className="stat-box main-stat">
                      <label>Proj Pts</label>
                      <div style={{ fontSize: "1.2rem", color: "#00B5C1" }}>
                        {player.projected_points}
                      </div>
                    </div>
                    <div style={{ color: "#8BB2C9", fontWeight: "bold" }}>
                      VS
                    </div>
                    <div className="stat-box" style={{ textAlign: "right" }}>
                      <label>
                        Opp: {oppPlayer.player_name || "Empty Slot"}
                      </label>
                      <div style={{ fontSize: "1.2rem", color: "#FC4C02" }}>
                        {oppPlayer.projected_points || 0.0} pts
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Waiver Wire Targets Section */}
      {analysis && (
        <div style={{ marginTop: "24px" }}>
          <h3 style={{ color: "#32CD32", marginBottom: "12px" }}>
            ⚡ Recommended Waiver Wire Pickups (Free Agents)
          </h3>
          <div className="live-board-grid">
            {analysis.waiver_recommendations.map((fa) => (
              <div key={fa.sleeper_id} className="live-player-card">
                <div className="card-header">
                  <div>
                    <strong>{fa.player_name}</strong> - {fa.pos_rank_label} (
                    {fa.team})
                  </div>
                  <div style={{ display: "flex", gap: "6px" }}>
                    {fa.gems.map((g) => (
                      <span
                        key={g}
                        className="badge"
                        style={{
                          backgroundColor: GEM_COLORS[g]?.bg || "#12223D",
                        }}
                      >
                        {g}
                      </span>
                    ))}
                    <span className="badge" style={{ color: "#FFD700" }}>
                      {"★".repeat(fa.favorability_stars)}
                    </span>
                  </div>
                </div>
                <div className="card-body">
                  <div className="stat-box main-stat">
                    <label>Week {week} Proj</label>
                    <div style={{ color: "#32CD32" }}>
                      {fa.projected_points}
                    </div>
                  </div>
                  <div className="stat-box">
                    <label>Matchup</label>
                    <div>{fa.favorability_desc}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Weekly League Awards & Discord Webhook Dispatcher */}
      {awardsEnabled ? (
        <div
          className="draft-control-panel"
          style={{ marginTop: "30px", border: "1px solid #FFD700" }}
        >
          <h3 style={{ color: "#FFD700", marginBottom: "8px" }}>
            🏆 Weekly League Awards & Discord Dispatcher
          </h3>
          <p style={{ color: "#8BB2C9", fontSize: "0.85rem" }}>
            Calculate end-of-week awards (Nailbiter, Bench Star, Nostradamus,
            etc.) and blast them to your league Discord channel.
          </p>

          <div className="control-row">
            <input
              type="text"
              placeholder="Paste Discord Webhook URL"
              value={discordWebhook}
              onChange={(e) => setDiscordWebhook(e.target.value)}
              style={{ flex: 1 }}
            />
            <button
              className="manual-fetch-btn"
              onClick={handleCalculateAwards}
              style={{ backgroundColor: "#FFD700", color: "#0A1526" }}
            >
              Calculate Awards
            </button>
            <button
              className="manual-fetch-btn"
              onClick={handlePostToDiscord}
              disabled={!awardsData || !discordWebhook}
              style={{ backgroundColor: "#5865F2" }}
            >
              Post to Discord 🚀
            </button>
          </div>
          {discordStatus && (
            <div style={{ color: "#32CD32", marginTop: "8px" }}>
              {discordStatus}
            </div>
          )}

          {awardsData && (
            <div
              style={{
                marginTop: "16px",
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: "10px",
              }}
            >
              {awardsData.map((award, i) => (
                <div
                  key={i}
                  style={{
                    backgroundColor: "#0A1526",
                    padding: "10px",
                    borderRadius: "6px",
                    border: "1px solid #1B3054",
                  }}
                >
                  <div style={{ fontWeight: 800, color: "#00B5C1" }}>
                    {award.award}
                  </div>
                  <div style={{ fontWeight: "bold", marginTop: "4px" }}>
                    {award.team}
                  </div>
                  <div
                    style={{
                      fontSize: "0.8rem",
                      color: "#8BB2C9",
                      marginTop: "2px",
                    }}
                  >
                    {award.desc}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div
          className="draft-control-panel"
          style={{
            marginTop: "30px",
            border: "1px solid #1B3054",
            backgroundColor: "#0A1526",
          }}
        >
          <h3 style={{ color: "#8BB2C9", marginBottom: "8px" }}>
            Weekly League Awards
          </h3>
          <p style={{ color: "#8BB2C9", fontSize: "0.9rem" }}>
            Weekly Awards are currently disabled for this league. You can
            re-enable them in the Settings tab.
          </p>
        </div>
      )}
    </div>
  );
};

export default WeeklyManagerView;
