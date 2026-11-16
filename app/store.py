import os,sqlite3,json
from pathlib import Path
from app.errors import RuleError
def connect():
    path=os.environ.get('DB_PATH','/tmp/cdrforge.sqlite3')
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=15);con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, reviewed INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL)')
    return con

def save(bundle):
    rid=bundle['manifest']['run_id']
    with connect() as c:
        c.execute('INSERT OR IGNORE INTO runs(id,payload,created) VALUES(?,?,?)',(rid,json.dumps(bundle,ensure_ascii=False),bundle['manifest']['created_at']))
        row=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
    out=json.loads(row['payload']);out['version']=row['version'];out['reviewed']=bool(row['reviewed'])
    return out

def latest():
    with connect() as c: row=c.execute('SELECT * FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
    if not row:return None
    out=json.loads(row['payload']);out['version']=row['version'];out['reviewed']=bool(row['reviewed']);return out

def history():
    with connect() as c: rows=c.execute('SELECT id,version,reviewed,created FROM runs ORDER BY rowid DESC').fetchall()
    return [dict(r) for r in rows]

def review(rid,version):
    with connect() as c:
        cur=c.execute('UPDATE runs SET version=version+1,reviewed=1 WHERE id=? AND version=?',(rid,version))
        if cur.rowcount!=1:raise RuleError('STALE','记录已变更，请刷新后复核',409)
    return {'run_id':rid,'version':version+1,'reviewed':True}
