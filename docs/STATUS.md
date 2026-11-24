# Project status — read this first when resuming

Last updated: 2026-11-24 18:55 UTC (Wed 25 Nov, 00:25 IST) · Updated by: Claude Code (lead engineer)

## Where we are
- **Phase 1 (architecture): approved 2026-11-24.** Now on M1 (Phases 2+3).
- Orchestration transferred from ChatGPT on 2026-11-24 ([handover](handover/2026-11-24-chatgpt-handover.md)).
  Its appendix was identical to the repo docs; its preamble's open issues were reconciled (see below).
- Working title per handover: "Data Intelligence Platform". `InsightFlow`/`insightflow` remain the
  repo and package identifiers until a deliberate rename (not worth time now).
- Interview: Fri 27 Nov 2026 (Associate Analyst) — *owner to confirm still relevant*.

## Evidence of completed work (all in git)
| Item | Evidence |
|---|---|
| PRD, architecture, data architecture, security, deployment, roadmap | `docs/*.md` |
| ADRs 0001–0017 (all *Proposed*) | `docs/decisions/` |
| DuckDB 2.0.1 sandbox behaviour | `docs/spikes/duckdb_sandbox_spike.py` + `.output.txt` (Linux container) |
| Metadata schema applies on PostgreSQL 16 (18 tables); org- and dataset-binding FKs reject cross-org/cross-dataset writes | `docs/spikes/postgres_*` |
| Independent design review (21 findings) resolved | ROADMAP §8 review log |
| Not yet verified on the owner's Windows machine | everything above |

## Handover issues reconciled on 2026-11-24
- Silver dedup contradiction → multiset `max(k,m)` rule across batches; within-batch repeats kept (ADR-0017).
- Queued follow-up vs single-active-run index → durable `rerun_requested_at` marker; coalesced re-run.
- Published run / run inputs bound to same org **and** data source (composite FKs, verified on PG16).
- Explicit `dataset_id` on analytics endpoints; UI defaults to most recently published dataset.
- Metrics: inclusive date ranges, `NULLIF` on ratios, unknown-customer dimension member, value-based
  `return_rate_value` named as such; sign conventions to verify against real data in Phase 3.
- LLM budget: global + per-org; atomic reservation deferred until multi-worker (P2).
- RAG: citation validity ≠ faithfulness → sentence/citation term-overlap check + manual faithfulness eval.
- Public demo: no unrestricted quota-consuming AI endpoint; public/synthetic data only; owner approval required.

## Owner decisions
- 2026-11-24: Owner delegated full technical ownership ("take decisions on your own"). Accepted defaults:
  Phase 1 architecture incl. React; ADR-0001…0017 Accepted (0016 auth still decided at P1 start);
  ADR-0017 upload semantics; metric definitions as proposed (sign conventions verified in Phase 3);
  Phases 2+3 = one milestone; interview Fri 27 Nov, RAG first to cut.
- Still escalated to owner: spending, credentials, external deployment, destructive actions.

## Next milestone (proposed): M1 = Phase 2 + 3 "Data foundation"
See the latest report in conversation / ROADMAP §3. Starts only after decisions 1–2.

## Blockers / environment
- Cloud dev container cannot push to GitHub → hand-off via git bundle each milestone (owner pushes).
- Network blocks `archive.ics.uci.edu` (dataset) and `api.groq.com` (LLM) — request access when needed,
  or owner downloads the dataset manually.
- Context7 MCP not connected; docs verified from package metadata, spikes and official sites instead.

## How to resume / test (once code exists)
```bash
git log --oneline | head        # what was done last
uv sync                         # (from Phase 2) install deps
uv run pytest                   # (from Phase 2) run tests
```
