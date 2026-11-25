from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from insightflow.analytics import service
from insightflow.analytics.question_provider import MetricOption
from insightflow.api.app import create_app
from insightflow.core.context import OrgContext
from insightflow.core.errors import ValidationFailed
from insightflow.core.settings import Settings
from insightflow.domains.loader import load_domain_pack
from insightflow.metadata.db import session_scope
from insightflow.metadata.models import QualityResult
from insightflow.metadata.repositories import DataSourceRepo, RunRepo
from insightflow.pipeline.service import request_run, run_pipeline
from insightflow.warehouse.paths import OrgPaths
from pipeline_helpers import ingest_fixtures, published_fixture_gold, setup_source

H = {"X-InsightFlow-Client": "web"}


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def ds(client: TestClient, settings: Settings) -> uuid.UUID:
    """Fixture data published in the app's own demo org (gate relaxed for the fixtures)."""
    return published_fixture_gold(settings)[2]


def kpi(body: dict, name: str) -> dict:  # type: ignore[type-arg]
    return next(k for k in body["kpis"] if k["name"] == name)


def test_metric_catalog(client: TestClient) -> None:
    items = client.get("/api/v1/metrics").json()["items"]
    assert len(items) == 10
    gross = next(i for i in items if i["name"] == "gross_revenue")
    assert gross["unit"] == "GBP" and gross["description"] and "country" in gross["dimensions"]


def test_dashboard_defaults_to_full_range(client: TestClient, ds: uuid.UUID) -> None:
    body = client.get(f"/api/v1/datasets/{ds}/dashboard").json()
    assert body["range"] == {
        "from": "2010-12-01", "to": "2010-12-06", "min": "2010-12-01", "max": "2010-12-06",
        "default_limited": False,
    }  # fmt: skip
    g = kpi(body, "gross_revenue")
    assert g["value"] == pytest.approx(140.445) and g["unit"] == "GBP"
    assert g["previous"] is None and g["change"] is None  # nothing before the data starts
    # Counts too: "0 orders before the data starts" would be a false comparison.
    assert all(k["previous"] is None for k in body["kpis"])
    assert kpi(body, "repeat_customer_rate")["value"] == pytest.approx(0.25)
    assert body["trend"]["grain"] == "day" and len(body["trend"]["points"]) == 6
    assert body["top_products"][0] == {"key": "22633", "label": "HAND WARMER", "value": 37.0}
    assert body["countries"][0]["key"] == "United Kingdom"
    fresh = body["freshness"]
    assert fresh["run_id"] and fresh["quality"]["failed"] == 0 and fresh["quality"]["passed"] > 0


def test_dashboard_compares_with_previous_period(client: TestClient, ds: uuid.UUID) -> None:
    body = client.get(
        f"/api/v1/datasets/{ds}/dashboard", params={"from": "2010-12-04", "to": "2010-12-06"}
    ).json()
    g = kpi(body, "gross_revenue")
    assert g["value"] == pytest.approx(50.805)
    assert g["previous"] == pytest.approx(89.64)  # 2010-12-01..03
    assert g["change"] == pytest.approx((50.805 - 89.64) / 89.64)


def test_dashboard_pins_gold_when_publication_changes(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, ctx, source_id = setup_source(settings)
    ingest_fixtures(settings, engine, ctx, source_id, names=("batch_b.csv",))
    first = request_run(ctx, engine, source_id, trigger="manual")
    assert first is not None
    assert run_pipeline(ctx, engine, settings, first.id)[-1].status == "succeeded"

    ingest_fixtures(settings, engine, ctx, source_id, names=("batch_a.csv",))
    second = request_run(ctx, engine, source_id, trigger="manual")
    assert second is not None
    pack = load_domain_pack("ecommerce").with_threshold("quarantine_ratio", 0.2)
    assert run_pipeline(ctx, engine, settings, second.id, pack=pack)[-1].status == "succeeded"
    with session_scope(engine) as session:
        DataSourceRepo(session).get(ctx, source_id).published_run_id = first.id

    original_quality = RunRepo.quality

    def quality_and_publish(
        repo: RunRepo, org: OrgContext, run_id: uuid.UUID
    ) -> list[QualityResult]:
        quality = original_quality(repo, org, run_id)
        with session_scope(engine) as session:
            DataSourceRepo(session).get(ctx, source_id).published_run_id = second.id
        return quality

    monkeypatch.setattr(RunRepo, "quality", quality_and_publish)
    response = client.get(f"/api/v1/datasets/{source_id}/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["freshness"]["run_id"] == str(first.id)
    assert kpi(body, "gross_revenue")["value"] == pytest.approx(75.75)


def test_missing_published_file_is_503(client: TestClient, settings: Settings) -> None:
    engine, ctx, source_id = published_fixture_gold(settings)
    with session_scope(engine) as session:
        run_id = DataSourceRepo(session).get(ctx, source_id).published_run_id
    assert run_id is not None
    path = OrgPaths(settings.data_dir, ctx.org_id).gold_db(source_id, run_id)
    path.unlink()
    for endpoint in ("dashboard", "metrics/orders/series"):
        response = client.get(f"/api/v1/datasets/{source_id}/{endpoint}")
        assert response.status_code == 503
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["type"] == "/errors/published-data-unavailable"
        assert str(path) not in response.text


def test_date_limit_bounds_daily_series(client: TestClient, ds: uuid.UUID) -> None:
    path = f"/api/v1/datasets/{ds}/metrics/orders/series"
    start = date(2010, 12, 1)
    at_limit = client.get(
        path, params={"from": start, "to": start + timedelta(days=3659), "grain": "day"}
    )
    assert at_limit.status_code == 200
    assert len(at_limit.json()["points"]) == 3660
    for params in (
        {"from": start, "to": start + timedelta(days=3660)},
        {"to": date(2050, 1, 1)},
        {"from": date(9999, 12, 31), "to": date(9999, 12, 31)},
    ):
        result = client.get(path, params=params)
        assert result.status_code == 422
        assert result.json()["type"] == "/errors/validation-failed"


def test_dashboard_handles_earliest_calendar_day(client: TestClient, ds: uuid.UUID) -> None:
    response = client.get(
        f"/api/v1/datasets/{ds}/dashboard", params={"from": "0001-01-01", "to": "0001-01-01"}
    )
    assert response.status_code == 200
    assert all(item["previous"] is None for item in response.json()["kpis"])


def test_reversed_range_is_422(client: TestClient, ds: uuid.UUID) -> None:
    r = client.get(
        f"/api/v1/datasets/{ds}/dashboard", params={"from": "2010-12-06", "to": "2010-12-01"}
    )
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem")


def test_series_and_breakdown(client: TestClient, ds: uuid.UUID) -> None:
    s = client.get(f"/api/v1/datasets/{ds}/metrics/orders/series", params={"grain": "month"})
    assert s.json()["points"] == [{"period": "2010-12-01", "value": 7}]
    b = client.get(
        f"/api/v1/datasets/{ds}/metrics/gross_revenue/breakdown",
        params={"dimension": "country", "limit": 2},
    )
    assert [r["key"] for r in b.json()["items"]] == ["United Kingdom", "Netherlands"]


@pytest.mark.parametrize(
    ("path", "params", "status"),
    [
        ("metrics/nope/series", {}, 404),
        ("metrics/orders/series", {"grain": "year"}, 422),
        ("metrics/gross_revenue/breakdown", {"dimension": "city"}, 422),
        ("metrics/gross_revenue/breakdown", {"dimension": "country", "limit": 500}, 422),
        ("metrics/net_revenue/breakdown", {"dimension": "country"}, 422),
    ],
)
def test_invalid_requests(
    client: TestClient, ds: uuid.UUID, path: str, params: dict[str, object], status: int
) -> None:
    assert client.get(f"/api/v1/datasets/{ds}/{path}", params=params).status_code == status


def test_no_published_data_is_409(client: TestClient) -> None:
    created = client.post("/api/v1/datasets", json={"name": "Empty"}, headers=H).json()
    r = client.get(f"/api/v1/datasets/{created['id']}/dashboard")
    assert r.status_code == 409 and r.json()["type"] == "/errors/no-published-data"


def test_unknown_dataset_is_404(client: TestClient) -> None:
    r = client.get(f"/api/v1/datasets/{uuid.uuid4()}/dashboard")
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("question", "metric", "value", "statements"),
    [
        ("  HOW  MUCH did we sell? ", "gross_revenue", 140.445, 1),
        ("How many orders did we have?", "orders", 7, 1),
        ("What was our net revenue?", "net_revenue", 133.495, 2),
        ("what was the average order value?", "average_order_value", 140.445 / 7, 2),
        ("How many units did we sell?", "units_sold", 60, 1),
        ("active_customers", "active_customers", 4, 1),
        ("How many new customers did we have?", "new_customers", 4, 1),
        ("Repeat customer rate", "repeat_customer_rate", 0.25, 1),
        ("What was the return rate by value?", "return_rate_value", 6.95 / 140.445, 2),
        ("What was the value of returns?", "returns_value", 6.95, 1),
    ],
)
def test_question_answers_use_published_metrics(
    client: TestClient, ds: uuid.UUID, question: str, metric: str, value: float, statements: int
) -> None:
    base = f"/api/v1/datasets/{ds}"
    response = client.post(f"{base}/questions", json={"question": question}, headers=H)
    assert response.status_code == 200
    answer = response.json()
    assert answer["metric"] == metric
    assert answer["value"] == pytest.approx(value)
    assert answer["parameters"] == {"start": "2010-12-01", "end": "2010-12-07"}
    assert len(answer["sql"]) == statements
    assert all("$start" in sql and "$end" in sql for sql in answer["sql"])
    assert answer["run_id"] == client.get(f"{base}/dashboard").json()["freshness"]["run_id"]


def test_questions_respect_date_bounds_and_decline_unsupported_requests(
    client: TestClient, ds: uuid.UUID
) -> None:
    path = f"/api/v1/datasets/{ds}/questions"
    gross = {"question": "Gross revenue", "from": "2010-12-04", "to": "2010-12-06"}
    answer = client.post(path, json=gross, headers=H)
    assert answer.status_code == 200
    assert answer.json()["value"] == pytest.approx(50.805)
    dated = {"question": "How much did we sell from 2010-12-04 to 2010-12-06?"}
    natural = client.post(path, json=dated, headers=H)
    assert natural.status_code == 200
    assert natural.json() == answer.json()
    for body in (
        {"question": "How much did we sell in France?"},
        {"question": "Forecast next month's sales"},
        {"question": "x" * 241},
        {**gross, "to": "2009-12-06"},
        {**dated, "to": "2010-12-06"},
        {"question": "Gross revenue from 2010-11-31 to 2010-12-06"},
        {"question": "Gross revenue from 2010-12-06 to 2010-12-01"},
    ):
        declined = client.post(path, json=body, headers=H)
        assert declined.status_code == 422
        assert "sql" not in declined.json()


def test_questions_require_a_published_dataset(client: TestClient) -> None:
    empty = client.post("/api/v1/datasets", json={"name": "Empty"}, headers=H).json()
    for dataset, expected in ((empty["id"], 409), (uuid.uuid4(), 404)):
        response = client.post(
            f"/api/v1/datasets/{dataset}/questions", json={"question": "Orders"}, headers=H
        )
        assert response.status_code == expected


def test_provider_cannot_override_registry_or_explicit_dates(settings: Settings) -> None:
    engine, ctx, source_id = published_fixture_gold(settings)
    from_date, to_date = date(2010, 12, 4), date(2010, 12, 6)

    class StubProvider:
        def __init__(self, metric: str) -> None:
            self.metric = metric

        def select_metric(self, question: str, options: tuple[MetricOption, ...]) -> str:
            assert question == "What did we earn from sales?"
            assert {entry.name for entry in options} >= {"gross_revenue", "orders"}
            return self.metric

    question = "What did we earn from sales?"
    answer = service.answer_question(
        ctx, engine, settings, source_id, question, from_date, to_date,
        provider=StubProvider("gross_revenue"),
    )  # fmt: skip
    assert answer["value"] == pytest.approx(50.805)
    assert answer["from"] == from_date
    assert answer["to"] == to_date

    with pytest.raises(ValidationFailed, match="outside the supported set"):
        service.answer_question(
            ctx, engine, settings, source_id, question, from_date, to_date,
            provider=StubProvider("unregistered_metric"),
        )  # fmt: skip
