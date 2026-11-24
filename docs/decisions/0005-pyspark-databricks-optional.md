# ADR-0005: PySpark on Databricks Free Edition as an optional parity implementation

- **Status:** Proposed — pending Phase 1 approval (implementation in P1)
- **Date:** 2026-11-24

## Context (why we need it)
Spark/Databricks skills are valuable to demonstrate, but Spark is unjustified for our data size and painful on Windows (Java, winutils, RAM).

## Decision (why selected)
A second implementation of the same Silver/Gold logic in PySpark, run on Databricks Free Edition and in an optional CI job (GitHub runners include Java). Must match DuckDB on shared fixtures (parity tests). Not on the primary dev path.

## Alternatives considered
Local PySpark (heavy, Windows friction); skip Spark entirely (loses interview value); Spark only as a disconnected notebook (rejected by product owner — must share fixtures and rules).

## Current limitations
Databricks Free Edition is non-commercial, quota-limited (compute stops for the day), no SLA. Two implementations must be kept in sync.

## Revisit / replace when
Real data volumes need distributed compute → paid Databricks or similar; then Spark could become the primary engine for large orgs behind the engine interface.
