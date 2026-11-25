from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.core.settings import Settings


def test_segments_use_published_sales_and_exclude_unknown_customers(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        headers = {"X-InsightFlow-Client": "web"}
        dataset = client.post("/api/v1/datasets", json={"name": "Segments"}, headers=headers).json()
        base = f"/api/v1/datasets/{dataset['id']}"
        assert client.get(f"{base}/customer-segments").status_code == 409
        sales = ["Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country"]
        records = (
            ("2010-11-01", 10, "300"),
            ("2010-12-01", 5, "400"),
            ("2010-12-02", 40, "100"),
            ("2010-12-04", 30, "100"),
            ("2010-12-05", 30, "100"),
            ("2010-12-05", 100, "200"),
            ("2010-12-06", 90, "200"),
            ("2010-12-06", 10, ""),
        )
        sales.extend(
            f"{1000 + index},85123A,WHITE HEART,1,{day} 08:00:00,{value},{customer},United Kingdom"
            for index, (day, value, customer) in enumerate(records)
        )
        upload = client.post(
            f"{base}/uploads", headers=headers,
            files={"file": ("sales.csv", "\n".join(sales).encode())},
        )  # fmt: skip
        assert upload.status_code == 201
        response = client.get(f"{base}/customer-segments")
        assert response.status_code == 200
        report = response.json()
        assert report["as_of"] == "2010-12-06"
        assert report["published_run_id"] == upload.json()["run_id"]
        assert {
            row["key"]: (row["customers"], row["orders"], row["gross_revenue"])
            for row in report["segments"]
        } == {
            "high_value_repeat": (1, 3, 100.0),
            "recent_repeat": (1, 2, 190.0),
            "recent_single": (1, 1, 5.0),
            "inactive": (1, 1, 10.0),
        }
