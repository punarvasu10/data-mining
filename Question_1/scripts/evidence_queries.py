#!/usr/bin/env python3
import os, json, hashlib, duckdb, pandas as pd

BUCKET=os.environ.get("S3_BUCKET","annapurna")
con=duckdb.connect("evidence.duckdb")
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("""
CREATE OR REPLACE SECRET minio (
 TYPE S3, KEY_ID 'minioadmin', SECRET 'minioadmin', REGION 'us-east-1',
 ENDPOINT 'localhost:9000', URL_STYLE 'path', USE_SSL false
)""")
con.execute("INSTALL postgres; LOAD postgres;")
con.execute("""
ATTACH 'dbname=annapurna user=annapurna password=annapurna host=localhost port=5432'
AS pg (TYPE POSTGRES, READ_ONLY)
""")

def run(period):
    q=f"""
    SELECT
      r.business_date,
      r.store_id,
      COALESCE(c.category_name, 'Bill-level adjustments') AS category_name,
      SUM(r.revenue_amount) AS revenue_inr
    FROM read_parquet('s3://{BUCKET}/curated/store_id=*/business_date=*/data.parquet',
                      hive_partitioning=true) r
    LEFT JOIN pg.products p ON p.product_sk=r.product_sk
    LEFT JOIN pg.product_categories c ON c.category_id=p.category_id
    WHERE r.business_date >= DATE '{period}-01'
      AND r.business_date < DATE '{period}-01' + INTERVAL 1 MONTH
    GROUP BY 1,2,3
    ORDER BY 1,2,3
    """
    return q, con.execute(q).fetchdf()

for period in ["2024-03","2024-10"]:
    q,df=run(period)
    df.to_csv(f"reports/dashboard_{period}.csv",index=False)
    print(f"--- {period} ---")
    print(df.head(10).to_string(index=False))

# Idempotency evidence over curated source.
q="""SELECT COUNT(*) row_count,
          sha256(string_agg(concat_ws('|',bill_no,line_no::VARCHAR,store_id,
                 business_date::VARCHAR,product_sk::VARCHAR,qty::VARCHAR,
                 unit_price::VARCHAR,line_type), '||' ORDER BY bill_no,line_no)) checksum
   FROM read_parquet('s3://annapurna/curated/store_id=*/business_date=*/data.parquet',
                     hive_partitioning=true)"""
print("--- idempotency checksum ---")
print(con.execute(q).fetchall())

# Cross-system evidence: DuckDB owns the join/aggregation while scanning
# Parquet from MinIO and tables through the Postgres extension.
cross="""
EXPLAIN ANALYZE
SELECT r.store_id, s.store_name, COALESCE(c.category_name, 'Bill-level adjustments') AS category_name,
       SUM(r.revenue_amount) revenue_inr
FROM read_parquet('s3://annapurna/curated/store_id=*/business_date=*/data.parquet',
                  hive_partitioning=true) r
JOIN pg.stores s ON s.store_id=r.store_id
LEFT JOIN pg.products p ON p.product_sk=r.product_sk
LEFT JOIN pg.product_categories c ON c.category_id=p.category_id
WHERE r.business_date >= DATE '2024-10-01'
  AND r.business_date < DATE '2024-11-01'
GROUP BY 1,2,3
"""
plan=con.execute(cross).fetchall()
open("evidence/explain_analyze.txt","w",encoding="utf-8").write("\n".join(str(x) for x in plan))
print("EXPLAIN ANALYZE written to evidence/explain_analyze.txt")
