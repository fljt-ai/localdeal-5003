#!/usr/bin/env python3
"""Measure legitimate simulated purchase contention, using temporary SQLite DBs.

Each run creates 100 fictional buyers and a fresh ten-voucher offer. Independent
connections invoke the same business transaction as the application. No HTTP,
authentication, live records, external services or production targets are used.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database import init_db, operations


def percentile(samples, fraction):
    data = sorted(samples)
    return data[min(len(data)-1, max(0, int(len(data)*fraction+.999999)-1))]


def evaluate(path, buyers, stock, workers):
    def buy(i):
        start=time.perf_counter()
        with closing(operations.connect(path)) as db:
            try:
                result=operations.purchase_coupon(db, f'bench-user-{i}', 'c6', f'bench-{i}')
                outcome='purchased'
            except operations.DatabaseRuleError as exc:
                outcome=exc.code
                result=None
            except sqlite3.OperationalError as exc:
                if not any(word in str(exc).lower() for word in ('busy','locked')):
                    raise
                outcome='DATABASE_BUSY';result=None
        return outcome,result,(time.perf_counter()-start)*1000

    with closing(operations.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM orders WHERE coupon_id='c6'").fetchone()[0]==0
        with operations.transaction(db):
            db.execute("UPDATE coupons SET total_stock=?,available_stock=? WHERE coupon_id='c6'",(stock,stock))
            db.executemany('INSERT INTO users(user_id,email,display_name) VALUES (?,?,?)',
               [(f'bench-user-{i}',f'bench-{i}@example.com',f'Simulated buyer {i}') for i in range(buyers)])
    start=time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results=list(pool.map(buy,range(buyers)))
    elapsed=time.perf_counter()-start
    counts=Counter(r[0] for r in results)
    purchased=[r[1] for r in results if r[1]]
    with closing(operations.connect(path)) as db:
        remaining=db.execute("SELECT available_stock FROM coupons WHERE coupon_id='c6'").fetchone()[0]
        orders=db.execute("SELECT count(*) FROM orders WHERE coupon_id='c6'").fetchone()[0]
        assert orders==len(purchased)==counts['purchased']
        assert 0<=remaining<=stock and remaining+orders==stock
        assert len({p['order_id'] for p in purchased})==len(purchased)
        assert set(counts)<= {'purchased','SOLD_OUT','DATABASE_BUSY'}
        for order in purchased:
            again=operations.purchase_coupon(db,order['user_id'],'c6',order['idempotency_key'])
            assert again['order_id']==order['order_id']
        assert db.execute("SELECT available_stock FROM coupons WHERE coupon_id='c6'").fetchone()[0]==remaining
        assert db.execute("SELECT count(*) FROM orders WHERE coupon_id='c6'").fetchone()[0]==orders
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    durations=[r[2] for r in results]
    return {'workers':workers,'attempts':buyers,'initial_stock':stock,'successful':orders,
        'sold_out':counts['SOLD_OUT'],'busy':counts['DATABASE_BUSY'],'remaining_stock':remaining,
        'elapsed_ms':round(elapsed*1000,3),'attempts_per_second':round(buyers/elapsed,2),
        'median_ms':round(statistics.median(durations),3),'p95_ms':round(percentile(durations,.95),3),
        'replayed_orders':len(purchased),'oversell':max(0,orders-stock),'inventory_conserved':True,
        'unique_orders':True,'integrity_ok':True,'foreign_keys_ok':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repetitions',type=int,default=5)
    args=parser.parse_args()
    if not 1<=args.repetitions<=20:parser.error('repetitions must be 1–20')
    timestamp=datetime.now(operations.HK)
    output=ROOT/'evaluation/results'/('transactions-'+timestamp.strftime('%Y-%m-%d-%H%M%S'))
    results=[]
    with tempfile.TemporaryDirectory(prefix='localdeal-transaction-benchmark-') as directory:
        base=Path(directory)/'template.db'
        init_db.create_database(base,timestamp.date())
        for workers in (1,8,32):
            for repetition in range(1,args.repetitions+1):
                path=Path(directory)/f'{workers}-{repetition}.db'
                shutil.copyfile(base,path)
                row=evaluate(path,100,10,workers)
                row['repetition']=repetition
                results.append(row)
                print(f"workers={workers:2} run={repetition} sold={row['successful']} sold_out={row['sold_out']} busy={row['busy']} stock={row['remaining_stock']} p95={row['p95_ms']:.3f}ms",flush=True)
    output.mkdir(parents=True,exist_ok=False)
    metadata={'timestamp':timestamp.isoformat(),'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,
       'platform':platform.platform(),'measurement':'Business operation latency including opening and closing an independent database connection; worker-pool queue time excluded. Overall elapsed includes scheduling; attempts/s includes rejected requests.',
       'scenarios':results}
    (output/'results.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    lines=['# Transaction contention evaluation','',
      f"Run: {timestamp.isoformat()} | Python {metadata['python']} | SQLite {metadata['sqlite']}",'',
      'Each independent run uses a fresh synthetic database, 100 distinct test buyers, 10 available vouchers, and a bounded worker pool. The purchase function uses the application transaction; no live database or network is involved.','',
      '| Workers | Runs | Successful purchases per run | Sold-out per run | Busy per run | Median of medians (ms) | Median run p95 (ms) | Median attempts/s |',
      '| ---: | ---: | --- | --- | --- | ---: | ---: | ---: |']
    for workers in (1,8,32):
        group=[r for r in results if r['workers']==workers]
        def span(field):
            v=[r[field] for r in group];return str(min(v)) if min(v)==max(v) else f'{min(v)}–{max(v)}'
        def med(field):return f'{statistics.median(r[field] for r in group):.3f}'
        lines.append(f"| {workers} | {len(group)} | {span('successful')} | {span('sold_out')} | {span('busy')} | {med('median_ms')} | {med('p95_ms')} | {med('attempts_per_second')} |")
    lines+=['',f"All {len(results)} runs verified stock conservation, unique orders, no overselling, idempotent replay of successful purchases, database integrity and foreign keys.",
       '',metadata['measurement'],'',
       'SQLite has one writer at a time. Increased worker count can increase lock waiting rather than throughput. These are synthetic local transaction measurements, not web-server capacity or production throughput. The number of successful orders is bounded by stock; busy requests, if any, are reported separately instead of treated as sold-out.']
    (output/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(output.relative_to(ROOT))


if __name__=='__main__':
    main()
