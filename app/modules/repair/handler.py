from fastapi import APIRouter, Body
from fastapi.responses import Response

from app import store
from app.errors import RuleError
from app.modules.repair.service import apply, package_bytes, evidence_csv

router = APIRouter()


@router.get('/api/repairs')
def result(root: str = None):
    return store.repairs(root)


@router.post('/api/repairs')
def submit(payload: dict = Body(default={})):
    base = store.latest()
    if not base:
        raise RuleError('NOT_FOUND', '当前没有可修复的批次', 404)
    text = payload.get('csv_text')
    if isinstance(text, str):
        raw = text.encode('utf-8')
    else:
        raw = package_bytes(payload.get('sample', 'repair_partial'))
    return apply(base, raw)


@router.get('/api/repairs/export')
def export(root: str = None):
    rows = store.repairs(root)
    return Response(evidence_csv(rows), media_type='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="cdr-repair-audit.csv"'})


# Aliases so the batch review contract is reachable from either module path.
@router.get('/api/repair')
def result_alias(root: str = None):
    return result(root)


@router.post('/api/repair')
def submit_alias(payload: dict = Body(default={})):
    return submit(payload)


@router.post('/api/batches/repair')
def submit_batch(payload: dict = Body(default={})):
    return submit(payload)
