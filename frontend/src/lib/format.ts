import { BASE_CURRENCY } from "./currency";
import type { CurrencyPreference } from "./currency";

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

function converted(value: number, currency: CurrencyPreference, compact: boolean): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: currency.code,
    currencyDisplay: "code",
    ...(compact && Math.abs(value * currency.rate) >= 10_000 ? { notation: "compact" } : {}),
  }).format(value * currency.rate);
}

export function formatValue(value: number | null, unit: Unit, currency: CurrencyPreference = BASE_CURRENCY): string {
  if (value === null || Number.isNaN(value)) return DASH;
  if (unit === "GBP") return currency.code === "GBP" ? money(value) : converted(value, currency, true);
  if (unit === "ratio") return `${roundTo(value * 100, 1).toFixed(1)}%`;
  return grouped.format(value);
}

/** Exact value for tooltips and screen readers. */
export function formatExact(value: number | null, unit: Unit, currency: CurrencyPreference = BASE_CURRENCY): string {
  if (value === null) return "no data";
  if (unit === "GBP") return currency.code === "GBP" ? `£${pence.format(roundTo(value, 2))}` : converted(value, currency, false);
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

export function formatBytes(bytes: number): string {
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const exponent = Math.min(units.length - 1, bytes > 0 ? Math.floor(Math.log2(bytes) / 10) : 0);
  const size = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 }).format(bytes / 1024 ** exponent);
  return `${size} ${units[exponent]}`;
}
