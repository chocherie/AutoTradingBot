"""Upload local SQLite to Vercel after each daily run so the hosted dashboard stays in sync."""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from src.utils.config import load_settings
from src.utils.paths import project_root

logger = logging.getLogger(__name__)


def _sqlite_snapshot_bytes(db_path: Path) -> bytes | None:
    """
    Snapshot the DB via SQLite backup API so uploads include WAL-committed state.
    Copying only the main .db file can upload stale data while journal_mode=WAL.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            src = sqlite3.connect(str(db_path))
            try:
                dst = sqlite3.connect(str(tmp_path))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            return tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
    except (OSError, sqlite3.Error) as e:
        logger.warning("dashboard_sync_sqlite_backup_failed", extra={"error": str(e)})
        return None


def maybe_sync_dashboard_db() -> None:
    """
    If DASHBOARD_DB_SYNC_URL and DASHBOARD_DB_SYNC_SECRET are set, POST a copy of
    trading_bot.db to the Next.js /api/admin/sync-db route (stores in Vercel Blob).
    """
    url = (os.environ.get("DASHBOARD_DB_SYNC_URL") or "").strip()
    secret = (os.environ.get("DASHBOARD_DB_SYNC_SECRET") or "").strip()
    if not url or not secret:
        return

    settings = load_settings()
    rel = settings.get("database", {}).get("path", "storage/trading_bot.db")
    db_path = project_root() / Path(rel)
    if not db_path.is_file():
        logger.warning(
            "dashboard_sync_skipped_missing_file",
            extra={"path": str(db_path)},
        )
        return

    data = _sqlite_snapshot_bytes(db_path)
    if data is None:
        return

    req = urllib.request.Request(  # noqa: S310 — URL is operator-configured
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status != 200:
                logger.warning(
                    "dashboard_sync_non_200",
                    extra={"status": resp.status, "body": resp.read(500).decode("utf-8", "replace")},
                )
            else:
                logger.info(
                    "dashboard_sync_ok",
                    extra={"bytes": len(data)},
                )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if e.fp else ""
        logger.warning(
            "dashboard_sync_http_error",
            extra={"status": e.code, "error": body[:500]},
        )
    except urllib.error.URLError as e:
        logger.warning("dashboard_sync_url_error", extra={"error": str(e.reason)})
