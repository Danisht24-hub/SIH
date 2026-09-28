from __future__ import annotations

import argparse
import csv
from config import load_settings
from db.analytics import upsert_route_basket
from db.connection import init_schema

p=argparse.ArgumentParser(description='Load DGCA passenger-traffic-derived route weights')
p.add_argument('--file',required=True,help='CSV: origin,destination,weight,source')
a=p.parse_args()
settings=load_settings(); init_schema(settings)
routes=[]
with open(a.file,newline='',encoding='utf-8-sig') as fh:
    for r in csv.DictReader(fh):
        routes.append({'origin':r['origin'].upper(),'destination':r['destination'].upper(),'weight':float(r['weight']),'source':r.get('source') or 'DGCA passenger traffic'})
upsert_route_basket(settings,routes)
print(f'Loaded {len(routes)} route weights')
