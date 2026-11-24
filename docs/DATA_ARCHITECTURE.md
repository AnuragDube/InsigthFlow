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
| **DuckDB** | Executes Silver/Gold SQL models and quality rules over Parquet; serves Gold to the API via a per-org `gold.duckdb` holding **views over the published Parquet**; sandboxed read-only connection for NL-to-SQL. | Yes |
| **PostgreSQL** | Application metadata only, in deployed environments. Never stores analytical facts. | Schema designed; SQLite used locally until P1 |
| **Delta Lake (delta-rs)** | Not in P0. Candidate for Silver/Gold when incremental MERGE or concurrent writers appear, and as the format of the Databricks implementation. See §5. | No |
| **PySpark (Databricks Free Edition)** | Second implementation of the same Silver/Gold logic for scale/interview demonstration, validated by parity tests on shared fixtures. Not on the primary dev path. | P1 |

Not adding: a separate warehouse (Snowflake/BigQuery), Iceberg, Kafka, Airflow, a vector DB. Each would
duplicate a role above with no P0 benefit.

## 3. Medallion design

Storage layout (local disk in P0; object storage prefix in P2 — same relative layout):
```
data/orgs/{org_id}/
  bronze/{dataset}/ingest_id={uuid}/raw.csv            # original bytes, never modified
  bronze/{dataset}/ingest_id={uuid}/data.parquet       # all columns as VARCHAR + lineage columns
  bronze/{dataset}/ingest_id={uuid}/_manifest.json     # checksum, size, rows, received_at, contract version
  silver/{table}/run_id={uuid}/part-*.parquet          # one directory per pipeline run
  silver/{table}/_current                              # text file: run_id of the published version
  gold/{table}/run_id={uuid}/part-*.parquet
  gold/{table}/_current
  gold.duckdb                                          # views → gold/{table}/run_id={current}/*.parquet
  quarantine/{dataset}/run_id={uuid}/rejected.parquet  # rows rejected in Silver + reason codes
  rag/bm25_index/                                      # retrieval index (see ARCHITECTURE §6.4)
```

### Bronze — immutable raw
- Exactly what was received (`raw.csv`) plus a Parquet copy with **every column as text** so that type errors
  are handled in Silver, not lost at ingestion.
- Lineage columns: `_ingest_id`, `_source_file`, `_row_number`, `_ingested_at`.
- Append-only. Re-uploading identical bytes (same SHA-256) is a no-op returning the existing ingestion.
- Retention: kept until org deletes the dataset (P2: retention policies).

### Silver — cleaned, validated, standardized (e-commerce pack)
`silver.order_lines` from all Bronze ingestions of the dataset:
- Cast types (`quantity INTEGER`, `unit_price DECIMAL(12,2)`, `invoice_ts TIMESTAMP`), trim strings,
  normalize country names and stock codes (upper-case, trimmed).
- Flags: `is_cancellation` (invoice starts with `C`), `is_adjustment` (non-product stock codes such as
  postage/manual/bank charges — list maintained in the domain pack).
- Deduplicate exact duplicate lines (same invoice, stock code, quantity, price, timestamp, customer) keeping
  the earliest `_ingest_id`/`_row_number` → deterministic.
- Rows failing hard parsing (unparseable date, non-numeric quantity) go to **quarantine** with `reason_code`,
  not silently dropped.
- Missing `customer_id` is kept (valid sales) but flagged; customer-level metrics exclude them explicitly.

### Gold — business-ready
| Table | Grain | Notes |
|---|---|---|
| `dim_date` | day | calendar attributes |
| `dim_customer` | customer | first/last order date, country, order count, lifetime revenue |
| `dim_product` | stock code | latest description (deterministic tie-break), first seen |
| `fact_sales` | invoice line (non-cancelled, non-adjustment, quantity > 0, price > 0) | `revenue = quantity * unit_price` |
| `fact_returns` | cancelled lines | for return-rate metrics |
| `agg_daily_sales` | day × country | pre-aggregated for the dashboard |
| `metric_*` views | per metric | canonical definitions exposed to NL-to-SQL |

### Metric registry (deterministic definitions)
`domains/ecommerce/metrics.yaml`, e.g.:
```yaml
- name: net_revenue
  label: Net revenue
  unit: GBP
  sql: SUM(revenue)
  source: fact_sales
  time_column: invoice_date
  dimensions: [country, product, customer]
  description: Sum of quantity × unit price for non-cancelled product lines with positive quantity and price.
- name: average_order_value
  sql: SUM(revenue) / NULLIF(COUNT(DISTINCT invoice_no), 0)
- name: repeat_customer_rate     # customers with ≥2 invoices in period / customers with ≥1 (known customer_id only)
```
P0 set (≥ 8): net revenue, orders, average order value, units sold, active customers, new customers,
repeat customer rate, return rate (by value), revenue by country, top products.
Golden tests compute each metric by hand on a ~60-row fixture and assert exact equality.

**Currency caveat:** the UCI dataset is in GBP. Multi-currency is a P2 concern (would need FX tables);
P0 labels units explicitly and does not convert.

### Data quality rules (`quality.yaml`)
| Rule | Stage | Severity |
|---|---|---|
| Required columns present | Bronze contract | blocking |
| `invoice_ts` parseable ≥ 99% of rows | Silver | blocking |
| `quantity`, `unit_price` numeric | Silver | blocking (row → quarantine) |
| Duplicate-line ratio reported | Silver | warning |
| `customer_id` null ratio ≤ 30% | Silver | warning (UCI is known to have many missing customer ids) |
| `fact_sales.revenue` ≥ 0, no nulls in keys | Gold | blocking |
| Row reconciliation: bronze = silver + quarantine + duplicates removed | Silver | blocking |
| Gold revenue equals Silver eligible revenue (± 0.01) | Gold | blocking |

Thresholds are configuration, reviewed when real data is profiled in Phase 3 (not guessed as final now).

## 4. Idempotency, atomic publish and reproducibility
- Each run writes to `.../run_id={new}/`; nothing reads that directory until publish.
- Publish = all quality gates passed → write `_current` files via write-temp-then-`os.replace` (atomic on
  Windows and POSIX for the same volume), then recreate `gold.duckdb` views. Readers see either old or new.
- A failed or blocked run leaves the previous published version intact and visible.
- Same Bronze set ⇒ same Silver/Gold (deterministic SQL: explicit `ORDER BY` for tie-breaks, no `now()` in
  models; run timestamp stored only in metadata). Tested by running twice and comparing sorted outputs.
- Old run directories are pruned to the last N (default 3) → lightweight "time travel" for debugging.
- **Single-writer assumption:** one pipeline run per (org, dataset) at a time, enforced by a DB-level
  unique partial index on active runs (Postgres) / a check in the service (SQLite). This is exactly the
  assumption Delta would remove — see next section.

## 5. Where Delta Lake would add measurable value (evaluation criteria)
| Delta capability | Do we need it in P0? | Trigger to adopt |
|---|---|---|
| ACID commits | No — single writer + atomic pointer swap suffices | Concurrent writers (e.g. background workers, multiple ingestion processes) |
| MERGE / upserts | No — full rebuild of ~1 M rows is cheap | Datasets where full rebuild exceeds ~5 min or incremental CDC sources (P2 connectors) |
| Schema enforcement/evolution | Partially — Bronze contract + typed Silver cover it | Many sources evolving independently |
| Time travel | Kept-run directories cover debugging | Audit/regulatory need to query "as of" versions |
| Spark/Databricks interop | Yes, for the Databricks path | P1 Databricks implementation writes Delta natively |

Decision: P0 Parquet only. P1 spike: write Gold with `deltalake` 1.x and read via DuckDB's `delta`
extension; measure added complexity (extension download requires network on first use, and the NL-to-SQL
sandbox disables extension autoloading) before adopting. See [ADR-0004](decisions/0004-delta-lake-deferred.md).

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
  created_by       uuid REFERENCES users(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, id),
  UNIQUE (org_id, name)
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
  rejection_reason text,
  created_by      uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, id),
  FOREIGN KEY (org_id, data_source_id) REFERENCES data_sources(org_id, id) ON DELETE CASCADE,
  UNIQUE (org_id, data_source_id, sha256)             -- idempotent re-upload
);

CREATE TABLE pipeline_runs (
  id              uuid NOT NULL,
  org_id          uuid NOT NULL,
  data_source_id  uuid NOT NULL,
  trigger         text NOT NULL CHECK (trigger IN ('upload','manual','schedule','sample')),
  status          text NOT NULL CHECK (status IN ('queued','running','succeeded','failed','blocked_by_quality')),
  engine          text NOT NULL DEFAULT 'duckdb',     -- 'duckdb' | 'spark'
  code_version    text NOT NULL,                      -- git sha → reproducibility
  input_ingestions uuid[] NOT NULL,                   -- Bronze inputs (SQLite: JSON)
  started_at      timestamptz,
  finished_at     timestamptz,
  error_code      text,
  error_detail    text,                               -- sanitized
  created_by      uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, id),
  FOREIGN KEY (org_id, data_source_id) REFERENCES data_sources(org_id, id) ON DELETE CASCADE,
  CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
);
CREATE INDEX ix_runs_source_created ON pipeline_runs(org_id, data_source_id, created_at DESC);
CREATE UNIQUE INDEX uq_one_active_run ON pipeline_runs(org_id, data_source_id)
  WHERE status IN ('queued','running');              -- single-writer guarantee

CREATE TABLE pipeline_stage_runs (
  org_id       uuid NOT NULL,
  run_id       uuid NOT NULL,
  stage        text NOT NULL CHECK (stage IN ('bronze','silver','gold','publish')),
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
  PRIMARY KEY (org_id, run_id, rule_id),
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
  PRIMARY KEY (org_id, id),
  UNIQUE (org_id, sha256)
);

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
  FOREIGN KEY (org_id, training_run_id) REFERENCES pipeline_runs(org_id, id)
);
CREATE UNIQUE INDEX uq_one_active_model ON ml_models(org_id, kind) WHERE status = 'active';
```

### Organization isolation strategy (layered)
1. **Request context:** org comes from the principal (P1) / demo config (P0), never from client input.
2. **Repository layer:** every repository method takes `OrgContext` as a required first argument and adds
   `WHERE org_id = :org_id`; no "unscoped" query helpers exist. Tests assert cross-org reads return nothing.
3. **Schema:** composite FKs on `(org_id, id)` make cross-org references impossible at the DB level.
4. **Analytical data:** physical separation — each org has its own directory and `gold.duckdb`; the
   sandboxed connection is opened on one org's file with external access disabled, so SQL cannot reach
   another org's files even if validation were bypassed (verified behaviour in DuckDB 2.0.1, see SECURITY §5).
5. **P2 defence in depth:** PostgreSQL Row-Level Security policies using `current_setting('app.org_id')`
   set per transaction, with a non-owner app role (`FORCE ROW LEVEL SECURITY`).

### SQLite compatibility notes (local dev)
`uuid` → stored as 36-char text via SQLAlchemy `Uuid`; `jsonb` → `JSON`; `citext` → `COLLATE NOCASE`;
`uuid[]` → JSON array; partial unique indexes are supported by SQLite. Alembic migrations are written once
with SQLAlchemy types; Postgres-only features (RLS, citext) live in Postgres-only migration branches.
CI runs the metadata tests against both SQLite and PostgreSQL from P1 onward.
