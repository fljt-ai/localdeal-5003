# Transaction contention evaluation

Run: 2026-11-27T12:51:50.176864+08:00 | Python 3.14.4 | SQLite 3.50.4

Each independent run uses a fresh synthetic database, 100 distinct test buyers, 10 available vouchers, and a bounded worker pool. The purchase function uses the application transaction; no live database or network is involved.

| Workers | Runs | Successful purchases per run | Sold-out per run | Busy per run | Median of medians (ms) | Median run p95 (ms) | Median attempts/s |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | 5 | 10 | 90 | 0 | 0.261 | 0.657 | 3177.560 |
| 8 | 5 | 10 | 90 | 0 | 0.263 | 22.833 | 1553.980 |
| 32 | 5 | 10 | 90 | 0 | 0.820 | 117.554 | 643.700 |

All 15 runs verified stock conservation, unique orders, no overselling, idempotent replay of successful purchases, database integrity and foreign keys.

Business operation latency including opening and closing an independent database connection; worker-pool queue time excluded. Overall elapsed includes scheduling; attempts/s includes rejected requests.

SQLite has one writer at a time. Increased worker count can increase lock waiting rather than throughput. These are synthetic local transaction measurements, not web-server capacity or production throughput. The number of successful orders is bounded by stock; busy requests, if any, are reported separately instead of treated as sold-out.
