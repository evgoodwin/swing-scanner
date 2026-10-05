"""NYSE trading days. Uses exchange_calendars (XNYS) when installed; otherwise a hardcoded 2026
list, and refuses dates outside 2026 rather than guessing (convention: timing_call_current)."""
from datetime import date, timedelta
import logging

log = logging.getLogger("rules_service.calendar")

NYSE_HOLIDAYS_2026 = {date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
                      date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
                      date(2026, 11, 26), date(2026, 12, 25)}

try:
    import exchange_calendars as _xc
    _XNYS = _xc.get_calendar("XNYS")
    SOURCE = f"exchange_calendars {_xc.__version__}"
except Exception:  # pragma: no cover - exercised only where the library is missing
    _XNYS = None
    SOURCE = "hardcoded 2026"
    log.warning("exchange_calendars not installed; using the hardcoded 2026 NYSE holiday list")


def previous_trading_day(d: date) -> date:
    """The last NYSE session strictly before d. Early closes count as trading days."""
    if _XNYS is not None:
        import pandas as pd
        return _XNYS.date_to_session(pd.Timestamp(d - timedelta(days=1)), direction="previous").date()
    if not (date(2026, 1, 2) <= d <= date(2026, 12, 31)):
        raise ValueError(f"no trading calendar for {d}: install exchange_calendars")
    d -= timedelta(days=1)
    while d.weekday() >= 5 or d in NYSE_HOLIDAYS_2026:
        d -= timedelta(days=1)
    return d
