-- Quarantine: rows that could not be typed, kept with their raw values and a reason.
SELECT
    _ingest_id, _row_number, reason_code, invoice_no,
    raw_invoice, raw_stock_code, raw_quantity, raw_invoice_date, raw_price
FROM typed
WHERE reason_code IS NOT NULL
