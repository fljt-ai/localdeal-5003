#!/usr/bin/env python3
"""Reproducible, isolated SQLite read-query experiments using fictional data."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import sqlite3
import statistics
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from baseline_guest import guest_state

SCALES = {
    'small': dict(users=1000, stores=100, reviews=5000, orders=2000),
    'medium': dict(users=10000, stores=1000, reviews=50000, orders=20000),
    'large': dict(users=20000, stores=2000, reviews=100000, orders=50000),
}
BASE_TIME = 1767225600  # Fixed synthetic 2026-01-01 UTC epoch.
EXPIRY = '2030-12-31'


def identifier(kind, number):
    return f'b-{kind}{number:06d}'


def generate(path, counts, seed):
    """Build a NEW database; never read or change the running application's DB."""
    assert not path.exists()
    db = sqlite3.connect(path)
    rng = random.Random(seed)
    n_users, n_stores = counts['users'], counts['stores']
    merchants = max(1, n_stores // 10)
    try:
        db.executescript((ROOT / 'database/schema.sql').read_text())
        db.executescript((ROOT / 'database/migration_v2.sql').read_text())
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        db.executemany('INSERT INTO users VALUES (?,?,?,?,?)',
                       ((identifier('u', i), f'benchmark-{i}@example.com', f'Synthetic User {i}', None, BASE_TIME)
                        for i in range(n_users)))
        db.executemany('INSERT INTO merchants VALUES (?,?,?,?,?)',
                       ((identifier('m', i), identifier('u', i), f'Synthetic Merchant {i}',
                         f'merchant-{i}@example.com', BASE_TIME) for i in range(merchants)))
        db.executemany('INSERT INTO categories VALUES (?,?)', ((f'cat-{i}', f'Category {i}') for i in range(3)))
        db.executemany('INSERT INTO districts VALUES (?,?)', ((f'district-{i}', f'District {i}') for i in range(3)))
        db.executemany('INSERT INTO stores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       ((identifier('s', i), identifier('m', i % merchants), f'cat-{i % 3}',
                         f'district-{(i // 3) % 3}', f'Synthetic Store {i}', f'Synthetic Store {i}',
                         f'{i} Example Street', '09:00-21:00', 'Fictional benchmark store.',
                         8000 + (i % 20) * 500, 'assets/burger.jpg', 1, BASE_TIME)
                        for i in range(n_stores)))
        db.executemany('INSERT INTO store_staff VALUES (?,?,?,?)',
                       ((identifier('s', i), identifier('u', i % merchants), 'owner', 1) for i in range(n_stores)))
        db.executemany('INSERT INTO menu_items VALUES (?,?,?,?,?,?,?)',
                       ((identifier('menu', i * 3 + p), identifier('s', i), f'Menu item {p}',
                         'Fictional menu item.', 4000 + p * 500, p + 1, 1)
                        for i in range(n_stores) for p in range(3)))
        db.executemany('INSERT INTO coupons VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       ((identifier('c', i), identifier('s', i), f'Synthetic offer {i}',
                         'Fictional benchmark offer.', 20000, 5000 + (i % 20) * 500,
                         100000, 100000, EXPIRY, 1, BASE_TIME) for i in range(n_stores)))
        db.executemany('INSERT INTO coupon_terms VALUES (?,?,?)',
                       ((identifier('c', i), 1, 'Valid only at its fictional issuing branch.') for i in range(n_stores)))

        hot_reviews = counts['reviews'] // 10
        assert hot_reviews <= n_users

        def reviews():
            for i in range(counts['reviews']):
                if i < hot_reviews:
                    store, user = 0, i  # One stress-case store holds 10% of all reviews.
                else:
                    j = i - hot_reviews
                    store, user = 1 + j % (n_stores - 1), j // (n_stores - 1)
                timestamp = BASE_TIME + i * 17
                yield (identifier('r', i), identifier('s', store), identifier('u', user),
                       rng.randint(1, 5), f'Synthetic review {i}: fictional food, service and atmosphere for evaluation.',
                       timestamp, timestamp)

        db.executemany('INSERT INTO reviews VALUES (?,?,?,?,?,?,?)', reviews())
        hot_orders = counts['orders'] // 10

        def orders():
            for i in range(counts['orders']):
                user = 0 if i < hot_orders else 1 + (i - hot_orders) % (n_users - 1)
                coupon = i % n_stores
                yield (identifier('o', i), identifier('u', user), identifier('c', coupon),
                       f'Synthetic offer {coupon}', 5000 + (coupon % 20) * 500, 20000,
                       EXPIRY, f'LD-BENCH{i:012d}', f'benchmark-intent-{i}', BASE_TIME + i * 31)

        # Bulk setup is not a simulated purchase transaction. Set corresponding
        # inventory explicitly so generated sold counts and stocks agree.
        db.executemany('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)', orders())
        db.execute('UPDATE coupons SET available_stock = total_stock - '
                   '(SELECT count(*) FROM orders WHERE orders.coupon_id=coupons.coupon_id)')
        db.executemany('INSERT INTO redemptions VALUES (?,?,?)',
                       ((identifier('o', i), identifier('u', (i % n_stores) % merchants), BASE_TIME + i * 31 + 3600)
                        for i in range(0, counts['orders'], 5)))
        db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert not db.execute('SELECT 1 FROM coupons c WHERE total_stock-available_stock != '
                              '(SELECT count(*) FROM orders o WHERE o.coupon_id=c.coupon_id)').fetchone()
        actual = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                  for table in ('users','merchants','stores','reviews','orders','redemptions','coupons','menu_items')}
        assert all(actual[key] == value for key, value in counts.items())
        return actual
    finally:
        db.close()


def prepare_copy(source, target, baseline):
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
        indexes = dst.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL "
                              "AND tbl_name <> 'sessions' ORDER BY name").fetchall()
        assert len(indexes) == 13
        if baseline:
            for (name,) in indexes:
                dst.execute('DROP INDEX "' + name.replace('"','""') + '"')
        dst.commit()
        dst.execute('VACUUM')
        dst.execute('ANALYZE')
        dst.commit()
        assert not dst.execute('PRAGMA foreign_key_check').fetchall()
    return [name for (name,) in indexes]


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA automatic_index=ON')
    db.execute('PRAGMA cache_size=-8192')
    db.execute('PRAGMA mmap_size=0')
    db.execute('PRAGMA query_only=ON')
    return db


def workloads():
    review_sql = ('SELECT r.review_id,u.display_name,r.rating,r.comment FROM reviews r '
                  'JOIN users u ON u.user_id=r.user_id WHERE r.store_id=? '
                  'ORDER BY r.created_at DESC,r.review_id LIMIT 10')
    wallet_sql = 'SELECT * FROM wallet WHERE user_id=? ORDER BY purchased_at DESC,order_id'
    return [
        ('reviews_hot', 'Latest reviews: hot store', review_sql, (identifier('s',0),), 'sample SQL, LIMIT 10; separate from the later paginated service benchmark'),
        ('reviews_regular', 'Latest reviews: regular store', review_sql, (identifier('s',1),), 'sample SQL, LIMIT 10; separate from the later paginated service benchmark'),
        ('wallet_hot', 'Wallet: frequent buyer', wallet_sql, (identifier('u',0),), 'former full-list wallet SQL; all matching orders fetched'),
        ('wallet_regular', 'Wallet: regular buyer', wallet_sql, (identifier('u',999),), 'former full-list wallet SQL; all matching orders fetched'),
        ('merchant', 'Merchant branch ledger',
         'SELECT w.* FROM wallet w JOIN store_staff ss ON ss.store_id=w.store_id '
         'WHERE ss.user_id=? AND ss.is_active=1 ORDER BY w.purchased_at DESC,w.order_id',
         (identifier('u',0),), 'former full-list merchant SQL; all matching branch orders fetched'),
        ('discovery', 'District/category discovery',
         'SELECT store_id,name,district,category,price_per_person_cents,average_rating,review_count '
         'FROM store_summary WHERE is_active=1 AND district_id=? AND category_id=? '
         'ORDER BY average_rating DESC,store_id',
         ('district-0','cat-0'), 'preserved store_summary discovery sample; separate from the later targeted page API'),
        ('code_lookup', 'Voucher code lookup (control)',
         'SELECT order_id,user_id,coupon_id FROM orders WHERE redeem_code=?',
         ('LD-BENCH000000000100',), 'lookup retains the UNIQUE redeem_code constraint index in both conditions'),
    ]


def summary(samples):
    ordered = sorted(samples)
    return {'median_ms':statistics.median(samples), 'p95_ms':ordered[math.ceil(len(samples)*0.95)-1],
            'min_ms':min(samples), 'max_ms':max(samples), 'samples_ms':samples}


def compare(connections, workload, repetitions, rng):
    key, label, sql, parameters, scope = workload
    plans, expected = {}, None
    row_count = None
    for condition, db in connections.items():
        rows = [tuple(row) for row in db.execute(sql,parameters).fetchall()]
        digest = hashlib.sha256(repr(rows).encode()).hexdigest()
        if expected is None:
            expected, row_count = digest, len(rows)
        else:
            assert digest == expected, f'Query results differ for {key}'
        plans[condition] = [dict(row) for row in db.execute('EXPLAIN QUERY PLAN '+sql,parameters)]
        for _ in range(3):
            db.execute(sql,parameters).fetchall()
    samples = {condition:[] for condition in connections}
    for _ in range(repetitions):
        sequence = list(connections)
        rng.shuffle(sequence)
        for condition in sequence:
            started = time.perf_counter_ns()
            rows = connections[condition].execute(sql,parameters).fetchall()
            samples[condition].append((time.perf_counter_ns()-started)/1e6)
    stats = {condition:summary(values) for condition,values in samples.items()}
    return {'id':key,'label':label,'sql':sql,'parameters':list(parameters),'scope':scope,
            'result_rows':row_count,'result_sha256':expected,'results_equal':True,
            'conditions':stats,'speedup_baseline_over_indexed':stats['baseline']['median_ms']/stats['indexed']['median_ms'],
            'plans':plans}


def state_diagnostic(db):
    """Measure the preserved pre-pagination guest assembly, not HTTP latency."""
    def assemble():
        state = guest_state(db)
        encoded = json.dumps({'data':state},ensure_ascii=False,allow_nan=False).encode('utf-8')
        return len(encoded), len(state['reviews'])
    assemble()
    samples = []
    for _ in range(3):
        started = time.perf_counter_ns()
        payload_size, review_count = assemble()
        samples.append((time.perf_counter_ns()-started)/1e6)
    return {**summary(samples),'payload_bytes':payload_size,'reviews_returned':review_count,
            'scope':'indexed database; preserved pre-pagination guest assembly plus server-style JSON/UTF-8 encoding; excludes sockets and browser',
            'measured_runs':3,'warmup_runs':1}


def render_summary(result):
    lines = ['# LocalDeal Performance Evaluation', '', 'Measured on '+result['measured_at_hk']+' (Hong Kong time).', '',
             'This is a local synthetic read experiment. Values below were measured; raw samples, SQL and query plans are in `results.json`.', '',
             '## Environment and method', '',
             f"- Python {result['environment']['python']}; SQLite {result['environment']['sqlite']}; {result['environment']['platform']}; {result['environment']['machine']}.",
             '- The live application database was neither opened nor modified. All generated databases and comparison copies were temporary.',
             '- Same data and SQL in both conditions. Baseline removes 13 explicit business secondary indexes; primary-key and UNIQUE indexes, two session indexes, foreign keys, checks and triggers remain.',
             '- Both conditions run ANALYZE, use automatic_index=ON, mmap_size=0 and an 8 MiB SQLite page cache. Each query has three warm-up runs and '+str(result['repetitions'])+' measured execute+fetchall runs per condition, with randomly interleaved condition order.',
             '- Median and nearest-rank p95 are reported. Connection opening, data generation, EXPLAIN, correctness hashing and JSON encoding are excluded from the SQL timings.',
             '- Each workload uses one fixed entity parameter per scale. Thirty repeats measure repeated local reads of that case, not thirty independently sampled users or stores.',
             '- Every query result was compared across conditions by ordered result hash. Integrity, foreign keys, requested row counts and inventory/sold-count consistency were checked.',
             '- Fixed seed '+str(result['seed'])+'. A deliberately busy store contains 10% of reviews, with distinct users; a frequent buyer has 10% of orders. Other stores/users are distributed deterministically. These are stress cases, not claims about real restaurant behavior.', '',
             '## Dataset sizes and storage', '',
             '| Scale | Users | Stores | Reviews | Orders | Baseline MiB | Indexed MiB |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for run in result['scales']:
        c = run['counts']
        lines.append(f"| {run['scale']} | {c['users']:,} | {c['stores']:,} | {c['reviews']:,} | {c['orders']:,} | {run['storage_bytes']['baseline']/1048576:.2f} | {run['storage_bytes']['indexed']/1048576:.2f} |")
    lines += ['', '## Query results', '',
              'Ratio = baseline median / indexed median. Above 1 means the indexed condition was faster; below 1 means it was slower in this run. Small differences can be timing noise.', '',
              '| Scale | Workload | Rows | Baseline median ms | Indexed median ms | Indexed p95 ms | Ratio |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for run in result['scales']:
        for query in run['queries']:
            a, b = query['conditions']['baseline'], query['conditions']['indexed']
            lines.append(f"| {run['scale']} | {query['label']} | {query['result_rows']:,} | {a['median_ms']:.4f} | {b['median_ms']:.4f} | {b['p95_ms']:.4f} | {query['speedup_baseline_over_indexed']:.2f}x |")
    lines += ['', '## Pre-pagination full guest state diagnostic', '',
              'This separate diagnostic invokes the preserved baseline_guest.guest_state and JSON/UTF-8 encoding on the indexed database. It has one warm-up and three timed runs. It is not an HTTP or browser benchmark.', '',
              '| Scale | Reviews returned | Payload MiB | Assembly + encoding median ms |',
              '| --- | ---: | ---: | ---: |']
    for run in result['scales']:
        d = run['guest_state']
        lines.append(f"| {run['scale']} | {d['reviews_returned']:,} | {d['payload_bytes']/1048576:.2f} | {d['median_ms']:.2f} |")
    lines += ['', '## Interpretation and limits', '',
              '- The latest-review experiment is a LIMIT 10 sample query. Actual paginated service timings are measured separately by pagination_benchmark.py.',
              '- Wallet and merchant workloads retain the former full-list SQL. Fetching many matching rows still costs time even when an index avoids sorting or narrows a join.',
              '- Discovery uses store_summary. Inspect its plan before attributing a speed change to the district/category index: the view can aggregate all stores and reviews before the outer filter.',
              '- Voucher lookup keeps its UNIQUE index in both conditions and is a control workload, not a comparison against a table without indexes.',
              '- The preserved pre-pagination guest state loads all reviews. Rising payload size and assembly time motivated the later compact bootstrap and paginated API/UI; see the separate pagination experiment.',
              '- Regular-store result density is almost fixed (about 45 reviews); regular buyers have only 1–3 orders. The hot cases grow with each scale. These different selectivities must not be combined into a general user-population speedup.',
              '- The full-state diagnostic uses only three measured samples and reports its median. Its raw p95 equals its maximum and is not evidence of a stable tail latency.',
              '- These are repeated local reads after warm-up, not controlled cold-cache tests. Filesystem/OS caching, scheduler noise and the synthetic distribution affect timings.',
              '- Indexes increase storage, measured here after VACUUM. Write throughput, HTTP latency, browser rendering, multiple devices, concurrent workloads and production deployment were not measured.',
              '- A successful run checks experiment correctness; it is not a capacity guarantee or maximum supported-user count.', '',
              '## References', '',
              '- [SQLite Query Planner](https://www.sqlite.org/queryplanner.html)',
              '- [SQLite EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html)',
              '- [SQLite ANALYZE](https://www.sqlite.org/lang_analyze.html)', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scales',nargs='+',choices=SCALES,default=list(SCALES))
    parser.add_argument('--repetitions',type=int,default=30)
    parser.add_argument('--seed',type=int,default=5003)
    parser.add_argument('--output-dir',type=Path)
    args = parser.parse_args()
    if args.repetitions < 5:
        parser.error('Use at least five measured repetitions')
    stamp = datetime.now(ZoneInfo('Asia/Hong_Kong'))
    output = args.output_dir or ROOT / 'evaluation/results' / stamp.strftime('%Y%m%d-%H%M%S')
    if output.exists():
        parser.error('Output directory already exists; choose a new path to preserve earlier results')
    output.mkdir(parents=True)
    result = {'measured_at_hk':stamp.isoformat(),'seed':args.seed,'repetitions':args.repetitions,
              'environment':{'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,
                             'platform':platform.platform(),'machine':platform.machine(),
                             'automatic_index':1,'cache_size_kib':8192,'mmap_size':0},'scales':[]}
    rng = random.Random(args.seed)
    with tempfile.TemporaryDirectory(prefix='localdeal-evaluation-') as directory:
        scratch = Path(directory)
        for scale in args.scales:
            print(f'Generating and validating {scale}: {SCALES[scale]}',flush=True)
            source = scratch / f'{scale}-source.db'
            counts = generate(source,SCALES[scale],args.seed)
            paths = {condition:scratch / f'{scale}-{condition}.db' for condition in ('baseline','indexed')}
            dropped = prepare_copy(source,paths['baseline'],True)
            prepare_copy(source,paths['indexed'],False)
            connections = {condition:connect(path) for condition,path in paths.items()}
            try:
                queries = [compare(connections,query,args.repetitions,rng) for query in workloads()]
                diagnostic = state_diagnostic(connections['indexed'])
            finally:
                for db in connections.values():
                    db.close()
            result['scales'].append({'scale':scale,'counts':counts,'dropped_business_indexes':dropped,
                                     'storage_bytes':{condition:path.stat().st_size for condition,path in paths.items()},
                                     'queries':queries,'guest_state':diagnostic})
            (output / 'results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
            print(f'{scale}: {len(queries)} query comparisons passed; guest payload {diagnostic["payload_bytes"]/1048576:.2f} MiB',flush=True)
    (output / 'summary.md').write_text(render_summary(result))
    print(f'Completed. Results: {output.resolve()}',flush=True)


if __name__ == '__main__':
    main()
