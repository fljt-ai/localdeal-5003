# Contributing to LocalDeal

This is a course group project. Record each member's actual work in [the contribution statement](docs/CONTRIBUTIONS.md), including evidence and any assistance used.

## Make and review a change

1. Read the [README](README.md), [architecture](docs/ARCHITECTURE.md), and the relevant frontend or database documentation.
2. Start a branch from the current `main`, using a name such as `member-name/improve-search`.
3. Make a focused change. Update documentation when behavior, setup, schema, or interfaces change.
4. Run the checks appropriate to the change and include the results in the pull request.
5. Ask another group member to review the change, explain its behavior, and resolve comments before merging into `main`.

Use your own name and a short description in the branch name. Do not treat a proposed role or an AI-generated change as completed personal work. Retain citations for external code, assets, and ideas; photograph sources are recorded in [asset credits](frontend/docs/ASSET-CREDITS.md).

## Run locally

Use Python 3.10 or newer:

```sh
python3 -B run.py
```

The first start creates a fresh `database/localdeal.db` from the SQL and seed files. Each member uses their own local database; existing data persists on later starts. Runtime databases, sessions, and Python caches are ignored by Git. Commit schema, migration, seed, and operation source files when needed. Use a separate temporary database for destructive experiments.

## Check a change

For database or backend changes, run both suites from the project root:

```sh
python3 -B -m unittest discover -s database/tests -v
python3 -B -m unittest discover -s tests -v
```

These suites create temporary databases and do not modify the running application's database. They include HTTP checks that bind to the local loopback interface.

For frontend changes, also run the dependency-free checks with Node 18 or newer:

```sh
node frontend/tests/http-api.test.js
node frontend/tests/app-state.test.js
```

Node is optional for running the application. For a visual change, inspect the affected page in a browser at desktop and narrow widths. For a changed user flow, perform that flow with the relevant customer or merchant account. Re-run performance experiments only when a change affects the measured behavior; retain the original samples and describe the new measurement conditions.

## Before course submission

Group members must understand and validate the code and explanations they submit. Complete the actual contribution record, verify repository and video access, and confirm the course's rules for reporting AI assistance. Do not add a software license on behalf of other contributors without agreement.
