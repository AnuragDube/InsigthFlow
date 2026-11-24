from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.core.settings import Settings
from pipeline_helpers import published_fixture_gold

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
    }  # fmt: skip
    g = kpi(body, "gross_revenue")
    assert g["value"] == pytest.approx(140.445) and g["unit"] == "GBP"
    assert g["previous"] is None and g["change"] is None  # nothing before the data starts
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
