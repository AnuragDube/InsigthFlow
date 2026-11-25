from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from insightflow.analytics.groq_provider import GroqQuestionProvider
from insightflow.api.app import create_app
from insightflow.core.settings import Settings
from pipeline_helpers import published_fixture_gold

QUESTION = "What did we earn from sales?"


@pytest.mark.parametrize(
    ("upstream_status", "content", "api_status"),
    [
        (200, '{"metric": "gross_revenue"}', 200),
        (200, '{"metric": null}', 422),
        (200, '{"metric": "unregistered_metric"}', 422),
        (200, '{"metric": "gross_revenue", "extra": "unexpected"}', 503),
        (200, "invalid response", 503),
        (200, "x" * 16_384, 503),
        (429, "upstream provider detail", 503),
    ],
)
def test_groq_provider_over_questions_api(
    settings: Settings, upstream_status: int, content: str, api_status: int
) -> None:
    calls = 0

    def upstream(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-only"
        payload = json.loads(request.content)
        assert payload["model"] == "mock-model"
        user_input = json.loads(payload["messages"][1]["content"])
        assert set(user_input) == {"question", "metrics"}
        assert user_input["question"] == QUESTION
        assert len(user_input["metrics"]) == 10
        return httpx.Response(
            upstream_status, json={"choices": [{"message": {"content": content}}]}
        )

    with httpx.Client(transport=httpx.MockTransport(upstream)) as http_client:
        provider = GroqQuestionProvider(http_client, SecretStr("test-only"), "mock-model")
        with TestClient(create_app(settings, question_provider=provider)) as client:
            _, _, dataset = published_fixture_gold(settings)
            response = client.post(
                f"/api/v1/datasets/{dataset}/questions",
                json={"question": QUESTION, "from": "2010-12-04", "to": "2010-12-06"},
                headers={"X-InsightFlow-Client": "web"},
            )
    assert calls == 1
    assert response.status_code == api_status
    if api_status == 200:
        assert response.json()["value"] == pytest.approx(50.805)
    elif api_status == 503:
        assert response.json()["type"] == "/errors/question-provider-unavailable"
        assert "upstream provider detail" not in response.text
