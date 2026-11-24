# ADR-0016: Authentication approach (built-in vs hosted)

- **Status:** Proposed (decide in P1)
- **Date:** 2026-11-24

## Context (why we need it)
P1 needs sign-in, sessions and RBAC; mistakes here are high-impact.

## Decision (why selected)
Leaning: built-in auth (argon2id, short-lived JWT access token, rotating refresh token in httpOnly cookie, CSRF protection) to avoid vendor lock-in; final decision at P1 start after reviewing current free hosted options.

## Alternatives considered
Hosted auth (e.g. Supabase Auth free tier) — less custom security code, but vendor coupling and pausing behavior; OAuth-only sign-in via GitHub/Google (simple, but B2B users may need email login).

## Current limitations
Built-in auth requires careful implementation and testing (password reset, lockout, token rotation).

## Revisit / replace when
Enterprise SSO (SAML/OIDC) requirements → add an IdP integration or a hosted identity provider.
