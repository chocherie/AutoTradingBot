/**
 * Format position quantity for tables. Avoids Number.toPrecision(4), which uses only
 * 4 significant figures and can round 1751.55 → "1752", breaking qty × price vs notional.
 */
export function formatPositionQuantity(q: number): string {
  if (!Number.isFinite(q)) return "—";
  const a = Math.abs(q);
  if (a >= 1) return q.toLocaleString(undefined, { maximumFractionDigits: 6 });
  if (a >= 0.01) return q.toLocaleString(undefined, { maximumFractionDigits: 8 });
  return q.toLocaleString(undefined, { maximumFractionDigits: 10 });
}
