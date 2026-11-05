"""AN ACT IS SAID DONE ONLY WHEN IT LANDED (the owner, 2026-11-04: "stress test the assistant popup - it says it's doing things and it does
not do them"). A handler that came back without an error was taken as the act itself: "Done - Mark done · TQ-0002" stood over a task still
open, "Pressed Send to agent - an agent is on it now" over a start that never started, "Remembered ..." over a memory nobody wrote, "✓
Rewritten" over the same words or an empty box. The receipt was written from the PLAN - the handler was asked - and never from the STATE.

Here each act names what it promised, as a look at the store after it ran: `snap` before, `missed` after - '' when the promise holds, else
the reason in plain words ("TQ-0002 is still open"). operations.execute asks it for every operation (the chat, the task page and the phone
take that road alike), concierge asks it for the writes the chat makes itself; a reply's draft is the reply door's (server._rewritten). An act with no
promise here is unchecked - its handler's word stands, as before."""
from . import kinds
from .store import task_ref

CLOSED = ('done', 'dropped')


def _task(store, n): return store.get_task(int(n)) if n else None
def _docs(store): return tuple(store.get_doc(d) or '' for d in ('learned', 'style', 'soul', 'counsel'))
def _todo(store, n): return [(i.get('id'), i.get('text'), bool(i.get('done')), i.get('note')) for i in store.task_checklist(int(n))] if n else []
def _fields(t): return {k: v for k, v in (t or {}).items() if k not in ('UpdatedAt', 'Revision')}
def _notes(store, n): return len(store.list_comments(int(n))) if n else 0


def _complete(store, n, p, was, out):
    t = _task(store, n)
    if not t: return f'{task_ref(n)} is not there'
    if (out or {}).get('kept_open') or (out or {}).get('unsent'): return ''     # a send's close kept open says so itself (receipt_turn)
    return '' if t.get('Status') in CLOSED else f"{task_ref(n)} is still {t.get('Status') or 'open'}"

def _dropped(store, n, p, was, out):
    t = _task(store, n)
    return '' if not t or t.get('Status') == 'dropped' else f"{task_ref(n)} is still on your list ({t.get('Status')})"

def _reopened(store, n, p, was, out):
    t = _task(store, n)
    return f"{task_ref(n)} is still {t.get('Status')}" if t and t.get('Status') in CLOSED else ''

def _deferred(store, n, p, was, out):
    t, back = _task(store, n) or {}, bool(str(p.get('until') or '').strip())
    return '' if bool(t.get('RemindAt')) == back else f"{task_ref(n)} has {'no day to come back' if back else 'its day still set'}"

def _watched(store, n, p, was, out):
    t, off = _task(store, n) or {}, str(p.get('off')).strip().lower() in ('true', '1', 'yes')
    return '' if bool(t.get('WatchedAt')) != off else f"{task_ref(n)} is {'still' if off else 'not'} under Watching"

def _merged(store, n, p, was, out):
    t = _task(store, n)
    return '' if not t or t.get('Status') in CLOSED else f"{task_ref(n)} is still a task of its own"

def _changed(what):
    "The act changed `what` of the task - any of it: its row's fields, its to-dos, its notes."
    get = {'fields': lambda s, n: _fields(_task(s, n)), 'todo': _todo, 'notes': _notes}[what]
    def snap(store, n, p): return get(store, n)
    def missed(store, n, p, was, out):
        if (out or {}).get('already') or (out or {}).get('note') is not None and what == 'todo': return ''
        return '' if get(store, n) != was else {'fields': f'{task_ref(n)} did not change', 'todo': f"{task_ref(n)}'s to-dos did not change",
                                                'notes': f'no note landed on {task_ref(n)}'}[what]
    return snap, missed

def _started(store, n, p, was, out):
    o = out if isinstance(out, dict) else {}
    if o.get('started') or o.get('existing') or o.get('chat') or o.get('dispatch') == 'needs_repo': return ''
    t = o.get('taskId') or (n if p.get('_on') == 'task' else None)
    if t and store.get_dispatch(int(t)): return ''                                    # waiting its turn: queued, said so (funnel 'queued')
    return f"the agent on {task_ref(t) if t else 'it'} did not start"

def _continued(store, n, p, was, out):
    o = out if isinstance(out, dict) else {}
    return '' if o.get('continued') or o.get('started') or o.get('existing') else f'the work on {task_ref(n)} did not pick up'

def _remembered(store, n, p, was, out):
    o = out if isinstance(out, dict) else {}
    return '' if o.get('already') or _docs(store) != was else 'nothing was written to your memory'

def _setting(store, n, p, was, out):
    o = out if isinstance(out, dict) else {}
    key = o.get('key') or p.get('setting')
    if not key or 'value' not in o: return ''
    return '' if str(store.get_setting(key)) == str(o['value']) else f"{o.get('label') or key} is still {store.get_setting(key)!r}"

def _approved(store, n, p, was, out):
    rv = store.get_review(int(n)) or {}
    return f'the draft is still waiting for its Send' if rv.get('Status') == 'pending' and not (out or {}).get('queued') else ''

def _filed(store, n, p, was, out):
    m = store.get_message(int(n)) or {}
    return '' if not m or m.get('Status') != was else 'the message is still where it was'


_T = lambda store, n, p: None
# kind -> (snap before, missed after). `n` is the operation's target: a task, a message or a review by its id
PROMISES = {
    'task.complete': (_T, _complete), 'task.not_a_task': (_T, _dropped), 'task.reopen': (_T, _reopened),
    'task.defer': (_T, _deferred), 'task.watching': (_T, _watched), 'task.merge': (_T, _merged),
    'task.update': _changed('fields'), 'task.set_kind': _changed('fields'),
    'task.check': _changed('todo'), 'task.checklist': _changed('todo'), 'task.comment': _changed('notes'),
    'dispatch.prepare': (lambda s, n, p: None, lambda s, n, p, w, o: _started(s, n, {**p, '_on': 'task'}, w, o)),
    'agent.continue': (_T, _continued),          # agent.answer checks its own delivery (server: not delivered raises)
    'memory.remember': (lambda s, n, p: _docs(s), _remembered), 'setting.set': (_T, _setting),
    'review.approve': (_T, _approved), 'message.file': (lambda s, n, p: (s.get_message(int(n)) or {}).get('Status') if n else None, _filed),
}
# ...and a message handed to an agent: a start like any other - a to-do made for the owner promises only its task
AGENT_KINDS = kinds.AGENT


def snap(store, kind: str, target, params: dict | None):
    f = PROMISES.get(kind)
    if not f: return None
    try: return f[0](store, target, params or {})
    except Exception: return None


def missed(store, kind: str, target, params: dict | None, was, outcome) -> str:
    """'' when what `kind` promised is so now (or it promised nothing checkable), else the reason it is not, in plain words."""
    p = params or {}
    if kind == 'task.create_from_message':
        if str(p.get('kind') or '').lower() not in AGENT_KINDS or (outcome or {}).get('start_error'): return ''   # receipt_turn says a start_error
        return _started(store, target, p, was, outcome)
    f = PROMISES.get(kind)
    if not f: return ''
    try: return f[1](store, target, p, was, outcome) or ''
    except Exception: return ''                                     # a check that cannot read the store never turns a done act into a failure
