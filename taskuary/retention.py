"""Chat retention (PW-156 to PW-161): archived guide conversations expire on their own clock.

A history read used to be the cleanup: concierge.chats() marked anything older than a hardcoded twenty
days `dropped` on the way past, so listing past chats mutated them. Retention is now one scheduled
lifecycle operation - once a day, from the app's own clock - with a setting (`chat_keep_days`,
fifteen by default). It removes only ARCHIVED guide conversations whose last word is older than the
cutoff: never the open chat, never a real task. What a chat said about a task was mirrored onto that
task as it was said (concierge.record_related), operation receipts and correction evidence are keyed
to their targets, and memories and rules are their own rows - none of it lives on the archive, so
none of it goes with it.
"""
from datetime import datetime, timedelta
from loguru import logger

from . import general

KEY, DEFAULT_DAYS, RAN_KEY = 'chat_keep_days', 15, 'chat_cleanup_at'


def keep_days(store) -> int:
    try: return max(1, int(store.get_settings().get(KEY) or DEFAULT_DAYS))
    except (TypeError, ValueError): return DEFAULT_DAYS


def cutoff(store, now: datetime = None) -> str:
    return ((now or datetime.now()) - timedelta(days=keep_days(store))).strftime('%Y-%m-%d %H:%M:%S')


def last_word(store, task: dict) -> str:
    rows = general.chat_rows(store, task['TaskId'])
    return str((rows[-1]['CreatedAt'] if rows else task.get('CreatedAt')) or '')


def eligible(store, now: datetime = None) -> list:
    """Archived guide conversations whose last word is older than the cutoff. The open chat is never archived
    (its status is open), so it is never here whatever its age."""
    cut = cutoff(store, now)
    return [t for t in store.dock_tasks(general.DOCK_TAG, limit=10_000) if t.get('Status') in ('done', 'dropped') and last_word(store, t) < cut]


def cleanup(store, now: datetime = None, actor: str = 'retention') -> dict:
    """Remove every eligible archive: the conversation rows and the guide task that held them, nothing else."""
    from .concierge import SID_KEY
    cut, gone = cutoff(store, now), []
    for t in eligible(store, now):
        tid = t['TaskId']
        store.set_setting(f'{SID_KEY}:{tid}', '', actor)           # the model conversation behind it is over too
        store.delete_task(tid)
        store.audit('task', tid, 'chat_retention_delete', actor, detail={'cutoff': cut})
        gone.append(tid)
    if gone: logger.info(f'chat retention: removed {len(gone)} archived chat(s) older than {cut}')
    return {'removed': gone, 'cutoff': cut, 'keep_days': keep_days(store)}


def tick(store, now: datetime = None) -> dict | None:
    """Once a day, on the app's own clock - at start-up and on the sync timer, never from a history read."""
    now = now or datetime.now()
    if str(store.get_settings().get(RAN_KEY) or '')[:10] == now.strftime('%Y-%m-%d'): return None
    out = cleanup(store, now)
    store.set_setting(RAN_KEY, now.strftime('%Y-%m-%d %H:%M:%S'), 'retention')
    return out
