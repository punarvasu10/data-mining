-- Dimension/fact model for the dashboard.
-- PostgreSQL owns master dimensions; the fact is written as partitioned Parquet.

CREATE TABLE IF NOT EXISTS dim_date (
  date_key DATE PRIMARY KEY,
  day_of_week INTEGER NOT NULL,
  day_name TEXT NOT NULL,
  month_key DATE NOT NULL,
  month_name TEXT NOT NULL,
  year INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_sales_line (
  bill_no TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  store_id TEXT NOT NULL REFERENCES stores(store_id),
  product_sk BIGINT REFERENCES products(product_sk),
  business_date DATE NOT NULL REFERENCES dim_date(date_key),
  qty NUMERIC(18,3) NOT NULL,
  unit_price NUMERIC(18,2) NOT NULL,
  line_type TEXT NOT NULL,
  revenue_amount NUMERIC(18,2) NOT NULL,
  PRIMARY KEY (bill_no, line_no)
);

CREATE INDEX IF NOT EXISTS ix_fact_sales_date ON fact_sales_line(business_date);
CREATE INDEX IF NOT EXISTS ix_fact_sales_store ON fact_sales_line(store_id);
CREATE INDEX IF NOT EXISTS ix_fact_sales_product ON fact_sales_line(product_sk);

-- Dashboard view: store/category/date dimensions without repeating descriptive
-- store attributes in every fact row.
CREATE OR REPLACE VIEW v_sales_dashboard AS
SELECT
  f.business_date,
  EXTRACT(ISODOW FROM f.business_date)::INT AS day_of_week,
  TO_CHAR(f.business_date, 'Day') AS day_name,
  DATE_TRUNC('month', f.business_date)::DATE AS month_key,
  f.store_id,
  s.store_name,
  p.product_sk,
  p.product_code,
  p.product_name,
  c.category_id,
  COALESCE(c.category_name, 'Bill-level adjustments') AS category_name,
  f.qty,
  f.unit_price,
  f.line_type,
  f.revenue_amount
FROM fact_sales_line f
JOIN stores s ON s.store_id = f.store_id
LEFT JOIN products p ON p.product_sk = f.product_sk
LEFT JOIN product_categories c ON c.category_id = p.category_id;
