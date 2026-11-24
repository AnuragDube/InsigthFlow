# ADR-0015: Local-first demo; optional stateless read-only public demo

- **Status:** Accepted
- **Date:** 2026-11-24

## Context (why we need it)
Free hosts sleep, have ephemeral disks and changing terms; a demo must not fail during the interview.

## Decision (why selected)
Interview demo runs locally with recorded fallback and offline AI mode. Optional public demo is read-only and stateless (Gold built from bundled sample). Persistent private beta in P1 uses Neon (no card) and Backblaze B2. Card-required or non-commercial services are excluded from the commercial path. See DEPLOYMENT.md.

## Alternatives considered
Hugging Face Docker Space (now requires PRO); Fly.io (card required); Render free Postgres (expires after 30 days).

## Current limitations
Cold starts, quotas, no SLA; not suitable for paying customers.

## Revisit / replace when
Paying customers or beta usage that needs uptime → paid managed hosting.
