# ADR-0013: React + Vite + TypeScript frontend

- **Status:** Accepted
- **Date:** 2026-11-24

## Context (why we need it)
Need an interactive dashboard and assistant UI that will not be rewritten for the commercial product.

## Decision (why selected)
Static SPA: React, Vite, TypeScript, TanStack Query for server state, Recharts for charts; deployable to free static hosting.

## Alternatives considered
Streamlit (fastest for the interview, but a rewrite later and harder to secure/customize); Next.js (SSR not needed, more hosting coupling); Apache ECharts (more powerful; heavier API — reconsider for advanced charts).

## Current limitations
More code than Streamlit within the interview window.

## Revisit / replace when
Need for SSR/SEO pages (marketing site) → separate site; heavy charting needs → ECharts.
