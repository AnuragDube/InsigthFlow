# InsightFlow — Engineering Plan & Roadmaps

Status: Draft for approval (Phase 1) · Last updated: 2026-11-24 (Tuesday)
Interview: **Friday 2026-11-27**. The interview deadline is the deadline for Roadmap A only.

## 1. Repository structure (target)
```
InsigthFlow/
├── CLAUDE.md                     # durable rules (short)
├── README.md                     # quickstart (Windows-first), demo script link
├── pyproject.toml · uv.lock · .python-version (3.12)
├── .env.example                  # placeholders only
├── backend/
│   ├── src/insightflow/
│   │   ├── core/                 # settings, logging, errors, OrgContext
│   │   ├── api/                  # app factory, routers/, deps, middleware
│   │   ├── metadata/             # SQLAlchemy base, session, models, repositories
│   │   ├── ingestion/  pipeline/  quality/  warehouse/  analytics/
│   │   ├── ai/{llm,nl2sql,rag}/
│   │   ├── audit/
│   │   ├── auth/  ml/            # P1
│   │   └── domains/ecommerce/    # contract.yaml, models/{silver,gold}/*.sql, quality.yaml, metrics.yaml
│   ├── migrations/               # Alembic
│   └── tests/{unit,integration,security}/ + fixtures/ecommerce/{input,expected}/
├── frontend/                     # Vite + React + TS; src/, tests (vitest), e2e/ (Playwright)
├── spark/                        # P1: PySpark jobs + Databricks notebooks + parity tests
├── scripts/                      # fetch_sample_data.py, demo helpers
├── data/                         # gitignored runtime data (orgs/...)
├── docs/                         # PRD, ARCHITECTURE, DATA_ARCHITECTURE, SECURITY, DEPLOYMENT, ROADMAP, decisions/, evals/
└── .github/workflows/ci.yml      # lint, type-check, tests, gitleaks, frontend build, e2e
```

## 2. Dependency map (P0 runtime; versions pinned in lockfiles at scaffold time)
| Package | Used by | Why | Weight |
|---|---|---|---|
| fastapi, uvicorn, pydantic, pydantic-settings | api, core | HTTP, validation, config | light |
| python-multipart | api | file uploads | light |
| duckdb | warehouse, pipeline, quality | analytical engine | ~one wheel, no deps |
| pyarrow | pipeline (Parquet I/O helpers) | Parquet interop | medium — evaluate if DuckDB alone suffices (it may) |
| sqlalchemy, alembic | metadata | ORM, migrations | light |
| sqlglot | ai.nl2sql | SQL AST validation | pure Python |
| bm25s (+numpy) | ai.rag | BM25 retrieval | light |
| pypdf | ai.rag | PDF text extraction | pure Python |
| httpx | ai.llm | provider HTTP calls | light |
| pyyaml | domains | config files | light |
| dev: pytest, pytest-asyncio, ruff, mypy, gitleaks (CI binary) | — | quality | — |
| frontend: react, react-dom, @tanstack/react-query, recharts, react-router; dev: vite, typescript, vitest, @playwright/test | frontend | UI | — |
| P1: scikit-learn, statsmodels, psycopg, argon2-cffi, pyjwt; spark: pyspark (CI/Databricks only) | ml, auth, metadata | — | heavier; P1 only |

Module dependency direction: `api → {ingestion, pipeline, quality, analytics, ai.*, audit} → {warehouse,
metadata, ai.llm, core}`; `domains` is data read by pipeline/quality/analytics/nl2sql. No cycles.

## 3. Roadmap A — Interview-ready MVP (Tue 24 → Fri 27 Nov)

Each phase ends with tests run, a report, a git bundle for you to push, and **your approval**.
**Honest capacity check:** six build phases of ~3–5 h each plus review/approval time is roughly 2.5 days of
continuous work. It fits only if approvals come back quickly. Recommended: merge Phases 2 and 3 under a
single approval gate (foundations alone have little to review), and treat Phase 6 (RAG) as the first
candidate to shrink, because the interview is for an **Associate Analyst** role — metrics, SQL and data
quality are the core of the story; RAG is depth.

| Phase | Target | Scope | Demo value |
|---|---|---|---|
| **1** Product & architecture | Tue 24 | These docs + ADRs | Talk track for system design questions |
| **2** Foundations | Wed 25 AM | Scaffold (uv, FastAPI app factory, settings, logging, problem+json errors, `/health`), metadata models for orgs/data_sources/ingestions/pipeline_runs/quality_results/audit (SQLite + Alembic), fixtures, CI workflow | "Production-minded foundations" |
| **3** Ingestion + Medallion + Quality | Wed 25 | CSV ingest → Bronze; Silver/Gold SQL models; quality rules; transactional publish; golden-fixture tests; UCI xlsx → CSV conversion script; real UCI run with **measured** timings. Needs: UCI download (host blocked here — network request or manual download) | Core data-engineering story |
| **4** Metrics API + Dashboard | Wed 25 PM → Thu 26 AM | metric registry, metric/overview endpoints, React dashboard (KPIs, trend, top products, country breakdown, run + DQ status) | The visible "wow" |
| **5** NL-to-SQL | Thu 26 | Validator (TDD with ~15–20 adversarial cases), sandbox executor, Groq provider + fake provider, UI panel showing SQL. Needs: Groq API key + network access to `api.groq.com` | AI + security story |
| **6** RAG assistant | Thu 26 PM | md/txt upload (PDF stretch), chunking, bm25s, cited answers, refusal path, UI | RAG story |
| **7** Demo hardening | Thu 26 night / Fri AM | Playwright happy-path e2e (run locally; CI later), `/security-review`, README quickstart, demo script, offline demo mode, screen recording. Public read-only deployment only if time remains | Reliability on the day |

**Cut line (decided now, not under pressure):** if Phase 5 isn't done by Thu 26 noon →
RAG drops PDF support (md/txt only); dashboard limited to 4 KPIs + 2 charts; no public deployment before
the interview. Deployment is *not* on the interview critical path in any case.

**Interview demo script (target ≤ 7 min):** load sample → pipeline run with stage timings → DQ report
(cancellations, missing customers, duplicates quarantined) → dashboard → NL question with visible SQL →
blocked malicious question → RAG question with citation → architecture diagram & trade-offs.

## 4. Roadmap B — Commercial product (gated by evidence, not dates)

| Release | Contents | Entry gate |
|---|---|---|
| **R1 — P1 capabilities** | Auth + RBAC; Postgres metadata (Neon) with CI on Postgres; cross-org isolation tests; pipeline monitoring UI; scheduled runs (GitHub Actions cron or in-app scheduler); ML: RFM segmentation, forecast vs seasonal-naive baseline with backtest, inactivity model with time-based split; model metadata; PySpark/Databricks implementation + parity tests; Delta spike | Roadmap A done; interview over |
| **R2 — Private beta** | Invite 3–5 real SMEs; persistent object storage (B2); usage metrics; feedback loop; data deletion on request; privacy notice | R1 security DoD met; no known cross-tenant issues |
| **R3 — Product validation** | Connectors driven by beta demand (e.g. Shopify, Google Sheets); hybrid retrieval if eval shows lexical gaps; background job worker; quotas | Evidence that ≥ 3 users return weekly |
| **R4 — Commercial launch (P2)** | Paid infra; Postgres RLS; backups/PITR, DR runbook; OpenTelemetry; billing; SSO; contracted LLM provider + DPA; external security review | Willingness to pay demonstrated; budget approved |
| **R5 — Product ecosystem** | Extract shared platform (ingestion/quality/metrics) for additional domain packs/products | Second domain with real users |

## 5. Test strategy
| Layer | What | Tooling | When |
|---|---|---|---|
| Unit | quality rule evaluation, metric compilation, SQL validator, chunker, BM25 wrapper, provider retry logic, settings | pytest | every commit |
| Golden data | Silver/Gold outputs and every metric on hand-verified fixtures (edge cases: cancellations, duplicates, null customers, bad dates, adjustments, overlapping uploads) | pytest + expected CSVs | every commit |
| Idempotency | run pipeline twice → identical Gold; re-upload same file → no new ingestion | pytest | every commit |
| Integration | API endpoints via TestClient with temp data dir + SQLite | pytest | every commit |
| Security | adversarial SQL corpus vs validator and vs sandbox alone; upload abuse (size, names, types); cross-org access (P1); error-leak checks | pytest | every commit |
| AI (offline) | NL-to-SQL/RAG flows with `FakeProvider`; citation verification; refusal paths; 429 handling | pytest | every commit |
| AI (online eval) | small result-equality eval set against Groq; recorded in docs/evals | script | manually, per model change |
| Frontend | component logic, formatting | vitest | every commit |
| E2E | load sample → dashboard → NL question → RAG answer (fake provider) | Playwright | CI + before demo |
| Parity (P1) | DuckDB vs PySpark on shared fixtures | pytest + pyspark (CI job with Java) / Databricks | P1 |
| Performance | pipeline on full UCI dataset; API p95 | timing script, results recorded with machine specs | Phase 3/4, re-run before demo |

Rules: tests never call the real LLM or network; test data is synthetic or CC BY; no test result is reported
unless it was run.

## 6. Risk register
| # | Risk | L | I | Mitigation | Owner/phase |
|---|---|---|---|---|---|
| R1 | 3-day window too short for full P0 | H | H | Cut line (§3); phases small; deployment off critical path | All |
| R2 | Groq unreachable / rate-limited / model deprecated during demo | M | H | Offline demo mode with labelled canned answers; recorded video; model id in config; budget guard | 5–7 |
| R3 | NL-to-SQL produces wrong-but-valid SQL | H | M | Metric views as canonical definitions; SQL always shown; few-shot examples; eval set; framing: "assistant, not oracle" | 5 |
| R4 | Sandbox bypass via unexpected DuckDB feature | L | H | Validator + materialized Gold + external access off + locked config; adversarial tests against both layers; upgrade DuckDB deliberately | 5 |
| R5 | Windows-specific breakage (paths, `os.replace` locking, encodings) | M | M | `pathlib` everywhere; UTF-8 explicit; you run the Windows checklist each phase; CI could add a Windows runner (free on public repo) | 2+ |
| R6 | UCI dataset quirks differ from assumptions (columns, encodings) | M | M | Contract verified against the real file in Phase 3 before writing models | 3 |
| R7 | SQLite/Postgres dialect drift | M | M | Portable SQLAlchemy types; Postgres CI from P1 | 2, R1 |
| R8 | Free-tier terms change (e.g. HF Docker now paid) | H | M | Facts dated in DEPLOYMENT.md; re-verify before deploying; stateless demo design | 7, R1 |
| R9 | Scope creep from "enterprise" ambitions | H | M | P0/P1/P2 discipline; ADRs required for new infra | All |
| R10 | Prompt injection via documents | M | M | No-tools RAG, per-org retrieval, citation checks, plain-text rendering | 6 |
| R11 | Learning goal lost in speed (you can't explain the code) | M | H | Each phase report includes a "how it works" walkthrough + 3 likely interview questions | All |
| R12 | Secrets leaked into git | L | H | env-only, gitleaks in CI, `.env` ignored from first commit | 2 |
| R13 | Push access to GitHub unavailable from cloud session | H | L | Git bundle hand-off each phase | All |

## 7. Definition of done
**Every phase:** scope items implemented (no disguised placeholders) · tests written first where practical and
passing locally (actual output reported) · ruff + mypy clean · docs/ADRs updated · security checklist
(SECURITY §12) for touched areas · committed with clear messages · bundle delivered · manual verification
checklist provided · open issues listed.

| Phase | Additional DoD |
|---|---|
| 2 | `uv sync && uv run pytest` passes on fresh clone; `/health` returns 200; CI workflow green or its failure reported; `.env.example` present; no secrets |
| 3 | Golden fixture tests pass; run-twice idempotency test passes; quality report persisted; real UCI run timing recorded with hardware; failed run leaves previous Gold intact (tested) |
| 4 | Every dashboard number comes from the metric registry; API p95 measured; dashboard usable by keyboard; vitest passing |
| 5 | Adversarial corpus 100% blocked by validator; sandbox-alone subset blocked; fake-provider flow tests pass; real Groq call demonstrated manually (or reported as blocked) |
| 6 | Cited answer + refusal tests pass; deleted document not retrievable (tested); hit@k on small eval reported |
| 7 | Playwright e2e passes; `/security-review` findings resolved or recorded; README quickstart verified on your Windows machine; demo rehearsed with timing |

## 8. Phase 1 review log
An independent review of these docs (2026-11-24) raised 5 high, 8 medium and 8 low findings. Resolved in
the docs: transactional publish via `published_run_id` instead of pointer files (Windows `os.replace`
issue); single sandboxed DuckDB connection config for all Gold readers (DuckDB rejects mixed configs —
verified); spike evidence committed under `docs/spikes/`; quality rules split into row-level quarantine vs
run-level gates; localhost CSRF/DNS-rebinding hardening; plain-text AI output to close Markdown-image
exfiltration; RAG ACL-before-ranking, calibrated relevance gate, versioned index; `WITH RECURSIVE`
banned and cost attacks assigned to timeouts; schema fixes (run inputs table, stage values, partial unique
indexes, publish pointer, cascade rules); scope trims (PDF stretch, no circuit breaker, Playwright local).
**Open for the product owner:** upload semantics, metric definitions, within-batch duplicates, RAG priority,
approval cadence, Groq key timing (see the Phase 1 report).

## 9. Interview value map
| Area | Where it shows up | What you can explain |
|---|---|---|
| Python | FastAPI services, typed DTOs, provider protocol, tests | Interfaces, dependency injection, async I/O for LLM calls, error handling |
| SQL | Silver/Gold models, metric definitions, window functions for dedup/first-order, DQ rules as SQL | Grain, joins, dedup with `ROW_NUMBER()`, NULL semantics in metrics |
| ETL | Bronze → Silver → Gold, quarantine, idempotent re-runs | Immutable raw, atomic publish, reprocessing |
| Data warehousing | Star schema (fact_sales, dims, dim_date), aggregates | Kimball grain decisions, conformed dimensions, why OLAP ≠ OLTP |
| PySpark | P1 Spark implementation of the same models | DataFrame API vs SQL, partitioning, when Spark is justified (and when not — our ADR) |
| Databricks | Free Edition notebooks, Unity Catalog, Delta | Lakehouse concepts; honest limits of Free Edition |
| ML | P1 segmentation, forecasting with baseline, inactivity with time split | Leakage, baselines, backtesting, choosing metrics |
| LLMs | Provider abstraction, retries, token/latency logging, budgets | Rate limits, determinism (temperature 0), cost/quotas, model churn |
| RAG | BM25, chunking, citations, refusal threshold | Why lexical first, evaluation (hit@k), hallucination controls |
| BI | Metric registry, dashboard, consistent definitions | Semantic layer concept, single source of truth |
| Cloud fundamentals | Free-tier analysis, stateless demo, secrets, cold starts, object storage | Trade-offs of serverless/free hosting, persistence, scaling path |
| Security | Threat model, SQL sandbox, tenant isolation, prompt injection | Defence in depth, least privilege, verified (not assumed) controls |
| Engineering ownership | ADRs, risk register, DoD, honest reporting, tests | Making and documenting trade-offs under constraints |

For an **Associate Analyst** interview specifically, lead with: metric definitions, SQL models, data quality,
and dashboard insights; use the AI and architecture parts as depth when asked.
