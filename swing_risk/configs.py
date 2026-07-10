"""
swing_risk.configs
==================
The named, versioned RulesetConfigs from Architecture v1.4 §5, encoded as data.

P2: rules are configuration, not code. To change a rule, create a NEW named
version (e.g. MTG-Core-Sizing-2) rather than editing an existing one that
trades may already reference.
"""

from .models import SizingConfig, ExitConfig, Rung, RungKind, RungTrigger


# ----------------------------------------------------------------------------
# Sizing configs (§5.2)
# ----------------------------------------------------------------------------

MTG_CORE_SIZING_1 = SizingConfig(
    config_id="MTG-Core-Sizing-1",
    risk_pct_by_mode={"GREEN": 1.0, "YELLOW": 0.5, "RED": 0.25},
    max_portfolio_heat_pct=5.0,
    max_positions=8,
    max_single_position_pct=30.0,
    min_rr_ratio=2.0,
    preferred_rr_ratio=3.0,
    allow_grade_c=False,
    red_mode_blocks_new_longs=True,
    notes="MTG baseline: risk tier by regime mode; 5% max current heat; "
          "2:1 minimum R/R (3:1 preferred); grade C = pass.",
)

# Ev's live tiering from METRICS (Bull 1.5% max ... Bear 0.25% min)
EV_LIVE_SIZING_1 = SizingConfig(
    config_id="Ev-Live-Sizing-1",
    risk_pct_by_mode={"GREEN": 1.5, "YELLOW": 0.75, "RED": 0.25},
    max_portfolio_heat_pct=5.0,
    max_positions=10,
    max_single_position_pct=30.0,
    min_rr_ratio=2.0,
    preferred_rr_ratio=3.0,
    allow_grade_c=False,
    red_mode_blocks_new_longs=True,
    notes="Per METRICS notes: 1.5% max in Bull down to 0.25% in Bear.",
)

# Legacy scorecard model preserved for comparison (SwingTrade_Journal era)
LEGACY_SCORECARD_SIZING_1 = SizingConfig(
    config_id="Legacy-Scorecard-Sizing-1",
    risk_pct_by_mode={"GREEN": 1.0, "YELLOW": 0.5, "RED": 0.0},
    max_portfolio_heat_pct=5.0,
    max_positions=8,
    max_single_position_pct=25.0,
    min_rr_ratio=2.0,
    preferred_rr_ratio=3.0,
    allow_grade_c=False,
    red_mode_blocks_new_longs=True,
    notes="Preserved legacy: scorecard multiplier model (1.0x/0.5x/0x).",
)


# ----------------------------------------------------------------------------
# Exit configs (§5.3) -- exit rungs + v1.4 management rungs
# ----------------------------------------------------------------------------

MTG_CORE_EXIT_1 = ExitConfig(
    config_id="MTG-Core-Exit-1",
    rungs=(
        Rung(kind=RungKind.MANAGE, trigger=RungTrigger.R_MULTIPLE, trigger_value=1.0,
             stop_action="BREAKEVEN", label="+1R: stop to breakeven"),
        Rung(kind=RungKind.EXIT, trigger=RungTrigger.R_MULTIPLE, trigger_value=2.0,
             exit_fraction=0.5, label="+2R: sell 1/2 (PT1)"),
        Rung(kind=RungKind.MANAGE, trigger=RungTrigger.R_MULTIPLE, trigger_value=2.0,
             stop_action="TRAIL:EMA20", label="+2R: trail remainder on 20 EMA"),
        Rung(kind=RungKind.EXIT, trigger=RungTrigger.MA_CLOSE_BELOW, trigger_param="EMA20",
             exit_fraction=1.0, label="Close below 20 EMA: exit remainder"),
    ),
    notes="MTG baseline ladder: breakeven at +1R, partial at 2R, trail 20 EMA.",
)

EV_LIVE_EXIT_1 = ExitConfig(
    config_id="Ev-Live-Exit-1",
    rungs=(
        Rung(kind=RungKind.MANAGE, trigger=RungTrigger.R_MULTIPLE, trigger_value=1.0,
             stop_action="BREAKEVEN", label="+1R: stop to breakeven"),
        Rung(kind=RungKind.EXIT, trigger=RungTrigger.MA_CLOSE_BELOW, trigger_param="EMA8",
             exit_fraction=0.5, label="Close below 8 EMA: sell 50%"),
        Rung(kind=RungKind.EXIT, trigger=RungTrigger.MA_CLOSE_BELOW, trigger_param="EMA21",
             exit_fraction=0.25, label="Close below 21 EMA: sell 1/4, start 6-day clock"),
        Rung(kind=RungKind.EXIT, trigger=RungTrigger.DAYS_ELAPSED, trigger_value=6,
             exit_fraction=1.0, label="6 days below 21 EMA: flat"),
    ),
    notes="Ev live rules per METRICS: 8 EMA 50% partial; 21 EMA break starts 6-day clock.",
)

EV_LEGACY_EXIT_1 = ExitConfig(
    config_id="Ev-Legacy-Exit-1",
    rungs=(
        Rung(kind=RungKind.EXIT, trigger=RungTrigger.MA_CLOSE_BELOW, trigger_param="SMA50",
             exit_fraction=1/3, label="50 SMA touch/close: sell 1/3"),
        Rung(kind=RungKind.EXIT, trigger=RungTrigger.MA_CLOSE_BELOW, trigger_param="HMA90",
             exit_fraction=0.5, label="Close below 90 HMA: sell 1/3 of original (1/2 remaining)"),
        Rung(kind=RungKind.EXIT, trigger=RungTrigger.MA_CLOSE_BELOW, trigger_param="SMA200",
             exit_fraction=1.0, label="Close below 200 SMA: flat"),
    ),
    notes="Ev legacy overlay ladder (experimental ruleset Ev-Exp-1).",
)


SIZING_CONFIGS = {c.config_id: c for c in
                  (MTG_CORE_SIZING_1, EV_LIVE_SIZING_1, LEGACY_SCORECARD_SIZING_1)}
EXIT_CONFIGS = {c.config_id: c for c in
                (MTG_CORE_EXIT_1, EV_LIVE_EXIT_1, EV_LEGACY_EXIT_1)}

DEFAULT_SIZING = "MTG-Core-Sizing-1"     # P1: MTG is the baseline
DEFAULT_EXIT = "MTG-Core-Exit-1"
