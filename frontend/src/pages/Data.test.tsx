import { fireEvent, screen, waitFor } from "@testing-library/react";
import { mockFetch, renderWithQuery } from "../test-utils";
import { Data } from "./Data";

afterEach(() => vi.unstubAllGlobals());

const run = {
  id: "r1", data_source_id: "d1", trigger: "upload", status: "blocked_by_quality", error_code: "quality_gate_failed",
  created_at: "2026-11-24T19:00:00", started_at: "2026-11-24T19:00:00", finished_at: "2026-11-24T19:00:03",
  stages: [{ stage: "silver", status: "succeeded", rows_in: 22, rows_out: 18, rows_quarantined: 2, duration_ms: 40 }],
};

it("shows batches, runs and the quality report of the latest run", async () => {
  mockFetch((url) => {
    if (url.endsWith("/workspace/storage")) return { body: { retained_csv_bytes: 2048, limit_bytes: 1048576 } };
    if (url.endsWith("/datasets/d1/ingestions"))
      return { body: { items: [{ id: "i1", original_name: "batch_a.csv", sha256: "x", size_bytes: 1200, row_count: 14, status: "stored", is_active: true, created_at: "2026-11-24T19:00:00" }] } };
    if (url.includes("/pipeline-runs?dataset_id=d1")) return { body: { items: [run] } };
    if (url.endsWith("/pipeline-runs/r1/quality"))
      return { body: { items: [{ rule_id: "quarantine_ratio", stage: "silver", severity: "blocking", passed: false, observed: 0.0909, threshold: 0.01, description: "Share of rows that could not be typed." }] } };
    return undefined;
  });
  renderWithQuery(<Data datasetId="d1" />);
  expect(await screen.findByText("batch_a.csv")).toBeInTheDocument();
  expect(await screen.findByText("Blocked by quality checks")).toBeInTheDocument();
  expect(await screen.findByText("Share of rows that could not be typed.")).toBeInTheDocument();
  expect(screen.getByText("Failed")).toBeInTheDocument();
  expect(await screen.findByRole("group", { name: "Workspace CSV storage" })).toHaveTextContent("2 KiB of 1 MiB used");
});

it("excludes a batch and sends the client header", async () => {
  const fetchMock = mockFetch((url, init) => {
    if (url.endsWith("/workspace/storage")) return { body: { retained_csv_bytes: 10, limit_bytes: 1048576 } };
    if (url.endsWith("/datasets/d1/ingestions"))
      return { body: { items: [{ id: "i1", original_name: "bad.csv", sha256: "x", size_bytes: 10, row_count: 1, status: "stored", is_active: true, created_at: "2026-11-24T19:00:00" }] } };
    if (url.includes("/pipeline-runs?")) return { body: { items: [] } };
    if (url.endsWith("/ingestions/i1") && init?.method === "PATCH") return { body: { run_id: null, rerun_queued: true } };
    return undefined;
  });
  renderWithQuery(<Data datasetId="d1" />);
  fireEvent.click(await screen.findByRole("button", { name: "Exclude bad.csv" }));
  await waitFor(() => {
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/ingestions/i1"));
    expect(call?.[1]?.headers).toMatchObject({ "X-InsightFlow-Client": "web" });
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ is_active: false });
  });
});
