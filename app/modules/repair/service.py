"""Supplier repair-package intake and per-session adoption.

Decision recorded here (mirrored in docs/DEPTH.md):

* A repair package is evaluated **per session**, never by replaying it wholesale.
  Only sessions that were isolated in the base batch are candidates.  A package
  row for an already-correct session is recorded as evidence and ignored, so a
  replay cannot perturb a bill that was already right.
* For a candidate session the package rows are merged with the base's rows for
  that same session, keyed by ``sequence``.  A package row replaces the base row
  at the same key, so a reissue can both *add* a missing fragment and *correct*
  a conflicting one.  The merged set is adopted only when it validates as one
  complete, internally consistent session (contract, stitch and tariff rules).
  Rows are never mixed piecemeal across sessions, which is what would let two
  sources inside one batch contradict each other.
* The package is **not held back** waiting for missing sessions: confirmable
  sessions are adopted now (PARTIAL_ADOPT) while unresolved ones keep their
  original rows and reasons.  A package with nothing confirmable is recorded as
  WAIT and creates no new batch at all.
* Registration is content-addressed by (root batch, package sha256).  Retrying
  the same bytes returns the stored receipt and never appends a batch or moves
  the version -- even if other packages were adopted in between.
* The effective batch is computed in memory first and written together with its
  ledger receipt in one transaction.  Any failure leaves the previous version
  untouched.  Every superseded original row is copied verbatim into the repair
  audit, so the original bad records are never lost even though the settlement
  view moves on.
"""

import csv
import hashlib
import io
import json
import time
from collections import defaultdict

from app import store
from app.config import SAMPLES
from app.errors import RuleError
from app.modules.calculate.service import calculate
from app.modules.contract.service import normalize
from app.modules.intake.reader import COLUMNS
from app.modules.intake.service import ingest
from app.modules.model.service import assemble
from app.pipeline import execute
from app.reasons import REASONS

PACKAGE_SAMPLES = ('repair_partial', 'repair_waiting', 'repair_full')

STATUS_LABELS = {
    'REPAIRED': '已修复',
    'STILL_ISOLATED': '仍隔离',
    'AWAITING_PACKAGE': '待补齐',
    'PROTECTED': '已正确未改动',
    'UNKNOWN_SESSION': '来源外会话',
}
DECISION_LABELS = {
    'FULL_ADOPT': '整包补齐，全部接纳',
    'PARTIAL_ADOPT': '先接纳可确认会话',
    'WAIT': '整包等待补齐',
}
REASON_LABELS = dict(REASONS, ALREADY_CORRECT='会话已正确', NO_PACKAGE_ROWS='修复包尚未补回该会话',
                     UNKNOWN_SESSION='基础批次没有该会话')
STATUS_ORDER = ('REPAIRED', 'STILL_ISOLATED', 'AWAITING_PACKAGE', 'PROTECTED', 'UNKNOWN_SESSION')


def package_bytes(name):
    if name not in PACKAGE_SAMPLES:
        raise RuleError('SAMPLE', '修复包样例不存在', 404)
    return (SAMPLES / (name + '.csv')).read_bytes()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _session_of(raw):
    if isinstance(raw, dict):
        value = raw.get('session')
    elif isinstance(raw, list) and len(raw) > 1:
        value = raw[1]
    else:
        value = None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _fields_of(raw):
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, dict) and all(key in raw for key in COLUMNS):
        return [raw[key] for key in COLUMNS]
    return None


def _base_records(bundle):
    """Every non-blank physical row of the base batch, one entry each."""
    records = []
    for row in bundle['intake']['rows']:
        records.append({'line': row['line'], 'raw': row,
                        'origin': row.get('origin') or 'root:%s' % row['line']})
    for issue in bundle['intake']['issues']:
        records.append({'line': issue['line'], 'raw': issue.get('raw'),
                        'origin': issue.get('origin') or 'root:%s' % issue['line']})
    records.sort(key=lambda item: item['line'])
    return records


def _package_records(raw, tariffs):
    """Parse a package into per-session entries plus unattributable rows."""
    try:
        parsed = ingest(raw)
    except RuleError as error:
        raise RuleError('PACKAGE_FORMAT', '修复包无法解析：%s' % error.message, 422) from error
    if parsed['state'] != 'READY':
        raise RuleError('PACKAGE_EMPTY', '修复包中没有可接纳的话单', 422)
    contract = normalize(parsed['rows'], tariffs)
    valid = {row['line']: row for row in contract['rows']}
    invalid = {issue['line']: issue['code'] for issue in contract['issues']}
    by_session, unattributed = defaultdict(list), []
    for row in parsed['rows']:
        entry = {'line': row['line'], 'raw': row, 'valid': valid.get(row['line']),
                 'code': invalid.get(row['line'])}
        session = _session_of(row)
        if session:
            by_session[session].append(entry)
        else:
            unattributed.append(dict(entry, session=None, code=entry['code'] or 'MISSING'))
    for issue in parsed['issues']:
        entry = {'line': issue['line'], 'raw': issue.get('raw'), 'valid': None,
                 'code': issue['code']}
        session = _session_of(issue.get('raw'))
        if session:
            by_session[session].append(entry)
        else:
            unattributed.append(dict(entry, session=None))
    return parsed, by_session, unattributed


def _merge_session(base_rows, entries, tariffs):
    """Merge package rows over base rows at the same sequence key.

    ``base_rows`` are normalised contract rows for this session from the base
    batch.  Returns ``(problem, chosen)`` where ``chosen`` is a list of
    ``{'row', 'origin', 'fields'}`` ready to be assembled and emitted.
    """
    for entry in entries:
        if entry['code']:
            return entry['code'], None
    base_by_seq = defaultdict(list)
    for row in base_rows:
        base_by_seq[row['sequence']].append({'row': row, 'origin': row['_origin']})
    package_by_seq = defaultdict(list)
    for entry in entries:
        package_by_seq[entry['valid']['sequence']].append(
            {'row': entry['valid'], 'origin': 'package:%s' % entry['line'],
             'fields': entry['raw'] and _fields_of(entry['raw'])})
    chosen = []
    for seq in sorted(set(base_by_seq) | set(package_by_seq)):
        pool = package_by_seq.get(seq) or base_by_seq[seq]
        spans = {(item['row']['start'], item['row']['end']) for item in pool}
        if len(spans) > 1:
            return 'CONFLICT', None
        winner = min(pool, key=lambda item: item['row']['line'])
        chosen.append({'row': winner['row'], 'origin': winner['origin'],
                       'fields': winner.get('fields')})
    if not chosen:
        return 'SEQUENCE', None
    built = assemble([item['row'] for item in chosen])
    if len(built['sessions']) != 1 or any(issue['code'] != 'DUPLICATE' for issue in built['issues']):
        fatal = next((issue['code'] for issue in built['issues'] if issue['code'] != 'DUPLICATE'),
                     'SEQUENCE')
        return fatal, None
    billed = calculate(built['sessions'], tariffs)
    if billed['issues'] or len(billed['rows']) != 1:
        return (billed['issues'][0]['code'] if billed['issues'] else 'TARIFF'), None
    return None, (chosen, built['sessions'][0], billed['rows'][0])



def _assert_stable(base, effective, dispositions, repaired):
    """Replaying the merged view must reproduce every disposition exactly.

    Already-correct sessions keep their fee and sources; newly repaired sessions
    appear with the fee predicted for them.  If the merge were not session-atomic
    this assertion trips and the whole package is refused before anything is
    written, so a partially applied source set can never reach a batch.
    """
    before = {row['session']: row for row in base['calculate']['rows']}
    after = {row['session']: row for row in effective['calculate']['rows']}
    for session, row in before.items():
        if session in repaired:
            continue
        # Every session that was not explicitly repaired must bill exactly as
        # before.  This is the invariant a wholesale replay would violate.
        if session not in after or after[session]['fee'] != row['fee']:
            raise RuleError('REPAIR_STABLE', '修复包会改变已确认会话，已拒绝整包', 409)
    for item in dispositions:
        session = item['session']
        if item['status'] in ('PROTECTED', 'AWAITING_PACKAGE', 'STILL_ISOLATED'):
            if session in before and (session not in after or
                                      after[session]['fee'] != before[session]['fee']):
                raise RuleError('REPAIR_STABLE', '修复包会改变已确认会话，已拒绝整包', 409)
            if item['status'] == 'PROTECTED' and session not in after:
                raise RuleError('REPAIR_STABLE', '修复包会移除已确认会话，已拒绝整包', 409)
            if item['status'] in ('STILL_ISOLATED', 'AWAITING_PACKAGE') and session in after:
                raise RuleError('REPAIR_STABLE', '隔离会话未被完整修复却被计入，已拒绝整包', 409)
        if item['status'] == 'REPAIRED':
            if session not in after:
                raise RuleError('REPAIR_STABLE', '已接纳会话未出现在结果中，已拒绝整包', 409)
            if after[session]['fee'] != item['fee_after']:
                raise RuleError('REPAIR_STABLE', '修复费用与预检不一致，已拒绝整包', 409)
    for session in after:
        if session in repaired:
            continue
        if session not in before:
            raise RuleError('REPAIR_STABLE', '修复包引入了基础批次外的会话，已拒绝整包', 409)


def _to_csv(rows):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode('utf-8')


def _annotate(bundle, line_origins):
    for row in bundle['intake']['rows']:
        row['origin'] = line_origins.get(row['line'], 'run:%s' % row['line'])
    for issue in bundle['intake']['issues']:
        issue['origin'] = line_origins.get(issue['line'], 'run:%s' % issue['line'])
    for issue in bundle['contract']['issues']:
        issue['origin'] = line_origins.get(issue['line'])
    for issue in bundle['model']['issues']:
        if isinstance(issue.get('raw'), dict):
            issue['raw']['origin'] = line_origins.get(issue['line'])
    for session in bundle['model']['sessions']:
        session['source_origins'] = [line_origins.get(line, 'run:%s' % line)
                                     for line in session['sources']]
    for row in bundle['calculate']['rows']:
        row['source_origins'] = [line_origins.get(line, 'run:%s' % line)
                                 for line in row['sources']]
    for row in bundle['reconcile']['rows']:
        evidence = row.get('evidence') or {}
        evidence['source_origins'] = [line_origins.get(line, 'run:%s' % line)
                                      for line in evidence.get('sources', [])]


def plan(base, raw):
    """Build the effective batch and receipt without writing anything."""
    package_sha = digest(raw)
    root_id = base.get('root_run_id') or base['manifest']['run_id']
    base_id = base['manifest']['run_id']
    tariffs = base['contract']['tariffs']
    parsed, package_by_session, unattributed = _package_records(raw, tariffs)

    records = _base_records(base)
    origin_by_line = {record['line']: record['origin'] for record in records}
    base_records_by_session = defaultdict(list)
    for record in records:
        session = _session_of(record['raw'])
        if session:
            base_records_by_session[session].append(record)
    base_valid_by_session = defaultdict(list)
    for row in base['contract']['rows']:
        base_valid_by_session[row['session']].append(dict(row, _origin=origin_by_line.get(row['line'], 'root:%s' % row['line'])))
    # Rows that failed normalisation cannot be addressed by sequence.  When a
    # session has both usable and unusable original rows, no reissue can be
    # proven to account for the unusable one, so the session must stay isolated.
    # When *none* of its original rows are usable, the supplier's complete,
    # contiguous reissue is authoritative for the session.
    base_barrier_by_session = defaultdict(list)
    for issue in base['contract']['issues']:
        session = _session_of(issue.get('raw'))
        if session:
            base_barrier_by_session[session].append(issue['code'])
    for issue in base['intake']['issues']:
        session = _session_of(issue.get('raw'))
        if session:
            base_barrier_by_session[session].append(issue['code'])
    # "Accepted" means it actually bills.  A session that stitched but was then
    # isolated by a tariff problem still needs the normal candidate path.
    before_rows = {row['session']: row for row in base['calculate']['rows']}
    accepted = set(before_rows)
    base_sessions = set(base_records_by_session)

    repaired, dispositions, superseded, ignored = {}, [], [], []
    for session in sorted(base_sessions | set(package_by_session)):
        entries = package_by_session.get(session, [])
        base_lines = [record['line'] for record in base_records_by_session.get(session, [])]
        base_origins = [origin_by_line.get(line, 'base:%s' % line) for line in base_lines]
        package_lines = [entry['line'] for entry in entries]
        package_origins = ['package:%s' % line for line in package_lines]
        if session in accepted:
            if entries:
                # A reissue for a session that already bills correctly must not
                # perturb it.  Record what the package would have produced so
                # the batch page can show the discrepancy without adopting it.
                problem, fixed = _merge_session(
                    base_valid_by_session.get(session, []), entries, tariffs)
                package_fee = fixed[2]['fee'] if fixed else None
                item = _disposition(
                    session, 'PROTECTED', 'ALREADY_CORRECT', base_lines, package_lines,
                    before_rows.get(session), before_rows.get(session), base_origins,
                    base_sources=base_origins, package_sources=package_origins,
                    package_fee=package_fee)
                item['package_conflict'] = problem or None
                item['package_differs'] = (
                    package_fee is not None and package_fee != item['fee_before'])
                dispositions.append(item)
                ignored.extend({'session': session, 'origin': origin, 'line': entry['line'],
                                'raw': entry['raw'], 'note': '会话已正确，修复包未采纳'}
                               for entry, origin in zip(entries, package_origins))
            continue
        if not entries:
            dispositions.append(_disposition(
                session, 'AWAITING_PACKAGE', 'NO_PACKAGE_ROWS', base_lines, [],
                before_rows.get(session), None, base_origins, base_sources=base_origins))
            continue
        if session not in base_sessions:
            dispositions.append(_disposition(
                session, 'UNKNOWN_SESSION', 'UNKNOWN_SESSION', [], package_lines,
                None, None, [], package_sources=package_origins))
            ignored.extend({'session': session, 'origin': origin, 'line': entry['line'],
                            'raw': entry['raw'], 'note': '基础批次没有该会话，未自动新增'}
                           for entry, origin in zip(entries, package_origins))
            continue
        usable = base_valid_by_session.get(session, [])
        barriers = base_barrier_by_session.get(session, [])
        if usable and barriers:
            # Some original rows for this session are unkeyable.  Merging the
            # package over the usable remainder could silently drop them, so the
            # session is never repaired automatically; it keeps its row-level
            # reasons until the supplier reissues the whole session cleanly.
            problem = barriers[0]
            dispositions.append(_disposition(
                session, 'STILL_ISOLATED', problem, base_lines, package_lines,
                before_rows.get(session), None, base_origins,
                package_sources=package_origins, base_sources=base_origins))
            ignored.extend({'session': session, 'origin': origin, 'line': entry['line'],
                            'raw': entry['raw'],
                            'note': '原始行存在无法定位的%s，需整会话重发' % REASON_LABELS.get(problem, problem)}
                           for entry, origin in zip(entries, package_origins))
            continue
        problem, fixed = _merge_session(usable, entries, tariffs)
        if problem is None:
            chosen, assembled, billed = fixed
            repaired[session] = chosen
            kept = {item['origin'] for item in chosen}
            dropped = [record for record in base_records_by_session[session]
                       if record['origin'] not in kept]
            dispositions.append(_disposition(
                session, 'REPAIRED', None, base_lines, package_lines,
                before_rows.get(session), billed, [item['origin'] for item in chosen],
                package_sources=package_origins, base_sources=base_origins,
                replaced_lines=[record['line'] for record in dropped],
                retained_lines=[record['line'] for record in base_records_by_session[session]
                                if record['origin'] in kept]))
            # Superseded originals are copied verbatim into the audit so the bad
            # records survive in full even though the settlement view moves on.
            superseded.extend({'session': session, 'origin': record['origin'],
                               'line': record['line'], 'raw': record['raw']}
                              for record in dropped)
            unused = {source for source in package_origins
                      if source not in {item['origin'] for item in chosen}}
            ignored.extend({'session': session, 'origin': entry_origin,
                            'line': entry['line'], 'raw': entry['raw'],
                            'note': '包内重复行未采用'}
                           for entry, entry_origin in zip(entries, package_origins)
                           if entry_origin in unused)
        else:
            dispositions.append(_disposition(
                session, 'STILL_ISOLATED', problem, base_lines, package_lines,
                before_rows.get(session), None, base_origins,
                package_sources=package_origins, base_sources=base_origins))
            ignored.extend({'session': session, 'origin': origin, 'line': entry['line'],
                            'raw': entry['raw'],
                            'note': '修复包内该会话仍存在%s' % REASON_LABELS.get(problem, problem)}
                           for entry, origin in zip(entries, package_origins))

    counts = {status: sum(item['status'] == status for item in dispositions)
              for status in STATUS_ORDER}
    if counts['REPAIRED'] == 0:
        decision = 'WAIT'
    elif counts['STILL_ISOLATED'] or counts['AWAITING_PACKAGE'] or counts['UNKNOWN_SESSION']:
        decision = 'PARTIAL_ADOPT'
    else:
        decision = 'FULL_ADOPT'

    receipt = {
        'package_sha256': package_sha,
        'root_run_id': root_id,
        'base_run_id': base_id,
        'effective_run_id': None,
        'decision': decision,
        'decision_label': DECISION_LABELS[decision],
        'policy': 'ADOPT_CONFIRMED_FIRST',
        'counts': counts,
        'sessions': dispositions,
        'package': {'input': parsed['input'], 'blank': parsed['blank'],
                    'encoding': parsed['encoding'], 'headers': parsed['headers']},
        'unattributed': [{'line': item['line'], 'code': item['code'] or 'COLUMN_COUNT',
                          'raw': item['raw']} for item in unattributed],
        'created': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    if decision == 'WAIT':
        receipt['note'] = '无可确认会话，整包等待补齐，未生成新批次'
        receipt['effective_run_id'] = base_id
        receipt['superseded'] = []
        receipt['ignored_package_rows'] = ignored
        receipt['retained_isolated'] = [item['session'] for item in dispositions
                                        if item['status'] in ('STILL_ISOLATED', 'AWAITING_PACKAGE')]
        return receipt, None, base_id

    emitted, origins = [], []
    for record in records:
        if _session_of(record['raw']) in repaired:
            continue
        fields = _fields_of(record['raw'])
        if fields is None:
            raise RuleError('REPAIR_SOURCE', '原始话单无法重放，请保留旧版并人工核对', 422)
        emitted.append(fields)
        origins.append(record['origin'])
    for session in sorted(repaired):
        for item in repaired[session]:
            fields = item.get('fields') or _fields_of(item['row'])
            if fields is None:
                raise RuleError('REPAIR_SOURCE', '修复包话单无法重放，请保留旧版并人工核对', 422)
            emitted.append(fields)
            origins.append(item['origin'])
    if any(fields == COLUMNS for fields in emitted):
        raise RuleError('REPAIR_FORMAT', '话单含与表头相同的记录，无法保留来源', 422)

    effective = execute(_to_csv(emitted))
    physical = sorted(list(effective['intake']['rows']) + list(effective['intake']['issues']),
                      key=lambda item: item['line'])
    if len(physical) != len(emitted):
        raise RuleError('REPAIR_SOURCE', '话单来源映射失败，请保留旧版后重试', 422)
    line_origins = {record['line']: origin for record, origin in zip(physical, origins)}
    _annotate(effective, line_origins)
    _assert_stable(base, effective, dispositions, repaired)
    receipt['effective_run_id'] = effective['manifest']['run_id']
    receipt['line_origins'] = {str(line): origin for line, origin in line_origins.items()}
    prior = (base.get('repair') or {}).get('superseded', [])
    receipt['superseded'] = prior + superseded
    receipt['ignored_package_rows'] = ignored
    receipt['retained_isolated'] = [item['session'] for item in dispositions
                                    if item['status'] in ('STILL_ISOLATED', 'AWAITING_PACKAGE')]
    effective['root_run_id'] = root_id
    effective['repair'] = receipt
    return receipt, effective, effective['manifest']['run_id']


def _disposition(session, status, reason, base_lines, package_lines,
                 before, after, final_sources, base_sources=(), package_sources=(),
                 replaced_lines=(), retained_lines=(), package_fee=None):
    return {
        'session': session,
        'status': status,
        'status_label': STATUS_LABELS[status],
        'reason': reason,
        'reason_label': REASON_LABELS.get(reason, reason or ''),
        'base_lines': sorted(base_lines),
        'package_lines': sorted(package_lines),
        'final_sources': list(final_sources),
        'base_sources': list(base_sources),
        'package_sources': list(package_sources),
        'replaced_lines': sorted(replaced_lines),
        'retained_lines': sorted(retained_lines),
        'package_fee': package_fee,
        'fee_before': None if before is None else before.get('fee'),
        'fee_after': None if after is None else after.get('fee'),
        'minutes_before': None if before is None else before.get('billed_minutes'),
        'minutes_after': None if after is None else after.get('billed_minutes'),
    }


def apply(base, raw):
    """Plan then persist one package; returns the stored receipt.

    The ledger is consulted before planning so a replay returns the original
    receipt byte-for-byte even if the current head would evaluate differently.
    """
    root_id = base.get('root_run_id') or base['manifest']['run_id']
    existing = store.find_repair(root_id, digest(raw))
    if existing:
        return existing
    receipt, effective, effective_id = plan(base, raw)
    return store.register_repair(
        receipt['root_run_id'], receipt['base_run_id'], receipt['package_sha256'],
        effective_id, effective, receipt)


def evidence_csv(receipts):
    """Audit export: one row per disposition, with the original source rows.

    The export is generated from the same stored receipts the batch page shows,
    and superseded originals are embedded verbatim, so archiving the audit never
    drops the bad records it replaced.
    """
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(['package_sha256', 'root_run_id', 'base_run_id', 'effective_run_id',
                     'decision', 'session', 'status', 'reason', 'base_lines',
                     'package_lines', 'replaced_lines', 'fee_before', 'fee_after',
                     'superseded_raw'])
    for item in receipts:
        receipt = item.get('receipt', item)
        superseded = {}
        for record in receipt.get('superseded', []):
            superseded.setdefault(record['session'], []).append(record['raw'])
        for row in receipt.get('sessions', []):
            writer.writerow([
                receipt.get('package_sha256'), receipt.get('root_run_id'),
                receipt.get('base_run_id'), receipt.get('effective_run_id'),
                receipt.get('decision'), row['session'], row['status'],
                row.get('reason') or '', ' '.join(map(str, row.get('base_lines', []))),
                ' '.join(map(str, row.get('package_lines', []))),
                ' '.join(map(str, row.get('replaced_lines', []))),
                row.get('fee_before'), row.get('fee_after'),
                json.dumps(superseded.get(row['session'], []), ensure_ascii=False)])
    return '﻿' + buffer.getvalue()
