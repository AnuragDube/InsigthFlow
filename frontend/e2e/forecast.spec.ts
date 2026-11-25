import { expect, test } from "@playwright/test";

test("forecast shows two methods and their historical errors", async ({ page }, info) => {
  const headers = { "X-InsightFlow-Client": "web" };
  const name = `Forecast fixture (${info.project.name})`;
  const dataset = await page.request.post("/api/v1/datasets", { headers, data: { name } });
  expect(dataset.ok()).toBeTruthy();
  const { id } = await dataset.json();
  const csv = ["Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country"];
  for (let day = 0; day < 35; day++) {
    const date = new Date(Date.UTC(2010, 11, 1 + day)).toISOString().slice(0, 10);
    csv.push(`${1000 + day},85123A,WHITE HEART,1,${date} 08:00:00,2.00,17850,United Kingdom`);
  }
  const uploaded = await page.request.post(`/api/v1/datasets/${id}/uploads`, {
    headers,
    multipart: { file: { name: "sales.csv", mimeType: "text/csv", buffer: Buffer.from(csv.join("\n")) } },
  });
  expect(uploaded.ok()).toBeTruthy();
  await expect.poll(async () => (await page.request.get(`/api/v1/datasets/${id}/forecast`)).ok()).toBe(true);

  await page.goto("/#forecast");
  await expect(page.getByRole("heading", { name: "Sales forecast" })).toBeVisible();
  const picker = page.getByRole("combobox", { name: "Dataset" });
  if (await picker.isVisible()) await picker.selectOption({ label: name });
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(8);
  await expect(page.getByText(/Mean absolute error over 7 held-out days/)).toBeVisible();

  await page.getByRole("button", { name: "Customers", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer segments" })).toBeVisible();
  const repeat = page.getByRole("row").filter({ hasText: "Recent repeat" });
  await expect(repeat).toContainText("£70.00");
});
