
from pathlib import Path
import pandas as pd

# Project paths
PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_FILE = PROJECT_DIR / "data" / "raw" / "traffic.csv"
OUTPUT_DIR = PROJECT_DIR / "data" / "processed"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CLEANED_FILE = OUTPUT_DIR / "cleaned_traffic.csv"
REPORT_FILE = OUTPUT_DIR / "data_quality_report.txt"


def main():
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {RAW_FILE}\n"
            "Place traffic.csv inside data/raw/."
        )

    # 1. Load the original dataset
    df = pd.read_csv(RAW_FILE)
    original_rows = len(df)

    print("\n========== DATASET AUDIT ==========")
    print(f"Original rows: {original_rows}")
    print(f"Original columns: {list(df.columns)}")
    print("\nFirst five records:")
    print(df.head())

    # 2. Check required columns
    required_columns = {"DateTime", "Junction", "Vehicles"}
    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Required columns missing: {sorted(missing_columns)}"
        )

    # 3. Standardize column names
    df.columns = df.columns.str.strip()

    # 4. Convert columns to appropriate data types
    df["DateTime"] = pd.to_datetime(
        df["DateTime"], errors="coerce"
    )
    df["Junction"] = pd.to_numeric(
        df["Junction"], errors="coerce"
    )
    df["Vehicles"] = pd.to_numeric(
        df["Vehicles"], errors="coerce"
    )

    if "ID" in df.columns:
        df["ID"] = pd.to_numeric(df["ID"], errors="coerce")

    # 5. Record data quality issues before removing rows
    missing_before = int(df.isna().sum().sum())
    invalid_timestamps = int(df["DateTime"].isna().sum())
    invalid_junctions = int(df["Junction"].isna().sum())
    invalid_vehicle_counts = int(df["Vehicles"].isna().sum())

    negative_vehicle_counts = int(
        (df["Vehicles"] < 0).fillna(False).sum()
    )

    exact_duplicates = int(df.duplicated().sum())

    # A junction should normally have one record per timestamp.
    repeated_junction_timestamps = int(
        df.duplicated(subset=["DateTime", "Junction"]).sum()
    )

    # 6. Remove exact duplicate rows
    df = df.drop_duplicates().copy()

    # 7. Remove records that cannot support the required analysis
    df = df.dropna(
        subset=["DateTime", "Junction", "Vehicles"]
    ).copy()

    df = df[df["Vehicles"] >= 0].copy()

    # Junction IDs should be whole numbers
    df = df[df["Junction"] % 1 == 0].copy()
    df["Junction"] = df["Junction"].astype("int64")

    # Vehicle counts should also be whole numbers
    df = df[df["Vehicles"] % 1 == 0].copy()
    df["Vehicles"] = df["Vehicles"].astype("int64")

    # 8. Create features for traffic analysis
    df["Date"] = df["DateTime"].dt.date.astype(str)
    df["Hour"] = df["DateTime"].dt.hour
    df["DayOfWeek"] = df["DateTime"].dt.day_name()
    df["Month"] = df["DateTime"].dt.month
    df["Year"] = df["DateTime"].dt.year
    df["IsWeekend"] = df["DateTime"].dt.dayofweek >= 5

    # Sort records for easier analysis
    df = df.sort_values(
        ["Junction", "DateTime"]
    ).reset_index(drop=True)

    # 9. Save cleaned data
    df.to_csv(CLEANED_FILE, index=False)

    # 10. Generate a data quality report
    report = [
        "TRAFFIC DATA QUALITY REPORT",
        "=" * 32,
        f"Input file: {RAW_FILE.name}",
        f"Original rows: {original_rows}",
        f"Final rows: {len(df)}",
        f"Rows removed: {original_rows - len(df)}",
        f"Original columns: {list(pd.read_csv(RAW_FILE, nrows=0).columns)}",
        f"Final columns: {list(df.columns)}",
        "",
        "QUALITY CHECKS",
        "-" * 32,
        f"Missing values before cleaning: {missing_before}",
        f"Invalid timestamps: {invalid_timestamps}",
        f"Invalid junction values: {invalid_junctions}",
        f"Invalid vehicle counts: {invalid_vehicle_counts}",
        f"Negative vehicle counts: {negative_vehicle_counts}",
        f"Exact duplicate rows: {exact_duplicates}",
        (
            "Repeated timestamp-junction combinations: "
            f"{repeated_junction_timestamps}"
        ),
        "",
        "FINAL DATASET",
        "-" * 32,
        f"Remaining missing values: {int(df.isna().sum().sum())}",
        f"Junctions: {sorted(df['Junction'].unique().tolist())}",
        f"Date range: {df['DateTime'].min()} to {df['DateTime'].max()}",
        f"Average vehicles per record: {df['Vehicles'].mean():.2f}",
        f"Cleaned file: {CLEANED_FILE}",
    ]

    REPORT_FILE.write_text("\n".join(report), encoding="utf-8")

    print("\n========== CLEANING SUMMARY ==========")
    print("\n".join(report))
    print("\nCleaning completed successfully!")


if __name__ == "__main__":
    main()
