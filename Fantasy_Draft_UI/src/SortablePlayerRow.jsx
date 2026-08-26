// src/SortablePlayerRow.jsx
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useEffect, useState } from "react";
import Select, { components } from "react-select";

const TAG_OPTIONS = [
  {
    value: "PPR Monster",
    label: "PPR Monster",
    icon: "/icons/ppr.svg",
    color: "#F1C27D",
  },
  {
    value: "Injury Risk",
    label: "Injury Risk",
    icon: "/icons/injury.svg",
    color: "#E60000",
    outline: "#FFFFFF",
  },
  {
    value: "Breakout",
    label: "Breakout Potential",
    icon: "/icons/breakout.svg",
    color: "#87CEFA",
  },
  {
    value: "Rookie",
    label: "Rookie",
    icon: "/icons/rookie.svg",
    color: "#32CD32",
  },
  {
    value: "Handcuff",
    label: "Premium Handcuff",
    icon: "/icons/handcuff.svg",
    color: "#C0C0C0",
  },
  {
    value: "DND",
    label: "Do Not Draft",
    icon: "/icons/dnd.svg",
    color: "#FF2400",
  },
  { value: "Star", label: "Star", icon: "/icons/star.svg", color: "#FFD700" },
  {
    value: "Regression",
    label: "Regression Candidate",
    icon: "/icons/regression.svg",
    color: "#B22222",
  },
  {
    value: "Hidden Gem",
    label: "Hidden Gem",
    icon: "/icons/gem.svg",
    color: "#9966CC",
  },
  {
    value: "Goalline",
    label: "Goalline Back",
    icon: "/icons/goalline.svg",
    color: "#4682B4",
  },
];

// 5-Segment Battery Meter for Upside and Bust
const BatteryMeter = ({ value = 0, type = "upside" }) => {
  const score = Math.max(0, Math.min(5, Number(value) || 0));

  const getFillColor = () => {
    if (type === "upside") {
      if (score >= 4) return "#32CD32"; // Green
      if (score === 3) return "#FFD700"; // Yellow
      if (score === 2) return "#FFA500"; // Orange
      return "#FC4C02"; // Red
    } else {
      // Inverted for Bust: 1/5 is lowest risk (Green), 5/5 is highest risk (Red)
      if (score <= 2) return "#32CD32"; // Low Risk = Green
      if (score === 3) return "#FFD700"; // Moderate = Yellow
      if (score === 4) return "#FFA500"; // High = Orange
      return "#FC4C02"; // Severe Risk = Red
    }
  };

  const activeColor = getFillColor();

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "3px",
        marginTop: "4px",
      }}
    >
      {[1, 2, 3, 4, 5].map((blockIdx) => {
        const isFilled = blockIdx <= score;
        return (
          <div
            key={blockIdx}
            style={{
              width: "8px",
              height: "14px",
              borderRadius: "2px",
              backgroundColor: isFilled
                ? activeColor
                : "rgba(255, 255, 255, 0.1)",
              border: `1px solid ${isFilled ? activeColor : "rgba(255, 255, 255, 0.2)"}`,
              transition: "background-color 0.2s ease",
            }}
          />
        );
      })}
      <span
        style={{
          fontSize: "0.78rem",
          marginLeft: "5px",
          color: "#8BB2C9",
          fontWeight: 600,
        }}
      >
        {score}/5
      </span>
    </div>
  );
};

const SvgIcon = ({ icon, color, outline }) => {
  const filterStyle = outline
    ? `drop-shadow(1px 0px 0px ${outline}) drop-shadow(0px 1px 0px ${outline}) drop-shadow(-1px 0px 0px ${outline}) drop-shadow(0px -1px 0px ${outline})`
    : "none";

  return (
    <div
      style={{
        filter: filterStyle,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          width: "18px",
          height: "18px",
          backgroundColor: color,
          WebkitMaskImage: `url(${icon})`,
          WebkitMaskSize: "contain",
          WebkitMaskRepeat: "no-repeat",
          WebkitMaskPosition: "center",
          maskImage: `url(${icon})`,
          maskSize: "contain",
          maskRepeat: "no-repeat",
          maskPosition: "center",
        }}
      />
    </div>
  );
};

const CustomOption = (props) => (
  <components.Option {...props}>
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <SvgIcon
        icon={props.data.icon}
        color={props.data.color}
        outline={props.data.outline}
      />
      <span style={{ color: "#FFFFFF", fontSize: "0.85rem" }}>
        {props.data.label}
      </span>
    </div>
  </components.Option>
);

const CustomMultiValueLabel = (props) => (
  <components.MultiValueLabel {...props}>
    <div
      title={props.data.label}
      style={{ display: "flex", alignItems: "center", padding: "1px 3px" }}
    >
      <SvgIcon
        icon={props.data.icon}
        color={props.data.color}
        outline={props.data.outline}
      />
    </div>
  </components.MultiValueLabel>
);

const customSelectStyles = {
  control: (base) => ({
    ...base,
    backgroundColor: "#0A1526",
    borderColor: "#00B5C1",
    minHeight: "28px",
    height: "auto",
    width: "170px",
    boxShadow: "none",
    "&:hover": { borderColor: "#FC4C02" },
  }),
  valueContainer: (base) => ({
    ...base,
    padding: "0 4px",
    display: "flex",
    flexWrap: "wrap",
    gap: "2px",
  }),
  placeholder: (base) => ({ ...base, color: "#8BB2C9", fontSize: "0.78rem" }),
  input: (base) => ({ ...base, color: "#FFFFFF", fontSize: "0.8rem" }),
  menu: (base) => ({
    ...base,
    backgroundColor: "#12223D",
    border: "1px solid #00B5C1",
    zIndex: 9999,
  }),
  option: (base, state) => ({
    ...base,
    backgroundColor: state.isFocused ? "#1B3054" : "#12223D",
    cursor: "pointer",
  }),
  multiValue: (base) => ({
    ...base,
    backgroundColor: "rgba(0, 181, 193, 0.15)",
    border: "1px solid #00B5C1",
    borderRadius: "4px",
    margin: "1px",
  }),
  multiValueRemove: (base) => ({
    ...base,
    color: "#FC4C02",
    cursor: "pointer",
    ":hover": { backgroundColor: "rgba(252, 76, 2, 0.2)", color: "#FF6826" },
  }),
};

// Tooltip Descriptions
const TOOLTIPS = {
  fpRankTier: `The FP Rank is the ADP of that player from FantasyPros.\n\nTier 1 (The Elite): Top 3 to 5 overall picks. High-volume PPR anchors.\nTier 2 (Core Starters): 1st and early 2nd round cornerstones.\nTier 3 (Positional Advantages): Elite QBs/TEs alongside Rd 2/3 WRs.\nTier 4 & 5 (Solid Starters): Mid-round secure volume or high upside.\nTier 6-9 (Flex & Depth): WR3s, RB3s, and standard starting QBs.\nTier 10-11 (High-Upside Bench): Handcuffs, breakout candidates, rookies.\nTier 12-14 (Dart Throws & Defense): Speculative lotto tickets, platoon DSTs, kickers.`,
  upside: `High-ceiling potential due to role, talent, or opportunity based on consensus expert opinions.`,
  bust: `Higher risk due to injuries, volatility, or uncertain usage based on consensus expert opinions.`,
  sos: `An estimation of how favorable the remaining games are to getting closer to the ceiling. A 5 star SOS has the max chance of booming and a 1 star SOS means there is a higher chance of bust.`,
  ecrVsAdp: `This shows the Expert Consensus Ranking (ECR) compared to Average Draft Position. A positive number means that the player is more valued by the Experts and ranked higher. A negative number means that the player is more valued by general opinion.`,
};

const SortablePlayerRow = ({ player, displayRank, viewMode }) => {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({
      id: player.player_id,
    });

  const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8005";

  const getInitialTags = () => {
    const rawTags = player.custom_tags || [];
    return rawTags.map(
      (tagVal) =>
        TAG_OPTIONS.find((opt) => opt.value === tagVal) || {
          value: tagVal,
          label: tagVal,
          icon: "",
          color: "#FFFFFF",
        },
    );
  };

  const [selectedTags, setSelectedTags] = useState(getInitialTags);

  useEffect(() => {
    setSelectedTags(getInitialTags());
  }, [player.custom_tags]);

  const handleTagChange = async (selected) => {
    const newTags = selected || [];
    setSelectedTags(newTags);

    const tagValues = newTags.map((t) => t.value);
    try {
      await fetch(`${apiBase}/api/ti/player/${player.player_id}/tags`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: tagValues }),
      });
    } catch (err) {
      console.error("Failed to update player tags:", err);
    }
  };

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    backgroundColor: player.is_pinned ? "#162846" : "#12223D",
  };

  const getLogoUrl = (team) => {
    if (!team || team === "UNK" || team === "FA") {
      return "https://a.espncdn.com/i/teamlogos/nfl/500/nfl.png";
    }
    const cleanTeam = team === "WAS" ? "wsh" : team.toLowerCase();
    return `https://a.espncdn.com/i/teamlogos/nfl/500/${cleanTeam}.png`;
  };

  // Compact View
  if (viewMode === "compact") {
    return (
      <div
        ref={setNodeRef}
        style={style}
        className="player-row compact"
        {...attributes}
        {...listeners}
      >
        <div className="rank-col">{displayRank}</div>
        <img
          src={getLogoUrl(player.team)}
          alt={player.team}
          className="team-logo-small"
        />
        <div className="name-col">
          <strong>{player.player_name}</strong> - {player.position} (
          {player.team || "FA"})
          {player.pos_tier && (
            <span className="badge tier-badge compact-tier">
              {player.pos_tier}
            </span>
          )}
        </div>
        <div className="stat-col bye-col">Bye: {player.bye_week || "-"}</div>
        <div className="stat-col">TI: {player.ti_score}</div>
        <div className="stat-col">Dyn: {player.ti_score_dynasty || "-"}</div>
        <div className="stat-col cons-col">
          Cons: {player.consistency_label || player.consistency_score || "-"}
        </div>

        <div
          className="tag-icon-bar"
          style={{
            display: "flex",
            gap: "5px",
            alignItems: "center",
            minWidth: "40px",
          }}
        >
          {selectedTags.map((tag) => (
            <div key={tag.value} title={tag.label}>
              <SvgIcon
                icon={tag.icon}
                color={tag.color}
                outline={tag.outline}
              />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Expanded Grid Card View
  return (
    <div
      ref={setNodeRef}
      style={style}
      className="player-row grid-card"
      {...attributes}
      {...listeners}
    >
      <div className="card-header">
        <div className="header-left">
          <span className="grid-rank">#{displayRank}</span>
          <img
            src={getLogoUrl(player.team)}
            alt={player.team}
            className="team-logo-large"
          />
          <div className="header-names">
            <h3>{player.player_name}</h3>
            <span>
              {player.position} - {player.team || "Free Agent"}
            </span>
          </div>
        </div>

        <div className="header-right">
          <div
            className="tag-select-wrapper"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
          >
            <Select
              isMulti
              options={TAG_OPTIONS}
              value={selectedTags}
              onChange={handleTagChange}
              components={{
                Option: CustomOption,
                MultiValueLabel: CustomMultiValueLabel,
              }}
              styles={customSelectStyles}
              placeholder="Add Tags..."
              closeMenuOnSelect={false}
              isClearable={false}
            />
          </div>

          {/* Positional Tier Badge */}
          {player.pos_tier && (
            <span className="badge tier-badge" title={TOOLTIPS.fpRankTier}>
              {player.pos_tier}
            </span>
          )}

          {player.depth_chart_order && (
            <span className="badge depth-badge">
              Depth: {player.position}
              {player.depth_chart_order}
            </span>
          )}
          <span className="badge">Age: {player.age || "-"}</span>
          <span className="badge">Bye: {player.bye_week || "-"}</span>
        </div>
      </div>

      <div className="card-body">
        <div className="stat-box main-stat">
          <label>TI Score</label>
          <div>{player.ti_score}</div>
        </div>
        <div className="stat-box main-stat">
          <label>Dynasty TI</label>
          <div>{player.ti_score_dynasty || "-"}</div>
        </div>
        <div className="stat-box">
          <label>Consistency</label>
          <div>{player.consistency_label || "-"}</div>
        </div>

        {/* FantasyPros Cheatsheet Metrics with Tooltips & Battery Meters */}
        {player.fp_rank && (
          <>
            <div
              className="stat-box"
              title={TOOLTIPS.fpRankTier}
              style={{ cursor: "help" }}
            >
              <label>FP Rank / Tier ℹ️</label>
              <div>
                #{player.fp_rank} (T{player.fp_tier || "?"})
              </div>
            </div>

            <div
              className="stat-box"
              title={TOOLTIPS.upside}
              style={{ cursor: "help" }}
            >
              <label>Upside ℹ️</label>
              <BatteryMeter value={player.fp_upside} type="upside" />
            </div>

            <div
              className="stat-box"
              title={TOOLTIPS.bust}
              style={{ cursor: "help" }}
            >
              <label>Bust Risk ℹ️</label>
              <BatteryMeter value={player.fp_bust} type="bust" />
            </div>

            <div
              className="stat-box"
              title={TOOLTIPS.sos}
              style={{ cursor: "help" }}
            >
              <label>SoS ℹ️</label>
              <div style={{ color: "#FFD700", fontSize: "0.95rem" }}>
                {"★".repeat(player.fp_sos || 0)}
                {"☆".repeat(Math.max(0, 5 - (player.fp_sos || 0)))}
              </div>
            </div>

            <div
              className="stat-box"
              title={TOOLTIPS.ecrVsAdp}
              style={{ cursor: "help" }}
            >
              <label>ECR vs ADP ℹ️</label>
              <div
                style={{
                  color:
                    (player.fp_ecr_vs_adp || 0) >= 0 ? "#00B5C1" : "#FC4C02",
                  fontWeight: 700,
                }}
              >
                {(player.fp_ecr_vs_adp || 0) > 0
                  ? `+${player.fp_ecr_vs_adp}`
                  : player.fp_ecr_vs_adp || 0}
              </div>
            </div>
          </>
        )}

        <div className="stat-box">
          <label>2026 Proj</label>
          <div>{player.projected_points || "0.0"}</div>
        </div>
        <div className="stat-box">
          <label>Next 4</label>
          <div>{player.projected_next_4 || "0.0"}</div>
        </div>
      </div>
    </div>
  );
};

export default SortablePlayerRow;
