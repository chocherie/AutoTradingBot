#!/usr/bin/env python3
"""Merge duplicate OPEN position rows (same ticker/direction/instrument) into one VWAP leg.

Run from repo root after backups if needed:
  PYTHONPATH=. python3 scripts/consolidate_duplicate_open_positions.py

Use when the book shows multiple OPEN rows for the same future/ETF leg (e.g. two BZ=F
LONG rows from before merge-on-add was implemented). Re-points trades to the kept id.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.utils.config import load_settings
from src.utils.paths import project_root


def _row_key(row: sqlite3.Row) -> Tuple[Any, ...]:
    return (
        row["ticker"],
        row["direction"],
        row["instrument_type"],
        row["strike"],
        row["expiry"],
        row["option_type"],
    )


def main() -> None:
    settings = load_settings()
    rel = settings.get("database", {}).get("path", "storage/trading_bot.db")
    db_path = project_root() / Path(rel)
    if not db_path.is_file():
        raise SystemExit(f"No database at {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows: List[sqlite3.Row] = list(
        conn.execute("SELECT * FROM positions WHERE status = 'OPEN' ORDER BY id")
    )
    groups: Dict[Tuple[Any, ...], List[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        groups[_row_key(r)].append(r)

    merged = 0
    for _key, grp in groups.items():
        if len(grp) < 2:
            continue
        grp.sort(key=lambda r: int(r["id"]))
        keep = grp[0]
        keep_id = int(keep["id"])
        total_q = sum(float(r["quantity"]) for r in grp)
        vwap = sum(float(r["quantity"]) * float(r["entry_price"]) for r in grp) / total_q
        with conn:
            conn.execute(
                """UPDATE positions SET quantity=?, entry_price=?
                   WHERE id=? AND status='OPEN'""",
                (total_q, vwap, keep_id),
            )
            for r in grp[1:]:
                dup_id = int(r["id"])
                conn.execute(
                    "UPDATE trades SET position_id=? WHERE position_id=?",
                    (keep_id, dup_id),
                )
                conn.execute("DELETE FROM positions WHERE id=?", (dup_id,))
                merged += 1
        print(f"Merged position ids into {keep_id}: {[int(r['id']) for r in grp]}")

    conn.close()
    if merged == 0:
        print("No duplicate OPEN groups found.")
    else:
        print(f"Removed {merged} duplicate OPEN row(s). Run a price update cycle if needed.")


if __name__ == "__main__":
    main()
