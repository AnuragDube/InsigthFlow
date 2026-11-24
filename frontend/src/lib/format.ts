export type Unit = "GBP" | "count" | "ratio";

const DASH = "—";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const grouped = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const pence = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Decimal-correct rounding: 140.445 -> 140.45 (plain float maths gives 140.44). */
function roundTo(value: number, digits: number): number {
  return Number(`${Math.round(Number(`${value}e${digits}`))}e-${digits}`);
}

function money(v: number): string {
  const sign = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${sign}£${roundTo(a / 1_000_000, 1).toFixed(1)}M`;
  if (a >= 10_000) return `${sign}£${grouped.format(roundTo(a / 1_000, 0))}K`;
  return `${sign}£${pence.format(roundTo(a, 2))}`;
}

export function formatValue(value: number | null, unit: Unit): string {
  if (value === null || Number.isNaN(value)) return DASH;
  if (unit === "GBP") return money(value);
  if (unit === "ratio") return `${roundTo(value * 100, 1).toFixed(1)}%`;
  return grouped.format(value);
}

/** Exact value for tooltips and screen readers. */
export function formatExact(value: number | null, unit: Unit): string {
  if (value === null) return "no data";
  if (unit === "GBP") return `£${pence.format(roundTo(value, 2))}`;
  if (unit === "ratio") return `${roundTo(value * 100, 2)}%`;
  return grouped.format(value);
}

export function formatChange(change: number | null): string {
  if (change === null || Number.isNaN(change)) return DASH;
  const pct = roundTo(Math.abs(change) * 100, 1).toFixed(1);
  return `${change < 0 ? "−" : "+"}${pct}%`;
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[(m ?? 1) - 1]} ${y}`;
}

export function formatDateRange(from: string, to: string): string {
  return from === to ? formatDate(from) : `${formatDate(from)} to ${formatDate(to)}`;
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return DASH;
  return ms < 1000 ? `${ms} ms` : `${roundTo(ms / 1000, 1)} s`;
}
