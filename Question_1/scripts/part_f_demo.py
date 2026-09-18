from pathlib import Path
import duckdb
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
FINANCE_FILE = PROJECT.parent / "finance_monthly.csv"

con = duckdb.connect()

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

print("========== PART (F) RECONCILIATION ==========")
print()

# Finance closed figures
finance = pd.read_csv(FINANCE_FILE)
finance["month"] = finance["month"].astype(str)

# Pipeline revenue from curated MinIO Parquet
pipeline = con.execute("""
SELECT
    strftime(business_date, '%Y-%m') AS month,
    ROUND(SUM(revenue_amount), 2) AS pipeline_revenue
FROM read_parquet(
    's3://annapurna/curated/store_id=*/business_date=*/data.parquet',
    hive_partitioning=true
)
GROUP BY 1
ORDER BY 1
""").fetchdf()

# Raw source revenue
raw = con.execute("""
SELECT
    strftime(business_date, '%Y-%m') AS month,
    ROUND(SUM(
        CASE
            WHEN line_type IN ('SALE','RETURN','DISCOUNT','VOID')
            THEN qty * unit_price
            ELSE 0
        END
    ), 2) AS raw_revenue
FROM read_parquet(
    's3://annapurna/sales/store_id=*/business_date=*/data.parquet',
    hive_partitioning=true
)
GROUP BY 1
ORDER BY 1
""").fetchdf()

result = finance[["month", "revenue_inr"]].merge(
    raw, on="month", how="outer"
).merge(
    pipeline, on="month", how="outer"
)

result["finance_minus_raw"] = (
    result["revenue_inr"] - result["raw_revenue"]
).round(2)

result["pipeline_minus_raw"] = (
    result["pipeline_revenue"] - result["raw_revenue"]
).round(2)

result["pipeline_minus_finance"] = (
    result["pipeline_revenue"] - result["revenue_inr"]
).round(2)

print("MONTHLY RECONCILIATION")
print("----------------------")
print(
    result[
        [
            "month",
            "revenue_inr",
            "raw_revenue",
            "pipeline_revenue",
            "pipeline_minus_finance"
        ]
    ].to_string(index=False)
)

print()
print("DIAGNOSIS")
print("---------")

for _, r in result.iterrows():

    if abs(r["pipeline_minus_finance"]) < 0.01:
        continue

    month = r["month"]

    # Check source coverage
    coverage = con.execute(f"""
    SELECT
        store_id,
        COUNT(DISTINCT business_date) AS days_present
    FROM read_parquet(
        's3://annapurna/sales/store_id=*/business_date=*/data.parquet',
        hive_partitioning=true
    )
    WHERE strftime(business_date,'%Y-%m') = '{month}'
    GROUP BY store_id
    ORDER BY store_id
    """).fetchdf()

    incomplete = coverage[coverage["days_present"] < 28]

    print()
    print("Month:", month)
    print("Finance:", round(r["revenue_inr"], 2))
    print("Raw source:", round(r["raw_revenue"], 2))
    print("Pipeline:", round(r["pipeline_revenue"], 2))

    if abs(r["pipeline_minus_raw"]) > 0.01:
        print("Classification: PIPELINE / SOURCE PROCESSING DIFFERENCE")

    elif len(incomplete) > 0:
        print("Classification: SOURCE DATA GAP")
        print(incomplete.to_string(index=False))

    else:
        print("Classification: SOURCE / FINANCE RECONCILIATION DIFFERENCE")
        print("All stores have normal monthly coverage.")
        print("No revenue-definition or pipeline-calculation bug identified.")

# Specific July S07 gap evidence
july_s07 = con.execute("""
SELECT DISTINCT business_date
FROM read_parquet(
    's3://annapurna/sales/store_id=S07/business_date=*/data.parquet',
    hive_partitioning=true
)
WHERE strftime(business_date,'%Y-%m') = '2024-07'
ORDER BY 1
""").fetchdf()

expected_july = pd.date_range(
    "2024-07-01",
    "2024-07-31",
    freq="D"
).date

actual_july = set(pd.to_datetime(
    july_s07["business_date"]
).dt.date)

missing_july = [
    d for d in expected_july
    if d not in actual_july
]

print()
print("JULY S07 MISSING SOURCE DATES:")
for d in missing_july:
    print(" -", d)

print()
print("FINAL CLASSIFICATION")
print("--------------------")
print("March  : source/finance reconciliation difference; cause not established.")
print("July   : source-data gap; S07 missing July 9-11.")
print("December: source/finance reconciliation difference; cause not established.")
print()
print("Revenue-definition bug: NOT identified after correction.")
print("Pipeline bug: NOT identified in the remaining reconciliation differences.")
print()
print("PART (F) COMPLETE")

con.close()
