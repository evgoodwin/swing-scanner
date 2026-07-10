"""
swing_risk -- Phase 2 Risk Management module for Swing Scanner.
Implements the TradePlan generator per Canonical Data Architecture v1.4.
"""

from .models import (
    TradePlan, SizingConfig, ExitConfig, Rung, RungKind, RungTrigger,
    RegimeSnapshot, RegimeMode, StopSuggestion, SetupGrade, PlanStatus,
    Direction, AssetClass,
)
from .configs import (
    SIZING_CONFIGS, EXIT_CONFIGS, DEFAULT_SIZING, DEFAULT_EXIT,
)
from .stops import suggest_stops, sma, ema, wma, hma, atr
from .sizing import build_trade_plan, portfolio_current_heat_pct
from . import store

__all__ = [
    "TradePlan", "SizingConfig", "ExitConfig", "Rung", "RungKind",
    "RungTrigger", "RegimeSnapshot", "RegimeMode", "StopSuggestion",
    "SetupGrade", "PlanStatus", "Direction", "AssetClass",
    "SIZING_CONFIGS", "EXIT_CONFIGS", "DEFAULT_SIZING", "DEFAULT_EXIT",
    "suggest_stops", "sma", "ema", "wma", "hma", "atr",
    "build_trade_plan", "portfolio_current_heat_pct", "store",
]
