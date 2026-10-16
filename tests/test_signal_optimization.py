import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import signal_optimization as so  # noqa: E402


def _cleaned_sample():
    # Four junctions x at least two hours. Missing values are deliberate in
    # one variant used by the malformed-input test.
    records = []
    for junction in range(1, 5):
        for hour in range(24):
            records.append(
                {
                    "DateTime": f"2016-01-01 {hour:02d}:00:00",
                    "Junction": junction,
                    "Vehicles": 10 + junction * 3 + hour,
                    "ID": 1,
                }
            )
    return pd.DataFrame(records)


class SignalOptimizationTests(unittest.TestCase):
    def test_full_dataset_profile_count(self):
        data_file = PROJECT_ROOT / "data" / "processed" / "cleaned_traffic.csv"
        if not data_file.exists():
            self.skipTest("cleaned_traffic.csv is not available")
        df = pd.read_csv(data_file, parse_dates=["DateTime"])
        profiles = so.build_optimization_profiles(df)
        self.assertEqual(len(profiles), 96)
        self.assertEqual(profiles["Junction"].nunique(), 4)
        self.assertEqual(set(profiles["Hour"].unique()), set(range(24)))

    def test_missing_values_raise(self):
        df = _cleaned_sample()
        df.loc[0, "Vehicles"] = None
        with self.assertRaises(ValueError):
            so.validate_cleaned_dataframe(df)

    def test_malformed_values_raise(self):
        df = _cleaned_sample()
        df["Vehicles"] = df["Vehicles"].astype(object)
        df.loc[0, "Vehicles"] = "not-a-number"
        with self.assertRaises(ValueError):
            so.validate_cleaned_dataframe(df)
        df2 = _cleaned_sample()
        df2["Junction"] = df2["Junction"].astype(float)
        df2.loc[0, "Junction"] = 1.5
        with self.assertRaises(ValueError):
            so.validate_cleaned_dataframe(df2)

    def test_invalid_green_bounds_raise(self):
        original_min = so.OPTIMIZED_GREEN_MIN_SECONDS
        original_max = so.OPTIMIZED_GREEN_MAX_SECONDS
        try:
            so.OPTIMIZED_GREEN_MIN_SECONDS = 61
            with self.assertRaises(ValueError):
                so.validate_green_bounds()
        finally:
            so.OPTIMIZED_GREEN_MIN_SECONDS = original_min
            so.OPTIMIZED_GREEN_MAX_SECONDS = original_max

    def test_candidate_greens_within_bounds(self):
        for value in so.candidate_green_seconds():
            self.assertTrue(so.is_feasible_green(value))
            self.assertGreaterEqual(value, so.OPTIMIZED_GREEN_MIN_SECONDS)
            self.assertLessEqual(value, so.OPTIMIZED_GREEN_MAX_SECONDS)

    def test_deterministic_output(self):
        df = _cleaned_sample()
        first = so.build_optimization_profiles(df)
        second = so.build_optimization_profiles(df)
        pd.testing.assert_frame_equal(first, second)

    def test_comparison_logic(self):
        df = _cleaned_sample()
        comparison = so.build_optimization_profiles(df)
        recomputed = comparison["baseline_proxy_score"] > comparison[
            "optimized_proxy_score"
        ]
        self.assertTrue(
            (comparison.loc[recomputed, "comparison_result"] == "Improved").all()
        )
        self.assertTrue(
            (
                comparison.loc[
                    comparison["baseline_proxy_score"]
                    == comparison["optimized_proxy_score"],
                    "comparison_result",
                ]
                == "Unchanged"
            ).all()
        )

    def test_summary_honesty_and_counts(self):
        df = _cleaned_sample()
        comparison = so.build_optimization_profiles(df)
        summary = so.summarize_optimization(comparison)
        counts = {
            summary["overall"]["improved"],
            summary["overall"]["unchanged"],
            summary["overall"]["worsened"],
        }
        self.assertEqual(
            summary["overall"]["improved"]
            + summary["overall"]["unchanged"]
            + summary["overall"]["worsened"],
            len(comparison),
        )
        self.assertEqual(
            summary["observed_input_statistics"]["profile_count"],
            len(comparison),
        )

    def test_json_serializes(self):
        df = _cleaned_sample()
        comparison = so.build_optimization_profiles(df)
        summary = so.summarize_optimization(comparison)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            path.write_text(json.dumps(summary), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["overall"]["profiles"], len(comparison))

    def test_missing_output_path_does_not_change_defaults(self):
        self.assertTrue(so.OPTIMIZATION_COMPARISON_FILE.name.endswith(".csv"))


if __name__ == "__main__":
    unittest.main()
