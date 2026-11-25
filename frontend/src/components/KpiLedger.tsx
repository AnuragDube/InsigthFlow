import { useId, useState } from "react";
import type { Kpi } from "../api/types";
import { formatChange, formatExact, formatValue } from "../lib/format";

// Metrics where an increase is bad news (coloured as a decline).
const LOWER_IS_BETTER = new Set(["returns_value", "return_rate_value"]);

function deltaClass(kpi: Kpi): string {
  if (kpi.change === null || kpi.change === 0) return "delta";
  const good = LOWER_IS_BETTER.has(kpi.name) ? kpi.change < 0 : kpi.change > 0;
  return `delta ${good ? "up" : "down"}`;
}

function KpiItem({ kpi, comparison }: { kpi: Kpi; comparison: string | null }) {
  const [open, setOpen] = useState(false);
  const defId = useId();
  return (
    <div className="kpi">
      <dt>
        {kpi.label}
        <button
          type="button"
          className="info"
          aria-expanded={open}
          aria-controls={defId}
          aria-label={`How ${kpi.label} is calculated`}
          onClick={() => setOpen((o) => !o)}
        >
          i
        </button>
      </dt>
      <dd>
        <div className="value" title={formatExact(kpi.value, kpi.unit)}>
          {formatValue(kpi.value, kpi.unit)}
        </div>
        {comparison && (
          <div>
            <span className={deltaClass(kpi)}>{formatChange(kpi.change)}</span>
            <span className="delta"> {comparison}</span>
          </div>
        )}
        {open && (
          <p className="definition" id={defId}>
            {kpi.description}
          </p>
        )}
      </dd>
    </div>
  );
}

/** `comparison` is null when no metric has an earlier period: then say so once, not per tile. */
export function KpiLedger({ kpis, comparison }: { kpis: Kpi[]; comparison: string | null }) {
  return (
    <>
      {comparison === null && <p className="hint">Nothing earlier to compare with.</p>}
      <dl className="ledger" aria-label="Key metrics">
        {kpis.map((k) => (
          <KpiItem key={k.name} kpi={k} comparison={comparison} />
        ))}
      </dl>
    </>
  );
}
