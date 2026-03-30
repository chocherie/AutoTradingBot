import fs from "fs";
import path from "path";
import { parse as parseYaml } from "yaml";

let cache: Map<string, string> | null = null;

function loadMap(): Map<string, string> {
  if (cache) return cache;
  const map = new Map<string, string>();
  const yamlPath = path.resolve(process.cwd(), "..", "config", "instruments.yaml");
  try {
    const raw = fs.readFileSync(yamlPath, "utf8");
    const doc = parseYaml(raw) as Record<string, unknown>;
    for (const value of Object.values(doc)) {
      if (!Array.isArray(value)) continue;
      for (const row of value) {
        if (row && typeof row === "object" && "ticker" in row && "name" in row) {
          const t = String((row as { ticker: string }).ticker);
          const n = String((row as { name: string }).name);
          map.set(t, n);
        }
      }
    }
  } catch {
    /* repo layout differs on deploy — fall back to ticker-only */
  }
  cache = map;
  return map;
}

/** Human-readable underlying name from `config/instruments.yaml`, or the ticker if unknown. */
export function getInstrumentDisplayName(ticker: string): string {
  return loadMap().get(ticker) ?? ticker;
}
