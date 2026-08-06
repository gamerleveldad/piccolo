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
    weights: dict = None
) -> dict:
    """
    Computes the composite Trey Index for a given player.
    
    Default Configuration:
        50% Current Projection
        25% Historical Average
        15% Consistency Index
        10% Team Synergy Index
    """
    if weights is None:
        weights = {
            "proj": 0.50,
            "hist": 0.25,
            "cons": 0.15,
            "team": 0.10
        }

    # 1. Historical Fallback (Rookies or missing history default to current projection)
    hist_value = historical_pts if historical_pts and historical_pts > 0 else projected_pts
    hist_ratio = hist_value / projected_pts if projected_pts > 0 else 1.0

    # 2. Consistency Modifier
    # Coefficient of Variation (CV) = StdDev / Mean. Average NFL CV is roughly 0.40.
    # Lower CV indicates higher weekly floor.
    baseline_cv = 0.40
    cv_score = coefficient_of_variation if coefficient_of_variation is not None else baseline_cv
    # Invert CV impact so lower variance increases the score multiplier
    consistency_multiplier = 1.0 + (baseline_cv - cv_score)

    # 3. Team Synergy Modifier
    team_synergy_mult = calculate_team_synergy_multiplier(position, team_ranks)

    # 4. Weighted Aggregate Trey Index Multiplier
    composite_multiplier = (
        (weights["proj"] * 1.0) +
        (weights["hist"] * hist_ratio) +
        (weights["cons"] * consistency_multiplier) +
        (weights["team"] * team_synergy_mult)
    )

    ti_final = round(projected_pts * composite_multiplier, 2)

    return {
        "ti": ti_final,
        "projected_pts": projected_pts,
        "historical_pts": hist_value,
        "consistency_multiplier": round(consistency_multiplier, 3),
        "team_synergy_multiplier": round(team_synergy_mult, 3),
        "composite_multiplier": round(composite_multiplier, 3)
    }