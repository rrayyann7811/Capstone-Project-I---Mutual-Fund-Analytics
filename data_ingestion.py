from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


RAW_DATA_DIR = Path("data/raw")
PROCESSED_DATA_DIR = Path("data/processed")


def normalize_columns(columns: Iterable[str]) -> list[str]:
    return [str(column).strip().lower().replace(" ", "_") for column in columns]


def find_csv_files(raw_dir: Path = RAW_DATA_DIR) -> list[Path]:
    return sorted(
        path
        for path in raw_dir.glob("*.csv")
        if path.is_file() and not path.name.startswith("mfapi_")
    )


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = normalize_columns(df.columns)
    return df


def print_dataset_profile(path: Path, df: pd.DataFrame) -> list[str]:
    anomalies: list[str] = []

    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows:
        anomalies.append(f"{duplicate_rows} duplicate row(s)")

    empty_columns = [column for column in df.columns if df[column].isna().all()]
    if empty_columns:
        anomalies.append(f"empty column(s): {', '.join(empty_columns)}")

    missing_counts = df.isna().sum()
    columns_with_missing = missing_counts[missing_counts > 0]
    if not columns_with_missing.empty:
        missing_summary = ", ".join(
            f"{column}={count}" for column, count in columns_with_missing.items()
        )
        anomalies.append(f"missing values: {missing_summary}")

    unnamed_columns = [column for column in df.columns if column.startswith("unnamed")]
    if unnamed_columns:
        anomalies.append(f"unnamed/index-like column(s): {', '.join(unnamed_columns)}")

    print("\n" + "=" * 100)
    print(f"Dataset: {path.name}")
    print(f"Shape: {df.shape}")
    print("\nDtypes:")
    print(df.dtypes)
    print("\nHead:")
    print(df.head())
    print("\nAnomalies:")
    if anomalies:
        for anomaly in anomalies:
            print(f"- {anomaly}")
    else:
        print("- None found by baseline checks")

    return anomalies


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    normalized_candidates = {candidate.lower() for candidate in candidates}
    for column in df.columns:
        if column.lower() in normalized_candidates:
            return column
    return None


def explore_fund_master(df: pd.DataFrame) -> None:
    print("\n" + "=" * 100)
    print("Fund master exploration")

    fields = {
        "fund houses": ["fund_house", "amc", "amc_name", "mutual_fund_family"],
        "categories": ["category", "scheme_category"],
        "sub-categories": ["sub_category", "subcategory", "scheme_sub_category"],
        "risk grades": ["risk_grade", "risk_category", "risk", "riskometer", "risk_level"],
    }

    for label, candidates in fields.items():
        column = find_column(df, candidates)
        if not column:
            print(f"\nUnique {label}: column not found")
            continue
        unique_values = sorted(df[column].dropna().astype(str).str.strip().unique())
        print(f"\nUnique {label} ({column}) [{len(unique_values)}]:")
        print(unique_values)

    code_column = find_column(
        df,
        ["scheme_code", "amfi_code", "code", "scheme_cd", "scheme_id"],
    )
    if code_column:
        numeric_codes = pd.to_numeric(df[code_column], errors="coerce")
        print("\nAMFI scheme code structure:")
        print(f"- Column: {code_column}")
        print(f"- Non-null codes: {df[code_column].notna().sum()}")
        print(f"- Numeric-looking codes: {numeric_codes.notna().sum()}")
        print(f"- Min/Max numeric code: {numeric_codes.min()} / {numeric_codes.max()}")
        print("- AMFI scheme codes are numeric scheme identifiers used to join master metadata to NAV history.")
    else:
        print("\nAMFI scheme code structure: no scheme code column found")


def validate_amfi_codes(fund_master: pd.DataFrame, nav_history: pd.DataFrame) -> dict[str, int]:
    fund_code_column = find_column(
        fund_master,
        ["scheme_code", "amfi_code", "code", "scheme_cd", "scheme_id"],
    )
    nav_code_column = find_column(
        nav_history,
        ["scheme_code", "amfi_code", "code", "scheme_cd", "scheme_id"],
    )

    if not fund_code_column or not nav_code_column:
        return {
            "fund_master_codes": 0,
            "nav_history_codes": 0,
            "missing_in_nav_history": 0,
        }

    fund_codes = set(fund_master[fund_code_column].dropna().astype(str).str.strip())
    nav_codes = set(nav_history[nav_code_column].dropna().astype(str).str.strip())
    missing_codes = sorted(fund_codes - nav_codes)

    print("\n" + "=" * 100)
    print("AMFI code validation")
    print(f"fund_master codes: {len(fund_codes)}")
    print(f"nav_history codes: {len(nav_codes)}")
    print(f"Missing from nav_history: {len(missing_codes)}")
    if missing_codes:
        print("First 25 missing codes:")
        print(missing_codes[:25])
    else:
        print("Every fund_master code exists in nav_history.")

    return {
        "fund_master_codes": len(fund_codes),
        "nav_history_codes": len(nav_codes),
        "missing_in_nav_history": len(missing_codes),
    }


def main() -> None:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    csv_files = find_csv_files()
    if not csv_files:
        print(f"No CSV files found in {RAW_DATA_DIR.resolve()}.")
        print("Place the 10 provided datasets in data/raw and rerun this script.")
        output_path = PROCESSED_DATA_DIR / "data_quality_summary.csv"
        pd.DataFrame(
            [
                {
                    "dataset": "raw_data",
                    "anomaly": "No provided CSV datasets found in data/raw",
                }
            ]
        ).to_csv(output_path, index=False)
        print(f"Data quality summary written to {output_path}")
        return

    print(f"Found {len(csv_files)} CSV file(s) in {RAW_DATA_DIR}.")
    if len(csv_files) != 10:
        print(f"Expected 10 provided CSV datasets; found {len(csv_files)}.")

    loaded: dict[str, pd.DataFrame] = {}
    anomaly_rows: list[dict[str, str]] = []

    for path in csv_files:
        try:
            df = load_csv(path)
        except Exception as exc:
            print(f"\nFailed to load {path.name}: {exc}")
            anomaly_rows.append({"dataset": path.name, "anomaly": f"load failure: {exc}"})
            continue

        loaded[path.stem.lower()] = df
        anomalies = print_dataset_profile(path, df)
        for anomaly in anomalies:
            anomaly_rows.append({"dataset": path.name, "anomaly": anomaly})

    fund_master_key = next((key for key in loaded if "fund_master" in key), None)
    nav_history_key = next((key for key in loaded if "nav_history" in key), None)

    validation_summary = None
    if fund_master_key:
        explore_fund_master(loaded[fund_master_key])
    else:
        anomaly_rows.append({"dataset": "fund_master", "anomaly": "fund_master CSV not found"})

    if fund_master_key and nav_history_key:
        validation_summary = validate_amfi_codes(
            loaded[fund_master_key],
            loaded[nav_history_key],
        )
    else:
        anomaly_rows.append(
            {
                "dataset": "amfi_validation",
                "anomaly": "fund_master and/or nav_history CSV not found",
            }
        )

    quality_summary = pd.DataFrame(anomaly_rows)
    if validation_summary:
        quality_summary = pd.concat(
            [
                quality_summary,
                pd.DataFrame(
                    [
                        {
                            "dataset": "amfi_validation",
                            "anomaly": (
                                f"{validation_summary['missing_in_nav_history']} fund_master "
                                "code(s) missing from nav_history"
                            ),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    if quality_summary.empty:
        quality_summary = pd.DataFrame(
            [{"dataset": "all", "anomaly": "No baseline anomalies found"}]
        )

    output_path = PROCESSED_DATA_DIR / "data_quality_summary.csv"
    quality_summary.to_csv(output_path, index=False)
    print("\n" + "=" * 100)
    print(f"Data quality summary written to {output_path}")


if __name__ == "__main__":
    main()
