-- Pre-aggregated daily sales by country for fast dashboard queries.
SELECT
    invoice_date AS date,
    country,
    sum(revenue) AS revenue,
    count(DISTINCT invoice_no) AS orders,
    sum(quantity) AS units
FROM fact_sales
GROUP BY ALL
