import Link from "next/link";
import { getTrades } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function TradesPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; ticker?: string }>;
}) {
  const sp = await searchParams;
  const page = Math.max(1, parseInt(sp.page || "1", 10));
  const { rows, total, limit } = await getTrades(page, 20, sp.ticker);
  const pages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Trade journal</h1>
      <div className="card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-[var(--muted)] text-xs uppercase border-b border-[var(--border)]">
              <th className="p-3">Date</th>
              <th className="p-3">Ticker</th>
              <th className="p-3">Action</th>
              <th className="p-3 text-right">Qty</th>
              <th className="p-3 text-right">Price</th>
              <th className="p-3">Confidence</th>
              <th className="p-3">Rationale</th>
            </tr>
          </thead>
          <tbody>
            {(rows as Record<string, unknown>[]).map((t) => (
              <tr key={String(t.id)} className="border-t border-[var(--border)] align-top">
                <td className="p-3 font-mono text-xs whitespace-nowrap">{String(t.trade_date)}</td>
                <td className="p-3 font-mono">{String(t.ticker)}</td>
                <td className="p-3">{String(t.action)}</td>
                <td className="p-3 font-mono text-right">{Number(t.quantity).toPrecision(4)}</td>
                <td className="p-3 font-mono text-right">{Number(t.price).toFixed(2)}</td>
                <td className="p-3 text-xs">{String(t.confidence ?? "—")}</td>
                <td className="p-3 text-xs text-[var(--muted)] max-w-md">
                  {String(t.rationale ?? "").slice(0, 200)}
                  {String(t.rationale ?? "").length > 200 ? "…" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="p-8 text-center text-[var(--muted)] text-sm">No trades yet.</p>
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
          Page {page} / {pages} ({total} trades)
        </span>
      </div>
    </div>
  );
}
