-- Combine batches with the multiplicity rule (ADR-0017).
-- Each batch is a multiset of identical lines. occurrence_no numbers the copies of a line inside
-- its own batch (1, 2, ...). Keeping one row per (line, occurrence_no) across all batches keeps
-- max(k, m) copies: overlapping exports don't double count, and genuine repeats inside one
-- export survive. Ties go to the earliest batch, then the earliest row -> deterministic lineage.
WITH good AS (
    SELECT * FROM typed WHERE reason_code IS NULL
),
numbered AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY _ingest_id, invoice_no, stock_code, description, quantity,
                         invoice_ts, unit_price, customer_id, country
            ORDER BY _row_number
        ) AS occurrence_no
    FROM good
),
kept AS (
    SELECT *
    FROM numbered
    QUALIFY row_number() OVER (
        PARTITION BY invoice_no, stock_code, description, quantity,
                     invoice_ts, unit_price, customer_id, country, occurrence_no
        ORDER BY _batch_order, _row_number
    ) = 1
)
SELECT
    invoice_no,
    stock_code,
    description,
    quantity,
    unit_price,
    invoice_ts,
    CAST(invoice_ts AS DATE) AS invoice_date,
    customer_id,
    country,
    starts_with(invoice_no, 'C') AS is_cancellation,
    starts_with(invoice_no, 'A') AS is_bad_debt,
    (
        stock_code IN (SELECT code FROM adjustment_codes)
        OR EXISTS (SELECT 1 FROM adjustment_patterns p WHERE stock_code LIKE p.pattern)
    ) AS is_adjustment,
    (quantity < 0 AND NOT starts_with(invoice_no, 'C')) AS is_writeoff,
    occurrence_no,
    _ingest_id,
    _row_number
FROM kept
