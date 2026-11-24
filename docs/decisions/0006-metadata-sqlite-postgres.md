# ADR-0006: Metadata store: SQLAlchemy with SQLite locally and PostgreSQL when deployed

- **Status:** Accepted
- **Date:** 2026-11-24

## Context (why we need it)
Application metadata needs relational integrity. P0 has little metadata (no auth yet) and the dev machine should not need a database server install.

## Decision (why selected)
SQLAlchemy 2 + Alembic with portable types. SQLite file for local dev/tests in P0; PostgreSQL (Neon free tier, no card) for deployed environments; CI tests on both from P1. Postgres-only features (RLS, citext) in Postgres-specific migrations.

## Alternatives considered
PostgreSQL everywhere (most faithful, but needs local install or always-online cloud DB in dev); DuckDB for metadata (wrong workload: single writer); hosted Supabase (adds pausing behavior and vendor APIs).

## Current limitations
Dialect drift risk (types, locking, partial-index semantics); some isolation guarantees (RLS) only exist on Postgres.

## Revisit / replace when
As soon as auth/multi-user data exists (P1), Postgres becomes required in CI; if drift causes bugs, drop SQLite and use Postgres everywhere.
