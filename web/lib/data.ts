import { getDb } from "./db";

export function getPortfolioSummary() {
  const db = getDb();
  const snapshot = db
    .prepare(
      "SELECT * FROM portfolio_snapshots ORDER BY date DESC LIMIT 1",
    )
    .get() as Record<string, unknown> | undefined;
  const positions = db
    .prepare(
      "SELECT * FROM positions WHERE status = 'OPEN' ORDER BY ticker ASC",
    )
    .all();
  const regime = db
    .prepare(
      "SELECT date, market_regime, macro_summary FROM daily_analysis ORDER BY date DESC LIMIT 1",
    )
    .get() as Record<string, unknown> | undefined;
  const meta = db
    .prepare("SELECT cash, peak_nav FROM portfolio_meta WHERE id = 1")
    .get() as { cash: number; peak_nav: number } | undefined;
  return { snapshot, positions, regime, meta };
}

export function getNavHistory(days: number) {
  const db = getDb();
  const rows = db
    .prepare(
      `SELECT date, nav, daily_return, cash, total_margin_used, sharpe_ratio, max_drawdown
       FROM portfolio_snapshots ORDER BY date DESC LIMIT ?`,
    )
    .all(days);
  return rows.reverse();
}

export function getPositions(status: string) {
  const db = getDb();
  return db
    .prepare(
      `SELECT * FROM positions WHERE status = ? ORDER BY ticker ASC`,
    )
    .all(status);
}

export function getTrades(page: number, limit: number, ticker?: string) {
  const db = getDb();
  const offset = (page - 1) * limit;
  const like = ticker ? `%${ticker}%` : null;
  const total = like
    ? (
        db
          .prepare("SELECT COUNT(*) as c FROM trades WHERE ticker LIKE ?")
          .get(like) as { c: number }
      ).c
    : (db.prepare("SELECT COUNT(*) as c FROM trades").get() as { c: number }).c;
  const rows = like
    ? db
        .prepare(
          "SELECT * FROM trades WHERE ticker LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",
        )
        .all(like, limit, offset)
    : db
        .prepare("SELECT * FROM trades ORDER BY id DESC LIMIT ? OFFSET ?")
        .all(limit, offset);
  return { rows, total, page, limit };
}

export function getAnalysis(page: number, limit: number) {
  const db = getDb();
  const offset = (page - 1) * limit;
  const total = (db.prepare("SELECT COUNT(*) as c FROM daily_analysis").get() as { c: number })
    .c;
  const rows = db
    .prepare(
      `SELECT * FROM daily_analysis ORDER BY date DESC LIMIT ? OFFSET ?`,
    )
    .all(limit, offset);
  return { rows, total, page, limit };
}

export function getPerformanceBundle() {
  const db = getDb();
  const snaps = db
    .prepare(
      `SELECT date, nav, daily_return, sharpe_ratio, max_drawdown FROM portfolio_snapshots ORDER BY date ASC`,
    )
    .all() as { date: string; nav: number; daily_return: number | null; sharpe_ratio: number | null; max_drawdown: number | null }[];
  const closed = db
    .prepare(
      `SELECT realized_pnl FROM positions WHERE status = 'CLOSED' AND realized_pnl IS NOT NULL`,
    )
    .all() as { realized_pnl: number }[];
  const pnls = closed.map((r) => r.realized_pnl);
  const wins = pnls.filter((p) => p > 0).length;
  const losses = pnls.filter((p) => p < 0).length;
  const winRate = wins + losses > 0 ? wins / (wins + losses) : null;

  const navs = snaps.map((s) => s.nav);
  let sharpe: number | null = null;
  let maxDd: number | null = null;
  if (navs.length >= 2) {
    const rets: number[] = [];
    for (let i = 1; i < navs.length; i++) {
      rets.push((navs[i] - navs[i - 1]) / navs[i - 1]);
    }
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const v =
      rets.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(rets.length - 1, 1);
    const sd = Math.sqrt(v);
    sharpe = sd > 1e-8 ? (mean / sd) * Math.sqrt(252) : null;

    let peak = navs[0];
    let m = 0;
    for (const n of navs) {
      peak = Math.max(peak, n);
      m = Math.max(m, (peak - n) / peak);
    }
    maxDd = m;
  }

  const lastSharpe = snaps.length ? snaps[snaps.length - 1].sharpe_ratio : null;
  const lastMdd = snaps.length ? snaps[snaps.length - 1].max_drawdown : null;

  return {
    snapshots: snaps,
    winRate,
    tradeCount: pnls.length,
    sharpeRatio: lastSharpe ?? sharpe,
    maxDrawdown: lastMdd ?? maxDd,
    cumulativeReturn:
      navs.length >= 1 && navs[0] > 0 ? navs[navs.length - 1] / navs[0] - 1 : null,
  };
}
