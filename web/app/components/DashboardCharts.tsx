"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type NavRow = { date: string; nav: number; daily_return: number | null };

export function EquityLine({ data }: { data: NavRow[] }) {
  if (!data.length) {
    return <p className="text-[var(--muted)] text-sm py-12 text-center">No snapshot history yet.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243044" />
        <XAxis dataKey="date" tick={{ fill: "#8b9cb3", fontSize: 11 }} />
        <YAxis
          tick={{ fill: "#8b9cb3", fontSize: 11 }}
          tickFormatter={(v) => `$${(v / 1e6).toFixed(2)}M`}
        />
        <Tooltip
          contentStyle={{ background: "#141a22", border: "1px solid #243044" }}
          labelStyle={{ color: "#e8edf5" }}
          formatter={(v: number) => [`$${v.toLocaleString()}`, "NAV"]}
        />
        <Line type="monotone" dataKey="nav" stroke="#fbbf24" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function DailyReturnsBar({ data }: { data: NavRow[] }) {
  const withDr = data
    .filter((d) => d.daily_return != null && Number.isFinite(d.daily_return))
    .map((d) => ({
      date: d.date,
      dr: (d.daily_return as number) * 100,
    }));
  if (!withDr.length) {
    return <p className="text-[var(--muted)] text-sm py-8 text-center">No daily returns yet.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={withDr} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243044" />
        <XAxis dataKey="date" tick={{ fill: "#8b9cb3", fontSize: 10 }} />
        <YAxis tick={{ fill: "#8b9cb3", fontSize: 11 }} tickFormatter={(v) => `${v.toFixed(2)}%`} />
        <Tooltip
          contentStyle={{ background: "#141a22", border: "1px solid #243044" }}
          formatter={(v: number) => [`${v.toFixed(3)}%`, "Return"]}
        />
        <Bar dataKey="dr" radius={[2, 2, 0, 0]}>
          {withDr.map((e, i) => (
            <Cell key={i} fill={e.dr >= 0 ? "#34d399" : "#f87171"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

const LONG_FILL = "#34d399";
const SHORT_FILL = "#f87171";

export type AllocationBarRow = {
  ticker: string;
  name: string;
  direction: string;
  notional: number;
  returnPct: number | null;
};

/** Horizontal signed bars: long → right, short → left; tooltip has notional and % since entry. */
export function AllocationLongShortBars({ data }: { data: AllocationBarRow[] }) {
  if (!data.length) {
    return <p className="text-[var(--muted)] text-sm py-8 text-center">No open positions.</p>;
  }

  const rows = [...data]
    .map((d) => {
      const isShort = String(d.direction).toUpperCase() === "SHORT";
      const signed = isShort ? -Math.abs(d.notional) : Math.abs(d.notional);
      const fullLabel = d.name !== d.ticker ? `${d.ticker} · ${d.name}` : d.ticker;
      return {
        ...d,
        signed,
        label: d.ticker,
        fullLabel,
        isShort,
      };
    })
    .sort((a, b) => Math.abs(b.signed) - Math.abs(a.signed));

  const h = Math.min(440, Math.max(200, rows.length * 34 + 48));

  return (
    <div>
      <ResponsiveContainer width="100%" height={h}>
        <BarChart
          layout="vertical"
          data={rows}
          margin={{ top: 8, right: 20, left: 0, bottom: 8 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#243044" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: "#8b9cb3", fontSize: 10 }}
            tickFormatter={(v) => {
              const a = Math.abs(v);
              if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
              if (a >= 1e3) return `$${(v / 1e3).toFixed(0)}k`;
              return `$${v.toFixed(0)}`;
            }}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={76}
            tick={{ fill: "#8b9cb3", fontSize: 10 }}
          />
          <ReferenceLine x={0} stroke="#5c6b82" strokeDasharray="4 4" />
          <Tooltip
            cursor={{ fill: "#243044", opacity: 0.2 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as (typeof rows)[0];
              return (
                <div
                  className="rounded border border-[#243044] bg-[#141a22] px-3 py-2 text-xs shadow-lg"
                  style={{ color: "#e8edf5" }}
                >
                  <div className="font-medium">{p.fullLabel}</div>
                  <div className="text-[#8b9cb3] mt-0.5">{p.direction}</div>
                  <div className="mt-1 font-mono">
                    Notional:{" "}
                    {`$${Math.abs(p.signed).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                  </div>
                  <div className="font-mono mt-0.5">
                    Since entry:{" "}
                    {p.returnPct != null && Number.isFinite(p.returnPct)
                      ? `${p.returnPct >= 0 ? "+" : ""}${p.returnPct.toFixed(2)}%`
                      : "—"}
                  </div>
                </div>
              );
            }}
          />
          <Bar dataKey="signed" radius={[0, 3, 3, 0]} maxBarSize={24}>
            {rows.map((e, i) => (
              <Cell key={i} fill={e.isShort ? SHORT_FILL : LONG_FILL} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-4 flex flex-wrap items-center justify-center gap-x-8 gap-y-2 text-xs text-[var(--muted)]">
        <span className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-6 rounded-sm" style={{ background: LONG_FILL }} />
          Long (bars extend right)
        </span>
        <span className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-6 rounded-sm" style={{ background: SHORT_FILL }} />
          Short (bars extend left)
        </span>
      </div>
    </div>
  );
}
