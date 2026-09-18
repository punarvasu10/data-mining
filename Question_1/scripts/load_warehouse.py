
import io
import duckdb
import psycopg2

d = duckdb.connect("load_warehouse.duckdb")

d.execute("INSTALL httpfs; LOAD httpfs;")

d.execute("""
CREATE OR REPLACE SECRET minio (
    TYPE S3,
    KEY_ID 'minioadmin',
    SECRET 'minioadmin',
    REGION 'us-east-1',
    ENDPOINT 'localhost:9000',
    URL_STYLE 'path',
    USE_SSL false
)
""")

pg = psycopg2.connect(
    dbname="annapurna",
    user="annapurna",
    password="annapurna",
    host="localhost",
    port=5432
)

pg.autocommit = False
cur = pg.cursor()

cur.execute("TRUNCATE TABLE fact_sales_line")

query = """
SELECT
    bill_no,
    line_no,
    store_id,
    product_sk,
    business_date,
    qty,
    unit_price,
    line_type,
    revenue_amount
FROM read_parquet(
    's3://annapurna/curated/store_id=*/business_date=*/data.parquet',
    hive_partitioning=true
)
ORDER BY business_date, store_id, bill_no, line_no
"""

reader = d.execute(query).fetch_record_batch(rows_per_batch=50000)

total = 0

for batch in reader:
    df = batch.to_pandas()

    # PostgreSQL BIGINT needs integer values, while nullable Parquet
    # product_sk may arrive in pandas as float because discounts have NULL.
    df["product_sk"] = df["product_sk"].astype("Int64")

    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)

    cur.copy_expert("""
        COPY fact_sales_line
        (bill_no,line_no,store_id,product_sk,business_date,
         qty,unit_price,line_type,revenue_amount)
        FROM STDIN WITH (
            FORMAT CSV,
            NULL '\\N'
        )
    """, buf)

    total += len(df)
    print("loaded", total)

pg.commit()
cur.close()
pg.close()
d.close()

print("FACT LOAD COMPLETE")
print("fact_rows", total)
