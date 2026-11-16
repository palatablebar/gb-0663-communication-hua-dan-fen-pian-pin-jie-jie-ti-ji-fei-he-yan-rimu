from contextlib import asynccontextmanager
from fastapi import FastAPI,Body,Request
from fastapi.responses import JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.config import ROOT
from app.errors import RuleError
from app.pipeline import execute,sample_bytes
from app.modules.batches.service import persist
from app import store
@asynccontextmanager
async def lifespan(app):
    store.connect().close()
    if store.latest() is None:persist(execute(sample_bytes()))
    yield
app=FastAPI(title='话单拼接与计费核验',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=str(ROOT/'app/static')),name='static')
@app.exception_handler(RuleError)
async def rule_error(request:Request,exc:RuleError):return JSONResponse({'code':exc.code,'detail':exc.message},status_code=exc.status)
@app.exception_handler(ValueError)
async def bad_value(request:Request,exc:ValueError):return JSONResponse({'code':'VALUE','detail':'参数格式无效，请检查后重试'},status_code=422)
@app.get('/',include_in_schema=False)
def home():return RedirectResponse('/calculate')
@app.get('/health')
def health():return {'status':'ok'}
@app.post('/api/runs')
def run(payload:dict=Body(default={})):
    raw=payload.get('csv_text')
    return persist(execute(raw.encode('utf-8') if isinstance(raw,str) else sample_bytes(payload.get('sample','dirty'))))
from app.modules.intake.handler import router as r1
from app.modules.contract.handler import router as r2
from app.modules.model.handler import router as r3
from app.modules.calculate.handler import router as r4
from app.modules.quarantine.handler import router as r5
from app.modules.reconcile.handler import router as r6
from app.modules.batches.handler import router as r7
for router in (r1,r2,r3,r4,r5,r6,r7):app.include_router(router)
