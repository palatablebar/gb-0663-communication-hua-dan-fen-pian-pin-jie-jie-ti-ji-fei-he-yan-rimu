from decimal import Decimal
from app.modules.calculate.tariff import select_tariff,charge
from app.errors import RuleError

def calculate(sessions,tariffs):
    rows=[];issues=[]
    for session in sessions:
        try:
            version=select_tariff(session['zone'],session['start'],tariffs);bill=charge(session['active_seconds'],version['tiers'])
            rows.append(dict(session,**bill,tariff_version=version['version'],currency='CNY'))
        except RuleError as e:
            issues.extend({'line':line,'code':e.code,'raw':session} for line in session['sources'])
    return {'rows':rows,'issues':issues,'total_fee':str(sum((Decimal(r['fee']) for r in rows),Decimal(0)).quantize(Decimal('.01'))),'minutes':sum(r['billed_minutes'] for r in rows),'sessions':len(rows),'accepted_fragments':sum(r['fragments'] for r in rows)}
