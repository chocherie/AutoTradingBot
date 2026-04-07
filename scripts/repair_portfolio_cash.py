#!/usr/bin/env python3
"""Replay the trades journal to recompute portfolio_meta.cash (fixes stale cash after older bugs).

Duplicate CLOSE rows for the same position_id (legacy bad runs) are applied only once.

Usage:
  PYTHONPATH=. python scripts/repair_portfolio_cash.py           # print dry-run
  PYTHONPATH=. python scripts/repair_portfolio_cash.py --apply   # UPDATE portfolio_meta
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# repo root = parent of scripts/
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.portfolio.instrument_registry import build_registry, resolve_fx_to_usd
from src.utils.config import load_settings
from src.utils.paths import project_root


def _db_file() -> Path:
    rel = load_settings().get("database", {}).get("path", "storage/trading_bot.db")
    return project_root() / Path(rel)


def _cash_close(p: dict, exit_px: float, comm: float) -> float:
    reg = build_registry()
    meta = reg[p["ticker"]]
    it = p["instrument_type"]
    direction = p["direction"]
    qty = float(p["quantity"])
    entry = float(p["entry_price"])
    fx = resolve_fx_to_usd(meta, {p["ticker"]: exit_px})
    realized = 0.0
    if it == "future":
        if direction == "LONG":
            realized = (exit_px - entry) * qty * meta.multiplier
        else:
            realized = (entry - exit_px) * qty * meta.multiplier
    elif it == "option":
        om = meta.option_contract_multiplier or 100.0
        if direction == "LONG":
            realized = (exit_px - entry) * qty * om
        else:
            realized = (entry - exit_px) * qty * om
    else:
        if direction == "LONG":
            realized = (exit_px - entry) * qty * fx
        else:
            realized = (entry - exit_px) * qty * fx
    realized -= comm
    if it == "future":
        return realized
    if it == "option":
        om = meta.option_contract_multiplier or 100.0
        if direction == "LONG":
            return exit_px * qty * om - comm
        return -(exit_px * qty * om + comm)
    if direction == "LONG":
        return exit_px * qty * fx - comm
    return -(exit_px * qty * fx + comm)


def _cash_open(p: dict, qty: float, price: float, comm: float) -> float:
    reg = build_registry()
    meta = reg[p["ticker"]]
    fx = resolve_fx_to_usd(meta, {p["ticker"]: price})
    opening = -comm
    it = p["instrument_type"]
    direction = p["direction"]
    if it == "future":
        pass
    elif it == "option":
        om = meta.option_contract_multiplier or 100.0
        if direction == "LONG":
            opening -= price * qty * om
        else:
            opening += price * qty * om
    else:
        if direction == "LONG":
            opening -= price * qty * fx
        else:
            opening += price * qty * fx
    return opening


def replay_cash(path: Path) -> tuple[float, float, int]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    initial = float(load_settings().get("portfolio", {}).get("initial_capital", 1_000_000.0))
    cash = initial
    pos_rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM positions")}
    trades = conn.execute("SELECT * FROM trades ORDER BY id").fetchall()
    first_open: dict[int, int] = {}
    for t in trades:
        if t["action"] in ("BUY", "SHORT"):
            pid = int(t["position_id"])
            if pid not in first_open:
                first_open[pid] = int(t["id"])
    already_closed: set[int] = set()
    dup_skipped = 0
    for t in trades:
        pid = int(t["position_id"])
        if t["action"] == "CLOSE":
            if pid in already_closed:
                dup_skipped += 1
                continue
            already_closed.add(pid)
            p = pos_rows[pid]
            cash += _cash_close(p, float(t["price"]), float(t["commission"]))
        elif t["action"] in ("BUY", "SHORT"):
            p = pos_rows[pid]
            cash += _cash_open(p, float(t["quantity"]), float(t["price"]), float(t["commission"]))
    meta = float(conn.execute("SELECT cash FROM portfolio_meta WHERE id=1").fetchone()[0])
    conn.close()
    return cash, meta, dup_skipped


def main() -> None:
    ap = argparse.ArgumentParser(description="Recompute cash from trades ledger")
    ap.add_argument("--apply", action="store_true", help="UPDATE portfolio_meta.cash (and bump peak_nav if needed)")
    args = ap.parse_args()
    path = _db_file()
    if not path.exists():
        print(f"No database at {path}", file=sys.stderr)
        sys.exit(1)
    replayed, meta, dups = replay_cash(path)
    print(f"Database: {path}")
    print(f"Replayed cash: {replayed:,.2f}")
    print(f"Stored cash:   {meta:,.2f}")
    print(f"Delta:         {replayed - meta:,.2f}")
    print(f"Duplicate CLOSE rows skipped in replay: {dups}")
    if not args.apply:
        print("\nDry-run only. Pass --apply to write portfolio_meta.cash.")
        return
    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE portfolio_meta SET cash = ?, updated_at = datetime('now') WHERE id = 1",
        (replayed,),
    )
    conn.commit()
    conn.close()
    print("\nApplied portfolio_meta.cash (peak_nav unchanged — refresh via next full run / snapshot).")
    print("Run: PYTHONPATH=. python -m src.main --skip-claude --date YYYY-MM-DD  to refresh portfolio_snapshots NAV.")


if __name__ == "__main__":
    main()
