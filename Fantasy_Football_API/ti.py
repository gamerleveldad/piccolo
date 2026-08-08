# Fantasy_Football_API/ti.py

import logging

logger = logging.getLogger("ti")

# Positional synergy weights based on team unit rankings (1-32).
# Positive weight means a better unit rank (1) increases value.
# Negative weight means a worse unit rank (32) increases value (e.g., bad defense helping QB).
POSITIONAL_SYNERGY_MATRIX = {
    "QB": {
        "oline_rank": 0.03,  # +++ Strong line protects QB
        "wr_rank": 0.02,     # ++ Strong WRs elevate target quality
        "te_rank": 0.02,     # ++ Strong TEs give reliable safety valve
        "def_rank": -0.01,   # - Bad defense forces pass-heavy game scripts
    },
    "RB": {
        "oline_rank": 0.03,  # +++ Strong line opens rushing lanes
        "def_rank": 0.02,    # ++ Strong defense leads to positive clock-killing scripts
    },
    "TE": {
        "qb_rank": 0.03,     # +++ Strong QB ensures accurate target distribution
        "wr_rank": -0.02,    # -- Top-tier WRs siphon target share away
    },
    "WR": {
        "qb_rank": 0.03,     # +++ High-quality QB play increases efficient target rate
        "oline_rank": 0.01,  # + Gives plays time to develop downfield
        "te_rank": -0.01,    # - Strong TE takes away intermediate targets
        "def_rank": -0.01,   # - Bad defense leads to trailing game scripts / more passing
        "rb_rank": -0.01,    # - Strong run game reduces overall team pass attempts
    },
    "DEF": {
        "qb_rank": 0.03,     # +++ Efficient QB maintains drive control and field position
        "off_rank": 0.01,    # + High-scoring offense forces opponent into risky pass plays
    }
}

def calculate_team_synergy_multiplier(position: str, team_ranks: dict) -> float:
    """
    Calculates the team synergy multiplier using unit rank distance from average (16.5).
    
    Args:
        position (str): Player position (QB, RB, WR, TE, DEF).
        team_ranks (dict): Dictionary of unit ranks (e.g., {'oline_rank': 5, 'def_rank': 20}).
        
    Returns:
        float: Team synergy multiplier centered around 1.0.
    """
    pos_rules = POSITIONAL_SYNERGY_MATRIX.get(position.upper(), {})
    if not pos_rules or not team_ranks:
        return 1.0

    multiplier_offset = 0.0
    
    for rank_key, weight in pos_rules.items():
        if rank_key in team_ranks and team_ranks[rank_key] is not None:
            # 16.5 is neutral rank. Rank 1 gives +15.5, Rank 32 gives -15.5.
            rank_distance = 16.5 - team_ranks[rank_key]
            multiplier_offset += rank_distance * weight / 100.0

    return 1.0 + multiplier_offset


def calculate_ti_score(
    projected_pts: float,
    historical_pts: float,
    coefficient_of_variation: float,
    team_ranks: dict,
    position: str,
    age: int = None,
    depth_chart_order: int = None,
    weights: dict = None,
    dynasty_weights: dict = None
) -> dict:
    
    projected_pts = projected_pts if projected_pts is not None else 0.0
    historical_pts = historical_pts if historical_pts is not None else 0.0

    if weights is None:
        weights = {"proj": 0.50, "hist": 0.25, "cons": 0.15, "team": 0.10}
    if dynasty_weights is None:
        dynasty_weights = {"proj": 0.50, "hist": 0.15, "cons": 0.15, "age": 0.10, "team": 0.10}

    base_pts = projected_pts if projected_pts > 0 else historical_pts
    hist_value = historical_pts if historical_pts > 0 else base_pts
    hist_ratio = hist_value / base_pts if base_pts > 0 else 1.0

    baseline_cv = 0.40
    cv_score = coefficient_of_variation if coefficient_of_variation is not None else baseline_cv
    consistency_multiplier = 1.0 + (baseline_cv - cv_score)
    team_synergy_mult = calculate_team_synergy_multiplier(position, team_ranks)

    # 1. Standard TI
    std_multiplier = (
        (weights["proj"] * 1.0) +
        (weights["hist"] * hist_ratio) +
        (weights["cons"] * consistency_multiplier) +
        (weights["team"] * team_synergy_mult)
    )
    ti_final = base_pts * std_multiplier

    # 2. Dynasty TI
    player_age = age if age is not None else 26
    age_multiplier = 1.0 + ((26 - player_age) * 0.05)

    dyn_multiplier = (
        (dynasty_weights["proj"] * 1.0) +
        (dynasty_weights["hist"] * hist_ratio) +
        (dynasty_weights["cons"] * consistency_multiplier) +
        (dynasty_weights["age"] * age_multiplier) +
        (dynasty_weights["team"] * team_synergy_mult)
    )
    ti_dynasty_final = base_pts * dyn_multiplier

    # --- Depth Chart Backup Penalty ---
    # Divide score by 10 if player is not in a starting role
    is_starter = True
    if depth_chart_order is not None and depth_chart_order > 0:
        pos_upper = (position or "").upper()
        if pos_upper == "QB" and depth_chart_order >= 2:
            is_starter = False
        elif pos_upper == "RB" and depth_chart_order >= 3:
            is_starter = False
        elif pos_upper == "WR" and depth_chart_order >= 4:
            is_starter = False
        elif pos_upper == "TE" and depth_chart_order >= 2:
            is_starter = False

    if not is_starter:
        ti_final = ti_final / 10.0
        ti_dynasty_final = ti_dynasty_final / 10.0

    return {
        "ti_score": round(ti_final, 2),
        "ti_score_dynasty": round(ti_dynasty_final, 2),
        "is_starter": is_starter
    }