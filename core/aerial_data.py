"""S1-S7 reales; corredores académicos derivados, nunca vuelos observados."""
import hashlib
import json
import math
from datetime import datetime,timedelta,timezone
from functools import lru_cache
from uuid import UUID,NAMESPACE_URL,uuid5

import rasterio
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import shape,Point,LineString,Polygon,MultiPolygon,mapping
from shapely.ops import transform,unary_union

from core.area import load_area
from core.contracts import ROOT,canonical,sha256,stable_id

FWD=Transformer.from_crs(4326,32719,always_xy=True).transform
INV=Transformer.from_crs(32719,4326,always_xy=True).transform
KEYS={'M1':'S1','M2':'S2','M3':'S3','M4':'S4','A1':'S4','A2':'S5','A3':'S6','A4':'S7'}


def iso(value):return datetime.fromisoformat(value.replace('Z','+00:00'))


def polygonal(g):
    if g.geom_type=='Polygon':return MultiPolygon([g])
    if g.geom_type=='MultiPolygon':return g
    polygons=[]
    for p in getattr(g,'geoms',[]):
        if p.geom_type=='Polygon':polygons.append(p)
        elif p.geom_type=='MultiPolygon':polygons.extend(p.geoms)
    return MultiPolygon(polygons)


def load_sources(config):
    folder=ROOT/config['aerial_raw_directory'];manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest['bbox_wgs84']!=config['bbox_wgs84'] or set(manifest['sources'])!={f'S{i}' for i in range(1,8)} or manifest.get('errors'):
        raise ValueError('Manifiesto aéreo incompleto o de otra área')
    def path(entry):
        p=(folder/entry['file']).resolve()
        if not p.is_relative_to(folder.resolve()) or sha256(p)!=entry['sha256']:raise ValueError('Original alterado '+entry['file'])
        return p
    data={}
    for key,entry in manifest['sources'].items():
        if 'pages' in entry:
            features=[]
            ids=json.loads(path(entry['ids']).read_text(encoding='utf-8'))['objectIds'] or []
            for page in entry['pages']:features.extend(json.loads(path(page).read_text(encoding='utf-8'))['features'])
            got=[f['properties'][entry['id_field']] for f in features]
            if len(got)!=len(set(got)) or set(got)!=set(ids):raise ValueError('Originales incompletos '+key)
            data[key]=features
        else:data[key]=path(entry)
    return manifest,data


def assemble(config):
    manifest,raw=load_sources(config);area=load_area(ROOT/config['aoi_geojson'])
    profile=json.loads((ROOT/config['aerial_profile']).read_text(encoding='utf-8'))
    records={key:[] for key in KEYS}
    repairs={}
    for key,source in [('M2','S2')]:
        repaired=0
        for f in raw[source]:
            geom=shape(f['geometry']);bad=not geom.is_valid
            if bad:geom=make_valid(geom);repaired+=1
            geom=polygonal(geom.intersection(area))
            if geom.is_empty:continue
            p=f['properties'];item=dict(provider_id=str(p[manifest['sources'][source]['id_field']]),geometry=mapping(geom),repaired=bad)
            if key=='M2':item.update(category=p['uso'],source_year=2019)
            else:
                ordinal=int(p['gridcode'])
                if not 1<=ordinal<=5:raise ValueError('Clase histórica desconocida')
                item.update(ordinal_class=ordinal,class_label=p['recurrencia'],period_start=2020,period_end=2024)
            records[key].append(item)
        repairs[key]=repaired
    from Amenazas.a4_historial import transformar as transformar_a4
    records['A4'],repairs['A4']=transformar_a4(raw['S7'],area,manifest['sources']['S7']['id_field'],polygonal)
    for f in raw['S1']:
        if area.covers(shape(f['geometry'])):
            p=f['properties'];records['M1'].append(dict(provider_id=str(p['objectid_1']),name=p['nombre'],commune=p.get('comuna'),address=p.get('direccion'),geometry=f['geometry']))
    if not records['M1']:raise ValueError('No hay bases candidatas reales dentro del AOI')
    grid=profile['grid_m'];bounds=transform(FWD,area).bounds;nodes=[]
    forest=unary_union([shape(r['geometry']) for r in records['M2'] if r['category'] in ['Bosques','Praderas y Matorrales']])
    for x in range(math.ceil(bounds[0]/grid)*grid,math.floor(bounds[2]/grid)*grid+1,grid):
        for y in range(math.ceil(bounds[1]/grid)*grid,math.floor(bounds[3]/grid)*grid+1,grid):
            coord=list(INV(x,y));p=Point(coord)
            if area.covers(p):
                key=f'aerial:grid:{grid}:{x}:{y}'
                nodes.append(dict(id=stable_id(key),natural_key=key,kind='vigilancia' if forest.covers(p) else 'navegacion',source_record_id=None,geometry=dict(type='Point',coordinates=coord)))
    for base in records['M1']:
        key='aerial:base:S1:'+base['provider_id'];base['node_id']=stable_id(key)
        nodes.append(dict(id=base['node_id'],natural_key=key,kind='base_candidata',source_record_id=base['provider_id'],geometry=base['geometry']))
    metric={n['id']:transform(FWD,shape(n['geometry'])) for n in nodes};by_id={n['id']:n for n in nodes};pairs=set()
    for n in nodes:
        near=sorted((metric[n['id']].distance(metric[m['id']]),m['id']) for m in nodes if m['id']!=n['id'])
        for distance,target in near[:profile['neighbours']]:
            if distance<=profile['max_link_m']:
                segment=LineString([n['geometry']['coordinates'],by_id[target]['geometry']['coordinates']])
                if area.covers(segment):pairs.update([(n['id'],target),(target,n['id'])])
    edges=[]
    for s,t in sorted(pairs):
        key=f'arc:{by_id[s]["natural_key"]}->{by_id[t]["natural_key"]}'
        edges.append(dict(id=stable_id(key),natural_key=key,source=s,target=t,
            physical_key='corridor:'+'|'.join(sorted([by_id[s]['natural_key'],by_id[t]['natural_key']])),
            geometry=dict(type='LineString',coordinates=[by_id[s]['geometry']['coordinates'],by_id[t]['geometry']['coordinates']])))
    with rasterio.open(raw['S3']) as src:
        if src.crs is None or src.crs.to_epsg()!=4326:raise ValueError('CRS DSM no verificado')
        for node,sample in zip(nodes,src.sample([n['geometry']['coordinates'] for n in nodes],masked=True)):
            value=None if __import__('numpy').ma.getmaskarray(sample)[0] else float(sample[0])
            if value is not None:value=value*src.scales[0]+src.offsets[0]
            if value is not None and not math.isfinite(value):value=None
            records['M3'].append(dict(node_id=node['id'],elevation_m=value,quality='valid' if value is not None else 'nodata'))
        raster_info=dict(crs=src.crs.to_string(),transform=list(src.transform),shape=[src.height,src.width],nodata=src.nodata,
            bands=src.count,scales=list(src.scales),offsets=list(src.offsets),band_units=list(src.units),
            horizontal_units='degrees',vertical_units='m',vertical_datum='EGM2008 (Copernicus GLO-30 product)',support='approximately 30 m; not obstacle clearance')
    weather=json.loads(raw['S4'].read_text(encoding='utf-8'));hourly=weather['hourly'];units=weather['hourly_units']
    if weather['utc_offset_seconds']!=0 or units['wind_speed_10m']!='m/s' or units['wind_gusts_10m']!='m/s':raise ValueError('Unidades/tiempo meteorológico inesperado')
    fields={'temperature_c':'temperature_2m','relative_humidity_pct':'relative_humidity_2m','wind_speed_ms':'wind_speed_10m',
            'wind_direction_deg':'wind_direction_10m','wind_gust_ms':'wind_gusts_10m','precipitation_mm':'precipitation'}
    for i,date in enumerate(hourly['time']):
        row={k:hourly[v][i] for k,v in fields.items()};row.update(valid_at=date+':00+00:00',cell=[weather['longitude'],weather['latitude']])
        if row['wind_direction_deg'] is not None:row['wind_direction_deg']%=360
        records['M4'].append(row)
    acquisition=iso(manifest['fetched_at_utc']);clock=acquisition.replace(minute=0,second=0,microsecond=0)
    if not any(iso(r['valid_at'])==clock for r in records['M4']):clock=iso(records['M4'][0]['valid_at'])
    from Amenazas.a1_meteorologia import transformar as transformar_a1
    records['A1']=transformar_a1(records['M4'],area,profile)
    # Conservar todos los focos del AOI en el original de siete días; aplicar ventana por consulta.
    from Amenazas.a2_firms import transformar as transformar_a2
    records['A2']=transformar_a2(raw['S5'].read_text(encoding='utf-8-sig'),area,profile['thermal_buffer_m'])
    from Amenazas.a3_aip import transformar as transformar_a3
    records['A3'],aip_parser_report=transformar_a3(raw['S6'],area,profile['aip_margin_m'])
    for rows in records.values():rows.sort(key=lambda r:str(r.get('provider_id',r.get('node_id',r.get('valid_at','')))))
    context=dict(records=records,reference_time=clock.isoformat(),weather_fetched_at=manifest['sources']['S4']['fetched_at_utc'],profile=profile,repairs=repairs,raster=raster_info,
                 aip_parser_report=aip_parser_report,
                 catalog_scope='S6 ENR 5.1: todas las SC-P/SC-R/SC-D inventariadas; geometrías soportadas seleccionadas con margen AOI configurable; ver aip_parser_report para excepciones. No es autorización de vuelo.',
                 clearance_verified=False)
    lineage=dict(builder=profile['builder'],configuration_sha256=hashlib.sha256(canonical(config)).hexdigest(),
        aoi=dict(file=config['aoi_geojson'],sha256=sha256(ROOT/config['aoi_geojson']),geometry=json.loads(json.dumps(mapping(area))),predicate='covers'),
        sources=manifest['sources'],manifest_sha256=sha256(ROOT/config['aerial_raw_directory']/'manifest.json'),
        profile=profile,context_sha256=hashlib.sha256(canonical(context)).hexdigest(),derived_corridors=True)
    return sorted(nodes,key=lambda n:n['id']),sorted(edges,key=lambda e:e['id']),lineage,context,manifest


@lru_cache(maxsize=2)
def cached_assembly(config_text,manifest_hash,profile_hash):
    return assemble(json.loads(config_text))


def build(config,run_id=None,mode='snapshot'):
    nodes,edges,lineage,context,manifest=cached_assembly(canonical(config).decode(),sha256(ROOT/config['aerial_raw_directory']/'manifest.json'),sha256(ROOT/config['aerial_profile']))
    semantic=dict(nodes=nodes,edges=edges,crs='EPSG:4326',analysis_srid=32719,lineage=lineage,
        observed_at=manifest['fetched_at_utc'],extracted_at=manifest['fetched_at_utc'],builder='aerial-grid-v1')
    digest=hashlib.sha256(canonical(semantic)).hexdigest();rid=str(UUID(run_id)) if run_id else str(uuid5(NAMESPACE_URL,'udp:aerial:v1:'+mode+':'+digest))
    doc=dict(schema_version='3.0',run_id=rid,dataset_id=str(uuid5(UUID(rid),'I')),dataset_key='I',source_id='DERIVED_AERIAL',
        input_hash=digest,extraction_mode=mode,**{k:v for k,v in semantic.items() if k!='builder'})
    return doc,context


def validate(doc,config):
    load_sources(config)
    expected,_=build(config,doc['run_id'],doc['extraction_mode'])
    if canonical(expected)!=canonical(doc):raise ValueError('Infraestructura aérea alterada o procedencia incompatible')
