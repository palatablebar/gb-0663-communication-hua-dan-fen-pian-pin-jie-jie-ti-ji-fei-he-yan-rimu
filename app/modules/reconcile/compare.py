from decimal import Decimal

def compare(intake,calculation,quarantine,invoices):
    rows=[]
    for r in calculation['rows']:
        billed=invoices.get(r['session']);delta=None if billed is None else Decimal(billed)-Decimal(r['fee'])
        rows.append({'session':r['session'],'computed':r['fee'],'provider':billed,'difference':None if delta is None else str(delta.quantize(Decimal('.01'))),'state':'缺账单' if billed is None else ('相符' if delta==0 else '有差异'),'evidence':{'raw_seconds':r['raw_seconds'],'active_seconds':r['active_seconds'],'gap_seconds':r['gap_seconds'],'overlap_seconds':r['overlap_seconds'],'sources':r['sources']}})
    delta=intake['input']-calculation['accepted_fragments']-quarantine['total']-intake['blank']
    active=sum((Decimal(r['active_seconds']) for r in calculation['rows']),Decimal(0));raw=sum((Decimal(r['raw_seconds']) for r in calculation['rows']),Decimal(0));overlap=sum((Decimal(r['overlap_seconds']) for r in calculation['rows']),Decimal(0))
    return {'rows':rows,'input':intake['input'],'output':calculation['accepted_fragments'],'isolated':quarantine['total'],'blank':intake['blank'],'row_delta':delta,'balanced':delta==0 and raw==active+overlap,'active_seconds':str(active),'raw_seconds':str(raw),'overlap_seconds':str(overlap),'differences':sum(r['state']!='相符' for r in rows),'total_difference':str(sum((Decimal(r['difference']) for r in rows if r['difference'] is not None),Decimal(0)).quantize(Decimal('.01'))),'orphan_invoices':sorted(set(invoices)-{r['session'] for r in calculation['rows']})}
