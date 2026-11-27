# LocalDeal Pagination Evaluation

Measured on 2026-11-27T12:52:10.352994+08:00 (Hong Kong time).

The original guest read functions are preserved in `baseline_guest.py`. Both versions use the same indexed generated database and JSON envelope. The new homepage sum includes both bootstrap and its first 12-store page. This is service assembly plus JSON encoding, excluding HTTP, network and browser rendering.

Python 3.14.4; SQLite 3.50.4; macOS-27.2.1-arm64-arm-64bit-Mach-O.

Fixed seed 5003; three warm-ups per homepage condition and 30 measured runs, randomly interleaved. Secondary page cases have one warm-up and the same number of measured runs. All generated files are temporary; the live database is never opened.

| Scale | Stores / reviews / orders | Before KiB | After KiB (2 responses) | Before median ms | After median ms | After p95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| small | 100 / 5,000 / 2,000 | 1459.78 | 13.15 | 14.37 | 1.82 | 1.97 |
| medium | 1,000 / 50,000 / 20,000 | 14654.09 | 13.22 | 158.36 | 13.66 | 14.55 |
| large | 2,000 / 100,000 / 50,000 | 29324.30 | 13.24 | 339.94 | 27.25 | 29.22 |

## Large-scale first pages

| Page | Returned / total | Payload KiB | Median ms | p95 ms |
| --- | --- | ---: | ---: | ---: |
| hot_store_reviews | 10 / 10,000 | 4.19 | 0.17 | 0.20 |
| frequent_buyer_wallet | 10 / 5,000 | 4.07 | 1.98 | 2.16 |
| authorized_merchant_ledger | 10 / 250 | 4.22 | 0.26 | 0.30 |
| filtered_discovery | 12 / 223 | 11.56 | 9.94 | 10.11 |

## Correctness and limits

- Generated row counts, foreign keys, integrity and inventory were checked. The first-page store names, full review counts and full ratings agree with the former implementation.
- Pagination changes how much content is returned. Equal full response hashes are neither expected nor claimed; complete records remain accessible on subsequent pages or explicit personal export.
- A hot store has 10% of reviews and a frequent buyer has 10% of orders. The distribution is deliberately synthetic, not observed user behavior.
- Results are warm repeated local reads of fixed cases. Counts and rating aggregates still read matching database rows; rating sort may examine all matching stores, and deep OFFSET pages may cost more.
- The old response contained full menus, coupons and all public reviews. The new response contains a featured card and the first 12 store cards; full menu and review pages load when a detail view opens.
- SQL timings in the older index experiment are a different boundary from this service-plus-encoding experiment. Do not combine their ratios.
- The homepage comparison is for guests. A signed-in discovery page also requests favorites and personal counts; those costs are not included here. The merchant page case includes all authorized stores with no storeId filter, not the entire selected-branch workbench or its extra detail requests.
- HTTP latency, browser rendering time, concurrency, production deployments and a maximum supported-user count are not measured here.
