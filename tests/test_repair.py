import json

import pytest

from app import store
from app.errors import RuleError
from app.modules.repair.service import apply, evidence_csv, package_bytes, plan
from app.pipeline import execute, sample_bytes


@pytest.fixture
def base(dirty):
    return dirty


def _by_session(receipt):
    return {item['session']: item for item in receipt['sessions']}


def test_partial_package_adopts_confirmed_only(base):
    receipt, effective, run_id = plan(base, package_bytes('repair_partial'))
    assert receipt['decision'] == 'PARTIAL_ADOPT'
    rows = _by_session(receipt)
    assert rows['C00001']['status'] == 'REPAIRED'
    assert rows['C00090']['status'] == 'REPAIRED'
    assert rows['C00095']['status'] == 'STILL_ISOLATED'
    assert rows['C00095']['reason'] == 'ZONE'
    assert rows['C00091']['status'] == 'AWAITING_PACKAGE'
    assert rows['C00099']['status'] == 'UNKNOWN_SESSION'
    assert run_id is not None


def test_correct_sessions_never_change(base):
    receipt, effective, _ = plan(base, package_bytes('repair_partial'))
    before = {row['session']: row['fee'] for row in base['calculate']['rows']}
    after = {row['session']: row['fee'] for row in effective['calculate']['rows']}
    for session, fee in before.items():
        if session in {'C00001', 'C00090'}:
            continue
        assert after[session] == fee
    protected = _by_session(receipt)['C00002']
    assert protected['status'] == 'PROTECTED'
    assert protected['package_fee'] is not None and protected['package_differs']
    assert protected['fee_after'] == protected['fee_before'] == before['C00002']


def test_merge_is_session_atomic(base):
    """Adopting only part of a session must leave it isolated, never half-merged."""
    # C00090 is missing sequence 2.  A package that supplies sequence 4 instead
    # cannot be grafted on: the session still has a hole and stays isolated.
    rows = ['subscriber,session,sequence,start,end,zone',
            '00000090,C00090,4,2026-11-02T09:01:00+08:00,2026-11-02T09:02:00+08:00,国内']
    receipt, effective, _ = plan(base, '\n'.join(rows).encode())
    item = _by_session(receipt)['C00090']
    assert item['status'] == 'STILL_ISOLATED' and item['reason'] == 'SEQUENCE'
    assert effective is None and receipt['decision'] == 'WAIT'
    assert 46 in item['base_lines'] and 47 in item['base_lines']


def test_unusable_original_row_blocks_auto_merge():
    """A bad row that cannot be keyed by sequence must block auto-repair."""
    base_csv = ('subscriber,session,sequence,start,end,zone\n'
                '00000001,C00001,1,2026-11-02T09:00:00+08:00,2026-11-02T09:01:00+08:00,国内\n'
                '00000001,C00001,3,2026-11-02T09:02:00+08:00,2026-11-02T09:03:00+08:00,国内\n'
                '00000001,C00001,N/A,2026-11-02T09:01:00+08:00,2026-11-02T09:02:00+08:00,国内\n')
    base = execute(base_csv.encode())
    assert [i['code'] for i in base['contract']['issues']] == ['MISSING']
    assert base['calculate']['rows'] == []
    package = ('subscriber,session,sequence,start,end,zone\n'
               '00000001,C00001,2,2026-11-02T09:01:00+08:00,2026-11-02T09:02:00+08:00,国内\n')
    receipt, effective, _ = plan(base, package.encode())
    item = _by_session(receipt)['C00001']
    assert item['status'] == 'STILL_ISOLATED' and item['reason'] == 'MISSING'
    assert effective is None and receipt['decision'] == 'WAIT'


def test_package_fills_the_hole(base):
    rows = ['subscriber,session,sequence,start,end,zone',
            '00000090,C00090,2,2026-11-02T09:00:30+08:00,2026-11-02T09:00:40+08:00,国内']
    receipt, effective, _ = plan(base, '\n'.join(rows).encode())
    item = _by_session(receipt)['C00090']
    assert item['status'] == 'REPAIRED'
    assert item['fee_after'] == '0.20'
    assert item['final_sources'] == ['root:46', 'package:2', 'root:47']


def test_package_conflict_does_not_merge(base):
    receipt, effective, _ = plan(base, package_bytes('repair_waiting'))
    assert receipt['decision'] == 'WAIT'
    assert effective is None
    rows = _by_session(receipt)
    assert rows['C00001']['status'] == 'STILL_ISOLATED'
    assert rows['C00001']['reason'] == 'CONFLICT'
    assert rows['C00095']['reason'] == 'ZONE'


def test_no_contradiction_inside_effective_batch(base):
    _, effective, _ = plan(base, package_bytes('repair_partial'))
    assert not any(issue['code'] == 'CONFLICT' for issue in effective['model']['issues'])
    assert effective['reconcile']['balanced']
    assert effective['reconcile']['row_delta'] == 0
    assert effective['reconcile']['input'] == (
        effective['reconcile']['output'] + effective['reconcile']['isolated']
        + effective['reconcile']['blank'])
    sessions = {row['session'] for row in effective['model']['sessions']}
    assert {'C00001', 'C00090'} <= sessions


def test_original_bad_rows_are_retained(base):
    receipt, effective, _ = plan(base, package_bytes('repair_partial'))
    superseded = effective['repair']['superseded']
    assert superseded
    lines = {(row['session'], row['line']) for row in superseded}
    assert ('C00001', 45) in lines
    assert all(row['raw'] is not None for row in superseded)
    exported = evidence_csv([{'receipt': receipt}])
    assert 'C00001' in exported and 'C00090' in exported
    import csv as csv_module
    import io as io_module
    rows = list(csv_module.DictReader(io_module.StringIO(exported.lstrip('\ufeff'))))
    c1 = next(row for row in rows if row['session'] == 'C00001')
    superseded_raw = json.loads(c1['superseded_raw'])
    assert superseded_raw and all(isinstance(item, dict) for item in superseded_raw)


def test_full_package_leaves_nothing_isolated(base):
    receipt, effective, _ = plan(base, package_bytes('repair_full'))
    assert receipt['decision'] == 'FULL_ADOPT'
    assert receipt['counts']['STILL_ISOLATED'] == 0
    assert effective['quarantine']['total'] == 0
    assert effective['reconcile']['balanced']


def test_replay_is_idempotent(client):
    first = client.post('/api/repairs', json={'sample': 'repair_partial'}).json()
    count = len(store.history())
    second = client.post('/api/repairs', json={'sample': 'repair_partial'}).json()
    assert len(store.history()) == count
    assert first['effective_run_id'] == second['effective_run_id']
    assert first['decision'] == second['decision']
    assert second['idempotent'] is True
    assert store.latest()['calculate']['total_fee'] == '16.40'


def test_retry_after_wait_adds_no_batch(client):
    count = len(store.history())
    first = client.post('/api/repairs', json={'sample': 'repair_waiting'}).json()
    assert first['decision'] == 'WAIT'
    assert len(store.history()) == count
    second = client.post('/api/repairs', json={'sample': 'repair_waiting'}).json()
    assert second['idempotent'] is True
    assert len(store.history()) == count


def test_failed_admission_keeps_old_version(client, monkeypatch):
    from app.modules.repair import service as repair_service
    before = store.latest()
    before_history = len(store.history())

    def boom(raw):
        raise RuleError('REPAIR_SOURCE', '模拟重放失败', 422)

    monkeypatch.setattr(repair_service, 'execute', boom)
    response = client.post('/api/repairs', json={'sample': 'repair_partial'})
    assert response.status_code == 422
    after = store.latest()
    assert after['manifest']['run_id'] == before['manifest']['run_id']
    assert after['version'] == before['version']
    assert len(store.history()) == before_history
    assert store.repairs() == []


def test_invalid_package_keeps_old_version(client):
    before = store.latest()
    response = client.post('/api/repairs', json={'csv_text': 'not,a,cdr,file'})
    assert response.status_code == 422
    assert response.json()['code'] == 'PACKAGE_FORMAT'
    assert store.latest()['manifest']['run_id'] == before['manifest']['run_id']
    assert store.repairs() == []


def test_original_file_as_package_waits(client):
    raw = sample_bytes().decode('utf-8-sig')
    response = client.post('/api/repairs', json={'csv_text': raw})
    assert response.status_code == 200
    assert response.json()['decision'] == 'WAIT'


def test_second_package_continues_same_root(client):
    first = client.post('/api/repairs', json={'sample': 'repair_partial'}).json()
    second = client.post('/api/repairs', json={'sample': 'repair_full'}).json()
    assert first['root_run_id'] == second['root_run_id']
    assert second['base_run_id'] == first['effective_run_id']
    ledger = store.repairs(first['root_run_id'])
    assert len(ledger) == 2


def test_batch_page_shows_sources(client):
    client.post('/api/repairs', json={'sample': 'repair_partial'})
    page = client.get('/batches').text
    for marker in ('repair --isolated', 'repair --repaired', 'repair --adopted',
                   '仍隔离', '已修复', '最终采用', '先接纳可确认会话'):
        assert marker in page
    assert 'C00001' in page and 'C00095' in page and 'package:' in page


def test_repair_audit_export(client):
    client.post('/api/repairs', json={'sample': 'repair_partial'})
    response = client.get('/api/repairs/export')
    assert response.status_code == 200
    assert response.text.startswith('﻿package_sha256')
    assert '仍' not in response.text.split('\n')[0]
    assert response.text.count('\n') > 1


def test_apply_replay_returns_stored_receipt(client, monkeypatch):
    first = client.post('/api/repairs', json={'sample': 'repair_partial'}).json()
    # Even if planning would now explode, a replay must return the stored receipt.
    monkeypatch.setattr('app.modules.repair.service.plan',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('no plan')))
    again = apply(store.latest(), package_bytes('repair_partial'))
    assert again['effective_run_id'] == first['effective_run_id']
    assert again['idempotent'] is True


def test_transaction_rolls_back_effective_run(client):
    """A ledger write failure must not leave a half-registered effective run."""
    before = store.latest()
    before_history = len(store.history())
    conn = store.connect()
    conn.execute("CREATE TRIGGER fail_repair BEFORE INSERT ON repairs "
                 "BEGIN SELECT RAISE(ABORT,'forced'); END")
    conn.commit()
    conn.close()
    import sqlite3
    try:
        with pytest.raises(sqlite3.IntegrityError):
            client.post('/api/repairs', json={'sample': 'repair_partial'})
    finally:
        conn = store.connect()
        conn.execute('DROP TRIGGER fail_repair')
        conn.commit()
        conn.close()
    assert store.latest()['manifest']['run_id'] == before['manifest']['run_id']
    assert len(store.history()) == before_history
    assert store.repairs() == []
    # Retrying after the failure must now succeed and register exactly one batch.
    retried = client.post('/api/repairs', json={'sample': 'repair_partial'}).json()
    assert retried['decision'] == 'PARTIAL_ADOPT'
    assert len(store.history()) == before_history + 1


def test_wait_after_adoption_shows_latest_isolated(client):
    client.post('/api/repairs', json={'sample': 'repair_partial'})
    waited = client.post('/api/repairs', json={'sample': 'repair_waiting'}).json()
    assert waited['decision'] == 'WAIT'
    page = client.get('/batches').text
    assert waited['decision_label'] in page
    assert '[WAIT]' in page
    assert 'C00001' in page
    assert len(store.history()) == 2


def test_alias_endpoints(client):
    first = client.post('/api/batches/repair', json={'sample': 'repair_partial'}).json()
    assert first['decision'] == 'PARTIAL_ADOPT'
    listing = client.get('/api/repair').json()
    assert listing and listing[0]['decision'] == 'PARTIAL_ADOPT'
    replay = client.post('/api/repair', json={'sample': 'repair_partial'}).json()
    assert replay['idempotent'] is True
    assert len(store.history()) == 2
