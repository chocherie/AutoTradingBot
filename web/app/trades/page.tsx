import Link from "next/link";
import { getPositionJournal } from "@/lib/data";

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

export default async function TradesPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; ticker?: string }>;
}) {
  const sp = await searchParams;
  const page = Math.max(1, parseInt(sp.page || "1", 10));
  const { rows, total, limit } = await getPositionJournal(page, 20, sp.ticker);
  const pages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Trade journal</h1>
        <p className="text-[var(--muted)] text-sm mt-1">
          One row per position — entry and exit notionals. Closed: realized P&L. Open: unrealized P&L.
        </p>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full text-left text-sm min-w-[1100px]">
          <thead>
            <tr className="text-[var(--muted)] text-xs uppercase border-b border-[var(--border)]">
              <th className="p-3">Ticker</th>
              <th className="p-3">Dir</th>
              <th className="p-3">Status</th>
              <th className="p-3 text-right">Qty</th>
              <th className="p-3">Entry date</th>
              <th className="p-3 text-right">Entry px</th>
              <th className="p-3 text-right">Entry notional</th>
              <th className="p-3">Exit date</th>
              <th className="p-3 text-right">Exit px</th>
              <th className="p-3 text-right">Exit notional</th>
              <th className="p-3 text-right">P&L</th>
            </tr>
          </thead>
          <tbody>
            {(rows as Record<string, unknown>[]).map((r) => {
              const open = String(r.status) === "OPEN";
              const rpnl = r.realized_pnl != null ? Number(r.realized_pnl) : null;
              const upnl = r.unrealized_pnl != null ? Number(r.unrealized_pnl) : null;
              const pnlDisplay = open
                ? upnl != null
                  ? `${upnl >= 0 ? "+" : ""}${fmtMoney(upnl)}`
                  : "—"
                : rpnl != null
                  ? `${rpnl >= 0 ? "+" : ""}${fmtMoney(rpnl)}`
                  : "—";
              return (
                <tr key={String(r.id)} className="border-t border-[var(--border)] align-top">
                  <td className="p-3 font-mono">{String(r.ticker)}</td>
                  <td className="p-3 text-xs">{String(r.direction)}</td>
                  <td className="p-3 text-xs">{String(r.status)}</td>
                  <td className="p-3 font-mono text-right">{Number(r.quantity).toPrecision(4)}</td>
                  <td className="p-3 font-mono text-xs whitespace-nowrap">{String(r.entry_date)}</td>
                  <td className="p-3 font-mono text-right">{fmtPrice(Number(r.entry_price))}</td>
                  <td className="p-3 font-mono text-right">{fmtMoney(Number(r.entry_notional_usd))}</td>
                  <td className="p-3 font-mono text-xs whitespace-nowrap">
                    {open ? "" : r.exit_date != null ? String(r.exit_date) : "—"}
                  </td>
                  <td className="p-3 font-mono text-right">
                    {open ? "" : fmtPrice(r.exit_price != null ? Number(r.exit_price) : null)}
                  </td>
                  <td className="p-3 font-mono text-right">
                    {open ? "" : fmtMoney(r.exit_notional_usd != null ? Number(r.exit_notional_usd) : null)}
                  </td>
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
            })}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="p-8 text-center text-[var(--muted)] text-sm">No positions yet.</p>
        )}
      </div>
      <div className="flex gap-4 text-sm">
        {page > 1 && (
          <Link href={`/trades?page=${page - 1}`} className="text-tape-amber hover:underline">
            ← Previous
          </Link>
        )}
        {page < pages && (
          <Link href={`/trades?page=${page + 1}`} className="text-tape-amber hover:underline">
            Next →
          </Link>
        )}
        <span className="text-[var(--muted)]">
          Page {page} / {pages} ({total} positions)
        </span>
      </div>
    </div>
  );
}
