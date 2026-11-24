-- Grain: one cancelled merchandise line (UCI marks cancellations with a 'C' invoice prefix and a
-- negative quantity). Values are stored as positive amounts.
SELECT
    invoice_no,
    invoice_ts,
    invoice_date,
    stock_code,
    coalesce(customer_id, 'UNKNOWN') AS customer_key,
    country,
    abs(quantity) AS return_quantity,
    unit_price,
    CAST(abs(quantity) * unit_price AS DECIMAL(18, 3)) AS return_value,
    _ingest_id,
    _row_number
FROM order_lines
WHERE is_cancellation
  AND NOT is_adjustment
  AND quantity < 0
  AND unit_price >= 0
