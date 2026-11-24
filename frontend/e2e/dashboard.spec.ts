import { expect, test } from "@playwright/test";

test("first run: load sample data, watch it publish, read the dashboard", async ({ page }, info) => {
  // Each project gets its own server state only per run, so make the flow idempotent.
  await page.goto("/");
  const start = page.getByRole("button", { name: "Load sample data" });
  if (await start.isVisible()) await start.click();
  else await page.goto("/#data");

  await expect(page.getByText("Published").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Share of input rows that could not be typed", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "Overview", exact: true }).click();
  // batch_b fixture: 15.30 + 18.50 + 19.50 + 19.50 + 2.95 = £75.75 across 4 invoices.
  await expect(page.getByRole("heading", { level: 1 })).toContainText("£75.75 gross revenue from 4 orders");
  await expect(page.getByText("quality checks passed")).toBeVisible();
  await page.screenshot({ path: `test-results/overview-${info.project.name}.png`, fullPage: true });
});
