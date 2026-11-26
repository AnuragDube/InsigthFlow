import { useCurrency } from "../lib/currency";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import { formatDate, formatValue } from "../lib/format";

export function Forecast({ datasetId, runId }: { datasetId: string; runId: string | null }) {
  const currency = useCurrency();
  const forecast = useQuery({
    queryKey: ["forecast", datasetId, runId],
    queryFn: () => api.forecast(datasetId),
    retry: (count, error) => count < 3 && !(error instanceof ApiError && error.status < 500),
  });
  const report = forecast.data;

  return (
    <>
      <h1 className="summary">Sales forecast</h1>
      {forecast.isPending && <p role="status">Loading forecast…</p>}
      {forecast.error && <p className="notice" role="status">{forecast.error.message}</p>}
      {report && (
        <>
          <p>Gross revenue for the seven days after {formatDate(report.as_of)}.</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Date</th><th className="num">Previous week</th><th className="num">Four-week weekday average</th></tr>
              </thead>
              <tbody>
                {report.points.map((point) => (
                  <tr key={point.date}>
                    <th scope="row">{formatDate(point.date)}</th>
                    <td className="num">{formatValue(point.seasonal_naive, report.unit, currency)}</td>
                    <td className="num">{formatValue(point.weekday_average, report.unit, currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <section className="section">
            <h2>Historical forecast error</h2>
            <p>
              Mean absolute error over {report.backtest.days_evaluated} held-out days:
              {" "}{formatValue(report.backtest.seasonal_naive_mae, report.unit, currency)} for the previous-week baseline
              and {formatValue(report.backtest.weekday_average_mae, report.unit, currency)} for the weekday average.
            </p>
            <p className="hint">
              Days without sales are treated as zero. Check that the latest sales day is complete
              before using the forecast.
            </p>
            <p className="hint">Published run {report.published_run_id}</p>
          </section>
        </>
      )}
    </>
  );
}
