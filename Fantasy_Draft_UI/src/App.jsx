// Fantasy_Draft_UI/src/App.jsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import BoardView from './BoardView';
import TeamRankingsView from './TeamRankingsView';
import LiveDraftView from './LiveDraftView';
import ModelSettingsView from './ModelSettingsView';
import './App.css';

function App() {
  return (
    <Router>
      <div className="app-container">
        <header className="app-header">
          <h1>TI Draft Room</h1>
          <nav className="tabs">
            <NavLink to="/board/standard" className={({isActive}) => isActive ? "tab active" : "tab"}>Standard Board</NavLink>
            <NavLink to="/board/dynasty" className={({isActive}) => isActive ? "tab active" : "tab"}>Dynasty Board</NavLink>
            <NavLink to="/board/chopped" className={({isActive}) => isActive ? "tab active" : "tab"}>Chopped Board</NavLink>
            <NavLink to="/rankings" className={({isActive}) => isActive ? "tab active" : "tab"}>Team Unit Ranks</NavLink>
            <NavLink to="/live-draft" className={({isActive}) => isActive ? "tab active" : "tab"}>Live Assistant</NavLink>
            <NavLink to="/settings" className={({isActive}) => isActive ? "tab active" : "tab"}>Model Settings</NavLink>
          </nav>
        </header>

        <main className="board-content">
          <Routes>
            <Route path="/" element={<Navigate to="/board/standard" replace />} />
            <Route path="/board/:boardType" element={<BoardView />} />
            <Route path="/rankings" element={<TeamRankingsView />} />
            <Route path="/live-draft" element={<LiveDraftView />} />
            <Route path="/settings" element={<ModelSettingsView />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;