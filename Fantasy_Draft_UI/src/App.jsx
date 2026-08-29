import { useEffect, useState } from "react";
import "./App.css";
import DraftBoardView from "./DraftBoardView"; // Adjust this import name if your standard board file is named differently
import LiveDraftView from "./LiveDraftView";
import ModelSettingsView from "./ModelSettingsView";
import WeeklyManagerView from "./WeeklyManagerView";

function App() {
  const [activeTab, setActiveTab] = useState("Settings");

  useEffect(() => {
    const savedTab = localStorage.getItem("defaultAppTab") || "LiveDraft";
    setActiveTab(savedTab);
  }, []);

  return (
    <div className="app-container">
      {/* Unified Navigation Bar (No Emojis) */}
      <nav className="top-nav-bar">
        <div className="nav-brand">TREY INDEX HUB</div>
        <div className="nav-links">
          <button
            className={activeTab === "DraftBoard" ? "active" : ""}
            onClick={() => setActiveTab("DraftBoard")}
          >
            Draft Board
          </button>
          <button
            className={activeTab === "LiveDraft" ? "active" : ""}
            onClick={() => setActiveTab("LiveDraft")}
          >
            Live Draft
          </button>
          <button
            className={activeTab === "WeeklyManager" ? "active" : ""}
            onClick={() => setActiveTab("WeeklyManager")}
          >
            Weekly Manager
          </button>
          <button
            className={activeTab === "Settings" ? "active" : ""}
            onClick={() => setActiveTab("Settings")}
          >
            Settings
          </button>
        </div>
      </nav>

      {/* Main Tab Content Routing */}
      <div className="tab-content">
        {activeTab === "DraftBoard" && <DraftBoardView />}
        {activeTab === "LiveDraft" && <LiveDraftView />}
        {activeTab === "WeeklyManager" && <WeeklyManagerView />}
        {activeTab === "Settings" && <ModelSettingsView />}
      </div>
    </div>
  );
}

export default App;
