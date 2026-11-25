import { expect, test } from "@playwright/test";

test("upload, cite, and remove a document", async ({ page }, info) => {
  await page.goto("/#documents");
  const title = `refund-policy-${info.project.name}.md`;
  await page.getByLabel("Upload document").setInputFiles({
    name: title,
    mimeType: "text/markdown",
    buffer: Buffer.from("# Returns\nRefunds take seven business days."),
  });
  const remove = page.getByRole("button", { name: `Remove ${title}`, exact: true });
  await expect(remove).toBeVisible();
  const question = page.getByRole("textbox", { name: "Search question" });
  const search = page.getByRole("button", { name: "Search", exact: true });
  await question.fill("How many business days for refunds?");
  await search.click();
  await expect(page.getByRole("heading", { name: `${title} · Lines 1–2` })).toBeVisible();
  await expect(page.getByText("Refunds take seven business days.", { exact: false })).toBeVisible();
  await page.screenshot({ path: `test-results/documents-${info.project.name}.png`, fullPage: true });

  await remove.click();
  await page.getByRole("button", { name: "Confirm removal" }).click();
  await expect(remove).toHaveCount(0);
  await search.click();
  await expect(page.getByText("No matching evidence was found.")).toBeVisible();
});
