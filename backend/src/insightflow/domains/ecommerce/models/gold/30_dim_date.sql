-- One row per calendar day between the first and last transaction (no gaps, for time series).
SELECT
    CAST(d AS DATE) AS date,
    year(d) AS year,
    quarter(d) AS quarter,
    month(d) AS month,
    monthname(d) AS month_name,
    CAST(date_trunc('month', d) AS DATE) AS month_start,
    isodow(d) AS iso_day_of_week,
    isodow(d) >= 6 AS is_weekend
FROM range(
    CAST((SELECT min(invoice_date) FROM order_lines) AS TIMESTAMP),
    CAST((SELECT max(invoice_date) FROM order_lines) AS TIMESTAMP) + INTERVAL 1 DAY,
    INTERVAL 1 DAY
) AS t(d)
