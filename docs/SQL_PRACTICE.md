# FactoryIQ SQL practice

Run these against the seeded synthetic database. Start with `docker compose exec database psql -U factoryiq -d factoryiq`. Use `\d` to inspect relations and `SELECT anchor_date FROM demo_seed;` to orient date filters.

| Level | Exercise | Check your answer |
| --- | --- | --- |
| 1 | Count machines by status and facility. Include facility names. | Totals sum to 20. Look for 16 operational, 3 in maintenance, and 1 offline. |
| 1 | Find SKUs whose available stock is below their reorder point. Calculate the shortage. | Compare with `inventory_availability` and `low_stock.sql`. |
| 1 | Show the five newest movements for a selected SKU. Include its supplier. | Join the movement to part, then part to supplier. Use timestamp and ID to break ties. |
| 2 | Give each supplier its inspection count, failed count and rounded defect rate. | Total inspections sum to 500 on a clean seed. Use decimal division. |
| 2 | Find a batch’s inspection results and measurement count without multiplying the inspection total. | Aggregate measurements by inspection before joining, or count distinct inspection IDs. |
| 2 | Compare overdue work orders per location. Include locations with zero overdue work. | Start with locations, left join equipment, and place the overdue predicate inside an aggregate filter. |
| 3 | Rank the worst three batches by rejection rate within each equipment type. | Pre-aggregate per batch, then use `row_number() OVER (PARTITION BY type ORDER BY rate DESC,batch)`. |
| 3 | Report each machine’s mean elapsed time between recorded stops and mean repair duration. | Merge overlapping intervals first. The first stop has no previous start and contributes no gap. |
| 3 | Compute a seven-day weighted defect rate including days with no inspections. | Generate UTC days, aggregate per day, then use a seven-row frame and `NULLIF`. |
| 4 | Reconcile every balance against the movement ledger. | Usable is received minus consumed and rejected. Reserved is reserved minus consumed and released. |
| 4 | Compare `EXPLAIN (ANALYZE, BUFFERS)` for all machines and one machine over the same period. | Compare scan types, processed rows and buffer hits. Plan costs and execution milliseconds are different quantities. |
| 4 | Trace a last-unit race from two psql sessions inside explicit transactions. | Lock the same part in each. Observe the wait and read the new stock after the first transaction commits. Roll back any changes to the second session. |

Example pattern for supplier rate:

```sql
WITH counted AS (
  SELECT p.supplier_id, count(*) AS inspected,
         count(*) FILTER (WHERE NOT i.passed) AS rejected
  FROM quality_inspections i
  JOIN parts p ON p.id = i.part_id
  GROUP BY p.supplier_id
)
SELECT s.name, c.inspected, c.rejected,
       round(100.0 * c.rejected / nullif(c.inspected, 0), 2) AS defect_pct
FROM counted c
JOIN suppliers s ON s.id = c.supplier_id
ORDER BY defect_pct DESC, s.name;
```

The [query library](../backend/factoryiq/sql/) covers operational use cases. Compare after writing your own solution and explain any differences in denominators or window boundaries.
