from datetime import datetime
from decimal import Decimal

def union(intervals):
    out=[]
    for a,b in sorted(intervals):
        if out and a<=out[-1][1]:out[-1]=(out[-1][0],max(b,out[-1][1]))
        else:out.append((a,b))
    return out

def seconds(intervals):
    return sum((Decimal(str((b-a).total_seconds())) for a,b in intervals),Decimal(0))

def stitch(rows):
    intervals=[(datetime.fromisoformat(r['start']),datetime.fromisoformat(r['end'])) for r in rows]
    merged=union(intervals);active=seconds(merged);raw=seconds(intervals);span=seconds([(min(a for a,b in intervals),max(b for a,b in intervals))])
    return {'active_seconds':str(active),'raw_seconds':str(raw),'overlap_seconds':str(raw-active),'gap_seconds':str(span-active),'windows':[{'start':a.isoformat(),'end':b.isoformat()} for a,b in merged]}
