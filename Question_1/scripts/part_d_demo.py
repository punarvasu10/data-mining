import duckdb

con = duckdb.connect()

con.execute("INSTALL postgres; LOAD postgres;")

con.execute("""
ATTACH 'dbname=annapurna user=annapurna password=annapurna host=localhost port=5432'
AS pg (TYPE POSTGRES, READ_ONLY)
""")

# Same query is used for both periods.
# Only the reporting period changes.
query = """
SELECT
    p.product_code,
    p.product_name,
    pr.selling_price,
    pr.effective_from,
    pr.effective_to
FROM pg.products p
JOIN pg.price_revisions pr
    ON pr.product_sk = p.product_sk
WHERE p.product_code = 'P100049'
  AND pr.effective_from < ?
  AND pr.effective_to >= ?
ORDER BY pr.effective_from;
"""

product = "P100049"

periods = [
    ("MARCH 2024", "2024-04-01", "2024-03-01"),
    ("OCTOBER 2024", "2024-11-01", "2024-10-01")
]

print("========== PART (D) HISTORICAL PRICE ==========")
print()
print("Product: P100049 - Britannia Cream Biscuit 60g")
print()

for name, end_date, start_date in periods:
    print(f"----- {name} -----")

    result = con.execute(
        query,
        [end_date, start_date]
    ).fetchdf()

    print(result.to_string(index=False))
    print()

con.close()

print("PART (D) COMPLETE")
