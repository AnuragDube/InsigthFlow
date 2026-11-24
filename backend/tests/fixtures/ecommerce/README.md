# E-commerce golden fixtures

Two small batches that contain every edge case found when profiling UCI Online Retail II
(see `docs/DATA_PROFILE.md`). Expected values in `expected.yaml` were computed **by hand**, below.
Line ids: `A1..A14` = data rows of `batch_a.csv` in order, `B1..B8` = rows of `batch_b.csv`.

| Line | What it tests | Fate |
|---|---|---|
| A1, A2 | normal sale (invoice 1001) | fact_sales: 6×2.55=15.30, 6×3.39=20.34 |
| A3, A4 | identical line twice in one batch | both kept (within-batch repeat, warning): 10×1.85=18.50 each |
| A5 | missing customer id | fact_sales 4×4.25=17.00, customer = UNKNOWN |
| A6 | cancellation `C1004` | fact_returns 2×2.55=5.10 |
| A7 | `POST` adjustment code | excluded |
| A8 | negative qty on a non-C invoice (write-off), price 0 | excluded |
| A9 | `A` bad-debt invoice, negative price | excluded |
| A10 | zero price | excluded |
| A11 | unparseable date | quarantine `bad_timestamp` |
| A12 | non-numeric quantity | quarantine `bad_quantity` |
| A13 | 3-decimal price 2.955 | fact_sales 2.955 (must not round) |
| A14 | customer 12583 in Germany (also France in A13) | fact_sales 2×2.95=5.90 |
| B1 | same as A1 (overlap) | removed: A has 1 copy, B has 1 → keep max(1,1)=1 |
| B2 | same as A3 (overlap) | removed: A has 2 copies, B has 1 → keep max(2,1)=2 |
| B3, B4 | normal sales, invoice 1013 | 19.50 each |
| B5 | cancellation `C1014` | fact_returns 1×1.85=1.85 |
| B6 | gift voucher `gift_0001_20` | excluded (pattern `GIFT_%`) |
| B7 | normal sale, Germany | 2.95 |
| B8 | cancellation of `POST` | excluded from returns (adjustment code) |

- rows_in 22 = 14 + 8; quarantined 2; overlap removed 2 → Silver rows_out 18.
- fact_sales (10 rows): 15.30 + 20.34 + 18.50 + 18.50 + 17.00 + 2.955 + 5.90 + 19.50 + 19.50 + 2.95
  = **140.445**; units 6+6+10+10+4+1+2+10+10+1 = **60**.
- orders: invoices 1001, 1002, 1003, 1011, 1012, 1013, 1016 = **7**.
- returns: 5.10 + 1.85 = **6.95** (2 rows).
- known customers in facts: 17850, 13047, 12583, 14646 = **4**; dim_customer adds UNKNOWN → 5.
- products: 85123A, 71053, 22633, 21730, 22086, 85099B, 85099C = **7**.
- customer 12583 primary country: fact_sales lines France 1 (A13), Germany 2 (A14, B7) → **Germany**.
