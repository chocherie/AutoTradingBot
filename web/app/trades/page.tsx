import Link from "next/link";
import { getTradesJournalData } from "@/lib/data";
import { formatPositionQuantity } from "@/lib/formatQuantity";
import { getInstrumentDisplayName } from "@/lib/instruments";

export const dynamic = "force-dynamic";

function fmtMoney(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function fmtPrice(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

/** Group positions by calendar entry date (session), newest session first; rows sorted by ticker. */
function groupByEntrySession(
  rows: Record<string, unknown>[],
): { session: string; rows: Record<string, unknown>[] }[] {
  const map = new Map<string, Record<string, unknown>[]>();
  for (const r of rows) {
    const session = String(r.entry_date ?? "").slice(0, 10) || "—";
    if (!map.has(session)) map.set(session, []);
    map.get(session)!.push(r);
  }
  return Array.from(map.entries())
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([session, rs]) => ({
      session,
      rows: [...rs].sort((x, y) => String(x.ticker).localeCompare(String(y.ticker))),
    }));
}

function TradeTable({
  grouped,
  showExitCols,
  showLastPx = false,
}: {
  grouped: { session: string; rows: Record<string, unknown>[] }[];
  showExitCols: boolean;
  /** Mark-to-market last price from `positions.current_price` (open book only). */
  showLastPx?: boolean;
}) {
  if (grouped.length === 0 || grouped.every((g) => g.rows.length === 0)) {
    return <p className="p-8 text-center text-[var(--muted)] text-sm">No rows.</p>;
  }

  return (
    <table className="w-full text-left text-sm min-w-[1260px]">
      <thead>
        <tr className="text-[var(--muted)] text-xs uppercase border-b border-[var(--border)]">
          <th className="p-3 min-w-[160px]">Ticker / name</th>
          <th className="p-3">Dir</th>
          <th className="p-3 text-right">Qty</th>
          <th className="p-3">Entry date</th>
          <th className="p-3 text-right">Entry px</th>
          <th className="p-3 text-right">Entry notional</th>
          {showLastPx && !showExitCols && (
            <th className="p-3 text-right">Last</th>
          )}
          {showExitCols && (
            <>
              <th className="p-3">Exit date</th>
              <th className="p-3 text-right">Exit px</th>
              <th className="p-3 text-right">Exit notional</th>
            </>
          )}
          <th className="p-3 text-right">P&L</th>
        </tr>
      </thead>
      <tbody>
        {grouped.map(({ session, rows }) => (
          <FragmentSession
            key={session}
            session={session}
            rows={rows}
            showExitCols={showExitCols}
            showLastPx={showLastPx}
          />
        ))}
      </tbody>
    </table>
  );
}

function FragmentSession({
  session,
  rows,
  showExitCols,
  showLastPx = false,
}: {
  session: string;
  rows: Record<string, unknown>[];
  showExitCols: boolean;
  showLastPx?: boolean;
}) {
  const colSpan = showExitCols ? 10 : showLastPx ? 8 : 7;
  return (
    <>
      <tr className="bg-[#1a2230]/80">
        <td
          colSpan={colSpan}
          className="py-2.5 px-3 text-xs font-medium uppercase tracking-wide text-tape-amber/90 border-t border-tape-amber/20"
        >
          Entry session {session}
        </td>
      </tr>
      {rows.map((r) => (
        <TradeRow key={String(r.id)} r={r} showExitCols={showExitCols} showLastPx={showLastPx} />
      ))}
    </>
  );
}

function TradeRow({
  r,
  showExitCols,
  showLastPx = false,
}: {
  r: Record<string, unknown>;
  showExitCols: boolean;
  showLastPx?: boolean;
}) {
  const open = String(r.status) === "OPEN";
  const rpnl = r.realized_pnl != null ? Number(r.realized_pnl) : null;
  const upnl = r.unrealized_pnl != null ? Number(r.unrealized_pnl) : null;
  const tk = String(r.ticker);
  const dn = getInstrumentDisplayName(tk);
  const pnlDisplay = open
    ? upnl != null
      ? `${upnl >= 0 ? "+" : ""}${fmtMoney(upnl)}`
      : "—"
    : rpnl != null
      ? `${rpnl >= 0 ? "+" : ""}${fmtMoney(rpnl)}`
      : "—";

  return (
    <tr className="border-t border-[var(--border)] align-top">
      <td className="p-3">
        <div className="font-mono">{tk}</div>
        {dn !== tk && (
          <div className="text-xs text-[var(--muted)] mt-1 leading-snug max-w-[200px]">{dn}</div>
        )}
      </td>
      <td className="p-3 text-xs">{String(r.direction)}</td>
      <td className="p-3 font-mono text-right">{formatPositionQuantity(Number(r.quantity))}</td>
      <td className="p-3 font-mono text-xs whitespace-nowrap">{String(r.entry_date)}</td>
      <td className="p-3 font-mono text-right">{fmtPrice(Number(r.entry_price))}</td>
      <td className="p-3 font-mono text-right">{fmtMoney(Number(r.entry_notional_usd))}</td>
      {showLastPx && !showExitCols && (
        <td className="p-3 font-mono text-right">
          {fmtPrice(r.current_price != null ? Number(r.current_price) : null)}
        </td>
      )}
      {showExitCols && (
        <>
          <td className="p-3 font-mono text-xs whitespace-nowrap">
            {open ? "—" : r.exit_date != null ? String(r.exit_date) : "—"}
          </td>
          <td className="p-3 font-mono text-right">
            {open ? "—" : fmtPrice(r.exit_price != null ? Number(r.exit_price) : null)}
          </td>
          <td className="p-3 font-mono text-right">
            {open ? "—" : fmtMoney(r.exit_notional_usd != null ? Number(r.exit_notional_usd) : null)}
          </td>
        </>
      )}
      <td
        className={`p-3 font-mono text-right ${
          !open && rpnl != null
            ? rpnl > 0
              ? "text-tape-green"
              : rpnl < 0
                ? "text-tape-red"
                : ""
            : open && upnl != null
              ? upnl > 0
                ? "text-tape-green"
                : upnl < 0
                  ? "text-tape-red"
                  : ""
              : ""
        }`}
      >
        {pnlDisplay}
      </td>
    </tr>
  );
}

export default async function TradesPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; ticker?: string }>;
}) {
  const sp = await searchParams;
  const closedPage = Math.max(1, parseInt(sp.page || "1", 10));
  const data = await getTradesJournalData(closedPage, 20, sp.ticker);
  const closedPages = Math.max(1, Math.ceil(data.closedTotal / data.closedLimit));

  const openGrouped = groupByEntrySession(data.open);
  const closedGrouped = groupByEntrySession(data.closed);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Trade journal</h1>
        <p className="text-[var(--muted)] text-sm mt-1">
          Open and closed positions in separate sections. Each block is grouped by <strong>entry session</strong>{" "}
          (trade <code className="text-xs font-mono">entry_date</code>), newest sessions first.
        </p>
      </div>

      {data.dbUnavailable && (
        <div className="rounded-lg border border-tape-amber/40 bg-tape-amber/10 px-4 py-3 text-sm text-tape-amber">
          No database available here yet.
        </div>
      )}

      <div className="space-y-3">
        <h2 className="text-lg font-medium text-tape-amber">
          Open trades
          <span className="text-[var(--muted)] text-sm font-normal ml-2">({data.open.length})</span>
        </h2>
        <div className="card overflow-x-auto">
          <TradeTable grouped={openGrouped} showExitCols={false} showLastPx />
        </div>
      </div>

      <div className="space-y-3">
        <h2 className="text-lg font-medium text-tape-amber">
          Closed trades
          <span className="text-[var(--muted)] text-sm font-normal ml-2">
            ({data.closedTotal} total · page {data.closedPage} of {closedPages})
          </span>
        </h2>
        <div className="card overflow-x-auto">
          <TradeTable grouped={closedGrouped} showExitCols={true} />
        </div>
        <div className="flex gap-4 text-sm">
          {data.closedPage > 1 && (
            <Link
              href={`/trades?page=${data.closedPage - 1}${sp.ticker ? `&ticker=${encodeURIComponent(sp.ticker)}` : ""}`}
              className="text-tape-amber hover:underline"
            >
              ← Previous (closed)
            </Link>
          )}
          {data.closedPage < closedPages && (
            <Link
              href={`/trades?page=${data.closedPage + 1}${sp.ticker ? `&ticker=${encodeURIComponent(sp.ticker)}` : ""}`}
              className="text-tape-amber hover:underline"
            >
              Next (closed) →
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
