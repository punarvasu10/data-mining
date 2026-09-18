# Annapurna Stores — Data Mining & Data Warehousing Lab

## Architecture

- **MinIO**: object store for normalized/curated Parquet.
- **PostgreSQL**: stores, products, product categories, price revisions.
- **DuckDB**: analytical query engine. It reads Parquet from MinIO and attaches PostgreSQL directly.

Object-store layout:

`curated/store_id=S03/business_date=2024-10-14/data.parquet`

This gives partition pruning by store and business date. A one-store/one-month query can consider only that store's daily partitions instead of the complete dataset.

## Important source rules

From `billing_notes.md`:
- business date comes from the filename, not the timestamp.
- re-sends can be partial, so do not choose the newest file.
- de-duplicate at `(bill_no,line_no)`.
- keep VOID rows so cancellation nets to zero.
- revenue includes SALE, RETURN, DISCOUNT, VOID; excludes TAX and TENDER.
- product code is not globally unique; resolve it by product validity dates / product_sk.
- March price questions use `price_revisions` effective during the requested period.
- S06-S09 are semicolon CSV; S10-S12 have BOM/epoch timestamps; Parquet also occurs.

## Run

### 1. Start services

```bash
docker compose up -d
docker compose ps
```

### 2. Load the master

```bash
docker exec -i annapurna-postgres psql -U annapurna -d annapurna < /exam/data/masters.sql
docker exec -i annapurna-postgres psql -U annapurna -d annapurna < sql/model.sql
```

### 3. Install Python packages

```bash
python3 -m pip install -r requirements.txt
```

### 4. Ingest and normalize

```bash
python3 scripts/ingest_sales.py
```

Run it three times for idempotency evidence. Because each store-day is rewritten from the full union of input files and deduplicated by `(bill_no,line_no)`, the resulting dataset is deterministic.

### 5. Build the fact

```bash
python3 scripts/build_fact.py
```

### 6. Historical price demo

Open `sql/price_demo.sql`. Run it for March 2024, then change only the two reporting dates to October 2024 and run again. First find a real biscuit product code if needed:

```sql
SELECT product_code, product_name FROM pg.products WHERE category_id='C01' LIMIT 10;
```

### 7. Run evidence queries

```bash
python3 scripts/evidence_queries.py
```

The script creates:
- `reports/dashboard_2024-03.csv`
- `reports/dashboard_2024-10.csv`
- `evidence/explain_analyze.txt`

## Revenue SQL

The core expression is:

```sql
SUM(
  CASE
    WHEN line_type IN ('SALE','RETURN','DISCOUNT','VOID')
    THEN qty * unit_price
    ELSE 0
  END
)
```

Do NOT sum all lines: `TENDER` repeats the bill total and `TAX` is not revenue.

## Historical price query

Use the same query and change only `:report_month`:

```sql
SELECT p.product_name,
       pr.selling_price,
       pr.effective_from,
       pr.effective_to
FROM pg.price_revisions pr
JOIN pg.products p ON p.product_sk = pr.product_sk
WHERE p.product_code = :product_code
  AND pr.effective_from < :report_month_end
  AND pr.effective_to >= :report_month_start
ORDER BY pr.effective_from;
```

For a point-in-time price on a reporting date, select the revision whose interval contains that date.

### 8. Reconciliation

Finance target is `finance_monthly.csv`. The uploaded target currently contains Jan-Dec 2024. Compare it with the pipeline output and classify differences as:

1. **Source-data issue** — e.g. S07 July has three missing export days, which vendor notes say will never exist.
2. **Revenue-definition issue** — e.g. including TENDER or TAX.
3. **Pipeline bug** — e.g. duplicate resend rows or joining products on product_code alone.

Take source-data or definition differences back to Finance for documented reconciliation; fix pipeline bugs before presenting results as final.

## Cross-system evidence

`EXPLAIN ANALYZE` is saved under `evidence/`. In the plan, look for:
- Parquet scan / `READ_PARQUET` for MinIO data.
- PostgreSQL scans for `pg.*` tables.
- Join and aggregation operators in DuckDB.

This is engine evidence, not a documentation claim.


## Final GitHub checklist

Commit the code, `docker-compose.yml`, SQL, README, and the generated evidence/report files. Do not commit database volumes, passwords beyond the lab demo credentials, or the full raw sales dataset unless the exam explicitly asks for it.
