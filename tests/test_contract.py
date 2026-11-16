import pytest
from app.modules.contract.normalize import sequence,instant
from app.errors import RuleError

def test_fullwidth_sequence():
    """TRAP-06"""
    assert sequence('１')==1

def test_missing(dirty):
    """TRAP-07"""
    assert any(r['code']=='MISSING' for r in dirty['contract']['issues'])

def test_leading_zero(clean):
    """TRAP-08"""
    assert clean['contract']['rows'][0]['subscriber']=='00000001'

def test_offset_equivalence():
    assert instant('2026-11-02T09:00:00+08:00')==instant('2026-11-02T01:00:00Z')

def test_unknown_zone(dirty):
    assert any(r['code']=='ZONE' for r in dirty['contract']['issues'])

def test_reversed(dirty):
    assert any(r['code']=='REVERSED' for r in dirty['contract']['issues'])

def test_sequence_fraction():
    with pytest.raises(RuleError):sequence('1.5')
