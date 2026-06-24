-- 1. Top 5 funds by AUM
SELECT
    f.scheme_name,
    f.fund_house,
    p.aum_crore
FROM fact_performance p
JOIN dim_fund f ON f.amfi_code = p.amfi_code
ORDER BY p.aum_crore DESC
LIMIT 5;

-- 2. Average NAV per month
SELECT
    d.year_month,
    ROUND(AVG(n.nav), 4) AS avg_nav
FROM fact_nav n
JOIN dim_date d ON d.date_key = n.date_key
GROUP BY d.year_month
ORDER BY d.year_month;

-- 3. SIP YoY growth
SELECT
    month,
    sip_inflow_crore,
    yoy_growth_pct
FROM cleaned_monthly_sip_inflows
ORDER BY month;

-- 4. Transactions by state
SELECT
    state,
    COUNT(*) AS transaction_count,
    SUM(amount_inr) AS total_amount_inr
FROM fact_transactions
GROUP BY state
ORDER BY total_amount_inr DESC;

-- 5. Funds with expense ratio below 1%
SELECT
    f.amfi_code,
    f.scheme_name,
    f.fund_house,
    p.expense_ratio_pct
FROM fact_performance p
JOIN dim_fund f ON f.amfi_code = p.amfi_code
WHERE p.expense_ratio_pct < 1
ORDER BY p.expense_ratio_pct, f.scheme_name;

-- 6. Best 5 funds by 3-year alpha
SELECT
    f.scheme_name,
    f.category,
    f.sub_category,
    p.alpha
FROM fact_performance p
JOIN dim_fund f ON f.amfi_code = p.amfi_code
ORDER BY p.alpha DESC
LIMIT 5;

-- 7. Monthly redemption value
SELECT
    d.year_month,
    SUM(t.amount_inr) AS redemption_amount_inr
FROM fact_transactions t
JOIN dim_date d ON d.date_key = t.date_key
WHERE t.transaction_type = 'Redemption'
GROUP BY d.year_month
ORDER BY d.year_month;

-- 8. Investor transaction mix by city tier
SELECT
    city_tier,
    transaction_type,
    COUNT(*) AS transaction_count,
    SUM(amount_inr) AS total_amount_inr
FROM fact_transactions
GROUP BY city_tier, transaction_type
ORDER BY city_tier, transaction_type;

-- 9. Highest portfolio sector exposure
SELECT
    sector,
    ROUND(SUM(weight_pct), 2) AS total_weight_pct
FROM cleaned_portfolio_holdings
GROUP BY sector
ORDER BY total_weight_pct DESC
LIMIT 10;

-- 10. Benchmark monthly average close
SELECT
    SUBSTR(date, 1, 7) AS year_month,
    index_name,
    ROUND(AVG(close_value), 2) AS avg_close_value
FROM cleaned_benchmark_indices
GROUP BY SUBSTR(date, 1, 7), index_name
ORDER BY year_month, index_name;
