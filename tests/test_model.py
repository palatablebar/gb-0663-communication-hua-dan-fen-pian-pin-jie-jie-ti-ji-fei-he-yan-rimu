from copy import deepcopy
from datetime import datetime
from app.modules.model.stitch import union,seconds,stitch
from app.modules.model.service import assemble

def test_sample_union_counterexample(clean):
    r=clean['model']['sessions'][0];assert r['active_seconds']=='90.0';assert r['raw_seconds']=='100.0';assert r['gap_seconds']=='50.0'

def test_conflict_isolate_whole_session(dirty):
    """TRAP-14"""
    assert sum(r['code']=='CONFLICT' for r in dirty['model']['issues'])==5;assert all(r['session']!='C00001' for r in dirty['model']['sessions'])

def test_sequence_hole(dirty):
    assert sum(r['code']=='SEQUENCE' for r in dirty['model']['issues'])==2

def test_duplicate_exact(clean):
    rows=deepcopy(clean['contract']['rows']);rows.append(dict(rows[3],line=999));r=assemble(rows);assert sum(i['code']=='DUPLICATE' for i in r['issues'])==1;assert len(r['rows'])==42

def test_adjacent_half_open():
    """TRAP-23"""
    a=datetime.fromisoformat('2026-01-01T00:00:00+00:00');b=datetime.fromisoformat('2026-01-01T00:01:00+00:00');c=datetime.fromisoformat('2026-01-01T00:02:00+00:00')
    merged=union([(a,b),(b,c)]);assert len(merged)==1;assert seconds(merged)==120

def test_reorder_invariant(clean):
    r=assemble(list(reversed(clean['contract']['rows'])));assert r['sessions']==clean['model']['sessions']

def test_subscriber_conflict(clean):
    rows=deepcopy(clean['contract']['rows'][:3]);rows[1]['subscriber']='other';r=assemble(rows);assert r['sessions']==[];assert all(i['code']=='METADATA' for i in r['issues'])
