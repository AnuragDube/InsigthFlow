#!/usr/bin/env bash
# Local quality gate: stops at the first failure (same steps as CI).
set -euo pipefail
uv run ruff check . -q
uv run ruff format --check . -q
uv run mypy
uv run pytest
if command -v npm >/dev/null 2>&1 && [ -d frontend/node_modules ]; then
  (cd frontend && npm run -s typecheck && npm test --silent && npm run -s build >/dev/null)
fi
