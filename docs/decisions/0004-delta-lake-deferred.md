# ADR-0004: Delta Lake deferred; Parquet with atomic publish in P0

- **Status:** Accepted
- **Date:** 2026-11-24

## Context (why we need it)
Silver/Gold must never be partially published, and runs must be reproducible. Delta Lake (via delta-rs) offers ACID, MERGE, schema enforcement and time travel.

## Decision (why selected)
P0 uses plain Parquet with per-run directories and an atomic `_current` pointer (write temp + `os.replace`), single writer per dataset enforced in the metadata DB. Delta is evaluated in P1 alongside the Databricks path.

## Alternatives considered
Adopt `deltalake` 1.x now (adds a dependency and the DuckDB `delta` extension, which needs network on first install and conflicts with our sandbox's no-autoload setting); Apache Iceberg (more catalog machinery).

## Current limitations
No concurrent writers; no incremental MERGE; time travel limited to the last N kept runs.

## Revisit / replace when
Concurrent writers, incremental/CDC sources where full rebuild is too slow (>~5 min), audit 'as-of' requirements, or sharing tables with Databricks. See DATA_ARCHITECTURE §5.
