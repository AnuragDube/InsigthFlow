# InsightFlow engineering instructions

Read [project status](docs/STATUS.md), [project rules](CLAUDE.md), the relevant
[ADRs](docs/decisions/README.md), and the active milestone before making changes. Check the current
branch, working tree, and upstream history. Preserve existing working code and user edits. Work on
a topic branch, keep commits small, and obtain owner approval before moving to the next phase,
deploying externally, spending money, changing credential requirements, or taking destructive actions.

## Product and architecture

- Keep the standard workflow usable on Windows 11 with Python 3.12, uv, and Node 22 for the UI.
  Use local SQLite, DuckDB and Parquet. Keep additional expenditure at ₹0. The standard workflow
  needs no Docker, JVM, Spark, local model downloads, or managed services.
- Preserve the modular monolith and existing service boundaries. Scope reads, writes, and storage
  paths by organization and dataset. Derive organization context from trusted server state or the
  authenticated principal. Document significant architecture decisions in an ADR.
- Keep Bronze immutable, rebuild Silver and Gold deterministically, and publish Gold only after
  blocking quality gates pass. Keep prior publication available when a new run fails. Use the
  metric registry as the single source for metric definitions.
- Keep the unauthenticated demo on loopback. Treat uploads and model output as untrusted. Use
  bounded input and query execution, parameter binding, and the read-only locked Gold reader.
  Any future generated SQL requires validation and execution limits before use. Keep secrets in
  environment settings and use synthetic fixtures in automated tests.
- Keep the dashboard compact and accessible. Show units, periods, publication provenance, and
  actionable loading, empty, and error states. Preserve the existing visual system.

## Validation and handoff

- At the root, run `uv sync --frozen`, `uv run --frozen ruff check .`,
  `uv run --frozen ruff format --check .`, `uv run --frozen mypy`, and `uv run --frozen pytest`.
- For frontend changes, run `npm ci`, `npm run typecheck`, `npm test`, and `npm run build` in
  `frontend/`. Run the existing Playwright suite for integrated changes. Keep generated build output
  out of commits. Review diffs for changes to the currently tracked TypeScript build metadata.
- Use focused regression coverage for changes in behavior. Report the commit, runtime, exact
  outcomes, and any skipped or blocked checks. Keep historical benchmarks distinct from fresh
  measurements. Update `docs/STATUS.md` at milestone boundaries with evidence, decisions, and
  blockers. Include a short code walkthrough and likely interview questions in milestone reports.
