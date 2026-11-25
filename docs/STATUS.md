# InsightFlow project status

Updated 25 November 2026 (IST). Interview on Friday, 27 November 2026.

**M1 data foundation and M2 metrics dashboard are implemented.** The M2 reliability and demo
workflow passed Linux validation. The November 27 priority is a rehearsal on Windows 11. Keep the
current application local and use public or synthetic demo data.

**M3 offline foundation is implemented.** The Ask tab maps supported questions and metric names
to the existing registry. It shows the value, applied date range, published run, parameterized SQL,
and metric definition. Unsupported questions are declined. Use the date fields or an ISO date
range in the question. An opt-in Groq adapter passed mocked HTTP integration tests. Live provider
activation and broader natural-language interpretation remain open.

**M4 offline document search is implemented.** The Documents tab accepts UTF-8 TXT and Markdown,
returns matching excerpts with source line numbers, and supports removal. It runs locally with BM25
and returns an empty result when lexical evidence is insufficient.

**M5 private-pilot authorization is underway.** The app factory can accept a trusted
server-side identity resolver. The application looks up the role from a stored membership
keyed by workspace, verified issuer, and verified subject. Viewers may read, ask questions,
and search documents. Editors and owners may mutate datasets and documents. A local operator
can create a workspace, grant or change a role, and revoke membership. The default app remains
a localhost demo. The app supports opt-in browser sessions, signed RFC 9068 access tokens,
and a workspace sign-in screen using OAuth authorization code with PKCE. Integration tests
exercise the callback with a simulated provider and locally signed tokens. Selecting and
connecting a live provider, then verifying sign-in against that provider, remain open.

M5 Linux verification passed **152 backend tests in 25.34 s**, along with Ruff lint,
formatting, and mypy. The authorization test covers all seven mutation routes and
cross-organization access to published analysis and documents.

## Branch and design review

| Ref | Evidence |
|---|---|
| Remote default and `m1-data-foundation` | `55ec08c`, including merged M3 and M4 |
| `m2-dashboard` | `be8a16e`, eight commits after the shared base `950e869`. Adds metrics, API, SPA and CI coverage |
| Audit | `audit/lead-engineering-2026-11-25`, based on M2. The M1-only publication note was reconciled here |
| Reliability | `fix/m2-dashboard-reliability`, based on the audit branch |
| Demo workflow | `feat/m2-demo-workflow`, based on the reliability branch |
| M3 offline analytics | `feat/m3-offline-analytics`, based on the demo branch |
| M4 offline documents | `feat/m4-offline-documents`, based on the green M3 branch |
| M5 pilot authorization | `feat/m5-pilot-authorization`, based on the merged M4 baseline |
| M5 workspace memberships | `feat/m5-workspace-memberships`, based on merged authorization at `1951dba` |
| M5 browser sessions | `feat/m5-browser-sessions`, based on merged memberships at `4dc67c2` |
| M5 token verification | `feat/m5-token-verification`, based on merged browser sessions at `0d3052c` |
| M5 interactive sign-in | `feat/m5-interactive-sign-in`, based on merged token verification at `cba7bdf` |

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

The Windows CI matrix is configured for Python. The owner's Windows 11 rehearsal and PostgreSQL
runtime validation were outside this Linux run. The existing PostgreSQL
16 migration spike and earlier UCI results are recorded in [spikes](spikes/README.md) and
[Data Profile](DATA_PROFILE.md). A fresh Linux M2 run downloaded and verified the UCI archive, processed 1,067,371
Silver input rows, published after all 9 checks passed, and returned 10 dashboard KPIs with the
published run ID.

### Reliability branch verification

- `uv run --frozen pytest -o addopts='' -ra` collected and passed **123 tests in 21.55 s**.
  Ruff lint passed, all 74 Python files were formatted, and mypy checked 55 source files.
- `npm run typecheck`, `npm test` and `npm run build` passed on Node 24.22.3.
  Vitest passed **14 tests in 3 files**. The existing Vite chunk-size warning remains.
- `npm run e2e` with an ephemeral configuration for system Chromium 156.0.8078.79
  passed **2 tests in 5.8 s** across desktop and phone.
- The checksum-verified UCI sample was loaded into an isolated SQLite store through the
  current API. The new run published after all nine quality checks passed. The dashboard
  returned ten KPIs and identified that same run.

### Demo workflow branch verification

- Linux backend checks passed on Python 3.12.14. Ruff lint passed, all 74 files were formatted,
  mypy checked 55 source files, and pytest passed **123 tests in 20.18 s**.
- On Node 22.23.5, `npm ci`, `npm run typecheck`, `npm test`, and `npm run build` passed.
  Vitest passed **15 tests in 3 files**. Vite still reports its chunk-size warning.
- Playwright with system Chromium 156.0.8078.79 passed **4 tests in 18.4 s**. Both desktop and
  phone verified the offline sample, dataset creation, rebuild, and a blocked upload leaving
  the prior publication and dashboard totals intact.

### M3 offline verification

- The Groq adapter is injectable through the app factory. Its requests contain question text
  and the metric catalog. It handles abstention, malformed or oversized responses and rate-limit
  errors. The standard app remains offline. Live access, terms, rate limits and quality
  evaluation must be resolved before activation.
- Latest local checks passed: **143 backend tests in 25.89 s**, Ruff lint and format (77 files),
  mypy (57 source files), and **4 browser tests in 20.9 s** using Node 22 and system Chromium.
  GitHub Actions run 45562356067 reported a Windows-only JavaScript MIME mismatch in pytest
  (135 passed, 1 failed). The SPA now explicitly serves JavaScript as `text/javascript`.
  The local regression test simulates the Windows MIME mapping. All four checks passed in GitHub
  Actions run [45563919813](https://github.com/AnuragDube/InsigthFlow/actions/runs/45563919813),
  including Windows backend pytest.

- The validated provider interface is now in place. A provider receives metric descriptions and
  question text and can return a registered metric identifier. Dates are interpreted and
  validated by the server. The running application selects its offline provider by default.
- The follow-up evaluation checked all ten metrics, date-field equivalence, conflicting or invalid
  dates, and rejection of an unregistered metric from a stub provider. Linux checks passed with
  **136 backend tests in 27.09 s**, **15 frontend tests**, and **4 Playwright tests in 19.9 s**
  on system Chromium. Ruff, mypy, TypeScript and the build passed. The owner's Windows 11 rehearsal remains unverified.

- Linux Python 3.12.14. Ruff lint and format passed (74 files formatted), mypy passed
  (55 source files), and pytest passed **129 tests in 24.04 s**.
- Linux Node 22.23.5. TypeScript and Vite build passed with the existing chunk-size warning.
  Vitest passed **15 tests**. Playwright passed **4 tests in 19.8 s** using system Chromium
  156.0.8078.79. Desktop and phone checked the fixture answer, SQL evidence, and an unsupported
  question, alongside both dashboard and quality-gate flows.
- The question text selects a registry entry through whole-question matching. The compiler
  binds dates on the locked read-only Gold connection. Formula metrics show the SQL for their
  operands and the formula definition. Hosted inference, model-generated SQL, and live evaluation
  remain outside the verified scope.

### M4 offline document search

- Documents live in SQLite under an organization-scoped key. List, search, and removal use that
  organization scope. Uploads are limited to 64 KiB and each organization can hold 20 documents.
- Search chunks only the caller's documents and builds an in-memory index for the bounded corpus.
  It returns up to five literal excerpts with one-based line references. Retrieval uses lexical
  overlap and BM25 scoring. A larger evaluation set is still needed to measure relevance.
- Current scope is local demo data, under the same demo-organization context as analytics.
  Hosted answer generation, document ACLs, and durable index versions remain future work.
- Verified on Linux with Python 3.12.14 and Node 22.23.5. Pytest passed **151 tests in 25.11 s**.
  Vitest passed **15 tests**, and Playwright passed **6 tests in 20.0 s** on installed Chromium,
  including document upload, citation, and removal on desktop and phone. Lint, formatting,
  mypy, TypeScript, and the production build passed.

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
| Addressed on reliability branch | Dashboard freshness, quality and results share a run ID, including when a new publication arrives mid-request. Missing published Gold files return a safe 503. | Windows rehearsal remains open. |
| High before shared deployment | Analytics limits ranges to 3,660 days. Endpoint-level deadlines and concurrency budgets are absent. Uploads cap the body and spool size, but header reads can consume the whole allowed body, and cumulative storage is unbounded. | Bound query work, cap header length, add storage quotas and define safe retention before sharing. |
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

**M2 Windows sign-off.** Rehearse the fixture-backed flow on Windows 11 with Node 22 and Python
3.12, including a successful publish followed by a blocked fixture. The publication consistency,
missing artifact and range limit changes have passed the Linux quality gates. After the interview,
use the commercial sequence below to prioritize the next implementation.

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

Open the local dashboard and choose **Load sample data**. Then demonstrate the quality gate
without modifying the sample dataset:

1. In **Data**, choose **New dataset**, name it `Quality gate rehearsal`, and create it.
2. Upload `backend/tests/fixtures/ecommerce/batch_b.csv` and wait for **Published**. In **Overview**,
   confirm **£75.75 gross revenue from 4 orders**.
3. Upload `batch_a.csv` to the same rehearsal dataset. Show **Blocked by quality checks** and
   the failed quarantine-ratio check. Return to **Overview** and confirm the same headline.
4. If asked to recover, choose **Exclude batch_a.csv**. Excluding it queues a new run. To rebuild
   from the active uploads after a missing Gold file, use **Rebuild dashboard** in **Processing runs**.

The browser tests verify the fixture-backed publish, explicit rebuild, and blocked attempt on
desktop and phone. They compare the published run ID before and after the blocked upload.
Windows execution remains part of the rehearsal.

Use the [Windows PowerShell quickstart](../README.md#quickstart-windows-11-powershell). Application
checks use local fixtures and require no credentials. The audit, reliability and demo branches
are local.
