"""Opt-in hosted metric selection through Groq's OpenAI-compatible endpoint."""

from __future__ import annotations

import json
from dataclasses import asdict

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from insightflow.analytics.question_provider import MetricOption
from insightflow.core.errors import QuestionProviderUnavailable

_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_MAX_RESPONSE_BYTES = 16_384


class _Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str | None


class GroqQuestionProvider:
    """Return a metric ID for server-side validation. The caller owns the HTTP client."""

    def __init__(self, client: httpx.Client, api_key: SecretStr, model: str) -> None:
        self._client = client
        self._key = api_key
        self._model = model

    def select_metric(self, question: str, options: tuple[MetricOption, ...]) -> str | None:
        request = {
            "model": self._model,
            "temperature": 0,
            "max_completion_tokens": 96,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        'Return a JSON object with exactly one key, "metric". Select an ID from '
                        "the supplied metrics only when it fully answers the question. Return "
                        "null for ambiguous questions, forecasts, grouping, comparisons or other "
                        "unsupported filters. Do not return SQL or an explanation."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"question": question, "metrics": [asdict(option) for option in options]}
                    ),
                },
            ],
        }
        try:
            with self._client.stream(
                "POST",
                _ENDPOINT,
                headers={"Authorization": f"Bearer {self._key.get_secret_value()}"},
                json=request,
                timeout=5.0,
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=_MAX_RESPONSE_BYTES):
                    body.extend(chunk)
                    if len(body) > _MAX_RESPONSE_BYTES:
                        raise ValueError("provider response too large")
            content = json.loads(body)["choices"][0]["message"]["content"]
            return _Selection.model_validate_json(content).metric
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise QuestionProviderUnavailable(
                "The question provider could not return a metric selection. Try again later."
            ) from exc
