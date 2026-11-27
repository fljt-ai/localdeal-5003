#!/usr/bin/env python3
"""Render measured JSON into PNG and SVG figures; requires matplotlib."""
import argparse
import json
import os
from pathlib import Path
import tempfile

cache = tempfile.TemporaryDirectory(prefix='localdeal-matplotlib-')
os.environ.setdefault('MPLCONFIGDIR',cache.name)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import statistics


def transaction_figures(data, output):
    groups={n:[r for r in data['scenarios'] if r['workers']==n] for n in (1,8,32)}
    labels=[str(n) for n in groups]
    fig,axes=plt.subplots(1,2,figsize=(10.5,4.8),layout='constrained')
    ax=axes[0]
    for field,color,label in [('successful','#1d5545','Purchased'),('sold_out','#c0c9be','Sold out'),('busy','#c88838','Database busy')]:
        values=[statistics.mean(r[field] for r in rows) for rows in groups.values()]
        if field=='successful':bottom=[0]*3
        elif field=='sold_out':bottom=[statistics.mean(r['successful'] for r in rows) for rows in groups.values()]
        else:bottom=[statistics.mean(r['successful']+r['sold_out'] for r in rows) for rows in groups.values()]
        ax.bar(labels,values,bottom=bottom,label=label,color=color,width=.54)
    ax.set_ylim(0,110);ax.set_ylabel('Outcomes per 100 attempts (mean)');ax.set_xlabel('Concurrent workers');ax.legend(loc='upper center',fontsize=8)
    ax=axes[1]
    values=[statistics.median(r['p95_ms'] for r in rows) for rows in groups.values()]
    bars=ax.bar(labels,values,color='#1d5545',width=.54)
    ax.set_yscale('log');ax.set_ylabel('Median run p95 latency (ms, log scale)');ax.set_xlabel('Concurrent workers')
    for bar,value in zip(bars,values):ax.annotate(f'{value:.2f}',(bar.get_x()+bar.get_width()/2,value),xytext=(0,5),textcoords='offset points',ha='center',fontsize=9)
    ax.set_ylim(min(values)/2,max(values)*2)
    for ax in axes:ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.suptitle('LocalDeal: transaction correctness under simulated contention',fontsize=13)
    fig.supxlabel(f"{len(data['scenarios'])} independent runs; 10 initial vouchers; local SQLite operation, not HTTP or production capacity.",fontsize=8)
    for ext in ('png','svg'):fig.savefig(output/f'transaction-contention.{ext}',dpi=190,bbox_inches='tight')
    plt.close(fig)


def pagination_figures(data, output):
    runs = data['scales']
    labels = [r['scale'].title() for r in runs]
    fig, axes = plt.subplots(1,2,figsize=(11,5.7))
    fig.subplots_adjust(left=0.09,right=0.98,bottom=0.24,top=0.76,wspace=0.34)
    positions = list(range(len(runs)))
    for ax,metric,denominator,ylabel in zip(axes,['payload_bytes','median_ms'],[1024,1],
                                          ['JSON bytes returned (KiB, log scale)','Assembly + JSON median (ms, log scale)']):
        for condition,shift,label,color in [('before',-0.19,'Before: full guest state','#8e9c96'),
                                            ('after',0.19,'After: bootstrap + first 12 stores','#1d5545')]:
            values = [r['homepage'][condition][metric]/denominator for r in runs]
            bars = ax.bar([p+shift for p in positions],values,0.38,label=label,color=color)
            for bar,value in zip(bars,values):
                ax.annotate(f'{value:,.2f}',(bar.get_x()+bar.get_width()/2,value),xytext=(0,5),
                            textcoords='offset points',ha='center',fontsize=8)
        ax.set_yscale('log')
        ax.set_xticks(positions,labels)
        ax.set_ylabel(ylabel)
        ax.set_xlabel('Synthetic dataset scale')
        ax.grid(axis='y',alpha=0.18)
        ax.set_axisbelow(True)
        ax.set_ylim(top=max(r['homepage']['before'][metric]/denominator for r in runs)*5)
    fig.suptitle('LocalDeal — bounded homepage responses after pagination',fontsize=14,y=0.97)
    fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(0.54,0.91),fontsize=9)
    fig.text(0.5,0.07,f"Same generated indexed databases; {data['repetitions']} interleaved runs per condition after warm-up.",ha='center',fontsize=8)
    last = runs[-1]
    counts = last['counts']
    fig.text(0.5,0.035,f"{last['scale'].title()}: {counts['stores']:,} stores / {counts['reviews']:,} reviews / {counts['orders']:,} orders. HTTP, network and browser excluded.",ha='center',fontsize=8)
    for extension in ('png','svg'):
        fig.savefig(output/f'pagination-comparison.{extension}',dpi=190,bbox_inches='tight')
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results',type=Path)
    args = parser.parse_args()
    data = json.loads(args.results.read_text())
    output = args.results.parent
    if 'scenarios' in data:
        transaction_figures(data,output)
        print(f'Figures saved to {output.resolve()}')
        return
    runs = data['scales']
    if 'homepage' in runs[0]:
        pagination_figures(data,output)
        print(f'Figures saved to {output.resolve()}')
        return
    last = runs[-1]
    labels = ['Reviews\n(hot store)','Reviews\n(regular)','Wallet\n(frequent buyer)',
              'Wallet\n(regular)','Merchant\nledger','Discovery','Voucher\nlookup']
    baseline = [q['conditions']['baseline']['median_ms'] for q in last['queries']]
    indexed = [q['conditions']['indexed']['median_ms'] for q in last['queries']]
    fig, ax = plt.subplots(figsize=(11,6.5))
    fig.subplots_adjust(left=0.10,right=0.98,bottom=0.23,top=0.76)
    positions = list(range(len(labels)))
    ax.bar([p-0.19 for p in positions],baseline,0.38,label='13 business secondary indexes removed',color='#8e9c96')
    ax.bar([p+0.19 for p in positions],indexed,0.38,label='Application business indexes present',color='#1d5545')
    ax.set_yscale('log')
    ax.set_xticks(positions,labels)
    ax.set_ylabel('Median execute + fetchall latency (ms, log scale)')
    fig.suptitle(f'LocalDeal SQLite queries — {last["counts"]["reviews"]:,} reviews / {last["counts"]["orders"]:,} orders',y=0.98,fontsize=14)
    ax.grid(axis='y',alpha=0.18)
    ax.set_axisbelow(True)
    fig.legend(*ax.get_legend_handles_labels(),fontsize=9,loc='upper center',bbox_to_anchor=(0.54,0.92))
    fig.text(0.5,0.045,'Synthetic local reads after warm-up. PK/UNIQUE indexes retained in both conditions; not HTTP latency.',ha='center',fontsize=8,color='#555555')
    for extension in ('png','svg'):
        fig.savefig(output / f'query-latency.{extension}',dpi=190,bbox_inches='tight')
    plt.close(fig)

    sizes = [r['counts']['reviews'] for r in runs]
    times = [r['guest_state']['median_ms'] for r in runs]
    payloads = [r['guest_state']['payload_bytes']/1048576 for r in runs]
    fig, axes = plt.subplots(1,2,figsize=(10,4.8))
    fig.subplots_adjust(left=0.09,right=0.98,bottom=0.23,top=0.83,wspace=0.35)
    for ax, values, color, ylabel in zip(axes,[times,payloads],['#1d5545','#56858f'],
                                        ['State assembly + JSON encoding (median ms)','JSON response size (MiB)']):
        ax.plot(sizes,values,marker='o',linewidth=2,color=color)
        ax.set_xticks(sizes,[f'{s:,}' for s in sizes])
        ax.set_xlabel('Reviews in synthetic database')
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.2)
        for x,y in zip(sizes,values):
            ax.annotate(f'{y:.1f}',(x,y),xytext=(0,8),textcoords='offset points',ha='center',fontsize=9)
        ax.set_ylim(0,max(values)*1.25)
        ax.margins(x=0.08)
    fig.suptitle('Pre-pagination guest state loads every review',fontsize=14,y=0.98)
    fig.text(0.5,0.03,'Indexed database; one warm-up and three measured runs. Network and browser excluded.',ha='center',fontsize=8,color='#555555')
    for extension in ('png','svg'):
        fig.savefig(output / f'guest-state-growth.{extension}',dpi=190,bbox_inches='tight')
    plt.close(fig)
    print(f'Figures saved to {output.resolve()}')


if __name__ == '__main__':
    main()
