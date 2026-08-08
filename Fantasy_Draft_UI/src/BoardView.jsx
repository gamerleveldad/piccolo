// src/BoardView.jsx
import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { DndContext, closestCenter } from '@dnd-kit/core';
import { SortableContext, arrayMove, verticalListSortingStrategy } from '@dnd-kit/sortable';
import SortablePlayerRow from './SortablePlayerRow';

const BoardView = () => {
  const { boardType } = useParams();
  const [players, setPlayers] = useState([]);
  const [viewMode, setViewMode] = useState('compact');
  
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8005';

  useEffect(() => {
    const fetchBoard = async () => {
      try {
        const response = await fetch(`${apiBase}/api/ti/board/${boardType}`);
        if (response.ok) {
          const data = await response.json();
          setPlayers(data.draft_board || []);
        }
      } catch (error) {
        console.error("Error fetching board:", error);
      }
    };
    fetchBoard();
  }, [boardType, apiBase]);

  const handleDragEnd = async (event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = players.findIndex((p) => p.player_id === active.id);
    const newIndex = players.findIndex((p) => p.player_id === over.id);

    const newPlayers = arrayMove(players, oldIndex, newIndex);
    setPlayers(newPlayers); // Optimistic UI update

    const targetAbovePlayerId = newIndex > 0 ? newPlayers[newIndex - 1].player_id : null;
    const targetBelowPlayerId = newIndex < newPlayers.length - 1 ? newPlayers[newIndex + 1].player_id : null;

    try {
      await fetch(`${apiBase}/api/ti/board/${boardType}/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_id: active.id,
          target_above_player_id: targetAbovePlayerId,
          target_below_player_id: targetBelowPlayerId
        })
      });
    } catch (error) {
      console.error("Failed to persist drag order:", error);
    }
  };

  return (
    <div>
      <div className="board-controls">
        <h2>{boardType.charAt(0).toUpperCase() + boardType.slice(1)} Rankings</h2>
        <div className="view-toggles">
          <button 
            className={viewMode === 'compact' ? 'active' : ''} 
            onClick={() => setViewMode('compact')}
          >
            Compact View
          </button>
          <button 
            className={viewMode === 'grid' ? 'active' : ''} 
            onClick={() => setViewMode('grid')}
          >
            Grid View
          </button>
        </div>
      </div>

      <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <div className={`player-list ${viewMode}`}>
          <SortableContext items={players.map((p) => p.player_id)} strategy={verticalListSortingStrategy}>
            {players.map((player, index) => (
              <SortablePlayerRow 
                key={player.player_id} 
                player={player} 
                displayRank={index + 1} 
                viewMode={viewMode} 
              />
            ))}
          </SortableContext>
        </div>
      </DndContext>
    </div>
  );
};

export default BoardView;