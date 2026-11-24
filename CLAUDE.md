# InsightFlow — durable project rules

Modular-monolith Data & AI intelligence platform. First domain: e-commerce analytics.
Detailed design lives in `docs/` (start at `docs/ARCHITECTURE.md`); decisions in `docs/decisions/`.

## Non-negotiables
- ₹0 budget: no paid APIs, paid cloud, paid DBs, local LLMs, or Ollama. Flag anything that needs a card.
- Primary dev workflow must not require Docker, Java, Spark or a local LLM. Target machine: Windows 11, 16 GB RAM.
- Never commit secrets. Config comes from environment / `.env` (gitignored); keep `.env.example` current.
- Work one phase at a time; inspect before changing; wait for approval between phases.
- TDD where practical. Never report test results that were not actually run.
- No placeholder code presented as finished. Unfinished work is marked `NotImplementedError` + roadmap entry.

## Architecture rules
- Module boundaries: modules talk through their public `service.py` / interfaces, never each other's internals.
- Every tenant-owned record and every analytical path carries `org_id`. No query without an org context.
- Application metadata (PostgreSQL/SQLite via SQLAlchemy) is separate from analytical data (Parquet + DuckDB).
- Medallion: Bronze is immutable and append-only; Silver/Gold are rebuilt deterministically and idempotently.
- Business metrics are defined once in the domain metric registry; dashboard, API and NL-to-SQL all use it.
- LLM access only through `ai/llm` provider interface. Tests use the fake provider, never the network.
- Uploaded documents and LLM-generated SQL are untrusted input. Generated SQL runs only on the per-org,
  read-only, external-access-disabled DuckDB connection after sqlglot validation.
- Errors returned to clients are RFC 9457 problem+json with a correlation id; never stack traces.

## Conventions
- Python 3.12, `uv` for env/deps, `ruff` (lint+format), `mypy`, `pytest`.
- Frontend: React + Vite + TypeScript, `vitest`, Playwright for e2e.
- Commit small and often, conventional commit prefixes (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- When a design decision changes, update the relevant doc and add/supersede an ADR in the same commit.
