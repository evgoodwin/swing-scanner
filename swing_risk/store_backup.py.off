"""
swing_risk.store
================
SQLite persistence for TradePlans (§4.6) and a lightweight open-positions
table feeding the heat calculation until Phase 8's TradeRecords take over.

SQLite is deliberate: file-based, zero-config, ships with Python, and is the
stepping stone to the production database called out in Tier 3 (§8).

NOTE for Streamlit Cloud: the container filesystem is EPHEMERAL -- the .db
file survives reruns but not redeploys/restarts. Fine for local use (the
current Phase 2 target). For hosted persistence, point DB_PATH at a mounted
volume or swap this module for a hosted DB; the interface stays the same.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import TradePlan

DB_PATH = Path("swing_scanner.db")   # lives next to the app by default


def _conn(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("""
        CREATE TABLE IF NOT EXISTS trade_plans (
            plan_id   TEXT PRIMARY KEY,
            user_id   TEXT NOT NULL,
            created   TEXT NOT NULL,
            symbol    TEXT NOT NULL,
            status    TEXT NOT NULL,
            is_valid  INTEGER NOT NULL,
            json      TEXT NOT NULL
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS open_positions (
            user_id      TEXT NOT NULL,
            account_id   TEXT NOT NULL,
            symbol       TEXT NOT NULL,
            direction    TEXT NOT NULL DEFAULT 'LONG',
            shares       REAL NOT NULL,
            avg_entry    REAL NOT NULL,
            current_stop REAL NOT NULL,
            book         TEXT NOT NULL DEFAULT 'SWING',
            PRIMARY KEY (user_id, account_id, symbol)
        )""")
    # v3 migration: fill tracking (initial risk per share, source plan)
    for _col, _typ in (("initial_risk_ps", "REAL DEFAULT 0"),
                       ("plan_id", "TEXT DEFAULT ''")):
        try:
            con.execute(f"ALTER TABLE open_positions ADD COLUMN {_col} {_typ}")
        except sqlite3.OperationalError:
            pass
    con.commit()
    return con


# ---------------------------------------------------------------- trade plans
def save_plan(plan: TradePlan, db_path: Path | str = DB_PATH) -> None:
    con = _conn(db_path)
    con.execute(
        "INSERT OR REPLACE INTO trade_plans VALUES (?,?,?,?,?,?,?)",
        (plan.plan_id, plan.user_id, plan.created, plan.symbol,
         plan.status, int(plan.is_valid), plan.to_json()),
    )
    con.commit()
    con.close()


def load_plans(user_id: str = "ev", status: str | None = None,
               db_path: Path | str = DB_PATH) -> list[TradePlan]:
    con = _conn(db_path)
    q = "SELECT json FROM trade_plans WHERE user_id=?"
    args: list = [user_id]
    if status:
        q += " AND status=?"
        args.append(status)
    q += " ORDER BY created DESC"
    rows = con.execute(q, args).fetchall()
    con.close()
    return [TradePlan.from_json(r[0]) for r in rows]


def delete_plan(plan_id: str, db_path: Path | str = DB_PATH) -> None:
    con = _conn(db_path)
    con.execute("DELETE FROM trade_plans WHERE plan_id=?", (plan_id,))
    con.commit()
    con.close()


def update_plan_status(plan_id: str, status: str,
                       db_path: Path | str = DB_PATH) -> None:
    con = _conn(db_path)
    row = con.execute("SELECT json FROM trade_plans WHERE plan_id=?",
                      (plan_id,)).fetchone()
    if row:
        d = json.loads(row[0])
        d["status"] = status
        con.execute("UPDATE trade_plans SET status=?, json=? WHERE plan_id=?",
                    (status, json.dumps(d), plan_id))
        con.commit()
    con.close()


# ------------------------------------------------------------ open positions
def get_open_positions(user_id: str = "ev", account_id: str = "default",
                       book: str | None = "SWING",
                       db_path: Path | str = DB_PATH) -> list[dict]:
    con = _conn(db_path)
    q = ("SELECT symbol, direction, shares, avg_entry, current_stop, book, "
         "initial_risk_ps, plan_id FROM open_positions "
         "WHERE user_id=? AND account_id=?")
    args = [user_id, account_id]
    if book:
        q += " AND book=?"
        args.append(book)
    rows = con.execute(q, args).fetchall()
    con.close()
    return [{"symbol": r[0], "direction": r[1], "shares": r[2],
             "avg_entry": r[3], "current_stop": r[4], "book": r[5],
             "initial_risk_ps": r[6], "plan_id": r[7]}
            for r in rows]


def upsert_position(user_id: str, account_id: str, symbol: str, shares: float,
                    avg_entry: float, current_stop: float,
                    direction: str = "LONG", book: str = "SWING",
                    initial_risk_ps: float = 0.0, plan_id: str = "",
                    db_path: Path | str = DB_PATH) -> None:
    con = _conn(db_path)
    con.execute(
        """INSERT OR REPLACE INTO open_positions
           (user_id, account_id, symbol, direction, shares,
            avg_entry, current_stop, book, initial_risk_ps, plan_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (user_id, account_id, symbol.upper(), direction, shares,
         avg_entry, current_stop, book, initial_risk_ps, plan_id),
    )
    con.commit()
    con.close()


def delete_position(user_id: str, account_id: str, symbol: str,
                    db_path: Path | str = DB_PATH) -> None:
    con = _conn(db_path)
    con.execute(
        "DELETE FROM open_positions WHERE user_id=? AND account_id=? AND symbol=?",
        (user_id, account_id, symbol.upper()),
    )
    con.commit()
    con.close()
