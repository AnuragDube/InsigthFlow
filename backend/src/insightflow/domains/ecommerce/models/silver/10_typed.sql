-- Cast every Bronze text column to its type. Nothing is dropped here: rows that fail a cast get a
-- reason_code and are routed to quarantine by the next model.
WITH t AS (
    SELECT
        _ingest_id,
        _batch_order,
        _row_number,
        nullif(upper(trim("Invoice")), '') AS invoice_no,
        nullif(upper(trim("StockCode")), '') AS stock_code,
        nullif(trim("Description"), '') AS description,
        -- Strict formats first, then cast. A bare try_cast would silently ROUND '1.6' to 2 and
        -- accept '1e3' or '2010-12-01T08:00:00Z' (dropping the zone): those are quarantined.
        CASE WHEN regexp_full_match(trim("Quantity"), '[+-]?[0-9]{1,9}')
             THEN try_cast(trim("Quantity") AS INTEGER) END AS quantity,
        CASE WHEN regexp_full_match(
                 trim("InvoiceDate"),
                 '[0-9]{4}-[0-9]{2}-[0-9]{2}([ T][0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]{1,6})?)?)?')
             THEN try_cast(trim("InvoiceDate") AS TIMESTAMP) END AS invoice_ts,
        -- At most 3 decimals (the data has prices like 2.955); more would be rounded silently.
        CASE WHEN regexp_full_match(trim("Price"), '[+-]?[0-9]{1,9}(\.[0-9]{1,3})?')
             THEN try_cast(trim("Price") AS DECIMAL(12, 3)) END AS unit_price,
        -- Some exports write ids as 13085.0; normalize to 13085.
        nullif(regexp_replace(trim("Customer ID"), '\.0+$', ''), '') AS customer_id,
        nullif(trim("Country"), '') AS country,
        "Invoice" AS raw_invoice,
        "StockCode" AS raw_stock_code,
        "Quantity" AS raw_quantity,
        "InvoiceDate" AS raw_invoice_date,
        "Price" AS raw_price
    FROM bronze
)
SELECT
    *,
    CASE
        WHEN invoice_no IS NULL OR stock_code IS NULL THEN 'missing_key'
        WHEN invoice_ts IS NULL THEN 'bad_timestamp'
        WHEN quantity IS NULL THEN 'bad_quantity'
        WHEN unit_price IS NULL THEN 'bad_price'
    END AS reason_code
FROM t
