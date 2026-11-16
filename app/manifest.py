import hashlib,json,time
from app.config import RULE_VERSION
def make_manifest(raw, parameters, references):
    digest=hashlib.sha256(raw).hexdigest()
    canonical=json.dumps({'input':digest,'parameters':parameters,'references':references,'rule':RULE_VERSION},sort_keys=True,ensure_ascii=False)
    return {'run_id':hashlib.sha256(canonical.encode()).hexdigest()[:20],'sha256':digest,'rule_version':RULE_VERSION,'parameters':parameters,'references':references,'created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
