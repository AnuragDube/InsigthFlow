# InsightFlow — Data Architecture & Database Design

Status: Draft for approval (Phase 1) · Last updated: 2026-11-24

## 1. Two stores, two workloads (deliberately separate)

| | Application metadata | Analytical data |
|---|---|---|
| Holds | orgs, users, roles, data sources, ingestions, pipeline runs, quality results, documents/chunks, audit, LLM calls, model metadata | Bronze/Silver/Gold datasets |
| Workload | OLTP: small transactional reads/writes, constraints, concurrency | OLAP: scans/aggregations over millions of rows |
| Technology | SQLAlchemy → SQLite (local dev/tests) / PostgreSQL (deployed) | Parquet files + DuckDB |
| Isolation | `org_id` column on every tenant table, enforced in repositories; Postgres RLS later | Physical: one directory tree and one Gold DuckDB file per org |

Using DuckDB for metadata would be wrong (single writer, no row-level concurrency); using Postgres for
analytics would be slow and costly on free tiers. Keeping them apart is also what makes the analytical
engine replaceable.

## 2. How the technologies fit (and what we are *not* adding)

| Technology | Role | In P0? |
|---|---|---|
| **Parquet** | The physical format of Bronze (copy of raw), Silver and Gold tables. Engine-neutral. | Yes |
| **DuckDB** | Executes Silver/Gold SQL models and quality rules over Parquet; serves Gold to the API from a per-org DuckDB file in which Gold tables are **materialized** (see SECURITY §5 for why not views); sandboxed read-only connection for NL-to-SQL. | Yes |
| **PostgreSQL** | Application metadata only, in deployed environments. Never stores analytical facts. | Schema designed; SQLite used locally until P1 |
| **Delta Lake (delta-rs)** | Not in P0. Candidate for Silver/Gold when incremental MERGE or concurrent writers appear, and as the format of the Databricks implementation. See §5. | No |
| **PySpark (Databricks Free Edition)** | Second implementation of the same Silver/Gold logic for scale/interview demonstration, validated by parity tests on shared fixtures. Not on the primary dev path. | P1 |

Not adding: a separate warehouse (Snowflake/BigQuery), Iceberg, Kafka, Airflow, a vector DB. Each would
duplicate a role above with no P0 benefit.

## 3. Medallion design

Storage layout (local disk in P0; object storage prefix in P2 — same relative layout):
```
data/orgs/{org_id}/                                     # org_id and source_id are UUIDs — never user-supplied names
  bronze/{source_id}/ingest_id={uuid}/raw.csv           # original bytes, never modified
  bronze/{source_id}/ingest_id={uuid}/data.parquet      # all columns as VARCHAR + lineage columns
  bronze/{source_id}/ingest_id={uuid}/_manifest.json    # checksum, size, rows, received_at, contract version
  silver/{source_id}/run_id={uuid}/{table}.parquet      # one directory per pipeline run
  quarantine/{source_id}/run_id={uuid}/rejected.parquet # rows rejected in Silver + reason codes
  gold/{source_id}/run_id={uuid}/gold.duckdb            # Gold tables materialized for serving + NL-to-SQL
  gold/{source_id}/run_id={uuid}/{table}.parquet        # engine-neutral export of Gold (interop, Spark parity)
  rag/index/{version}/                                  # retrieval index (see ARCHITECTURE §6.4)
```
**Which run is published is recorded only in the metadata DB** (`data_sources.published_run_id`), never by
pointer files on disk. See §4.

### Bronze — immutable raw
- Exactly what was received (`raw.csv`) plus a Parquet copy with **every column as text** so that type errors
  are handled in Silver, not lost at ingestion.
- Lineage columns: `_ingest_id`, `_source_file`, `_row_number`, `_ingested_at`.
- Append-only. Re-uploading identical bytes (same SHA-256) is a no-op returning the existing ingestion.
- Retention: kept until org deletes the dataset (P2: retention policies).

### Silver — cleaned, validated, standardized (e-commerce pack)
`silver.order_lines` from all **active** Bronze ingestions of the data source (upload semantics: see §3a):
- Cast types (`quantity INTEGER`, `unit_price DECIMAL(12,3)` — the data has 3-decimal prices; more
  decimals are quarantined rather than rounded — `invoice_ts TIMESTAMP`), trim strings,
  normalize country names and stock codes (upper-case, trimmed).
- Flags: `is_cancellation` (invoice starts with `C`), `is_bad_debt` (starts with `A`), `is_writeoff`
  (negative quantity on a non-`C` invoice), `is_adjustment` (non-product stock codes such as
  postage/manual/bank charges/vouchers — list in `domains/ecommerce/rules.yaml`). Evidence: DATA_PROFILE.md.
- Combine batches with the **multiplicity rule** in §3a (overlapping batches don't double count; repeated
  lines inside one batch are kept). Surviving rows keep the lineage of the earliest batch/row → deterministic.
- Rows failing hard parsing (unparseable date, non-numeric quantity) go to **quarantine** with `reason_code`,
  not silently dropped.
- Missing `customer_id` is kept (valid sales) but flagged; customer-level metrics exclude them explicitly.

### 3a. Upload semantics (recommended — pending product-owner confirmation; ADR-0017)
- An upload **adds a batch** (an ingestion) to the data source; Silver is rebuilt from all *active* batches.
- A batch can be **deactivated** (excluded from future runs; Bronze bytes are kept for audit) — this is how a
  bad upload is undone. Re-uploading identical bytes returns the existing batch.
- **Multiplicity rule for combining batches.** A line's identity is the tuple of all its business columns
  (invoice, stock code, description, quantity, unit price, timestamp, customer, country). Each batch is
  treated as a *multiset*: if an identical line appears `k` times in batch A and `m` times in batch B, Silver
  keeps **`max(k, m)`** copies — not `k + m` (overlapping exports would double count) and not `1` (a
  legitimate repeated line inside one export would be lost). Copies beyond the maximum are counted as
  "cross-batch overlap removed" in the quality report.
- Exact repeats **within** a batch are kept and reported as a warning metric: the source data cannot
  distinguish a genuine repeated purchase line from an export duplicate. Changing this to "remove" later is
  a one-line rule change plus a golden-test update.
- **Upload during an active run:** the batch is stored and the data source gets a durable
  `rerun_requested_at` marker (same transaction). When the active run finishes, the runner clears the marker
  and starts a new run in one transaction; the startup recovery sweep also honours a leftover marker.
  At most one run is ever queued/running per data source (`uq_one_active_run` unchanged), several uploads
  during one run coalesce into one follow-up run, and no stored batch can be left unprocessed.

### 3a-ii. Which dataset a request uses
Metric, dashboard and NL-to-SQL endpoints take an explicit `dataset_id`. The UI shows a dataset selector that
defaults to the most recently published dataset. If an org has no published dataset, analytics endpoints
return a clear `409 no-published-data` problem, never an empty success.

### 3b. Time
Source timestamps have no time zone (UK retailer). They are stored as naive timestamps and interpreted as
`Europe/London` wall-clock time; date filters operate on the calendar date in that time. No conversion in P0.

### Gold — business-ready
| Table | Grain | Notes |
|---|---|---|
| `dim_date` | day | calendar attributes |
| `dim_customer` | customer | first/last order date, primary country (most frequent; tie → most recent), order count, lifetime revenue. Includes one **unknown-customer member** (`customer_key = 'UNKNOWN'`) so that every fact row joins to a dimension even when the source has no customer id (standard Kimball practice) |
| `dim_product` | stock code | latest description (deterministic tie-break), first seen |
| `fact_sales` | invoice line (non-cancelled, non-adjustment, quantity > 0, price > 0) | `revenue = quantity * unit_price`; carries the line's `country` (country is a property of the order line in this data, not of the customer) |
| `fact_returns` | cancelled lines | for return-rate metrics |
| `agg_daily_sales` | day × country | pre-aggregated for the dashboard |
| `metric_*` | per metric, monthly grain | **views inside `gold.duckdb` over the materialized tables above** (no file access) — canonical definitions exposed to NL-to-SQL |

### Metric registry (deterministic definitions)
`domains/ecommerce/metrics.yaml`, e.g.:
```yaml
- name: gross_revenue
  label: Gross revenue
  unit: GBP
  sql: SUM(revenue)
  source: fact_sales
  time_column: invoice_date
  dimensions: [country, product]
  description: Sum of quantity × unit price over product lines that are not cancellations or adjustments, with quantity > 0 and price > 0.
```
**Proposed P0 definitions — pending product-owner approval.** Rules common to all metrics:
- Date range: `from` and `to` are **inclusive calendar dates** in dataset local time (§3b), implemented as
  `invoice_date >= :from AND invoice_date < :to + 1 day`.
- Every ratio uses `NULLIF(denominator, 0)` → a period with no orders returns `null` ("no data"), never 0 or an error.
- Customer-level metrics exclude the unknown-customer member and state this in their description.
- Sign conventions are **verified against the real file in Phase 3** before these are finalized (expected:
  cancellation lines carry negative quantity, hence `ABS` below).
| Metric | Definition |
|---|---|
| `gross_revenue` | `SUM(quantity × unit_price)` over `fact_sales` |
| `returns_value` | `SUM(ABS(quantity) × unit_price)` over `fact_returns` (cancellation lines) |
| `net_revenue` | `gross_revenue − returns_value` |
| `orders` | distinct invoices in `fact_sales` (cancellation invoices excluded) |
| `average_order_value` | `gross_revenue / orders` |
| `units_sold` | `SUM(quantity)` over `fact_sales` |
| `active_customers` | distinct known `customer_id` with ≥ 1 order in the range |
| `new_customers` | active customers whose first-ever order falls in the range |
| `repeat_customer_rate` | of active customers, share with ≥ 2 orders **in the range** |
| `return_rate_value` | `returns_value / gross_revenue` — a **value-based** rate. A count-based rate (`returned lines / sold lines`) is a different metric and is not in P0 |
| breakdowns | gross revenue by country, top products by gross revenue |

Customer-level metrics exclude lines with no `customer_id` and say so in their description.
Golden tests compute each metric by hand on a ~60-row fixture and assert exact equality.

**Currency caveat:** the UCI dataset is in GBP. Multi-currency is a P2 concern (would need FX tables);
P0 labels units explicitly and does not convert.

### Data quality rules (`quality.yaml`)
Two levels, never mixed: **row-level** problems send individual rows to quarantine; **run-level** rules
decide whether the run may be published.

| Rule | Stage | Level | Severity |
|---|---|---|---|
| Required columns present | ingestion (contract) | file | reject upload |
| Unparseable date / non-numeric quantity or price | Silver | row → quarantine | — |
| Quarantined rows ≤ 1% of input | Silver | run | blocking |
| Row reconciliation: bronze = silver + quarantined + duplicates removed | Silver | run | blocking |
| Cross-batch duplicates removed (count) | Silver | run | warning (reported) |
| Within-batch exact duplicates (count) | Silver | run | warning (reported) |
| `customer_id` null ratio ≤ 30% (UCI is known to have many missing ids) | Silver | run | warning |
| No null keys in facts/dimensions; every fact joins to its dimensions (missing customers join to the unknown member) | Gold | run | blocking |
| Gold gross revenue = Silver eligible revenue (± 0.01) | Gold | run | blocking |

Thresholds are configuration, reviewed when real data is profiled in Phase 3 (not guessed as final now).

## 4. Idempotency, atomic publish and reproducibility
- Each run writes only into its own new `run_id={uuid}` directories; nothing reads them until published.
- **Publish = one metadata-DB transaction** that sets `pipeline_runs.status = 'succeeded'` *and*
  `data_sources.published_run_id = run_id`. Readers resolve the Gold DB path from `published_run_id`.
  This avoids file-pointer swaps entirely (reviewer finding: `os.replace` fails on Windows while another
  process has the target open, and several pointer files cannot be swapped atomically together).
- Crash before the transaction → run stays `running`; the startup recovery sweep marks it `failed`
  and the previous publication is untouched. Crash after → the run is already `succeeded`; nothing to fix.
- A failed or blocked run never changes `published_run_id`.
- Same active Bronze batches ⇒ same Silver/Gold (deterministic SQL: explicit `ORDER BY` for tie-breaks, no
  `now()` in models; run timestamps stored only in metadata). Tested by running twice and comparing sorted outputs.
- Old run directories are pruned **lazily** (keep the published run plus the last 2); deletion failures
  (e.g. a file still open on Windows) are logged and retried later, never fatal.
- **Single writer per data source**, enforced by the partial unique index `uq_one_active_run` on both
  PostgreSQL and SQLite (SQLite supports partial indexes).
- **One process:** P0 runs uvicorn with a single worker and without `--reload` in demo mode; the recovery
  sweep relies on that. SQLite runs in WAL mode with `busy_timeout` so the background pipeline and API
  requests don't hit "database is locked".

**DuckDB connections:** DuckDB refuses a second connection to the same file *in the same process* if its
configuration differs (verified, see `docs/spikes/`). Therefore **all readers of Gold — dashboard and
NL-to-SQL alike — use one connection factory with the identical sandboxed configuration**. Opening per
request vs caching one connection per published run is decided by measurement in Phase 4.

The dashboard resolves the published run once and uses that ID for its quality report, freshness
metadata, and read-only Gold connection. A dataset awaiting its first publication returns
`409 no-published-data`. A publication with a missing Gold file returns
`503 published-data-unavailable` and can be rebuilt from its active batches.

Analytics date ranges include both endpoints and may span up to 3,660 days. When both dates
are omitted, datasets with longer histories default to their latest 3,660 days. The dashboard
reports the original data bounds so callers can select earlier windows, and labels the capped
default as **Latest data**.

## 5. Where Delta Lake would add measurable value (evaluation criteria)
| Delta capability | Do we need it in P0? | Trigger to adopt |
|---|---|---|
| ACID commits | No — single writer + atomic pointer swap suffices | Concurrent writers (e.g. background workers, multiple ingestion processes) |
| MERGE / upserts | No — full rebuild of ~1 M rows is cheap | Datasets where full rebuild exceeds ~5 min or incremental CDC sources (P2 connectors) |
| Schema enforcement/evolution | Partially — Bronze contract + typed Silver cover it | Many sources evolving independently |
| Time travel | Kept-run directories cover debugging | Audit/regulatory need to query "as of" versions |
| Spark/Databricks interop | Yes, for the Databricks path | P1 Databricks implementation writes Delta natively |

Decision: P0 Parquet only. P1 spike: write Gold with `deltalake` 1.x and read via DuckDB's `delta`
extension; measure added complexity (extension download requires network on first use, and the Gold sandbox
configuration disables extension autoloading) before adopting. See [ADR-0004](decisions/0004-delta-lake-deferred.md).

## 6. DuckDB ↔ PySpark parity (P1)
- `tests/fixtures/ecommerce/` holds small CSVs with every edge case (cancellations, duplicates, nulls,
  bad dates, adjustments, multi-ingest overlap) and `expected/*.csv` hand-verified Gold outputs.
- Both implementations must produce those expected outputs: DuckDB in the normal test suite; PySpark in an
  optional CI job (GitHub-hosted runners include Java) and in a Databricks notebook run.
- Shared business rules live in the domain pack (adjustment codes, thresholds) and are read by both.

## 7. Metadata database design (PostgreSQL target)

Conventions: `uuid` PKs (generated in the app, UUIDv7-style for index locality), `timestamptz` in UTC,
`created_at`/`updated_at`, soft-delete only where required (`deleted_at`). Every tenant-owned table has
`org_id NOT NULL` and **composite foreign keys `(org_id, id)`** so a child row cannot reference a parent in
another org even through a bug.

```sql
CREATE TABLE organizations (
  id          uuid PRIMARY KEY,
  slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{2,62}$'),
  name        text NOT NULL,
  status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','deleted')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (                                  -- global identity; membership is per org
  id             uuid PRIMARY KEY,
  email          citext NOT NULL UNIQUE,
  display_name   text NOT NULL,
  password_hash  text,                                -- argon2id; NULL if external IdP (P2)
  is_active      boolean NOT NULL DEFAULT true,
  last_login_at  timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE permissions (                            -- static catalog, seeded by migration
  code         text PRIMARY KEY,                      -- e.g. 'datasets:write', 'analytics:sql', 'documents:read'
  description  text NOT NULL
);

-- Standard roles (owner, admin, analyst, viewer) are *copied into each org* at org creation rather than
-- shared with org_id NULL. Reason: a nullable org_id would make it impossible to enforce with a composite
-- FK that a membership's role belongs to the same org. Copies also let orgs customize roles later.
CREATE TABLE roles (
  id         uuid NOT NULL,
  org_id     uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name       text NOT NULL,
  is_system  boolean NOT NULL DEFAULT false,         -- seeded standard role; not deletable
  PRIMARY KEY (org_id, id),
  UNIQUE (org_id, name)
);

CREATE TABLE role_permissions (
  org_id           uuid NOT NULL,
  role_id          uuid NOT NULL,
  permission_code  text NOT NULL REFERENCES permissions(code),
  PRIMARY KEY (org_id, role_id, permission_code),
  FOREIGN KEY (org_id, role_id) REFERENCES roles(org_id, id) ON DELETE CASCADE
);

CREATE TABLE memberships (
  org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id     uuid NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, user_id),
  FOREIGN KEY (org_id, role_id) REFERENCES roles(org_id, id)   -- role must belong to the same org
);
CREATE INDEX ix_memberships_user ON memberships(user_id);

CREATE TABLE data_sources (                           -- a logical dataset, e.g. "Online Retail"
  id               uuid NOT NULL,
  org_id           uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name             text NOT NULL,
  domain           text NOT NULL,                     -- 'ecommerce'
  kind             text NOT NULL CHECK (kind IN ('file_upload','sample','connector')),
  contract_version text NOT NULL,
  published_run_id uuid,                             -- the one published run; set in the publish transaction
  rerun_requested_at timestamptz,                     -- durable "new batches arrived during a run" marker (§3a)
  created_by       uuid REFERENCES users(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, id),
  UNIQUE (org_id, name)
  -- FK (org_id, id, published_run_id) → pipeline_runs added after that table exists (ALTER TABLE below)
);

CREATE TABLE ingestions (
  id              uuid NOT NULL,
  org_id          uuid NOT NULL,
  data_source_id  uuid NOT NULL,
  original_name   text NOT NULL,
  sha256          char(64) NOT NULL,
  size_bytes      bigint NOT NULL CHECK (size_bytes >= 0),
  row_count       bigint,
  storage_path    text NOT NULL,                      -- relative to org root, never user-controlled
  status          text NOT NULL CHECK (status IN ('received','rejected','stored')),
  is_active       boolean NOT NULL DEFAULT true,       -- deactivated batches are excluded from runs
  rejection_reason text,
  created_by      uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, id),
  FOREIGN KEY (org_id, data_source_id) REFERENCES data_sources(org_id, id) ON DELETE CASCADE,
  UNIQUE (org_id, data_source_id, id)                 -- target for dataset-bound FKs
);
-- idempotent re-upload; rejected uploads don't block re-trying the same bytes after a contract fix
CREATE UNIQUE INDEX uq_ingestion_bytes ON ingestions(org_id, data_source_id, sha256) WHERE status = 'stored';

CREATE TABLE pipeline_runs (
  id              uuid NOT NULL,
  org_id          uuid NOT NULL,
  data_source_id  uuid NOT NULL,
  trigger         text NOT NULL CHECK (trigger IN ('upload','manual','schedule','sample')),
  status          text NOT NULL CHECK (status IN ('queued','running','succeeded','failed','blocked_by_quality')),
  engine          text NOT NULL DEFAULT 'duckdb',     -- 'duckdb' | 'spark'
  code_version    text NOT NULL,                      -- git sha → reproducibility
  started_at      timestamptz,
  finished_at     timestamptz,
  error_code      text,
  error_detail    text,                               -- sanitized
  created_by      uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, id),
  FOREIGN KEY (org_id, data_source_id) REFERENCES data_sources(org_id, id) ON DELETE CASCADE,
  CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at),
  UNIQUE (org_id, data_source_id, id)                 -- target for dataset-bound FKs
);
CREATE INDEX ix_runs_source_created ON pipeline_runs(org_id, data_source_id, created_at DESC);
CREATE UNIQUE INDEX uq_one_active_run ON pipeline_runs(org_id, data_source_id)
  WHERE status IN ('queued','running');              -- single-writer guarantee

-- The published run must belong to the same org AND the same data source:
ALTER TABLE data_sources ADD FOREIGN KEY (org_id, id, published_run_id)
  REFERENCES pipeline_runs(org_id, data_source_id, id);

CREATE TABLE pipeline_run_inputs (                    -- which Bronze batches a run consumed (lineage)
  org_id         uuid NOT NULL,
  data_source_id uuid NOT NULL,
  run_id         uuid NOT NULL,
  ingestion_id   uuid NOT NULL,
  PRIMARY KEY (org_id, run_id, ingestion_id),
  -- run and batch must belong to the same org AND the same data source:
  FOREIGN KEY (org_id, data_source_id, run_id) REFERENCES pipeline_runs(org_id, data_source_id, id) ON DELETE CASCADE,
  FOREIGN KEY (org_id, data_source_id, ingestion_id) REFERENCES ingestions(org_id, data_source_id, id) ON DELETE CASCADE
);

CREATE TABLE pipeline_stage_runs (
  org_id       uuid NOT NULL,
  run_id       uuid NOT NULL,
  stage        text NOT NULL CHECK (stage IN ('silver','silver_quality','gold','gold_quality','publish')),
  status       text NOT NULL,
  rows_in      bigint, rows_out bigint, rows_quarantined bigint,
  started_at   timestamptz, finished_at timestamptz,
  PRIMARY KEY (org_id, run_id, stage),
  FOREIGN KEY (org_id, run_id) REFERENCES pipeline_runs(org_id, id) ON DELETE CASCADE
);

CREATE TABLE quality_results (
  org_id      uuid NOT NULL,
  run_id      uuid NOT NULL,
  rule_id     text NOT NULL,
  stage       text NOT NULL,
  severity    text NOT NULL CHECK (severity IN ('blocking','warning')),
  passed      boolean NOT NULL,
  observed    numeric, threshold numeric,
  details     jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (org_id, run_id, stage, rule_id),
  FOREIGN KEY (org_id, run_id) REFERENCES pipeline_runs(org_id, id) ON DELETE CASCADE
);

CREATE TABLE documents (
  id            uuid NOT NULL,
  org_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  title         text NOT NULL,
  mime_type     text NOT NULL CHECK (mime_type IN ('text/plain','text/markdown','application/pdf')),
  sha256        char(64) NOT NULL,
  size_bytes    bigint NOT NULL,
  storage_path  text NOT NULL,
  visibility    text NOT NULL DEFAULT 'org' CHECK (visibility IN ('org','restricted')),
  status        text NOT NULL CHECK (status IN ('processing','ready','failed')),
  uploaded_by   uuid REFERENCES users(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  deleted_at    timestamptz,
  PRIMARY KEY (org_id, id)
);
-- allows re-uploading a document after it was deleted
CREATE UNIQUE INDEX uq_document_bytes ON documents(org_id, sha256) WHERE deleted_at IS NULL;

CREATE TABLE document_access (                        -- only consulted when visibility = 'restricted'
  org_id       uuid NOT NULL,
  document_id  uuid NOT NULL,
  role_id      uuid NOT NULL,
  PRIMARY KEY (org_id, document_id, role_id),
  FOREIGN KEY (org_id, document_id) REFERENCES documents(org_id, id) ON DELETE CASCADE,
  FOREIGN KEY (org_id, role_id) REFERENCES roles(org_id, id) ON DELETE CASCADE
);

CREATE TABLE document_chunks (
  org_id       uuid NOT NULL,
  document_id  uuid NOT NULL,
  chunk_no     integer NOT NULL CHECK (chunk_no >= 0),
  heading      text,
  content      text NOT NULL,
  char_start   integer NOT NULL, char_end integer NOT NULL,
  page         integer,
  PRIMARY KEY (org_id, document_id, chunk_no),
  FOREIGN KEY (org_id, document_id) REFERENCES documents(org_id, id) ON DELETE CASCADE
);

CREATE TABLE audit_events (                           -- append-only; app role has INSERT/SELECT only
  id           uuid PRIMARY KEY,
  org_id       uuid REFERENCES organizations(id),     -- NULL for pre-auth events (failed login)
  actor_user_id uuid REFERENCES users(id),
  actor_type   text NOT NULL CHECK (actor_type IN ('user','system','anonymous')),
  action       text NOT NULL,                         -- 'dataset.upload', 'nl2sql.execute', 'auth.login_failed'
  target_type  text, target_id uuid,
  outcome      text NOT NULL CHECK (outcome IN ('success','denied','error')),
  correlation_id text NOT NULL,
  ip_hash      text,                                  -- salted hash, not raw IP
  details      jsonb NOT NULL DEFAULT '{}',           -- never secrets or document contents
  occurred_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_org_time ON audit_events(org_id, occurred_at DESC);
CREATE INDEX ix_audit_actor ON audit_events(actor_user_id, occurred_at DESC);

CREATE TABLE llm_calls (
  id                uuid PRIMARY KEY,
  org_id            uuid NOT NULL REFERENCES organizations(id),
  user_id           uuid REFERENCES users(id),
  feature           text NOT NULL CHECK (feature IN ('nl2sql','rag')),
  provider          text NOT NULL, model text NOT NULL,
  prompt_tokens     integer, completion_tokens integer,
  latency_ms        integer NOT NULL,
  status            text NOT NULL CHECK (status IN ('ok','rate_limited','error','timeout','budget_blocked')),
  error_class       text,
  correlation_id    text NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_llm_calls_org_day ON llm_calls(org_id, created_at);   -- daily budget checks

CREATE TABLE ml_models (                              -- P1
  id              uuid NOT NULL,
  org_id          uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  kind            text NOT NULL CHECK (kind IN ('segmentation','forecast','inactivity')),
  version         integer NOT NULL,
  algorithm       text NOT NULL,
  params          jsonb NOT NULL,
  training_run_id uuid,                               -- pipeline run whose Gold it trained on
  metrics         jsonb NOT NULL,                     -- e.g. {"mape":..., "baseline_mape":...}
  artifact_path   text NOT NULL,
  status          text NOT NULL CHECK (status IN ('candidate','active','retired')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, id),
  UNIQUE (org_id, kind, version),
  FOREIGN KEY (org_id, training_run_id) REFERENCES pipeline_runs(org_id, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX uq_one_active_model ON ml_models(org_id, kind) WHERE status = 'active';
```

**Validation performed (2026-11-24) on the first draft:** the DDL (plus `CREATE EXTENSION citext`) was applied to a local
PostgreSQL 16 instance: 17 tables created without errors. Constraint checks run by hand: a membership pointing
at another org's role, and a pipeline run pointing at another org's data source, were both rejected by the
composite FKs; a second `queued/running` run for the same data source was rejected by `uq_one_active_run`.
The schema was revised after review (publish pointer, run inputs table, partial unique indexes); the revised
version was re-applied to PostgreSQL 16 the same day (18 tables, no errors); its constraint checks are
re-run as automated migration tests in Phase 2. Evidence: `docs/spikes/postgres_schema_check.sql`.

### Organization isolation strategy (layered)
1. **Request context:** org comes from the principal (P1) / demo config (P0), never from client input.
2. **Repository layer:** every repository method takes `OrgContext` as a required first argument and adds
   `WHERE org_id = :org_id`; no "unscoped" query helpers exist. Tests assert cross-org reads return nothing.
3. **Schema:** composite FKs on `(org_id, id)` make cross-org references impossible at the DB level.
4. **Analytical data:** physical separation — each org has its own directory and Gold DB file; the
   sandboxed connection is opened on one org's file with external access disabled, so SQL cannot reach
   another org's files even if validation were bypassed (verified behaviour in DuckDB 2.0.1, see SECURITY §5).
5. **P2 defence in depth:** PostgreSQL Row-Level Security policies using `current_setting('app.org_id')`
   set per transaction, with a non-owner app role (`FORCE ROW LEVEL SECURITY`).

### SQLite compatibility notes (local dev)
`uuid` → stored as 36-char text via SQLAlchemy `Uuid`; `jsonb` → `JSON`; `citext` → `COLLATE NOCASE`;
partial unique indexes are supported by SQLite and are used on both databases. Alembic migrations are written once
with SQLAlchemy types; Postgres-only features (RLS, citext) live in Postgres-only migration branches.
CI runs the metadata tests against both SQLite and PostgreSQL from P1 onward.
