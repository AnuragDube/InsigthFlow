# ADR-0010: LLM provider abstraction with Groq via OpenAI-compatible HTTP

- **Status:** Accepted
- **Date:** 2026-11-24

## Context (why we need it)
NL-to-SQL and RAG need a capable LLM at ₹0 with no local model; providers and models change frequently.

## Decision (why selected)
`LLMProvider` protocol; `OpenAICompatibleProvider` using httpx, configured for Groq (`https://api.groq.com/openai/v1`); `FakeProvider` for tests/offline demo. Model id is configuration. Retries with backoff on 429/5xx, budget guard, per-call token/latency logging without payloads.

## Alternatives considered
Groq SDK (extra dependency, provider-specific); Gemini free tier (different API, data-use terms to check); OpenRouter free models (variable availability); LangChain/LlamaIndex (heavy abstractions for two simple flows).

## Current limitations
Free-tier limits unverified and may change; model deprecations (Llama 3.3 70B shut down 2026-08-16); third-party data processing.

## Revisit / replace when
Paying customers, data-residency/DPA requirements, or quality needs → contracted provider via a new adapter.
