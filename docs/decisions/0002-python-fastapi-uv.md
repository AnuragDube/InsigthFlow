# ADR-0002: Python 3.12, FastAPI and uv

- **Status:** Proposed — pending Phase 1 approval
- **Date:** 2026-11-24

## Context (why we need it)
Need a backend language strong in data/ML/AI with typed HTTP APIs, runnable on Windows without Docker.

## Decision (why selected)
Python 3.12 managed by `uv` (installs Python, venv, lockfile). FastAPI + Pydantic v2 for the API.

## Alternatives considered
Django (batteries included, but ORM/admin-centric and heavier); Flask (less typing/validation); Node/TypeScript backend (weaker data/ML ecosystem); Python 3.13 (works; 3.12 chosen as the conservative, widely supported version — the Databricks serverless Python version is unverified and checked in P1).

## Current limitations
FastAPI background tasks are in-process only; async code requires care around blocking DuckDB calls (run in threadpool).

## Revisit / replace when
Needs like a built-in admin back office could justify Django for an admin service; otherwise none foreseen.
