import pytest
from app.pipeline import sample_bytes
from app.modules.intake.reader import read
from app.errors import RuleError

def test_bom():
    """TRAP-02"""
    r=read(sample_bytes());assert r['input']==53;assert r['rows'][0]['subscriber']=='00000001'

def test_legacy():
    """TRAP-01"""
    r=read(sample_bytes('gb18030'));assert r['encoding']=='gb18030';assert r['rows'][0]['zone']=='国内'

def test_column_error(dirty):
    assert dirty['intake']['issues'][0]['code']=='COLUMN_COUNT';assert dirty['intake']['issues'][0]['line']==53

def test_blank(dirty):
    assert dirty['intake']['blank']==1;assert dirty['intake']['state']=='READY'

def test_empty_states():
    h=b'subscriber,session,sequence,start,end,zone\n';assert read(b'')['state']=='EMPTY_FILE';assert read(h)['state']=='HEADER_ONLY';assert read(h+b'\n')['state']=='BLANK_ROWS'

def test_truncated():
    with pytest.raises(RuleError):read(b'subscriber,session,sequence,start,end,zone\n"unfinished')

def test_source_order(dirty):
    assert dirty['intake']['rows'][0]['line']==2;assert dirty['intake']['rows'][3]['line']==5
