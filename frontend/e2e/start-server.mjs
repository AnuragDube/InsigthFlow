// Starts the real backend (serving the built SPA) on an isolated, throwaway data directory,
// with the small golden fixture as "sample data". Used by playwright.config.ts.
import { spawn } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const work = mkdtempSync(join(tmpdir(), "insightflow-e2e-"));
const samples = join(work, "samples");
mkdirSync(samples);
copyFileSync(join(repo, "backend/tests/fixtures/ecommerce/batch_b.csv"), join(samples, "Year_2010-2011.csv"));

const env = {
  ...process.env,
  INSIGHTFLOW_ENVIRONMENT: "demo",
  INSIGHTFLOW_DATA_DIR: join(work, "data"),
  INSIGHTFLOW_DATABASE_URL: `sqlite:///${join(work, "meta.sqlite3").replaceAll("\\", "/")}`,
  INSIGHTFLOW_SAMPLE_DIR: samples,
  INSIGHTFLOW_FRONTEND_DIST: join(repo, "frontend/dist"),
};
const child = spawn(
  "uv",
  ["run", "uvicorn", "insightflow.api.app:create_app", "--factory", "--host", "127.0.0.1", "--port", "8010"],
  { cwd: repo, env, stdio: "inherit", shell: process.platform === "win32" },
);
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
child.on("exit", (code) => process.exit(code ?? 0));
