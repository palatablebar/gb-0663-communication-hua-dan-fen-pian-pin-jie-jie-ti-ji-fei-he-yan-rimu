from fastapi import APIRouter,Request,Body
from app.web import page
from app import store
from app.pipeline import execute,sample_bytes
router=APIRouter()
@router.get('/calculate')
def view(request:Request):return page(request,'calculate')
@router.get('/api/calculate')
def result():return store.latest()['calculate']
@router.post('/api/calculate')
def trial(payload:dict=Body(default={})):
    raw=payload.get('csv_text');data=execute(raw.encode() if isinstance(raw,str) else sample_bytes(payload.get('sample','dirty')))
    return data['calculate']
