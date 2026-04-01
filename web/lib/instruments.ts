import fs from "fs";
import path from "path";
import { parse as parseYaml } from "yaml";

export type InstrumentCalcInfo = {
  name: string;
  /** Contract multiplier for futures (null if not listed as future). */
  futureMultiplier: number | null;
  /** Options contract multiplier from options_underlyings (e.g. 100). */
  optionContractMultiplier: number | null;
  /** Set for ETF rows; USD for US-listed. */
  etfCurrency: string | null;
};

let registryCache: Map<string, InstrumentCalcInfo> | null = null;

function loadCalcRegistry(): Map<string, InstrumentCalcInfo> {
  if (registryCache) return registryCache;
  const map = new Map<string, InstrumentCalcInfo>();
  const yamlPath = path.resolve(process.cwd(), "..", "config", "instruments.yaml");
  try {
    const raw = fs.readFileSync(yamlPath, "utf8");
    const doc = parseYaml(raw) as Record<string, unknown>;

    const futureCats = ["equity_index_futures", "bond_futures", "commodity_futures"];
    for (const cat of futureCats) {
      for (const row of (doc[cat] as Record<string, unknown>[] | undefined) || []) {
        if (!row || typeof row !== "object" || row.ticker == null) continue;
        const t = String(row.ticker);
        const mult = Number(row.multiplier ?? 50);
        map.set(t, {
          name: String(row.name ?? t),
          futureMultiplier: mult,
          optionContractMultiplier: null,
          etfCurrency: null,
        });
      }
    }

    const etfCats = ["equity_index_etfs", "bond_etfs"];
    for (const cat of etfCats) {
      for (const row of (doc[cat] as Record<string, unknown>[] | undefined) || []) {
        if (!row || typeof row !== "object" || row.ticker == null) continue;
        const t = String(row.ticker);
        const cur = String(row.currency ?? "USD");
        const existing = map.get(t);
        map.set(t, {
          name: String(row.name ?? t),
          futureMultiplier: existing?.futureMultiplier ?? null,
          optionContractMultiplier: existing?.optionContractMultiplier ?? null,
          etfCurrency: cur,
        });
      }
    }

    for (const row of (doc.options_underlyings as Record<string, unknown>[] | undefined) || []) {
      if (!row || typeof row !== "object" || row.ticker == null) continue;
      const t = String(row.ticker);
      const om = Number(row.multiplier ?? 100);
      const existing = map.get(t);
      if (existing) {
        map.set(t, { ...existing, optionContractMultiplier: om });
      } else {
        map.set(t, {
          name: String(row.name ?? t),
          futureMultiplier: null,
          optionContractMultiplier: om,
          etfCurrency: String(row.currency ?? "USD"),
        });
      }
    }
  } catch {
    /* deploy without sibling config */
  }
  registryCache = map;
  return map;
}

export function getInstrumentCalcInfo(ticker: string): InstrumentCalcInfo {
  return (
    loadCalcRegistry().get(ticker) ?? {
      name: ticker,
      futureMultiplier: null,
      optionContractMultiplier: null,
      etfCurrency: null,
    }
  );
}

/** Human-readable underlying name from `config/instruments.yaml`, or the ticker if unknown. */
export function getInstrumentDisplayName(ticker: string): string {
  return getInstrumentCalcInfo(ticker).name;
}
