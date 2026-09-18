import os, duckdb, pandas as pd
BUCKET=os.environ.get("S3_BUCKET","annapurna")
con=duckdb.connect("reconciliation.duckdb")
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("""CREATE OR REPLACE SECRET minio (
 TYPE S3, KEY_ID 'minioadmin', SECRET 'minioadmin', REGION 'us-east-1',
 ENDPOINT 'localhost:9000', URL_STYLE 'path', USE_SSL false)""")
con.execute("INSTALL postgres; LOAD postgres;")
con.execute("""ATTACH 'dbname=annapurna user=annapurna password=annapurna host=localhost port=5432'
 AS pg (TYPE POSTGRES, READ_ONLY)""")

actual=con.execute(f"""
SELECT strftime(business_date,'%Y-%m') AS month,
       ROUND(SUM(revenue_amount),2) AS pipeline_revenue
FROM read_parquet('s3://{BUCKET}/curated/store_id=*/business_date=*/data.parquet',
                  hive_partitioning=true)
GROUP BY 1 ORDER BY 1
""").fetchdf()
finance=pd.read_csv("../finance_monthly.csv")
finance["month"]=finance["month"].astype(str)
out=finance[["month","revenue_inr"]].merge(actual,on="month",how="outer")
out["difference"]=out["pipeline_revenue"]-out["revenue_inr"]
out["abs_difference"]=out["difference"].abs()
out.to_csv("reports/reconciliation.csv",index=False)
print(out.to_string(index=False))
print("\nSaved reports/reconciliation.csv")
