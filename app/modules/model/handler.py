from fastapi import APIRouter,Request,Body
from app.web import page
from app import store
from app.pipeline import execute,sample_bytes
router=APIRouter()
@router.get('/model')
def view(request:Request):return page(request,'model')
@router.get('/api/model')
def result():return store.latest()['model']
@router.post('/api/model')
def trial(payload:dict=Body(default={})):
    raw=payload.get('csv_text');data=execute(raw.encode() if isinstance(raw,str) else sample_bytes(payload.get('sample','dirty')))
    return data['model']
