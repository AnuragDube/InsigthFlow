# ADR-0012: Lexical BM25 retrieval with bm25s

- **Status:** Accepted 2026-11-24
- **Date:** 2026-11-24

## Context (why we need it)
RAG needs retrieval without paid embeddings or local model downloads.

## Decision (why selected)
`bm25s` (numpy-only, released 2026-10) with a per-org persisted index rebuilt on document changes; heading-aware chunking; score threshold for refusal.

## Alternatives considered
rank_bm25 (last release 2022); DuckDB FTS extension (needs extension install); PostgreSQL full-text search (not BM25, ties RAG to Postgres); embeddings (paid API or local model download — excluded).

## Current limitations
No semantic matching (synonyms/paraphrases); full index rebuild per change (fine for small corpora).

## Revisit / replace when
Retrieval eval shows recall gaps, or corpora grow large → hybrid lexical + embeddings (free/self-hosted option re-evaluated) and possibly a vector store (P2).
