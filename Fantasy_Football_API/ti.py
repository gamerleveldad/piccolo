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
    if not team_ranks or not position:
        return 1.0
    pos = position.upper()
    
    # Map position to unit key
    unit_map = {
        "QB": "oline_rank",
        "RB": "oline_rank",
        "WR": "qb_rank",
        "TE": "qb_rank"
    }
    key = unit_map.get(pos, "off_rank")
    rank = team_ranks.get(key, 16)
    
    # Unit Rank 1 = +15% boost, Unit Rank 32 = -15% penalty
    return 1.0 + ((16.5 - rank) * 0.01)

def calculate_ti_score(
    projected_pts: float,
    historical_pts: float,
    coefficient_of_variation: float,
    team_ranks: dict,
    position: str,
    years_exp: int = None,
    age: int = None,
    depth_chart_order: int = None,
    role_discounts: dict = None,
    weights: dict = None,
    dynasty_weights: dict = None
) -> dict:
    
    projected_pts = float(projected_pts) if projected_pts is not None else 0.0
    historical_pts = float(historical_pts) if historical_pts is not None else 0.0

    if role_discounts is None:
        role_discounts = {"RB2": 0.85, "WR2": 0.90, "WR3": 0.80}

    pos_upper = (position or "WR").upper()
    team_synergy_mult = calculate_team_synergy_multiplier(pos_upper, team_ranks)
    player_age = age if age is not None else 25
    age_multiplier = 1.0 + ((26 - player_age) * 0.05)

    is_rookie = (years_exp == 0) or (historical_pts == 0.0 and projected_pts > 0)

    # --- ROOKIE FORMULA OVERRIDE ---
    if is_rookie:
        ti_final = (0.60 * projected_pts) + (0.40 * projected_pts * team_synergy_mult)
        ti_dynasty_final = (0.50 * projected_pts) + (0.30 * projected_pts * team_synergy_mult) + (0.20 * projected_pts * age_multiplier)
    else:
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

        std_mult = (
            (weights["proj"] * 1.0) +
            (weights["hist"] * hist_ratio) +
            (weights["cons"] * consistency_multiplier) +
            (weights["team"] * team_synergy_mult)
        )
        ti_final = base_pts * std_mult

        dyn_mult = (
            (dynasty_weights["proj"] * 1.0) +
            (dynasty_weights["hist"] * hist_ratio) +
            (dynasty_weights["cons"] * consistency_multiplier) +
            (dynasty_weights["age"] * age_multiplier) +
            (dynasty_weights["team"] * team_synergy_mult)
        )
        ti_dynasty_final = base_pts * dyn_mult

    # --- RB2 / WR2 / WR3 ROLE & TARGET SHARE DISCOUNTS ---
    depth_order = depth_chart_order or 1
    if pos_upper == "RB" and depth_order == 2:
        ti_final *= role_discounts.get("RB2", 0.85)
        ti_dynasty_final *= role_discounts.get("RB2", 0.85)
    elif pos_upper == "WR" and depth_order == 2:
        ti_final *= role_discounts.get("WR2", 0.90)
        ti_dynasty_final *= role_discounts.get("WR2", 0.90)
    elif pos_upper == "WR" and depth_order == 3:
        ti_final *= role_discounts.get("WR3", 0.80)
        ti_dynasty_final *= role_discounts.get("WR3", 0.80)

    # Backup Starter Threshold Penalty (/10 for depth_order >= starter limit + 1)
    is_starter = True
    if depth_order >= 2 and pos_upper in ["QB", "TE"]:
        is_starter = False
    elif depth_order >= 3 and pos_upper == "RB":
        is_starter = False
    elif depth_order >= 4 and pos_upper == "WR":
        is_starter = False

    if not is_starter:
        ti_final /= 10.0
        ti_dynasty_final /= 10.0

    return {
        "ti_score": round(ti_final, 2),
        "ti_score_dynasty": round(ti_dynasty_final, 2),
        "is_starter": is_starter,
        "is_rookie": is_rookie
    }