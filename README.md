# LocalDeal

**A database-centered restaurant discovery and digital voucher application for Course 5003, Track 1.**

[GitHub repository](https://github.com/fljt-ai/localdeal-5003) · [中文启动指南](README.zh-CN.md) · [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Demo guide](docs/DEMO-GUIDE.md)

The complete 65-file source tree has been uploaded to the verified **Private** GitHub repository. Repository access requires an authorized GitHub account; group invitations and teacher access have not yet been configured.

LocalDeal helps customers discover fictional Hong Kong restaurants, save favorites, share reviews and purchase simulated dining vouchers. Authorized store staff can inspect their branch orders and redeem vouchers. A vanilla JavaScript frontend connects to a Python HTTP backend and a persistent SQLite database.

![LocalDeal discovery page with fictional demo data](docs/images/discovery.jpg)

## Features

- Search restaurants by name, district, category, menu item or tag; filter and sort in SQL.
- Browse offers and full store details with menu items, ratings and paginated reviews.
- Register or sign in, manage favorites, edit your own reviews and export your own records.
- Purchase simulated vouchers with stock checks, immutable purchase snapshots and idempotent retries.
- View a private voucher wallet with unused, redeemed and expired status filters.
- Redeem vouchers through a merchant workspace restricted to assigned branches.
- Load bounded pages with complete totals; keep store ratings independent of the current review page.

All restaurant details, accounts and transactions are fictional. Payments are simulated.

## Quick start

Use **Python 3.10 or later**. Running the app needs only Python's standard library; no frontend build step or package installation is required.

1. Sign in to GitHub with repository access, then download and extract the [repository](https://github.com/fljt-ai/localdeal-5003), or clone it with the commands below using authenticated Git access. The prepared local source package can also be used.
2. Open a terminal in the project root, beside `run.py`.
3. Run:

```sh
python3 -B run.py
```

4. Open [http://127.0.0.1:8787](http://127.0.0.1:8787) in a browser.
5. Keep the terminal open. Press **Control+C** to stop the server.

On Windows, use `py -3 -B run.py` if that is your Python launcher. On macOS, you can also launch `start.command`; if it lacks executable permission after extraction, use the terminal command above. Open the HTTP address to use the app; opening `frontend/index.html` directly does not connect to the backend.

Use `python3 -B run.py --port 8788` if the default port is occupied. `--db /path/to/copy.db` selects a separate database, and `--verbose` logs HTTP requests. On systems where Python has no IANA time-zone data, install the `tzdata` package to provide the `Asia/Hong_Kong` time zone; see the [Python time-zone documentation](https://docs.python.org/3/library/zoneinfo.html#data-sources).

With authenticated Git access to the private repository, clone the source and enter its project directory:

```sh
git clone https://github.com/fljt-ai/localdeal-5003.git
cd localdeal-5003
```

## Demo accounts

The public **fictional demo password** for these accounts is `LocalDealDemo!2026`.

| Role | Email | Access |
| --- | --- | --- |
| Customer Alex | `alex@example.com` | Personal profile, reviews, favorites and wallet |
| Harbor Bites staff | `harbor.owner@example.com` | Central and Tsim Sha Tsui branches |
| Little Dumpling staff | `dumpling.owner@example.com` | Causeway Bay and Central branches |
| Daily Grind staff | `coffee.owner@example.com` | Tsim Sha Tsui and Causeway Bay branches |

Newly registered accounts are customers. The [demo guide](docs/DEMO-GUIDE.md) describes purchasing a voucher as a customer and redeeming it with the corresponding merchant account.

## Data and database model

First startup creates `database/localdeal.db`, seeds fictional examples using the current Hong Kong date, and migrates the core schema to application version 2. Later startups preserve existing records. The source repository excludes local databases and session records; each checkout creates its own database.

The fresh demo contains 9 users, 3 merchants, 6 stores, 18 menu items, 6 offers, 30 reviews, 3 orders, 1 redemption and 2 favorites. Expired orders retain their historical expiry dates.

The application has **16 tables, 3 views, foreign keys, checks, indexes and transaction/history guards**. The core v1 schema has 15 tables; v2 adds server-side sessions. Prices are stored as integer Hong Kong cents; events use UTC Unix seconds and expiry rules use Hong Kong calendar dates.

- [Current 16-table ER source](database/docs/ER-DIAGRAM.md)
- [Core database design and normalization notes](database/docs/DATABASE-DESIGN.md)
- [Schema](database/schema.sql), [session migration](database/migration_v2.sql), [sample SQL queries](database/queries.sql)

The older `database/docs/er-diagram.svg` shows the 15-table core model and omits the added session table. Back up personal demo data by stopping the server and copying `database/localdeal.db`.

## Repository structure

```text
localdeal-5003/
├── run.py                  # Local server entry point
├── start.command           # macOS launcher
├── frontend/               # HTML, CSS, JavaScript, local photos and UI checks
├── backend/                # HTTP routing, sessions, authorization and services
├── database/               # Schema, migration, seed data and transaction logic
├── tests/                  # Isolated HTTP integration tests
├── evaluation/             # Synthetic data, benchmarks, raw results and figures
├── docs/                   # Architecture, API, demo and course delivery notes
└── .github/workflows/      # Database, API and frontend checks
```

## Tests

From the project root:

```sh
python3 -B -m unittest discover -s database/tests -v
python3 -B -m unittest discover -s tests -v
```

Optional frontend checks use Node.js 18 or later, without npm packages:

```sh
node frontend/tests/http-api.test.js
node frontend/tests/app-state.test.js
```

The tests create temporary databases and preserve the running demo database. On 2026-10-03, **18 database tests, 26 HTTP tests and both frontend check scripts passed locally**. See the [application validation](database/docs/VALIDATION.md) and [frontend validation](frontend/docs/FRONTEND-CHECKS.md) for exact coverage and browser checks.

[GitHub Actions](.github/workflows/checks.yml) is configured for Python 3.10/3.14 and Node 22 on Ubuntu. On 2026-10-03, the initial [Project checks run #1](https://github.com/fljt-ai/localdeal-5003/actions/runs/37096568279) completed successfully for source commit [0fe0b27](https://github.com/fljt-ai/localdeal-5003/commit/0fe0b2781bda8a83fb6eed4a09afe9810fc895a4). This result applies to that commit; see [Actions](https://github.com/fljt-ai/localdeal-5003/actions) for later runs. The workflow follows GitHub's [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

## Evaluation

Two reproducible experiments use temporary synthetic databases:

```sh
python3 -B evaluation/benchmark.py
python3 -B evaluation/pagination_benchmark.py
```

The first compares preserved SQL workloads with and without 13 explicit business secondary indexes. The second compares the former complete guest response with a compact bootstrap plus the first 12 stores, using the same indexed data and JSON encoding boundary.

The largest dataset has **2,000 stores, 100,000 reviews and 50,000 orders**. In the pagination experiment, the combined guest homepage responses decreased from **28.64 MiB to 11.04 KiB**; median service assembly plus JSON encoding decreased from **325.22 ms to 2.79 ms** over 30 measured runs per condition. These are warm synthetic local reads, excluding HTTP, network, browser and concurrent production workloads.

[Evaluation guide](evaluation/README.md) · [Index report](evaluation/results/2026-10-03/summary.md) · [Pagination report](evaluation/results/pagination-2026-10-03/summary.md)

Raw JSON samples and figures are included. Recreating plots optionally requires Matplotlib; the app and benchmark timing scripts do not use it.

## Group work and course delivery

See [contributing](CONTRIBUTING.md), the [group contribution record](docs/CONTRIBUTIONS.md), [publication instructions](docs/GITHUB-PUBLISH.md) and [project status](docs/PROJECT-STATUS.md).

Group members should use their own GitHub accounts. After their accounts are confirmed, the owner can invite them through **Settings → Collaborators → Add people**. Collaborators on a personal private repository have both read and write access; teacher access must also be arranged and verified before submission. See GitHub's [collaborator invitation guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository) and [personal repository permissions](https://docs.github.com/en/enterprise-cloud%40latest/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository).

The final course delivery still needs the confirmed 4–8 group members and undergraduate majors, actual contributions, verified teacher access to the [repository](https://github.com/fljt-ai/localdeal-5003), a 5–8 minute demonstration video and the final `XXXX-report.pdf`. This README is the runnable-code guide, not the final course report. Codex assistance is recorded in the contribution document for the group to review and disclose according to course rules.

## Credits and scope

Food photographs are credited in [asset sources](frontend/docs/ASSET-CREDITS.md). Technical references appear in the architecture and evaluation documents. No project open-source license has been selected; the photographs retain their source terms.

This is a local course demo bound to the loopback interface. It includes password hashing, server-managed sessions, CSRF checks and branch authorization. Email verification, password recovery, real payments and public deployment are outside the implemented scope. Python's HTTP server is intended for this local demonstration; see the [Python documentation](https://docs.python.org/3/library/http.server.html).
