# M1 Data Foundation (Phases 2 + 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tested FastAPI backend that ingests e-commerce CSV batches into immutable Bronze, builds Silver (with quarantine and the multiplicity rule) and a materialized Gold star schema with quality gates, and publishes runs transactionally — demonstrated on the real UCI Online Retail II data with measured timings.

**Architecture:** Modular monolith (`backend/src/insightflow`). Metadata in SQLite via SQLAlchemy 2 + Alembic; analytical data as Parquet + per-run `gold.duckdb` under `data/orgs/{org_id}/`. Transformations are SQL files in the e-commerce domain pack, executed by a small runner on DuckDB.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2, Alembic, DuckDB 2.0.x, PyYAML, python-multipart, pytest, ruff, mypy. Dev-only: openpyxl (sample conversion).

**Spec:** `docs/ARCHITECTURE.md`, `docs/DATA_ARCHITECTURE.md`, `docs/SECURITY.md` (§1a, §11), `docs/decisions/0017-batch-semantics-and-reruns.md`, data profile in Task 11.

## Global Constraints
- Python `>=3.12`; all deps pinned via `uv.lock`; no Docker/Java/Spark; must run on Windows (use `pathlib`, explicit `encoding="utf-8"`, no POSIX-only calls).
- Every metadata query is org-scoped through an `OrgContext`; no repository method without it.
- Storage paths are built only from UUIDs (org, data source, ingestion, run) — never from user-supplied names.
- Bronze is never modified after write. A failed/blocked run never changes `published_run_id`.
- Errors to clients: RFC 9457 `application/problem+json` with `correlation_id`; no stack traces.
- Mutating HTTP requests require header `X-InsightFlow-Client: web`; TrustedHost allows `localhost`, `127.0.0.1`, `testserver`.
- Tests never use the network. The real UCI dataset is never committed.
- Monetary columns `DECIMAL(12,3)` (profile found 3-decimal prices); quantities `INTEGER`; timestamps naive, interpreted as Europe/London wall time.

## Review Focus
1. **Overlapping batches** (the two UCI sheets share 22,523 lines): Silver must keep `max(k,m)` copies, not `k+m` — test in Task 5 with a fixture line present in both batches, and twice within one batch.
2. **Re-uploading the same file** must return the existing ingestion (200, same id), not create a batch — test in Task 4 and Task 10.
3. **A file with wrong headers or not CSV** must be rejected with a 422 problem naming the missing columns, and nothing written to Bronze — test in Task 4.
4. **Pipeline failure mid-run** (e.g. a blocking quality gate) must leave the previously published Gold readable and unchanged — test in Task 8.
5. **Server restart during a run** must not leave a run stuck in `running`, and a pending `rerun_requested_at` must still be honoured — test in Task 8.

---

### Task 1: Project scaffold, settings, errors, health

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.env.example`, `backend/src/insightflow/__init__.py`, `core/{__init__,settings,logging,errors,ids}.py`, `api/{__init__,app,middleware,routers/__init__,routers/health}.py`, `backend/tests/conftest.py`, `backend/tests/unit/test_settings.py`, `backend/tests/integration/test_health_and_errors.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `Settings` (pydantic-settings, env prefix `INSIGHTFLOW_`): `data_dir: Path = Path("data")`, `database_url: str = "sqlite:///data/metadata.sqlite3"`, `demo_org_slug: str = "demo"`, `max_upload_mb: int = 200`, `cors_origins: list[str] = ["http://localhost:5173"]`, `environment: Literal["dev","test","demo"] = "dev"`. `get_settings() -> Settings` (lru_cache).
- `AppError(Exception)` with `status: int`, `type_slug: str`, `title: str`, `detail: str`; subclasses `NotFoundError(404,"not-found")`, `ConflictError(409,"conflict")`, `ValidationFailed(422,"validation-failed")`. Problem `type` = `/errors/{type_slug}`.
- `create_app(settings: Settings | None = None) -> FastAPI`. Middleware sets/echoes `X-Correlation-ID` (accepts incoming if matches `^[A-Za-z0-9-]{1,64}$`, else generates uuid4 hex).
- `new_id() -> uuid.UUID` (uuid7 if available in stdlib, else uuid4).

- [ ] Step 1: Tests: `GET /health` → 200 `{"status":"ok"}` with `X-Correlation-ID`; route raising `NotFoundError` → 404, content-type `application/problem+json`, body has `type,title,status,detail,correlation_id`; unhandled `RuntimeError("secret path /x")` → 500 body without "secret"; `POST` to any route without `X-InsightFlow-Client` → 403 problem `/errors/client-header-required`; Host `evil.com` → 400; settings read `INSIGHTFLOW_MAX_UPLOAD_MB=5`.
- [ ] Step 2: Run `uv run pytest backend/tests -q` → FAIL (imports missing).
- [ ] Step 3: Implement. `uv add fastapi uvicorn pydantic-settings sqlalchemy alembic duckdb pyyaml python-multipart`; `uv add --dev pytest httpx ruff mypy openpyxl`. Logging: stdlib JSON formatter (one line, keys `ts, level, logger, msg, correlation_id`). Readiness `GET /ready` checks DB `SELECT 1` and that `data_dir` is writable (wired in Task 2).
- [ ] Step 4: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy backend/src` → all pass.
- [ ] Step 5: CI workflow: ubuntu + windows matrix, `astral-sh/setup-uv`, `uv sync --frozen`, ruff, mypy, pytest. Commit `feat: scaffold backend with settings, problem+json errors and health`.

### Task 2: Metadata store, org-scoped repositories, demo org

**Files:**
- Create: `metadata/{__init__,db,models,repositories,bootstrap}.py`, `core/context.py`, `backend/migrations/` (Alembic env + `0001_initial.py`), `alembic.ini`, tests `unit/test_repositories.py`, `integration/test_migrations.py`

**Interfaces:**
- `OrgContext(org_id: UUID)` frozen dataclass.
- `make_engine(url: str) -> Engine` (SQLite: `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000` on connect). `session_scope(engine) -> ContextManager[Session]` (commit/rollback).
- Models (M1 subset of DATA_ARCHITECTURE §7, same columns/constraints, SQLAlchemy portable types; `Uuid`, `JSON`): `Organization, DataSource (incl. published_run_id, rerun_requested_at), Ingestion (incl. is_active), PipelineRun, PipelineRunInput, PipelineStageRun, QualityResult, AuditEvent`. Partial unique indexes `uq_one_active_run` (status in queued,running) and `uq_ingestion_bytes` (status='stored') via `sqlite_where`/`postgresql_where`.
- Repositories (each method's first param `ctx: OrgContext`): `DataSourceRepo.create(ctx, name, domain, kind, contract_version) -> DataSource`, `.get(ctx, id) -> DataSource` (raises `NotFoundError`), `.list(ctx)`, `IngestionRepo.find_stored_by_sha(ctx, source_id, sha256)`, `.add(...)`, `.list_active(ctx, source_id)`, `.set_active(ctx, id, active)`, `RunRepo.create_queued(ctx, source_id, trigger) -> PipelineRun` (raises `ConflictError` on `uq_one_active_run`), `.get`, `.list(ctx, source_id)`, `AuditRepo.record(ctx, action, outcome, target_type, target_id, details)`.
- `ensure_demo_org(session, slug) -> OrgContext`.

- [ ] Step 1: Tests: org B cannot `get` org A's data source (NotFoundError); second `create_queued` for same source → ConflictError; a `succeeded` run doesn't block a new one; `uq_ingestion_bytes` allows a re-upload after `rejected`; `alembic upgrade head` on empty SQLite creates all tables and `alembic check` reports no drift vs models.
- [ ] Step 2: Run → FAIL. Step 3: Implement; Alembic migration autogenerated once then reviewed by hand. Step 4: pass + ruff/mypy. Step 5: Commit `feat: org-scoped metadata models, repositories and migrations`.

### Task 3: E-commerce domain pack and golden fixtures

**Files:**
- Create: `backend/src/insightflow/domains/ecommerce/{contract.yaml, rules.yaml, quality.yaml}`, `domains/loader.py`, `backend/tests/fixtures/ecommerce/{batch_a.csv, batch_b.csv, bad_headers.csv, expected.yaml, README.md}`, test `unit/test_domain_pack.py`

**Interfaces:**
- `DomainPack` (dataclass) with `required_columns: list[str]`, `column_map: dict[str,str]` (source → silver name), `adjustment_codes: list[str]`, `adjustment_code_patterns: list[str]` (SQL LIKE), `quality_rules: list[QualityRule]`, `models_dir: Path`. `load_domain_pack(name: str) -> DomainPack`.
- contract: `Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID, Country` → `invoice_no, stock_code, description, quantity, unit_price, invoice_ts, customer_id, country`.
- rules: adjustment codes `POST, DOT, M, C2, D, S, B, BANK CHARGES, ADJUST, AMAZONFEE, PADS, CRUK` (upper-cased compare) + patterns `GIFT_%`, `TEST%`.
- Fixtures (hand-built, ~25 lines each) must include: normal sales; a line in both batches; a line twice in batch A and once in B; a `C` cancellation; a non-C negative-quantity write-off; an `A` bad-debt line with negative price; zero price; POST adjustment; missing customer; unparseable date; non-numeric quantity; 3-decimal price; a customer in two countries. `expected.yaml` holds hand-computed values: silver row count, quarantined count, cross-batch overlap removed, within-batch repeats, `fact_sales` rows, gross revenue, returns value, orders, distinct known customers. README shows the arithmetic.

- [ ] Steps: test loader returns the contract/codes above; commit `feat: e-commerce domain pack and golden fixtures`.

### Task 4: Ingestion to Bronze

**Files:** Create `ingestion/{__init__,service,storage}.py`, `warehouse/paths.py`; test `unit/test_ingestion.py`

**Interfaces:**
- `OrgPaths(data_dir, org_id)` with `bronze_dir(source_id, ingest_id) -> Path`, `silver_dir(source_id, run_id)`, `quarantine_dir(source_id, run_id)`, `gold_dir(source_id, run_id)`, `gold_db(source_id, run_id) -> Path`.
- `ingest_file(ctx, session, settings, source_id: UUID, src: BinaryIO, original_name: str) -> IngestResult(ingestion: Ingestion, created: bool)`.
  Streams to a temp file in the org's bronze area (size cap → `ValidationFailed` "file too large"), SHA-256 while streaming, header check (UTF-8, comma CSV; missing columns listed in detail), existing stored sha → `created=False`. Writes `raw.csv`, `data.parquet` via DuckDB: `CREATE TABLE t AS SELECT * FROM read_csv(path, all_varchar=true, header=true)` (insertion order preserved), then export `SELECT '<ingest_id>' AS _ingest_id, rowid + 1 AS _row_number, * FROM t` — `rowid` follows insertion order, unlike `row_number() OVER ()`; a test asserts `_row_number` matches the CSV line order. Plus `_manifest.json`. Records audit `dataset.upload`.

- [ ] Steps: tests for success (files exist, row_count, sha), idempotent re-upload (`created=False`, no new dir), bad headers (422 detail lists `Country`, nothing in Bronze, ingestion row `rejected`), size cap; implement; commit `feat: immutable Bronze ingestion with idempotent batches`.

### Task 5: Silver build (typing, flags, multiplicity rule, quarantine)

**Files:** Create `domains/ecommerce/models/silver/order_lines.sql`, `pipeline/sql_runner.py`, test `unit/test_silver.py`

**Interfaces:**
- `render_sql(path: Path, params: dict[str, str]) -> str` (only `{{ name }}` substitution of trusted, runner-generated values such as quoted path lists; reject unknown placeholders).
- Silver SQL (DuckDB) inputs: `bronze` = union of active batches' `data.parquet`. Steps: typed CTE with `try_cast`; rows with any failed cast → quarantine with `reason_code` in (`bad_timestamp`,`bad_quantity`,`bad_price`); multiplicity: `occurrence_no = row_number() over (partition by _ingest_id, <all business cols> order by _row_number)`, then keep one row per (`<business cols>`, `occurrence_no`) choosing min(`_ingest_id` order by ingestion created_at, `_row_number`) → yields `max(k,m)`; flags `is_cancellation` (invoice starts `C`), `is_bad_debt` (starts `A`), `is_adjustment` (code list/patterns), `is_writeoff` (quantity < 0 and not cancellation); normalized `stock_code=upper(trim())`, `country=trim()`, `customer_id` NULL when empty.
- `build_silver(conn, inputs: list[BatchInput], out_dir: Path, pack: DomainPack) -> SilverStats(rows_in, rows_out, quarantined, overlap_removed, within_batch_repeats)` writing `order_lines.parquet` and `rejected.parquet`.

- [ ] Steps: tests assert every `expected.yaml` silver number on fixtures and reconciliation `rows_in = rows_out + quarantined + overlap_removed`; implement; commit `feat: Silver build with quarantine and multiplicity rule`.

### Task 6: Gold build (materialized star schema)

**Files:** Create `domains/ecommerce/models/gold/{dim_date,dim_customer,dim_product,fact_sales,fact_returns,agg_daily_sales}.sql`, `pipeline/gold.py`, test `unit/test_gold.py`

**Interfaces:**
- `build_gold(silver_dir: Path, gold_dir: Path, pack: DomainPack) -> GoldStats(table_rows: dict[str,int])`: creates `gold_dir/gold.duckdb` with tables (materialized, not views) and exports each table to `gold_dir/{table}.parquet`.
- `fact_sales`: lines not cancellation/bad-debt/adjustment/writeoff, quantity > 0, unit_price > 0; `revenue = quantity * unit_price` DECIMAL(18,3); `customer_key = coalesce(customer_id,'UNKNOWN')`; `invoice_date = cast(invoice_ts as date)`; keeps `country`.
- `fact_returns`: cancellation lines excluding adjustment codes; `return_value = abs(quantity) * unit_price`.
- `dim_customer` incl. `'UNKNOWN'` member; `primary_country` = most frequent, tie → latest `invoice_ts`, tie → alphabetical. `dim_product`: latest non-null description by `invoice_ts` then alphabetical. `dim_date`: min..max invoice date continuous. `agg_daily_sales`: date × country: revenue, orders, units.

- [ ] Steps: tests against `expected.yaml` (fact rows, gross revenue, returns value, orders, customers), every fact row joins dims, building twice yields identical sorted table contents; implement; commit `feat: materialized Gold star schema`.

### Task 7: Quality rules and gates

**Files:** Create `quality/{__init__,engine}.py`, update `domains/ecommerce/quality.yaml`; test `unit/test_quality.py`

**Interfaces:**
- `QualityRule(id, stage: Literal["silver","gold"], severity: Literal["blocking","warning"], sql: str, op: Literal["<=",">=","=="], threshold: float, description)`. Rule SQL returns one numeric `observed` value, evaluated against tables `order_lines`, `rejected`, Gold tables, and a `stats` table of `SilverStats`.
- `evaluate(conn, rules, stage) -> list[RuleResult(rule_id, stage, severity, passed, observed, threshold)]`; `gate_passed(results) -> bool` (all blocking passed).
- Rules (DATA_ARCHITECTURE §3): quarantine ratio ≤ 0.01 (blocking); reconciliation difference == 0 (blocking); overlap removed (warning, threshold large, reported); within-batch repeats (warning); customer null ratio ≤ 0.30 (warning); Gold null keys == 0 (blocking); orphan facts == 0 (blocking); Gold revenue vs Silver eligible revenue abs diff ≤ 0.01 (blocking).

- [ ] Steps: tests: fixtures pass all blocking; a fixture variant with 20% bad dates fails `quarantine_ratio`; implement; commit `feat: declarative data quality rules and gates`.

### Task 8: Pipeline runner, publish, recovery, re-runs

**Files:** Create `pipeline/{__init__,runner,service}.py`; test `integration/test_pipeline_runner.py`

**Interfaces:**
- `start_run(ctx, session, source_id, trigger) -> PipelineRun | None` (returns None and sets `rerun_requested_at` if a run is active).
- `execute_run(ctx, engine, settings, run_id) -> PipelineRun`: stages `silver → silver_quality → gold → gold_quality → publish`, each recorded in `pipeline_stage_runs` with timings and row counts; quality results persisted; publish = one transaction setting run `succeeded`, `finished_at`, `data_sources.published_run_id`; then if `rerun_requested_at` set → clear it and create+execute a new run (loop, not recursion). Failures → `failed` with sanitized `error_code`; gate failure → `blocked_by_quality`. Records `pipeline_run_inputs`.
- `recover_interrupted_runs(engine) -> int`: on startup mark `queued/running` as `failed` (`error_code="interrupted"`), then start runs for sources with `rerun_requested_at`.
- `prune_old_runs(ctx, session, settings, source_id, keep: int = 2)`: delete run dirs not published and not in the last `keep`; errors logged, never raised.

- [ ] Steps: tests (Review Focus 4, 5): happy path publishes; second run with identical inputs → identical Gold sorted contents; forcing a blocking failure keeps old `published_run_id` and its Gold readable; simulated crash (run left `running`) → recovery marks failed and honours rerun marker; upload during active run → marker set, one follow-up run after; implement; commit `feat: pipeline runner with transactional publish and recovery`.

### Task 9: Sandboxed Gold reader

**Files:** Create `warehouse/{__init__,engine}.py`; test `security/test_gold_sandbox.py`

**Interfaces:**
- `SANDBOX_CONFIG: dict` = `{"enable_external_access": False, "autoinstall_known_extensions": False, "autoload_known_extensions": False, "lock_configuration": True}` plus `memory_limit` and `threads` (from settings) set at connect.
- `open_gold(ctx, session, settings, source_id) -> duckdb.DuckDBPyConnection` (resolves `published_run_id`; raises `ConflictError("no-published-data")` if none; read_only). The **only** way any code reads Gold.

- [ ] Steps: tests: query `fact_sales` works; `read_csv`, `COPY`, `ATTACH`, `INSTALL`, `SET enable_external_access=true` all raise; opening twice in-process works; implement; commit `feat: sandboxed read-only Gold connection factory`.

### Task 10: HTTP API for datasets, uploads, runs, quality

**Files:** Create `api/routers/{datasets,runs}.py`, `api/deps.py`, `api/schemas.py`; modify `api/app.py` (lifespan: migrations check, demo org, recovery sweep); test `integration/test_api_datasets.py`

**Interfaces (ARCHITECTURE §5):** `GET/POST /api/v1/datasets`; `POST /api/v1/datasets/{id}/uploads` (multipart `file`) → 201 new / 200 existing, plus `run_id` or `rerun_queued: true`; `POST /api/v1/datasets/{id}/load-sample` (reads CSVs from `settings.sample_dir`, default `data/samples/uci`; 404 problem with fetch instructions if absent); `PATCH /api/v1/datasets/{id}/ingestions/{ingestion_id}` `{is_active}`; `POST /api/v1/datasets/{id}/pipeline-runs` → 202; `GET /api/v1/pipeline-runs?dataset_id=`; `GET /api/v1/pipeline-runs/{id}` (stages); `GET /api/v1/pipeline-runs/{id}/quality`. Runs execute via FastAPI `BackgroundTasks`. Org from `get_org_context` dependency (demo org) — never from the request.

- [ ] Steps: tests (TestClient, temp data dir) for upload → run succeeds → quality report; duplicate upload returns 200 same id; bad headers 422; unknown dataset id 404 problem; missing client header 403; implement; commit `feat: dataset, upload and pipeline-run API`.

### Task 11: Real data run, docs and status

**Files:** Create `scripts/fetch_sample_data.py`, `docs/DATA_PROFILE.md`, `docs/evals/` (none yet); modify `README.md` (Windows quickstart), `docs/STATUS.md`, `docs/DATA_ARCHITECTURE.md` (DECIMAL(12,3), flag categories from profile).

- [ ] Step 1: `scripts/fetch_sample_data.py --dest data/samples/uci`: downloads the zip from `https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip`, verifies size, extracts the xlsx, converts each sheet to CSV with openpyxl (read-only mode), prints sha256s. Idempotent (skips if CSVs exist).
- [ ] Step 2: Run end-to-end on the two sheets via the API (`load-sample`), record wall-clock per stage, row counts, Gold DB size, quality results, hardware (`nproc`, RAM) in `DATA_PROFILE.md`. Verify overlap removed = 22,523.
- [ ] Step 3: Independent data-correctness review (subagent) of Tasks 5–8; fix verified issues.
- [ ] Step 4: `/security-review` on the branch diff; fix or record findings.
- [ ] Step 5: Update README/STATUS; commit; create bundle.
