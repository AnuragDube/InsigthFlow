import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Dashboard } from "../api/types";
import { KpiLedger } from "../components/KpiLedger";
import { Provenance } from "../components/Provenance";
import { RankedList } from "../components/RankedList";
import { TrendChart } from "../components/TrendChart";
import { formatDateRange, formatValue } from "../lib/format";

type Preset = "all" | "12m" | "3m" | "30d";
const PRESETS: { id: Preset; label: string }[] = [
  { id: "all", label: "All data" },
  { id: "12m", label: "Last 12 months" },
  { id: "3m", label: "Last 3 months" },
  { id: "30d", label: "Last 30 days" },
];

function shift(iso: string, days: number, months = 0): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() - months);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

/** Presets are relative to the last day with data, not to today (historical datasets). */
function presetRange(preset: Preset, max: string): { from?: string; to?: string } {
  if (preset === "all") return {};
  if (preset === "30d") return { from: shift(max, 29), to: max };
  return { from: shift(max, -1, preset === "12m" ? 12 : 3), to: max };
}

function kpi(d: Dashboard, name: string) {
  return d.kpis.find((k) => k.name === name);
}

export function Overview({ datasetId, onOpenData }: { datasetId: string; onOpenData: () => void }) {
  const [preset, setPreset] = useState<Preset>("all");
  const [range, setRange] = useState<{ from?: string; to?: string }>({});
  const q = useQuery({
    queryKey: ["dashboard", datasetId, range.from, range.to],
    queryFn: () => api.dashboard(datasetId, range.from, range.to),
    placeholderData: (prev) => prev,
  });

  if (q.error instanceof ApiError && q.error.type === "/errors/no-published-data") {
    return (
      <section className="empty">
        <h1 className="summary">There is nothing to report yet.</h1>
        <p>Add a CSV of order lines or load the sample shop data. The dashboard fills in as soon as the first run passes its quality checks.</p>
        <div className="actions">
          <button type="button" className="btn" onClick={onOpenData}>
            Add data
          </button>
        </div>
      </section>
    );
  }
  if (q.error) return <p className="notice error">{q.error.message}</p>;
  if (!q.data) return <p className="hint" aria-busy="true">Loading the dashboard…</p>;

  const d = q.data;
  const gross = kpi(d, "gross_revenue");
  const orders = kpi(d, "orders");
  const days =
    (Date.parse(`${d.range.to}T00:00:00Z`) - Date.parse(`${d.range.from}T00:00:00Z`)) / 86_400_000 + 1;
  const choose = (p: Preset) => {
    setPreset(p);
    setRange(presetRange(p, d.range.max));
  };

  return (
    <>
      <h1 className="summary">
        <strong>{formatValue(gross?.value ?? null, "GBP")}</strong> gross revenue from{" "}
        {formatValue(orders?.value ?? null, "count")} orders, {formatDateRange(d.range.from, d.range.to)}.
      </h1>

      <div className="toolbar">
        <div className="presets" role="group" aria-label="Period">
          {PRESETS.map((p) => (
            <button key={p.id} type="button" className="chip" aria-pressed={preset === p.id} onClick={() => choose(p.id)}>
              {p.label}
            </button>
          ))}
        </div>
        <label className="field">
          From
          <input
            type="date"
            value={d.range.from}
            min={d.range.min}
            max={d.range.to}
            onChange={(e) => e.target.value && (setPreset("all"), setRange({ from: e.target.value, to: d.range.to }))}
          />
        </label>
        <label className="field">
          To
          <input
            type="date"
            value={d.range.to}
            min={d.range.from}
            max={d.range.max}
            onChange={(e) => e.target.value && (setPreset("all"), setRange({ from: d.range.from, to: e.target.value }))}
          />
        </label>
      </div>

      <Provenance freshness={d.freshness} onOpenData={onOpenData} />

      <KpiLedger kpis={d.kpis} comparison={`vs previous ${days} days`} />

      <section className="section">
        <h2>Gross revenue by {d.trend.grain}</h2>
        <p className="hint">Days without sales count as zero.</p>
        <TrendChart trend={d.trend} />
      </section>

      <div className="split">
        <section className="section">
          <h2>Best-selling products</h2>
          <p className="hint">By gross revenue in the period.</p>
          <RankedList items={d.top_products} label="Products by gross revenue" />
        </section>
        <section className="section">
          <h2>Where sales come from</h2>
          <p className="hint">Country on each order line.</p>
          <RankedList items={d.countries} label="Countries by gross revenue" />
        </section>
      </div>
    </>
  );
}
