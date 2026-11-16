from collections import defaultdict
from app.modules.model.stitch import stitch

def assemble(rows):
    groups=defaultdict(list)
    for r in rows:groups[r['session']].append(r)
    accepted=[];sessions=[];issues=[]
    for session,records in sorted(groups.items()):
        code=None
        if len({(r['subscriber'],r['zone']) for r in records})!=1:code='METADATA'
        byseq=defaultdict(list)
        for r in records:byseq[r['sequence']].append(r)
        if any(len({(r['start'],r['end']) for r in items})>1 for items in byseq.values()):code='CONFLICT'
        if sorted(byseq)!=list(range(1,max(byseq)+1)):code=code or 'SEQUENCE'
        if code:
            issues.extend({'line':r['line'],'code':code,'raw':r} for r in records);continue
        unique=[]
        for seq,items in sorted(byseq.items()):
            winner=min(items,key=lambda r:r['line']);unique.append(winner)
            issues.extend({'line':r['line'],'code':'DUPLICATE','raw':r} for r in items if r is not winner)
        merged=stitch(unique);accepted.extend(unique)
        sessions.append({'session':session,'subscriber':unique[0]['subscriber'],'zone':unique[0]['zone'],'start':min(r['start'] for r in unique),'sources':[r['line'] for r in unique],'fragments':len(unique),**merged})
    return {'rows':accepted,'sessions':sessions,'issues':issues}
