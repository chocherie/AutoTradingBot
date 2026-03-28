"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
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

const ALLOC_COLORS = ["#fbbf24", "#34d399", "#60a5fa", "#c084fc", "#f87171"];

export function AllocationDonut({
  data,
}: {
  data: { name: string; value: number }[];
}) {
  if (!data.length) {
    return <p className="text-[var(--muted)] text-sm py-8 text-center">No open positions.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          innerRadius={52}
          outerRadius={80}
          paddingAngle={2}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={ALLOC_COLORS[i % ALLOC_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: "#141a22", border: "1px solid #243044" }}
          formatter={(v: number) => [`$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`, ""]}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
