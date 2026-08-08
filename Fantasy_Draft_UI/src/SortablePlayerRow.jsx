// src/SortablePlayerRow.jsx
import React from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

const SortablePlayerRow = ({ player, displayRank, viewMode }) => {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: player.player_id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    backgroundColor: player.is_pinned ? '#f8fdf8' : '#ffffff',
  };

  // Build the ESPN Logo URL dynamically
  const getLogoUrl = (team) => {
    if (!team || team === 'UNK' || team === 'FA') return 'https://a.espncdn.com/i/teamlogos/nfl/500/nfl.png';
    const cleanTeam = team === 'WAS' ? 'wsh' : team.toLowerCase();
    return `https://a.espncdn.com/i/teamlogos/nfl/500/${cleanTeam}.png`;
  };

  if (viewMode === 'compact') {
    return (
      <div ref={setNodeRef} style={style} className="player-row compact" {...attributes} {...listeners}>
        <div className="rank-col">{displayRank}</div>
        <img src={getLogoUrl(player.team)} alt={player.team} className="team-logo-small" />
        <div className="name-col">
          <strong>{player.player_name}</strong> - {player.position} ({player.team || 'FA'})
        </div>
        <div className="stat-col">Bye: {player.bye_week || '-'}</div>
        <div className="stat-col">TI: {player.ti_score}</div>
        <div className="stat-col">Dyn: {player.ti_score_dynasty || '-'}</div>
      </div>
    );
  }

  // Grid View
  return (
    <div ref={setNodeRef} style={style} className="player-row grid-card" {...attributes} {...listeners}>
      <div className="card-header">
        <div className="header-left">
          <span className="grid-rank">#{displayRank}</span>
          <img src={getLogoUrl(player.team)} alt={player.team} className="team-logo-large" />
          <div className="header-names">
            <h3>{player.player_name}</h3>
            <span>{player.position} - {player.team || 'Free Agent'}</span>
          </div>
        </div>
        <div className="header-right">
          <span className="badge">Age: {player.age || '-'}</span>
          <span className="badge">Bye: {player.bye_week || '-'}</span>
        </div>
      </div>
      <div className="card-body">
        <div className="stat-box main-stat">
          <label>TI Score</label>
          <div>{player.ti_score}</div>
        </div>
        <div className="stat-box main-stat">
          <label>Dynasty TI</label>
          <div>{player.ti_score_dynasty || '-'}</div>
        </div>
        <div className="stat-box">
          <label>2026 Proj</label>
          <div>{player.projected_points || '0.0'}</div>
        </div>
        <div className="stat-box">
          <label>Next Game</label>
          <div>{player.projected_next_game || '0.0'}</div>
        </div>
        <div className="stat-box">
          <label>Next 4</label>
          <div>{player.projected_next_4 || '0.0'}</div>
        </div>
      </div>
    </div>
  );
};

export default SortablePlayerRow;