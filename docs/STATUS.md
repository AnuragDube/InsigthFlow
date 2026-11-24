# Project status — read this first when resuming

Last updated: 2026-11-24 19:32 UTC (Wed 25 Nov, 01:02 IST) · Updated by: Copilot

## Where we are
- **Phase 1 (architecture): approved 2026-11-24.**
- **M1 = Phases 2+3 "Data foundation": complete on branch `m1-data-foundation`** (94 tests).
  Published to GitHub at `AnuragDube/InsigthFlow`; Windows verification remains pending.
  Independent review: 0 critical; 3 important + 2 re-graded findings fixed with regression tests.
  `/security-review`: no findings.
- Next: **M2 = Phase 4** — metric registry + metrics API + React dashboard.
- Working title per handover: "Data Intelligence Platform"; `InsightFlow`/`insightflow` remain the
  repo and package identifiers.
- Interview: Fri 27 Nov 2026 (Associate Analyst). RAG is the first thing cut if time runs short.

## What works (evidence)
| Capability | Evidence |
|---|---|
| FastAPI app: settings, JSON logs, correlation ids, problem+json errors, `/health`, `/ready` | `backend/tests/integration/test_health_and_errors.py` |
| Localhost hardening: trusted hosts, client header on mutations, strict CORS, upload size pre-check | same + `test_api_datasets.py` |
| Metadata (SQLite; PostgreSQL-compatible) with org- and dataset-bound composite FKs, migrations | `test_repositories.py`, `test_migrations.py`; migration also applied to PostgreSQL 16 by hand (no drift) |
| Ingestion → immutable Bronze (raw + all-text Parquet + manifest), idempotent re-upload, rejections recorded | `test_ingestion.py` |
| Silver: typing, quarantine with reason codes, flags, multiplicity rule | `test_silver.py` vs hand-computed `fixtures/ecommerce/expected.yaml` |
| Gold star schema materialized in per-run `gold.duckdb` (+ Parquet) | `test_gold.py` |
| 9 declarative quality rules, blocking vs warning gates | `test_quality.py` |
| Runner: stages, transactional publish, blocked runs keep old Gold, coalesced re-runs, crash recovery, pruning | `test_pipeline_runner.py` |
| Sandboxed read-only Gold reader (11 escape attempts blocked) | `backend/tests/security/test_gold_sandbox.py` |
| HTTP API: datasets, uploads, load-sample, batch (de)activation, runs, quality | `test_api_datasets.py` |
| Real UCI run: 1,067,371 lines → published Gold in ≈3.2 s; overlap 22,523 removed; reruns identical | `docs/DATA_PROFILE.md` (Linux container) |
| **Not yet verified on the owner's Windows laptop** | everything above — CI includes a Windows job |

## Current task
M1 is published to GitHub. Next: plan M2 (Phase 4: metric registry, metrics API, React dashboard).

## Known minor issues (deferred from M1 review)
- Revenue reconciliation rule reuses Silver flags (not fully independent of fact eligibility).
- Bronze lacks `_source_file`/`_ingested_at` lineage columns; manifest lacks `received_at`.
- Country names only trimmed, not normalized.
- `load-sample` queues a run even when all files were already ingested.
- A deleted published Gold file surfaces as 500 instead of a problem response.
- CSV header read uses an unbounded `readline()` (bounded by the upload cap).
- Product decisions pending: Excel-style dates (`12/1/2010 8:26`) are quarantined; re-uploading a
  deactivated batch keeps it inactive.

## Owner decisions
- 2026-11-24: Owner delegated full technical ownership. Accepted defaults: Phase 1 architecture incl.
  React; ADR-0001…0017 Accepted (0016 auth decided at P1 start); ADR-0017 upload semantics; metric
  definitions as proposed; Phases 2+3 = one milestone; interview Fri 27 Nov, RAG first to cut.
- Still escalated to owner: spending, credentials, external deployment, destructive actions.

## Blockers / environment
- Cloud dev container cannot push to GitHub; M1 was published from the owner's Windows environment.
- Network: `archive.ics.uci.edu` allowed via the personal environment "InsigthFlow" (created
  2026-11-24). `api.groq.com` still blocked — requested with the key at Phase 5.
- Context7 MCP not connected; library behaviour verified by tests/spikes instead.

## How to run (Windows PowerShell)
```powershell
uv sync
uv run pytest
uv run python scripts/fetch_sample_data.py
uv run uvicorn insightflow.api.app:create_app --factory --host 127.0.0.1 --port 8000
```
In a second PowerShell window:
```powershell
$h = @{ "X-InsightFlow-Client" = "web" }
$ds = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/datasets -Headers $h `
      -ContentType "application/json" -Body '{"name":"UCI Online Retail II"}'
$run = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/datasets/$($ds.id)/load-sample" -Headers $h
Start-Sleep -Seconds 10
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/pipeline-runs/$($run.run_id)" | ConvertTo-Json -Depth 5
(Invoke-RestMethod "http://127.0.0.1:8000/api/v1/pipeline-runs/$($run.run_id)/quality").items | Format-Table
```

## Plans & ledgers
- M1 plan: `docs/superpowers/plans/2026-11-25-m1-data-foundation.md`
- Execution ledger (gitignored scratch): `.superpowers/sdd/2026-11-25-m1-data-foundation/progress.md`
