"""Deterministic canonical membership reconciliation.

The caller owns a SQLite write transaction.  This module reads the complete raw
identity graph and updates only the additive ``processing_*`` identity tables.  It
does not infer read/action state or call providers, workers, or legacy feed code.
"""
import json


MANAGED_ENTITY_KINDS = {'task', 'message', 'review', 'idea', 'attachment', 'run'}
MANAGED_RELATION_PROVENANCE = {
    'legacy-assistant-wrapper', 'legacy-assistant-brief', 'processing-membership',
}
_ENTITY_ORDER = {'task': 0, 'message': 1, 'review': 2, 'idea': 3, 'attachment': 4, 'run': 5}
_GROUP_ORDER = {'task': 0, 'message': 1, 'review': 2, 'idea': 3}


def _id_key(value):
    value = str(value)
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _entity_key(entity):
    return (_ENTITY_ORDER.get(entity[0], 99), _id_key(entity[1]))


def _group_key(group):
    return (_GROUP_ORDER[group['kind']], _id_key(group['primary'][1]))


def _problem(code, entity_kind, local_id, **detail):
    out = {'code': code, 'entity_kind': entity_kind, 'local_id': str(local_id)}
    if detail:
        out['detail'] = detail
    return out


def _active_item_for(cur, entity, follow_item):
    row = cur.execute('''SELECT ItemId FROM processing_member
        WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL''', entity).fetchone()
    return follow_item(cur, row['ItemId']) if row else None


def reconcile_membership(cur, *, stamp, new_item_id, follow_item):
    """Apply one uncapped raw-identity census inside ``cur``'s transaction."""
    tasks = {str(r['TaskId']): dict(r) for r in cur.execute('SELECT * FROM task ORDER BY TaskId')}
    messages = {str(r['MessageId']): dict(r) for r in cur.execute('SELECT * FROM message ORDER BY MessageId')}
    reviews = {str(r['ReviewId']): dict(r) for r in cur.execute('SELECT * FROM review ORDER BY ReviewId')}
    ideas = {str(r['IdeaId']): dict(r) for r in cur.execute('SELECT * FROM idea ORDER BY IdeaId')}
    attachments = {str(r['AttachmentId']): dict(r) for r in cur.execute(
        'SELECT * FROM attachment ORDER BY AttachmentId')}
    runs = {str(r['RunId']): dict(r) for r in cur.execute('SELECT * FROM run ORDER BY RunId')}

    item_rows = {r['ItemId']: dict(r) for r in cur.execute(
        'SELECT * FROM processing_item ORDER BY ItemId')}
    current_rows = [dict(r) for r in cur.execute('''SELECT * FROM processing_member
        WHERE RetiredAt IS NULL ORDER BY MemberId''')]
    current = {}
    conflicts, diagnostics = [], []
    for row in current_rows:
        exact = (row['EntityKind'], row['LocalId'])
        root = follow_item(cur, row['ItemId'])
        if root is None:
            conflicts.append(_problem('missing_member_item', *exact, item_id=row['ItemId']))
            continue
        if exact in current:
            conflicts.append(_problem('duplicate_active_membership', *exact))
            continue
        current[exact] = {'row': row, 'root': root}

    groups = {}

    def add_group(key, kind, primary):
        groups[key] = {'key': key, 'kind': kind, 'primary': primary, 'entities': {primary}}

    for tid in sorted(tasks, key=_id_key):
        add_group(('task', tid), 'task', ('task', tid))

    message_group = {}
    for mid, row in sorted(messages.items(), key=lambda pair: _id_key(pair[0])):
        task_id = None if row.get('TaskId') is None else str(row['TaskId'])
        if task_id in tasks:
            key = ('task', task_id)
        else:
            if task_id is not None:
                diagnostics.append(_problem('dangling_message_task', 'message', mid,
                                            task_id=task_id))
            key = ('message', mid)
            add_group(key, 'message', ('message', mid))
        groups[key]['entities'].add(('message', mid))
        message_group[mid] = key

    frozen = set()
    for rid, row in sorted(reviews.items(), key=lambda pair: _id_key(pair[0])):
        mid = None if row.get('MessageId') is None else str(row['MessageId'])
        tid = None if row.get('TaskId') is None else str(row['TaskId'])
        message_parent = message_group.get(mid)
        task_parent = ('task', tid) if tid in tasks else None
        if mid is not None and message_parent is None:
            diagnostics.append(_problem('dangling_review_message', 'review', rid,
                                        message_id=mid))
        if tid is not None and task_parent is None:
            diagnostics.append(_problem('dangling_review_task', 'review', rid,
                                        task_id=tid))
        if message_parent is not None and task_parent is not None and message_parent != task_parent:
            conflicts.append(_problem('contradictory_review_parents', 'review', rid,
                                      message_id=mid, task_id=tid))
            frozen.add(('review', rid))
            continue
        # MessageId has strict precedence.  A non-null dangling MessageId never
        # silently falls through to an otherwise valid TaskId.
        if message_parent is not None:
            key = message_parent
        elif mid is None and task_parent is not None:
            key = task_parent
        else:
            key = ('review', rid)
            add_group(key, 'review', ('review', rid))
        groups[key]['entities'].add(('review', rid))

    # an idea and the task it became (or the task it is about) are ONE thing on the rail: two roots
    # drew two rows wearing the same TQ ref (the owner, 2026-09-07), and the idea row outlived the task
    spawned = {str(r.get('SourceRef') or ''): tid for tid, r in tasks.items()}
    for iid, row in sorted(ideas.items(), key=lambda pair: _id_key(pair[0])):
        try: action = json.loads(row.get('ActionJson') or '{}')
        except (ValueError, TypeError): action = {}
        tid = str(action.get('tid')) if action.get('tid') else spawned.get(f'assistant:idea:{iid}')
        key = ('task', tid) if tid in tasks else ('idea', iid)
        if key[0] == 'idea': add_group(key, 'idea', ('idea', iid))
        groups[key]['entities'].add(('idea', iid))

    for aid, row in sorted(attachments.items(), key=lambda pair: _id_key(pair[0])):
        mid = None if row.get('MessageId') is None else str(row['MessageId'])
        key = message_group.get(mid)
        if key is None:
            diagnostics.append(_problem('dangling_attachment_message', 'attachment', aid,
                                        message_id=mid))
        else:
            groups[key]['entities'].add(('attachment', aid))

    for run_id, row in sorted(runs.items(), key=lambda pair: _id_key(pair[0])):
        tid = None if row.get('TaskId') is None else str(row['TaskId'])
        key = ('task', tid) if tid in tasks else None
        if key is None:
            diagnostics.append(_problem('dangling_run_task', 'run', run_id, task_id=tid))
        else:
            groups[key]['entities'].add(('run', run_id))

    ordered_groups = sorted(groups.values(), key=_group_key)
    assigned_roots = set()
    targets = {}
    created_item_ids = set()
    first_member_by_root = {}
    for found in current.values():
        member_id = int(found['row']['MemberId'])
        first_member_by_root[found['root']] = min(
            member_id, first_member_by_root.get(found['root'], member_id))

    def root_order(item_id):
        row = item_rows.get(item_id) or {}
        return (str(row.get('CreatedAt') or ''), first_member_by_root.get(item_id, 2 ** 63), item_id)

    # A message being reassigned must never let an earlier-sorted new task steal
    # the durable root of a later task. Reserve every unambiguous task root before
    # considering any member-derived candidate.
    reserved_for = {}
    for group in ordered_groups:
        if group['kind'] != 'task':
            continue
        found = current.get(group['primary'])
        if found:
            reserved_for.setdefault(found['root'], group['key'])

    for group in ordered_groups:
        candidates = {current[e]['root'] for e in group['entities'] if e in current}
        preferred = None
        if group['kind'] == 'task':
            task_current = current.get(group['primary'])
            if (task_current and task_current['root'] not in assigned_roots
                    and reserved_for.get(task_current['root']) == group['key']):
                preferred = task_current['root']
        if preferred is None:
            available = sorted((root for root in candidates if root not in assigned_roots
                                and reserved_for.get(root, group['key']) == group['key']),
                               key=root_order)
            preferred = available[0] if available else None
        if preferred is None:
            preferred = new_item_id()
            cur.execute('''INSERT INTO processing_item
                (ItemId,Kind,CreatedAt,UpdatedAt) VALUES (?,?,?,?)''',
                (preferred, group['kind'], stamp, stamp))
            created_item_ids.add(preferred)
            item_rows[preferred] = {'ItemId': preferred, 'Kind': group['kind'],
                                    'CreatedAt': stamp, 'UpdatedAt': stamp,
                                    'RedirectItemId': None}
        assigned_roots.add(preferred)
        targets[group['key']] = preferred

    desired = {}
    for group in ordered_groups:
        target = targets[group['key']]
        for entity in group['entities']:
            desired[entity] = target

    raw_entities = ({('task', key) for key in tasks} |
                    {('message', key) for key in messages} |
                    {('review', key) for key in reviews} |
                    {('idea', key) for key in ideas} |
                    {('attachment', key) for key in attachments} |
                    {('run', key) for key in runs})
    retired_members = 0
    moved_members = 0
    moved_destinations = {}
    touched_items = set()
    for entity, found in sorted(current.items(), key=lambda pair: _entity_key(pair[0])):
        if entity[0] not in MANAGED_ENTITY_KINDS or entity in frozen:
            continue
        target = desired.get(entity)
        stale_item = found['row']['ItemId'] != found['root']
        if entity not in raw_entities or target is None or found['root'] != target or stale_item:
            cur.execute('UPDATE processing_member SET RetiredAt=? WHERE MemberId=?',
                        (stamp, found['row']['MemberId']))
            retired_members += 1
            touched_items.add(found['root'])
            if target is not None:
                moved_members += 1
                moved_destinations.setdefault(found['root'], set()).add(target)

    active = {(r['EntityKind'], r['LocalId']): dict(r) for r in cur.execute('''SELECT *
        FROM processing_member WHERE RetiredAt IS NULL ORDER BY MemberId''')}
    created_members = 0
    for group in ordered_groups:
        target = targets[group['key']]
        have_primary = cur.execute('''SELECT 1 FROM processing_member
            WHERE ItemId=? AND RetiredAt IS NULL AND Role='primary' LIMIT 1''',
            (target,)).fetchone() is not None
        entities = sorted(group['entities'], key=_entity_key)
        entities.sort(key=lambda entity: entity != group['primary'])
        for entity in entities:
            if entity in active:
                continue
            role = ('primary' if not have_primary and entity == group['primary'] else
                    'attachment' if entity[0] == 'attachment' else
                    'work' if entity[0] == 'run' else 'member')
            if role == 'primary':
                have_primary = True
            cur.execute('''INSERT INTO processing_member
                (ItemId,EntityKind,LocalId,Role,JoinedAt) VALUES (?,?,?,?,?)''',
                (target, entity[0], entity[1], role, stamp))
            active[entity] = {'ItemId': target, 'EntityKind': entity[0],
                              'LocalId': entity[1], 'Role': role}
            created_members += 1
            touched_items.add(target)

        # A deleted old primary can leave unchanged members behind.  Preserve the
        # old row as history, then promote the group's preferred surviving entity.
        if not cur.execute('''SELECT 1 FROM processing_member WHERE ItemId=?
            AND RetiredAt IS NULL AND Role='primary' LIMIT 1''', (target,)).fetchone():
            chosen = next((entity for entity in entities if entity in active), None)
            if chosen is not None:
                row = cur.execute('''SELECT MemberId FROM processing_member
                    WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL''', chosen).fetchone()
                cur.execute('UPDATE processing_member SET RetiredAt=? WHERE MemberId=?',
                            (stamp, row['MemberId']))
                cur.execute('''INSERT INTO processing_member
                    (ItemId,EntityKind,LocalId,Role,JoinedAt) VALUES (?,?,?,?,?)''',
                    (target, chosen[0], chosen[1], 'primary', stamp))
                retired_members += 1
                created_members += 1
                touched_items.add(target)

    # Generated legacy aliases identify exact local entities.  Existing provider
    # aliases, scopes and provenance are never inferred or rewritten here.
    alias_specs = []
    for tid in sorted(tasks, key=_id_key):
        alias_specs.extend((value, 'task', tid) for value in
                           (f'task:{tid}', f'agent:{tid}', f'wrap:{tid}'))
    for mid, row in sorted(messages.items(), key=lambda pair: _id_key(pair[0])):
        alias_specs.append((f'msg:{mid}', 'message', mid))
        if row.get('Channel') == 'report':
            alias_specs.append((f'report:{mid}', 'message', mid))
    alias_specs.extend((f'review:{rid}', 'review', rid) for rid in sorted(reviews, key=_id_key)
                       if ('review', rid) not in frozen)
    alias_specs.extend((f'idea:{iid}', 'idea', iid) for iid in sorted(ideas, key=_id_key))
    created_aliases = 0
    for value, entity_kind, local_id in alias_specs:
        old = cur.execute('''SELECT EntityKind,LocalId FROM processing_alias
            WHERE Namespace='legacy_funnel' AND Scope='local' AND Value=?
              AND RetiredAt IS NULL''', (value,)).fetchone()
        if old and (old['EntityKind'], old['LocalId']) != (entity_kind, local_id):
            conflicts.append(_problem('legacy_alias_collision', entity_kind, local_id,
                                      value=value, existing_entity_kind=old['EntityKind'],
                                      existing_local_id=old['LocalId']))
            continue
        if old:
            continue
        cur.execute('''INSERT INTO processing_alias
            (Namespace,Scope,Value,EntityKind,LocalId,Provenance,CreatedAt)
            VALUES ('legacy_funnel','local',?,?,?,'processing-membership',?)''',
            (value, entity_kind, local_id, stamp))
        created_aliases += 1
        target = desired.get((entity_kind, local_id))
        if target:
            touched_items.add(target)

    desired_relations = set()
    for iid, row in sorted(ideas.items(), key=lambda pair: _id_key(pair[0])):
        mid = None if row.get('MessageId') is None else str(row['MessageId'])
        if mid is not None:
            if mid in messages:
                desired_relations.add(('message', mid, 'idea', iid, 'mentions'))
            else:
                diagnostics.append(_problem('dangling_idea_message', 'idea', iid,
                                            message_id=mid))
    for mid, row in sorted(messages.items(), key=lambda pair: _id_key(pair[0])):
        raw_brief = row.get('Brief')
        if not raw_brief:
            continue
        try:
            brief = json.loads(raw_brief)
        except (TypeError, ValueError, json.JSONDecodeError):
            diagnostics.append(_problem('malformed_message_brief', 'message', mid))
            continue
        entries = brief.get('ideas') if isinstance(brief, dict) else None
        if entries is None:
            continue
        if not isinstance(entries, list):
            diagnostics.append(_problem('malformed_brief_ideas', 'message', mid))
            continue
        for entry in entries:
            idea_id = entry.get('id') if isinstance(entry, dict) else None
            idea_id = None if idea_id is None else str(idea_id)
            if idea_id not in ideas:
                diagnostics.append(_problem('unknown_brief_idea', 'message', mid,
                                            idea_id=idea_id))
                continue
            desired_relations.add(('message', mid, 'idea', idea_id, 'mentions'))

    active_relations = [dict(r) for r in cur.execute('''SELECT * FROM processing_relation
        WHERE RetiredAt IS NULL ORDER BY RelationId''')]
    existing_relations = set()
    retired_relations = 0
    for row in active_relations:
        key = (row['FromEntityKind'], row['FromLocalId'], row['ToEntityKind'],
               row['ToLocalId'], row['Kind'])
        if row['Provenance'] in MANAGED_RELATION_PROVENANCE:
            if key not in desired_relations:
                cur.execute('UPDATE processing_relation SET RetiredAt=? WHERE RelationId=?',
                            (stamp, row['RelationId']))
                retired_relations += 1
                for entity in ((key[0], key[1]), (key[2], key[3])):
                    if entity in active:
                        touched_items.add(follow_item(cur, active[entity]['ItemId']))
                continue
        existing_relations.add(key)
    created_relations = 0
    for key in sorted(desired_relations):
        if key in existing_relations:
            continue
        cur.execute('''INSERT INTO processing_relation
            (FromEntityKind,FromLocalId,ToEntityKind,ToLocalId,Kind,Provenance,CreatedAt)
            VALUES (?,?,?,?,?,'processing-membership',?)''', (*key, stamp))
        created_relations += 1
        for entity in ((key[0], key[1]), (key[2], key[3])):
            if entity in active:
                touched_items.add(follow_item(cur, active[entity]['ItemId']))

    redirected_items = 0
    for source, destinations in sorted(moved_destinations.items()):
        if source in destinations or len(destinations) != 1:
            continue
        if cur.execute('''SELECT 1 FROM processing_member WHERE ItemId=?
            AND RetiredAt IS NULL LIMIT 1''', (source,)).fetchone():
            continue
        target = next(iter(destinations))
        target = follow_item(cur, target)
        if target and target != source:
            cur.execute('''UPDATE processing_item SET RedirectItemId=?,ContextRevision=NULL,
                ViewRevision=NULL,UpdatedAt=? WHERE ItemId=? AND RedirectItemId IS NULL''',
                (target, stamp, source))
            redirected_items += cur.rowcount
            touched_items.add(target)

    for group in ordered_groups:
        target = targets[group['key']]
        row = item_rows.get(target) or {}
        if row.get('Kind') != group['kind']:
            cur.execute('''UPDATE processing_item SET Kind=?,ContextRevision=NULL,
                ViewRevision=NULL,UpdatedAt=? WHERE ItemId=?''',
                (group['kind'], stamp, target))
            touched_items.add(target)
    for item_id in sorted(item for item in touched_items if item):
        cur.execute('''UPDATE processing_item SET ContextRevision=NULL,ViewRevision=NULL,
            UpdatedAt=? WHERE ItemId=?''', (stamp, item_id))

    conflicts.sort(key=lambda row: json.dumps(row, sort_keys=True))
    diagnostics.sort(key=lambda row: json.dumps(row, sort_keys=True))
    return {
        'created_items': len(created_item_ids),
        'created_members': created_members,
        'moved_members': moved_members,
        'retired_members': retired_members,
        'redirected_items': redirected_items,
        'created_aliases': created_aliases,
        'created_relations': created_relations,
        'retired_relations': retired_relations,
        'conflicts': conflicts,
        'diagnostics': diagnostics,
    }
