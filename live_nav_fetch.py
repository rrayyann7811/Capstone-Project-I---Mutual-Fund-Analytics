from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests


MFAPI_URL = "https://api.mfapi.in/mf/{scheme_code}"
RAW_DATA_DIR = Path("data/raw")

SCHEMES = {
    "125497": "HDFC Top 100 Direct",
    "119551": "SBI Bluechip",
    "120503": "ICICI Bluechip",
    "118632": "Nippon Large Cap",
    "119092": "Axis Bluechip",
    "120841": "Kotak Bluechip",
}


def slugify(value: str) -> str:
    return (
        value.lower()
        .replace("&", "and")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def fetch_scheme_nav(scheme_code: str) -> dict[str, Any]:
    response = requests.get(MFAPI_URL.format(scheme_code=scheme_code), timeout=30)
    response.raise_for_status()
    payload = response.json()
    if "data" not in payload or not isinstance(payload["data"], list):
        raise ValueError(f"Unexpected mfapi response for scheme {scheme_code}")
    return payload


def payload_to_frame(scheme_code: str, scheme_name: str, payload: dict[str, Any]) -> pd.DataFrame:
    meta = payload.get("meta", {})
    df = pd.DataFrame(payload["data"])
    if df.empty:
        return pd.DataFrame(
            columns=[
                "scheme_code",
                "requested_scheme_name",
                "api_scheme_name",
                "date",
                "nav",
                "fetched_at",
            ]
        )

    df["scheme_code"] = str(scheme_code)
    df["requested_scheme_name"] = scheme_name
    df["api_scheme_name"] = meta.get("scheme_name")
    df["fund_house"] = meta.get("fund_house")
    df["scheme_type"] = meta.get("scheme_type")
    df["scheme_category"] = meta.get("scheme_category")
    df["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce").dt.date

    ordered_columns = [
        "scheme_code",
        "requested_scheme_name",
        "api_scheme_name",
        "fund_house",
        "scheme_type",
        "scheme_category",
        "date",
        "nav",
        "fetched_at",
    ]
    return df[ordered_columns]


def main() -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    frames: list[pd.DataFrame] = []
    for scheme_code, scheme_name in SCHEMES.items():
        print(f"Fetching NAV history for {scheme_code} - {scheme_name}")
        payload = fetch_scheme_nav(scheme_code)
        df = payload_to_frame(scheme_code, scheme_name, payload)
        frames.append(df)

        scheme_output = RAW_DATA_DIR / f"mfapi_{scheme_code}_{slugify(scheme_name)}.csv"
        df.to_csv(scheme_output, index=False)
        print(f"Saved {len(df)} row(s) to {scheme_output}")

    combined = pd.concat(frames, ignore_index=True)
    combined_output = RAW_DATA_DIR / "mfapi_key_scheme_nav_history.csv"
    latest_output = RAW_DATA_DIR / "mfapi_key_scheme_latest_nav.csv"

    combined.to_csv(combined_output, index=False)
    latest = (
        combined.sort_values(["scheme_code", "date"], ascending=[True, False])
        .groupby("scheme_code", as_index=False)
        .head(1)
        .reset_index(drop=True)
    )
    latest.to_csv(latest_output, index=False)

    print(f"Saved combined NAV history to {combined_output}")
    print(f"Saved latest NAV snapshot to {latest_output}")


if __name__ == "__main__":
    main()
