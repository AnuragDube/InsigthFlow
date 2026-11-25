import { screen } from "@testing-library/react";
import type { Dashboard } from "../api/types";
import { mockFetch, renderWithQuery } from "../test-utils";
import { Overview } from "./Overview";

const dashboard: Dashboard = {
  range: { from: "2009-12-01", to: "2011-12-09", min: "2009-12-01", max: "2011-12-09" },
  kpis: [
    { name: "gross_revenue", label: "Gross revenue", unit: "GBP", description: "Sales value.", value: 19701685.49, previous: null, change: null },
    { name: "orders", label: "Orders", unit: "count", description: "Distinct invoices.", value: 39519, previous: 30000, change: 0.3173 },
    { name: "return_rate_value", label: "Return rate (by value)", unit: "ratio", description: "Returns / gross.", value: 0.0365, previous: 0.03, change: 0.2167 },
  ],
  trend: { metric: "gross_revenue", grain: "month", points: [{ period: "2009-12-01", value: 100 }] },
  top_products: [{ key: "22423", label: "REGENCY CAKESTAND 3 TIER", value: 277656.25 }],
  countries: [{ key: "United Kingdom", label: "United Kingdom", value: 16500000 }],
  freshness: { run_id: "r1", finished_at: "2026-11-24T19:08:47", quality: { passed: 9, warnings: 0, failed: 0 } },
};

afterEach(() => vi.unstubAllGlobals());

it("tells the reader the headline in a sentence and lists every KPI", async () => {
  mockFetch((url) => {
    if (url.includes("/dashboard")) return { body: dashboard };
    if (url.endsWith("/pipeline-runs/r1"))
      return {
        body: {
          id: "r1", data_source_id: "d1", trigger: "sample", status: "succeeded", error_code: null,
          created_at: "", started_at: "", finished_at: "2026-11-24T19:08:47",
          stages: [
            { stage: "silver", status: "succeeded", rows_in: 1067371, rows_out: 1044848, rows_quarantined: 0, duration_ms: 1745 },
            { stage: "gold", status: "succeeded", rows_in: 1044848, rows_out: 1015074, rows_quarantined: null, duration_ms: 1240 },
          ],
        },
      };
    return undefined;
  });
  renderWithQuery(<Overview datasetId="d1" onOpenData={() => {}} />);

  const summary = await screen.findByRole("heading", { level: 1 });
  expect(summary).toHaveTextContent("£19.7M gross revenue from 39,519 orders");
  expect(summary).toHaveTextContent("1 Dec 2009 to 9 Dec 2011");
  expect(screen.getByText("+31.7%")).toBeInTheDocument();
  // A rising return rate is bad news: it must not be styled as good.
  expect(screen.getByText("+21.7%")).toHaveClass("down");
  expect(await screen.findByText(/1,067,371/)).toBeInTheDocument();
  expect(screen.getByText("REGENCY CAKESTAND 3 TIER")).toBeInTheDocument();
  // The last month is cut short by the data, so its dip must be explained.
  expect(screen.getByText(/Dec 2011 only has data up to 9 Dec/)).toBeInTheDocument();
});

it("says once that there is nothing earlier to compare with", async () => {
  const none = { ...dashboard, kpis: dashboard.kpis.map((k) => ({ ...k, previous: null, change: null })) };
  mockFetch((url) => (url.includes("/dashboard") ? { body: none } : url.includes("/pipeline-runs/") ? { status: 404, body: {} } : undefined));
  renderWithQuery(<Overview datasetId="d1" onOpenData={() => {}} />);
  expect(await screen.findByText("Nothing earlier to compare with.")).toBeInTheDocument();
  expect(screen.queryByText(/vs previous/)).not.toBeInTheDocument();
});

it("invites the user to load data when nothing is published yet", async () => {
  mockFetch((url) =>
    url.includes("/dashboard")
      ? { status: 409, body: { type: "/errors/no-published-data", detail: "No data yet." } }
      : undefined,
  );
  renderWithQuery(<Overview datasetId="d1" onOpenData={() => {}} />);
  expect(await screen.findByRole("button", { name: "Add data" })).toBeInTheDocument();
});

it("labels a capped default as latest data", async () => {
  const capped = { ...dashboard, range: { ...dashboard.range, default_limited: true } };
  mockFetch((url) => (url.includes("/dashboard") ? { body: capped } : undefined));
  renderWithQuery(<Overview datasetId="d1" onOpenData={() => {}} />);
  expect(await screen.findByRole("button", { name: "Latest data" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

it("offers a path to rebuild when a published file is missing", async () => {
  const openData = vi.fn();
  mockFetch((url) =>
    url.includes("/dashboard")
      ? { status: 503, body: { type: "/errors/published-data-unavailable", detail: "Rebuild the dataset." } }
      : undefined,
  );
  renderWithQuery(<Overview datasetId="d1" onOpenData={openData} />);
  const button = await screen.findByRole("button", { name: "Open Data" });
  button.click();
  expect(openData).toHaveBeenCalledOnce();
});
