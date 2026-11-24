# ADR-0014: Demo dataset: UCI Online Retail II plus synthetic fixtures

- **Status:** Proposed — pending Phase 1 approval
- **Date:** 2026-11-24

## Context (why we need it)
Need realistic, messy e-commerce data that can be used commercially, plus tiny deterministic test data.

## Decision (why selected)
UCI Online Retail II (CC BY 4.0, ~1.07M lines, 2009–2011, UK online retailer; known missing values) for demos, fetched by a script (not committed). It is reportedly published as an `.xlsx` workbook with two yearly sheets (to confirm on download), so the script converts it once to CSV with openpyxl (dev-only dependency; slow on ~1M rows, run once). The UCI download host is currently blocked in the cloud dev environment — network access is requested in Phase 3, or the file is downloaded manually. Hand-built small fixtures with expected outputs for tests.

## Alternatives considered
Olist Brazilian e-commerce (richer schema, but CC BY-NC-SA 4.0 — non-commercial, share-alike); fully synthetic data only (less convincing in a demo).

## Current limitations
Single transactional table; GBP only; exact column names to be verified against the downloaded file in Phase 3.

## Revisit / replace when
Real beta customers' data replaces it; a richer CC BY dataset or a synthetic generator could add multi-table scenarios.
