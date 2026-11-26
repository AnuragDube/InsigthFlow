import type { Dashboard } from "../api/types";
import { dashboardKpiCsv } from "./dashboardCsv";

it("exports canonical values, empty comparisons, and publication context", () => {
  const report: Dashboard = {
    range: { from: "2011-01-01", to: "2011-01-31", min: "2011-01-01", max: "2011-01-31" },
    trend: { metric: "gross_revenue", grain: "month", points: [] },
    top_products: [],
    countries: [],
    freshness: { run_id: "test-run", finished_at: null, quality: { passed: 9, warnings: 0, failed: 0 } },
    kpis: [
      { name: "gross_revenue", label: "Gross revenue", description: "", unit: "GBP", value: 140.445, previous: null, change: null },
      { name: ' =unsafe,"quoted"', label: "Synthetic", description: "", unit: "ratio", value: 0.25, previous: 0.5, change: -0.5 },
    ],
  };
  expect(dashboardKpiCsv(report)).toBe(
    "metric,unit,value,previous,change_ratio,from,to,published_run_id\r\n" +
    "gross_revenue,GBP,140.445,,,2011-01-01,2011-01-31,test-run\r\n" +
    "\"' =unsafe,\"\"quoted\"\"\",ratio,0.25,0.5,-0.5,2011-01-01,2011-01-31,test-run\r\n",
  );
});
