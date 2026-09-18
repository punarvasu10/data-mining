import duckdb

con = duckdb.connect()

# MinIO / Parquet configuration
con.execute("INSTALL httpfs; LOAD httpfs;")

con.execute("""
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

# PostgreSQL connection
con.execute("INSTALL postgres; LOAD postgres;")

con.execute("""
ATTACH 'dbname=annapurna user=annapurna password=annapurna
host=localhost port=5432'
AS pg (TYPE POSTGRES, READ_ONLY)
""")

print("========== PART (E) CROSS-SYSTEM QUERY ==========")
print()

query = """
SELECT
    r.business_date,
    r.store_id,
    s.store_name,
    COALESCE(c.category_name, 'Bill-level adjustments') AS category_name,
    ROUND(SUM(r.revenue_amount), 2) AS revenue_inr
FROM read_parquet(
    's3://annapurna/curated/store_id=*/business_date=*/data.parquet',
    hive_partitioning=true
) r
JOIN pg.stores s
    ON s.store_id = r.store_id
LEFT JOIN pg.products p
    ON p.product_sk = r.product_sk
LEFT JOIN pg.product_categories c
    ON c.category_id = p.category_id
WHERE r.business_date >= DATE '2024-10-01'
  AND r.business_date < DATE '2024-11-01'
GROUP BY 1,2,3,4
ORDER BY 1,2,4
LIMIT 15
"""

print("QUERY SOURCES:")
print("Sales        : MinIO / Parquet")
print("Master data  : PostgreSQL")
print("Engine       : DuckDB")
print()

print("----- QUERY RESULT -----")
result = con.execute(query).fetchdf()
print(result.to_string(index=False))

print()
print("----- EXPLAIN ANALYZE -----")

plan = con.execute(
    "EXPLAIN ANALYZE " + query.replace("LIMIT 15", "")
).fetchone()[1]

# Print the important engine-evidence lines
keywords = [
    "READ_PARQUET",
    "TABLE_SCAN",
    "Join Type:",
    "File Filters:",
    "Scanning Files:",
    "Total Files Read:",
    "HTTPFS HTTP Stats",
    "#GET:",
    "Total Time:"
]

for line in plan.splitlines():
    if any(k in line for k in keywords):
        print(line)

print()
print("PART (E) COMPLETE")

con.close()
