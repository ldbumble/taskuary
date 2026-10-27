"""WHERE A TASK IS UP TO, read from stages.json - the same file the task page reads (website/src/stages.js). Eight stages, each
with the parts the page draws for it: the main view, the drawer and what is in it, whether that drawer's tab is lit, where the
Advisor's section stands and the moves it is about (the owner, 2026-10-26: "are these modes defined well anywhere besides the UI ...
we should define this well"). The page decided all of it from its own facts in TaskPage (focusOf, mainOf, nextInDrawer) and the
Assistant was told none of it.

The RULES are the file's: the first whose fact holds wins. The page reads the facts from what it is drawing - a live terminal, the
white section; this side reads them from the task's rows (`facts`), so the task detail and the Assistant's CANVAS can say the stage
of a task nobody has open. Where the two could differ - a terminal that closed a second ago - the page's is what is on screen."""
import json
from pathlib import Path

_J = json.loads(Path(__file__).with_name('stages.json').read_text(encoding='utf-8'))
RULES = tuple((r.get('if'), r['stage']) for r in _J['rules'])
STAGE = {s['key']: s for s in _J['stages']}
KEYS = tuple(STAGE)
FACTS = tuple(f for f, _ in RULES if f)              # live, waiting, closed, drafted, result, owed, list


def of(facts: dict) -> str:
    """The stage the facts make: the first rule whose fact holds, else the last rule's (it has none)."""
    return next(s for f, s in RULES if not f or facts.get(f))


def parts(key: str) -> dict:
    """The stage's parts - main, shows, drawer, lit, advisor, verbs - or {} for no such stage."""
    return STAGE.get(key) or {}


def facts(store, t: dict, state: str | None = None) -> dict:
    """The rules' facts for a task, from its rows. `state` is its taskstate key (blocked, working, approve, theirs, closed...),
    read once by the caller - the detail already has it - else read here."""
    from . import kinds, taskstate
    tid = int(t['TaskId'])
    st = state or taskstate.state(store, t)
    closed = t.get('Status') in ('done', 'dropped') or st in ('closed', 'dropped')
    # ...somebody owed an answer: a message on it from someone, on a task the owner or a reply works - an agent's task answers in its Result
    msgs = [] if closed else (store.list_messages(tid) or [])
    sender = any(str(m.get('Direction') or 'in') == 'in' and str(m.get('Status') or '') != 'context' for m in msgs)
    try: checklist = bool(str(store.checklist_markdown(tid) or '').strip())
    except Exception: checklist = False
    return {'live': st in ('working', 'blocked'), 'waiting': st == 'theirs', 'closed': closed,
            'drafted': st == 'approve' or (not closed and bool(store.sent_reply(task_id=tid))),
            'result': st in ('saved', 'stopped', 'agentdone'),
            'owed': sender and str(t.get('Kind') or '') not in kinds.AGENT,
            'list': checklist or bool(str(t.get('DoneWhen') or '').strip())}


def state_of(store, t: dict, session=None) -> str:
    """taskstate's key for a bare task row - its latest review and run read here, as the list row carries them. `session`: its live
    session ({alive, waiting}), when the caller has the live ones."""
    from . import taskstate
    tid = int(t['TaskId'])
    rv, rn = store.pending_review(tid), (store.list_runs(tid) or [{}])[0]
    row = {**t, 'ReviewStatus': t.get('ReviewStatus') or ('pending' if rv else None), 'RunStatus': t.get('RunStatus') or rn.get('Status')}
    return taskstate.state(store, row, session, store.get_dispatch(tid))


def of_task(store, t: dict, state: str | None = None, session=None) -> str | None:
    """The stage of task `t`, or None when it cannot be read. `state`: its taskstate key when the caller has it (the task detail)."""
    try: return of(facts(store, t, state or state_of(store, t, session)))
    except Exception: return None
