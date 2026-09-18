-- Run this exact query for March and October by changing ONLY report_start/report_end.
-- Replace product_code with the requested biscuit code.
WITH params AS (
  SELECT DATE '2024-03-01' AS report_start,
         DATE '2024-04-01' AS report_end,
         'P100003' AS product_code
)
SELECT p.product_code, p.product_name, pr.selling_price,
       pr.effective_from, pr.effective_to
FROM pg.products p
JOIN pg.price_revisions pr ON pr.product_sk=p.product_sk
CROSS JOIN params x
WHERE p.product_code=x.product_code
  AND pr.effective_from < x.report_end
  AND pr.effective_to >= x.report_start
ORDER BY pr.effective_from;
-- For October, change only the two dates in params to:
-- DATE '2024-10-01', DATE '2024-11-01'
