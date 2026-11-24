# InsightFlow — System Architecture

Status: Draft for approval (Phase 1) · Last updated: 2026-11-24
Related: [PRD](PRD.md) · [Data architecture](DATA_ARCHITECTURE.md) · [Security](SECURITY.md) ·
[Deployment](DEPLOYMENT.md) · [Roadmap](ROADMAP.md) · [Decisions](decisions/)

## 1. Architectural style: modular monolith

One deployable backend process (FastAPI) + one static frontend, organized into modules with explicit
public interfaces. See [ADR-0001](decisions/0001-modular-monolith.md).

**Why not microservices:** one developer, ₹0 budget, free hosts give one small instance. Microservices
would add network failure modes, distributed auth and deployment overhead with no benefit at this scale.
**What keeps the door open:** modules communicate only via their `service.py` (Python interfaces + Pydantic
DTOs), own their own tables, and never import another module's internals. A module can later be extracted
behind HTTP or a queue without rewriting its callers' logic.

```
                    ┌──────────────────────────────────────────────┐
  Browser ─────────▶│ Frontend (React + Vite, static files)        │
                    └───────────────┬──────────────────────────────┘
                                    │ HTTPS JSON (/api/v1), problem+json errors
┌───────────────────────────────────▼───────────────────────────────────────────────────┐
│ Backend: FastAPI modular monolith                                                     │
│  api (routers, deps, error mapping, rate limit, CORS, correlation id)                 │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ auth*    │ │ ingestion  │ │ pipeline │ │ quality  │ │analytics │ │ ai.nl2sql    │ │
│  │ (P1)     │ │            │ │ (medall.)│ │          │ │ (metrics)│ │ ai.rag       │ │
│  └──────────┘ └─────┬──────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘ │
│  ┌──────────┐ ┌─────▼───────────────▼─────────────▼────────────▼──────┐ ┌───▼───────┐ │
│  │ ml (P1)  │ │ warehouse: AnalyticalEngine interface → DuckDB impl   │ │ ai.llm    │ │
│  └──────────┘ │ storage layout: data/orgs/{org_id}/{bronze,silver,gold}│ │ providers │ │
│  ┌──────────┐ └───────────────────────────────────────────────────────┘ └───┬───────┘ │
│  │ audit &  │ ┌───────────────────────────────────────────────────────┐     │         │
│  │ monitor  │ │ metadata: SQLAlchemy models + repositories (org-scoped)│    │         │
│  └──────────┘ └──────────────────────────┬────────────────────────────┘     │         │
│  domains/ecommerce: contracts, SQL models, quality rules, metric registry    │         │
└──────────────────────────────────────────┼──────────────────────────────────┼─────────┘
                                           ▼                                  ▼
                      SQLite (dev) / PostgreSQL (deployed)          Groq API (OpenAI-compatible)
                      ── application metadata ──                    ── LLM inference ──
             Parquet files + per-org gold.duckdb on local disk / object storage (P2)
             ── analytical data ──
```

## 2. Modules and responsibilities

| Module | Owns | Public interface (examples) | P |
|---|---|---|---|
| `core` | settings (pydantic-settings), logging, error types, `OrgContext`, clock/ids | `get_settings()`, `OrgContext`, `AppError` | P0 |
| `api` | HTTP layer only: routers, request/response schemas, dependencies, middleware | FastAPI app factory `create_app()` | P0 |
| `auth` | users, roles, permissions, sessions/tokens | `authenticate()`, `require_permission(perm)` | P1 (P0: stub that returns the configured demo org + `demo` principal, clearly labelled) |
| `ingestion` | upload validation, contract check, Bronze writes, `data_sources`/`ingestions` records | `ingest_file(org, source, file) -> Ingestion` | P0 |
| `pipeline` | medallion runner, stage ordering, run lifecycle, idempotent publish | `run_pipeline(org, dataset) -> PipelineRun` | P0 |
| `quality` | rule definitions, evaluation, reports | `evaluate(stage, relation, rules) -> QualityReport` | P0 |
| `warehouse` | `AnalyticalEngine` protocol, DuckDB implementation, storage paths, sandboxed read-only connections | `engine.execute_model()`, `engine.readonly_session(org)` | P0 |
| `analytics` | metric registry loading, metric query compilation, dashboard aggregates | `query_metric(org, name, filters)` | P0 |
| `ai.llm` | provider protocol, Groq/OpenAI-compatible adapter, fake provider, retries, call logging | `LLMProvider.complete()` | P0 |
| `ai.nl2sql` | prompt building from Gold catalog + metric registry, SQL validation, safe execution | `answer_question(org, question)` | P0 |
| `ai.rag` | document parsing, chunking, BM25 index per org, grounded answer + citations | `ask(org, principal, question)` | P0 |
| `ml` | features, training, evaluation, model metadata, batch scoring | `train(org, model_kind)` | P1 |
| `audit` | audit events, LLM-call records, run metrics | `record(event)` | P0 (basic) |
| `metadata` | SQLAlchemy engine/session, Alembic migrations, shared base classes | `session_scope()` | P0 |
| `domains.ecommerce` | **data**, not code paths: CSV contract, Silver/Gold SQL models, quality rules, metric definitions | loaded by pipeline/quality/analytics | P0 |

**Dependency rule:** `api → services → (warehouse | metadata | ai.llm)`. Domain packs are configuration
consumed by core modules. `warehouse` and `ai.llm` depend on nothing else in the app. Enforced by review in
P0; an import-linter contract can be added in P1 if drift appears.

## 3. Key flows

### 3.1 Ingest → pipeline (P0, synchronous-with-status)
1. `POST /api/v1/datasets/{id}/uploads` streams the file to a temp path (size-limited), computes SHA-256.
2. Contract check (header names/required columns) against `domains/ecommerce/contract.yaml`.
3. If checksum already ingested for this dataset → return existing ingestion (idempotent).
4. Write Bronze: original file + Parquet copy at `bronze/{dataset}/ingest_id={id}/` (immutable).
5. Create `pipeline_run` (`queued`), run stages `silver → silver_quality → gold → gold_quality → publish`,
   each writing only into the run's own directories; publish is a single metadata-DB transaction setting
   the run `succeeded` and the data source's `published_run_id`; on failure nothing published changes. See [DATA_ARCHITECTURE §4](DATA_ARCHITECTURE.md#4-idempotency-atomic-publish-and-reproducibility).

*P0 runs the pipeline in a FastAPI background task (in-process, single uvicorn worker, no `--reload` in
demo mode).* This is honest about limits: a process restart mid-run marks the run `failed` on startup
(recovery sweep); there is no distributed queue.
P2 replaces this with a job worker (ADR to be written then). The 1 M-row sample is expected to process in
well under a minute; this is measured in Phase 3, not assumed.

### 3.2 Dashboard
Frontend calls `/api/v1/metrics/...` → `analytics` compiles the metric definition to SQL over Gold →
`warehouse` executes on the org's published Gold DB through the **single sandboxed connection factory**
(same configuration as NL-to-SQL — DuckDB requires it) → JSON with values + metric metadata.

**Serving the frontend:** dev uses the Vite dev server proxying `/api` to uvicorn; demo/production serves
the built static files from FastAPI (same origin → simpler CORS/CSP) or a static host.

### 3.3 NL-to-SQL (see §6.3)
### 3.4 RAG (see §6.4)

## 4. Technology selection

Every choice answers: why needed · why selected · alternatives · limitations · replace when.
Full reasoning in ADRs; summary here.

| Concern | Choice | Why selected | Main alternatives | Known limitations | Replace when |
|---|---|---|---|---|---|
| Language | Python 3.12 (managed by `uv`) | Data/ML/AI ecosystem; interview relevance; 3.12 as a conservative, widely supported version (Databricks serverless Python version to be checked in P1) | Go/TS backend | GIL for CPU work (DuckDB releases it) | Never wholesale; hot paths could move to services |
| Env/deps | `uv` + `uv.lock` | Fast, one tool for Python install + venv + lock; works natively on Windows | pip+venv, Poetry | Newer tool | — |
| API | FastAPI + Pydantic v2 | Typed request/response, OpenAPI for free, async I/O for LLM calls | Django (heavier, ORM-centric), Flask (less typing) | In-process background tasks only | Needs admin UI-heavy CRUD → consider Django |
| Analytical engine | **DuckDB** (ADR-0003) | In-process columnar OLAP, reads Parquet natively, no server, fast on a laptop, strong SQL; verified sandbox settings | Polars (no SQL-first sandbox), SQLite (row store, slow OLAP), Postgres (OLTP), Spark (JVM, heavy) | Single writer per DB file; single-node; not a multi-user server | Data > single-node (~100s GB) or concurrent writers → MotherDuck/ClickHouse/Databricks SQL behind the same `AnalyticalEngine` |
| Storage format | **Parquet** | Open, columnar, compressed; readable by DuckDB, Spark, Pandas, Polars → no lock-in | CSV (untyped), Delta (see next) | No ACID by itself | Need multi-writer ACID/time-travel → Delta (ADR-0004) |
| Table format | **Delta Lake deferred** (ADR-0004) | Our single-writer atomic-pointer publish gives the needed guarantees in P0 with zero extra deps | delta-rs now, Iceberg | No time-travel in P0 beyond kept run directories | Incremental MERGE/upserts, concurrent writers, or Databricks interop of shared tables |
| Distributed compute | PySpark on **Databricks Free Edition**, optional (ADR-0005) | Demonstrates Spark/Delta/Unity Catalog with genuine logic + parity tests; nothing local | Local PySpark (needs Java, RAM), Dask | Free Edition is **non-commercial**, quota-capped, no SLA | Commercial scale → paid Databricks/EMR, decided by data volume |
| Transformations | SQL model files + small Python runner (ADR-0008) | Readable, testable, portable SQL; DAG of ~8 models doesn't need a framework | dbt-duckdb (great, but adds a large dep + learning curve in a 3-day window) | We own the runner (keep it tiny) | > ~25 models, docs/lineage needs, or analysts authoring models → migrate to dbt (file layout chosen to make this cheap) |
| Data quality | Declarative YAML rules executed as SQL | Same engine, fast, explainable reports | Great Expectations (heavy), Pandera (DataFrame-centric), Soda | Fewer built-in checks | Rule count/complexity grows → Soda Core or GX |
| Metadata DB | SQLAlchemy 2 + Alembic; **SQLite for local dev/tests, PostgreSQL for deployed** (ADR-0006) | Zero-setup on Windows; Postgres-compatible schema; Neon free tier needs no card | Postgres-only (needs local install), DuckDB (wrong workload) | Dialect drift risk; RLS only on Postgres | Auth/multi-tenant go-live (P1/P2) → CI runs Postgres; RLS added |
| Retrieval | **bm25s** (ADR-0012) | Maintained (2026-10 release), numpy-only, fast, persistable index | rank_bm25 (last release 2022), DuckDB FTS, Postgres FTS (not BM25), embeddings | Lexical only: misses synonyms/paraphrase | Retrieval eval shows recall gaps → hybrid with free/self-hosted embeddings (P2) |
| SQL parsing | **sqlglot** | Parses DuckDB dialect into an AST we can inspect; also transpiles to Spark SQL | Regex (unsafe), DuckDB's own parser via `json_serialize_sql` | Must keep allowlist logic correct | — |
| LLM | Groq via OpenAI-compatible HTTP (`httpx`) behind `LLMProvider` (ADR-0010) | Free tier, very low latency, OpenAI-compatible → any compatible provider is a config change | Gemini free tier, OpenRouter free models, OpenAI (paid) | Free-tier RPM/TPD caps (exact values **unverified**, see DEPLOYMENT.md); models get deprecated | Paid customers or data-residency needs → contracted provider via a new adapter |
| Frontend | React + Vite + TypeScript, TanStack Query, Recharts (ADR-0013) | No rewrite needed for commercialization; static hosting; testable | Streamlit (fast, but would be rewritten), Next.js (SSR not needed) | More code than Streamlit for the interview | — |
| Logging | stdlib `logging` + JSON formatter (structlog optional) | Lightweight, correlation ids | OpenTelemetry (P2) | No tracing backend in P0 | P2 observability |
| Testing | pytest, vitest, Playwright | Standard, free | — | — | — |

## 5. API design

REST, JSON, versioned under `/api/v1`. OpenAPI generated by FastAPI at `/docs` (disabled in public mode).

**Conventions**
- Org scope comes from the authenticated principal (P1) or the configured demo org (P0) — **never** from a
  client-supplied `org_id` parameter. Resource IDs are UUIDs; a resource from another org returns 404 (not 403)
  to avoid existence leaks.
- Errors: RFC 9457 `application/problem+json` `{type, title, status, detail, instance, correlation_id}`.
- Pagination: `?limit=&cursor=`; list responses `{items, next_cursor}`.
- Long operations return `202 Accepted` + resource URL to poll (pipeline runs).
- Every response carries `X-Correlation-ID`.

| Method & path | Purpose | P |
|---|---|---|
| `GET /health` · `GET /ready` | liveness · readiness (metadata DB + storage reachable) | P0 |
| `GET /api/v1/datasets` · `POST /api/v1/datasets` | list/create logical datasets (e.g. "Online Retail") | P0 |
| `POST /api/v1/datasets/{id}/uploads` | upload CSV → ingestion (+ starts pipeline run) | P0 |
| `POST /api/v1/datasets/{id}/load-sample` | ingest bundled sample data | P0 |
| `GET /api/v1/pipeline-runs?dataset_id=` · `GET /api/v1/pipeline-runs/{id}` | run history · run detail with stage timings | P0 |
| `POST /api/v1/datasets/{id}/pipeline-runs` | re-run pipeline on latest Bronze | P0 |
| `GET /api/v1/pipeline-runs/{id}/quality` | data-quality report | P0 |
| `GET /api/v1/metrics` | metric catalog (definitions, units, dimensions) | P0 |
| `GET /api/v1/metrics/{name}?from=&to=&grain=&dimension=&limit=` | metric values | P0 |
| `GET /api/v1/dashboard/overview?from=&to=` | one call for KPI tiles (avoid N+1 from UI) | P0 |
| `POST /api/v1/assistant/sql` `{question}` | NL-to-SQL → `{sql, validation, columns, rows, truncated, timings, llm}` | P0 |
| `GET /api/v1/documents` · `POST /api/v1/documents` · `DELETE /api/v1/documents/{id}` | document library | P0 |
| `POST /api/v1/assistant/ask` `{question}` | RAG → `{answer, citations[], insufficient_context}` | P0 |
| `POST /api/v1/auth/login` · `/refresh` · `/logout` · `GET /api/v1/me` | auth | P1 |
| `/api/v1/orgs/{id}/members`, `/roles` | membership & RBAC admin | P1 |
| `/api/v1/ml/models`, `/ml/segments`, `/ml/forecast`, `/ml/inactivity-risk` | ML outputs | P1 |
| `GET /api/v1/audit-events` | audit trail (admin) | P1 |

Upload while a run is active: stored, follow-up run queued automatically, `202` with both ids (see
DATA_ARCHITECTURE §3a). Deactivate a bad batch: `PATCH /api/v1/datasets/{id}/ingestions/{ingestion_id}`
`{is_active:false}` (P0).

Raw user-written SQL (`POST /api/v1/sql/query`) is **deliberately not in P0**: it would reuse the same
sandbox as NL-to-SQL, but should be gated by an `analytics:sql` permission, which needs P1 auth.

## 6. AI architecture

### 6.1 Provider abstraction (`ai.llm`)
```python
class LLMProvider(Protocol):
    name: str
    async def complete(self, req: CompletionRequest) -> CompletionResult: ...

@dataclass(frozen=True)
class CompletionRequest:
    messages: list[Message]          # system/user/assistant
    model: str                       # from settings, never hardcoded in callers
    max_tokens: int
    temperature: float = 0.0
    json_mode: bool = False          # response_format={"type":"json_object"} when supported
    feature: str = ""                # "nl2sql" | "rag" — for logging/quotas

@dataclass(frozen=True)
class CompletionResult:
    text: str; model: str; provider: str
    prompt_tokens: int | None; completion_tokens: int | None
    latency_ms: int; request_id: str | None
```
Implementations:
- `OpenAICompatibleProvider(base_url, api_key, ...)` — plain `httpx`; Groq is configured as
  `base_url=https://api.groq.com/openai/v1`. Any OpenAI-compatible provider is a config change.
- `FakeProvider` — scripted responses for tests and an **offline demo mode** (canned answers for the
  rehearsed demo questions, visibly labelled "offline demo"). Never used silently in normal mode.
  In offline mode the canned *SQL* still goes through validation and real execution, so the numbers shown
  are real.
- Future adapters (Gemini, Anthropic, Azure OpenAI) implement the same protocol when needed — not before.

Selection: `LLM_PROVIDER=groq|openai_compatible|fake`, `LLM_MODEL=...`, `LLM_BASE_URL`, `LLM_API_KEY`
(env only). Default model ID is configuration; Groq deprecated `llama-3.3-70b-versatile` (shutdown
2026-08-16), so the code must not assume any model name. Initial candidates per Groq docs:
`openai/gpt-oss-120b` (quality) or a smaller Qwen model (speed) — chosen in Phase 5 by a small eval.

### 6.2 Reliability & accounting (applies to every call)
- Timeouts: connect 5 s, read 30 s.
- Retries: only on 429/5xx/timeouts, max 2, exponential backoff with jitter, honouring `Retry-After`.
  No retry on 4xx validation errors.
- Local budget guard: per-org daily call/token totals, derived by querying today's `llm_calls` rows, stop
  calls *before* hitting the provider's daily cap → friendly "assistant quota reached for today" instead of cascading 429s.
- Every call writes an `llm_calls` row: org, user, feature, provider, model, prompt/completion tokens,
  latency, status, error class, correlation id. **Prompt and response bodies are not logged by default**
  (they may contain customer data); a `LOG_LLM_PAYLOADS` dev-only flag exists for debugging.
- Errors map to stable user-facing codes: `llm_unavailable`, `llm_rate_limited`, `llm_quota_exhausted`,
  `llm_bad_output`. The dashboard and pipelines never depend on the LLM.

### 6.3 NL-to-SQL
```
question ─▶ build prompt ─▶ LLM (json_mode) ─▶ parse {sql, explanation}
          (Gold catalog: allowlisted tables/columns + descriptions,
           metric registry definitions, dialect=DuckDB, rules, 3–5 few-shot examples)
     ─▶ validate (sqlglot AST, see SECURITY §5) ─┬─ invalid ─▶ one repair attempt with the validator error ─▶ else refuse
                                                  └─ valid ─▶ rewrite: enforce LIMIT ≤ 1000
     ─▶ execute on org's read-only sandboxed DuckDB connection, statement timeout
     ─▶ return SQL + rows (+ optional suggested chart type)
```
Design points:
- **Only schema and metric definitions are sent to the LLM, not data rows.** Query results are not sent
  back to the LLM in P0 (no "summarize the result" step), which limits data exposure to the third party.
- Metrics in the registry are exposed as Gold views (e.g. `metric_monthly_revenue`) so the LLM can reuse
  canonical definitions instead of re-deriving revenue logic — keeps dashboard and NL answers consistent.
- The validator is the first defence; the sandboxed connection is the security boundary (defence in depth).

### 6.4 RAG
```
upload ─▶ type/size checks ─▶ extract text (md/txt; PDF via pypdf is a stretch goal) ─▶ normalize
       ─▶ chunk (heading-aware, ~800 chars, 100 overlap) ─▶ store chunks (metadata DB, org_id, doc ACL)
       ─▶ rebuild that org's bm25s index under a per-org lock into a new versioned directory, with a stored
          position → (document_id, chunk_no) map; the active index version is recorded in the metadata DB
ask ─▶ retrieve from *the caller's org index only*, over chunks the caller may read (ACL applied
       **before** ranking, so restricted documents never displace allowed ones), top-k = 5
    ─▶ if no chunk passes the relevance gate ─▶ "insufficient context" (no LLM call)
    ─▶ prompt: system rules + chunks wrapped as <source id="n">…</source> marked untrusted
    ─▶ LLM answer must cite [n]; post-check: invalid citation numbers are removed; an answer left with
       **no valid citation is not shown** — the API returns `insufficient_context` instead
    ─▶ return answer + citations (document title, `chunk_id` = "{document_id}:{chunk_no}", snippet)

Relevance gate: raw BM25 scores are not comparable across queries or corpora, so the gate combines a
minimum share of query terms matched with a score threshold, **calibrated on the Phase 6 eval set** and
recorded in `docs/evals/` — not a guessed constant.
```
The RAG path has **no tools and no SQL execution**, so injected instructions inside documents can at worst
distort an answer's text — they cannot exfiltrate other orgs' data or take actions. See SECURITY §6.

### 6.5 Evaluation (lightweight, free)
- NL-to-SQL: ~15 question → expected-result pairs on the fixture dataset; score = result-set equality, not
  SQL text equality. Run manually (it uses quota), not in CI.
- RAG: ~15 question → expected-source pairs; report hit@k and refusal correctness.
- Results recorded in `docs/evals/` with date, model and provider — never claimed without a run.

## 7. Monitoring & audit
- Structured JSON logs (one line per event) with `correlation_id`, `org_id`, `module`, `duration_ms`.
- Pipeline runs and stage timings persisted (`pipeline_runs`, `pipeline_stage_runs`) → monitoring view (P1).
- `audit_events` for: uploads, pipeline triggers, document upload/delete, NL-to-SQL executions (with SQL
  text and validation outcome), RAG questions (question length/hash, not content by default), auth events (P1).
- P2: OpenTelemetry traces/metrics to a free backend (e.g. Grafana Cloud free tier — to be verified then).

## 8. Multi-domain extensibility
A domain pack is a folder: `contract.yaml`, `models/silver/*.sql`, `models/gold/*.sql`, `quality.yaml`,
`metrics.yaml`, `nl2sql_examples.yaml`. Core code reads packs; it contains no e-commerce logic.
**We deliberately do not build a generic plugin framework now**: one domain exists. The pack layout is the
seam; real abstraction is extracted when the second domain arrives (rule of three).
