# Fault-frequency query performance

Measured on PostgreSQL 17.12 (Homebrew), ARM64 macOS, with 205,000 sorter events. The benchmark added 200,000 synthetic rows to an isolated database with 5,000 seed events. It used the production fault-frequency query for one machine over a ten-day UTC window.

| Available indexes | Plan over sorter events | Median execution | Shared hits at the root |
| --- | --- | ---: | ---: |
| Partial equipment and time index plus general time index | Bitmap scan using `sorter_fault_equipment_time_idx` | 0.045 ms | 109 |
| General time index | Bitmap scan using `sorter_time_idx` | 1.260 ms | 1,992 |

The partial index returned 105 qualifying event rows to the heap scan. The general index identified 14,833 timestamp candidates before filtering down to the same 105 events. Both variants produced three grouped fault rows. Elapsed execution was roughly 28× lower in this sample. The partial index adds write and storage cost, and the planner may choose a different path for narrow windows, small data, or an all-machines query.

Each comparison used one warm-up and five measured executions of `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. The indexed variant ran first. The index drop and temporary data were rolled back. PostgreSQL sequences can still advance, so use a disposable seeded database. Timing excludes network and UI rendering.

```sh
# Set DATABASE_URL to a separate seeded database
PYTHONPATH=backend python -m factoryiq.benchmark
```

[Recorded JSON plans](fault-query-plans.json) · [Query](../backend/factoryiq/sql/fault_frequency.sql)
