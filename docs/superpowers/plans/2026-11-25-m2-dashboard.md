# M2 Metrics & Dashboard (Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A deterministic metric registry over Gold, a metrics/dashboard API, and a polished React dashboard (KPIs with period comparison, trend, top products, countries, data health, data management) served from the same origin.

**Architecture:** Metric definitions live in the domain pack (`metrics.yaml`). `analytics` compiles them into parameterized SQL and runs it on the sandboxed Gold connection (`open_gold`). The SPA (Vite + React + TS + TanStack Query + Recharts) calls `/api/v1`; in demo mode FastAPI serves the built SPA.

**Tech Stack:** existing backend; frontend: React 19, Vite, TypeScript, TanStack Query, Recharts, Vitest, Playwright (pre-installed browser).

**Spec:** `docs/DATA_ARCHITECTURE.md` §3 (metric definitions, date rules), `docs/ARCHITECTURE.md` §3.2, §5, `docs/SECURITY.md` §1a, §4 (T14 CSP), ADR-0009, ADR-0013.

## Global Constraints
- Date range `from`/`to` are inclusive calendar dates → SQL `invoice_date >= :from AND invoice_date < :to + 1 day`; defaults = full published range.
- Ratios use `NULLIF(denominator, 0)`; a value with no data is `null`, never 0.
- Customer metrics exclude `customer_key = 'UNKNOWN'`.
- Metric names, dimensions and grains are allowlisted from the registry; user values only ever reach SQL as bound parameters.
- All Gold reads go through `open_gold` (sandbox). Analytics endpoints take an explicit `dataset_id`.
- Frontend: no `dangerouslySetInnerHTML`; every API mutation sends `X-InsightFlow-Client: web`.

## Review Focus
1. Date range outside the data (or `from > to`) → `from > to` is a 422; an empty range returns `null`/0 KPIs, not an error — test in Task 2.
2. Dataset with no published run → dashboard shows a clear "load data" state (API 409 `no-published-data`) — test in Tasks 2 and 4.
3. Previous-period comparison when the previous period has no data → delta `null`, rendered as "—" — test in Tasks 1 and 4.
4. Unknown metric/dimension/grain query params → 422, never interpolated — test in Task 2.
5. Large numbers/currency formatting (19.7M GBP, ratios as %) readable on a 360 px phone — check in Task 5.

---

### Task 1: Metric registry and compiler
**Files:** Create `domains/ecommerce/metrics.yaml`, `analytics/{__init__,registry,compiler}.py`; test `unit/test_metrics.py`
**Interfaces:**
- `Metric(name, label, unit: Literal["GBP","count","ratio"], description, kind: Literal["aggregate","formula"], source: str|None, expression: str, dimensions: list[str])`; `load_metrics(pack_name) -> dict[str, Metric]`. Sources: `fact_sales`, `fact_returns` (time `invoice_date`), `dim_customer` (time `first_order_date`), `customer_orders` (virtual: per-customer distinct invoices within range).
- `compute_kpis(con, metrics, start: date, end: date) -> dict[str, Decimal|int|float|None]`; `compute_series(con, metric, start, end, grain: Literal["day","month"]) -> list[(date, value)]`; `compute_breakdown(con, metric, start, end, dimension: Literal["country","product"], limit) -> list[(key, label, value)]`.
- Metrics (P0): gross_revenue, returns_value, net_revenue, orders, average_order_value, units_sold, active_customers, new_customers, repeat_customer_rate, return_rate_value.
- [ ] Tests on fixture Gold (relaxed pipeline): gross 140.445, returns 6.95, net 133.495, orders 7, AOV 140.445/7, units 60, active 4, new 4, repeat 0.25, return_rate 6.95/140.445; 2010-12-01 only → gross 72.64, orders 2; empty range → gross null, orders 0; breakdown country UK 89.64 > NL 39.00 > DE 8.85 > FR 2.955; product top = 22633 (37.00) with its description; month series one point (2010-12-01, 140.445).
- [ ] Implement; commit `feat: deterministic metric registry and compiler`.

### Task 2: Analytics API
**Files:** Create `analytics/service.py`, `api/routers/analytics.py`; modify `api/schemas.py`, `api/app.py`; test `integration/test_api_analytics.py`
**Interfaces:** `GET /api/v1/metrics` (catalog); `GET /api/v1/datasets/{id}/dashboard?from=&to=` → `{range:{from,to,min,max}, kpis:[{name,label,unit,value,previous,change}], trend:[{period,value}] (gross revenue, month grain, day if range ≤ 62 days), top_products, countries, freshness:{run_id, finished_at, quality:{passed,warnings,failed}}}`; `GET /api/v1/datasets/{id}/metrics/{name}/series?from=&to=&grain=`; `GET /api/v1/datasets/{id}/metrics/{name}/breakdown?dimension=&from=&to=&limit=` (limit 1..50).
- previous period = same length immediately before `from`; `change = (value - previous)/|previous|`, null if previous null/0.
- [ ] Tests: values match Task 1 numbers through HTTP; `from>to` 422; unknown metric 404 problem; bad dimension/grain 422; no published data 409 `/errors/no-published-data`; other org's dataset id 404.
- [ ] Implement; commit `feat: dashboard and metrics API`.

### Task 3: Frontend scaffold
**Files:** `frontend/` (Vite React TS), `frontend/src/api/{client,types}.ts`, `frontend/vite.config.ts` (proxy `/api` → 127.0.0.1:8000), vitest setup; test `src/lib/format.test.ts`
- `formatMoney(v, unit)` → `£19.7M`, `£140.45`; `formatRatio` → `25.0%`; `formatChange(null)` → `—`.
- [ ] Commit `feat: frontend scaffold with typed API client`.

### Task 4: Dashboard UI (frontend-design)
**Files:** `frontend/src/{App,pages/Overview,pages/Data,components/*}.tsx`, styles.
- Overview: dataset selector, date range (presets: all, last 3/12 months of data), KPI tiles (value, change vs previous period, definition on hover/focus), revenue trend, top products, countries, data-health strip (last run, status, quality counts). Empty state with "Load sample data" when 409.
- Data: upload CSV, load sample, batches table with activate/deactivate, runs list with stage timings, quality report table.
- [ ] Vitest component tests for empty state + KPI rendering with mocked fetch; `npm run build` passes; commit.

### Task 5: Same-origin serving, CSP, e2e
**Files:** modify `core/settings.py` (`frontend_dist: Path | None`), `api/app.py` (static mount + SPA fallback, security headers: CSP `default-src 'self'; img-src 'self' data:; connect-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy`); `frontend/e2e/dashboard.spec.ts`; test `integration/test_static.py`.
- [ ] Playwright: start uvicorn with fixture sample dir + built SPA → load sample → KPI "Gross revenue" visible with £ value → Data page shows run succeeded. Screenshots at 1440 and 390 width checked by eye.
- [ ] Commit; update README/STATUS; final review + `/security-review`; bundle.
