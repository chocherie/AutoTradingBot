# Rule: Artifacts to Disk

All analysis outputs, trade decisions, performance reports, and Claude responses must be persisted to the project tree (SQLite database or log files), not kept only in conversation context.

- Trade rationale → `trades` table
- Claude's full response → `daily_analysis` table
- Performance metrics → `portfolio_snapshots` table
- Application logs → `storage/logs/`
