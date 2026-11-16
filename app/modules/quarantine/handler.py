from fastapi import APIRouter,Request,Body
from app.web import page
from app import store
from app.pipeline import execute,sample_bytes
router=APIRouter()
@router.get('/quarantine')
def view(request:Request):return page(request,'quarantine')
@router.get('/api/quarantine')
def result():return store.latest()['quarantine']
@router.post('/api/quarantine')
def trial(payload:dict=Body(default={})):
    raw=payload.get('csv_text');data=execute(raw.encode() if isinstance(raw,str) else sample_bytes(payload.get('sample','dirty')))
    return data['quarantine']
@router.get('/api/quarantine/export')
def export():
    from fastapi.responses import Response
    from app.modules.quarantine.service import evidence_csv
    return Response(evidence_csv(store.latest()['quarantine']['rows']),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="cdr-rejects.csv"'})
