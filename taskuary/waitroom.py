"""The waiting room: what the owner thinks of WHILE an agent is working, held until it stops.

Ideas arrive mid-run - "also handle the null case", "rename that flag", "check the other repo" -
and both ways of giving them to a coding agent were bad: interrupt it (an agent mid-edit loses
its thread; "LLMs Get Lost in Multi-Turn Conversation" puts the turn-splitting tax at ~-39%,
almost all of it unreliability), or hold them in your head and retype them when it finally
stops. So they queue HERE, on the task, and are typed into the session as ONE batch at the next
boundary: the agent parked at its prompt (terminal silent for IDLE_WAITING seconds - the same
fact the Board reads as "waiting on you"). Except when it parked because it ASKED something:
then the question is the owner's to answer and the notes wait behind it - feeding new work to an
agent that is waiting on an answer buries the question under it.

A session that has ENDED with notes still waiting (headless run finished, TUI closed) reopens
one on the same task with the notes as the ask - same task, fresh agent, never a chained session.
Affinity's cousin: dispatchq queues TASKS behind an agent; the waiting room queues WORDS for one.
"""
import re, threading, time
from loguru import logger
from .store import task_ref

# What a parked agent's last lines look like when it is waiting on the OWNER rather than done: a
# question, a y/n, a numbered chooser (Claude Code's permission and AskUserQuestion menus), a
# "press enter". Judged on the tail only - a question in the middle of a report is not a stop.
_QUESTION = re.compile(r'\?\s*$|\b(y/n|yes/no|do you want|would you like|should i|which (one|of these)|press enter|'
                       r'choose an option|select an option|enter to (confirm|select))\b|^\s*[❯>]\s*\d+\.', re.I)
TAIL_LINES = 6
WATCH_EVERY = 10          # seconds between looks - delivery lands within IDLE_WAITING + this of the agent parking
MAX_BATCH = 6000          # chars typed in one go; a TUI paste past this is asking for dropped frames


def looks_like_question(tail) -> bool:
    lines = [str(l) for l in (tail or []) if str(l).strip()][-TAIL_LINES:]
    return any(_QUESTION.search(l) for l in lines)


def batch(notes: list, after_restart: bool = False) -> str:
    """The notes as one typed message. Flattened to one line: in a TUI a newline is Enter."""
    n = len(notes)
    head = (f'The owner left {n} note{"s" if n > 1 else ""} for you after the last session ended. Take them in order:'
            if after_restart else
            f'While you were working, the owner queued {n} note{"s" if n > 1 else ""} for you. Take them in order, '
            'after finishing the step you are on; if one conflicts with work already done, say so instead of undoing it:')
    return ' '.join((head + ' ' + ' '.join(f'({i}) {str(x.get("Note") or "").strip()}' for i, x in enumerate(notes, 1))).split())[:MAX_BATCH]


def state(store, tid: int) -> tuple:
    """('working'|'asking'|'parked'|'no_session', live Term or None) - where the agent on this
    task stands right now, read off the terminal's silence and its last lines."""
    from . import terminal as term
    t = next((x for x in term.SESSIONS.values() if x.task_id == tid and x.alive), None)
    if t is None:
        return ('working', None) if any(r.get('TaskId') == tid for r in store.running_runs()) else ('no_session', None)
    if t.idle() < term.IDLE_WAITING: return 'working', t
    return ('asking' if looks_like_question(t.tail(TAIL_LINES)) else 'parked'), t


def add(store, tid: int, note: str, actor: str = 'owner') -> dict:
    """Queue one note on a task. An agent already parked gets it at once; otherwise it waits."""
    note = (note or '').strip()
    if not note: raise ValueError('empty note')
    if not store.get_task(tid): raise ValueError(f'no task {tid}')
    wid = store.add_waiting(tid, note, actor)
    store.audit('task', tid, 'waitroom_add', actor, detail={'wid': wid, 'chars': len(note)})
    return {'wid': wid, **deliver(store, tid)}


def deliver(store, tid: int) -> dict:
    """Hand this task's waiting notes over IF the agent has stopped. {'delivered': n, 'state': ...}
    - 'held' states are the ones where nothing moved: working, asking, closed, full."""
    from . import terminal as term
    from .ingest import auto_sessions
    notes = store.waiting_notes(tid)
    if not notes: return {'delivered': 0, 'state': state(store, tid)[0]}
    st, t = state(store, tid)
    if st == 'parked':
        term.type_into(t, batch(notes))
        store.deliver_waiting([x['WId'] for x in notes], 'typed')
        store.add_comment(tid, 'router', 'agent', f'{len(notes)} waiting-room note(s) typed into the live session once the agent stopped.')
        store.audit('task', tid, 'waitroom_deliver', 'router', 'agent', {'n': len(notes), 'how': 'typed'})
        return {'delivered': len(notes), 'state': 'parked'}
    if st == 'no_session':
        task = store.get_task(tid) or {}
        if task.get('Status') not in ('open', 'in_progress'): return {'delivered': 0, 'state': 'closed'}
        if len([x for x in term.SESSIONS.values() if x.alive]) >= auto_sessions(store): return {'delivered': 0, 'state': 'full'}
        agent = store.get_settings().get('default_agent') or 'coder'
        term.start_on_task(store, tid, agent, instruction=batch(notes, after_restart=True), actor='router')
        store.deliver_waiting([x['WId'] for x in notes], 'seeded')
        store.add_comment(tid, 'router', 'agent', f'Reopened a session for {len(notes)} waiting-room note(s) - the previous one had ended.')
        store.audit('task', tid, 'waitroom_deliver', 'router', 'agent', {'n': len(notes), 'how': 'seeded'})
        return {'delivered': len(notes), 'state': 'restarted'}
    return {'delivered': 0, 'state': st}


def tick(store) -> int:
    """Every task with notes waiting: deliver where its agent has stopped."""
    n = 0
    for tid in store.tasks_with_waiting():
        try: n += deliver(store, tid)['delivered']
        except Exception as e: logger.warning(f'waiting room: {task_ref(tid)}: {e}')
    return n


def watch(store):
    """The clock. Silence is the signal, and only a clock can notice silence."""
    def loop():
        while True:
            time.sleep(WATCH_EVERY)
            try: tick(store)
            except Exception as e: logger.warning(f'waiting room tick failed: {e}')
    threading.Thread(target=loop, daemon=True).start()


def later(store, delay: float = 3.0):
    """Look shortly - called from a dying session's own pump thread, which must not host the
    next session's startup."""
    tm = threading.Timer(delay, lambda: _safe(store))
    tm.daemon = True
    tm.start()

def _safe(store):
    try: tick(store)
    except Exception as e: logger.warning(f'waiting room tick failed: {e}')
