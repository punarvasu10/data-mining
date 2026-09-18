#!/usr/bin/env python3
"""
Build dashboard-ready fact Parquet from the normalized object-store data.
Product identity is resolved using (product_code, business_date) against
PostgreSQL products.valid_from/valid_to, not product_code alone.
"""
import os, io
from datetime import date
import duckdb
import boto3
from botocore.client import Config

S3_ENDPOINT=os.environ.get("S3_ENDPOINT","localhost:9000")
S3_HTTP=os.environ.get("S3_HTTP_ENDPOINT","http://localhost:9000")
KEY=os.environ.get("S3_ACCESS_KEY","minioadmin")
SECRET=os.environ.get("S3_SECRET_KEY","minioadmin")
BUCKET=os.environ.get("S3_BUCKET","annapurna")

con=duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute(f"""
CREATE OR REPLACE SECRET minio (
 TYPE S3, KEY_ID '{KEY}', SECRET '{SECRET}', REGION 'us-east-1',
 ENDPOINT '{S3_ENDPOINT}', URL_STYLE 'path', USE_SSL false
)""")
con.execute("INSTALL postgres; LOAD postgres;")
con.execute("""
ATTACH 'dbname=annapurna user=annapurna password=annapurna host=localhost port=5432'
AS pg (TYPE POSTGRES, READ_ONLY)
""")

# Revenue definition from vendor notes:
# SALE, RETURN, DISCOUNT, VOID count; TAX and TENDER do not.
q=f"""
SELECT
  r.bill_no, r.line_no, r.store_id, p.product_sk,
  r.business_date, r.qty, r.unit_price, r.line_type,
  CAST(
    CASE
      WHEN r.line_type IN ('SALE','RETURN','DISCOUNT','VOID')
      THEN r.qty * r.unit_price
      ELSE 0
    END
    AS DECIMAL(18,2)
  ) AS revenue_amount
FROM read_parquet('s3://{BUCKET}/sales/store_id=*/business_date=*/data.parquet', hive_partitioning=true) r
LEFT JOIN pg.products p
  ON p.product_code = r.product_code
 AND r.business_date >= p.valid_from
 AND r.business_date < p.valid_to + INTERVAL 1 DAY
"""
fact=con.execute(q).fetchdf()
if len(fact) != fact[["bill_no","line_no"]].drop_duplicates().shape[0]:
    raise SystemExit("ERROR: fact contains duplicate line keys after product resolution")
print("fact_rows",len(fact))

s3=boto3.client("s3",endpoint_url=S3_HTTP,aws_access_key_id=KEY,
                aws_secret_access_key=SECRET,config=Config(signature_version="s3v4"),
                region_name="us-east-1")
# Replace each partition deterministically.
for (store,ds), g in fact.groupby(["store_id","business_date"], sort=True):
    b=io.BytesIO()
    g.to_parquet(b,index=False,compression="snappy")
    d=str(ds)[:10][:10]
    key=f"curated/store_id={store}/business_date={d}/data.parquet"
    s3.put_object(Bucket=BUCKET,Key=key,Body=b.getvalue())
print("curated object-store dataset written.")
