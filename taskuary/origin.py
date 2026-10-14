"""Where a task's words came from: the owner, a trusted sender, or a stranger (spec 2026-10-14).

Computed ON READ from the task's messages, worst wins - so a road that attaches a message without passing ingest
(attach_message, a split, a batch) cannot skip it. Only the owner raises it (raise_to), and only through the messages
it has seen: a stranger who writes afterwards lowers it again."""
from . import senders

ORDER = ('stranger', 'trusted', 'owner')
def worse(a, b): return a if ORDER.index(a) <= ORDER.index(b) else b

def _own(row): return row.get('Direction') == 'out' or row.get('Status') == 'context'

def of_message(store, row: dict) -> tuple:
    "(origin, why) for one stored message row. No network: senders.known is never asked to look deeper."
    if _own(row): return 'owner', 'your own words'
    ch = row.get('Channel') or ''
    # the assistant and reports speak in Taskuary's voice, but carry what they read - mail, the web - so they are not
    # vouched for here (senders.known still trusts them for the separate auto-start question)
    if ch in ('assistant', 'report'): return 'stranger', f"written by Taskuary's {ch} from what it read"
    if ch == 'github':
        from .batch import outside_row
        return ('stranger', 'a public repository, by someone without write access') if outside_row(store, row) \
            else ('trusted', 'a member of the repository')
    ok, why = senders.known(store, {'channel': ch, 'from_email': row.get('FromEmail'), 'source_name': row.get('SourceName')},
                            exclude_mid=row.get('MessageId'))
    return ('trusted' if ok else 'stranger'), why

def of_task(store, tid: int) -> tuple:
    "(origin, why) for a task, refreshing the card's cache."
    t = store.get_task(tid) or {}
    o, why = t.get('OriginBase') or 'trusted', 'you made it' if t.get('OriginBase') == 'owner' else 'no stranger wrote on it'
    through = int(t.get('TrustedThrough') or 0)
    for m in store.list_messages(tid):
        if m['MessageId'] <= through: continue
        mo, mwhy = of_message(store, m)
        if worse(mo, o) != o: o, why = mo, mwhy
    # a bare UPDATE: a read must not move UpdatedAt/UpdatedBy and reorder the lists
    if (t.get('Origin'), t.get('OriginWhy')) != (o, why): store._exec('UPDATE task SET Origin=?, OriginWhy=? WHERE TaskId=?', (o, why, tid))
    return o, why

def raise_to(store, tid: int, to: str, actor: str):
    "The owner's say-so: everything on the task so far counts as `to`. A later message is judged on its own."
    last = max((m['MessageId'] for m in store.list_messages(tid)), default=0)
    store.update_task(tid, {'TrustedThrough': last, **({'OriginBase': 'owner'} if to == 'owner' else {})}, actor)
    store.audit('task', tid, 'origin_raised', actor, detail={'to': to, 'through': last})
    of_task(store, tid)
