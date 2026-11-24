# InsightFlow

A modular Data & AI intelligence platform: ingest business data, process it through a governed
Bronze → Silver → Gold pipeline with data-quality gates, explore deterministic metrics on a dashboard,
ask questions in plain English (answered with visible, validated SQL), and query your documents with
cited answers. First domain: e-commerce analytics.

> **Status:** M1 "data foundation" — backend ingestion, Bronze/Silver/Gold pipeline, quality gates and
> API work and are tested; no frontend yet. This is an MVP under active development, **not**
> production-ready, and has **no authentication**: run it on localhost only. See [docs/STATUS.md](docs/STATUS.md).

## Quickstart (Windows 11, PowerShell)
Prerequisites: [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 itself) and git.

```powershell
git clone https://github.com/AnuragDube/InsigthFlow.git
cd InsigthFlow
uv sync                                            # create .venv with pinned dependencies
uv run pytest                                      # run the test suite
uv run python scripts/fetch_sample_data.py         # download + convert UCI sample (~45 MB, ~1 min)
uv run uvicorn insightflow.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Then open http://127.0.0.1:8000/docs (interactive API) and, in that page or with curl:
1. `POST /api/v1/datasets` with `{"name": "UCI Online Retail II"}`
2. `POST /api/v1/datasets/{id}/load-sample`
3. `GET /api/v1/pipeline-runs/{run_id}` (stages, timings) and `/quality` (data-quality report)

Mutating requests need the header `X-InsightFlow-Client: web` (a CSRF guard; the docs page does not
add it, so use curl or the `Invoke-RestMethod` examples in [docs/STATUS.md](docs/STATUS.md)).

Quality gate before committing (Git Bash / Linux / macOS): `scripts/check.sh`.

## Documentation
| Doc | Contents |
|---|---|
| [Status](docs/STATUS.md) | Current phase, pending decisions, blockers — start here |
| [Data profile](docs/DATA_PROFILE.md) | Real-data findings and measured pipeline run |
| [PRD](docs/PRD.md) | Vision, users, journeys, P0/P1/P2 scope, requirements |
| [Architecture](docs/ARCHITECTURE.md) | Modules, technology selection, API design, AI architecture |
| [Data architecture](docs/DATA_ARCHITECTURE.md) | Medallion design, storage layout, metrics, quality, metadata schema |
| [Security](docs/SECURITY.md) | Threat model, SQL sandbox, prompt injection, tenant isolation |
| [Deployment](docs/DEPLOYMENT.md) | Free-tier research, environments, what cannot be free |
| [Roadmap](docs/ROADMAP.md) | Repo structure, roadmaps, test strategy, risks, definition of done |
| [Decisions](docs/decisions/README.md) | Architecture decision records |

## Constraints
₹0 budget · no paid APIs or local LLMs · runs on Windows 11 / 16 GB RAM without Docker, Java or Spark.
