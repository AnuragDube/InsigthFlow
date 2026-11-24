# InsightFlow

A modular Data & AI intelligence platform: ingest business data, process it through a governed
Bronze → Silver → Gold pipeline with data-quality gates, explore deterministic metrics on a dashboard,
ask questions in plain English (answered with visible, validated SQL), and query your documents with
cited answers. First domain: e-commerce analytics.

> **Status:** Phase 1 — architecture and planning. No application code yet.
> This is an MVP under active development, **not** production-ready. See [docs/SECURITY.md](docs/SECURITY.md).

## Documentation
| Doc | Contents |
|---|---|
| [Status](docs/STATUS.md) | Current phase, pending decisions, blockers — start here |
| [PRD](docs/PRD.md) | Vision, users, journeys, P0/P1/P2 scope, requirements |
| [Architecture](docs/ARCHITECTURE.md) | Modules, technology selection, API design, AI architecture |
| [Data architecture](docs/DATA_ARCHITECTURE.md) | Medallion design, storage layout, metrics, quality, metadata schema |
| [Security](docs/SECURITY.md) | Threat model, SQL sandbox, prompt injection, tenant isolation |
| [Deployment](docs/DEPLOYMENT.md) | Free-tier research, environments, what cannot be free |
| [Roadmap](docs/ROADMAP.md) | Repo structure, roadmaps, test strategy, risks, definition of done |
| [Decisions](docs/decisions/README.md) | Architecture decision records |

## Constraints
₹0 budget · no paid APIs or local LLMs · runs on Windows 11 / 16 GB RAM without Docker, Java or Spark.
