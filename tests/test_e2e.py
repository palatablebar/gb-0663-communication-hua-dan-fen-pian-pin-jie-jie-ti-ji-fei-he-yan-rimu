from app.modules.model.stitch import stitch

def test_pages(client):
    for slug in ['intake','contract','model','calculate','quarantine','reconcile','batches']:
        r=client.get('/'+slug);assert r.status_code==200;assert 'statusbar' in r.text

def test_module_posts(client):
    for slug in ['intake','contract','model','calculate','quarantine','reconcile']:
        assert client.post('/api/'+slug,json={}).status_code==200

def test_csv_export(client):
    r=client.get('/api/quarantine/export');assert r.status_code==200;assert r.text.count('\n')==13

def test_empty_flow(client):
    r=client.post('/api/runs',json={'csv_text':''});assert r.status_code==200;assert r.json()['reconcile']['balanced'];assert r.json()['calculate']['total_fee']=='0.00'

def test_cross_month_union():
    r=stitch([{'start':'2026-10-31T23:59:30+00:00','end':'2026-11-01T00:00:30+00:00'},{'start':'2026-11-01T00:00:00+00:00','end':'2026-11-01T00:01:30+00:00'}]);assert r['active_seconds']=='120.0';assert r['overlap_seconds']=='30.0'

def test_tariff_overlap_quarantine(clean):
    from app.modules.calculate.service import calculate
    tariffs=clean['contract']['tariffs']+[clean['contract']['tariffs'][0].copy()];r=calculate(clean['model']['sessions'],tariffs)
    assert len(r['issues'])==30;assert r['sessions']==4
