import { useCurrency } from "../lib/currency";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import { formatDate, formatDateRange, formatValue } from "../lib/format";

const LABELS: Record<string, string> = {
  high_value_repeat: "High-value repeat",
  recent_repeat: "Recent repeat",
  recent_single: "Recent single",
  inactive: "Inactive",
};

export function Customers({ datasetId, runId }: { datasetId: string; runId: string | null }) {
  const currency = useCurrency();
  const query = useQuery({
    queryKey: ["customer-segments", datasetId, runId],
    queryFn: () => api.customerSegments(datasetId),
    retry: (count, error) => count < 3 && !(error instanceof ApiError && error.status < 500),
  });
  const backtest = useQuery({
    queryKey: ["inactivity-backtest", datasetId, runId],
    queryFn: () => api.inactivityBacktest(datasetId),
    enabled: Boolean(query.data),
    retry: (count, error) => count < 3 && !(error instanceof ApiError && error.status < 500),
  });
  const sameRun = query.data?.published_run_id === backtest.data?.published_run_id;
  const evaluation = sameRun ? backtest.data?.evaluation : undefined;
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
                    <td className="num">{formatValue(segment.gross_revenue, "GBP", currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">Published run {query.data.published_run_id}</p>
          <section className="section" aria-label="Inactivity backtest">
            <h2>Inactivity backtest</h2>
            {backtest.isFetching && <p role="status">Checking historical purchases…</p>}
            {backtest.error && <p className="hint" role="status">{backtest.error.message}</p>}
            {backtest.data && !sameRun && <p className="hint" role="status">A new run was published. Reload to compare results from the same run.</p>}
            {evaluation && (
              <>
                <p>
                  The rule flagged customers who had gone at least 30 days without buying by
                  {" "}{formatDate(evaluation.snapshot_date)}. Their next 30 days, through
                  {" "}{formatDate(evaluation.holdout_through)}, were held out for evaluation.
                </p>
                <dl>
                  <dt>Flagged customers who did not buy again</dt>
                  <dd>{formatValue(evaluation.true_positives, "count")} of {formatValue(evaluation.flagged, "count")} ({formatValue(evaluation.precision, "ratio")})</dd>
                  <dt>All cohort customers who did not buy again</dt>
                  <dd>{formatValue(evaluation.inactive, "count")} of {formatValue(evaluation.customers, "count")} ({formatValue(evaluation.baseline_rate, "ratio")})</dd>
                  <dt>Share of inactive customers the rule flagged</dt>
                  <dd>{formatValue(evaluation.recall, "ratio")}</dd>
                </dl>
              </>
            )}
          </section>
        </>
      )}
    </>
  );
}
