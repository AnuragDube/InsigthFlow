-- One row per stock code seen in sales or returns. The source repeats codes with varying
-- descriptions, so: the description of the latest line; ties -> alphabetically first.
-- (An explicit ORDER BY, not arg_max: arg_max picks an arbitrary row among ties.)
WITH lines AS (
    SELECT f.stock_code, f.invoice_ts, o.description
    FROM fact_sales f JOIN order_lines o USING (_ingest_id, _row_number)
    UNION ALL
    SELECT f.stock_code, f.invoice_ts, o.description
    FROM fact_returns f JOIN order_lines o USING (_ingest_id, _row_number)
),
latest AS (
    SELECT stock_code, description
    FROM lines
    WHERE description IS NOT NULL
    QUALIFY row_number() OVER (
        PARTITION BY stock_code ORDER BY invoice_ts DESC, description
    ) = 1
),
seen AS (
    SELECT stock_code, CAST(min(invoice_ts) AS DATE) AS first_seen_date
    FROM lines
    GROUP BY stock_code
)
SELECT s.stock_code, l.description, s.first_seen_date
FROM seen s
LEFT JOIN latest l USING (stock_code)
