# V2 telemetry measurements

Measured locally on ARM64 macOS with PostgreSQL 17.12. The ingestion timer includes JSON decoding, Pydantic validation, per-device locking, readings, threshold checks and commit for preconstructed messages on one stream. MQTT network transit is outside this timer.

| Measurement | Recorded result |
| --- | ---: |
| Successful single-stream inserts | 500 |
| Decode through commit | 0.3316 s |
| Decode-to-commit rate | 1,507.82 readings/s |
| Indexed history median on 200,500 telemetry rows | 0.114 ms |
| Diagnostic sequential history median on the same rows | 4.777 ms |

The history comparison used the production history SQL for a single station/hour and five measured runs following one warm-up per variant. The diagnostic plan used PostgreSQL session planner controls to disable index scans and bitmap scans. The benchmark records full plans and individual execution times. It does not estimate multi-publisher capacity or public service latency.

Use a fresh migrated and V1-seeded disposable database. The benchmark retains its 500 ingestion samples and rolls back the 200,000 comparison rows.

```sh
PYTHONPATH=backend python -m factoryiq.iot_benchmark
```

[Recorded execution plans](iot-benchmark-plans.json) · [History SQL](../backend/factoryiq/sql/iot_history.sql) · [Benchmark source](../backend/factoryiq/iot_benchmark.py)
