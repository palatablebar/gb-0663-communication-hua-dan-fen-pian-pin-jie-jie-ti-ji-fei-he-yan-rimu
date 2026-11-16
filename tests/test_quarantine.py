from app.modules.quarantine.service import evidence_csv
from app.modules.quarantine.diagnose import classify

def test_count(dirty):
    assert dirty['quarantine']['total']==12

def test_raw_evidence(dirty):
    assert all(r['line']>0 and r['reason'] for r in dirty['quarantine']['rows'])

def test_missing_retained(dirty):
    r=next(r for r in dirty['quarantine']['rows'] if r['code']=='MISSING');assert r['raw']['sequence']=='N/A'

def test_filter(dirty):
    r=classify(dirty['quarantine']['rows'],'SEQUENCE');assert len(r['rows'])==2

def test_csv(dirty):
    s=evidence_csv(dirty['quarantine']['rows']);assert s.startswith('\ufeffline,code,reason,raw');assert s.count('\n')==13

def test_clean_no_issues(clean):
    assert clean['quarantine']['rows']==[];assert clean['quarantine']['total']==0

def test_count_conserve(dirty):
    assert sum(dirty['quarantine']['counts'].values())==12
