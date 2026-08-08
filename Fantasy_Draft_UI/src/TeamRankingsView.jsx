// Fantasy_Draft_UI/src/TeamRankingsView.jsx
import React, { useState, useEffect } from 'react';
import { DndContext, closestCenter } from '@dnd-kit/core';
import { SortableContext, arrayMove, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

// Full list of 32 NFL team abbreviations
const ALL_TEAMS = [
  'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE',
  'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
  'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
  'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS'
];

// Unit category definitions
const UNIT_CATEGORIES = [
  { key: 'oline_rank', label: 'Offensive Line' },
  { key: 'qb_rank', label: 'Quarterback Room' },
  { key: 'wr_rank', label: 'Wide Receiver Corps' },
  { key: 'te_rank', label: 'Tight End Group' },
  { key: 'rb_rank', label: 'Running Back Room' },
  { key: 'def_rank', label: 'Defense Unit' },
  { key: 'off_rank', label: 'Overall Offense' },
];

// Individual Draggable Team Row
const SortableTeamRow = ({ team, rank }) => {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: team });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const getLogoUrl = (teamAbbr) => {
    const cleanTeam = teamAbbr === 'WAS' ? 'wsh' : teamAbbr.toLowerCase();
    return `https://a.espncdn.com/i/teamlogos/nfl/500/${cleanTeam}.png`;
  };

  return (
    <div ref={setNodeRef} style={style} className="team-rank-row" {...attributes} {...listeners}>
      <span className="team-rank-number">#{rank}</span>
      <img src={getLogoUrl(team)} alt={team} className="team-logo-small" />
      <span className="team-abbr-text">{team}</span>
    </div>
  );
};

const TeamRankingsView = () => {
  const [selectedUnit, setSelectedUnit] = useState('oline_rank');
  const [fullMatrix, setFullMatrix] = useState({});
  const [currentOrder, setCurrentOrder] = useState(ALL_TEAMS);
  const [saveStatus, setSaveStatus] = useState('');

  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8005';

  // Fetch initial matrix from API
  useEffect(() => {
    const fetchRankings = async () => {
      try {
        const res = await fetch(`${apiBase}/api/rankings/team-units`);
        if (res.ok) {
          const data = await res.json();
          const matrix = data.rankings || {};
          setFullMatrix(matrix);

          // Populate current unit order based on fetched DB values
          const sorted = [...ALL_TEAMS].sort((a, b) => {
            const rankA = matrix[a]?.[selectedUnit] || 16;
            const rankB = matrix[b]?.[selectedUnit] || 16;
            return rankA - rankB;
          });
          setCurrentOrder(sorted);
        }
      } catch (err) {
        console.error("Failed to load team rankings:", err);
      }
    };
    fetchRankings();
  }, [apiBase]);

  // Handle unit category tab switch
  const handleUnitChange = (unitKey) => {
    setSelectedUnit(unitKey);
    setSaveStatus('');

    // Re-sort current view order according to selected unit's stored values
    const sorted = [...ALL_TEAMS].sort((a, b) => {
      const rankA = fullMatrix[a]?.[unitKey] || 16;
      const rankB = fullMatrix[b]?.[unitKey] || 16;
      return rankA - rankB;
    });
    setCurrentOrder(sorted);
  };

  // Drag-and-drop reorder handler
  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = currentOrder.indexOf(active.id);
    const newIndex = currentOrder.indexOf(over.id);

    const updatedOrder = arrayMove(currentOrder, oldIndex, newIndex);
    setCurrentOrder(updatedOrder);

    // Update fullMatrix in local memory
    const updatedMatrix = { ...fullMatrix };
    updatedOrder.forEach((team, index) => {
      if (!updatedMatrix[team]) updatedMatrix[team] = {};
      updatedMatrix[team][selectedUnit] = index + 1; // 1 to 32 scale
    });
    setFullMatrix(updatedMatrix);
  };

  // Save all rankings to the API
  const handleSave = async () => {
    setSaveStatus('Saving...');
    
    // Structure payload for POST /api/rankings/team-units
    const payload = {};
    ALL_TEAMS.forEach((team) => {
      payload[team] = {
        oline_rank: fullMatrix[team]?.oline_rank || 16,
        qb_rank: fullMatrix[team]?.qb_rank || 16,
        wr_rank: fullMatrix[team]?.wr_rank || 16,
        te_rank: fullMatrix[team]?.te_rank || 16,
        rb_rank: fullMatrix[team]?.rb_rank || 16,
        def_rank: fullMatrix[team]?.def_rank || 16,
        off_rank: fullMatrix[team]?.off_rank || 16,
      };
    });

    try {
      const res = await fetch(`${apiBase}/api/rankings/team-units`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setSaveStatus('Rankings saved successfully!');
      } else {
        setSaveStatus('Error saving rankings.');
      }
    } catch (err) {
      console.error("Failed to save team rankings:", err);
      setSaveStatus('Failed to connect to API.');
    }
  };

  return (
    <div className="team-rankings-container">
      <div className="rankings-header">
        <h2>Team Unit Rankings (1 = Strongest, 32 = Weakest)</h2>
        <button className="save-btn" onClick={handleSave}>Save Rankings</button>
      </div>

      {saveStatus && <div className="save-status-msg">{saveStatus}</div>}

      {/* Category Selection Tabs */}
      <div className="unit-category-tabs">
        {UNIT_CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            className={`unit-tab ${selectedUnit === cat.key ? 'active' : ''}`}
            onClick={() => handleUnitChange(cat.key)}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Draggable List */}
      <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={currentOrder} strategy={verticalListSortingStrategy}>
          <div className="team-rankings-list">
            {currentOrder.map((team, index) => (
              <SortableTeamRow key={team} team={team} rank={index + 1} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
};

export default TeamRankingsView;