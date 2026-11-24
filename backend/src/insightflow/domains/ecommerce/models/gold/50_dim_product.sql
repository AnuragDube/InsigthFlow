-- One row per stock code seen in sales or returns. Description: latest non-empty one
-- (ties -> alphabetical) because the source repeats codes with varying descriptions.
WITH lines AS (
    SELECT f.stock_code, f.invoice_ts, o.description
    FROM fact_sales f JOIN order_lines o USING (_ingest_id, _row_number)
    UNION ALL
    SELECT f.stock_code, f.invoice_ts, o.description
    FROM fact_returns f JOIN order_lines o USING (_ingest_id, _row_number)
)
SELECT
    stock_code,
    arg_max(description, invoice_ts) FILTER (WHERE description IS NOT NULL) AS description,
    CAST(min(invoice_ts) AS DATE) AS first_seen_date
FROM lines
GROUP BY stock_code
