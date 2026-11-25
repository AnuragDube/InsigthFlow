import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import { formatDateRange, formatValue } from "../lib/format";

const LABELS: Record<string, string> = {
  high_value_repeat: "High-value repeat",
  recent_repeat: "Recent repeat",
  recent_single: "Recent single",
  inactive: "Inactive",
};

export function Customers({ datasetId, runId }: { datasetId: string; runId: string | null }) {
  const query = useQuery({
    queryKey: ["customer-segments", datasetId, runId],
    queryFn: () => api.customerSegments(datasetId),
    retry: (count, error) => count < 3 && !(error instanceof ApiError && error.status < 500),
  });
  return (
    <>
      <h1 className="summary">Customer segments</h1>
      {query.isPending && <p role="status">Loading customer segments…</p>}
      {query.error && <p className="notice" role="status">{query.error.message}</p>}
      {query.data && (
        <>
          <p>{formatDateRange(query.data.from, query.data.as_of)}. Only purchases with a known customer are counted.</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Segment</th><th className="num">Customers</th><th className="num">Orders</th><th className="num">Gross revenue</th></tr></thead>
              <tbody>
                {query.data.segments.map((segment) => (
                  <tr key={segment.key}>
                    <th scope="row">{LABELS[segment.key] ?? segment.key}<br /><small>{segment.definition}</small></th>
                    <td className="num">{formatValue(segment.customers, "count")}</td>
                    <td className="num">{formatValue(segment.orders, "count")}</td>
                    <td className="num">{formatValue(segment.gross_revenue, "GBP")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">Published run {query.data.published_run_id}</p>
        </>
      )}
    </>
  );
}
