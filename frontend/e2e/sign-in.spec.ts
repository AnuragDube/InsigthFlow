import { expect, test } from "@playwright/test";

test("an interactive pilot shows the workspace sign-in form", async ({ page }) => {
  const workspace = "7e266c0a-3a1f-4751-9ec1-31aa11694dc6";
  await page.route("**/api/v1/session", (route) => route.fulfill({ json: { interactive: true } }));
  await page.route("**/api/v1/datasets", (route) =>
    route.fulfill({
      status: 401,
      json: { type: "/errors/authentication-required", detail: "Sign in to access this workspace." },
    }),
  );
  await page.route((url) => url.pathname === "/api/v1/session/login", (route) => {
    expect(new URL(route.request().url()).searchParams.get("workspace")).toBe(workspace);
    return route.fulfill({ status: 303, headers: { location: "https://identity.example/authorize" } });
  });
  await page.route("https://identity.example/authorize", (route) =>
    route.fulfill({ contentType: "text/html", body: "<h1>Identity provider handoff</h1>" }),
  );

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in to InsightFlow." })).toBeVisible();
  await page.getByRole("textbox", { name: "Workspace ID" }).fill(workspace);
  await page.getByRole("button", { name: "Continue to sign in" }).click();
  await expect(page).toHaveURL("https://identity.example/authorize");
  await expect(page.getByText("Identity provider handoff")).toBeVisible();
});
