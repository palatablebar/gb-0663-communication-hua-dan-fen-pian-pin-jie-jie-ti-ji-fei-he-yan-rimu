from copy import deepcopy
from decimal import Decimal
import pytest
from app.modules.calculate.tariff import charge,select_tariff
from app.errors import RuleError

def test_union_before_rounding(clean):
    r=clean['calculate']['rows'][0];assert r['billed_minutes']==2;assert r['fee']=='0.40'

def test_cross_zone_rates(clean):
    assert next(r for r in clean['calculate']['rows'] if r['zone']=='漫游')['fee']=='3.00';assert clean['calculate']['total_fee']=='16.00'

def test_tier_boundary(clean):
    tiers=clean['contract']['tariffs'][0]['tiers'];assert charge('180',tiers)['fee']=='0.60';assert charge('181',tiers)['fee']=='0.70'

def test_decimal_exact():
    """TRAP-10"""
    tiers=[{'minutes':None,'rate':'.10'}];assert sum((Decimal(charge('60',tiers)['fee']) for _ in range(1000)),Decimal(0))==Decimal('100.00')

def test_overlapping_version(clean):
    """TRAP-25"""
    t=deepcopy(clean['contract']['tariffs']);t.append(t[0].copy())
    with pytest.raises(RuleError) as e:select_tariff('国内','2026-11-02T01:00:00Z',t)
    assert e.value.code=='TARIFF'

def test_version_end_boundary(clean):
    t=deepcopy(clean['contract']['tariffs']);v=deepcopy(t[0]);v.update(start='2027-01-01T00:00:00+08:00',end='2028-01-01T00:00:00+08:00',version='domestic-2027');t.append(v)
    assert select_tariff('国内','2027-01-01T00:00:00+08:00',t)['version']=='domestic-2027'

def test_microsecond_ceiling(clean):
    tiers=clean['contract']['tariffs'][0]['tiers'];assert charge('60.000001',tiers)['billed_minutes']==2
