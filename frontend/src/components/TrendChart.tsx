import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Dashboard } from "../api/types";
import { formatDate, formatExact, formatValue } from "../lib/format";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function tick(period: string, grain: "day" | "month"): string {
  const [y, m, d] = period.split("-").map(Number);
  const mon = MONTHS[(m ?? 1) - 1];
  return grain === "month" ? `${mon} ${String(y).slice(2)}` : `${d} ${mon}`;
}

export function TrendChart({ trend }: { trend: Dashboard["trend"] }) {
  const total = trend.points.reduce((s, p) => s + (p.value ?? 0), 0);
  const peak = trend.points.reduce<{ period: string; value: number } | null>(
    (best, p) => (p.value !== null && (!best || p.value > best.value) ? { period: p.period, value: p.value } : best),
    null,
  );
  return (
    <figure className="chart" style={{ margin: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={trend.points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--rule)" vertical={false} />
          <XAxis
            dataKey="period"
            tickFormatter={(p: string) => tick(p, trend.grain)}
            stroke="var(--ink-faint)"
            fontSize={12}
            minTickGap={24}
          />
          <YAxis
            tickFormatter={(v: number) => formatValue(v, "GBP")}
            stroke="var(--ink-faint)"
            fontSize={12}
            width={64}
          />
          <Tooltip
            formatter={(v) => [formatExact(Number(v), "GBP"), "Gross revenue"]}
            labelFormatter={(p) => formatDate(String(p))}
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--rule)" }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--ledger)"
            strokeWidth={2}
            fill="var(--ledger-tint)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      <figcaption className="visually-hidden">
        Gross revenue by {trend.grain}: {trend.points.length} points totalling {formatExact(total, "GBP")}
        {peak ? `, highest ${formatExact(peak.value, "GBP")} on ${formatDate(peak.period)}` : ""}.
      </figcaption>
    </figure>
  );
}
