import { getDb } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function PositionsPage({
  searchParams,
}: {
  searchParams: Promise<{ closed?: string }>;
}) {
  const sp = await searchParams;
  const showClosed = sp.closed === "1";
  const db = getDb();
  const open = db
    .prepare("SELECT * FROM positions WHERE status = 'OPEN' ORDER BY ticker")
    .all() as Record<string, unknown>[];
  const closed = showClosed
    ? (db
        .prepare(
          `SELECT * FROM positions WHERE status = 'CLOSED' AND exit_date >= date('now', '-30 day') ORDER BY exit_date DESC`,
        )
        .all() as Record<string, unknown>[])
    : [];
  const snap = db
    .prepare("SELECT nav, total_margin_used FROM portfolio_snapshots ORDER BY date DESC LIMIT 1")
    .get() as { nav: number; total_margin_used: number } | undefined;
  const nav = snap?.nav ?? 1;
  const mu = snap?.nav ? ((snap.total_margin_used || 0) / snap.nav) * 100 : 0;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap justify-between gap-4 items-start">
        <div>
          <h1 className="text-2xl font-semibold">Positions</h1>
          <p className="text-[var(--muted)] text-sm mt-1">Open legs and optional recent exits.</p>
        </div>
        <a
          href={showClosed ? "/positions" : "/positions?closed=1"}
          className="text-sm text-tape-amber hover:underline"
        >
          {showClosed ? "Hide closed (30d)" : "Show closed (30d)"}
        </a>
      </div>

      <div className="card p-5">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm text-[var(--muted)]">Margin utilization vs 60% limit</span>
          <span className="font-mono text-tape-amber">{mu.toFixed(1)}%</span>
        </div>
        <div className="h-2 rounded-full bg-[#243044] overflow-hidden">
          <div
            className="h-full bg-tape-amber transition-all"
            style={{ width: `${Math.min(100, (mu / 60) * 100)}%` }}
          />
        </div>
      </div>

      <div className="card p-5 overflow-x-auto">
        <h2 className="text-sm font-medium text-[var(--muted)] mb-4">Open</h2>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-[var(--muted)] text-xs uppercase">
              <th className="pb-2">Ticker</th>
              <th className="pb-2">Class</th>
              <th className="pb-2">Dir</th>
              <th className="pb-2 text-right">Qty</th>
              <th className="pb-2 text-right">Entry</th>
              <th className="pb-2 text-right">Last</th>
              <th className="pb-2 text-right">U-P&amp;L</th>
              <th className="pb-2 text-right">% NAV</th>
              <th className="pb-2 text-right">Stop</th>
              <th className="pb-2 text-right">TP</th>
            </tr>
          </thead>
          <tbody>
            {open.map((p) => {
              const pctNav = nav > 0 ? ((Number(p.notional_value) || 0) / nav) * 100 : 0;
              const up = p.unrealized_pnl as number | null;
              return (
                <tr key={String(p.id)} className="border-t border-[var(--border)]">
                  <td className="py-2 pr-3 font-mono">{String(p.ticker)}</td>
                  <td className="py-2 pr-3">{String(p.asset_class)}</td>
                  <td className="py-2 pr-3">{String(p.direction)}</td>
                  <td className="py-2 pr-3 font-mono text-right">
                    {Number(p.quantity).toPrecision(4)}
                  </td>
                  <td className="py-2 pr-3 font-mono text-right">{Number(p.entry_price).toFixed(2)}</td>
                  <td className="py-2 pr-3 font-mono text-right">
                    {p.current_price != null ? Number(p.current_price).toFixed(2) : "—"}
                  </td>
                  <td
                    className={`py-2 pr-3 font-mono text-right ${
                      up != null && up >= 0 ? "text-tape-green" : "text-tape-red"
                    }`}
                  >
                    {up != null ? up.toLocaleString(undefined, { maximumFractionDigits: 0 }) : "—"}
                  </td>
                  <td className="py-2 pr-3 font-mono text-right text-[var(--muted)]">
                    {pctNav.toFixed(1)}%
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs text-right">
                    {p.stop_loss != null ? Number(p.stop_loss).toFixed(2) : "—"}
                  </td>
                  <td className="py-2 font-mono text-xs text-right">
                    {p.take_profit != null ? Number(p.take_profit).toFixed(2) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {open.length === 0 && (
          <p className="text-[var(--muted)] text-sm py-6">No open positions.</p>
        )}
      </div>

      {showClosed && (
        <div className="card p-5 overflow-x-auto">
          <h2 className="text-sm font-medium text-[var(--muted)] mb-4">Closed (30d)</h2>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-[var(--muted)] text-xs uppercase">
                <th className="pb-2">Ticker</th>
                <th className="pb-2">Class</th>
                <th className="pb-2">Dir</th>
                <th className="pb-2 text-right">Qty</th>
                <th className="pb-2 text-right">Entry</th>
                <th className="pb-2 text-right">Exit</th>
                <th className="pb-2 text-right">Realized</th>
              </tr>
            </thead>
            <tbody>
              {closed.map((p) => (
                <tr key={String(p.id)} className="border-t border-[var(--border)]">
                  <td className="py-2 font-mono">{String(p.ticker)}</td>
                  <td className="py-2">{String(p.asset_class)}</td>
                  <td className="py-2">{String(p.direction)}</td>
                  <td className="py-2 font-mono text-right">{Number(p.quantity).toPrecision(4)}</td>
                  <td className="py-2 font-mono text-right">{Number(p.entry_price).toFixed(2)}</td>
                  <td className="py-2 font-mono text-right">
                    {p.exit_price != null ? Number(p.exit_price).toFixed(2) : "—"}
                  </td>
                  <td className="py-2 font-mono text-right">
                    {p.realized_pnl != null ? Number(p.realized_pnl).toFixed(0) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
