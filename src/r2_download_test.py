
import os
from pathlib import Path

import boto3
import pandas as pd
from dotenv import load_dotenv

# Load project settings
PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")

# Connect to Cloudflare R2
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

BUCKET = os.environ["R2_BUCKET_NAME"]
OBJECT_KEY = "raw/traffic.csv"

# Read the CSV directly from R2
response = s3.get_object(
    Bucket=BUCKET,
    Key=OBJECT_KEY,
)

df = pd.read_csv(response["Body"])

print("\nCloud download successful!")
print(f"Rows: {len(df):,}")
print(f"Columns: {list(df.columns)}")
print("\nFirst five rows:")
print(df.head())
