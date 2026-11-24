# ADR-0008: Transformations as SQL model files with a small Python runner

- **Status:** Proposed — pending Phase 1 approval
- **Date:** 2026-11-24

## Context (why we need it)
Silver/Gold logic must be readable, testable, reproducible, and portable to Spark.

## Decision (why selected)
One SQL file per model in the domain pack, executed in declared order by a tiny runner that handles run directories, quality gates and publish. Layout mirrors dbt conventions to keep migration cheap.

## Alternatives considered
dbt-core + dbt-duckdb (lineage, docs, tests — but a large dependency and learning curve inside a 3-day window); Python DataFrame transforms (less readable for analysts); stored procedures (engine lock-in).

## Current limitations
We own a small amount of orchestration code; no built-in lineage docs.

## Revisit / replace when
More than ~25 models, analysts authoring models, or need for lineage/docs → migrate to dbt.
