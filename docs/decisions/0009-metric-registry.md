# ADR-0009: Deterministic metric registry (lightweight semantic layer)

- **Status:** Proposed — pending Phase 1 approval
- **Date:** 2026-11-24

## Context (why we need it)
Dashboard, API and NL-to-SQL must agree on what 'revenue' or 'repeat rate' means.

## Decision (why selected)
Metrics defined once in `metrics.yaml` (name, SQL expression, source, time column, dimensions, unit, description), compiled to SQL by `analytics`, exposed as `metric_*` views inside the materialized Gold DuckDB file for NL-to-SQL, and covered by golden tests.

## Alternatives considered
dbt Semantic Layer / MetricFlow, Cube (powerful, heavier/hosted); definitions hardcoded in endpoints (drift).

## Current limitations
Limited expressiveness (no complex derived metric graphs initially).

## Revisit / replace when
Many metrics with derived dependencies or external BI tools needing a semantic API → adopt MetricFlow or Cube.
