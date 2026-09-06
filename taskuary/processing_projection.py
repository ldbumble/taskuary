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


def _rows_for(cur, table, column, ids):
    ids = sorted(set(ids), key=str)
    rows = []
    # Stay below older SQLite variable limits even for a large grouped item.
    for offset in range(0, len(ids), 400):
        part = ids[offset:offset + 400]
        rows.extend(dict(row) for row in cur.execute(
            f'SELECT * FROM {table} WHERE {column} IN ({",".join("?" for _ in part)})', part))
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))


def processing_projection(cur, item_id, *, live_state=None):
    """Build full-content and displayed-state revisions from one database snapshot.

    ``cur`` must already be protected by the store lock and a read or write
    transaction. This function neither begins nor commits that transaction.
    """
    live_state = None if live_state is None else copy.deepcopy(tuple(live_state))
    membership = [dict(row) for row in cur.execute('''SELECT * FROM processing_member
        WHERE ItemId=? AND RetiredAt IS NULL ORDER BY EntityKind,LocalId''', (item_id,))]
    ids = {}
    for member in membership:
        ids.setdefault(member['EntityKind'], []).append(member['LocalId'])
    member_ids = [f"{row['EntityKind']}:{row['LocalId']}" for row in membership]
    messages = _rows_for(cur, 'message', 'MessageId', ids.get('message', []))
    tasks = _rows_for(cur, 'task', 'TaskId', ids.get('task', []))
    message_ids = [row['MessageId'] for row in messages]
    task_ids = [row['TaskId'] for row in tasks]
    transcripts = []
    for tid in task_ids:
        row = cur.execute('''SELECT TaskId, Sid sid, Agent agent, Cwd cwd, CreatedAt at,
            LENGTH(IFNULL(Text,'')) chars FROM transcript WHERE TaskId=?
            ORDER BY TranscriptId DESC LIMIT 1''', (tid,)).fetchone()
        if row:
            transcripts.append(dict(row))
    attachments = _rows_for(cur, 'attachment', 'MessageId', message_ids)

    relations = {}
    for member in membership:
        for row in cur.execute('''SELECT * FROM processing_relation WHERE RetiredAt IS NULL AND
            ((FromEntityKind=? AND FromLocalId=?) OR (ToEntityKind=? AND ToLocalId=?))''',
            (member['EntityKind'], member['LocalId'], member['EntityKind'], member['LocalId'])):
            value = dict(row)
            relations[json.dumps(value, sort_keys=True)] = value
    relations = [relations[key] for key in sorted(relations)]
    idea_ids = set(ids.get('idea', []))
    for relation in relations:
        for side in ('From', 'To'):
            if relation[f'{side}EntityKind'] == 'idea':
                idea_ids.add(relation[f'{side}LocalId'])
    ideas = _rows_for(cur, 'idea', 'IdeaId', idea_ids)
    relation_context = [{'Relation': {
        key: row[key] for key in ('FromEntityKind', 'FromLocalId', 'ToEntityKind', 'ToLocalId', 'Kind')
    }} for row in relations]

    aliases = []
    for member in membership:
        aliases.extend(dict(row) for row in cur.execute('''SELECT * FROM processing_alias
            WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL ORDER BY Namespace,Scope,Value''',
            (member['EntityKind'], member['LocalId'])))
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
        for row in _rows_for(cur, 'review', column, values):
            reviews[row['ReviewId']] = row
    runs = _rows_for(cur, 'run', 'TaskId', task_ids)
    state_keys = [
        row['Value'] for row in aliases if row['Namespace'] == 'legacy_funnel'
    ] + ['processing:' + row[0] for row in cur.execute('''WITH RECURSIVE roots(id) AS (
        SELECT ItemId FROM processing_item WHERE ItemId=?
        UNION SELECT p.ItemId FROM processing_item p JOIN roots r ON p.RedirectItemId=r.id)
        SELECT id FROM roots''', (item_id,))]
    states = _rows_for(cur, 'funnel_state', 'Key', state_keys)
    settings = {row['Name']: row['Value'] for row in cur.execute('''SELECT Name,Value FROM setting
        WHERE Name IN ('funnel_hours','funnel_mutes','feed_days','team_domains','owner_email') ORDER BY Name''')}
    view = dict(member_ids=member_ids, messages=messages, tasks=tasks,
                attachments=attachments, ideas=ideas, relations=relations,
                comments=_rows_for(cur, 'comment', 'TaskId', task_ids),
                artifacts=_rows_for(cur, 'task_artifact', 'TaskId', task_ids), transcripts=transcripts,
                reviews=[reviews[key] for key in sorted(reviews)], runs=runs,
                routes=_rows_for(cur, 'route', 'MessageId', message_ids),
                legacy_states=states, settings=settings, aliases=aliases,
                processing_summaries=_rows_for(cur, 'processing_display_summary', 'Key', state_keys),
                worker_attention_available=live_state is not None,
                worker_attention=sorted((dict(row) for row in (live_state or ())
                    if str(row.get('taskId', row.get('task_id'))) in set(map(str, task_ids))),
                    key=lambda row: json.dumps(row, sort_keys=True)))
    from .processing_reads import project as read_projection
    view['processing_read'] = read_projection(cur, item_id, view)
    if any(m.get('Channel') == 'report' for m in messages):
        outcomes = {}
        for source in cur.execute("SELECT SourceId,Address,ConfigJson FROM source WHERE Channel='report'").fetchall():
            last = cur.execute('SELECT Failed FROM report_run WHERE SourceId=? ORDER BY RunId DESC LIMIT 1', (source['SourceId'],)).fetchone()
            if last is None:
                continue
            try: title = json.loads(source['ConfigJson'] or '{}').get('title')
            except (ValueError, TypeError): title = None
            for name in (source['Address'], title):
                if name: outcomes[str(name)] = bool(last['Failed'])
        view['report_outcomes'] = outcomes
    return dict(item_id=item_id, member_ids=member_ids,
                related_entity_ids=sorted({
                    f"{row[side + 'EntityKind']}:{row[side + 'LocalId']}"
                    for row in relations for side in ('From', 'To')
                }), context_revision=context_revision,
                view_revision=processing_view_revision(context_revision, view),
                context=context, view=view)
