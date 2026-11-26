import { useCurrency } from "../lib/currency";
import type { Ranked } from "../api/types";
import { formatExact, formatValue } from "../lib/format";

export function RankedList({ items, label }: { items: Ranked[]; label: string }) {
  const currency = useCurrency();
  const max = Math.max(0, ...items.map((i) => i.value ?? 0));
  if (items.length === 0) return <p className="hint">No sales in this period.</p>;
  return (
    <ol className="ranked" aria-label={label}>
      {items.map((item) => (
        <li key={item.key}>
          <span className="name" title={item.label ?? item.key}>
            {item.label ?? item.key}
          </span>
          <span className="amount" title={formatExact(item.value, "GBP", currency)}>
            {formatValue(item.value, "GBP", currency)}
          </span>
          <span className="bar" aria-hidden="true">
            <span style={{ width: `${max > 0 ? ((item.value ?? 0) / max) * 100 : 0}%` }} />
          </span>
        </li>
      ))}
    </ol>
  );
}
