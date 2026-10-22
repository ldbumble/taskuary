"""Read a canonical foundation snapshot using a caller-owned SQLite transaction.

No identity allocation, historical inference, runtime worker access or writes happen
here. All consumes this projection; membership is reconciled explicitly by the
owned background lifecycle. Canonical Unread/read adoption remains separate.
"""
import copy
import json

from .processing import processing_context_revision, processing_view_revision


def _pick(row, fields):
    return {field: row[field] for field in fields if field in row}


def _worker_attention(row):
    # Elapsed idle seconds are a clock, not changed content. Preserve the
    # existing threshold-based waiting fact before removing that clock so a
    # real working/waiting transition still changes the view and selection.
    from .terminal import IDLE_WAITING
    row = dict(row)
    if row.get('waiting') is None:
        row['waiting'] = (row.get('idle') or 0) >= IDLE_WAITING
    row.pop('idle', None)
    return row


def _row_order(rows):
    return rows if len(rows) < 2 else sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))


def _rows_for(cur, table, column, ids):
    ids = sorted(set(ids), key=str)
    rows = []
    # Stay below older SQLite variable limits even for a large grouped item.
    for offset in range(0, len(ids), 400):
        part = ids[offset:offset + 400]
        rows.extend(dict(row) for row in cur.execute(
            f'SELECT * FROM {table} WHERE {column} IN ({",".join("?" for _ in part)})', part))
    return _row_order(rows)


_TRANSCRIPT = '''SELECT TaskId, Sid sid, Agent agent, Cwd cwd, CreatedAt at, LENGTH(IFNULL(Text,'')) chars FROM transcript'''
_SETTINGS = '''SELECT Name,Value FROM setting
    WHERE Name IN ('funnel_hours','funnel_mutes','feed_days','team_domains','owner_email') ORDER BY Name'''


class Direct:
    """The projection's reads for ONE item, a query each on the caller's transaction."""
    def __init__(self, cur): self.cur = cur

    def members(self, item_id):
        return [dict(row) for row in self.cur.execute('''SELECT * FROM processing_member
            WHERE ItemId=? AND RetiredAt IS NULL ORDER BY EntityKind,LocalId''', (item_id,))]

    def rows(self, table, column, ids): return _rows_for(self.cur, table, column, ids)

    def transcript(self, tid):
        row = self.cur.execute(_TRANSCRIPT + ' WHERE TaskId=? ORDER BY TranscriptId DESC LIMIT 1', (tid,)).fetchone()
        return dict(row) if row else None

    def relations(self, kind, local):
        return [dict(row) for row in self.cur.execute('''SELECT * FROM processing_relation WHERE RetiredAt IS NULL AND
            ((FromEntityKind=? AND FromLocalId=?) OR (ToEntityKind=? AND ToLocalId=?))''', (kind, local, kind, local))]

    def aliases(self, kind, local):
        return [dict(row) for row in self.cur.execute('''SELECT * FROM processing_alias
            WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL ORDER BY Namespace,Scope,Value''', (kind, local))]

    def lineage(self, item_id):
        """The item and every item redirected into it."""
        return [row[0] for row in self.cur.execute('''WITH RECURSIVE roots(id) AS (
            SELECT ItemId FROM processing_item WHERE ItemId=?
            UNION SELECT p.ItemId FROM processing_item p JOIN roots r ON p.RedirectItemId=r.id)
            SELECT id FROM roots''', (item_id,))]

    def settings(self): return {row['Name']: row['Value'] for row in self.cur.execute(_SETTINGS)}

    def report_failed(self, mid):
        run = self.cur.execute('SELECT Failed FROM report_run WHERE MessageId=? ORDER BY RunId DESC LIMIT 1', (mid,)).fetchone()
        return None if run is None else bool(run['Failed'])

    # ...and the read state's (processing_reads.project)
    def read_version(self):
        from .processing_reads import active_version
        return active_version(self.cur)

    def receipt(self, kind, local, prints):
        row = self.cur.execute(f'''SELECT MAX(CASE WHEN Fingerprint IN ({','.join('?' * len(prints))}) THEN ReadAt END) AS ReadAt,
            MAX(ReadAt) AS LastReadAt FROM processing_read_receipt WHERE EntityKind=? AND LocalId=?''',
            (*prints, kind, local)).fetchone()
        return (row['ReadAt'] or None, row['LastReadAt'] or None) if row else (None, None)

    def root_deferrals(self, item_id):
        return [dict(row) for row in self.cur.execute('''WITH RECURSIVE lineage(ItemId) AS (
            SELECT ? UNION SELECT p.ItemId FROM processing_item p JOIN lineage l
            ON p.RedirectItemId=l.ItemId)
            SELECT d.* FROM processing_read_defer d WHERE d.TargetItemId IN (SELECT ItemId FROM lineage)
            AND d.TargetEntityKind IS NULL''', (item_id,))]

    def entity_deferrals(self, kind, local):
        return [dict(row) for row in self.cur.execute('''SELECT * FROM processing_read_defer
            WHERE TargetEntityKind=? AND TargetLocalId=?''', (kind, local))]


class Prefetch(Direct):
    """The same reads for MANY roots, answered from a few bulk queries: the rail's cold build.

    That build projected every root with ~17 queries of its own - ~200,000 statements on a home of 12,000 items, and
    the first task list after a restart of the owner's took 71 s (2026-10-21). Every answer here is the one Direct gives:
    the same rows, grouped in Python, in the same order. Anything outside the roots it was made for is read directly."""
    def __init__(self, cur, lineage):
        super().__init__(cur)
        self._lineage = {r: list(ids) for r, ids in lineage.items()}
        self._members = {}
        for row in cur.execute('SELECT * FROM processing_member WHERE RetiredAt IS NULL ORDER BY ItemId,EntityKind,LocalId'):
            if row['ItemId'] in self._lineage: self._members.setdefault(row['ItemId'], []).append(dict(row))
        self._rel, self._alias = {}, {}
        for row in cur.execute('SELECT * FROM processing_relation WHERE RetiredAt IS NULL'):
            r = dict(row)
            for side in ('From', 'To'): self._rel.setdefault((r[f'{side}EntityKind'], r[f'{side}LocalId']), []).append(r)
        for row in cur.execute('SELECT * FROM processing_alias WHERE RetiredAt IS NULL ORDER BY Namespace,Scope,Value'):
            self._alias.setdefault((row['EntityKind'], row['LocalId']), []).append(dict(row))
        want = {}
        for ms in self._members.values():
            for m in ms: want.setdefault(m['EntityKind'], set()).add(m['LocalId'])
        msg, task = want.get('message', set()), want.get('task', set())
        ideas = want.get('idea', set()) | {r[f'{s}LocalId'] for rs in self._rel.values() for r in rs for s in ('From', 'To')
                                           if r[f'{s}EntityKind'] == 'idea'}
        keys = {a['Value'] for ms in self._members.values() for m in ms for a in self._alias.get((m['EntityKind'], m['LocalId']), ())
                if a['Namespace'] == 'legacy_funnel'} | {'processing:' + i for ids in self._lineage.values() for i in ids}
        # what each (table, column) is asked for across the build, loaded on its first ask
        self._universe = {('message', 'MessageId'): msg, ('task', 'TaskId'): task, ('attachment', 'MessageId'): msg,
                          ('route', 'MessageId'): msg, ('review', 'MessageId'): msg, ('review', 'TaskId'): task,
                          ('review', 'ReviewId'): want.get('review', set()), ('run', 'TaskId'): task,
                          ('comment', 'TaskId'): task, ('task_artifact', 'TaskId'): task, ('idea', 'IdeaId'): ideas,
                          ('funnel_state', 'Key'): keys, ('processing_display_summary', 'Key'): keys}
        self._idx, self._have = {}, {}
        self._tasks = {str(t) for t in task}
        self._tr = {}
        for part in _parts(sorted(self._tasks)):
            for row in cur.execute(_TRANSCRIPT + f' WHERE TaskId IN ({",".join("?" * len(part))}) ORDER BY TranscriptId DESC', part):
                self._tr.setdefault(str(row['TaskId']), dict(row))
        self._settings = Direct.settings(self)
        self._runs = self._receipts = self._defers = None
        self._version = Direct.read_version(self)

    def members(self, item_id):
        if item_id not in self._lineage: return Direct.members(self, item_id)
        return [dict(m) for m in self._members.get(item_id, ())]

    def _load(self, key, ids):
        idx, have = self._idx.setdefault(key, {}), self._have.setdefault(key, set())
        table, column = key
        for part in _parts(sorted({str(i) for i in ids} - have)):
            for row in self.cur.execute(f'SELECT * FROM {table} WHERE {column} IN ({",".join("?" * len(part))})', part):
                if row[column] is not None: idx.setdefault(str(row[column]), []).append(dict(row))
            have.update(part)
        return idx

    def rows(self, table, column, ids):
        key = (table, column)
        if key not in self._idx: self._load(key, self._universe.get(key, ()))
        ids = {str(i) for i in ids}
        idx = self._load(key, ids) if not ids <= self._have[key] else self._idx[key]
        return _row_order([dict(r) for i in ids for r in idx.get(i, ())])

    def transcript(self, tid):
        if str(tid) not in self._tasks: return Direct.transcript(self, tid)
        row = self._tr.get(str(tid))
        return dict(row) if row else None

    def relations(self, kind, local): return [dict(r) for r in self._rel.get((kind, local), ())]
    def aliases(self, kind, local): return [dict(r) for r in self._alias.get((kind, local), ())]
    def lineage(self, item_id): return list(self._lineage[item_id]) if item_id in self._lineage else Direct.lineage(self, item_id)
    def settings(self): return dict(self._settings)

    def report_failed(self, mid):
        if self._runs is None:
            self._runs = {}
            for row in self.cur.execute('SELECT MessageId, Failed FROM report_run WHERE MessageId IS NOT NULL ORDER BY RunId DESC'):
                self._runs.setdefault(str(row['MessageId']), bool(row['Failed']))
        return self._runs.get(str(mid))

    def read_version(self): return self._version

    def receipt(self, kind, local, prints):
        if self._receipts is None:
            self._receipts = {}
            for row in self.cur.execute('SELECT EntityKind, LocalId, Fingerprint, ReadAt FROM processing_read_receipt'):
                self._receipts.setdefault((row[0], row[1]), []).append((row[2], row[3]))
        rows = self._receipts.get((kind, local), ())
        read = [at for f, at in rows if f in prints and at is not None]
        last = [at for _, at in rows if at is not None]
        return (max(read) if read else None) or None, (max(last) if last else None) or None

    def _deferrals(self):
        if self._defers is None:
            self._defers = ({}, {})
            for row in self.cur.execute('SELECT * FROM processing_read_defer'):
                if row['TargetEntityKind'] is None: self._defers[0].setdefault(row['TargetItemId'], []).append(dict(row))
                else: self._defers[1].setdefault((row['TargetEntityKind'], row['TargetLocalId']), []).append(dict(row))
        return self._defers

    def root_deferrals(self, item_id):
        if item_id not in self._lineage: return Direct.root_deferrals(self, item_id)
        return [dict(r) for i in self._lineage[item_id] for r in self._deferrals()[0].get(i, ())]

    def entity_deferrals(self, kind, local): return [dict(r) for r in self._deferrals()[1].get((kind, local), ())]


def _parts(ids, n=400):
    """Stay below older SQLite variable limits."""
    return [ids[o:o + n] for o in range(0, len(ids), n)]


def processing_projection(cur, item_id, *, live_state=None, pre=None):
    """Build full-content and displayed-state revisions from one database snapshot.

    ``cur`` must already be protected by the store lock and a read or write
    transaction. This function neither begins nor commits that transaction.
    ``pre`` (a Prefetch) answers its reads from bulk queries made once for many items.
    """
    src = pre or Direct(cur)
    live_state = None if live_state is None else copy.deepcopy(tuple(live_state))
    membership = src.members(item_id)
    ids = {}
    for member in membership:
        ids.setdefault(member['EntityKind'], []).append(member['LocalId'])
    member_ids = [f"{row['EntityKind']}:{row['LocalId']}" for row in membership]
    messages = src.rows('message', 'MessageId', ids.get('message', []))
    tasks = src.rows('task', 'TaskId', ids.get('task', []))
    message_ids = [row['MessageId'] for row in messages]
    task_ids = [row['TaskId'] for row in tasks]
    transcripts = [t for t in map(src.transcript, task_ids) if t]
    attachments = src.rows('attachment', 'MessageId', message_ids)

    relations = {}
    for member in membership:
        for value in src.relations(member['EntityKind'], member['LocalId']):
            relations[json.dumps(value, sort_keys=True)] = value
    relations = [relations[key] for key in sorted(relations)]
    idea_ids = set(ids.get('idea', []))
    for relation in relations:
        for side in ('From', 'To'):
            if relation[f'{side}EntityKind'] == 'idea':
                idea_ids.add(relation[f'{side}LocalId'])
    ideas = src.rows('idea', 'IdeaId', idea_ids)
    relation_context = [{'Relation': {
        key: row[key] for key in ('FromEntityKind', 'FromLocalId', 'ToEntityKind', 'ToLocalId', 'Kind')
    }} for row in relations]

    aliases = []
    for member in membership: aliases.extend(src.aliases(member['EntityKind'], member['LocalId']))
    context_members = [{'MemberId': mid} for mid in member_ids]
    context_members.extend(_pick(row, (
        'MessageId', 'TaskId', 'ExternalId', 'ConversationId', 'Channel', 'SourceName', 'Subject',
        'FromName', 'FromEmail', 'SentAt', 'BodyText', 'SourceLink', 'Direction',
        'RecipientsJson', 'MailMetaJson')) for row in messages)
    context_members.extend({
        'Namespace': row['Namespace'], 'AccountScope': row['Scope'], 'ProviderId': row['Value'],
        'EntityKind': row['EntityKind'], 'LocalId': row['LocalId'],
    } for row in aliases if row['Namespace'] != 'legacy_funnel')
    context = dict(members=context_members,
                   tasks=[_pick(row, ('TaskId', 'Title', 'Summary', 'Checklist', 'Kind', 'Source', 'SourceRef', 'Tags'))
                          for row in tasks],
                   attachments=[_pick(row, ('AttachmentId', 'MessageId', 'ExternalId', 'Name',
                                           'ContentType', 'Size', 'ContentId', 'Inline', 'Path'))
                                for row in attachments],
                   related_entities=[*[_pick(row, ('IdeaId', 'Text', 'Kind', 'ActionJson', 'Sig'))
                                       for row in ideas], *relation_context])
    context_revision = processing_context_revision(**context)

    # Review/run status and drafts can change in place or be added after identity
    # capture. Read them through exact task/message relationships without allocating
    # members in a getter. Their state affects the view, not substantive context.
    reviews = {}
    for column, values in (('MessageId', message_ids), ('TaskId', task_ids),
                           ('ReviewId', ids.get('review', []))):
        for row in src.rows('review', column, values):
            reviews[row['ReviewId']] = row
    runs = src.rows('run', 'TaskId', task_ids)
    state_keys = [
        row['Value'] for row in aliases if row['Namespace'] == 'legacy_funnel'
    ] + ['processing:' + i for i in src.lineage(item_id)]
    states = src.rows('funnel_state', 'Key', state_keys)
    view = dict(member_ids=member_ids, messages=messages, tasks=tasks,
                attachments=attachments, ideas=ideas, relations=relations,
                comments=src.rows('comment', 'TaskId', task_ids),
                artifacts=src.rows('task_artifact', 'TaskId', task_ids), transcripts=transcripts,
                reviews=[reviews[key] for key in sorted(reviews)], runs=runs,
                routes=src.rows('route', 'MessageId', message_ids),
                legacy_states=states, settings=src.settings(), aliases=aliases,
                processing_summaries=src.rows('processing_display_summary', 'Key', state_keys),
                worker_attention_available=live_state is not None,
                worker_attention=sorted((_worker_attention(row) for row in (live_state or ())
                    if str(row.get('taskId', row.get('task_id'))) in set(map(str, task_ids))),
                    key=lambda row: json.dumps(row, sort_keys=True)))
    from .processing_reads import project as read_projection
    view['processing_read'] = read_projection(cur, item_id, view, src=src)
    if any(m.get('Channel') == 'report' for m in messages):
        # Keyed by the MESSAGE, not the report: keying by source name handed every row of a report the
        # newest run's verdict, so an old "- FAILED" row read as a landed result and one fresh failure
        # would have re-marked every good row before it (the owner, 2026-09-10). report_run.MessageId
        # is the row that run actually produced.
        outcomes = {}
        ids = [m['MessageId'] for m in messages if m.get('Channel') == 'report' and m.get('MessageId')]
        for mid in ids:
            failed = src.report_failed(mid)
            if failed is not None: outcomes[int(mid)] = failed
        view['report_outcomes'] = outcomes
    return dict(item_id=item_id, member_ids=member_ids,
                related_entity_ids=sorted({
                    f"{row[side + 'EntityKind']}:{row[side + 'LocalId']}"
                    for row in relations for side in ('From', 'To')
                }), context_revision=context_revision,
                view_revision=processing_view_revision(context_revision, view),
                context=context, view=view)
