import type { Dashboard } from "../api/types";

function csvCell(value: string | number | null): string {
  if (value === null) return "";
  if (typeof value === "number") return String(value);
  // Spreadsheet programs may interpret formula-like text as executable formulas.
  const safe = /^[\s]*[=+\-@]|^[\t\r\n]/.test(value) ? "'" + value : value;
  return /[",\r\n]/.test(safe) ? '"' + safe.replaceAll('"', '""') + '"' : safe;
}

export function dashboardKpiCsv(report: Dashboard): string {
  const rows = [
    ["metric", "unit", "value", "previous", "change_ratio", "from", "to", "published_run_id"],
    ...report.kpis.map((kpi) => [
      kpi.name,
      kpi.unit,
      kpi.value,
      kpi.previous,
      kpi.change,
      report.range.from,
      report.range.to,
      report.freshness.run_id,
    ]),
  ];
  return rows.map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

export function downloadDashboardKpis(report: Dashboard): void {
  const file = new Blob([dashboardKpiCsv(report)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = url;
  link.download = `insightflow-kpis-${report.range.from}-to-${report.range.to}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
