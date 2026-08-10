// Fantasy_Draft_UI/src/App.jsx
import {
  NavLink,
  Navigate,
  Route,
  BrowserRouter as Router,
  Routes,
} from "react-router-dom";
import "./App.css";
import BoardView from "./BoardView";
import LiveDraftView from "./LiveDraftView";
import ModelSettingsView from "./ModelSettingsView";
import TeamRankingsView from "./TeamRankingsView";

function App() {
  return (
    <Router>
      <div className="app-container">
        <header className="app-header">
          <h1>Draft Room</h1>
          <nav className="tabs">
            <NavLink
              to="/board/standard"
              className={({ isActive }) => (isActive ? "tab active" : "tab")}
            >
              Standard Board
            </NavLink>
            <NavLink
              to="/board/dynasty"
              className={({ isActive }) => (isActive ? "tab active" : "tab")}
            >
              Dynasty Board
            </NavLink>
            <NavLink
              to="/board/chopped"
              className={({ isActive }) => (isActive ? "tab active" : "tab")}
            >
              Chopped Board
            </NavLink>
            <NavLink
              to="/rankings"
              className={({ isActive }) => (isActive ? "tab active" : "tab")}
            >
              Team Unit Ranks
            </NavLink>
            <NavLink
              to="/live-draft"
              className={({ isActive }) => (isActive ? "tab active" : "tab")}
            >
              Live Assistant
            </NavLink>
            <NavLink
              to="/settings"
              className={({ isActive }) => (isActive ? "tab active" : "tab")}
            >
              Model Settings
            </NavLink>
          </nav>
        </header>

        <main className="board-content">
          <Routes>
            <Route
              path="/"
              element={<Navigate to="/board/standard" replace />}
            />
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
