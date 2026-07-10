"""
swing_risk.models
=================
Core data objects for Phase 2 (Risk Management / TradePlan generator),
implementing the Canonical Data Architecture v1.4:

  - SizingConfig      (RulesetConfig category 2, §5)
  - ExitConfig        (RulesetConfig category 3, §5) with exit + management rungs
  - RegimeSnapshot    (minimal RegimeState view consumed by the sizer, §4.3)
  - StopSuggestion    (§4.6 stop_suggestions)
  - TradePlan         (§4.6)

Design principles honored:
  P2 - rules are configuration, not code (configs are frozen dataclasses,
       identified by name+version; edits create new versions)
  P4 - multi-asset ready (asset_class carried; point_value defaults to 1)
  P6 - user_id stamped on private entities (single-user = one user)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Optional
import json
import uuid


# ----------------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------------

class RegimeMode(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"          # Phase 7 mirror-ready


class SetupGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"                  # C = pass; sizer refuses to size a C by default


class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    ARMED = "ARMED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    ETF = "ETF"
    CRYPTO = "CRYPTO"
    OPTION = "OPTION"        # placeholder (§4.1)
    FUTURE = "FUTURE"        # placeholder
    FOREX = "FOREX"          # placeholder


class RungKind(str, Enum):
    EXIT = "EXIT"            # sell a fraction at a condition
    MANAGE = "MANAGE"        # adjust stop at a condition (v1.4 management rung)


class RungTrigger(str, Enum):
    R_MULTIPLE = "R_MULTIPLE"        # open_r >= value
    MA_CLOSE_BELOW = "MA_CLOSE_BELOW"  # close below named MA (param: ma name)
    MA_CLOSE_ABOVE = "MA_CLOSE_ABOVE"
    DAYS_ELAPSED = "DAYS_ELAPSED"
    PRICE_LEVEL = "PRICE_LEVEL"


# ----------------------------------------------------------------------------
# Configs (immutable once referenced -- P2)
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class SizingConfig:
    """RulesetConfig category 2: how risk dollars are determined."""
    config_id: str                        # e.g. "MTG-Core-Sizing-1"
    # account risk %, keyed by regime mode of the instrument's benchmark
    risk_pct_by_mode: dict            # {"GREEN": 1.0, "YELLOW": 0.5, "RED": 0.25}
    max_portfolio_heat_pct: float = 5.0   # current-heat ceiling
    max_positions: int = 8
    max_single_position_pct: float = 30.0 # of equity, allocation cap
    min_rr_ratio: float = 2.0             # plan rejected below this
    preferred_rr_ratio: float = 3.0
    allow_grade_c: bool = False
    red_mode_blocks_new_longs: bool = True
    notes: str = ""


@dataclass(frozen=True)
class Rung:
    """One rung of an exit ladder -- either an exit or a stop-management action."""
    kind: RungKind
    trigger: RungTrigger
    trigger_value: float | None = None    # R multiple, days, or price
    trigger_param: str | None = None      # MA name, e.g. "EMA8", "SMA50", "HMA90"
    exit_fraction: float | None = None    # for EXIT rungs: fraction of remaining
    stop_action: str | None = None        # for MANAGE rungs: "BREAKEVEN",
                                          # "TRAIL:EMA8", "TRAIL:EMA20", "RAISE_TO:<level>"
    label: str = ""


@dataclass(frozen=True)
class ExitConfig:
    """RulesetConfig category 3: complete trade-management script as data."""
    config_id: str
    rungs: tuple                          # tuple[Rung, ...] ordered
    notes: str = ""


# ----------------------------------------------------------------------------
# Regime snapshot (what the sizer needs from RegimeState)
# ----------------------------------------------------------------------------

@dataclass
class RegimeSnapshot:
    as_of: date
    benchmark_id: str                     # "QQQ", "SPY", "IWM", "DIA", "BTC"
    mode: RegimeMode
    composite_mode: RegimeMode            # headline RYG verdict
    ruleset_id: str = "MTG-Core-Regime-1"
    detail: str = ""                      # human-readable basis


# ----------------------------------------------------------------------------
# Stop suggestion
# ----------------------------------------------------------------------------

@dataclass
class StopSuggestion:
    basis: str                            # "SWING_LOW", "SMA50", "HMA90", "ATR"
    level: float
    distance_pct: float                   # from entry
    note: str = ""
    is_overlay: bool = False              # True for Ev-Exp fields (HMA90 etc.)


# ----------------------------------------------------------------------------
# TradePlan (§4.6)
# ----------------------------------------------------------------------------

@dataclass
class EntryLeg:
    fraction: float                       # of total planned shares
    trigger: str                          # description or level
    price: float


@dataclass
class TradePlan:
    # identity / links
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str = "ev"
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    symbol: str = ""
    asset_class: str = AssetClass.EQUITY.value
    benchmark_id: str = "QQQ"
    book: str = "SWING"
    account_id: str = "default"
    watchlist_id: Optional[str] = None

    # governing configs (P2)
    sizing_config_id: str = ""
    exit_config_id: str = ""
    regime_ruleset_id: str = ""

    # regime snapshot at planning time
    regime_mode: str = ""
    regime_composite: str = ""
    regime_detail: str = ""

    # the setup
    setup_type: str = ""
    setup_grade: str = SetupGrade.B.value
    direction: str = Direction.LONG.value

    # prices & risk
    entry_price: float = 0.0
    stop_price: float = 0.0
    stop_basis: str = ""
    stop_suggestions: list = field(default_factory=list)   # [StopSuggestion as dict]
    target_price: Optional[float] = None
    rr_ratio: Optional[float] = None

    risk_pct: float = 0.0                 # effective account risk % (post-regime tier)
    risk_dollars: float = 0.0
    shares_planned: int = 0
    position_dollars: float = 0.0
    scale_plan: list = field(default_factory=list)          # [EntryLeg as dict]

    # portfolio context
    equity: float = 0.0
    heat_before_pct: float = 0.0          # current heat before this plan
    heat_after_pct: float = 0.0

    # validation
    checklist: dict = field(default_factory=dict)           # name -> (bool, msg)
    is_valid: bool = False
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    status: str = PlanStatus.DRAFT.value
    thesis: str = ""

    # ------------------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @staticmethod
    def from_json(s: str) -> "TradePlan":
        d = json.loads(s)
        return TradePlan(**d)
