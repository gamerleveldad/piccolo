// Fantasy_Draft_UI/src/ModelSettingsView.jsx
import React, { useState } from 'react';

const ModelSettingsView = () => {
  const [roleDiscounts, setRoleDiscounts] = useState({
    RB2: 0.85,
    WR2: 0.90,
    WR3: 0.80,
  });

  const [rookieWeights, setRookieWeights] = useState({
    proj: 60,
    team: 40,
  });

  const [savedMsg, setSavedMsg] = useState('');

  const handleSave = () => {
    setSavedMsg('Settings updated for current draft session!');
    setTimeout(() => setSavedMsg(''), 3000);
  };

  return (
    <div className="team-rankings-container">
      <div className="rankings-header">
        <h2>TI Model Settings & Calibration</h2>
        <button className="save-btn" onClick={handleSave}>Save Settings</button>
      </div>

      {savedMsg && <div className="save-status-msg">{savedMsg}</div>}

      <div className="draft-control-panel">
        <h3>Role & Target Share Discounts</h3>
        <div className="control-row">
          <div className="control-group">
            <label>RB2 Committee Discount</label>
            <input
              type="number" step="0.05"
              value={roleDiscounts.RB2}
              onChange={(e) => setRoleDiscounts({ ...roleDiscounts, RB2: parseFloat(e.target.value) })}
            />
          </div>
          <div className="control-group">
            <label>WR2 Target Share Discount</label>
            <input
              type="number" step="0.05"
              value={roleDiscounts.WR2}
              onChange={(e) => setRoleDiscounts({ ...roleDiscounts, WR2: parseFloat(e.target.value) })}
            />
          </div>
          <div className="control-group">
            <label>WR3 Target Share Discount</label>
            <input
              type="number" step="0.05"
              value={roleDiscounts.WR3}
              onChange={(e) => setRoleDiscounts({ ...roleDiscounts, WR3: parseFloat(e.target.value) })}
            />
          </div>
        </div>
      </div>

      <div className="draft-control-panel">
        <h3>Rookie Formula Weights (Standard)</h3>
        <div className="control-row">
          <div className="control-group">
            <label>Projection Weight (%)</label>
            <input
              type="number"
              value={rookieWeights.proj}
              onChange={(e) => setRookieWeights({ ...rookieWeights, proj: parseInt(e.target.value) })}
            />
          </div>
          <div className="control-group">
            <label>Team Synergy Weight (%)</label>
            <input
              type="number"
              value={rookieWeights.team}
              onChange={(e) => setRookieWeights({ ...rookieWeights, team: parseInt(e.target.value) })}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ModelSettingsView;