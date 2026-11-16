from app.modules.intake.reader import read
def ingest(raw):
    out=read(raw);out['accepted']=len(out['rows']);return out
