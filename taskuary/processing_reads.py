"""Canonical read receipts, independent of display history and root membership.

Receipts cover exact substantive entity versions. Moving an entity between roots
does not erase its receipt; new members and changed substance have no receipt.
Temporary deferrals retain their existing interval semantics, including when new
activity arrives, until that separate owner policy is changed.
"""
import hashlib
import json
from datetime import datetime


def _pick(row, fields):
    return {key: row.get(key) for key in fields}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def units(view):
    """Read-bearing members; drafts, priority and processing status are not substance."""
    owned = set(view.get('member_ids', ()))
    result = []

    def add(kind, row, id_field, substance):
        local_id = str(row[id_field])
        if f'{kind}:{local_id}' in owned:
            result.append(dict(entity_kind=kind, local_id=local_id,
                               fingerprint=fingerprint(substance)))

    for row in view.get('messages', ()):
        # History/context remains available in details, not an independent arrival.
        if row.get('Status') in ('context', 'history', 'skipped') or row.get('Status') is None:
            continue
        substance = _pick(row, ('ExternalId', 'ConversationId', 'Channel', 'SourceName',
            'Subject', 'FromName', 'FromEmail', 'SentAt', 'BodyText', 'SourceLink',
            'Direction', 'RecipientsJson', 'MailMetaJson'))
        substance['attachments'] = [_pick(a, ('AttachmentId', 'ExternalId', 'Name',
            'ContentType', 'Size', 'ContentId', 'Inline', 'Path'))
            for a in view.get('attachments', ()) if a.get('MessageId') == row['MessageId']]
        add('message', row, 'MessageId', substance)
    for row in view.get('tasks', ()):
        substance = _pick(row, ('Title', 'Summary', 'Kind', 'Tags'))
        checklist = row.get('Checklist')
        try:
            checklist = json.loads(checklist) if isinstance(checklist, str) else checklist
        except ValueError:
            pass
        # A checkbox is workflow state; changing the requested text is new substance.
        substance['checklist'] = ([_pick(x, ('id', 'text')) if isinstance(x, dict) else x
                                  for x in checklist] if isinstance(checklist, list) else checklist)
        substance['comments'] = [_pick(c, ('CommentId', 'Actor', 'ActorType', 'Body'))
            for c in view.get('comments', ()) if c.get('TaskId') == row['TaskId']]
        substance['artifacts'] = [_pick(a, ('ArtifactId', 'Name', 'ContentType', 'Size', 'Path', 'Kind'))
            for a in view.get('artifacts', ()) if a.get('TaskId') == row['TaskId']]
        add('task', row, 'TaskId', substance)
    for row in view.get('ideas', ()):
        substance = _pick(row, ('Text', 'Kind', 'ActionJson', 'Sig'))
        try:
            action = json.loads(substance['ActionJson'])
            if isinstance(action, dict) and isinstance(action.get('triage'), dict):
                action['triage'] = {k: v for k, v in action['triage'].items()
                                    if k not in ('priority', 'pending', 'error')}
            substance['ActionJson'] = action
        except (ValueError, TypeError):
            pass
        add('idea', row, 'IdeaId', substance)
    for row in view.get('reviews', ()):
        add('review', row, 'ReviewId', _pick(row, ('Kind', 'CreatedAt', 'RunId')))
    for row in view.get('runs', ()):
        add('run', row, 'RunId', _pick(row, ('AgentName', 'Instruction', 'StartedAt',
                                          'Result', 'DiffText', 'LastError')))
    return sorted(result, key=lambda x: (x['entity_kind'], x['local_id']))


def active_version(cur):
    row = cur.execute('''SELECT a.Version FROM processing_read_activation a
        JOIN processing_migration m ON m.Version=a.Version
        WHERE a.Singleton=1 AND m.Completion='complete' ''').fetchone()
    return row[0] if row else None


def project(cur, item_id, view):
    """Read using the caller's transaction; never materialize receipts on display."""
    version = active_version(cur)
    current = units(view)
    for unit in current:
        unit['read'] = bool(cur.execute('''SELECT 1 FROM processing_read_receipt
            WHERE EntityKind=? AND LocalId=? AND Fingerprint=?''',
            (unit['entity_kind'], unit['local_id'], unit['fingerprint'])).fetchone())
    # Root deferrals survive redirects. Exact legacy entity deferrals follow moves.
    deferrals = {row['Key']: dict(row) for row in cur.execute('''WITH RECURSIVE lineage(ItemId) AS (
        SELECT ? UNION SELECT p.ItemId FROM processing_item p JOIN lineage l
        ON p.RedirectItemId=l.ItemId)
        SELECT d.* FROM processing_read_defer d WHERE d.TargetItemId IN (SELECT ItemId FROM lineage)
        AND d.TargetEntityKind IS NULL''', (item_id,)).fetchall()}
    for mid in view.get('member_ids', ()):
        kind, local_id = mid.split(':', 1)
        for row in cur.execute('''SELECT * FROM processing_read_defer
            WHERE TargetEntityKind=? AND TargetLocalId=?''', (kind, local_id)).fetchall():
            deferrals[row['Key']] = dict(row)
    return dict(active=bool(version), version=version, units=current,
                deferrals=[dict(key=row['Key'], status=row['Status'], until=row['Until'],
                                at=row['At'], by=row['By'])
                           for _, row in sorted(deferrals.items())])


def _time(value):
    stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return stamp.astimezone().replace(tzinfo=None) if stamp.tzinfo else stamp


def state(item, now):
    """Return intrinsic unread and a separate temporary visibility deferral."""
    read = item.get('view', {}).get('processing_read', {})
    active = []
    clock = _time(now)
    for deferred in read.get('deferrals', ()):
        if deferred.get('status') not in ('later', 'skip'):
            continue
        until = deferred.get('until')
        try:
            applies = not until or _time(until) > clock
        except (TypeError, ValueError):
            # A malformed retained interval must not silently release owner deferral.
            applies = True
        if applies:
            active.append(deferred)
    deadlines = [d.get('until') for d in active]
    try:
        until = max(deadlines, key=_time) if deadlines and all(deadlines) else None
    except (TypeError, ValueError):
        until = None
    return dict(unread=any(not u.get('read') for u in read.get('units', ())),
                deferred=bool(active), defer_until=until)


def record(cur, current, *, version, at, by, origin):
    for unit in current:
        cur.execute('''INSERT OR IGNORE INTO processing_read_receipt
            (EntityKind,LocalId,Fingerprint,Version,ReadAt,ReadBy,Origin)
            VALUES (?,?,?,?,?,?,?)''', (unit['entity_kind'], unit['local_id'],
            unit['fingerprint'], version, at, by, origin))


def capture_legacy(cur, version, picture, *, at):
    """Retain the frozen evaluator's permanent verdict, never the displayed state later."""
    view = picture['view']
    verdicts = {r['LocalId']: bool(r['PermanentRead']) for r in cur.execute('''
        SELECT LocalId,PermanentRead FROM processing_legacy_evidence
        WHERE MigrationVersion=? AND EntityKind='message' AND PermanentRead IS NOT NULL''',
        (version,)).fetchall()}
    messages = [r for r in view['messages'] if str(r['MessageId']) in verdicts]
    task_rows = {str(r['TaskId']): r for r in view['tasks']}
    review_rows = {str(r['ReviewId']): r for r in view['reviews']}
    idea_rows = {str(r['IdeaId']): r for r in view['ideas']}
    run_rows = {str(r['RunId']): r for r in view['runs']}
    legacy = {}
    for alias in view['aliases']:
        if alias['Namespace'] != 'legacy_funnel' or alias['Scope'] != 'local':
            continue
        row = cur.execute('SELECT Status FROM funnel_state WHERE Key=?', (alias['Value'],)).fetchone()
        if row and row[0] in ('surfaced', 'done'):
            legacy[(alias['EntityKind'], alias['LocalId'])] = True
    selected = []
    for unit in units(view):
        kind, lid = unit['entity_kind'], unit['local_id']
        permanent = False
        if kind == 'message':
            permanent = verdicts.get(lid, False)
        elif kind == 'task':
            attached = [r for r in messages if str(r.get('TaskId')) == lid]
            permanent = (all(verdicts[str(r['MessageId'])] for r in attached) if attached else
                         legacy.get((kind, lid), False) or task_rows[lid].get('Status') in ('done', 'dropped'))
        elif kind == 'review':
            row = review_rows[lid]
            mid = str(row.get('MessageId'))
            permanent = (verdicts[mid] if mid in verdicts else
                         legacy.get((kind, lid), False) or row.get('Status') in ('approved', 'edited', 'sent', 'rejected'))
        elif kind == 'idea':
            permanent = legacy.get((kind, lid), False) or idea_rows[lid].get('Status') in ('done', 'dismissed')
        elif kind == 'run':
            tid = str(run_rows[lid].get('TaskId'))
            attached = [r for r in messages if str(r.get('TaskId')) == tid]
            permanent = (all(verdicts[str(r['MessageId'])] for r in attached) if attached else
                         legacy.get(('task', tid), False) or task_rows.get(tid, {}).get('Status') in ('done', 'dropped'))
        if permanent:
            selected.append(unit)
    record(cur, selected, version=version, at=at, by='legacy', origin='legacy_preserved')
    # Some assistant wrappers were temporarily hidden by an independent idea's
    # deferral. Preserve that exact source verdict without making it permanent or
    # adding a live cross-idea hiding rule after activation.
    for row in cur.execute('''SELECT LocalId,TemporaryDeferJson FROM processing_legacy_evidence
        WHERE MigrationVersion=? AND ItemId=? AND EntityKind='message'
          AND PermanentRead=0 AND ObservedUnread=0 AND TemporaryDeferJson IS NOT NULL''',
        (version, picture['item_id'])).fetchall():
        deferred = json.loads(row['TemporaryDeferJson'])
        if deferred.get('status') not in ('later', 'skip'):
            continue
        cur.execute('''INSERT OR IGNORE INTO processing_read_defer
            (Key,TargetItemId,TargetEntityKind,TargetLocalId,Status,Until,At,By)
            VALUES (?,?,'message',?,?,?,?,?)''',
            ('legacy-message:' + row['LocalId'], picture['item_id'], row['LocalId'],
             deferred['status'], deferred.get('until'), at, 'legacy'))
    for row in view['ideas']:
        if f"idea:{row['IdeaId']}" not in view['member_ids'] or row.get('Status') != 'snoozed':
            continue
        cur.execute('''INSERT OR IGNORE INTO processing_read_defer
            (Key,TargetItemId,TargetEntityKind,TargetLocalId,Status,Until,At,By)
            VALUES (?,?,'idea',?,'later',?,?,?)''', (f"idea:{row['IdeaId']}", picture['item_id'],
            str(row['IdeaId']), row.get('SnoozeUntil'), row.get('DecidedAt') or at, row.get('DecidedBy')))
