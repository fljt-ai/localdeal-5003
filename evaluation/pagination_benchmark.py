#!/usr/bin/env python3
"""Compare former guest assembly with compact bootstrap + the first store page.

Uses isolated generated databases and the same service/JSON timing boundary.
No sockets, live accounts, browser or running application database are used.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import platform
import random
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

from benchmark import SCALES, connect, generate, identifier, prepare_copy, summary
from baseline_guest import guest_state

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import service


def encode(value):
    return json.dumps({'data':value},ensure_ascii=False,allow_nan=False).encode('utf-8')


def measure(function, repetitions):
    value = function()
    samples = []
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        value = function()
        samples.append((time.perf_counter_ns()-start)/1e6)
    return {**summary(samples),'payload_bytes':len(encode(value)),
            'returned_items':len(value.get('items',[])), 'total':value.get('total')}


def evaluate(db, repetitions, rng):
    def before():
        return [encode(guest_state(db))]

    def after():
        return [encode(service.state(db,None)), encode(service.stores_page(db,None,{}))]

    # Compare the displayed first-page store information with the former data.
    old = guest_state(db)
    page = service.stores_page(db,None,{})
    old_stores = {s['id']:s for s in old['stores']}
    for store in page['items']:
        assert store['reviewCount'] == old_stores[store['id']]['reviewCount']
        assert store['averageRating'] == old_stores[store['id']]['averageRating']
        assert store['name'] == old_stores[store['id']]['name']
    assert page['total'] == len(old['stores']) and len(page['items']) == 12
    assert not service.state(db,None)['reviews']
    samples = {'before':[], 'after':[]}
    sizes = {}
    functions = {'before':before,'after':after}
    for name, function in functions.items():
        for _ in range(3):
            function()
    for _ in range(repetitions):
        names = list(functions)
        rng.shuffle(names)
        for name in names:
            start = time.perf_counter_ns()
            parts = functions[name]()
            samples[name].append((time.perf_counter_ns()-start)/1e6)
            sizes[name] = sum(map(len,parts))
    homepage = {name:{**summary(values),'payload_bytes':sizes[name],
                       'response_count':1 if name=='before' else 2}
                for name,values in samples.items()}
    homepage['before']['reviews_returned'] = len(old['reviews'])
    homepage['after']['stores_returned'] = len(page['items'])
    homepage['after']['total_stores'] = page['total']
    session = {'user_id':identifier('u',0),'csrf_token':'evaluation-only'}
    cases = {
        'hot_store_reviews':lambda:service.reviews_page(db,session,{},store_id=identifier('s',0)),
        'frequent_buyer_wallet':lambda:service.orders_page(db,session,{}),
        'authorized_merchant_ledger':lambda:service.orders_page(db,session,{},merchant=True),
        'filtered_discovery':lambda:service.stores_page(db,None,{'district':['district-0'],'category':['cat-0']}),
    }
    # Page measurements include full service assembly and server-style encoding.
    pages = {}
    for name, function in cases.items():
        def timed(function=function):
            value = function()
            encode(value)
            return value
        pages[name] = measure(timed,repetitions)
        assert pages[name]['returned_items'] <= 12
    return {'homepage':homepage,'pages':pages,'first_page_store_counts_and_ratings_equal':True}


def report(result):
    lines = ['# LocalDeal Pagination Evaluation','',
             'Measured on '+result['measured_at_hk']+' (Hong Kong time).','',
             'The original guest read functions are preserved in `baseline_guest.py`. Both versions use the same indexed generated database and JSON envelope. The new homepage sum includes both bootstrap and its first 12-store page. This is service assembly plus JSON encoding, excluding HTTP, network and browser rendering.','',
             f"Python {result['environment']['python']}; SQLite {result['environment']['sqlite']}; {result['environment']['platform']}.", '',
             f"Fixed seed {result['seed']}; three warm-ups per homepage condition and {result['repetitions']} measured runs, randomly interleaved. Secondary page cases have one warm-up and the same number of measured runs. All generated files are temporary; the live database is never opened.", '',
             '| Scale | Stores / reviews / orders | Before KiB | After KiB (2 responses) | Before median ms | After median ms | After p95 ms |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for run in result['scales']:
        c,h = run['counts'],run['homepage']
        a,b = h['before'],h['after']
        lines.append(f"| {run['scale']} | {c['stores']:,} / {c['reviews']:,} / {c['orders']:,} | {a['payload_bytes']/1024:.2f} | {b['payload_bytes']/1024:.2f} | {a['median_ms']:.2f} | {b['median_ms']:.2f} | {b['p95_ms']:.2f} |")
    lines += ['', '## '+result['scales'][-1]['scale'].title()+'-scale first pages','',
              '| Page | Returned / total | Payload KiB | Median ms | p95 ms |',
              '| --- | --- | ---: | ---: | ---: |']
    for name,page in result['scales'][-1]['pages'].items():
        lines.append(f"| {name} | {page['returned_items']} / {page['total']:,} | {page['payload_bytes']/1024:.2f} | {page['median_ms']:.2f} | {page['p95_ms']:.2f} |")
    lines += ['', '## Correctness and limits','',
              '- Generated row counts, foreign keys, integrity and inventory were checked. The first-page store names, full review counts and full ratings agree with the former implementation.',
              '- Pagination changes how much content is returned. Equal full response hashes are neither expected nor claimed; complete records remain accessible on subsequent pages or explicit personal export.',
              '- A hot store has 10% of reviews and a frequent buyer has 10% of orders. The distribution is deliberately synthetic, not observed user behavior.',
              '- Results are warm repeated local reads of fixed cases. Counts and rating aggregates still read matching database rows; rating sort may examine all matching stores, and deep OFFSET pages may cost more.',
              '- The old response contained full menus, coupons and all public reviews. The new response contains a featured card and the first 12 store cards; full menu and review pages load when a detail view opens.',
              '- SQL timings in the older index experiment are a different boundary from this service-plus-encoding experiment. Do not combine their ratios.',
              '- The homepage comparison is for guests. A signed-in discovery page also requests favorites and personal counts; those costs are not included here. The merchant page case includes all authorized stores with no storeId filter, not the entire selected-branch workbench or its extra detail requests.',
              '- HTTP latency, browser rendering time, concurrency, production deployments and a maximum supported-user count are not measured here.','']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scales',nargs='+',choices=SCALES,default=list(SCALES))
    parser.add_argument('--repetitions',type=int,default=30)
    parser.add_argument('--seed',type=int,default=5003)
    parser.add_argument('--output-dir',type=Path)
    args = parser.parse_args()
    if args.repetitions<5:
        parser.error('Use at least five repetitions')
    stamp = datetime.now(ZoneInfo('Asia/Hong_Kong'))
    output = args.output_dir or ROOT/'evaluation/results'/stamp.strftime('pagination-%Y%m%d-%H%M%S')
    if output.exists():
        parser.error('Choose a new output directory to preserve earlier measurements')
    output.mkdir(parents=True)
    result = {'measured_at_hk':stamp.isoformat(),'seed':args.seed,'repetitions':args.repetitions,
              'environment':{'python':platform.python_version(),'sqlite':__import__('sqlite3').sqlite_version,
                             'platform':platform.platform()},
              'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in (ROOT/'backend/service.py',ROOT/'evaluation/baseline_guest.py')},
              'scales':[]}
    rng = random.Random(args.seed)
    with tempfile.TemporaryDirectory(prefix='localdeal-pagination-evaluation-') as directory:
        for scale in args.scales:
            print('Measuring '+scale,flush=True)
            source,indexed = Path(directory)/(scale+'-source.db'),Path(directory)/(scale+'-indexed.db')
            counts = generate(source,SCALES[scale],args.seed)
            prepare_copy(source,indexed,False)
            db = connect(indexed)
            try:
                run = evaluate(db,args.repetitions,rng)
            finally:
                db.close()
            result['scales'].append({'scale':scale,'counts':counts,**run})
            (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (output/'summary.md').write_text(report(result))
    print('Completed. Results: '+str(output.resolve()),flush=True)


if __name__=='__main__':
    main()
