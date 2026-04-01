import { getInstrumentCalcInfo } from "./instruments";

function fmtCalc(n: number): string {
  if (!Number.isFinite(n)) return "?";
  const a = Math.abs(n);
  if (a >= 1_000_000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (a >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (a >= 1) return n.toLocaleString(undefined, { maximumFractionDigits: 6 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

export type EntryNotionalCalc = {
  /** Single-line formula shown under the notional figure */
  formula: string;
  /** Optional reconcile note vs DB */
  note?: string;
};

/**
 * Build display lines for entry notional (matches bot: portfolio.add_position).
 * Futures: |qty| × entry × multiplier. Options: |qty| × premium × opt mult. ETF USD: |qty| × entry.
 */
export function entryNotionalCalculation(
  ticker: string,
  instrumentType: string,
  qty: number,
  entryPrice: number,
  storedNotionalUsd: number,
): EntryNotionalCalc {
  const info = getInstrumentCalcInfo(ticker);
  const q = Math.abs(Number(qty));
  const px = Number(entryPrice);
  const stored = Number(storedNotionalUsd);
  const inst = instrumentType.toUpperCase();

  const reconcile = (product: number) => {
    if (!Number.isFinite(product) || !Number.isFinite(stored)) return undefined;
    const diff = Math.abs(product - stored);
    if (diff <= 1) return undefined;
    return `Stored ${fmtMoneyUsd(stored)} — ${diff <= stored * 0.02 ? "within ~2% (slippage / rounding)." : "if this persists, verify instrument_type in DB."}`;
  };

  if (inst === "FUTURE") {
    const m = info.futureMultiplier ?? 1;
    const product = q * px * m;
    return {
      formula: `${fmtCalc(q)} × ${fmtCalc(px)} × ${m} = ${fmtCalc(product)} USD`,
      note: reconcile(product),
    };
  }

  if (inst === "OPTION") {
    const m = info.optionContractMultiplier ?? 100;
    const product = q * px * m;
    return {
      formula: `${fmtCalc(q)} × ${fmtCalc(px)} × ${m} = ${fmtCalc(product)} USD (option contracts)`,
      note: reconcile(product),
    };
  }

  const cur = info.etfCurrency;
  if (cur && cur !== "USD") {
    return {
      formula: `${fmtCalc(q)} × ${fmtCalc(px)} × FX(${cur}→USD)`,
      note: `Stored: ${fmtMoneyUsd(stored)} (FX at session).`,
    };
  }

  const product = q * px;
  return {
    formula: `${fmtCalc(q)} × ${fmtCalc(px)} = ${fmtCalc(product)} USD`,
    note: reconcile(product),
  };
}

function fmtMoneyUsd(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}
