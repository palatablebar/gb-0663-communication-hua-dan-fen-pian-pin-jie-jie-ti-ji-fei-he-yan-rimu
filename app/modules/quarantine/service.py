import csv,io,json
from app.modules.quarantine.diagnose import classify

def quarantine(*groups):return classify([r for group in groups for r in group])
def evidence_csv(rows):
    out=io.StringIO();w=csv.writer(out);w.writerow(['line','code','reason','raw'])
    for r in rows:w.writerow([r['line'],r['code'],r['reason'],json.dumps(r['raw'],ensure_ascii=False)])
    return '﻿'+out.getvalue()
