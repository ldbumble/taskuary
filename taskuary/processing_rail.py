"""The rail's incremental read: re-project only the roots a write touched, reuse the rest.

A rail read used to re-project every root in the window (~1,100 on the owner's store, ~20 queries
each) after ANY write, because the display cache was keyed on one write counter - and a Next press
writes (its receipts, the surfaced mark), so every press paid two full rebuilds, 1.5-2 s each
(2026-09-17, docs/superpowers/specs/2026-09-17-rail-ranks-assistant-takes-design.md).

The triggers below record WHICH row changed (`processing_dirty_row`) beside the generation counter
the census already bumps. They live in the database, so a write from the sync process or the
membership worker is seen exactly as the counter is. `touched()` turns those rows into the roots
whose projection can have changed; the store re-projects those and hands back the others by
reference.
"""
import hashlib, json

# table -> the (kind, id) pairs one of its rows belongs to. A kind in quotes is a literal; bare, it is a
# column of the row. A review names its message and its task too: the projection reads reviews by
# those before the census has filed the review as a member of its own.
DIRTY_ROWS = {
    'message': [("'message'", 'MessageId')],
    'task': [("'task'", 'TaskId')],
    'review': [("'review'", 'ReviewId'), ("'message'", 'MessageId'), ("'task'", 'TaskId')],
    'idea': [("'idea'", 'IdeaId')],
    'attachment': [("'message'", 'MessageId')],
    'run': [("'task'", 'TaskId')],
    'route': [("'message'", 'MessageId'), ("'task'", 'TaskId')],
    'comment': [("'task'", 'TaskId')],
    # ...and the two tables only the card's display backing reads (funnel_presentation): the stamp cache
    # is valid exactly while no backing table has been written, so every one of them must leave a row here
    'waitroom': [("'task'", 'TaskId')],
    'connector': [("'connector'", 'ConnectorId')],
    'task_artifact': [("'task'", 'TaskId')],
    'transcript': [("'task'", 'TaskId')],
    'report_run': [("'message'", 'MessageId')],
    'funnel_state': [("'state'", 'Key')],
    'processing_display_summary': [("'state'", 'Key')],
    'processing_item': [("'item'", 'ItemId')],
    'processing_member': [("'item'", 'ItemId'), ('EntityKind', 'LocalId')],
    'processing_read_defer': [("'item'", 'TargetItemId')],
    'processing_read_receipt': [('EntityKind', 'LocalId')],
    'processing_alias': [('EntityKind', 'LocalId')],
    'processing_relation': [('FromEntityKind', 'FromLocalId'), ('ToEntityKind', 'ToLocalId')],
}
ENTITY_KINDS = ('message', 'task', 'review', 'idea')
KEEP_ROWS = 10_000     # a rail older than this many dirty rows rebuilds in full


def follow(redirect, item_id):
    """The root of an item, walked in Python over the redirect map (one query per hop used to be the
    cost: ~8,000 SELECTs per build on the owner's store). None for an unknown id."""
    seen, current = set(), item_id
    while current and current not in seen:
        seen.add(current)
        if current not in redirect: return None
        if not redirect[current]: return current
        current = redirect[current]
    raise ValueError(f'processing item redirect cycle at {item_id}')


def _ref(kind, row):
    return kind if kind.startswith("'") else f'{row}.{kind}'


def triggers(setting_names):
    """The CREATE TRIGGER statements: one per table and action, each writing the row's (kind, id) pairs."""
    out = []
    for table, pairs in DIRTY_ROWS.items():
        for action, rows in (('INSERT', ('NEW',)), ('UPDATE', ('NEW', 'OLD')), ('DELETE', ('OLD',))):
            # an UPDATE names its old key only when the key moved: a plain edit is one dirty row, not two
            body = ''.join(f"INSERT INTO processing_dirty_row(Kind, LocalId) SELECT {_ref(k, r)}, CAST({r}.{i} AS TEXT) WHERE {r}.{i} IS NOT NULL"
                           + (f" AND OLD.{i} IS NOT NEW.{i}" if action == 'UPDATE' and r == 'OLD' else '') + ";\n"
                           for r in rows for k, i in pairs)
            out.append(f'CREATE TRIGGER IF NOT EXISTS rail_dirty_{table}_{action.lower()} AFTER {action} ON {table} BEGIN\n{body}END')
    names = ','.join("'" + n + "'" for n in setting_names)
    for action, row in (('INSERT', 'NEW'), ('UPDATE', 'NEW'), ('DELETE', 'OLD')):
        out.append(f'''CREATE TRIGGER IF NOT EXISTS rail_dirty_setting_{action.lower()} AFTER {action} ON setting
            WHEN {row}.Name IN ({names}) BEGIN
              INSERT INTO processing_dirty_row(Kind, LocalId) VALUES ('setting', {row}.Name);
            END''')
    return out


def dirty_since(cur, mark):
    """(top, rows): the newest dirty id and the distinct (kind, id) pairs written after `mark` - or
    rows=None when rows between were trimmed away, so what happened is unknown and the rail rebuilds."""
    top = cur.execute('SELECT COALESCE(MAX(Id),0) FROM processing_dirty_row').fetchone()[0]
    if top <= mark: return top, ()
    low = cur.execute('SELECT MIN(Id) FROM processing_dirty_row WHERE Id>?', (mark,)).fetchone()[0]
    if low is None or low > mark + 1: return top, None
    return top, [(r[0], r[1]) for r in cur.execute(
        'SELECT DISTINCT Kind, LocalId FROM processing_dirty_row WHERE Id>?', (mark,))]


def trim(cx):
    cx.execute('DELETE FROM processing_dirty_row WHERE Id < (SELECT COALESCE(MAX(Id),0) FROM processing_dirty_row) - ?', (KEEP_ROWS,))


def touched(cur, rows, follow):
    """The roots whose projection can have changed, given dirty (kind, id) pairs; `follow(item_id)`
    resolves redirects. Returns (roots, structural) - roots None means everything: a setting every
    projection reads, or a state key no root can be named for."""
    roots, structural, entities = set(), False, set()
    for kind, local in rows:
        if kind == 'setting': return None, True
        if kind == 'item':
            structural = True
            root = follow(local)
            if root: roots.add(root)
        elif kind == 'state':
            if local.startswith('processing:'):
                root = follow(local[len('processing:'):])
                if root: roots.add(root)
            else:
                # a legacy funnel key is an alias of exactly one entity; a key that is neither is
                # not a root's business (a batch key, a chat mark) - nothing in a projection reads it
                for r in cur.execute("SELECT EntityKind, LocalId FROM processing_alias WHERE Value=? AND RetiredAt IS NULL", (local,)):
                    entities.add((r[0], r[1]))
        else:
            entities.add((kind, local))
    # an entity's root, and the roots of whatever is related to it: a related idea is read into the
    # projection of the item it points at, member or not
    for kind, local in list(entities):
        for r in cur.execute('''SELECT FromEntityKind, FromLocalId, ToEntityKind, ToLocalId FROM processing_relation
            WHERE RetiredAt IS NULL AND ((FromEntityKind=? AND FromLocalId=?) OR (ToEntityKind=? AND ToLocalId=?))''',
                             (kind, local, kind, local)):
            entities.add((r[0], r[1])); entities.add((r[2], r[3]))
    for kind, local in entities:
        for r in cur.execute('SELECT ItemId FROM processing_member WHERE EntityKind=? AND LocalId=?', (kind, local)):
            root = follow(r[0])
            if root: roots.add(root)
    return roots, structural


def revision(snapshot, hashes):
    """The snapshot's fingerprint from per-root fingerprints - never a json.dumps of 12.8 MB."""
    h = hashlib.sha256()
    for item in snapshot['items']:
        h.update(hashes.get(item['item_id'], '').encode()); h.update(str(item.get('view_revision')).encode()); h.update(b'\n')
    h.update(json.dumps({k: v for k, v in snapshot.items() if k != 'items'}, ensure_ascii=False, sort_keys=True,
                        separators=(',', ':'), allow_nan=False, default=str).encode())
    return h.hexdigest()


def root_hash(projection):
    return hashlib.sha256(json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()
