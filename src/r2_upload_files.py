
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")

s3 = boto3.client(
    "s3",
    endpoint_url=(
        f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    ),
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)

BUCKET = os.environ["R2_BUCKET_NAME"]

# Local file -> desired object key in R2
FILES = {
    "data/raw/traffic.csv": "raw/traffic.csv",
    "data/processed/cleaned_traffic.csv": "processed/cleaned_traffic.csv",
    "data/processed/hourly_analysis.csv": "processed/hourly_analysis.csv",
    "data/processed/junction_analysis.csv": "processed/junction_analysis.csv",
    "data/processed/weekday_analysis.csv": "processed/weekday_analysis.csv",
    "data/processed/congestion_analysis.csv": "processed/congestion_analysis.csv",
    "data/processed/junction_hourly_analysis.csv": "processed/junction_hourly_analysis.csv",
    "data/processed/signal_recommendations.csv": "processed/signal_recommendations.csv",
    "data/processed/signal_optimization_comparison.csv": "processed/signal_optimization_comparison.csv",
    "data/processed/signal_optimization_summary.json": "processed/signal_optimization_summary.json",
    "data/processed/signal_optimization_summary.txt": "processed/signal_optimization_summary.txt",
}

for local_relative, object_key in FILES.items():
    local_path = PROJECT_DIR / local_relative

    if not local_path.exists():
        print(f"SKIPPED (local file missing): {local_relative}")
        continue

    s3.upload_file(str(local_path), BUCKET, object_key)
    print(f"Uploaded: {local_relative} -> {object_key}")

print("\nUpload finished.")
