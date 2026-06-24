from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
SQL_DIR = Path("sql")
DB_PATH = Path("bluestock_mf.db")


RAW_FILES = {
    "fund_master": "01_fund_master.csv",
    "nav_history": "02_nav_history.csv",
    "aum_by_fund_house": "03_aum_by_fund_house.csv",
    "monthly_sip_inflows": "04_monthly_sip_inflows.csv",
    "category_inflows": "05_category_inflows.csv",
    "industry_folio_count": "06_industry_folio_count.csv",
    "scheme_performance": "07_scheme_performance.csv",
    "investor_transactions": "08_investor_transactions.csv",
    "portfolio_holdings": "09_portfolio_holdings.csv",
    "benchmark_indices": "10_benchmark_indices.csv",
}


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS fact_aum;
DROP TABLE IF EXISTS fact_performance;
DROP TABLE IF EXISTS fact_transactions;
DROP TABLE IF EXISTS fact_nav;
DROP TABLE IF EXISTS dim_fund;
DROP TABLE IF EXISTS dim_date;

CREATE TABLE dim_fund (
    amfi_code INTEGER PRIMARY KEY,
    fund_house TEXT NOT NULL,
    scheme_name TEXT NOT NULL,
    category TEXT NOT NULL,
    sub_category TEXT NOT NULL,
    plan TEXT NOT NULL,
    launch_date DATE,
    benchmark TEXT,
    expense_ratio_pct REAL,
    exit_load_pct REAL,
    min_sip_amount INTEGER,
    min_lumpsum_amount INTEGER,
    fund_manager TEXT,
    risk_category TEXT,
    sebi_category_code TEXT
);

CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    year_month TEXT NOT NULL,
    day_of_month INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
);

CREATE TABLE fact_nav (
    amfi_code INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    nav REAL NOT NULL CHECK (nav > 0),
    is_forward_filled INTEGER NOT NULL CHECK (is_forward_filled IN (0, 1)),
    PRIMARY KEY (amfi_code, date_key),
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code),
    FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);

CREATE TABLE fact_transactions (
    transaction_id INTEGER PRIMARY KEY,
    investor_id TEXT NOT NULL,
    amfi_code INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('SIP', 'Lumpsum', 'Redemption')),
    amount_inr INTEGER NOT NULL CHECK (amount_inr > 0),
    state TEXT,
    city TEXT,
    city_tier TEXT,
    age_group TEXT,
    gender TEXT,
    annual_income_lakh REAL,
    payment_mode TEXT,
    kyc_status TEXT NOT NULL CHECK (kyc_status IN ('Verified', 'Pending')),
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code),
    FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);

CREATE TABLE fact_performance (
    amfi_code INTEGER PRIMARY KEY,
    return_1yr_pct REAL,
    return_3yr_pct REAL,
    return_5yr_pct REAL,
    benchmark_3yr_pct REAL,
    alpha REAL,
    beta REAL,
    sharpe_ratio REAL,
    sortino_ratio REAL,
    std_dev_ann_pct REAL,
    max_drawdown_pct REAL,
    aum_crore INTEGER,
    expense_ratio_pct REAL CHECK (expense_ratio_pct BETWEEN 0.1 AND 2.5),
    morningstar_rating INTEGER,
    risk_grade TEXT,
    return_anomaly_flag INTEGER NOT NULL CHECK (return_anomaly_flag IN (0, 1)),
    expense_ratio_anomaly_flag INTEGER NOT NULL CHECK (expense_ratio_anomaly_flag IN (0, 1)),
    FOREIGN KEY (amfi_code) REFERENCES dim_fund(amfi_code)
);

CREATE TABLE fact_aum (
    date_key INTEGER NOT NULL,
    fund_house TEXT NOT NULL,
    aum_lakh_crore REAL NOT NULL,
    aum_crore INTEGER NOT NULL,
    num_schemes INTEGER NOT NULL,
    PRIMARY KEY (date_key, fund_house),
    FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);
"""


QUERIES_SQL = """
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
"""


def date_key(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.strftime("%Y%m%d").astype(int)


def read_raw() -> dict[str, pd.DataFrame]:
    return {name: pd.read_csv(RAW_DIR / filename) for name, filename in RAW_FILES.items()}


def clean_fund_master(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["launch_date"] = pd.to_datetime(df["launch_date"], errors="coerce").dt.date
    df = df.drop_duplicates(subset=["amfi_code"], keep="last").sort_values("amfi_code")
    numeric_cols = ["expense_ratio_pct", "exit_load_pct", "min_sip_amount", "min_lumpsum_amount"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def clean_nav_history(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df = df.dropna(subset=["amfi_code", "date", "nav"])
    df = df[df["nav"] > 0]
    df = df.drop_duplicates(subset=["amfi_code", "date"], keep="last")
    df = df.sort_values(["amfi_code", "date"])

    filled_frames: list[pd.DataFrame] = []
    for amfi_code, group in df.groupby("amfi_code", sort=True):
        full_dates = pd.date_range(group["date"].min(), group["date"].max(), freq="D")
        expanded = (
            group.set_index("date")
            .reindex(full_dates)
            .rename_axis("date")
            .reset_index()
        )
        expanded["amfi_code"] = int(amfi_code)
        expanded["is_forward_filled"] = expanded["nav"].isna().astype(int)
        expanded["nav"] = expanded["nav"].ffill()
        filled_frames.append(expanded)

    cleaned = pd.concat(filled_frames, ignore_index=True)
    cleaned = cleaned.dropna(subset=["nav"])
    cleaned["date"] = pd.to_datetime(cleaned["date"]).dt.date
    return cleaned[["amfi_code", "date", "nav", "is_forward_filled"]]


def clean_investor_transactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    mapping = {
        "sip": "SIP",
        "systematic investment plan": "SIP",
        "lumpsum": "Lumpsum",
        "lump sum": "Lumpsum",
        "redemption": "Redemption",
        "redeem": "Redemption",
    }
    df["transaction_type"] = (
        df["transaction_type"].astype(str).str.strip().str.lower().map(mapping)
    )
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce").dt.date
    df["amount_inr"] = pd.to_numeric(df["amount_inr"], errors="coerce")
    df["kyc_status"] = df["kyc_status"].astype(str).str.strip().str.title()
    df = df[df["transaction_type"].isin(["SIP", "Lumpsum", "Redemption"])]
    df = df[df["kyc_status"].isin(["Verified", "Pending"])]
    df = df[df["amount_inr"] > 0]
    df = df.dropna(subset=["transaction_date", "amfi_code"])
    df = df.reset_index(drop=True)
    df.insert(0, "transaction_id", df.index + 1)
    return df


def clean_scheme_performance(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    numeric_cols = [
        "return_1yr_pct",
        "return_3yr_pct",
        "return_5yr_pct",
        "benchmark_3yr_pct",
        "alpha",
        "beta",
        "sharpe_ratio",
        "sortino_ratio",
        "std_dev_ann_pct",
        "max_drawdown_pct",
        "aum_crore",
        "expense_ratio_pct",
        "morningstar_rating",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return_cols = [
        "return_1yr_pct",
        "return_3yr_pct",
        "return_5yr_pct",
        "benchmark_3yr_pct",
    ]
    df["return_anomaly_flag"] = (
        df[return_cols].isna().any(axis=1)
        | (df[return_cols].abs() > 100).any(axis=1)
    ).astype(int)
    df["expense_ratio_anomaly_flag"] = (
        ~df["expense_ratio_pct"].between(0.1, 2.5, inclusive="both")
    ).astype(int)
    return df.drop_duplicates(subset=["amfi_code"], keep="last").sort_values("amfi_code")


def clean_generic_dates(df: pd.DataFrame, date_columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in date_columns:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df.drop_duplicates().reset_index(drop=True)


def clean_all(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    cleaned = {
        "fund_master": clean_fund_master(raw["fund_master"]),
        "nav_history": clean_nav_history(raw["nav_history"]),
        "aum_by_fund_house": clean_generic_dates(raw["aum_by_fund_house"], ["date"]),
        "monthly_sip_inflows": clean_generic_dates(raw["monthly_sip_inflows"], []),
        "category_inflows": clean_generic_dates(raw["category_inflows"], []),
        "industry_folio_count": clean_generic_dates(raw["industry_folio_count"], []),
        "scheme_performance": clean_scheme_performance(raw["scheme_performance"]),
        "investor_transactions": clean_investor_transactions(raw["investor_transactions"]),
        "portfolio_holdings": clean_generic_dates(raw["portfolio_holdings"], ["portfolio_date"]),
        "benchmark_indices": clean_generic_dates(raw["benchmark_indices"], ["date"]),
    }
    return cleaned


def build_dim_date(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    date_values: list[pd.Series] = [
        pd.to_datetime(cleaned["nav_history"]["date"]),
        pd.to_datetime(cleaned["investor_transactions"]["transaction_date"]),
        pd.to_datetime(cleaned["aum_by_fund_house"]["date"]),
        pd.to_datetime(cleaned["benchmark_indices"]["date"]),
        pd.to_datetime(cleaned["portfolio_holdings"]["portfolio_date"]),
    ]
    all_dates = pd.Series(pd.concat(date_values).dropna().unique()).sort_values()
    dim = pd.DataFrame({"full_date": pd.to_datetime(all_dates)})
    dim["date_key"] = date_key(dim["full_date"])
    dim["year"] = dim["full_date"].dt.year
    dim["quarter"] = dim["full_date"].dt.quarter
    dim["month"] = dim["full_date"].dt.month
    dim["month_name"] = dim["full_date"].dt.month_name()
    dim["year_month"] = dim["full_date"].dt.strftime("%Y-%m")
    dim["day_of_month"] = dim["full_date"].dt.day
    dim["day_of_week"] = dim["full_date"].dt.day_name()
    dim["is_weekend"] = dim["full_date"].dt.weekday.isin([5, 6]).astype(int)
    dim["full_date"] = dim["full_date"].dt.date
    return dim[
        [
            "date_key",
            "full_date",
            "year",
            "quarter",
            "month",
            "month_name",
            "year_month",
            "day_of_month",
            "day_of_week",
            "is_weekend",
        ]
    ]


def write_processed_csvs(cleaned: dict[str, pd.DataFrame]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for index, (name, df) in enumerate(cleaned.items(), start=1):
        output = PROCESSED_DIR / f"{index:02d}_{name}_cleaned.csv"
        df.to_csv(output, index=False)


def write_sql_files() -> None:
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    (SQL_DIR / "schema.sql").write_text(SCHEMA_SQL.strip() + "\n", encoding="utf-8")
    (SQL_DIR / "queries.sql").write_text(QUERIES_SQL.strip() + "\n", encoding="utf-8")


def write_data_dictionary(cleaned: dict[str, pd.DataFrame]) -> None:
    descriptions = {
        "fund_master": "Master metadata for mutual fund schemes. Source: 01_fund_master.csv.",
        "nav_history": "Daily NAV history expanded to calendar dates and forward-filled for non-trading days. Source: 02_nav_history.csv.",
        "aum_by_fund_house": "Quarterly AUM by fund house. Source: 03_aum_by_fund_house.csv.",
        "monthly_sip_inflows": "Monthly industry SIP inflows and account metrics. Source: 04_monthly_sip_inflows.csv.",
        "category_inflows": "Monthly net inflows by fund category. Source: 05_category_inflows.csv.",
        "industry_folio_count": "Industry folio counts by broad fund class. Source: 06_industry_folio_count.csv.",
        "scheme_performance": "Scheme-level return, risk, AUM, rating, and anomaly flags. Source: 07_scheme_performance.csv.",
        "investor_transactions": "Investor transaction ledger after transaction/KYC validation. Source: 08_investor_transactions.csv.",
        "portfolio_holdings": "Scheme portfolio holdings by stock and sector. Source: 09_portfolio_holdings.csv.",
        "benchmark_indices": "Benchmark index close values by date. Source: 10_benchmark_indices.csv.",
    }
    business_definitions = {
        "amfi_code": "AMFI scheme identifier used to join fund metadata, NAV, transactions, holdings, and performance.",
        "date": "Calendar date for the observation.",
        "nav": "Net asset value for one scheme unit.",
        "is_forward_filled": "1 when NAV was filled from the previous available NAV for a non-trading date; otherwise 0.",
        "transaction_type": "Standardized transaction category: SIP, Lumpsum, or Redemption.",
        "amount_inr": "Transaction amount in Indian rupees; validated as positive.",
        "kyc_status": "Investor KYC state; allowed values are Verified and Pending.",
        "expense_ratio_pct": "Annual expense ratio percentage; Day 2 validation expects 0.1 to 2.5.",
        "return_anomaly_flag": "1 when a return field is missing or outside +/-100%; otherwise 0.",
        "expense_ratio_anomaly_flag": "1 when expense ratio is outside 0.1 to 2.5%; otherwise 0.",
    }
    lines = [
        "# Bluestock Mutual Fund Data Dictionary",
        "",
        "Generated by `day2_clean_load.py` from the 10 provided raw CSV datasets.",
        "",
        "## SQLite Star Schema",
        "",
        "- `dim_fund`: scheme master dimension keyed by `amfi_code`.",
        "- `dim_date`: reusable calendar dimension keyed by `date_key` in `YYYYMMDD` format.",
        "- `fact_nav`: NAV time series by fund and date.",
        "- `fact_transactions`: investor transaction events by fund and date.",
        "- `fact_performance`: scheme-level performance, risk, and AUM facts.",
        "- `fact_aum`: fund-house AUM facts by date.",
        "",
        "## Cleaned Dataset Columns",
        "",
    ]
    for name, df in cleaned.items():
        lines.extend([f"### {name}", "", descriptions[name], "", "| Column | Data Type | Business Definition | Source |", "|---|---:|---|---|"])
        source = RAW_FILES[name]
        for col, dtype in df.dtypes.items():
            definition = business_definitions.get(col, col.replace("_", " ").capitalize())
            lines.append(f"| `{col}` | `{dtype}` | {definition} | `{source}` |")
        lines.append("")
    Path("data_dictionary.md").write_text("\n".join(lines), encoding="utf-8")


def load_sqlite(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if DB_PATH.exists():
        DB_PATH.unlink()

    engine = create_engine(f"sqlite:///{DB_PATH}")
    with engine.begin() as conn:
        for statement in SCHEMA_SQL.split(";"):
            if statement.strip():
                conn.execute(text(statement))

    dim_date = build_dim_date(cleaned)
    dim_date.to_sql("dim_date", engine, if_exists="append", index=False)
    cleaned["fund_master"].to_sql("dim_fund", engine, if_exists="append", index=False)

    fact_nav = cleaned["nav_history"].copy()
    fact_nav["date_key"] = date_key(fact_nav["date"])
    fact_nav = fact_nav[["amfi_code", "date_key", "nav", "is_forward_filled"]]
    fact_nav.to_sql("fact_nav", engine, if_exists="append", index=False)

    fact_transactions = cleaned["investor_transactions"].copy()
    fact_transactions["date_key"] = date_key(fact_transactions["transaction_date"])
    fact_transactions = fact_transactions[
        [
            "transaction_id",
            "investor_id",
            "amfi_code",
            "date_key",
            "transaction_type",
            "amount_inr",
            "state",
            "city",
            "city_tier",
            "age_group",
            "gender",
            "annual_income_lakh",
            "payment_mode",
            "kyc_status",
        ]
    ]
    fact_transactions.to_sql("fact_transactions", engine, if_exists="append", index=False)

    fact_performance = cleaned["scheme_performance"].copy()
    fact_performance = fact_performance[
        [
            "amfi_code",
            "return_1yr_pct",
            "return_3yr_pct",
            "return_5yr_pct",
            "benchmark_3yr_pct",
            "alpha",
            "beta",
            "sharpe_ratio",
            "sortino_ratio",
            "std_dev_ann_pct",
            "max_drawdown_pct",
            "aum_crore",
            "expense_ratio_pct",
            "morningstar_rating",
            "risk_grade",
            "return_anomaly_flag",
            "expense_ratio_anomaly_flag",
        ]
    ]
    fact_performance.to_sql("fact_performance", engine, if_exists="append", index=False)

    fact_aum = cleaned["aum_by_fund_house"].copy()
    fact_aum["date_key"] = date_key(fact_aum["date"])
    fact_aum = fact_aum[["date_key", "fund_house", "aum_lakh_crore", "aum_crore", "num_schemes"]]
    fact_aum.to_sql("fact_aum", engine, if_exists="append", index=False)

    for name, df in cleaned.items():
        df.to_sql(f"cleaned_{name}", engine, if_exists="replace", index=False)

    expected_counts = {
        f"cleaned_{name}": len(df)
        for name, df in cleaned.items()
    } | {
        "dim_fund": len(cleaned["fund_master"]),
        "dim_date": len(dim_date),
        "fact_nav": len(fact_nav),
        "fact_transactions": len(fact_transactions),
        "fact_performance": len(fact_performance),
        "fact_aum": len(fact_aum),
    }
    rows: list[dict[str, int | str]] = []
    with engine.begin() as conn:
        for table_name, expected in expected_counts.items():
            actual = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
            rows.append(
                {
                    "table_name": table_name,
                    "expected_rows": expected,
                    "actual_rows": actual,
                    "status": "match" if expected == actual else "mismatch",
                }
            )
    report = pd.DataFrame(rows).sort_values("table_name")
    report.to_csv(PROCESSED_DIR / "sqlite_row_count_validation.csv", index=False)
    return report


def write_quality_report(raw: dict[str, pd.DataFrame], cleaned: dict[str, pd.DataFrame]) -> None:
    rows = []
    for name, raw_df in raw.items():
        clean_df = cleaned[name]
        rows.append(
            {
                "dataset": name,
                "source_rows": len(raw_df),
                "cleaned_rows": len(clean_df),
                "notes": "NAV expanded to calendar dates with forward-fill"
                if name == "nav_history"
                else "Cleaned rows match source rows"
                if len(raw_df) == len(clean_df)
                else "Rows changed during cleaning",
            }
        )
    rows.extend(
        [
            {
                "dataset": "nav_history",
                "source_rows": len(raw["nav_history"]),
                "cleaned_rows": len(cleaned["nav_history"]),
                "notes": f"{int(cleaned['nav_history']['is_forward_filled'].sum())} forward-filled NAV row(s); all NAV values > 0",
            },
            {
                "dataset": "investor_transactions",
                "source_rows": len(raw["investor_transactions"]),
                "cleaned_rows": len(cleaned["investor_transactions"]),
                "notes": "transaction_type and kyc_status enums validated; amount_inr > 0",
            },
            {
                "dataset": "scheme_performance",
                "source_rows": len(raw["scheme_performance"]),
                "cleaned_rows": len(cleaned["scheme_performance"]),
                "notes": (
                    f"{int(cleaned['scheme_performance']['return_anomaly_flag'].sum())} return anomaly row(s); "
                    f"{int(cleaned['scheme_performance']['expense_ratio_anomaly_flag'].sum())} expense ratio anomaly row(s)"
                ),
            },
        ]
    )
    pd.DataFrame(rows).to_csv(PROCESSED_DIR / "day2_quality_report.csv", index=False)


def main() -> None:
    raw = read_raw()
    cleaned = clean_all(raw)
    write_processed_csvs(cleaned)
    write_sql_files()
    write_data_dictionary(cleaned)
    write_quality_report(raw, cleaned)
    row_count_report = load_sqlite(cleaned)
    print("SQLite row-count validation:")
    print(row_count_report.to_string(index=False))
    print(f"\nWrote cleaned CSVs to {PROCESSED_DIR}")
    print(f"Wrote SQLite database to {DB_PATH}")
    print(f"Wrote schema and queries to {SQL_DIR}")
    print("Wrote data dictionary to data_dictionary.md")


if __name__ == "__main__":
    main()
