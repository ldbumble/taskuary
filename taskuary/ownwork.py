"""The timeline rows for work that did not arrive from outside.

The Timeline is built from `message`, which made it an inbox: a task the owner started from the
Board or the Tasks tab had no message, so it had no row, so an agent could work for forty minutes
and the page that is supposed to be the record of the day said nothing about it. Half the day was
missing from the one screen the owner watches - and the half that was missing is the half they
started themselves.

So work that begins inside Taskuary gets a row too, on channel `own`, stamped at the moment it
actually began (not the moment we noticed). Two makers:

- `ensure` - a session is opening on a task nothing has ever written about. Called from the two
  places a session can start, so wherever the click was, the rail shows it.
- `note` - the one row that is genuinely YOURS rather than something that happened to you: a
  reminder, an idea, a thing to come back to. Kind `note`, so nothing triages it, nothing
  dispatches an agent at it, and nothing drafts a reply to anybody.

A note's row is stamped with WHEN IT IS FOR, not when it was typed. The timeline is a clock, so
"chase this Tuesday" is a row that sits in Tuesday - out of the way until Tuesday, and then at
the top of the day, which is the whole behaviour a reminder needs and none of the machinery a
due-date column would have cost.
"""
from datetime import datetime
from loguru import logger

CHANNEL = 'own'
KIND = 'note'                      # the task kind a note-to-self creates
SOURCE = 'you'                     # what the row says it came from


def _stamp(when=None) -> str:
    if isinstance(when, datetime): return when.strftime('%Y-%m-%d %H:%M:%S')
    s = str(when or '').strip()
    return s[:19].replace('T', ' ') if s else datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def row_for(store, tid: int):
    """The own-row already on this task, if any."""
    return next((m for m in store.list_messages(tid) if (m.get('Channel') or '') == CHANNEL), None)


def ensure(store, tid: int, when=None, why: str = '', actor: str = 'owner'):
    """Give a task a timeline row if nothing else already speaks for it. Returns the message id,
    or None when the task already has one (from mail, chat, a report, or an earlier session).

    Never raises: a missing timeline row is a cosmetic loss and must not stop a session from
    opening. That is the whole reason this is a separate function and not an inline insert."""
    try:
        t = store.get_task(tid)
        if not t: return None
        if t.get('SourceRef') == 'assistant:dock': return None
        if [m for m in store.list_messages(tid) if m.get('Status') != 'context']: return None
        at = _stamp(when)
        mid = store.add_message({
            'TaskId': tid, 'ExternalId': f'own:{tid}', 'ConversationId': f'own:{tid}',
            'Channel': CHANNEL, 'SourceName': SOURCE, 'Subject': t.get('Title') or 'Untitled',
            'FromName': 'You', 'SentAt': at, 'BodyText': str(t.get('Summary') or '').strip(),
            'Status': 'routed'})
        store.add_route(mid, tid, 'own', None,
                        why or 'you started this yourself - no message came in, so the timeline '
                               'carries the work instead', [], actor)
        return mid
    except Exception as e:
        logger.warning(f'could not put task {tid} on the timeline: {e}')
        return None


def note(store, title: str, body: str = '', when=None, actor: str = 'owner') -> dict:
    """A note to yourself: a reminder, an idea, a thing to come back to.

    It is a task so it can be found, listed and closed like everything else - but kind `note`,
    which is outside every routing rule in the app: triage never sees it (nothing arrived),
    auto_code_ok refuses anything that is not `coding`, and general.handles does not claim it,
    so it never opens a chat either. Nothing works it. That is the point."""
    title = ' '.join(str(title or '').split())[:300]
    if not title: raise ValueError('a note with no words is not a note')
    at = _stamp(when)
    tid = store.create_task({'Title': title, 'Summary': str(body or '').strip(), 'Kind': KIND,
                             'Status': 'open', 'Priority': 'normal', 'Source': CHANNEL}, actor)
    mid = store.add_message({'TaskId': tid, 'ExternalId': f'own:note:{tid}', 'ConversationId': f'own:{tid}',
                             'Channel': CHANNEL, 'SourceName': SOURCE, 'Subject': title,
                             'FromName': 'You', 'SentAt': at, 'BodyText': str(body or '').strip(),
                             'Status': 'routed'})
    store.add_route(mid, tid, 'own', None, 'a note you left yourself - nothing is working it, and nothing will', [], actor)
    store.audit('task', tid, 'note', actor, detail={'at': at})
    return {'taskId': tid, 'messageId': mid, 'at': at}
