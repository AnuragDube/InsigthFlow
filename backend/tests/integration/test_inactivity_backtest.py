from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.core.settings import Settings


def test_inactivity_backtest_uses_only_pre_snapshot_purchases_for_flags(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        headers = {"X-InsightFlow-Client": "web"}
        dataset = client.post("/api/v1/datasets", json={"name": "Backtest"}, headers=headers).json()
        base = f"/api/v1/datasets/{dataset['id']}"
        assert client.get(f"{base}/inactivity-backtest").status_code == 409
        records = (
            ("2011-01-01", "100"),
            ("2011-03-01", "200"),
            ("2011-03-31", "300"),
            ("2011-04-01", "100"),
            ("2011-04-30", "400"),
            ("2011-01-15", ""),
        )
        csv = ["Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country"]
        csv.extend(
            f"{1000 + i},85123A,WHITE HEART,1,{day} 08:00:00,2.00,{customer},United Kingdom"
            for i, (day, customer) in enumerate(records)
        )
        upload = client.post(
            f"{base}/uploads",
            headers=headers,
            files={"file": ("sales.csv", "\n".join(csv).encode())},
        )
        assert upload.status_code == 201
        report = client.get(f"{base}/inactivity-backtest").raise_for_status().json()
        assert report["published_run_id"] == upload.json()["run_id"]
        assert report["evaluation"] == {
            "cohort_from": "2011-01-01",
            "snapshot_date": "2011-03-31",
            "holdout_through": "2011-04-30",
            "customers": 3,
            "flagged": 2,
            "inactive": 2,
            "true_positives": 1,
            "precision": 0.5,
            "recall": 0.5,
            "baseline_rate": 2 / 3,
        }
