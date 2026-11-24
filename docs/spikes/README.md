# Spikes (throwaway experiments, not application code)

Evidence for claims made in the design docs. Each spike is re-runnable; outputs are captured as observed.
They become proper automated tests in the phase noted.

| Spike | Date | Claim it supports | Becomes tests in |
|---|---|---|---|
| [duckdb_sandbox_spike.py](duckdb_sandbox_spike.py) → [output](duckdb_sandbox_spike.output.txt) | 2026-11-24 | SECURITY §5 sandbox behaviour (DuckDB 2.0.1, sqlglot 30.34.0); views over Parquet fail in sandbox; same-file connections must share config | Phase 5 |
| [postgres_dataset_binding_check.sql](postgres_dataset_binding_check.sql) → [output](postgres_dataset_binding_check.output.txt) | 2026-11-24 | Revised schema: published run and run inputs bound to the same org **and** data source (3 cross-dataset writes rejected, 1 valid write accepted) | Phase 2 |
| [postgres_schema_check.sql](postgres_schema_check.sql) | 2026-11-24 | DATA_ARCHITECTURE §7 composite-FK isolation and single-active-run index (run by hand on PostgreSQL 16; observed errors recorded in the file) | Phase 2 (migration tests) |

An `allowed_directories` variant was also tried by hand on 2026-11-24 (views resolved inside the allowed
directory; reads outside it were blocked; the setting could not be changed after `lock_configuration`).
That run was not scripted here; it is not relied on because Gold is materialized instead.

**Caveat:** all spikes ran in the Linux cloud dev container, not on the owner's Windows machine. They are
re-run on Windows as part of the Phase 2 checklist before being relied on there.
