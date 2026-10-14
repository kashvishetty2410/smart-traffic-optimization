
from pathlib import Path
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_DIR / "data" / "processed" / "cleaned_traffic.csv"
OUTPUT_DIR = PROJECT_DIR / "data" / "processed"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Prototype timings in seconds.
# These values are configurable demonstration assumptions.
GREEN_TIMINGS = {
    "Low": 30,
    "Moderate": 40,
    "High": 50,
    "Very High": 60,
}


def classify_demand(percentile):
    if percentile <= 0.50:
        return "Low"
    elif percentile <= 0.75:
        return "Moderate"
    elif percentile <= 0.90:
        return "High"
    return "Very High"


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            "Cleaned dataset not found. Run data_cleaning.py first."
        )

    df = pd.read_csv(DATA_FILE, parse_dates=["DateTime"])

    # 1. Calculate historical average traffic for each
    # junction and hour of day.
    hourly = (
        df.groupby(["Junction", "Hour"])["Vehicles"]
        .agg(
            average_vehicles="mean",
            maximum_vehicles="max",
            observations="count",
        )
        .reset_index()
    )

    
    # 2. Compare each hourly average with its junction's
    # overall average hourly demand.
    hourly["junction_baseline"] = (
        hourly.groupby("Junction")["average_vehicles"]
        .transform("mean")
    )

    hourly["demand_ratio"] = (
        hourly["average_vehicles"] / hourly["junction_baseline"]
    )

    # 3. Classify demand relative to the junction baseline.
    def classify_demand(ratio):
        if ratio <= 0.75:
            return "Low"
        elif ratio <= 1.00:
            return "Moderate"
        elif ratio <= 1.25:
            return "High"
        return "Very High"

    hourly["demand_category"] = (
        hourly["demand_ratio"].apply(classify_demand)
    )

    # 4. Assign prototype green-light recommendations.
    hourly["recommended_green_seconds"] = (
        hourly["demand_category"].map(GREEN_TIMINGS)
    )


    # 5. Add a clear explanation of the recommendation.
    hourly["recommendation_basis"] = (
        "Historical hourly average and relative junction demand"
    )

    # 6. Sort and save results.
    hourly = hourly.sort_values(
        ["Junction", "Hour"]
    ).reset_index(drop=True)

    output_file = OUTPUT_DIR / "signal_recommendations.csv"
    hourly.to_csv(output_file, index=False)

    # 7. Display a useful summary.
    print("\n========== SIGNAL OPTIMIZATION ==========")
    print(f"Junctions analyzed: {hourly['Junction'].nunique()}")
    print(f"Hourly profiles generated: {len(hourly)}")

    print("\nRecommendations for each junction:")
    summary = (
        hourly.groupby(
            ["Junction", "demand_category"]
        )
        .size()
        .unstack(fill_value=0)
    )
    print(summary.to_string())

    print("\nBusiest recommended hours per junction:")
    for junction, group in hourly.groupby("Junction"):
        busiest = group.nlargest(3, "average_vehicles")

        print(f"\nJunction {junction}:")
        for _, row in busiest.iterrows():
            print(
                f"  {int(row['Hour']):02d}:00 | "
                f"Average vehicles: {row['average_vehicles']:.2f} | "
                f"Demand: {row['demand_category']} | "
                f"Recommended green: "
                f"{int(row['recommended_green_seconds'])} seconds"
            )

    print(f"\nSaved recommendations to: {output_file}")


if __name__ == "__main__":
    main()
