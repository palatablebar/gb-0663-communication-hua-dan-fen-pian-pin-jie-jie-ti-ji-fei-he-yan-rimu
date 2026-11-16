from fastapi import APIRouter,Request,Body
from app.web import page
from app import store
from app.pipeline import execute,sample_bytes
router=APIRouter()
@router.get('/batches')
def view(request:Request):return page(request,'batches')
@router.get('/api/batches')
def result():return store.history()
@router.post('/api/batches/review')
def review(payload:dict=Body(...)):
    from app.modules.batches.service import approve
    if not isinstance(payload.get('version'),int):
        from app.errors import RuleError
        raise RuleError('VERSION','版本必须为整数')
    return approve(payload.get('run_id',''),payload['version'])
