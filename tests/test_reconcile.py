from copy import deepcopy
from decimal import Decimal
from app.modules.reconcile.compare import compare

def test_row_conservation(dirty):
    r=dirty['reconcile'];assert r['input']==53;assert r['output']==40;assert r['isolated']==12;assert r['blank']==1;assert r['balanced']

def test_seconds_conserve(clean):
    r=clean['reconcile'];assert Decimal(r['raw_seconds'])==Decimal(r['active_seconds'])+Decimal(r['overlap_seconds']);assert r['active_seconds']=='1260.0'

def test_provider_diff(clean):
    r=clean['reconcile'];assert r['total_difference']=='8.00';assert r['differences']==14

def test_missing_invoice(dirty):
    r=next(r for r in dirty['reconcile']['rows'] if r['session']=='C00092');assert r['state']=='缺账单';assert r['difference'] is None

def test_orphan_invoice(dirty):
    assert dirty['reconcile']['orphan_invoices']==['C00001']

def test_bad_count_detected(dirty):
    x=deepcopy(dirty['intake']);x['input']+=1;r=compare(x,dirty['calculate'],dirty['quarantine'],{});assert not r['balanced'];assert r['row_delta']==1

def test_dirty_total(dirty):
    assert dirty['calculate']['total_fee']=='15.80';assert dirty['calculate']['minutes']==27
