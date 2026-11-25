from datetime import date, timedelta

from fastapi.testclient import TestClient

from insightflow.analytics.forecast import forecast_week
from insightflow.api.app import create_app
from insightflow.core.settings import Settings

H = {"X-InsightFlow-Client": "web"}
DATASETS = "/api/v1/datasets"


def test_backtest_does_not_train_on_held_out_week() -> None:
    history = [float(week) for week in range(1, 6) for _ in range(7)]
    points, evaluation = forecast_week(history, date(2011, 1, 4))
    assert evaluation.folds == 1
    assert evaluation.days_evaluated == 7
    assert evaluation.seasonal_naive_mae == 1.0
    assert evaluation.weekday_average_mae == 2.5
    assert points[0].date == date(2011, 1, 5)
    assert points[-1].date == date(2011, 1, 11)
    assert all(point.seasonal_naive == 5.0 and point.weekday_average == 3.5 for point in points)


def test_sales_forecast_uses_published_gold(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        dataset = client.post(DATASETS, headers=H, json={"name": "Forecast fixture"}).json()
        base = f"{DATASETS}/{dataset['id']}"
        assert client.get(f"{base}/forecast").status_code == 409
        first_date = date(2010, 12, 1)
        sales = ["Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country"]
        sales.extend(
            f"{1000 + day},85123A,WHITE HEART,1,{first_date + timedelta(days=day)} 08:00:00,"
            "2.00,17850,United Kingdom"
            for day in range(35)
        )
        upload = client.post(
            f"{base}/uploads", headers=H, files={"file": ("sales.csv", "\n".join(sales).encode())}
        )
        assert upload.status_code == 201
        response = client.get(f"{base}/forecast")
        assert response.status_code == 200
        report = response.json()
        assert report["published_run_id"] == upload.json()["run_id"]
        assert len(report["points"]) == 7
        assert report["points"][0] == {
            "date": "2011-01-05", "seasonal_naive": 2.0, "weekday_average": 2.0,
        }  # fmt: skip
        assert report["backtest"] == {
            "folds": 1, "days_evaluated": 7, "seasonal_naive_mae": 0.0, "weekday_average_mae": 0.0,
        }  # fmt: skip
