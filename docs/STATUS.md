# InsightFlow project status

Updated 25 November 2026 (IST). Interview on Friday, 27 November 2026.

**M1 data foundation and M2 metrics dashboard are implemented.** The November 27 priority is a
rehearsed, offline-capable M2 demo on Windows 11. The next engineering milestone is an M2 reliability
pass, followed by an offline-first NL-to-SQL milestone if approved. Keep the current application
local and use public or synthetic demo data.

## Branch and design review

| Ref | Evidence |
|---|---|
| Remote default and `m1-data-foundation` | `b796cb4`, including the M1 publication note |
| `m2-dashboard` | `be8a16e`, eight commits after the shared base `950e869`. Adds metrics, API, SPA and CI coverage |
| Audit | `audit/lead-engineering-2026-11-25`, based on M2. The M1-only publication note was reconciled here |

Remote branch discovery returned those two branches and no `main` branch. The selected starting
checkout was local `work` at the M1 tip. Phase 1 was approved on 24 November. The architecture,
data and security designs, roadmap, CLAUDE.md and ADRs 0001–0017 were reviewed. The modular monolith,
SQLite metadata, DuckDB/Parquet analytics, and React/Vite UI remain appropriate at the present
scale. ADR-0016 still leaves the authentication approach open. See the [ADR index](decisions/README.md)
and [prior roadmap](ROADMAP.md).

## Independent verification

| Check | M1 `b796cb4` | M2 `be8a16e` |
|---|---|---|
| Linux, Python 3.12.14, pytest 9.2.0, frozen dependencies | 94 passed in 14.16 s | 119 passed in 20.48 s |
| Ruff lint | Passed | Passed |
| Ruff format | 64 already formatted | 73 already formatted |
| mypy | Passed, 49 source files | Passed, 55 source files |
| Frontend, Linux with Node 24.22.3 | No frontend | TypeScript passed. Vitest 13 passed across 3 files. Vite build passed, with a 686.17 kB minified JS chunk warning |
| Playwright | No frontend | 2 passed in 8.3 s (desktop and phone). The proxy blocked the pinned Chrome download. A temporary configuration used installed Chromium 156.0.8078.79 |

The Windows CI matrix is configured for Python. Windows 11 execution, Node 22 parity, hosted
CI results, and PostgreSQL runtime validation were outside this Linux run. The existing PostgreSQL
16 migration spike and earlier UCI results are recorded in [spikes](spikes/README.md) and
[Data Profile](DATA_PROFILE.md). A fresh Linux M2 run downloaded and verified the UCI archive, processed 1,067,371
Silver input rows, published after all 9 checks passed, and returned 10 dashboard KPIs with the
published run ID.

## Capability inventory

| State | Capabilities and limits |
|---|---|
| Implemented | FastAPI liveness/readiness, typed settings, correlated problem responses, SQLite/Alembic, basic system audit events, e-commerce CSV ingestion, batch toggles, run and quality APIs. |
| Implemented | Bronze raw CSV, all-text Parquet, hash and manifest. Silver typing, quarantine, adjustments and overlap handling. Gold sales/returns facts, dimensions and daily aggregates. Gated publication, run inputs and stage records, retry coalescing, startup recovery and pruning. |
| Implemented on M2 | Ten metric definitions, parameterized dashboard/series/breakdown queries, React Overview and Data pages, same-origin SPA with CSP, keyboard-accessible controls designed into the UI. Desktop/phone projects cover the fixture-backed publish path. |
| Partial | Organization-scoped repositories and composite keys operate under one demo org. PostgreSQL compatibility has spike evidence. Pipeline execution and recovery assume one server process. Basic audit trail lacks authenticated actor identity. |
| Missing | Auth and RBAC, enforced public read-only demo mode, PostgreSQL application CI and tenant RLS, scheduled jobs and operational alerts, NL-to-SQL, ADR-0009’s Gold metric views and provider abstraction, RAG/document citations, connectors, ML, billing and commercial operations. |

## Pipeline and quality assessment

1. Bronze streams and hashes input, saves immutable files under server-generated IDs and
   deduplicates identical uploads per dataset. A stored batch records durable pending work.
2. Silver uses explicit typing and quarantine, preserving within-batch multiplicity and removing
   overlap across batches via maximum multiplicity. Hand-computed fixtures cover returns,
   adjustments, duplicates, missing customers and precision.
3. Gold materializes trusted SQL into per-run DuckDB and Parquet. Nine declarative checks
   comprise six blocking rules and three warnings. Checks cover quarantine, conservation of
   rows, key completeness, dimensional links and revenue reconciliation. Failed gates preserve
   the prior `published_run_id`.
4. SQLite publishes the pointer and records completion in one transaction. Artifacts live on the
   filesystem, so crash recovery and retention remain operational concerns. Run inputs are
   snapshotted when execution begins. The M2 dashboard reads Gold via the locked, read-only adapter.

## Risks and debt in priority order

| Priority | Finding | Before closing it |
|---|---|---|
| Release blocker | All HTTP calls resolve to the demo org. The custom mutation header, explicit CORS, trusted hosts, body cap and CSP harden a local demo. ADR-0016 auth/RBAC and the designed public read-only mode are absent. | Loopback only. Require authentication, authorization and cross-org HTTP tests before handling customer data or exposing a service. |
| High | Dashboard freshness and quality resolve a published run, then `open_gold` reads the pointer again in another transaction. Code review found a possible mismatch if a publish lands between reads. Missing Gold artifacts currently reach the generic 500 handler. | Pin metadata and Gold to one run for the duration of a request. Test publication overlap and explicit missing-artifact behavior. |
| High before shared deployment | Analytics accepts arbitrary date spans. The series materializes the requested date spine, and endpoint-level deadlines and concurrency budgets are absent. Uploads cap the body and spool size, but header reads can consume the whole allowed body, and cumulative storage is unbounded. | Bound analytics ranges and work, cap header length, add storage quotas and define safe retention before sharing. |
| High before parallel workers | Startup recovery treats all active runs as interrupted. Artifact pruning and local storage assume single-process ownership. A process killed before the ingest transaction commits can leave unreferenced files. | Retain one process for now. Test reconciliation and restore, and add durable claims only when a second worker is necessary. |
| Medium | Revenue reconciliation shares Silver eligibility flags with Gold. The overlap warning uses a nonnegative threshold and serves as telemetry. Bronze manifest lacks receipt time and row lineage lacks file/time fields. Country names are trim-only. | Add independent control totals and lineage. Preserve raw values and confirm normalization policy. |
| Medium | Repeated sample loads can enqueue an unchanged rebuild. Date parsing quarantines ambiguous Excel-style values. Re-uploading an inactive batch keeps it inactive. | Confirm intended UX, document it and cover approved behavior with regressions. |
| Medium | TypeScript build metadata is tracked. The bundle exceeds Vite's default chunk threshold. The threat model describes future security controls alongside shipped controls, and dependency audit gates are absent from CI. | Ignore generated metadata in a follow-up, measure client startup, and align the security inventory with evidence. Add dependency checks before a beta. |

The existing Gold sandbox tests passed as part of both backend suites. They cover the reader
boundary. Generated-SQL validation, query isolation from authenticated tenants, vendor data handling
and rate limits remain future work. This audit used code review and the repository suites.

## November 27 interview priorities

1. **25 November, P0:** Freeze the M2 demo scope. Keep scope changes out of the
   demo path. Use the checked-in `batch_b.csv` fixture as the guaranteed offline fallback and retain
   the checksum-verified UCI dataset if local rehearsal confirms it.
2. **26 November, P0:** Rehearse the README workflow on Windows 11 with Python 3.12 and Node 22.
   Verify first load, publication, and the Overview and Data views. In a separate fixture dataset,
   publish `batch_b.csv`, then upload `batch_a.csv` and verify that the quality gate keeps the prior run. Prepare a screenshot or short local recording as fallback.
3. **27 November, P0:** Use a five-minute walkthrough. Load data, show run and quality results,
   move to the dashboard and explain a KPI's grain and provenance, then switch to the fixture dataset
   to demonstrate the blocked batch. Prepare answers about overlapping extracts, atomic publication, sandbox limits, and
   the trade-offs of SQLite metadata with DuckDB analytics.
4. **Hold until after the interview:** New AI features, RAG, deployment, infrastructure changes
   and UI redesign. Use any remaining time to rehearse.

### Recommended next engineering milestone

**M2 reliability and sign-off.** Complete the Windows rehearsal, pin dashboard reads to a
publication, handle missing artifacts explicitly, and add date-range limits with focused
regressions. Acceptance is a fixture-backed Windows run, matching dashboard and quality
provenance, and the current CI suite passing. Keep the existing Overview and Data UI.

## Commercial sequence after the interview

1. **Private pilot foundations.** Decide ADR-0016 and implement identity, RBAC, cross-org tests,
   PostgreSQL CI, quotas, audit identity, retention/deletion and a verified backup/restore
   procedure before accepting customer data. Keep deployments and costs subject to owner approval.
2. **M3, offline-first NL-to-SQL.** Validate demand before connecting a provider. Evaluate with a
   fake provider, result-based fixtures, an allowlisted read-only query interface and resource
   budgets. Keep a provider call optional until access, quota and data-handling terms are approved.
   Defer RAG unless user feedback supports document search.
3. **Pilot and iterate.** Measure repeat use and accuracy with invited users. Prioritize connectors,
   scheduling and monitoring using pilot evidence. Add shared storage or worker infrastructure
   when durability or throughput requirements justify them.
4. **Commercial launch after budget and readiness approval.** Require reliable storage, restore
   drills, tenant isolation assurance, privacy terms, dependency monitoring, incident handling and
   a supported provider plan before taking paid accounts.

### Offline rehearsal setup

After installing dependencies and building the frontend, point the sample loader at a folder
containing only the good fixture. Run from the repository root in PowerShell.

```powershell
$sampleDir = Join-Path ([System.IO.Path]::GetTempPath()) ("insightflow-demo-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $sampleDir | Out-Null
Copy-Item backend/tests/fixtures/ecommerce/batch_b.csv $sampleDir
$env:INSIGHTFLOW_SAMPLE_DIR = $sampleDir
$env:INSIGHTFLOW_DATA_DIR = Join-Path $sampleDir "data"
$db = (Join-Path $sampleDir "metadata.sqlite3").Replace([char]92, [char]47)
$env:INSIGHTFLOW_DATABASE_URL = "sqlite:///$db"
$env:INSIGHTFLOW_FRONTEND_DIST = "frontend/dist"
uv run --frozen uvicorn insightflow.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open the local dashboard and choose **Load sample data**. The browser test verified the equivalent
isolated flow on Linux, including **£75.75 gross revenue from 4 orders**. Windows execution of
these commands is part of rehearsal.

Use the [Windows PowerShell quickstart](../README.md#quickstart-windows-11-powershell). Application
checks use local fixtures and require no credentials. The previous cloud push limitation is
historical, and this audit is committed on its local topic branch.
