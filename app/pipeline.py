import json,hashlib,time
from app.config import SAMPLES
from app.errors import RuleError
from app.manifest import make_manifest
from app.modules.intake.service import ingest
from app.modules.contract.service import normalize
from app.modules.model.service import assemble
from app.modules.calculate.service import calculate
from app.modules.quarantine.service import quarantine
from app.modules.reconcile.service import reconcile

def execute(raw):
    start=time.perf_counter();objects={};refs={}
    for name in ('tariffs','invoices'):
        data=(SAMPLES/(name+'.json')).read_bytes();refs[name]=hashlib.sha256(data).hexdigest();objects[name]=json.loads(data)
    intake=ingest(raw);contract=normalize(intake['rows'],objects['tariffs']);model=assemble(contract['rows']);calc=calculate(model['sessions'],objects['tariffs']);isolated=quarantine(intake['issues'],contract['issues'],model['issues'],calc['issues']);checked=reconcile(intake,calc,isolated,objects['invoices'])
    manifest=make_manifest(raw,{},refs);manifest['elapsed_ms']=round((time.perf_counter()-start)*1000,3)
    return {'manifest':manifest,'intake':intake,'contract':contract,'model':model,'calculate':calc,'quarantine':isolated,'reconcile':checked}

def sample_bytes(name='dirty'):
    if name not in ('dirty','clean','gb18030'):raise RuleError('SAMPLE','话单样例不存在',404)
    return (SAMPLES/(name+'.csv')).read_bytes()
