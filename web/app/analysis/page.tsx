import Link from "next/link";
import { getAnalysis } from "@/lib/data";

export const dynamic = "force-dynamic";

export default async function AnalysisPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const sp = await searchParams;
  const page = Math.max(1, parseInt(sp.page || "1", 10));
  const { rows, total, limit } = await getAnalysis(page, 15);
  const pages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Daily analysis</h1>
      <div className="space-y-4">
        {(rows as Record<string, unknown>[]).map((r) => (
          <article key={String(r.id)} className="card p-5 space-y-2">
            <div className="flex flex-wrap gap-3 items-center">
              <span className="font-mono text-tape-amber">{String(r.date)}</span>
              <span className="px-2 py-0.5 rounded text-xs bg-[#243044]">{String(r.market_regime)}</span>
              <span className="text-xs text-[var(--muted)]">
                tokens {String(r.input_tokens)}/{String(r.output_tokens)} ~$
                {Number(r.estimated_cost_usd || 0).toFixed(3)}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-[var(--text)]">{String(r.macro_summary)}</p>
            {r.daily_findings ? (
              <div className="text-sm leading-relaxed text-[var(--text)] border-t border-[var(--border)] pt-3 mt-2 whitespace-pre-wrap">
                {String(r.daily_findings)}
              </div>
            ) : null}
            {r.risk_notes ? (
              <p className="text-xs text-tape-amber/90 border-t border-[var(--border)] pt-2">
                {String(r.risk_notes)}
              </p>
            ) : null}
          </article>
        ))}
      </div>
      {rows.length === 0 && (
        <p className="text-[var(--muted)] text-sm">No analysis rows — run `python -m src.main`.</p>
      )}
      <div className="flex gap-4 text-sm">
        {page > 1 && (
          <Link href={`/analysis?page=${page - 1}`} className="text-tape-amber hover:underline">
            ← Newer
          </Link>
        )}
        {page < pages && (
          <Link href={`/analysis?page=${page + 1}`} className="text-tape-amber hover:underline">
            Older →
          </Link>
        )}
      </div>
    </div>
  );
}
