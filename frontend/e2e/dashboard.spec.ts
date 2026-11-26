import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

test("first run: load sample data, watch it publish, read the dashboard", async ({ page }, info) => {
  // Each project gets its own server state only per run, so make the flow idempotent.
  await page.goto("/");
  const start = page.getByRole("button", { name: "Load sample data", exact: true });
  const overview = page.getByRole("button", { name: "Overview", exact: true });
  await expect(start.or(overview)).toBeVisible();
  if (await start.isVisible()) {
    await start.click();
  } else {
    await page.getByRole("button", { name: "Data", exact: true }).click();
    const picker = page.getByRole("combobox", { name: "Dataset" });
    if (await picker.isVisible()) await picker.selectOption({ label: "Sample shop (UCI Online Retail II)" });
  }

  await expect(page.getByText("Published").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Share of input rows that could not be typed", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Load sample data", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Sample data is already loaded.");

  await overview.click();
  // batch_b fixture: 15.30 + 18.50 + 19.50 + 19.50 + 2.95 = £75.75 across 4 invoices.
  await expect(page.getByRole("heading", { level: 1 })).toContainText("£75.75 gross revenue from 4 orders");
  await expect(page.getByText("quality checks passed")).toBeVisible();
  await page.screenshot({ path: `test-results/overview-${info.project.name}.png`, fullPage: true });

  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await page.getByRole("button", { name: "How much did we sell?" }).click();
  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(page.getByRole("heading", { name: "Gross revenue: £75.75" })).toBeVisible();
  await page.getByText("Query and published run").click();
  await expect(page.locator("pre")).toContainText("SELECT sum(revenue)");
  await page.screenshot({ path: `test-results/questions-${info.project.name}.png`, fullPage: true });

  await page.getByRole("textbox", { name: "Question" }).fill("How much did we sell in France?");
  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(page.getByRole("alert")).toContainText("outside the supported set");
});

test("a blocked upload preserves the last published dashboard", async ({ page }, info) => {
  await page.goto("/#data");
  const newDataset = page.getByRole("button", { name: "New dataset" });
  const firstUpload = page.getByRole("button", { name: "Upload your own CSV" });
  await expect(newDataset.or(firstUpload)).toBeVisible();
  if (await firstUpload.isVisible()) await firstUpload.click();
  const name = `Quality gate rehearsal (${info.project.name})`;
  await newDataset.click();
  await page.getByRole("textbox", { name: "Dataset name" }).fill(name);
  await page.getByRole("button", { name: "Create dataset" }).click();

  const picker = page.getByRole("combobox", { name: "Dataset" });
  await expect(picker.locator("option:checked")).toHaveText(name);
  const datasetId = await picker.inputValue();
  const dashboardUrl = `/api/v1/datasets/${datasetId}/dashboard`;

  const csv = page.getByLabel("CSV file");
  const fixture = (filename: string) =>
    fileURLToPath(new URL(`../../backend/tests/fixtures/ecommerce/${filename}`, import.meta.url));
  await csv.setInputFiles(fixture("batch_b.csv"));
  await expect(page.getByText("Published", { exact: true })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Rebuild dashboard" }).click();
  await expect(page.getByText("Published", { exact: true })).toHaveCount(2, { timeout: 30_000 });
  const before = await page.request.get(dashboardUrl);
  expect(before.ok()).toBe(true);
  const publication = (await before.json()).freshness.run_id;
  expect(publication).toBeTruthy();

  await csv.setInputFiles(fixture("batch_a.csv"));
  await expect(page.getByText("Blocked by quality checks", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("row").filter({ hasText: "Share of input rows that could not be typed" }),
  ).toContainText("Failed");
  await page.screenshot({ path: `test-results/quality-gate-${info.project.name}.png`, fullPage: true });

  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("£75.75 gross revenue from 4 orders");
  const after = await page.request.get(dashboardUrl);
  expect(after.ok()).toBe(true);
  expect((await after.json()).freshness.run_id).toBe(publication);
});
