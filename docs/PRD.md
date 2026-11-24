# InsightFlow — Product Requirements Document

Status: Draft for approval (Phase 1) · Last updated: 2026-11-24

## 1. Vision

InsightFlow turns an organization's raw operational data into trustworthy, explainable business answers.
A business user uploads data, the platform cleans and models it through a governed Bronze → Silver → Gold
pipeline, and then anyone in the organization can explore deterministic business metrics on a dashboard,
ask questions in plain English (answered with *visible, validated* SQL), and query the organization's own
documents with cited answers.

The differentiator is **trust**: every number traces back to a defined metric, a data-quality report and a
pipeline run; every AI answer shows its SQL or its sources. The AI never invents numbers.

First demonstration domain: **e-commerce analytics**. The core (ingestion, medallion pipeline, quality,
metrics, assistants) is domain-agnostic; domains plug in as "domain packs" (schema contracts, SQL models,
metric definitions, quality rules).

### Why this product, two horizons
| Horizon | Goal | Implication |
|---|---|---|
| Now (interview, 2026-11-27) | Demonstrate data engineering, analytics, ML-readiness, AI and engineering ownership | Ship a working vertical slice, run locally, honest about limits |
| Later (commercial SaaS) | Multi-tenant product, possibly a family of data/AI products | Foundations must not need a rewrite: org-aware data, replaceable engine/LLM, clean module boundaries |

## 2. Target users

| Persona | Need | Primary surfaces |
|---|---|---|
| **Business owner / manager** (SME e-commerce) | "How are we doing and why?" without SQL | Dashboard, NL questions |
| **Data/business analyst** | Fast, correct metrics; ad-hoc SQL; trust in data | Metrics, SQL view, quality reports |
| **Data engineer / admin** | Reliable ingestion, reproducible runs, visibility into failures | Datasets, pipeline runs, quality |
| **Operations / support staff** | Answers from policies, SOPs, product docs | Document assistant (RAG) |
| *Future:* org administrator | Users, roles, access, usage | Admin (P1/P2) |

## 3. Main user journeys

1. **Ingest** — Analyst uploads a CSV (or loads the bundled sample) → file stored immutably in Bronze →
   pipeline run starts → user sees run status per stage.
2. **Trust the data** — User opens the run's data-quality report: rows in/out per stage, rule results
   (nulls, duplicates, negative quantities, invalid dates, cancellations), quarantined row counts.
3. **Monitor the business** — Dashboard: revenue, orders, AOV, customers, repeat rate, top products,
   revenue by country, monthly trend; date-range filter. Every tile names its metric definition.
4. **Ask a data question** — "Which 5 countries had the highest revenue in 2011?" → system shows generated SQL,
   validation status, result table/chart. Unsafe or unanswerable questions are refused with a reason.
5. **Ask a document question** — User uploads policy/product docs → asks "What is our return window?" →
   answer with numbered citations linking to source chunks; "not found in your documents" when unsupported.
6. *(P1)* **Predict** — View customer segments, a sales forecast with backtest error, and an inactivity-risk list.
7. *(P1)* **Govern** — Sign in; roles restrict who can upload, run pipelines, query SQL or see documents;
   audit trail of who did what.

## 4. Feature priorities

### P0 — Interview-ready MVP (vertical slice)
| ID | Feature | Acceptance criteria (summary) |
|---|---|---|
| P0-1 | Dataset ingestion | CSV upload (≤ 100 MB configurable) + "load sample dataset"; schema-contract check; stored immutably in Bronze with checksum; idempotent on identical re-upload |
| P0-2 | Medallion processing | Bronze → Silver (typed, cleaned, deduplicated, standardized, quarantine) → Gold (star schema + aggregates); deterministic; re-run yields identical Gold |
| P0-3 | Data quality validation | Declarative rules per domain; per-run report with pass/warn/fail and counts; failing *blocking* rules stop promotion to Gold |
| P0-4 | Metrics & SQL analytics | Metric registry (≥ 8 metrics) with definitions; API to query metrics by date range/grain/dimension |
| P0-5 | Interactive dashboard | KPI tiles, trend, top-N, breakdown; date filter; run status & DQ summary visible |
| P0-6 | NL-to-SQL | Question → validated read-only SQL on Gold only → results + SQL shown; adversarial test suite passes |
| P0-7 | Basic RAG assistant | Upload .md/.txt/.pdf; BM25 retrieval; answer with citations; refuses when no supporting chunk |
| P0-8 | Reproducible tests & docs | One-command setup and test run on Windows; README quickstart; docs current |

Within P0, *organization context* exists in code (a single configured demo org), but there is **no
authentication** and the app must **not** be exposed publicly with uploads enabled (see SECURITY.md).

### P1 — Extended capabilities
Customer segmentation (RFM + k-means) · sales forecasting (with baseline + backtest) · customer inactivity
prediction · pipeline monitoring view · Databricks/PySpark implementation with parity tests ·
authentication & RBAC · persistent PostgreSQL metadata · automated/scheduled orchestration.

### P2 — Commercial evolution
Secure public multi-tenant deployment · more connectors (Shopify, Postgres, Google Sheets, S3) · advanced
analytics · hybrid/semantic retrieval · vector DB · background job workers · usage tracking & quotas ·
billing · SSO/enterprise integrations · advanced observability, backups & disaster recovery.

## 5. Explicit non-goals (for now)
- Not a general BI tool replacement (no drag-and-drop chart builder, no arbitrary joins across orgs).
- Not real-time/streaming analytics; batch is sufficient for SME e-commerce.
- No LLM-computed numbers: numbers come from SQL; the LLM writes SQL or prose, never arithmetic results.
- No write access from the assistant (no INSERT/UPDATE, no actions/tools that change state).
- No fine-tuning, no local model hosting, no GPU dependency.
- No public multi-tenant deployment before P1 auth/authorization/tenant-isolation tests exist.
- No Kubernetes, Airflow, Kafka or microservices.

### Anti-goals (would be failure even if it "works")
- Dashboards and NL answers disagreeing on the same metric.
- Any path where one org can read another org's data or documents.
- A demo that depends on a free service that is asleep, rate-limited or down at interview time with no fallback.
- Hidden costs or a card-required service introduced silently.

## 6. Functional requirements (P0)
- FR-1 Upload CSV via UI/API; validate header against the domain contract; reject with a clear report.
- FR-2 Persist raw file + ingestion metadata (org, dataset, checksum, size, row count, received_at) in Bronze.
- FR-3 Pipeline run lifecycle: `queued → running → succeeded | failed | blocked_by_quality`, per stage timings.
- FR-4 Silver: type casting, trimming/normalization, dedup, business-rule flags (e.g. cancellation), quarantine table for rejected rows with reason codes.
- FR-5 Gold: `fact_sales`, `dim_customer`, `dim_product`, `dim_date`, `agg_daily_sales`; plus metric views.
- FR-6 Quality rules declared in config; results stored per run; blocking vs warning severity.
- FR-7 Metric API returns value(s) plus metric metadata (definition, unit, grain, source run id).
- FR-8 NL-to-SQL returns: SQL, validation result, rows (≤ 1,000), execution ms, model/latency/tokens.
- FR-9 RAG returns: answer, citations `[{n, document, chunk_id, snippet}]`, or an explicit "insufficient context".
- FR-10 All mutating actions and AI calls write audit events.

## 7. Non-functional requirements
| Category | Requirement (P0 target) |
|---|---|
| Cost | ₹0; no card-required services in the dev/demo path |
| Footprint | Dev stack runs on Windows 11, 16 GB RAM, no Docker/Java/Spark/local LLM; backend idle RSS < 500 MB |
| Performance | Full pipeline on UCI Online Retail II (~1.07 M rows) < 60 s on the dev laptop *(to be measured, not assumed)*; dashboard API p95 < 500 ms on Gold |
| Reproducibility | Same Bronze input ⇒ byte-identical Gold row sets (ordering-normalized); pinned dependencies (`uv.lock`, `package-lock.json`) |
| Reliability | Failed runs never leave partially-published Silver/Gold; LLM outage degrades gracefully (dashboard unaffected) |
| Security | See SECURITY.md; generated SQL sandboxed; no secrets in repo; safe errors |
| Observability | Structured JSON logs with correlation ids; pipeline-run and LLM-call records |
| Testability | Unit + integration tests runnable offline; LLM via fake provider in tests |
| Portability | Analytical engine and LLM provider behind interfaces; open formats (Parquet, SQL) |
| Accessibility | Dashboard keyboard-navigable, sufficient contrast, charts have text equivalents |

## 8. Success measures
- Interview: live end-to-end demo in < 7 minutes from "load sample" to cited RAG answer, offline fallback ready.
- Engineering: CI green; NL-to-SQL adversarial suite 100% blocked; metric golden tests pass.
- Product (later): 3–5 real SMEs use it on their own data; time-to-first-insight < 15 minutes.

## 9. Open questions
- Which real users will validate the product after the interview (Shopify sellers? D2C brands?) — drives connectors.
- Will customers accept their data/schema being sent to a third-party LLM API? (Affects provider choice and DPA needs.)
