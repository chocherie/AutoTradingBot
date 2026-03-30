import { format } from "date-fns";
import {
  getNavHistory,
  getPerformanceBundle,
  getPortfolioSummary,
} from "@/lib/data";
import { getInstrumentDisplayName } from "@/lib/instruments";
import { AllocationLongShortBars, DailyReturnsBar, EquityLine } from "./components/DashboardCharts";

export const dynamic = "force-dynamic";

function fmtMoney(n: number) {
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

/**
 * Do not trust `portfolio_snapshots.daily_return` for the hero tile — older runs used a bad prior-NAV
 * fallback (cash vs full NAV). Prefer NAV vs previous snapshot; single row → cumulative vs initial.
 */
function todayReturnDisplayPct(
  historyAsc: { nav: number; daily_return: number | null }[],
  snap: Record<string, unknown> | undefined,
): number | null {
  const n = historyAsc.length;
  if (n >= 2) {
    const prevNav = Number(historyAsc[n - 2]!.nav);
    const lastNav = Number(historyAsc[n - 1]!.nav);
    if (prevNav > 0 && Number.isFinite(lastNav)) {
      return (lastNav / prevNav - 1) * 100;
    }
  }
  if (snap?.cumulative_return != null) {
    const c = Number(snap.cumulative_return);
    if (Number.isFinite(c)) return c * 100;
  }
  if (snap?.daily_return != null) {
    const d = Number(snap.daily_return);
    if (Number.isFinite(d)) return d * 100;
  }
  return null;
}

/** Daily returns from consecutive NAVs (ignores possibly wrong `daily_return` in SQLite). */
function historyWithImpliedDailyReturns<T extends { nav: number; daily_return: number | null }>(
  historyAsc: T[],
): T[] {
  return historyAsc.map((row, i) => {
    if (i === 0) {
      return { ...row, daily_return: null };
    }
    const prevNav = Number(historyAsc[i - 1]!.nav);
    const nav = Number(row.nav);
    const implied =
      prevNav > 0 && Number.isFinite(nav) ? nav / prevNav - 1 : null;
    return { ...row, daily_return: implied };
  });
}

export default async function DashboardPage() {
  const summary = await getPortfolioSummary();
  const history = (await getNavHistory(400)) as {
    date: string;
    nav: number;
    daily_return: number | null;
    total_margin_used: number | null;
  }[];
  const perf = await getPerformanceBundle();
  const snap = summary.snapshot as Record<string, unknown> | undefined;
  const nav = (snap?.nav as number) ?? (summary.meta?.cash as number) ?? 0;
  const cash = (snap?.cash as number) ?? summary.meta?.cash ?? 0;
  const regime = summary.regime?.market_regime as string | undefined;
  const lastDate = snap?.date as string | undefined;

  const positions = summary.positions as Record<string, unknown>[];
  const allocRows = positions.map((p) => {
    const ticker = String(p.ticker ?? "");
    const direction = String(p.direction ?? "");
    const notional = Number(p.notional_value) || 0;
    const entry =
      p.entry_notional_usd != null && Number.isFinite(Number(p.entry_notional_usd))
        ? Number(p.entry_notional_usd)
        : null;
    const upnl =
      p.unrealized_pnl != null && Number.isFinite(Number(p.unrealized_pnl))
        ? Number(p.unrealized_pnl)
        : null;
    const returnPct =
      entry != null && entry > 0 && upnl != null ? (upnl / entry) * 100 : null;
    return {
      ticker,
      name: getInstrumentDisplayName(ticker),
      direction,
      notional,
      returnPct,
    };
  });

  const cumRet = perf.cumulativeReturn != null ? perf.cumulativeReturn * 100 : null;
  const todayRet = todayReturnDisplayPct(history, snap);
  const historyForBars = historyWithImpliedDailyReturns(history);

  return (
    <div className="space-y-8">
      {summary.dbUnavailable && (
        <div className="rounded-lg border border-tape-amber/40 bg-tape-amber/10 px-4 py-3 text-sm text-tape-amber">
          <strong>No database available here yet.</strong> On Vercel, enable{" "}
          <strong>Vercel Blob</strong>, set <code className="font-mono text-xs">BLOB_READ_WRITE_TOKEN</code>{" "}
          and <code className="font-mono text-xs">DB_UPLOAD_SECRET</code>, and run the bot with{" "}
          <code className="font-mono text-xs">DASHBOARD_DB_SYNC_URL</code> pointing at{" "}
          <code className="font-mono text-xs">/api/admin/sync-db</code>. Or use{" "}
          <code className="font-mono text-xs">npm run dev</code> locally next to{" "}
          <code className="font-mono text-xs">storage/trading_bot.db</code>.
        </div>
      )}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-[var(--muted)] text-sm mt-1">
          {lastDate ? `Last snapshot ${lastDate}` : "No snapshots yet — run the daily bot."}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          ["NAV", fmtMoney(nav)],
          ["Cash", fmtMoney(cash)],
          ["Total return", cumRet != null ? `${cumRet >= 0 ? "+" : ""}${cumRet.toFixed(2)}%` : "—"],
          ["Today", todayRet != null ? `${todayRet >= 0 ? "+" : ""}${todayRet.toFixed(3)}%` : "—"],
          ["Sharpe", perf.sharpeRatio != null ? perf.sharpeRatio.toFixed(2) : "—"],
          [
            "Max DD",
            perf.maxDrawdown != null
              ? `${(-Math.abs(perf.maxDrawdown) * 100).toFixed(2)}%`
              : "—",
          ],
        ].map(([k, v]) => (
          <div key={k} className="card p-4">
            <div className="text-xs text-[var(--muted)] uppercase tracking-wide">{k}</div>
            <div className="text-lg font-mono mt-1 text-tape-amber">{v}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <span className="text-sm text-[var(--muted)]">Regime</span>
        <span className="px-3 py-1 rounded-full text-xs font-medium bg-[#243044] text-tape-amber border border-tape-amber/30">
          {regime ?? "—"}
        </span>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-5">
          <h2 className="text-sm font-medium text-[var(--muted)] mb-4">Equity curve</h2>
          <EquityLine data={history} />
        </div>
        <div className="card p-5">
          <h2 className="text-sm font-medium text-[var(--muted)] mb-4">Daily returns</h2>
          <DailyReturnsBar data={historyForBars} />
        </div>
        <div className="card p-5">
          <h2 className="text-sm font-medium text-[var(--muted)] mb-4">
            Exposure by position (signed notional)
          </h2>
          <AllocationLongShortBars data={allocRows} />
        </div>
        <div className="card p-5 flex flex-col justify-center">
          <h2 className="text-sm font-medium text-[var(--muted)] mb-2">Latest macro</h2>
          <p className="text-sm text-[var(--text)] leading-relaxed line-clamp-6">
            {(summary.regime?.macro_summary as string) || "Run the daily cycle with Claude to populate analysis."}
          </p>
        </div>
      </div>

      <p className="text-xs text-[var(--muted)] font-mono">
        Updated {format(new Date(), "yyyy-MM-dd HH:mm")} (server)
      </p>
    </div>
  );
}
