# Data profile — UCI Online Retail II

Measured 2026-11-24 in the Linux cloud dev container. **Not yet measured on the owner's Windows laptop.**
Hardware: 4 vCPU (Intel Xeon @ 2.10 GHz), 15 GiB RAM. DuckDB 2.0.1, Python 3.12.13.

## Source
- UCI Machine Learning Repository, dataset 502, licence **CC BY 4.0** (commercial use allowed with
  attribution). UK online retailer, 2009-12-01 → 2011-12-09.
- Download: `online+retail+ii.zip` (45,622,418 bytes, sha256 `572e3627…7bfb`) containing
  `online_retail_II.xlsx` with two sheets. Converted by `scripts/fetch_sample_data.py` in ~40 s.

| Sheet → CSV | Lines | Size |
|---|---|---|
| Year 2009-2010 | 525,461 | 46.5 MB |
| Year 2010-2011 | 541,910 | 47.8 MB |

Columns: `Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID, Country`.

## Findings that shaped the design
| Finding (profiled with DuckDB) | Consequence |
|---|---|
| The sheets overlap: **22,523** lines dated 2010-12-01…09 appear in both (`INTERSECT ALL` = exactly 22,523) | Multiplicity rule `max(k,m)` (ADR-0017); summing would double count |
| 6,865 exact repeats inside the first sheet alone | Kept, reported as a warning (can't tell repeats from duplicates) |
| `C` invoices: 19,494 lines, 19,493 with negative quantity | `fact_returns`, values stored as `ABS(quantity) × price` |
| 3,457 negative-quantity lines on non-`C` invoices (stock write-offs, price 0, no customer) | Flag `is_writeoff`; excluded from sales and returns |
| 6 `A` invoices ("Adjust bad debt", negative price) | Flag `is_bad_debt`; excluded |
| 6,202 zero-price lines; 5 negative-price lines | Excluded from `fact_sales` (price > 0 required) |
| Non-merchandise codes: POST, DOT, M, C2, D, S, B, BANK CHARGES, ADJUST, AMAZONFEE, PADS, CRUK, gift_*, TEST* | `rules.yaml` adjustment list; excluded from sales/returns |
| 18 prices with 3 decimals (e.g. 2.955) | `DECIMAL(12,3)`; >3 decimals quarantined instead of rounded |
| 243,007 lines (22.8%) without customer id | Kept; `UNKNOWN` customer member; warning threshold 30% |
| 0 unparseable dates/quantities/prices | Quarantine is empty on this dataset |
| 43 countries; 13 customers appear under >1 country | `primary_country` = most frequent, then most recent |

## Pipeline run on the full dataset (both sheets as two batches)
Run through the real HTTP API (`load-sample`), server started with `uvicorn` on 127.0.0.1.

| Step | Result |
|---|---|
| Ingestion of both CSVs (hash + contract check + all-text Parquet) | 1.3 s for the HTTP request |
| Silver | 1,067,371 in → 1,044,848 out, 0 quarantined, 22,523 overlap removed — 1.75 s |
| Silver quality | 19 ms, all blocking rules passed |
| Gold | 1,015,074 `fact_sales` rows — 1.24 s |
| Gold quality | 66 ms, all blocking rules passed (revenue reconciliation difference 0.00) |
| Publish | 4 ms |
| **Total run** | **≈ 3.2 s** |
| Re-run on the same batches | Identical Gold (row counts + order-independent row hash per table) |
| Server memory | peak RSS ≈ 1.0 GB during the run, 153 MB idle after |
| Storage | Bronze 102 MB, Silver 12 MB, Gold 27 MB (of which `gold.duckdb` 16.5 MB) |

## Resulting Gold
| Table | Rows |
|---|---|
| fact_sales | 1,015,074 |
| fact_returns | 17,973 |
| dim_customer | 5,876 (5,875 known + UNKNOWN) |
| dim_product | 4,739 |
| dim_date | 739 (2009-12-01 → 2011-12-09) |
| agg_daily_sales | 2,827 |

Headline figures (GBP, from Gold, definitions in DATA_ARCHITECTURE §3): gross revenue
**19,701,685.49**; returns value **719,656.34**; orders **39,519**; 13.1% of gross revenue has no
customer id. These are reproducible outputs of the pipeline, not audited financials.

## Implications
- Peak memory ~1 GB means a 512 MB free instance (e.g. Koyeb) is not viable without lowering
  `INSIGHTFLOW_DUCKDB_MEMORY_LIMIT` and re-measuring.
- To re-measure on Windows: see README quickstart, then compare stage `duration_ms` from
  `GET /api/v1/pipeline-runs/{id}`.
