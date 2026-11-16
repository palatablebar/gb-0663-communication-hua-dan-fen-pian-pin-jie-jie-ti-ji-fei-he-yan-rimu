import os,sqlite3,json
from pathlib import Path
from app.errors import RuleError

SCHEMA=(
    'CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, reviewed INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS repairs(root_run_id TEXT NOT NULL, base_run_id TEXT NOT NULL, package_sha TEXT NOT NULL, effective_run_id TEXT NOT NULL, decision TEXT NOT NULL, receipt TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(root_run_id,package_sha))',
)

def connect():
    path=os.environ.get('DB_PATH','/tmp/cdrforge.sqlite3')
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=15);con.row_factory=sqlite3.Row
    for statement in SCHEMA:con.execute(statement)
    return con

def _bundle(row):
    out=json.loads(row['payload']);out['version']=row['version'];out['reviewed']=bool(row['reviewed']);return out

def save(bundle):
    rid=bundle['manifest']['run_id']
    with connect() as c:
        c.execute('INSERT OR IGNORE INTO runs(id,payload,created) VALUES(?,?,?)',(rid,json.dumps(bundle,ensure_ascii=False),bundle['manifest']['created_at']))
        row=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
    return _bundle(row)

def latest():
    with connect() as c:row=c.execute('SELECT * FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
    return _bundle(row) if row else None

def history():
    with connect() as c:rows=c.execute('SELECT id,version,reviewed,created FROM runs ORDER BY rowid DESC').fetchall()
    return [dict(r) for r in rows]

def repairs(root=None):
    sql='SELECT * FROM repairs';args=()
    if root:sql+=' WHERE root_run_id=?';args=(root,)
    with connect() as c:rows=c.execute(sql+' ORDER BY rowid DESC',args).fetchall()
    out=[]
    for row in rows:
        item={'root_run_id':row['root_run_id'],'base_run_id':row['base_run_id'],'package_sha256':row['package_sha'],'effective_run_id':row['effective_run_id'],'decision':row['decision'],'created':row['created'],'receipt':json.loads(row['receipt'])}
        out.append(item)
    return out

def review(rid,version):
    with connect() as c:
        cur=c.execute('UPDATE runs SET version=version+1,reviewed=1 WHERE id=? AND version=?',(rid,version))
        if cur.rowcount!=1:raise RuleError('STALE','记录已变更，请刷新后复核',409)
    return {'run_id':rid,'version':version+1,'reviewed':True}

def find_repair(root,package_sha):
    with connect() as c:row=c.execute('SELECT * FROM repairs WHERE root_run_id=? AND package_sha=?',(root,package_sha)).fetchone()
    return _receipt(row,True) if row else None

def register_repair(root_id,base_id,package_sha,effective_id,payload,receipt):
    """Register one repair package and its effective run in a single transaction.

    The ledger is content-addressed by (root batch, package digest).  A replay of
    the same package returns the receipt already stored and never inserts a
    second run, so retries cannot add a batch or bump its version.  The payload
    is computed by the caller before this function is entered; if the write
    fails the transaction rolls back and the previous run stays untouched.
    A WAIT receipt carries no payload and is still recorded, so a retry of a
    package that could not be adopted never creates a batch either.
    """
    created=receipt['created']
    try:
        with connect() as c:
            row=c.execute('SELECT * FROM repairs WHERE root_run_id=? AND package_sha=?',(root_id,package_sha)).fetchone()
            if row:return _receipt(row,True)
            if payload is not None:
                c.execute('INSERT OR IGNORE INTO runs(id,payload,created) VALUES(?,?,?)',(effective_id,json.dumps(payload,ensure_ascii=False),created))
            c.execute('INSERT INTO repairs(root_run_id,base_run_id,package_sha,effective_run_id,decision,receipt,created) VALUES(?,?,?,?,?,?,?)',(root_id,base_id,package_sha,effective_id,receipt['decision'],json.dumps(receipt,ensure_ascii=False),created))
    except sqlite3.IntegrityError:
        with connect() as c:row=c.execute('SELECT * FROM repairs WHERE root_run_id=? AND package_sha=?',(root_id,package_sha)).fetchone()
        if not row:raise
        return _receipt(row,True)
    return dict(receipt,idempotent=False)

def _receipt(row,replay):
    out=json.loads(row['receipt']);out['idempotent']=replay
    with connect() as c:run=c.execute('SELECT version,reviewed FROM runs WHERE id=?',(row['effective_run_id'],)).fetchone()
    if run:out['version']=run['version'];out['reviewed']=bool(run['reviewed'])
    return out
