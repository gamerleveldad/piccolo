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
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');

  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8005';

  const handleSaveSettings = () => {
    setSavedMsg('Settings updated for current draft session!');
    setTimeout(() => setSavedMsg(''), 3000);
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      setUploadStatus('');
    }
  };

  const handleUploadHandcuffs = async () => {
    if (!selectedFile) {
      setUploadStatus('Please select a FantasyPros CSV file first.');
      return;
    }

    setUploading(true);
    setUploadStatus('');

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await fetch(`${apiBase}/api/handcuffs/upload`, {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        setUploadStatus(`Success! Updated depth charts for ${data.updated} players.`);
        setSelectedFile(null);
      } else {
        const err = await response.json();
        setUploadStatus(`Upload failed: ${err.detail || 'Server error'}`);
      }
    } catch (err) {
      console.error('Error uploading handcuffs CSV:', err);
      setUploadStatus('Error connecting to backend server.');
    } finally {
      setUploading(false);
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

      {savedMsg && <div className="save-status-msg">{savedMsg}</div>}

      {/* --- Handcuff Rankings Ingestion Section --- */}
      <div className="draft-control-panel">
        <h3>FantasyPros Handcuff Rankings Ingestion</h3>
        <p className="settings-description">
          Upload a 2026 FantasyPros Handcuffs CSV to update running back depth chart orders (RB1 vs RB2) across PostgreSQL.
        </p>

        <div className="control-row upload-row">
          <div className="control-group file-group">
            <label>Select CSV File</label>
            <input 
              type="file" 
              accept=".csv" 
              onChange={handleFileChange} 
            />
          </div>

          <button 
            className="manual-fetch-btn upload-btn" 
            onClick={handleUploadHandcuffs} 
            disabled={uploading || !selectedFile}
          >
            {uploading ? 'Processing...' : 'Upload & Process CSV'}
          </button>
        </div>

        {uploadStatus && (
          <div className={`upload-status-text ${uploadStatus.includes('Success') ? 'status-success' : 'status-error'}`}>
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
              onChange={(e) => setRoleDiscounts({ ...roleDiscounts, RB2: parseFloat(e.target.value) })}
            />
          </div>
          <div className="control-group">
            <label>WR2 Target Share Discount</label>
            <input
              type="number"
              step="0.05"
              value={roleDiscounts.WR2}
              onChange={(e) => setRoleDiscounts({ ...roleDiscounts, WR2: parseFloat(e.target.value) })}
            />
          </div>
          <div className="control-group">
            <label>WR3 Target Share Discount</label>
            <input
              type="number"
              step="0.05"
              value={roleDiscounts.WR3}
              onChange={(e) => setRoleDiscounts({ ...roleDiscounts, WR3: parseFloat(e.target.value) })}
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
              onChange={(e) => setRookieWeights({ ...rookieWeights, proj: parseInt(e.target.value, 10) })}
            />
          </div>
          <div className="control-group">
            <label>Team Synergy Weight (%)</label>
            <input
              type="number"
              value={rookieWeights.team}
              onChange={(e) => setRookieWeights({ ...rookieWeights, team: parseInt(e.target.value, 10) })}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ModelSettingsView;