
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError, BotoCoreError

PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")

account_id = os.getenv("R2_ACCOUNT_ID")
access_key = os.getenv("R2_ACCESS_KEY_ID")
secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
bucket_name = os.getenv("R2_BUCKET_NAME")

if not all([account_id, access_key, secret_key, bucket_name]):
    raise ValueError(
        "Missing R2 settings. Check the .env file in the project root."
    )

endpoint_url = f"https://165c2be45724146246bb02d6e5b90809.r2.cloudflarestorage.com"

s3 = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    region_name="auto",
)

try:
    response = s3.head_bucket(Bucket=bucket_name)
    print("R2 connection successful!")
    print(f"Bucket: {bucket_name}")
    print(f"HTTP status: {response['ResponseMetadata']['HTTPStatusCode']}")

except (ClientError, BotoCoreError) as exc:
    print("Could not verify the R2 bucket.")
    print("Check your account ID, credentials, bucket name and permissions.")
    print(f"Error: {exc}")
