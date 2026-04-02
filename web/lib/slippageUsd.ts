import { getInstrumentCalcInfo } from "./instruments";

function notionalMultiplier(ticker: string, instrumentType: string): number {
  const inst = instrumentType.toLowerCase();
  const info = getInstrumentCalcInfo(ticker);
  if (inst === "future") return info.futureMultiplier ?? 1;
  if (inst === "option") return info.optionContractMultiplier ?? 100;
  return 1;
}

/** Inverse of PaperSimulator._fill_price: BUY/COVER pay up; SHORT/SELL receive less. */
function slipPriceMode(
  action: string,
  positionDirection: string | undefined,
): "buy_cover" | "short_sell" {
  const a = String(action).toUpperCase();
  if (a === "CLOSE") {
    const d = String(positionDirection ?? "").toUpperCase();
    return d === "SHORT" ? "buy_cover" : "short_sell";
  }
  if (a === "BUY" || a === "COVER") return "buy_cover";
  return "short_sell";
}

/**
 * Dollar slippage for one paper fill (adverse move vs mid), matching execution/simulator.py.
 */
export function slippageUsdForFill(args: {
  action: string;
  quantity: number;
  fillPrice: number;
  slippageBps: number;
  ticker: string;
  instrumentType: string;
  /** Required logic for CLOSE rows (SELL exit vs COVER exit). */
  positionDirection?: string;
}): number {
  const bps = Number(args.slippageBps);
  if (!Number.isFinite(bps) || bps <= 0) return 0;
  const adj = bps / 10000;
  const fill = Number(args.fillPrice);
  const q = Math.abs(Number(args.quantity));
  if (!Number.isFinite(fill) || !Number.isFinite(q) || q < 1e-12) return 0;

  const mode = slipPriceMode(args.action, args.positionDirection);
  const mid =
    mode === "buy_cover" ? fill / (1 + adj) : fill / (1 - adj);
  const slipPerUnit = Math.abs(fill - mid);
  const mult = notionalMultiplier(args.ticker, args.instrumentType);
  return slipPerUnit * q * mult;
}
