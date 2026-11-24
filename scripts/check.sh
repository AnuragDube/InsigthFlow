#!/usr/bin/env bash
# Local quality gate: stops at the first failure (same steps as CI).
set -euo pipefail
uv run ruff check . -q
uv run ruff format --check . -q
uv run mypy
uv run pytest
