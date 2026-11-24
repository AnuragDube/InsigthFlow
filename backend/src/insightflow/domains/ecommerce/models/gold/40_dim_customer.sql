-- One row per known customer plus a single 'UNKNOWN' member, so every fact row has a customer.
-- primary_country: most frequent country on the customer's lines; ties -> most recent, then name.
WITH lines AS (
    SELECT customer_key, country, invoice_ts FROM fact_sales
    UNION ALL
    SELECT customer_key, country, invoice_ts FROM fact_returns
),
ranked AS (
    SELECT customer_key, country
    FROM (
        SELECT customer_key, country, count(*) AS n, max(invoice_ts) AS last_ts
        FROM lines
        WHERE customer_key <> 'UNKNOWN'
        GROUP BY ALL
    )
    QUALIFY row_number() OVER (
        PARTITION BY customer_key ORDER BY n DESC, last_ts DESC, country
    ) = 1
),
sales AS (
    SELECT
        customer_key,
        min(invoice_date) AS first_order_date,
        max(invoice_date) AS last_order_date,
        count(DISTINCT invoice_no) AS order_count,
        sum(revenue) AS lifetime_revenue
    FROM fact_sales
    GROUP BY customer_key
)
SELECT
    r.customer_key,
    r.country AS primary_country,
    s.first_order_date,
    s.last_order_date,
    coalesce(s.order_count, 0) AS order_count,
    coalesce(s.lifetime_revenue, 0) AS lifetime_revenue,
    false AS is_unknown
FROM ranked r
LEFT JOIN sales s USING (customer_key)
UNION ALL
SELECT 'UNKNOWN', NULL, NULL, NULL, 0, 0, true
