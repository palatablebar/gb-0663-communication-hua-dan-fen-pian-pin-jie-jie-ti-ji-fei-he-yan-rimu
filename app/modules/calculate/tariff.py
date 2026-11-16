from decimal import Decimal,ROUND_CEILING,ROUND_HALF_UP
from app.modules.contract.service import instant
from app.errors import RuleError

def select_tariff(zone,start,tariffs):
    t=instant(start);found=[r for r in tariffs if r['zone']==zone and instant(r['start'])<=t<instant(r['end'])]
    if len(found)!=1:raise RuleError('TARIFF','资费版本重叠或未覆盖')
    return found[0]

def charge(active_seconds,tiers):
    count=int((Decimal(active_seconds)/60).to_integral_value(rounding=ROUND_CEILING));remaining=count;fee=Decimal(0);parts=[]
    if not tiers or tiers[-1]['minutes'] is not None:raise RuleError('TARIFF','阶梯资费缺少最后无限档')
    for tier in tiers:
        cap=tier['minutes'];take=remaining if cap is None else min(remaining,int(cap));rate=Decimal(tier['rate'])
        if rate<0 or (cap is not None and int(cap)<=0):raise RuleError('TARIFF','资费阶梯必须为正')
        fee+=take*rate;remaining-=take
        if take:parts.append({'minutes':take,'rate':str(rate),'fee':str(take*rate)})
    return {'billed_minutes':count,'fee':str(fee.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)),'tiers':parts}
