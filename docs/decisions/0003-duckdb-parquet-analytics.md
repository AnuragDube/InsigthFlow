# ADR-0003: DuckDB + Parquet as the analytical engine and storage

- **Status:** Accepted 2026-11-24
- **Date:** 2026-11-24

## Context (why we need it)
Need fast SQL analytics over ~1M+ rows on a laptop, open storage, no server, and a sandboxable read-only execution path for generated SQL.

## Decision (why selected)
Parquet files for Bronze/Silver/Gold; DuckDB executes models and quality rules; Gold is materialized inside a per-org DuckDB file for serving. All access goes through an `AnalyticalEngine` interface.

## Alternatives considered
Polars (excellent DataFrames, but SQL sandboxing is weaker); SQLite (row store, slow aggregations); PostgreSQL (OLTP, costly on free tiers for analytics); local PySpark (Java, RAM, slow startup); cloud warehouses (paid).

## Current limitations
Single node; single writer per DuckDB file; not a concurrent multi-user server; major-version upgrades (2.0 is new) need deliberate testing.

## Revisit / replace when
Data exceeds what one machine handles comfortably (hundreds of GB), many concurrent writers, or customers require a managed warehouse → MotherDuck, ClickHouse, Databricks SQL or BigQuery behind the same interface.
