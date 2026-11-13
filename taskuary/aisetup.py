"""The setup task an AI app's install runs as (clisetup.py): its kind, the open one a press reuses, and its plain close.

Setting up a CONNECTION, a report, a dashboard, a routine or a playbook is the Assistant's now, on that thing's own page (build.py, the owner
2026-11-13) - no task and no walk. What is left here is the one setup that still runs as a task: installing an AI app, in a terminal pane.
"""
KIND = 'setup'


def open_task(store, tags: str, title: str):
    """The still-open setup task this press belongs to, or None. A pane that died took its task with
    it only in spirit: the row stayed in progress, went "interrupted" and landed on the owner, so a
    CLI that crashed on launch left one more "Set up codex" per press (TQ-0726). Reuse it instead."""
    for t in store.list_tasks(active_only=True):
        if t.get('Kind') == KIND and t.get('Status') != 'done' and str(t.get('Tags') or '') == tags and t.get('Title') == title:
            return t['TaskId']
    return None


def finish(store, tid: int, actor: str = 'owner') -> dict:
    """Done means the session goes and the task closes - the AI app's own Test said the rest."""
    from . import terminal as term
    live = term.for_task(tid)
    if live: term.close(live['sid'])
    store.add_comment(tid, actor, 'human', 'Setup session closed.')
    if (store.get_task(tid) or {}).get('Status') not in ('done', 'dropped'): store.update_task(tid, {'Status': 'done'}, actor)
    store.audit('terminal', tid, 'wrap', actor, detail={'sid': live and live['sid'], 'setup': True})
    return {'wrap': 'done', 'taskId': tid}
