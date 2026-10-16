
import os
import subprocess
import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv


# --------------------------------------------------
# 1. PROJECT CONFIGURATION
# --------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(PROJECT_DIR / ".env")

BUCKET = os.environ["R2_BUCKET_NAME"]

s3 = boto3.client(
    "s3",
    endpoint_url=(
        f"https://{os.environ['R2_ACCOUNT_ID']}"
        ".r2.cloudflarestorage.com"
    ),
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)


# --------------------------------------------------
# 2. DOWNLOAD RAW DATASET FROM CLOUD
# --------------------------------------------------

def download_dataset():
    print("\n[1/5] Downloading dataset from Cloudflare R2...")

    local_file = RAW_DIR / "traffic.csv"

    s3.download_file(
        BUCKET,
        "raw/traffic.csv",
        str(local_file),
    )

    print(f"Downloaded successfully: {local_file.name}")


# --------------------------------------------------
# 3. RUN EXISTING PROCESSING SCRIPTS
# --------------------------------------------------

def run_script(script_name):
    script_path = PROJECT_DIR / "src" / script_name

    print(f"\nRunning {script_name}...")

    subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PROJECT_DIR),
        check=True,
    )

    print(f"{script_name} completed successfully.")


# --------------------------------------------------
# 4. UPLOAD PROCESSED RESULTS TO CLOUD
# --------------------------------------------------

def upload_results():
    print("\n[5/5] Uploading updated results to Cloudflare R2...")

    files_to_upload = {
        "data/processed/cleaned_traffic.csv":
            "processed/cleaned_traffic.csv",

        "data/processed/data_quality_report.txt":
            "processed/data_quality_report.txt",

        "data/processed/hourly_analysis.csv":
            "processed/hourly_analysis.csv",

        "data/processed/junction_analysis.csv":
            "processed/junction_analysis.csv",

        "data/processed/weekday_analysis.csv":
            "processed/weekday_analysis.csv",

        "data/processed/congestion_analysis.csv":
            "processed/congestion_analysis.csv",

        "data/processed/junction_hourly_analysis.csv":
            "processed/junction_hourly_analysis.csv",

        "data/processed/signal_recommendations.csv":
            "processed/signal_recommendations.csv",

        "data/processed/signal_optimization_comparison.csv":
            "processed/signal_optimization_comparison.csv",

        "data/processed/signal_optimization_summary.json":
            "processed/signal_optimization_summary.json",

        "data/processed/signal_optimization_summary.txt":
            "processed/signal_optimization_summary.txt",

        "data/processed/charts/hourly_traffic.png":
            "processed/charts/hourly_traffic.png",

        "data/processed/charts/junction_traffic.png":
            "processed/charts/junction_traffic.png",

        "data/processed/charts/weekday_traffic.png":
            "processed/charts/weekday_traffic.png",
    }

    for local_relative, object_key in files_to_upload.items():
        local_file = PROJECT_DIR / local_relative

        if not local_file.exists():
            raise FileNotFoundError(
                f"Expected output was not generated: {local_file}"
            )

        s3.upload_file(
            str(local_file),
            BUCKET,
            object_key,
        )

        print(f"Uploaded: {object_key}")


# --------------------------------------------------
# 5. EXECUTE THE COMPLETE PIPELINE
# --------------------------------------------------

def main():
    print("=" * 55)
    print(" SMART TRAFFIC OPTIMIZATION - CLOUD PIPELINE")
    print("=" * 55)

    try:
        download_dataset()

        print("\n[2/5] Cleaning traffic data...")
        run_script("data_cleaning.py")

        print("\n[3/5] Analysing traffic patterns...")
        run_script("traffic_analysis.py")

        print("\n[4/5] Generating signal recommendations...")
        run_script("signal_optimization.py")

        upload_results()

        print("\n" + "=" * 55)
        print("PIPELINE COMPLETED SUCCESSFULLY!")
        print("Raw data source: Cloudflare R2")
        print("Processed results: Cloudflare R2")
        print("=" * 55)

    except Exception as error:
        print("\nPIPELINE FAILED!")
        print(f"Reason: {error}")
        raise


if __name__ == "__main__":
    main()
