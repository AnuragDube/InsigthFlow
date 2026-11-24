# ADR-0001: Modular monolith architecture

- **Status:** Accepted 2026-11-24
- **Date:** 2026-11-24

## Context (why we need it)
We need one platform with ingestion, pipelines, analytics, AI and (later) auth/ML, built by one developer on a ₹0 budget, with a path to a commercial multi-product SaaS.

## Decision (why selected)
One FastAPI backend process + one static React frontend. Code organized into modules with public `service.py` interfaces and Pydantic DTOs; modules own their tables and never import each other's internals.

## Alternatives considered
Microservices (independent scaling, but network failures, distributed auth, N deployments — unjustified at this scale and impossible on one free instance); unstructured monolith (fast now, rewrite later — violates 'no disposable project').

## Current limitations
Single process: a CPU-heavy pipeline can compete with API latency; in-process background tasks don't survive restarts. Boundaries rely on discipline (import-linter can enforce later).

## Revisit / replace when
A module needs independent scaling or release cadence (likely first: pipeline workers, then AI services), or a team grows beyond ~5 engineers.
