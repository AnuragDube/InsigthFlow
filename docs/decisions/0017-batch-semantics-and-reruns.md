# ADR-0017: Batch semantics, multiplicity rule and durable re-runs

- **Status:** Accepted 2026-11-24
- **Date:** 2026-11-24

## Context (why we need it)
Uploads can overlap (e.g. two exports covering the same week), contain legitimate repeated lines, or be
wrong. The first draft said both "deduplicate exact duplicates" (collapses legitimate repeats) and "queue a
follow-up run" (impossible: the single-active-run unique index covers `queued` too). The ChatGPT handover
and the independent review both flagged these.

## Decision (why selected)
1. Uploads append batches; batches can be deactivated; Bronze is never modified.
2. Batches combine as multisets: an identical line kept `max(k, m)` times across batches; repeats within a
   batch kept and reported as a warning.
3. Uploads during a run set a durable `data_sources.rerun_requested_at` marker; the runner (and the startup
   recovery sweep) starts one coalesced follow-up run. `uq_one_active_run` stays as is.
4. Published run and run inputs are bound to the same org **and** data source by composite FKs
   (verified on PostgreSQL 16, see `docs/spikes/`).

## Alternatives considered
- Replace-on-upload (simple, but loses history and makes incremental exports impossible).
- Full dedup to one copy (double counting fixed, but legitimate repeated lines lost).
- Sum across batches (overlapping exports double count revenue).
- A separate run-request queue table (more general; unnecessary while one runner exists).

## Current limitations
`max(k, m)` assumes overlapping batches are re-exports of the same source. If a later batch legitimately
adds more identical copies of an already-seen line, only the larger count survives. It is accepted because
identical lines share invoice number *and* timestamp.

## Revisit / replace when
Connectors provide primary keys or change data capture (use keys and MERGE, see ADR-0004), or multiple
runners exist (move to a run-request queue table).
