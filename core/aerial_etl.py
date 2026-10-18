"""Contratos y cargas tipadas de los ocho datasets del simulador."""
import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID,uuid5

from psycopg.types.json import Jsonb
from core.contracts import ROOT,canonical,sha256,write_json
from core.aerial_data import KEYS,iso
from core.db import connect


def extract(key,rid,output):
    folder=ROOT/'datos/runs'/str(rid);doc=json.loads((folder/'infraestructura.json').read_text())
    context=json.loads((folder/'context.json').read_text())
    if hashlib.sha256(canonical(context)).hexdigest()!=doc['lineage']['context_sha256']:raise ValueError('Contexto ET alterado')
    packet=dict(schema_version='aerial-dataset-1',run_id=str(rid),dataset_id=str(uuid5(UUID(str(rid)),key)),dataset_key=key,source_id=KEYS[key],
        observed_at=doc['observed_at'],extracted_at=doc['extracted_at'],records=context['records'][key],
        lineage=dict(source=doc['lineage']['sources'][KEYS[key]],aoi=doc['lineage']['aoi'],context_sha256=doc['lineage']['context_sha256']))
    if key=='A3':
        packet['parser_report']=context['aip_parser_report']
    write_json(output,packet)


def load(conn,path):
    doc=json.loads(path.read_text());rid=UUID(doc['run_id']);key=doc['dataset_key'];rows=doc['records']
    if key not in KEYS or doc['source_id']!=KEYS[key] or doc['dataset_id']!=str(uuid5(rid,key)):raise ValueError('Identidad de dataset incorrecta')
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(74260104)')
        model=conn.execute('SELECT context#>%s::text[] AS records FROM routing.aerial_models WHERE run_id=%s',(['records',key],rid)).fetchone()
        lineage=conn.execute("SELECT lineage FROM routing.datasets WHERE run_id=%s AND dataset_key='I'",(rid,)).fetchone()
        if not model or rows!=model['records'] or doc['lineage']['source']!=lineage['lineage']['sources'][KEYS[key]]:
            raise ValueError('Registros ET no corresponden a fuentes validadas')
        old=conn.execute('SELECT file_sha256 FROM routing.datasets WHERE run_id=%s AND dataset_key=%s',(rid,key)).fetchone()
        if old:
            if old['file_sha256']!=sha256(path):raise ValueError('Dataset ya cargado con bytes distintos')
            return dict(idempotent=True,count=len(rows))
        conn.execute('''INSERT INTO routing.datasets(dataset_id,run_id,dataset_key,source_id,schema_version,observed_at,extracted_at,file_sha256,record_count,status,lineage)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(UUID(doc['dataset_id']),rid,key,doc['source_id'],doc['schema_version'],doc['observed_at'],doc['extracted_at'],sha256(path),len(rows),'valid' if rows else 'empty',Jsonb(doc['lineage'])))
        geom='ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32719)'
        from core.contracts import stable_id
        for r in rows:
            ident=stable_id(key+':'+str(r.get('provider_id',r.get('valid_at',r.get('node_id')))))
            if key=='M1':
                conn.execute('INSERT INTO routing.base_metadata(run_id,node_id,provider_id,name,commune,address) VALUES(%s,%s,%s,%s,%s,%s)',(rid,r['node_id'],r['provider_id'],r['name'],r['commune'],r['address']))
            elif key=='M2':
                conn.execute('INSERT INTO routing.landcover(run_id,id,provider_id,category,source_year,repaired,geom) VALUES(%s,%s,%s,%s,%s,%s,'+geom+')',(rid,ident,r['provider_id'],r['category'],r['source_year'],r['repaired'],Jsonb(r['geometry'])))
            elif key=='M3':
                conn.execute('INSERT INTO routing.node_elevation(run_id,node_id,elevation_m,quality) VALUES(%s,%s,%s,%s)',(rid,r['node_id'],r['elevation_m'],r['quality']))
            elif key=='M4':
                conn.execute('''INSERT INTO routing.weather(run_id,id,cell,valid_at,issued_at,temperature_c,relative_humidity_pct,wind_speed_ms,wind_gust_ms,wind_direction_deg,precipitation_mm)
                    VALUES(%s,%s,'''+geom+',%s,%s,%s,%s,%s,%s,%s,%s)',(rid,ident,Jsonb(dict(type='Point',coordinates=r['cell'])),r['valid_at'],None,*[r[k] for k in ['temperature_c','relative_humidity_pct','wind_speed_ms','wind_gust_ms','wind_direction_deg','precipitation_mm']]))
            else:
                kind={'A1':'weather','A2':'thermal','A3':'airspace','A4':'historical'}[key]
                start=r.get('valid_at',r.get('acquired_at'));until=None
                if key=='A1':until=iso(start)+__import__('datetime').timedelta(hours=1)
                conn.execute('''INSERT INTO routing.hazards(run_id,id,dataset_key,kind,provider_id,geom,state,valid_from,valid_until,model_version)
                    VALUES(%s,%s,%s,%s,%s,'''+geom+',%s,%s,%s,%s)',(rid,ident,key,kind,str(r.get('provider_id')),Jsonb(r['geometry']),r.get('state','historical' if key=='A4' else 'active'),start,until,'aerial-simulation-v1'))
                if key=='A1':conn.execute('INSERT INTO routing.weather_hazards(run_id,hazard_id,weather_id,reason) VALUES(%s,%s,%s,%s)',(rid,ident,stable_id('M4:'+r['valid_at']),r['reason']))
                elif key=='A2':conn.execute('INSERT INTO routing.thermal_events(run_id,hazard_id,acquired_at,confidence,fire_radiative_power_mw,buffer_m) VALUES(%s,%s,%s,%s,%s,%s)',(rid,ident,r['acquired_at'],r['confidence'],r['fire_radiative_power_mw'],r['buffer_m']))
                elif key=='A3':conn.execute('INSERT INTO routing.airspace_zones(run_id,hazard_id,code,lower_limit,upper_limit,conditions,document_page,original_record) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(rid,ident,*[r[k] for k in ['code','lower_limit','upper_limit','conditions','document_page','original_record']]))
                elif key=='A4':conn.execute('INSERT INTO routing.historical_risk(run_id,hazard_id,ordinal_class,class_label,period_start,period_end) VALUES(%s,%s,%s,%s,%s,%s)',(rid,ident,r['ordinal_class'],r['class_label'],r['period_start'],r['period_end']))
    return dict(idempotent=False,count=len(rows))


def main(key):
    parser=argparse.ArgumentParser(description='ET/cargador '+key+'; fuente '+KEYS[key])
    parser.add_argument('--run-id');parser.add_argument('--output',type=Path);parser.add_argument('--load',type=Path);parser.add_argument('--mode',choices=['snapshot','online'],default='snapshot')
    args=parser.parse_args()
    if args.load:
        with connect() as conn:print(json.dumps(load(conn,args.load)))
    else:
        if not args.run_id or not args.output:parser.error('Se requieren --run-id y --output')
        extract(key,args.run_id,args.output)
