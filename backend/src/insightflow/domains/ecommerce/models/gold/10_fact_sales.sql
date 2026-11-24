-- Grain: one merchandise sale line. Excludes cancellations, bad-debt entries, non-merchandise
-- adjustment codes, stock write-offs, and lines without positive quantity and price.
SELECT
    invoice_no,
    invoice_ts,
    invoice_date,
    stock_code,
    coalesce(customer_id, 'UNKNOWN') AS customer_key,
    country,
    quantity,
    unit_price,
    CAST(quantity * unit_price AS DECIMAL(18, 3)) AS revenue,
    _ingest_id,
    _row_number
FROM order_lines
WHERE NOT is_cancellation
  AND NOT is_bad_debt
  AND NOT is_adjustment
  AND NOT is_writeoff
  AND quantity > 0
  AND unit_price > 0
