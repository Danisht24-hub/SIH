from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from config import load_settings
from db.connection import connect


def load_observations(limit: int | None = None) -> pd.DataFrame:
    settings = load_settings()
    suffix = f" LIMIT {int(limit)}" if limit else ""
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT airline, origin, destination, travel_date, advance_purchase_days,
                           fare_amount, analysis_fare_amount, cleaning_status, is_outlier,
                           scraped_at FROM flight_observations ORDER BY scraped_at DESC{suffix}"""
            )
            rows = cur.fetchall()
    return pd.DataFrame(rows)


def profile(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"rows": 0, "missing_fare_pct": 0.0, "median_fare": None, "fare_std": None}
    fare = pd.to_numeric(df["analysis_fare_amount"], errors="coerce")
    return {
        "rows": int(len(df)),
        "routes": int(df[["origin", "destination"]].drop_duplicates().shape[0]),
        "airlines": int(df["airline"].nunique(dropna=True)),
        "missing_fare_pct": float(df["fare_amount"].isna().mean() * 100),
        "median_fare": float(np.nanmedian(fare)) if fare.notna().any() else None,
        "fare_std": float(np.nanstd(fare)) if fare.notna().any() else None,
        "outliers": int(df["is_outlier"].fillna(False).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile collected airfare observations with pandas/numpy")
    parser.add_argument("--csv", help="Optional exported flight_observations.csv instead of PostgreSQL")
    args = parser.parse_args()
    df = pd.read_csv(args.csv) if args.csv else load_observations()
    print(profile(df))


if __name__ == "__main__":
    main()
