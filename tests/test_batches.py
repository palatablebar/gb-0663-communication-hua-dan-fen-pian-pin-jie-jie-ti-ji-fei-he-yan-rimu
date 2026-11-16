from app import store

def test_same_key(client):
    a=client.post('/api/runs',json={}).json();b=client.post('/api/runs',json={'sample':'dirty'}).json();assert a['manifest']['run_id']==b['manifest']['run_id'];assert len(store.history())==1

def test_new_content_key(client):
    a=store.latest();b=client.post('/api/runs',json={'sample':'clean'}).json();assert a['manifest']['run_id']!=b['manifest']['run_id'];assert len(store.history())==2

def test_stale_review(client):
    """TRAP-26"""
    b=store.latest();p={'run_id':b['manifest']['run_id'],'version':b['version']};assert client.post('/api/batches/review',json=p).status_code==200;assert client.post('/api/batches/review',json=p).status_code==409

def test_atomic(client):
    count=len(store.history());assert client.post('/api/runs',json={'csv_text':'invalid'}).status_code==422;assert len(store.history())==count

def test_persistent(client):
    rid=store.latest()['manifest']['run_id'];store.connect().close();assert store.latest()['manifest']['run_id']==rid

def test_reference_digests(dirty):
    assert set(dirty['manifest']['references'])=={'tariffs','invoices'};assert all(len(v)==64 for v in dirty['manifest']['references'].values())

def test_unknown_sample(client):
    assert client.post('/api/runs',json={'sample':'missing'}).status_code==404
