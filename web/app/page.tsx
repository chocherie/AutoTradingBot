import { format } from "date-fns";
import {
  getNavHistory,
  getPerformanceBundle,
  getPortfolioSummary,
} from "@/lib/data";
import { AllocationDonut, DailyReturnsBar, EquityLine } from "./components/DashboardCharts";

export const dynamic = "force-dynamic";

function fmtMoney(n: number) {
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
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

  const positions = summary.positions as {
    asset_class: string;
    notional_value: number;
  }[];
  const allocMap: Record<string, number> = {};
  for (const p of positions) {
    const k = p.asset_class || "other";
    allocMap[k] = (allocMap[k] || 0) + (Number(p.notional_value) || 0);
  }
  const allocData = Object.entries(allocMap).map(([name, value]) => ({ name, value }));

  const cumRet = perf.cumulativeReturn != null ? perf.cumulativeReturn * 100 : null;
  const todayRet = snap?.daily_return != null ? Number(snap.daily_return) * 100 : null;

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
          ["Max DD", perf.maxDrawdown != null ? `${(perf.maxDrawdown * 100).toFixed(2)}%` : "—"],
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
          <DailyReturnsBar data={history} />
        </div>
        <div className="card p-5">
          <h2 className="text-sm font-medium text-[var(--muted)] mb-4">Allocation (notional)</h2>
          <AllocationDonut data={allocData} />
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
