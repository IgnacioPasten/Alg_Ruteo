import copy
import heapq
import json
import os
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4

from psycopg import errors
from shapely.geometry import Point,LineString,Polygon,mapping
from shapely.ops import transform

from core.aerial_data import FWD,INV,iso,build
from core.aerial_routing import coordinate,events_geometry,exposure,available,calculate,data,map_data,overlay
from core.contracts import ROOT,validate_infrastructure,write_json
from core.db import connect
from core.aerial_pipeline import run
from core.aerial_etl import load


class AerialRules(unittest.TestCase):
    def test_coordinate_accepts_boundary_but_not_outside_or_nonfinite(self):
        a=Polygon([(0,0),(2,0),(2,2),(0,2)])
        self.assertEqual(coordinate([0,1],a),[0,1])
        for c in [[3,1],[float('nan'),1],['0',1],[True,1]]:
            with self.assertRaises(ValueError):coordinate(c,a)

    def test_overlapping_history_uses_maximum_without_double_count(self):
        line=LineString([(0,0),(10,0)])
        high=Polygon([(0,-1),(5,-1),(5,1),(0,1)])
        all_area=Polygon([(0,-2),(10,-2),(10,2),(0,2)])
        value,unknown=exposure(line,[(high,1),(all_area,.5)])
        self.assertAlmostEqual(value,7.5);self.assertEqual(unknown,0)
        self.assertEqual(exposure(line,[]),(10,10))

    def test_resolution_does_not_clear_a_different_overlapping_event(self):
        a=dict(id='a',geometry=dict(type='Point',coordinates=[-71.65,-33.10]),radius_m=80,state='blocked',observed_at='2026-10-17T01:00:00Z')
        b=dict(a,id='b');resolved=dict(a,state='resolved',observed_at='2026-10-17T02:00:00Z')
        shapes,ledger=events_geometry([a,b,resolved,a])
        self.assertEqual(len(shapes),1);self.assertEqual(len(ledger),2)

    def test_weather_missing_and_threshold_are_not_safe(self):
        profile=json.loads((ROOT/'config/aereo.json').read_text())
        w=dict(valid_at='2026-10-17T00:00:00Z',wind_speed_ms=1,wind_gust_ms=8,temperature_c=20,wind_direction_deg=0)
        m=dict(profile=profile,records={'M4':[w]})
        self.assertEqual(available(m,iso(w['valid_at']))[1],'weather_outside_profile')
        w['wind_gust_ms']=None
        self.assertEqual(available(m,iso(w['valid_at']))[1],'unknown_weather')
        self.assertEqual(available(m,iso('2026-10-19T00:00:00Z'))[1],'missing_weather_time')

    def test_future_resolution_does_not_anticipate_the_scenario_clock(self):
        event=dict(id='a',geometry=dict(type='Point',coordinates=[-71.65,-33.10]),state='blocked',observed_at='2026-10-17T01:00:00Z')
        future=dict(event,state='resolved',observed_at='2026-10-17T03:00:00Z')
        shapes,_=events_geometry([event,future],iso('2026-10-17T02:00:00Z'))
        self.assertEqual(len(shapes),1)
        self.assertFalse(events_geometry([event,future],iso('2026-10-17T04:00:00Z'))[0])


class AerialIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (os.getenv('DATABASE_URL') or os.getenv('DB_HOST')):
            if os.getenv('REQUIRE_DB_TESTS')=='1':raise RuntimeError('Se requiere PostgreSQL Docker real')
            raise unittest.SkipTest('Ejecutar main probar')
        cls.report=run('completo','snapshot');cls.rid=cls.report['run_id'];cls.conn=connect()
        cls.model,cls.area,cls.nodes,cls.edges=data(cls.conn,cls.rid);cls.view=map_data(cls.conn,cls.rid)
        cls.clock=next(w['valid_at'] for w in cls.view['weather'] if available(cls.model,iso(w['valid_at']))[1] is None)
        cls.request=dict(origin=cls.view['default_origin'],destination=cls.view['examples'][1]['coordinates'],time=cls.clock,mode='mission')
        cls.result=calculate(cls.conn,cls.rid,cls.request)

    @classmethod
    def tearDownClass(cls):cls.conn.close()

    def test_nine_real_datasets_loaded_with_reconciled_counts(self):
        self.assertEqual(len(self.report['counts']),9)
        self.assertEqual(self.report['counts']['M3'],self.report['topology']['nodes'])
        self.assertEqual(self.report['topology']['spatial']['outside_edges'],0)
        self.assertEqual(self.report['topology']['spatial']['outside_nodes'],0)
        self.assertGreater(self.report['counts']['M2'],100)
        self.assertEqual(self.report['counts']['A3'],2)

    def test_laguna_verde_real_base_uses_its_exact_source_point(self):
        self.assertAlmostEqual(self.request['origin'][0],-71.6572392109999,places=12)
        self.assertTrue(self.area.covers(Point(self.request['origin'])))
        self.assertEqual(self.result['status'],'ready')
        self.assertGreater(self.result['alternatives'][0]['length_km'],1)
        self.assertFalse(self.result['clearance_verified'])

    def test_endpoints_away_from_roads_are_kept_exactly_without_publishing_nodes(self):
        req=dict(self.request,origin=[-71.65,-33.09],destination=[-71.64,-33.085],mode='trip',method='reference')
        before=self.conn.execute('SELECT count(*) AS n FROM routing.nodes WHERE run_id=%s',(self.rid,)).fetchone()['n']
        result=calculate(self.conn,self.rid,req)
        self.assertEqual(result['status'],'ready')
        coords=result['features'][0]['geometry']['coordinates']
        self.assertEqual(coords[0],req['origin']);self.assertEqual(coords[-1],req['destination'])
        after=self.conn.execute('SELECT count(*) AS n FROM routing.nodes WHERE run_id=%s',(self.rid,)).fetchone()['n']
        self.assertEqual(before,after)

    def test_dijkstra_reference_agrees_with_independent_heap_and_postgis(self):
        for goal in self.view['examples'][:3]:
            req=dict(self.request,destination=goal['coordinates'],mode='trip',method='reference')
            result=calculate(self.conn,self.rid,req)
            nodes,edges,ids=overlay(self.conn,self.nodes,self.edges,dict(home=req['origin'],target=req['destination'],current=req['origin']),self.area,self.model['profile'])
            adjacency={}
            for e in edges:adjacency.setdefault(e['source'],[]).append((e['target'],e['length_km']))
            source=ids['home'];target=ids['target'];dist={source:0};queue=[(0,source)]
            while queue:
                cost,n=heapq.heappop(queue)
                if cost!=dist[n]:continue
                for nxt,w in adjacency.get(n,[]):
                    candidate=cost+w
                    if candidate<dist.get(nxt,float('inf')):dist[nxt]=candidate;heapq.heappush(queue,(candidate,nxt))
            self.assertAlmostEqual(result['alternatives'][0]['length_km'],dist[target],places=9)
            geom=result['features'][0]['geometry']
            actual=self.conn.execute('SELECT ST_Length(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32719))/1000 AS km',(json.dumps(geom),)).fetchone()['km']
            self.assertAlmostEqual(actual,dist[target],places=8)
            alternatives=result['alternatives']
            if len(alternatives)>1:self.assertNotEqual(alternatives[0]['outbound']['edge_ids'],alternatives[1]['outbound']['edge_ids'])

    def test_mission_alternatives_are_distinct_and_preserve_return_budget(self):
        options=self.result['alternatives'];self.assertGreaterEqual(len(options),2)
        signatures=set()
        for p in options:
            signatures.add((tuple(p['outbound']['edge_ids']),tuple(p['return_path']['edge_ids'])))
            self.assertLessEqual(p['time_s'],1200)
            self.assertEqual(p['observation_s'],60)
            self.assertAlmostEqual(p['time_s'],p['outbound']['time_s']+p['return_path']['time_s']+60)
            for route in [p['outbound'],p['return_path']]:
                self.assertTrue(self.area.covers(LineString(route['coordinates'])))
        self.assertEqual(len(signatures),len(options))

    def test_blockage_removes_whole_segments_and_reference_stays_unchanged(self):
        p=LineString(self.result['alternatives'][0]['outbound']['coordinates']).interpolate(.5,normalized=True)
        event=dict(id='test',state='blocked',observed_at=self.clock,geometry=mapping(p),radius_m=80)
        result=calculate(self.conn,self.rid,dict(self.request,events=[event]))
        self.assertEqual(result['reference'],self.result['reference'])
        self.assertEqual(result['status'],'ready')
        obstacle=Point(FWD(p.x,p.y)).buffer(80)
        for f in result['features']:self.assertFalse(transform(FWD,shape_geometry(f)).intersects(obstacle))

    def test_all_blocked_and_weather_out_of_window_have_explicit_causes(self):
        event=dict(id='all',state='blocked',observed_at=self.clock,geometry=mapping(self.area))
        blocked=calculate(self.conn,self.rid,dict(self.request,events=[event]))
        self.assertEqual(blocked['reason'],'endpoint_blocked');self.assertFalse(blocked['alternatives'])
        unknown=calculate(self.conn,self.rid,dict(self.request,time='2000-01-01T00:00:00Z'))
        self.assertEqual(unknown['status'],'unknown');self.assertFalse(unknown['features'])

    def test_budget_consumption_and_observation_are_not_reset(self):
        exhausted=calculate(self.conn,self.rid,dict(self.request,elapsed_s=1199))
        self.assertEqual(exhausted['reason'],'insufficient_return_budget')
        returned=calculate(self.conn,self.rid,dict(self.request,position=self.request['destination'],phase='return',elapsed_s=300))
        self.assertEqual(returned['status'],'ready');self.assertEqual(returned['remaining_s'],900)
        self.assertEqual(returned['alternatives'][0]['observation_s'],0)
        emergency=calculate(self.conn,self.rid,dict(self.request,position=self.request['destination'],phase='emergency_return'))
        self.assertFalse(emergency['alternatives'][0]['mission_completed'])

    def test_interruptions_and_invalid_replanning_positions_are_not_escape_routes(self):
        interrupted=calculate(self.conn,self.rid,dict(self.request,on_edge=True))
        self.assertEqual(interrupted['status'],'interrupted');self.assertFalse(interrupted['features'])
        with self.assertRaisesRegex(ValueError,'requiere un nodo'):
            calculate(self.conn,self.rid,dict(self.request,position=[-71.651234,-33.099123]))

    def test_same_point_zero_travel_and_outside_points(self):
        same=calculate(self.conn,self.rid,dict(self.request,destination=self.request['origin']))
        self.assertEqual(same['status'],'ready');self.assertEqual(len(same['alternatives']),1)
        self.assertEqual(same['alternatives'][0]['length_km'],0);self.assertEqual(same['alternatives'][0]['time_s'],60)
        with self.assertRaises(ValueError):calculate(self.conn,self.rid,dict(self.request,destination=[-71.5,-33.05]))

    def test_complete_pipeline_is_idempotent_and_source_tampering_is_rejected(self):
        again=run('completo','snapshot');self.assertTrue(again['idempotent']);self.assertEqual(again['counts'],self.report['counts'])
        config=json.loads((ROOT/'config/proyecto.json').read_text());doc=build(config)[0];bad=copy.deepcopy(doc)
        bad['lineage']['profile']['grid_m']=400
        with self.assertRaises(ValueError):validate_infrastructure(bad,config)
        path=ROOT/'datos/runs'/self.rid/'metadata/bases.json'
        self.assertTrue(load(self.conn,path)['idempotent'])
        packet=json.loads(path.read_text());packet['records'][0]['name']='inventado'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.json';write_json(p,packet)
            with self.assertRaises(ValueError):load(self.conn,p)


def shape_geometry(feature):
    from shapely.geometry import shape
    return shape(feature['geometry'])
