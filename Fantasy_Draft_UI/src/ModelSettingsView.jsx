// Fantasy_Draft_UI/src/ModelSettingsView.jsx
import { useState } from "react";

const ModelSettingsView = () => {
  const [roleDiscounts, setRoleDiscounts] = useState({
    RB2: 0.85,
    WR2: 0.9,
    WR3: 0.8,
  });

  const [rookieWeights, setRookieWeights] = useState({
    proj: 60,
    team: 40,
  });

  const [savedMsg, setSavedMsg] = useState("");
  const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8005";

  // --- Handcuff State ---
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");

  // --- FantasyPros Cheat Sheet State ---
  const [fpFile, setFpFile] = useState(null);
  const [fpUploading, setFpUploading] = useState(false);
  const [fpUploadStatus, setFpUploadStatus] = useState("");

  const handleSaveSettings = () => {
    setSavedMsg("Settings updated for current draft session!");
    setTimeout(() => setSavedMsg(""), 3000);
  };
  // --- Sleeper Sync State ---
  const [syncingSleeper, setSyncingSleeper] = useState(false);
  const [sleeperSyncStatus, setSleeperSyncStatus] = useState("");

  const handleSyncSleeper = async () => {
    setSyncingSleeper(true);
    setSleeperSyncStatus("");
    try {
      const res = await fetch(`${apiBase}/api/admin/sync-sleeper`, {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        setSleeperSyncStatus(
          `Success! Synced ${data.synced_players} players from Sleeper.`,
        );
      } else {
        setSleeperSyncStatus("Failed to sync Sleeper data.");
      }
    } catch (err) {
      console.error(err);
      setSleeperSyncStatus("Error connecting to backend.");
    } finally {
      setSyncingSleeper(false);
    }
  };

  // --- Global App Settings State ---
  const [defaultTab, setDefaultTab] = useState(
    localStorage.getItem("defaultAppTab") || "LiveDraft",
  );
  const [sleeperUsername, setSleeperUsername] = useState(
    localStorage.getItem("sleeperUsername") || "",
  );
  const [sleeperLeagues, setSleeperLeagues] = useState([]);
  const [awardsConfig, setAwardsConfig] = useState(
    JSON.parse(localStorage.getItem("awardsConfig")) || {},
  );
  const [fetchingLeagues, setFetchingLeagues] = useState(false);

  const handleTabChange = (e) => {
    setDefaultTab(e.target.value);
    localStorage.setItem("defaultAppTab", e.target.value);
  };

  const handleFetchLeaguesForSettings = async () => {
    if (!sleeperUsername) return;
    setFetchingLeagues(true);
    localStorage.setItem("sleeperUsername", sleeperUsername); // Save so other tabs auto-load it
    try {
      const res = await fetch(
        `${apiBase}/api/sleeper/leagues/${sleeperUsername}`,
      );
      if (res.ok) {
        const data = await res.json();
        setSleeperLeagues(data);
      }
    } catch (err) {
      console.error("Failed to fetch leagues:", err);
    } finally {
      setFetchingLeagues(false);
    }
  };

  const toggleLeagueAward = (leagueId) => {
    const updated = { ...awardsConfig, [leagueId]: !awardsConfig[leagueId] };
    setAwardsConfig(updated);
    localStorage.setItem("awardsConfig", JSON.stringify(updated));
  };

  // --- Handcuff Handlers ---
  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      setUploadStatus("");
    }
  };

  const handleUploadHandcuffs = async () => {
    if (!selectedFile) {
      setUploadStatus("Please select a FantasyPros CSV file first.");
      return;
    }

    setUploading(true);
    setUploadStatus("");

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await fetch(`${apiBase}/api/handcuffs/upload`, {
        method: "POST",
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        setUploadStatus(
          `Success! Updated depth charts for ${data.updated} players.`,
        );
        setSelectedFile(null);
      } else {
        const err = await response.json();
        setUploadStatus(`Upload failed: ${err.detail || "Server error"}`);
      }
    } catch (err) {
      console.error("Error uploading handcuffs CSV:", err);
      setUploadStatus("Error connecting to backend server.");
    } finally {
      setUploading(false);
    }
  };

  // --- FantasyPros Cheat Sheet Handlers ---
  const handleFpFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFpFile(e.target.files[0]);
      setFpUploadStatus("");
    }
  };

  const handleUploadFp = async () => {
    if (!fpFile) {
      setFpUploadStatus("Please select a FantasyPros Cheat Sheet CSV first.");
      return;
    }

    setFpUploading(true);
    setFpUploadStatus("");

    const formData = new FormData();
    formData.append("file", fpFile);

    try {
      const response = await fetch(`${apiBase}/api/fantasypros/upload`, {
        method: "POST",
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        setFpUploadStatus(
          `Success! Processed ${data.processed_records} cheat sheet records.`,
        );
        setFpFile(null); // Clear input on success
      } else {
        const err = await response.json();
        setFpUploadStatus(`Upload failed: ${err.detail || "Server error"}`);
      }
    } catch (err) {
      console.error("Error uploading FantasyPros CSV:", err);
      setFpUploadStatus("Error connecting to backend server.");
    } finally {
      setFpUploading(false);
    }
  };

  return (
    <div className="team-rankings-container">
      <div className="rankings-header">
        <h2>TI Model Settings & Calibration</h2>
        <button className="save-btn" onClick={handleSaveSettings}>
          Save Settings
        </button>
      </div>
      {/* --- Global App Preferences --- */}
      <div className="draft-control-panel">
        <h3>Application Preferences</h3>

        <div className="control-row">
          <div className="control-group">
            <label>Default Startup Tab</label>
            <select
              value={defaultTab}
              onChange={handleTabChange}
              style={{ minWidth: "200px" }}
            >
              <option value="DraftBoard">Draft Board</option>
              <option value="LiveDraft">Live Draft</option>
              <option value="WeeklyManager">Weekly Manager</option>
              <option value="Settings">Settings</option>
            </select>
          </div>
        </div>

        <h4
          style={{ color: "#00B5C1", marginTop: "24px", marginBottom: "8px" }}
        >
          Weekly Awards Configuration
        </h4>
        <p className="settings-description">
          Load your leagues to toggle which specific leagues should calculate
          and display Weekly Awards.
        </p>

        <div
          className="control-row upload-row"
          style={{ marginBottom: "16px" }}
        >
          <div className="control-group file-group">
            <input
              type="text"
              placeholder="Sleeper Username"
              value={sleeperUsername}
              onChange={(e) => setSleeperUsername(e.target.value)}
              style={{ width: "250px" }}
            />
          </div>
          <button
            className="manual-fetch-btn"
            onClick={handleFetchLeaguesForSettings}
            disabled={fetchingLeagues || !sleeperUsername}
          >
            {fetchingLeagues ? "Loading..." : "Load Leagues"}
          </button>
        </div>

        {sleeperLeagues.length > 0 && (
          <div
            className="league-awards-toggles"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "12px",
              marginTop: "12px",
            }}
          >
            {sleeperLeagues.map((lg) => {
              // Default to true if the user hasn't explicitly disabled it yet
              const isEnabled = awardsConfig[lg.league_id] !== false;

              return (
                <div
                  key={lg.league_id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    backgroundColor: "#0A1526",
                    padding: "12px",
                    borderRadius: "6px",
                    border: "1px solid #1B3054",
                  }}
                >
                  <span style={{ fontWeight: 600 }}>
                    {lg.name} ({lg.season})
                  </span>
                  <button
                    onClick={() => toggleLeagueAward(lg.league_id)}
                    style={{
                      backgroundColor: isEnabled ? "#32CD32" : "#FC4C02",
                      color: "#0A1526",
                      border: "none",
                      padding: "6px 12px",
                      borderRadius: "4px",
                      cursor: "pointer",
                      fontWeight: 700,
                    }}
                  >
                    {isEnabled ? "Awards Enabled" : "Awards Disabled"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {/* --- Sleeper Master Sync Section --- */}
      <div className="draft-control-panel">
        <h3>Sleeper Master NFL Database Sync</h3>
        <p className="settings-description">
          Pulls the latest active NFL player list from Sleeper. Run this FIRST
          to ensure all rookies and missing players are in the database before
          uploading projections.
        </p>
        <div className="control-row upload-row">
          <button
            className="manual-fetch-btn upload-btn"
            onClick={handleSyncSleeper}
            disabled={syncingSleeper}
            style={{ backgroundColor: "#28a745", borderColor: "#28a745" }}
          >
            {syncingSleeper ? "Syncing..." : "Sync Sleeper Database"}
          </button>
        </div>
        {sleeperSyncStatus && (
          <div
            className={`upload-status-text ${sleeperSyncStatus.includes("Success") ? "status-success" : "status-error"}`}
          >
            {sleeperSyncStatus}
          </div>
        )}
      </div>
      {savedMsg && <div className="save-status-msg">{savedMsg}</div>}

      {/* --- FantasyPros Cheat Sheet Ingestion Section --- */}
      <div className="draft-control-panel">
        <h3>FantasyPros Cheat Sheet Ingestion</h3>
        <p className="settings-description">
          Upload a FantasyPros Cheat Sheet CSV to import player ranks, tiers,
          upside, bust, SoS, and ECR vs ADP.
        </p>

        <div className="control-row upload-row">
          <div className="control-group file-group">
            <label>Select CSV/TSV File</label>
            <input
              type="file"
              accept=".csv,.tsv,.txt"
              onChange={handleFpFileChange}
            />
          </div>

          <button
            className="manual-fetch-btn upload-btn"
            onClick={handleUploadFp}
            disabled={fpUploading || !fpFile}
            style={{ backgroundColor: "#00B5C1", borderColor: "#00B5C1" }} // Teal styling differentiation
          >
            {fpUploading ? "Processing..." : "Upload Cheat Sheet"}
          </button>
        </div>

        {fpUploadStatus && (
          <div
            className={`upload-status-text ${fpUploadStatus.includes("Success") ? "status-success" : "status-error"}`}
          >
            {fpUploadStatus}
          </div>
        )}
      </div>

      {/* --- Handcuff Rankings Ingestion Section --- */}
      <div className="draft-control-panel">
        <h3>FantasyPros Handcuff Rankings Ingestion</h3>
        <p className="settings-description">
          Upload a 2026 FantasyPros Handcuffs CSV to update running back depth
          chart orders (RB1 vs RB2) across PostgreSQL.
        </p>

        <div className="control-row upload-row">
          <div className="control-group file-group">
            <label>Select CSV File</label>
            <input type="file" accept=".csv" onChange={handleFileChange} />
          </div>

          <button
            className="manual-fetch-btn upload-btn"
            onClick={handleUploadHandcuffs}
            disabled={uploading || !selectedFile}
          >
            {uploading ? "Processing..." : "Upload & Process CSV"}
          </button>
        </div>

        {uploadStatus && (
          <div
            className={`upload-status-text ${uploadStatus.includes("Success") ? "status-success" : "status-error"}`}
          >
            {uploadStatus}
          </div>
        )}
      </div>

      {/* --- Role & Target Share Discounts Section --- */}
      <div className="draft-control-panel">
        <h3>Role & Target Share Discounts</h3>
        <div className="control-row">
          <div className="control-group">
            <label>RB2 Committee Discount</label>
            <input
              type="number"
              step="0.05"
              value={roleDiscounts.RB2}
              onChange={(e) =>
                setRoleDiscounts({
                  ...roleDiscounts,
                  RB2: parseFloat(e.target.value),
                })
              }
            />
          </div>
          <div className="control-group">
            <label>WR2 Target Share Discount</label>
            <input
              type="number"
              step="0.05"
              value={roleDiscounts.WR2}
              onChange={(e) =>
                setRoleDiscounts({
                  ...roleDiscounts,
                  WR2: parseFloat(e.target.value),
                })
              }
            />
          </div>
          <div className="control-group">
            <label>WR3 Target Share Discount</label>
            <input
              type="number"
              step="0.05"
              value={roleDiscounts.WR3}
              onChange={(e) =>
                setRoleDiscounts({
                  ...roleDiscounts,
                  WR3: parseFloat(e.target.value),
                })
              }
            />
          </div>
        </div>
      </div>

      {/* --- Rookie Weights Section --- */}
      <div className="draft-control-panel">
        <h3>Rookie Formula Weights (Standard)</h3>
        <div className="control-row">
          <div className="control-group">
            <label>Projection Weight (%)</label>
            <input
              type="number"
              value={rookieWeights.proj}
              onChange={(e) =>
                setRookieWeights({
                  ...rookieWeights,
                  proj: parseInt(e.target.value, 10),
                })
              }
            />
          </div>
          <div className="control-group">
            <label>Team Synergy Weight (%)</label>
            <input
              type="number"
              value={rookieWeights.team}
              onChange={(e) =>
                setRookieWeights({
                  ...rookieWeights,
                  team: parseInt(e.target.value, 10),
                })
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ModelSettingsView;
