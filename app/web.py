from fastapi.templating import Jinja2Templates
from app.config import ROOT
from app import store
from app.reasons import REASONS
PAGES=[('intake','话单接收'),('contract','资费契约'),('model','分片拼接'),('calculate','计费重算'),('quarantine','坏单隔离'),('reconcile','账单勾稽'),('batches','批次复核')]
templates=Jinja2Templates(directory=str(ROOT/'app/templates'))

def _session_of(raw):
    if isinstance(raw,dict):value=raw.get('session')
    elif isinstance(raw,list) and len(raw)>1:value=raw[1]
    else:value=None
    return value.strip() if isinstance(value,str) and value.strip() else None

_LIST_KEYS=('base_lines','package_lines','final_sources','base_sources','package_sources',
            'current_sources','replaced_lines','retained_lines')

def _display(item):
    """Render list-valued provenance as space-joined text for table cells."""
    out=dict(item)
    for key in _LIST_KEYS:
        value=out.get(key)
        if isinstance(value,(list,tuple)):out[key]=' '.join(map(str,value)) or '—'
    for key in ('fee_before','fee_after','package_fee','minutes_before','minutes_after'):
        if out.get(key) is None:out[key]='—'
    return out

def _adopted(session,row):
    sources=row.get('source_origins') or []
    return {'session':session,'status':'ADOPTED','status_label':'最终采用','reason':None,'reason_label':'',
            'base_lines':row.get('sources',[]),'package_lines':[],'final_sources':sources,
            'base_sources':sources,'package_sources':[],'current_sources':sources,
            'fee_before':None,'fee_after':row.get('fee'),'package_fee':None,'package_differs':'否',
            'replaced_lines':[],'retained_lines':[]}

def _quarantined(bundle,accepted):
    grouped={}
    for issue in bundle['quarantine']['rows']:
        session=_session_of(issue.get('raw'))
        if not session or session in accepted:continue
        grouped.setdefault(session,{'session':session,'lines':[],'codes':[]})
        grouped[session]['lines'].append(issue['line']);grouped[session]['codes'].append(issue['code'])
    return [{'session':item['session'],'status':'STILL_ISOLATED','status_label':'仍隔离',
             'reason':item['codes'][0],'reason_label':REASONS.get(item['codes'][0],item['codes'][0]),
             'base_lines':sorted(item['lines']),'package_lines':[],'final_sources':[],
             'base_sources':['root:%s'%line for line in item['lines']],'package_sources':[],
             'current_sources':[],'fee_before':None,'fee_after':None,'package_fee':None,
             'package_differs':'否','replaced_lines':[],'retained_lines':[]}
            for item in sorted(grouped.values(),key=lambda x:x['session'])]

def batch_view(bundle,repairs):
    """Batch page view: still-isolated, repaired, finally-adopted, and the ledger.

    ``repairs`` are ledger rows for the current root batch, newest first.  A
    package that was evaluated but could not be adopted (decision WAIT) has no
    corresponding head batch, so its own receipt is surfaced instead of the
    stale root view; that is what lets the reviewer see exactly which sessions
    are still isolated and which rows the supplier left unresolved.
    """
    ledger=[{'package_sha256':item['package_sha256'],'base_run_id':item['base_run_id'],
             'effective_run_id':item['effective_run_id'] if item['decision']!='WAIT' else '—',
             'decision':item['decision'],
             'created':item['created'],
             'repaired':item['receipt'].get('counts',{}).get('REPAIRED',0),
             'isolated':item['receipt'].get('counts',{}).get('STILL_ISOLATED',0)
                         +item['receipt'].get('counts',{}).get('UNKNOWN_SESSION',0),
             'awaiting':item['receipt'].get('counts',{}).get('AWAITING_PACKAGE',0)}
            for item in repairs]
    latest=repairs[0]['receipt'] if repairs else None
    if not bundle:
        return {'repair':latest,'decision':latest,'adopted':[],'repaired':[],'isolated':[],
                'packages':ledger,'root_id':None,'pending':False}
    repair=bundle.get('repair')
    decision=repair or latest
    # A WAIT package evaluated against the current head has no new batch of its
    # own; show its receipt rather than the older adopted view so the reviewer
    # sees the latest supplier state.
    pending=bool(latest and latest.get('decision')=='WAIT'
                 and latest.get('base_run_id')==bundle['manifest']['run_id'])
    accepted={row['session']:row for row in bundle['calculate']['rows']}
    origins={}
    for row in bundle['model']['sessions']:
        for line,origin in zip(row['sources'],row.get('source_origins') or []):
            origins.setdefault(row['session'],[]).append(origin)
    adopted=[];repaired=[];isolated=[]
    if pending:
        # The package was evaluated but nothing could be adopted, so the head
        # batch is unchanged; show the package's own still-open sessions.
        for item in decision['sessions']:
            isolated.append(dict(item,status='PROTECTED' if item['status']=='PROTECTED' else 'STILL_ISOLATED'))
        adopted=[_adopted(session,row) for session,row in accepted.items()]
    elif repair:
        for item in repair['sessions']:
            if item['status']=='REPAIRED':
                row=accepted.get(item['session'],{})
                repaired.append(dict(item,final_fee=row.get('fee'),final_minutes=row.get('billed_minutes'),
                                     current_sources=row.get('source_origins') or item['final_sources']))
            elif item['status']=='PROTECTED':
                adopted.append(dict(item,current_sources=origins.get(item['session'],item['base_sources']),
                                    package_differs='是' if item.get('package_differs') else '否'))
            else:
                isolated.append(item)
        for session,row in accepted.items():
            if not any(x['session']==session for x in adopted+repaired):
                adopted.append(_adopted(session,row))
    else:
        adopted=[_adopted(session,row) for session,row in accepted.items()]
        isolated=_quarantined(bundle,set(accepted))
    shown = latest if pending else (repair or None)
    return {'repair':shown,'decision':decision,
            'pending':pending,
            'adopted':[_display(x) for x in sorted(adopted,key=lambda x:x['session'])],
            'repaired':[_display(x) for x in sorted(repaired,key=lambda x:x['session'])],
            'isolated':[_display(x) for x in sorted(isolated,key=lambda x:x['session'])],
            'packages':ledger,'root_id':(decision or {}).get('root_run_id') or bundle['manifest']['run_id']}

def page(request,slug):
    bundle=store.latest()
    root=(bundle or {}).get('root_run_id') or ((bundle or {}).get('manifest') or {}).get('run_id')
    return templates.TemplateResponse(request=request,name=slug+'.html',context={'bundle':bundle,'pages':PAGES,'slug':slug,'title':dict(PAGES)[slug],'history':store.history(),'batch':batch_view(bundle,store.repairs(root))})
