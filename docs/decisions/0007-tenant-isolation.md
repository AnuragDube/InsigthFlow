# ADR-0007: Organization-aware data ownership from day one

- **Status:** Proposed — pending Phase 1 approval
- **Date:** 2026-11-24

## Context (why we need it)
The product will become multi-tenant; retrofitting tenancy is a classic rewrite trigger. Cross-org leakage is the worst failure mode.

## Decision (why selected)
`org_id` on every tenant row with composite FKs `(org_id, id)`; repositories require an `OrgContext`; org derived from the principal, never from client input; analytical data physically separated per org (own directory and Gold DB file); PostgreSQL RLS added in P2 as defence in depth.

## Alternatives considered
Database-per-tenant (strong isolation, heavy operations on free tiers); schema-per-tenant (migration complexity); shared tables without composite FKs (easier, weaker).

## Current limitations
Repository discipline must be tested; P0 has a single demo org so isolation is designed but only fully exercised in P1 tests.

## Revisit / replace when
Enterprise customers requiring dedicated infrastructure → database/storage-per-tenant option for that tier.
