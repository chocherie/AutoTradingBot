import { getPerformanceBundle } from "@/lib/data";
import { DrawdownArea, RollingSharpeLine } from "../components/PerfCharts";

export const dynamic = "force-dynamic";

export default function PerformancePage() {
  const perf = getPerformanceBundle();
  const snaps = perf.snapshots;

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold">Performance</h1>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          ["Sharpe", perf.sharpeRatio != null ? perf.sharpeRatio.toFixed(2) : "—"],
          ["Max drawdown", perf.maxDrawdown != null ? `${(perf.maxDrawdown * 100).toFixed(2)}%` : "—"],
          ["Win rate", perf.winRate != null ? `${(perf.winRate * 100).toFixed(1)}%` : "—"],
          ["Closed trades", String(perf.tradeCount)],
        ].map(([k, v]) => (
          <div key={k} className="card p-4">
            <div className="text-xs text-[var(--muted)] uppercase">{k}</div>
            <div className="text-xl font-mono text-tape-amber mt-1">{v}</div>
          </div>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-5">
          <h2 className="text-sm text-[var(--muted)] mb-4">Rolling Sharpe (30d)</h2>
          <RollingSharpeLine data={snaps} />
        </div>
        <div className="card p-5">
          <h2 className="text-sm text-[var(--muted)] mb-4">Drawdown from peak</h2>
          <DrawdownArea data={snaps} />
        </div>
      </div>

      <p className="text-xs text-[var(--muted)]">
        Sortino / Calmar / heatmap can extend the same snapshot series; profit factor requires tagging
        wins on closed trades.
      </p>
    </div>
  );
}
