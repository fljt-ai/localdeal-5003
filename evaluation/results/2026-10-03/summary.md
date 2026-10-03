# LocalDeal Performance Evaluation

Measured on 2026-10-03T01:19:37.610268+08:00 (Hong Kong time).

This is a local synthetic read experiment. Values below were measured; raw samples, SQL and query plans are in `results.json`.

## Environment and method

- Python 3.14.4; SQLite 3.50.4; macOS-27.0.1-arm64-arm-64bit-Mach-O; arm64.
- The live application database was neither opened nor modified. All generated databases and comparison copies were temporary.
- Same data and SQL in both conditions. Baseline removes 13 explicit business secondary indexes; primary-key and UNIQUE indexes, two session indexes, foreign keys, checks and triggers remain.
- Both conditions run ANALYZE, use automatic_index=ON, mmap_size=0 and an 8 MiB SQLite page cache. Each query has three warm-up runs and 30 measured execute+fetchall runs per condition, with randomly interleaved condition order.
- Median and nearest-rank p95 are reported. Connection opening, data generation, EXPLAIN, correctness hashing and JSON encoding are excluded from the SQL timings.
- Each workload uses one fixed entity parameter per scale. Thirty repeats measure repeated local reads of that case, not thirty independently sampled users or stores.
- Every query result was compared across conditions by ordered result hash. Integrity, foreign keys, requested row counts and inventory/sold-count consistency were checked.
- Fixed seed 5003. A deliberately busy store contains 10% of reviews, with distinct users; a frequent buyer has 10% of orders. Other stores/users are distributed deterministically. These are stress cases, not claims about real restaurant behavior.

## Dataset sizes and storage

| Scale | Users | Stores | Reviews | Orders | Baseline MiB | Indexed MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| small | 1,000 | 100 | 5,000 | 2,000 | 1.62 | 2.02 |
| medium | 10,000 | 1,000 | 50,000 | 20,000 | 14.71 | 18.29 |
| large | 20,000 | 2,000 | 100,000 | 50,000 | 31.57 | 39.29 |

## Query results

Ratio = baseline median / indexed median. Above 1 means the indexed condition was faster; below 1 means it was slower in this run. Small differences can be timing noise.

| Scale | Workload | Rows | Baseline median ms | Indexed median ms | Indexed p95 ms | Ratio |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| small | Latest reviews: hot store | 10 | 0.1111 | 0.0083 | 0.0105 | 13.39x |
| small | Latest reviews: regular store | 10 | 0.0179 | 0.0083 | 0.0095 | 2.17x |
| small | Wallet: frequent buyer | 200 | 0.2460 | 0.2356 | 0.2615 | 1.04x |
| small | Wallet: regular buyer | 1 | 0.0055 | 0.0050 | 0.0052 | 1.10x |
| small | Merchant branch ledger | 200 | 0.5304 | 0.2497 | 0.2684 | 2.12x |
| small | District/category discovery | 12 | 0.6059 | 0.6329 | 0.6538 | 0.96x |
| small | Voucher code lookup (control) | 1 | 0.0037 | 0.0037 | 0.0040 | 1.00x |
| medium | Latest reviews: hot store | 10 | 1.1242 | 0.0097 | 0.0142 | 115.80x |
| medium | Latest reviews: regular store | 10 | 0.0202 | 0.0087 | 0.0093 | 2.33x |
| medium | Wallet: frequent buyer | 2,000 | 2.6007 | 2.5024 | 3.0717 | 1.04x |
| medium | Wallet: regular buyer | 2 | 0.0070 | 0.0064 | 0.0085 | 1.10x |
| medium | Merchant branch ledger | 200 | 3.8482 | 0.2908 | 0.3252 | 13.23x |
| medium | District/category discovery | 112 | 8.9109 | 9.4984 | 9.7838 | 0.94x |
| medium | Voucher code lookup (control) | 1 | 0.0038 | 0.0038 | 0.0045 | 0.99x |
| large | Latest reviews: hot store | 10 | 2.2833 | 0.0101 | 0.0132 | 226.45x |
| large | Latest reviews: regular store | 10 | 0.0210 | 0.0089 | 0.0108 | 2.37x |
| large | Wallet: frequent buyer | 5,000 | 6.7220 | 6.3284 | 6.7700 | 1.06x |
| large | Wallet: regular buyer | 3 | 0.0085 | 0.0075 | 0.0081 | 1.13x |
| large | Merchant branch ledger | 250 | 9.6941 | 0.3770 | 0.4032 | 25.72x |
| large | District/category discovery | 223 | 18.0222 | 18.9902 | 19.4321 | 0.95x |
| large | Voucher code lookup (control) | 1 | 0.0038 | 0.0038 | 0.0042 | 1.01x |

## Full guest state diagnostic

This separate diagnostic invokes the current service.state(None) and JSON/UTF-8 encoding on the indexed database. It has one warm-up and three timed runs. It is not an HTTP or browser benchmark.

| Scale | Reviews returned | Payload MiB | Assembly + encoding median ms |
| --- | ---: | ---: | ---: |
| small | 5,000 | 1.43 | 14.33 |
| medium | 50,000 | 14.31 | 154.15 |
| large | 100,000 | 28.64 | 349.11 |

## Interpretation and limits

- The latest-review experiment is a LIMIT 10 sample query. The current review endpoint has no pagination; its full response cannot be inferred from this page-query latency.
- Wallet and merchant workloads use the current full-list SQL. Fetching many matching rows still costs time even when an index avoids sorting or narrows a join.
- Discovery uses store_summary. Inspect its plan before attributing a speed change to the district/category index: the view can aggregate all stores and reviews before the outer filter.
- Voucher lookup keeps its UNIQUE index in both conditions and is a control workload, not a comparison against a table without indexes.
- The actual guest state currently loads all reviews. Rising payload size and assembly time show why database-only improvements do not establish website scalability. Paginated API/UI loading is a future improvement.
- Regular-store result density is almost fixed (about 45 reviews); regular buyers have only 1–3 orders. The hot cases grow with each scale. These different selectivities must not be combined into a general user-population speedup.
- The full-state diagnostic uses only three measured samples and reports its median. Its raw p95 equals its maximum and is not evidence of a stable tail latency.
- These are repeated local reads after warm-up, not controlled cold-cache tests. Filesystem/OS caching, scheduler noise and the synthetic distribution affect timings.
- Indexes increase storage, measured here after VACUUM. Write throughput, HTTP latency, browser rendering, multiple devices, concurrent workloads and production deployment were not measured.
- A successful run checks experiment correctness; it is not a capacity guarantee or maximum supported-user count.

## References

- [SQLite Query Planner](https://www.sqlite.org/queryplanner.html)
- [SQLite EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html)
- [SQLite ANALYZE](https://www.sqlite.org/lang_analyze.html)
