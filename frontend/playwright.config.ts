import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1, // projects share one server and dataset: run them in order
  fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:8010", trace: "off" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "node e2e/start-server.mjs",
    url: "http://127.0.0.1:8010/ready",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
