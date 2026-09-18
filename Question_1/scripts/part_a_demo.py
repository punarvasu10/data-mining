import boto3
from botocore.client import Config

BUCKET = "annapurna"

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
    config=Config(signature_version="s3v4"),
    region_name="us-east-1"
)

paginator = s3.get_paginator("list_objects_v2")

# Count all sales objects and bytes
all_objects = 0
all_bytes = 0

for page in paginator.paginate(Bucket=BUCKET, Prefix="sales/"):
    for obj in page.get("Contents", []):
        all_objects += 1
        all_bytes += obj["Size"]

# Count S03 October objects and bytes
target_prefix = "sales/store_id=S03/business_date=2024-10-"

target_objects = 0
target_bytes = 0

for page in paginator.paginate(Bucket=BUCKET, Prefix=target_prefix):
    for obj in page.get("Contents", []):
        target_objects += 1
        target_bytes += obj["Size"]

print("========== PART (A) PARTITIONING ==========")
print()
print("Partition layout:")
print("sales/store_id=<store_id>/business_date=<YYYY-MM-DD>/data.parquet")
print()
print("Query: S03 + October 2024")
print("Files potentially scanned:", target_objects)
print("Bytes potentially scanned:", target_bytes)
print()
print("All sales objects:", all_objects)
print("All sales bytes:", all_bytes)
print()
print("Single-folder layout could require scanning all",
      all_objects, "objects and", all_bytes, "bytes.")