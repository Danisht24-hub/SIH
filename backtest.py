from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

from config import load_settings
from db.analytics import store_dgca_benchmark
from db.connection import connect


def load_csv(path: str, source: str):
    rows=[]
    with open(path, newline='', encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            rows.append({
                'reference_month': date.fromisoformat(r['reference_month'] + '-01') if len(r['reference_month']) == 7 else date.fromisoformat(r['reference_month']),
                'origin': r.get('origin') or None,
                'destination': r.get('destination') or None,
                'average_fare': float(r['average_fare']),
                'source': source,
            })
    return rows


def run(path: str):
    settings=load_settings()
    rows=load_csv(path, 'DGCA/MoSPI supplied CSV')
    store_dgca_benchmark(settings, rows)
    # Monthly benchmark comparison: compare monthly median collected total fares.
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT date_trunc('month',travel_date)::date AS month,
                              origin,destination, percentile_cont(0.5) WITHIN GROUP (ORDER BY fare_amount) AS collected_median
                       FROM flight_observations WHERE cleaning_status='valid' AND fare_amount>0
                       GROUP BY 1,2,3 ORDER BY 1,2,3""")
            collected=cur.fetchall()
            cur.execute("SELECT reference_month,origin,destination,average_fare,source FROM dgca_benchmarks ORDER BY reference_month,origin,destination")
            benchmark=cur.fetchall()
    b={(r['reference_month'],r['origin'],r['destination']): r for r in benchmark}
    out=[]
    for r in collected:
        key=(r['month'],r['origin'],r['destination'])
        if key in b:
            actual=float(r['collected_median']); target=float(b[key]['average_fare'])
            out.append({'month':r['month'],'origin':r['origin'],'destination':r['destination'],
                        'collected_median':actual,'dgca_average_fare':target,
                        'absolute_error':abs(actual-target),
                        'ape_percent':abs(actual-target)/target*100 if target else None})
    print(f"Loaded {len(rows)} benchmark rows; matched {len(out)} route-month comparisons")
    for r in out:
        print(r)

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Back-test collected fares against supplied DGCA/MoSPI benchmark data')
    p.add_argument('--file',required=True,help='CSV with reference_month,origin,destination,average_fare')
    args=p.parse_args(); run(args.file)
