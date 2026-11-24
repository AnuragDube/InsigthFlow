# Architecture Decision Records

Format: Context · Decision · Alternatives · Limitations · Revisit when. New decisions get the next number; superseded ADRs are kept and marked.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith architecture | Proposed |
| [0002](0002-python-fastapi-uv.md) | Python 3.12, FastAPI and uv | Proposed |
| [0003](0003-duckdb-parquet-analytics.md) | DuckDB + Parquet as the analytical engine and storage | Proposed |
| [0004](0004-delta-lake-deferred.md) | Delta Lake deferred; Parquet with atomic publish in P0 | Proposed |
| [0005](0005-pyspark-databricks-optional.md) | PySpark on Databricks Free Edition as an optional parity implementation | Proposed (P1) |
| [0006](0006-metadata-sqlite-postgres.md) | Metadata store: SQLAlchemy with SQLite locally and PostgreSQL when deployed | Proposed |
| [0007](0007-tenant-isolation.md) | Organization-aware data ownership from day one | Proposed |
| [0008](0008-sql-models-runner.md) | Transformations as SQL model files with a small Python runner | Proposed |
| [0009](0009-metric-registry.md) | Deterministic metric registry (lightweight semantic layer) | Proposed |
| [0010](0010-llm-provider-groq.md) | LLM provider abstraction with Groq via OpenAI-compatible HTTP | Proposed |
| [0011](0011-nl2sql-defense-in-depth.md) | NL-to-SQL with validation and sandboxed read-only execution | Proposed |
| [0012](0012-bm25s-retrieval.md) | Lexical BM25 retrieval with bm25s | Proposed |
| [0013](0013-react-vite-frontend.md) | React + Vite + TypeScript frontend | Proposed |
| [0014](0014-demo-dataset.md) | Demo dataset: UCI Online Retail II plus synthetic fixtures | Proposed |
| [0015](0015-free-deployment.md) | Local-first demo; optional stateless read-only public demo | Proposed |
| [0016](0016-authentication.md) | Authentication approach (built-in vs hosted) | Proposed (decide in P1) |
| [0017](0017-batch-semantics-and-reruns.md) | Batch semantics, multiplicity rule and durable re-runs | Proposed |
