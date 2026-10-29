"""Canonical read receipts, independent of display history and root membership.

Receipts cover exact substantive entity versions. Moving an entity between roots
does not erase its receipt; new members and changed substance have no receipt.
Temporary deferrals retain their existing interval semantics, including when new
activity arrives, until that separate owner policy is changed.
"""
import hashlib
import json
import threading
import weakref
from collections import OrderedDict
from datetime import datetime


def _pick(row, fields):
    return {key: row.get(key) for key in fields}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


# WHAT IS NEWS, AND WHAT IS ONLY WRITTEN DOWN ABOUT IT. A receipt hashed every column a row had, so Taskuary's own later
# writes made a read row a different row and brought it back unread with nothing new in it (the owner, 2026-10-29: ~400 read
# items back at once). Each was bookkeeping: a WhatsApp group's older messages given the group's name (SourceName), a
# sender named from the address book (FromName), a calendar verdict or an unsubscribe stamped into MailMetaJson, a report's
# spreadsheet and chart filed a second after the report was read (attachments, and Path is only where a file is kept), a
# profile renamed under every note and run it wrote (Actor, AgentName - and the rows sorted by the whole row, so the rename
# reordered them too), workflow tags (interrupted, reply-owed), and the Assistant's own "Next up" / "Opened" under the task.
# News is what the sender or the agent SAID: the words, who it came from and when, and what was asked.
MESSAGE_SUBSTANCE = ('ExternalId', 'ConversationId', 'Channel', 'Subject', 'FromEmail', 'SentAt', 'BodyText',
                     'SourceLink', 'Direction', 'RecipientsJson')
_OLD_MESSAGE = ('ExternalId', 'ConversationId', 'Channel', 'SourceName', 'Subject', 'FromName', 'FromEmail', 'SentAt',
                'BodyText', 'SourceLink', 'Direction', 'RecipientsJson', 'MailMetaJson')
_OLD_ATTACHMENT = ('AttachmentId', 'ExternalId', 'Name', 'ContentType', 'Size', 'ContentId', 'Inline', 'Path')


def _said(comments, talk):
    """The notes that are news, in the order they were written - never the Assistant's talk about the task (`talk`: its own
    words, and the owner's to it), which processing_own_words already treats as no news when it can catch it."""
    return [_pick(c, ('CommentId', 'Body')) for c in sorted(comments, key=lambda c: c.get('CommentId') or 0)
            if c.get('ActorType') not in talk]


def _was(rows, col, back):
    """`rows` as they read before a profile was renamed (`back`: its name now -> then), in the order the projection sorted them then."""
    from .processing_projection import _row_order
    return _row_order([{**r, col: back[r[col]]} if r.get(col) in back else r for r in rows]) \
        if any(r.get(col) in back for r in rows) else None


def _old_task(row, checklist, comments, artifacts):
    s = _pick(row, ('Title', 'Summary', 'Kind', 'Tags'))
    return {**s, 'checklist': checklist, 'artifacts': artifacts,
            'comments': [_pick(c, ('CommentId', 'Actor', 'ActorType', 'Body')) for c in comments]}


def units(view):
    """Read-bearing members; drafts, priority and processing status are not substance. `also`: the fingerprints a receipt
    written before this formula, or before one of Taskuary's own rewrites of the row, was hashed under - it still counts."""
    owned = set(view.get('member_ids', ()))
    result = []

    def add(kind, row, id_field, substance, *legacy):
        local_id = str(row[id_field])
        if f'{kind}:{local_id}' in owned:
            unit = dict(entity_kind=kind, local_id=local_id, fingerprint=fingerprint(substance))
            also = list(dict.fromkeys(f for f in map(fingerprint, (l for l in legacy if l is not None)) if f != unit['fingerprint']))
            if also: unit['also'] = also
            result.append(unit)

    from .agents import RENAMED
    from .concierge import DISCUSSION_ASSISTANT_TYPE, DISCUSSION_USER_TYPE
    from .messengers import GROUP_CHAT
    back, talk = {new: old for old, new in RENAMED.items()}, (DISCUSSION_ASSISTANT_TYPE, DISCUSSION_USER_TYPE)
    for row in view.get('messages', ()):
        # History/context remains available in details, not an independent arrival.
        if row.get('Status') in ('context', 'history', 'skipped', 'autoreply') or row.get('Status') is None:
            continue
        old = _pick(row, _OLD_MESSAGE)
        old['attachments'] = [_pick(a, _OLD_ATTACHMENT) for a in view.get('attachments', ()) if a.get('MessageId') == row['MessageId']]
        add('message', row, 'MessageId', _pick(row, MESSAGE_SUBSTANCE), old,
            {**old, 'attachments': []} if old['attachments'] else None,            # read before its files were filed
            {**old, 'SourceName': GROUP_CHAT} if row.get('Channel') == 'whatsapp' and row.get('SourceName') != GROUP_CHAT else None)
    for row in view.get('tasks', ()):
        checklist = row.get('Checklist')
        try:
            checklist = json.loads(checklist) if isinstance(checklist, str) else checklist
        except ValueError:
            pass
        # A checkbox is workflow state; changing the requested text is new substance.
        checklist = ([_pick(x, ('id', 'text')) if isinstance(x, dict) else x
                      for x in checklist] if isinstance(checklist, list) else checklist)
        notes = [c for c in view.get('comments', ()) if c.get('TaskId') == row['TaskId']]
        files = [a for a in view.get('artifacts', ()) if a.get('TaskId') == row['TaskId']]
        old_files = [_pick(a, ('ArtifactId', 'Name', 'ContentType', 'Size', 'Path', 'Kind')) for a in files]
        renamed = _was(notes, 'Actor', back)
        add('task', row, 'TaskId', {**_pick(row, ('Title', 'Summary', 'Kind')), 'checklist': checklist, 'comments': _said(notes, talk),
            'artifacts': [_pick(a, ('ArtifactId', 'Name', 'ContentType', 'Size', 'Kind')) for a in sorted(files, key=lambda a: a.get('ArtifactId') or 0)]},
            _old_task(row, checklist, notes, old_files), renamed and _old_task(row, checklist, renamed, old_files))
    for row in view.get('ideas', ()):
        substance, legacy = _pick(row, ('Text', 'Kind', 'ActionJson', 'Sig')), None
        try: action = json.loads(substance['ActionJson'])
        except (ValueError, TypeError): action = None
        if isinstance(action, dict):
            # Triage's verdict, and the task it linked, are bookkeeping ABOUT the idea: a failed verdict retried hours
            # later wrote intent/kind/why/at/linked_task and brought an idea the owner had read back unread, with
            # nothing new in it to read. Only the idea's own words and facts are news.
            substance['ActionJson'] = {k: v for k, v in action.items() if k not in ('triage', 'tid')}
            # ...and a receipt written before this (verdict hashed in, only the failure's own keys out) still counts
            tri = action.get('triage')
            legacy = {**substance, 'ActionJson': {**action, 'triage': {k: v for k, v in tri.items() if k not in ('priority', 'pending', 'error')}}
                      if isinstance(tri, dict) else action}
        add('idea', row, 'IdeaId', substance, legacy)
    for row in view.get('reviews', ()):
        add('review', row, 'ReviewId', _pick(row, ('Kind', 'CreatedAt', 'RunId')))
    runs = view.get('runs', ())
    renamed = {r['RunId']: r for r in _was(runs, 'AgentName', back) or ()}
    for row in runs:
        old = _pick(row, ('AgentName', 'Instruction', 'StartedAt', 'Result', 'DiffText', 'LastError'))
        # the profile a run went under is its label, not what it did
        add('run', row, 'RunId', {k: v for k, v in old.items() if k != 'AgentName'}, old,
            {**old, 'AgentName': renamed[row['RunId']]['AgentName']} if row['RunId'] in renamed else None)
    return sorted(result, key=lambda x: (x['entity_kind'], x['local_id']))


# WHAT EACH CARD SHOWED, by the revision it was drawn at. A press of Done or Next puts down what the card showed; the
# receipt used to be written off a fresh projection at the moment of the press, so a mail that landed after the card was
# drawn was marked read unseen. Entities, not fingerprints: the owner's own words on the card (the chat's comment on the
# task) change the task's fingerprint, and Done on it must still put it down. Kept in memory - a draw is a read and must not write - so after a restart a revision
# nobody drew since falls back to the item as it stands, which is what every press did before.
_DRAWN, _DRAWN_LOCK, DRAWN_CAP = weakref.WeakKeyDictionary(), threading.Lock(), 5000


def _drawn(store):
    store = getattr(store, '_store', store)               # a poll worker's writer proxy is the same store
    if store not in _DRAWN: _DRAWN[store] = {'by': OrderedDict(), 'last': {}}
    return _DRAWN[store]


def drawn(store, item_id, view_revision, current):
    """A card for `item_id` was drawn at `view_revision`, showing these units."""
    if not item_id or not view_revision: return
    keep = frozenset((u['entity_kind'], u['local_id']) for u in current)
    with _DRAWN_LOCK:
        d = _drawn(store)
        d['by'][(item_id, view_revision)] = keep; d['by'].move_to_end((item_id, view_revision))
        d['last'][item_id] = view_revision
        while len(d['by']) > DRAWN_CAP: d['by'].popitem(last=False)


def shown_units(store, item_id, view_revision=None):
    """The (entity_kind, local_id) the card at `view_revision` showed - or, with none named, the card last drawn. None: never
    drawn here."""
    with _DRAWN_LOCK:
        d = _drawn(store)
        return d['by'].get((item_id, view_revision)) or d['by'].get((item_id, d['last'].get(item_id)))


def active_version(cur):
    row = cur.execute('''SELECT a.Version FROM processing_read_activation a
        JOIN processing_migration m ON m.Version=a.Version
        WHERE a.Singleton=1 AND m.Completion='complete' ''').fetchone()
    return row[0] if row else None


def project(cur, item_id, view, src=None):
    """Read using the caller's transaction; never materialize receipts on display. `src` is the projection's
    reader (processing_projection.Direct, or the cold build's bulk Prefetch)."""
    if src is None:
        from .processing_projection import Direct
        src = Direct(cur)
    version = src.read_version()
    current = units(view)
    for unit in current:
        # WHEN it was read, not just that it was: an open task nobody closed comes back to the work
        # tab once it has been quiet that long, and the receipt is the only record of when it went.
        # ...and when ANY version of it was last read: a finished agent result asks "read since the close?", and
        # a note filed after that read changes the fingerprint without making the result news again (TQ-0740)
        prints = [unit['fingerprint'], *unit.get('also', ())]
        unit['read_at'], unit['last_read_at'] = src.receipt(unit['entity_kind'], unit['local_id'], prints)
        unit['read'] = bool(unit['read_at'])
    # Root deferrals survive redirects. Exact legacy entity deferrals follow moves.
    deferrals = {row['Key']: row for row in src.root_deferrals(item_id)}
    for mid in view.get('member_ids', ()):
        kind, local_id = mid.split(':', 1)
        for row in src.entity_deferrals(kind, local_id): deferrals[row['Key']] = row
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
    stamps = [u['read_at'] for u in read.get('units', ()) if u.get('read_at')]
    seen = [u['last_read_at'] for u in read.get('units', ()) if u.get('last_read_at')]
    return dict(unread=any(not u.get('read') for u in read.get('units', ())),
                read_at=max(stamps, key=_time) if stamps else None,
                last_read_at=max(seen, key=_time) if seen else None,
                deferred=bool(active), defer_until=until)


def record(cur, current, *, version, at, by, origin):
    # A LOOK AGAIN MOVES THE CLOCK. The receipt is what "quiet since you last looked" reads (processing_unread `back`,
    # task_return_minutes), and it was INSERT OR IGNORE: reading the same content again recorded nothing, so an open task
    # first read more than three hours ago came straight back to On you every time Next put it down (the owner,
    # 2026-09-30: "i hit next why is this still showing in on you"). A later read now moves ReadAt forward - never back,
    # and compared as times, since an older receipt may be spelled with a T.
    for unit in current:
        cur.execute('''INSERT INTO processing_read_receipt
            (EntityKind,LocalId,Fingerprint,Version,ReadAt,ReadBy,Origin)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(EntityKind,LocalId,Fingerprint) DO UPDATE SET ReadAt=excluded.ReadAt, ReadBy=excluded.ReadBy
            WHERE julianday(excluded.ReadAt) > julianday(processing_read_receipt.ReadAt)''', (unit['entity_kind'], unit['local_id'],
            unit['fingerprint'], version, at, by, origin))


def legacy_verdicts(cur, version):
    return {r['LocalId']: bool(r['PermanentRead']) for r in cur.execute('''
        SELECT LocalId,PermanentRead FROM processing_legacy_evidence
        WHERE MigrationVersion=? AND EntityKind='message' AND PermanentRead IS NOT NULL''',
        (version,)).fetchall()}


def capture_legacy(cur, version, picture, *, at, verdicts=None):
    """Retain the frozen evaluator's permanent verdict, never the displayed state later."""
    # ONE READ PER MIGRATION. Every item re-read every verdict, so the cutover was O(N^2) and ran before the port opened:
    # a 2k-message home started in 156 s (perf report 2.4, 2026-10-19: "just make it feel snappy"). The verdicts are
    # written before the item loop and never change inside it, so the caller reads them once and passes them in.
    view = picture['view']
    if verdicts is None: verdicts = legacy_verdicts(cur, version)
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
