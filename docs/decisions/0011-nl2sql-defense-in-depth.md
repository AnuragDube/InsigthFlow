# ADR-0011: NL-to-SQL with validation and sandboxed read-only execution

- **Status:** Proposed — pending Phase 1 approval
- **Date:** 2026-11-24

## Context (why we need it)
LLM-generated SQL is untrusted code; it must not modify data, read files, or reach other orgs.

## Decision (why selected)
sqlglot AST validation (single SELECT, Gold allowlist, no table functions/system catalogs, LIMIT) + execution on a read-only per-org DuckDB file with external access disabled, extensions off and configuration locked; Gold is materialized so no file access is needed; timeout/memory caps; SQL shown and audited.

## Alternatives considered
Validation only (single layer); LLM generates parameters for pre-written queries only (safe but far less flexible — kept as fallback idea); read-only DB user in Postgres (we don't serve analytics from Postgres).

## Current limitations
Validator maintenance as DuckDB evolves; semantically wrong-but-safe SQL remains possible.

## Revisit / replace when
If a bypass is found or the function surface grows, switch to a strict function allowlist and/or a query-template approach for untrusted tenants.
