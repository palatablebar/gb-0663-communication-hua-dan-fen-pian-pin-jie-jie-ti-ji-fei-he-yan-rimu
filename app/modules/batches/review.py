from app.errors import RuleError

def check(bundle):
    if not bundle['reconcile']['balanced']:raise RuleError('UNBALANCED','片段行数不平，请修正后复核',409)
    return True
