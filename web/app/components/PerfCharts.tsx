"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Snap = { date: string; nav: number; sharpe_ratio: number | null };

export function DrawdownArea({ data }: { data: { date: string; nav: number }[] }) {
  if (data.length < 2) {
    return <p className="text-[var(--muted)] text-sm py-8 text-center">Need more history.</p>;
  }
  let peak = data[0].nav;
  const dd = data.map((d) => {
    peak = Math.max(peak, d.nav);
    return { date: d.date, dd: ((peak - d.nav) / peak) * 100 };
  });
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={dd} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243044" />
        <XAxis dataKey="date" tick={{ fill: "#8b9cb3", fontSize: 10 }} />
        <YAxis tick={{ fill: "#8b9cb3", fontSize: 11 }} tickFormatter={(v) => `${v.toFixed(1)}%`} />
        <Tooltip
          contentStyle={{ background: "#141a22", border: "1px solid #243044" }}
          formatter={(v: number) => [`${v.toFixed(2)}%`, "Drawdown"]}
        />
        <Area type="monotone" dataKey="dd" stroke="#f87171" fill="#f8717133" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function RollingSharpeLine({ data }: { data: Snap[] }) {
  const window = 30;
  const enriched: { date: string; sh: number | null }[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < window - 1) {
      enriched.push({ date: data[i].date, sh: null });
      continue;
    }
    const slice = data.slice(i - window + 1, i + 1);
    const navs = slice.map((s) => s.nav);
    const rets: number[] = [];
    for (let j = 1; j < navs.length; j++) {
      rets.push((navs[j] - navs[j - 1]) / navs[j - 1]);
    }
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const v = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(rets.length - 1, 1);
    const sd = Math.sqrt(v);
    const sharpe = sd > 1e-8 ? (mean / sd) * Math.sqrt(252) : null;
    enriched.push({ date: data[i].date, sh: sharpe });
  }
  const plot = enriched.filter((e) => e.sh != null);
  if (!plot.length) {
    return <p className="text-[var(--muted)] text-sm py-8 text-center">Not enough data for rolling Sharpe.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={plot} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#243044" />
        <XAxis dataKey="date" tick={{ fill: "#8b9cb3", fontSize: 10 }} />
        <YAxis tick={{ fill: "#8b9cb3", fontSize: 11 }} />
        <Tooltip contentStyle={{ background: "#141a22", border: "1px solid #243044" }} />
        <Line type="monotone" dataKey="sh" stroke="#34d399" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
