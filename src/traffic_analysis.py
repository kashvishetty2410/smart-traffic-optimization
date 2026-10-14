
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_DIR / "data" / "processed" / "cleaned_traffic.csv"
OUTPUT_DIR = PROJECT_DIR / "data" / "processed"
CHART_DIR = PROJECT_DIR / "data" / "processed" / "charts"

CHART_DIR.mkdir(parents=True, exist_ok=True)


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            "Cleaned dataset not found. Run data_cleaning.py first."
        )

    df = pd.read_csv(DATA_FILE, parse_dates=["DateTime"])

    # 1. Overall traffic statistics
    print("\n========== TRAFFIC OVERVIEW ==========")
    print(f"Total records: {len(df):,}")
    print(f"Average vehicles: {df['Vehicles'].mean():.2f}")
    print(f"Maximum recorded vehicles: {df['Vehicles'].max()}")
    print(f"Minimum recorded vehicles: {df['Vehicles'].min()}")

    # 2. Peak-hour analysis
    hourly = (
        df.groupby("Hour")["Vehicles"]
        .agg(["mean", "sum", "count"])
        .reset_index()
        .rename(columns={
            "mean": "average_vehicles",
            "sum": "total_vehicles",
            "count": "record_count"
        })
    )

    peak_hour = hourly.loc[hourly["average_vehicles"].idxmax()]

    print("\n========== PEAK HOUR ==========")
    print(f"Busiest average hour: {int(peak_hour['Hour']):02d}:00")
    print(f"Average vehicles per record: {peak_hour['average_vehicles']:.2f}")

    hourly.to_csv(OUTPUT_DIR / "hourly_analysis.csv", index=False)

    # 3. Junction analysis
    junctions = (
        df.groupby("Junction")["Vehicles"]
        .agg(["mean", "median", "max", "count"])
        .reset_index()
        .rename(columns={
            "mean": "average_vehicles",
            "median": "median_vehicles",
            "max": "maximum_vehicles",
            "count": "record_count"
        })
    )

    junctions = junctions.sort_values(
        "average_vehicles", ascending=False
    )

    print("\n========== JUNCTION ANALYSIS ==========")
    print(junctions.round(2).to_string(index=False))

    junctions.to_csv(
        OUTPUT_DIR / "junction_analysis.csv", index=False
    )

    # 4. Day-of-week analysis
    day_order = [
        "Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday"
    ]

    weekday = (
        df.groupby("DayOfWeek")["Vehicles"]
        .mean()
        .reindex(day_order)
        .rename("average_vehicles")
        .reset_index()
    )

    print("\n========== DAY-OF-WEEK ANALYSIS ==========")
    print(weekday.round(2).to_string(index=False))

    weekday.to_csv(
        OUTPUT_DIR / "weekday_analysis.csv", index=False
    )

    # 5. Hourly traffic patterns for each junction
    junction_hourly = (
        df.groupby(["Junction", "Hour"])["Vehicles"]
        .mean()
        .reset_index(name="average_vehicles")
    )

    junction_hourly.to_csv(
        OUTPUT_DIR / "junction_hourly_analysis.csv",
        index=False
    )

    # 6. Relative congestion classification
    # Initial descriptive categories, not physical road capacity.
    # We will validate and refine these for signal optimization.
    def classify_traffic(value):
        if value <= 10:
            return "Low"
        elif value <= 25:
            return "Moderate"
        elif value <= 40:
            return "High"
        return "Very High"

    df["TrafficCategory"] = df["Vehicles"].apply(classify_traffic)

    congestion = (
        df["TrafficCategory"]
        .value_counts()
        .rename_axis("category")
        .reset_index(name="record_count")
    )

    congestion["percentage"] = (
        congestion["record_count"] / len(df) * 100
    )

    print("\n========== TRAFFIC CATEGORIES ==========")
    print(congestion.round(2).to_string(index=False))

    congestion.to_csv(
        OUTPUT_DIR / "congestion_analysis.csv", index=False
    )

    # 7. Generate charts
    plt.figure(figsize=(10, 5))
    plt.plot(
        hourly["Hour"],
        hourly["average_vehicles"],
        marker="o"
    )
    plt.xticks(range(24))
    plt.xlabel("Hour of day")
    plt.ylabel("Average recorded vehicles")
    plt.title("Average Traffic by Hour")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(CHART_DIR / "hourly_traffic.png", dpi=150)
    plt.close()

    plt.figure(figsize=(9, 5))
    plt.bar(
        junctions["Junction"].astype(str),
        junctions["average_vehicles"]
    )
    plt.xlabel("Junction")
    plt.ylabel("Average recorded vehicles")
    plt.title("Average Traffic by Junction")
    plt.tight_layout()
    plt.savefig(CHART_DIR / "junction_traffic.png", dpi=150)
    plt.close()

    plt.figure(figsize=(9, 5))
    plt.bar(
        weekday["DayOfWeek"],
        weekday["average_vehicles"]
    )
    plt.xlabel("Day of week")
    plt.ylabel("Average recorded vehicles")
    plt.title("Average Traffic by Day of Week")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(CHART_DIR / "weekday_traffic.png", dpi=150)
    plt.close()

    print("\nAnalysis completed successfully.")
    print(f"Results saved in: {OUTPUT_DIR}")
    print(f"Charts saved in: {CHART_DIR}")


if __name__ == "__main__":
    main()
