from collections import Counter
from app.reasons import REASONS

def classify(issues,code=None):
    return {'rows':[dict(r,reason=REASONS.get(r['code'],r['code'])) for r in issues if code is None or r['code']==code],'counts':dict(sorted(Counter(r['code'] for r in issues).items())),'total':len(issues)}
