from fastapi import APIRouter,Request,Body
from app.web import page
from app import store
from app.pipeline import execute,sample_bytes
router=APIRouter()
@router.get('/reconcile')
def view(request:Request):return page(request,'reconcile')
@router.get('/api/reconcile')
def result():return store.latest()['reconcile']
@router.post('/api/reconcile')
def trial(payload:dict=Body(default={})):
    raw=payload.get('csv_text');data=execute(raw.encode() if isinstance(raw,str) else sample_bytes(payload.get('sample','dirty')))
    return data['reconcile']
