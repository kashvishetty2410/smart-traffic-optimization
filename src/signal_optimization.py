"""Historical-data signal-timing recommendation and evaluation module.

This module has two parts:

1. Baseline recommendations (retained from the original implementation):
   each ``(Junction, Hour)`` profile is compared with its junction's average
   hourly demand, classified into a relative demand category, and assigned one
   of the prototype green times 30/40/50/60 seconds.

2. Optimized recommendations:
   a deterministic bounded grid search selects a green time from the
   configured [OPTIMIZED_GREEN_MIN_SECONDS, OPTIMIZED_GREEN_MAX_SECONDS] range.

Important limitations
---------------------
The dataset only contains historical vehicle counts.  There are no observed
signal states, queue lengths, waiting times, lane capacities, or phase plans.
Therefore every score produced here is a proxy for demand/capacity alignment,
NOT a measured delay or congestion value.
"""

from pathlib import Path
import json

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_DIR / "data" / "processed" / "cleaned_traffic.csv"
OUTPUT_DIR = PROJECT_DIR / "data" / "processed"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# Configuration / assumptions. These are explicit, editable settings.
# They are demonstration assumptions, not measured traffic-engineering
# parameters.
# ------------------------------------------------------------------

# Retained prototype green times used by the baseline.
GREEN_TIMINGS = {
    "Low": 30,
    "Moderate": 40,
    "High": 50,
    "Very High": 60,
}

# Fixed-cycle assumption. 120 s is a common simple urban cycle and is only an
# assumption here because no real cycle length is available in the dataset.
CYCLE_LENGTH_SECONDS = 120

# Lost time is assumed for each phase (startup + clearance). The dataset does
# not contain signal timing data, so this is a documented prototype value.
LOST_TIME_PER_PHASE_SECONDS = 4
PHASE_COUNT = 4

# A four-phase intersection is assumed to contain the optimized phase plus
# three other phases. Every non-optimized phase must receive at least this
# much green time. This keeps the optimizer from assigning the whole cycle
# to one phase.
OTHER_PHASE_MIN_GREEN_SECONDS = 10

# Bounded green-time search space for the optimized recommendation.
OPTIMIZED_GREEN_MIN_SECONDS = 10
OPTIMIZED_GREEN_MAX_SECONDS = 60

# Candidate levels are whole seconds; this makes the grid search exhaustive but
# still small (51 candidates per profile).
GREEN_CANDIDATE_STEP_SECONDS = 1

# Total lost time across all phases.
TOTAL_LOST_TIME_SECONDS = LOST_TIME_PER_PHASE_SECONDS * PHASE_COUNT

# Largest green time that can be given to the optimized phase while still
# leaving minimum green and lost time for the other phases.
MAX_FEASIBLE_GREEN_SECONDS = min(
    OPTIMIZED_GREEN_MAX_SECONDS,
    CYCLE_LENGTH_SECONDS
    - TOTAL_LOST_TIME_SECONDS
    - (PHASE_COUNT - 1) * OTHER_PHASE_MIN_GREEN_SECONDS,
)

# Output file names.
BASELINE_RECOMMENDATIONS_FILE = OUTPUT_DIR / "signal_recommendations.csv"
OPTIMIZATION_COMPARISON_FILE = (
    OUTPUT_DIR / "signal_optimization_comparison.csv"
)
OPTIMIZATION_SUMMARY_JSON_FILE = (
    OUTPUT_DIR / "signal_optimization_summary.json"
)
OPTIMIZATION_SUMMARY_TEXT_FILE = (
    OUTPUT_DIR / "signal_optimization_summary.txt"
)


def validate_green_bounds():
    """Validate the configured optimization bounds."""
    if OPTIMIZED_GREEN_MIN_SECONDS < 0:
        raise ValueError("OPTIMIZED_GREEN_MIN_SECONDS must be non-negative.")
    if OPTIMIZED_GREEN_MAX_SECONDS < OPTIMIZED_GREEN_MIN_SECONDS:
        raise ValueError(
            "OPTIMIZED_GREEN_MAX_SECONDS must be >= "
            "OPTIMIZED_GREEN_MIN_SECONDS."
        )
    if MAX_FEASIBLE_GREEN_SECONDS < OPTIMIZED_GREEN_MIN_SECONDS:
        raise ValueError(
            "Green-time bounds are infeasible for the configured cycle, "
            "lost time, phase count, and other-phase minimum green."
        )
    if GREEN_CANDIDATE_STEP_SECONDS <= 0:
        raise ValueError("GREEN_CANDIDATE_STEP_SECONDS must be positive.")


validate_green_bounds()


# ------------------------------------------------------------------
# Compatibility aliases for the older, unused percentile classifier.
# ------------------------------------------------------------------


def classify_demand_percentile(percentile):
    """Classify a demand percentile into a prototype category."""
    if percentile <= 0.50:
        return "Low"
    if percentile <= 0.75:
        return "Moderate"
    if percentile <= 0.90:
        return "High"
    return "Very High"


# Backwards-compatible name.
classify_demand = classify_demand_percentile
thresholds = {"Low": 0.50, "Moderate": 0.75, "High": 0.90}


# ------------------------------------------------------------------
# Input validation and data preparation
# ------------------------------------------------------------------


def validate_cleaned_dataframe(df):
    """Validate and normalize a cleaned traffic DataFrame.

    Returns a copy with validated columns.  The function is strict about
    missing values because the optimization is based entirely on historical
    averages.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Input data must be a pandas DataFrame.")
    if df.empty:
        raise ValueError("Input data must not be empty.")

    required_columns = {"DateTime", "Junction", "Vehicles"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(
            "Required columns missing: " + str(sorted(missing_columns))
        )

    work = df.copy()
    work.columns = work.columns.str.strip()

    work["DateTime"] = pd.to_datetime(work["DateTime"], errors="coerce")
    if work["DateTime"].isna().any():
        raise ValueError("Invalid or missing DateTime values in input data.")

    work["Junction"] = pd.to_numeric(work["Junction"], errors="coerce")
    work["Vehicles"] = pd.to_numeric(work["Vehicles"], errors="coerce")

    if work["Junction"].isna().any():
        raise ValueError("Invalid or missing Junction values in input data.")
    if work["Vehicles"].isna().any():
        raise ValueError("Invalid or missing Vehicles values in input data.")
    if (work["Vehicles"] < 0).any():
        raise ValueError("Vehicle counts must be non-negative.")

    # Junction and vehicle counts are expected to be whole numbers.
    if not (work["Junction"] % 1 == 0).all():
        raise ValueError("Junction values must be whole numbers.")
    if not (work["Vehicles"] % 1 == 0).all():
        raise ValueError("Vehicle counts must be whole numbers.")

    junctions = sorted(work["Junction"].unique().tolist())
    if not all(float(j).is_integer() for j in junctions):
        raise ValueError("Junction values must be whole numbers.")

    # Sensible sanity checks for timestamps.
    if work["DateTime"].dt.hour.isna().any():
        raise ValueError("Unable to derive hours from DateTime values.")

    work["Junction"] = work["Junction"].astype("int64")
    work["Vehicles"] = work["Vehicles"].astype("int64")
    work["Hour"] = work["DateTime"].dt.hour.astype("int64")
    if not work["Hour"].between(0, 23).all():
        raise ValueError("Hour values must lie between 0 and 23.")

    return work


def build_hourly_profiles(df):
    """Build one historical demand profile per observed Junction-Hour pair.

    Directly observed statistics: vehicle-count averages, maxima, and
    observation counts.
    """
    work = validate_cleaned_dataframe(df)

    profiles = (
        work.groupby(["Junction", "Hour"], as_index=False)
        .agg(
            average_vehicles=("Vehicles", "mean"),
            maximum_vehicles=("Vehicles", "max"),
            observations=("Vehicles", "size"),
        )
        .sort_values(["Junction", "Hour"])
        .reset_index(drop=True)
    )

    profiles["Junction"] = profiles["Junction"].astype("int64")
    profiles["Hour"] = profiles["Hour"].astype("int64")
    return profiles


# ------------------------------------------------------------------
# Baseline recommendation logic (preserved)
# ------------------------------------------------------------------


def classify_relative_demand(demand_ratio):
    """Classify demand relative to the junction's baseline hourly demand."""
    if demand_ratio <= 0.75:
        return "Low"
    if demand_ratio <= 1.00:
        return "Moderate"
    if demand_ratio <= 1.25:
        return "High"
    return "Very High"


def baseline_green_seconds(category):
    """Map a demand category to the retained prototype green time."""
    if category not in GREEN_TIMINGS:
        raise ValueError(f"Unknown demand category: {category}")
    return int(GREEN_TIMINGS[category])


def add_baseline_recommendations(profiles):
    """Add junction baseline, demand ratio/category, and baseline green."""
    if not isinstance(profiles, pd.DataFrame):
        raise TypeError("profiles must be a pandas DataFrame.")
    required = {"Junction", "Hour", "average_vehicles"}
    missing = required - set(profiles.columns)
    if missing:
        raise ValueError(
            "Profiles missing required columns: " + str(sorted(missing))
        )

    work = profiles.copy()
    work["junction_baseline"] = (
        work.groupby("Junction")["average_vehicles"].transform("mean")
    )
    work["demand_ratio"] = (
        work["average_vehicles"] / work["junction_baseline"]
    )
    work["demand_category"] = work["demand_ratio"].apply(
        classify_relative_demand
    )
    work["recommended_green_seconds"] = work["demand_category"].map(
        baseline_green_seconds
    )
    work["recommendation_basis"] = (
        "Historical hourly average and relative junction demand"
    )
    return work


def build_baseline_profiles(df):
    """Build baseline recommendation profiles from cleaned traffic data."""
    profiles = build_hourly_profiles(df)
    return add_baseline_recommendations(profiles)


# ------------------------------------------------------------------
# Optimization logic
# ------------------------------------------------------------------


def candidate_green_seconds():
    """Return the deterministic, feasible candidate green-time values."""
    validate_green_bounds()
    return [
        int(value)
        for value in range(
            OPTIMIZED_GREEN_MIN_SECONDS,
            OPTIMIZED_GREEN_MAX_SECONDS + 1,
            GREEN_CANDIDATE_STEP_SECONDS,
        )
        if value + (PHASE_COUNT - 1) * OTHER_PHASE_MIN_GREEN_SECONDS
        + TOTAL_LOST_TIME_SECONDS
        <= CYCLE_LENGTH_SECONDS
    ]


def is_feasible_green(value):
    """Check whether a green time is feasible in the configured cycle."""
    value = int(value)
    return (
        OPTIMIZED_GREEN_MIN_SECONDS <= value <= OPTIMIZED_GREEN_MAX_SECONDS
        and value + (PHASE_COUNT - 1) * OTHER_PHASE_MIN_GREEN_SECONDS
        + TOTAL_LOST_TIME_SECONDS
        <= CYCLE_LENGTH_SECONDS
    )


def demand_normalized_target(profile_rows):
    """Calculate an unconstrained target green from relative hourly demand.

    The target is a linear interpolation between the configured minimum and
    maximum green times.  Demand is normalized *within each junction* because
    each junction has its own historical demand scale.

    This is a proxy target, not a measured optimal timing.
    """
    if not isinstance(profile_rows, pd.DataFrame):
        raise TypeError("profile_rows must be a pandas DataFrame.")
    if "average_vehicles" not in profile_rows.columns:
        raise ValueError("profile_rows must contain average_vehicles.")
    if "Junction" not in profile_rows.columns:
        raise ValueError("profile_rows must contain Junction.")

    targets = pd.Series(index=profile_rows.index, dtype=float)
    for junction, group in profile_rows.groupby("Junction"):
        demands = group["average_vehicles"].astype(float)
        minimum = float(demands.min())
        maximum = float(demands.max())
        if maximum == minimum:
            normalized = pd.Series(0.5, index=group.index, dtype=float)
        else:
            normalized = (demands - minimum) / (maximum - minimum)
        target = (
            OPTIMIZED_GREEN_MIN_SECONDS
            + (OPTIMIZED_GREEN_MAX_SECONDS - OPTIMIZED_GREEN_MIN_SECONDS)
            * normalized
        )
        targets.loc[group.index] = target
    return targets


def proxy_alignment_score(green_seconds, target_seconds):
    """Return the demand/capacity alignment proxy score.

    Score = absolute difference between a green time and the demand-normalized
    target green time.  Lower is better.

    This is *not* waiting time.  It is a transparent proxy for how closely a
    discrete green time follows an assumed linear demand relationship.
    """
    return float(abs(int(green_seconds) - float(target_seconds)))


def optimize_profile(baseline_green, target_green):
    """Select the feasible candidate closest to the demand target."""
    baseline_green = int(baseline_green)
    target_green = float(target_green)

    if not is_feasible_green(baseline_green):
        # Scores can still be computed for infeasible baseline values.
        pass

    best_green = None
    best_score = None
    for candidate in candidate_green_seconds():
        score = proxy_alignment_score(candidate, target_green)
        if best_score is None or score < best_score:
            best_green = candidate
            best_score = score
    if best_green is None:
        raise RuntimeError("No feasible green-time candidate was available.")
    return int(best_green), float(best_score)


def add_optimization(profiles):
    """Add demand-normalized targets and optimized green times/scores."""
    if not isinstance(profiles, pd.DataFrame):
        raise TypeError("profiles must be a pandas DataFrame.")

    work = profiles.copy()
    work["target_green_seconds"] = demand_normalized_target(work)

    optimized = [
        optimize_profile(
            baseline_green=int(row.get("recommended_green_seconds", 0)),
            target_green=float(row["target_green_seconds"]),
        )
        for _, row in work.iterrows()
    ]
    work["optimized_green_seconds"] = [item[0] for item in optimized]
    work["optimized_proxy_score"] = [item[1] for item in optimized]

    work["baseline_proxy_score"] = [
        proxy_alignment_score(
            int(row["recommended_green_seconds"]),
            float(row["target_green_seconds"]),
        )
        for _, row in work.iterrows()
    ]

    # Do not force improvements. A worsening or unchanged result is valid and
    # should be reported as such.
    def comparison_status(row):
        if row["optimized_proxy_score"] < row["baseline_proxy_score"]:
            return "Improved"
        if row["optimized_proxy_score"] > row["baseline_proxy_score"]:
            return "Worsened"
        return "Unchanged"

    work["comparison_result"] = work.apply(comparison_status, axis=1)
    work["proxy_score_change"] = (
        work["optimized_proxy_score"] - work["baseline_proxy_score"]
    )
    return work


def build_optimization_profiles(df):
    """Build baseline plus optimized profiles from cleaned traffic data."""
    baseline = build_baseline_profiles(df)
    return add_optimization(baseline)


# ------------------------------------------------------------------
# Evaluation helpers
# ------------------------------------------------------------------


def summarize_optimization(comparison):
    """Create reproducible summary statistics for the optimization run."""
    if not isinstance(comparison, pd.DataFrame):
        raise TypeError("comparison must be a pandas DataFrame.")
    required = {
        "Junction",
        "Hour",
        "average_vehicles",
        "demand_category",
        "recommended_green_seconds",
        "optimized_green_seconds",
        "baseline_proxy_score",
        "optimized_proxy_score",
        "comparison_result",
    }
    missing = required - set(comparison.columns)
    if missing:
        raise ValueError(
            "Comparison missing required columns: " + str(sorted(missing))
        )
    if comparison.empty:
        raise ValueError("Comparison data must not be empty.")

    total = len(comparison)
    status_counts = {
        str(status): int(count)
        for status, count in comparison["comparison_result"].value_counts().items()
    }
    for status in ("Improved", "Unchanged", "Worsened"):
        status_counts.setdefault(status, 0)

    improved = status_counts["Improved"]
    unchanged = status_counts["Unchanged"]
    worsened = status_counts["Worsened"]

    def by_group(column):
        grouped = comparison.groupby(column, sort=True)
        records = []
        for value, group in grouped:
            counts = group["comparison_result"].value_counts().to_dict()
            records.append(
                {
                    column.lower(): (
                        int(value)
                        if float(value).is_integer()
                        else value
                    ),
                    "profiles": int(len(group)),
                    "improved": int(counts.get("Improved", 0)),
                    "unchanged": int(counts.get("Unchanged", 0)),
                    "worsened": int(counts.get("Worsened", 0)),
                    "improved_percent": float(
                        counts.get("Improved", 0) / len(group) * 100
                    ),
                    "mean_baseline_proxy_score": float(
                        group["baseline_proxy_score"].mean()
                    ),
                    "mean_optimized_proxy_score": float(
                        group["optimized_proxy_score"].mean()
                    ),
                    "mean_proxy_score_change": float(
                        group["proxy_score_change"].mean()
                    ),
                    "mean_baseline_green_seconds": float(
                        group["recommended_green_seconds"].mean()
                    ),
                    "mean_optimized_green_seconds": float(
                        group["optimized_green_seconds"].mean()
                    ),
                }
            )
        return records

    summary = {
        "configuration": {
            "cycle_length_seconds": CYCLE_LENGTH_SECONDS,
            "lost_time_per_phase_seconds": LOST_TIME_PER_PHASE_SECONDS,
            "phase_count": PHASE_COUNT,
            "other_phase_min_green_seconds": (
                OTHER_PHASE_MIN_GREEN_SECONDS
            ),
            "optimized_green_min_seconds": (
                OPTIMIZED_GREEN_MIN_SECONDS
            ),
            "optimized_green_max_seconds": (
                OPTIMIZED_GREEN_MAX_SECONDS
            ),
            "green_candidate_step_seconds": (
                GREEN_CANDIDATE_STEP_SECONDS
            ),
            "max_feasible_green_seconds": MAX_FEASIBLE_GREEN_SECONDS,
            "candidate_count": len(candidate_green_seconds()),
        },
        "proxy_metric": {
            "name": "demand_normalized_green_alignment_proxy",
            "direction": "lower_is_better",
            "units": (
                "seconds of green-time alignment error (proxy only; "
                "not measured waiting time)"
            ),
        },
        "observed_input_statistics": {
            "junction_count": int(comparison["Junction"].nunique()),
            "profile_count": int(total),
            "average_baseline_green_seconds": float(
                comparison["recommended_green_seconds"].mean()
            ),
            "average_optimized_green_seconds": float(
                comparison["optimized_green_seconds"].mean()
            ),
        },
        "overall": {
            "profiles": int(total),
            "improved": improved,
            "unchanged": unchanged,
            "worsened": worsened,
            "improved_percent": float(improved / total * 100),
            "unchanged_percent": float(unchanged / total * 100),
            "worsened_percent": float(worsened / total * 100),
            "mean_baseline_proxy_score": float(
                comparison["baseline_proxy_score"].mean()
            ),
            "mean_optimized_proxy_score": float(
                comparison["optimized_proxy_score"].mean()
            ),
            "mean_proxy_score_change": float(
                comparison["proxy_score_change"].mean()
            ),
            "total_proxy_score_improvement": float(
                comparison["baseline_proxy_score"].sum()
                - comparison["optimized_proxy_score"].sum()
            ),
        },
        "by_junction": by_group("Junction"),
        "by_hour": by_group("Hour"),
        "assumptions": [
            "Fixed cycle length of 120 seconds is an assumption, not an "
            "observed signal cycle.",
            "Four signal phases are assumed; only one phase is optimized "
            "per profile.",
            "Lost time of 4 seconds per phase is a prototype assumption.",
            "Non-optimized phases must receive at least 10 seconds each.",
            "Each junction-hour profile is treated independently; traffic "
            "correlation across adjacent hours is not modeled.",
            "Demand normalization is linear within each junction.",
        ],
        "limitations": [
            "Historical vehicle counts are available; measured delay, queue "
            "length, arrival rates, and signal states are not.",
            "Proxy scores are alignment errors, not seconds of waiting time.",
            "No validation against live traffic or real signal response is "
            "claimed.",
        ],
    }
    return summary


def format_summary_text(summary):
    """Convert a summary dictionary to a readable text report."""
    lines = [
        "SIGNAL OPTIMIZATION EVALUATION",
        "=" * 35,
        "",
        "CONFIGURATION",
        "-" * 35,
    ]
    for key, value in summary["configuration"].items():
        lines.append(f"{key}: {value}")

    lines.extend(
        [
            "",
            "PROXY METRIC",
            "-" * 35,
            summary["proxy_metric"]["name"],
            summary["proxy_metric"]["units"],
            f"Direction: {summary['proxy_metric']['direction']}",
            "",
            "OBSERVED INPUT STATISTICS",
            "-" * 35,
        ]
    )
    for key, value in summary["observed_input_statistics"].items():
        lines.append(f"{key}: {value}")

    lines.extend(["", "OVERALL COMPARISON", "-" * 35])
    for key, value in summary["overall"].items():
        lines.append(f"{key}: {value}")

    lines.extend(["", "BY JUNCTION", "-" * 35])
    for record in summary["by_junction"]:
        lines.append(str(record))

    lines.extend(["", "BY HOUR", "-" * 35])
    for record in summary["by_hour"]:
        lines.append(str(record))

    lines.extend(["", "ASSUMPTIONS", "-" * 35])
    lines.extend(f"- {item}" for item in summary["assumptions"])

    lines.extend(["", "LIMITATIONS", "-" * 35])
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------
# Backwards-compatible baseline script entry point
# ------------------------------------------------------------------


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            "Cleaned dataset not found. Run data_cleaning.py first."
        )

    df = pd.read_csv(DATA_FILE, parse_dates=["DateTime"])
    baseline = build_baseline_profiles(df)

    # Preserve the existing baseline output schema.
    baseline_output = baseline.copy()
    baseline.to_csv(BASELINE_RECOMMENDATIONS_FILE, index=False)

    comparison = add_optimization(baseline)
    # Keep machine-friendly, stable column order.
    ordered_columns = [
        "Junction",
        "Hour",
        "average_vehicles",
        "maximum_vehicles",
        "observations",
        "junction_baseline",
        "demand_ratio",
        "demand_category",
        "recommended_green_seconds",
        "target_green_seconds",
        "optimized_green_seconds",
        "baseline_proxy_score",
        "optimized_proxy_score",
        "proxy_score_change",
        "comparison_result",
        "recommendation_basis",
    ]
    ordered_columns = [
        column for column in ordered_columns
        if column in comparison.columns
    ]
    comparison = comparison[ordered_columns].sort_values(
        ["Junction", "Hour"]
    ).reset_index(drop=True)
    comparison.to_csv(OPTIMIZATION_COMPARISON_FILE, index=False)

    summary = summarize_optimization(comparison)
    OPTIMIZATION_SUMMARY_JSON_FILE.write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    OPTIMIZATION_SUMMARY_TEXT_FILE.write_text(
        format_summary_text(summary), encoding="utf-8"
    )

    print("\n========== SIGNAL OPTIMIZATION ==========")
    print(f"Junctions analyzed: {comparison['Junction'].nunique()}")
    print(f"Hourly profiles generated: {len(comparison)}")

    print("\nRecommendations for each junction (baseline):")
    baseline_summary = (
        comparison.groupby(["Junction", "demand_category"])
        .size()
        .unstack(fill_value=0)
    )
    print(baseline_summary.to_string())

    print("\nBusiest recommended hours per junction:")
    for junction, group in comparison.groupby("Junction"):
        busiest = group.nlargest(3, "average_vehicles")

        print(f"\nJunction {junction}:")
        for _, row in busiest.iterrows():
            print(
                f"  {int(row['Hour']):02d}:00 | "
                f"Average vehicles: {row['average_vehicles']:.2f} | "
                f"Demand: {row['demand_category']} | "
                f"Baseline green: "
                f"{int(row['recommended_green_seconds'])} seconds | "
                f"Optimized green: "
                f"{int(row['optimized_green_seconds'])} seconds"
            )

    print("\n========== OPTIMIZATION EVALUATION ==========")
    print(
        f"Improved: {summary['overall']['improved']} "
        f"({summary['overall']['improved_percent']:.1f}%)"
    )
    print(
        f"Unchanged: {summary['overall']['unchanged']} "
        f"({summary['overall']['unchanged_percent']:.1f}%)"
    )
    print(
        f"Worsened: {summary['overall']['worsened']} "
        f"({summary['overall']['worsened_percent']:.1f}%)"
    )
    print(
        "Mean proxy score change: "
        f"{summary['overall']['mean_proxy_score_change']:.4f}"
    )

    print(f"\nSaved baseline recommendations to: {BASELINE_RECOMMENDATIONS_FILE}")
    print(f"Saved optimization comparison to: {OPTIMIZATION_COMPARISON_FILE}")
    print(f"Saved optimization summary to: {OPTIMIZATION_SUMMARY_JSON_FILE}")


if __name__ == "__main__":
    main()
