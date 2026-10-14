
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")

import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_DIR / ".env")

account_id = os.getenv("R2_ACCOUNT_ID")
bucket_name = os.getenv("R2_BUCKET_NAME")

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://165c2be45724146246bb02d6e5b90809.r2.cloudflarestorage.com",
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    region_name="auto",
)

print("\n========== ALL FILES IN R2 BUCKET ==========")
print(f"Bucket: {bucket_name}\n")

paginator = s3.get_paginator("list_objects_v2")
total = 0

for page in paginator.paginate(Bucket=bucket_name):
    for obj in page.get("Contents", []):
        print(f"{obj['Key']}  |  {obj['Size']:,} bytes")
        total += 1

if total == 0:
    print("The bucket contains no visible objects.")
else:
    print(f"\nTotal objects found: {total}")

account_id = os.getenv("R2_ACCOUNT_ID")
bucket_name = os.getenv("R2_BUCKET_NAME")

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://165c2be45724146246bb02d6e5b90809.r2.cloudflarestorage.com",
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    region_name="auto",
)

response = s3.list_objects_v2(Bucket=bucket_name, Prefix="data/")

objects = response.get("Contents", [])

print("\n========== FILES IN CLOUDFLARE R2 ==========")

if not objects:
    print("No objects found under data/. Check the bucket and upload paths.")
else:
    for obj in objects:
        print(f"{obj['Key']}  |  {obj['Size']:,} bytes")

    print(f"\nTotal objects listed: {len(objects)}")
