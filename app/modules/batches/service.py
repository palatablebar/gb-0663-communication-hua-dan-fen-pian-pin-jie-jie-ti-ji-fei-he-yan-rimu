from app import store
from app.errors import RuleError
from app.modules.batches.review import check

def persist(bundle):return store.save(bundle)
def approve(rid,version):
    b=store.latest()
    if not b or b['manifest']['run_id']!=rid:raise RuleError('NOT_FOUND','当前批次不存在',404)
    check(b);return store.review(rid,version)
