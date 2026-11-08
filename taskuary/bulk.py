"""ONE PRESS OVER ROWS THE MODEL CHOSE (the owner, 2026-10-28: "yes on assistant that can run the whole app" - "dismiss the spam",
"put these three on my list", "block them and stop them").

A selector names a set by what it IS (a sender, a kind, an age); a judgement - "what looks like spam" - is no field. So SELECT takes
`keys` as well: the handles pipe.read printed (TQ-0123, m4321). The model reads the rail, picks the rows, and names them; code checks
every one is on the rail NOW and refuses what a sweep never touches - work waiting on the owner (for a put-down), an agent at work, a
draft waiting for its Send, a goal. Each row then runs the same operation its own button runs (operations.propose + run_proposal), so
the audit trail, the evidence and the Undo lines are the one road's. The receipt lists every row as its link - opening one is how it is
put back with its own button (the owner's ruling: no Undo button, no confirm card).

The set comes from the owner's words in this turn: the mail pipe.read quotes is data the model judged, never an instruction to act."""
import re
from loguru import logger
from . import lanes, operations, words
from .buttons import label as L
from .store import task_ref

AGENT_LANES = ('blocked', 'working', 'queued')
DRAFT_KINDS = ('review', 'not_sent', 'unsendable', 'wrapup')
SHOWN = 40                # rows a receipt lists one by one; past it, how many more
VERBS = {'pipe.remove': 'remove', 'pipe.block': 'block', 'pipe.mine': 'mine'}


def handles(keys) -> set:
    """'TQ-0123', 'm4321', 'task:12', 'msg:7' - each as the pile key it names. A bare number is a task ref."""
    out = set()
    for k in ([keys] if isinstance(keys, (str, int)) else keys or []):
        s = str(k).strip().lower()
        if m := re.fullmatch(r'(?:tq-?)?0*(\d+)', s): out.add(f'task:{int(m.group(1))}')
        elif m := re.fullmatch(r'(?:m|msg:?|mid:?)\s*(\d+)', s): out.add(f'msg:{int(m.group(1))}')
        elif m := re.fullmatch(r'task:(\d+)', s): out.add(f'task:{int(m.group(1))}')
        elif s: out.add(s)
    return out


def named(i: dict, want: set) -> bool:
    """A row is named by its own key, its task's ref or its message's m-number - a task row that came from a mail answers to both."""
    return bool({i.get('key'), f"task:{i['tid']}" if i.get('tid') else None, f"msg:{i['mid']}" if i.get('mid') else None} & want)


def refusal(i: dict, verb: str) -> str:
    """Why a sweep leaves this row alone - '' when it may go. `verb`: remove | block | mine | clear | close | defer."""
    if i.get('lane') in AGENT_LANES or i.get('working'): return 'an agent is on it'
    if i.get('rid') or i.get('lane') == 'approve' or i.get('kind') in DRAFT_KINDS: return 'a draft waits for your Send'
    if str(i.get('kind') or '').startswith('goal'): return 'a goal'
    if verb in ('remove', 'block') and lanes.on_you(i): return 'it waits on you'
    if verb == 'mine' and i.get('tid'): return 'already a task'
    if verb == 'block' and not i.get('mid'): return 'no sender to block'
    return ''


def link(i: dict) -> str:
    """The row as its link: its task while it has one, else its message - where its own buttons put it back."""
    ref = task_ref(i['tid']) if i.get('tid') else f"m{i['mid']}" if i.get('mid') else i.get('key') or '?'
    href = f"#task={i['tid']}" if i.get('tid') else f"#msg={i['mid']}" if i.get('mid') else ''
    who, title = ' '.join(str(i.get('who') or '').split()), ' '.join(str(i.get('title') or '').split())[:90]
    return f"- {f'[{ref}]({href})' if href else ref} {who + ' · ' if who else ''}{title}"


def listing_lines(ls: list) -> str: return '\n'.join(ls[:SHOWN] + ([f'- …and {len(ls) - SHOWN} more'] if len(ls) > SHOWN else []))
def listing(rows: list) -> str: return listing_lines([link(i) for i in rows])
def handle_of(line: str) -> str: return line[2:].split(' ', 1)[0]          # '[TQ-0012](#task=12)' out of a receipt line


def _run(store, kind: str, target: int, params: dict, actor: str) -> bool:
    from .concierge import run_proposal
    try: return run_proposal(store, operations.propose(store, kind, int(target), params, actor), actor).get('status') == 'done'
    except Exception as e: logger.warning(f'bulk: {kind} on {target} did not run - {e}'); return False


def act(store, verb: str, rows: list, actor: str = 'owner', learn: bool = False) -> dict:
    """Each row by its own button's operation. {done: [rows], stuck: [rows], rules: n} - audited with every key."""
    done, stuck, rules = [], [], 0
    if verb == 'block':
        seen = {}
        for i in rows:                           # one exclusion rule per sender, however many rows they sent
            em = str(i.get('email') or i.get('key')).lower()
            if em in seen: (done if seen[em] else stuck).append(i); continue
            seen[em] = _run(store, 'preference.sender_rule', i['mid'], {}, actor); rules += seen[em]
            (done if seen[em] else stuck).append(i)
    for i in rows if verb != 'block' else ():
        if verb == 'remove':
            ok = (_run(store, 'task.not_a_task', i['tid'], {'learn': learn}, actor) if i.get('tid')
                  else _run(store, 'message.file', i['mid'], {'learn': learn}, actor) if i.get('mid') else False)
        else: ok = bool(i.get('mid')) and _run(store, 'task.create_from_message', i['mid'], {'kind': 'task'}, actor)
        (done if ok else stuck).append(i)
    store.audit('pipe', 0, f'bulk_{verb}', actor, detail={'keys': [i.get('key') for i in done], 'stuck': [i.get('key') for i in stuck],
                                                         'learn': learn, 'rules': rules})
    return {'done': done, 'stuck': stuck, 'rules': rules}


# NOT OURS, TAKEN BACK (the owner, 2026-11-02: 'it should be "read" not marked as "Not ours"'). Rows put away as not ours are off the rail,
# so "mark them read" found nothing there and said "Marked 0 items read" - with the verdict still standing. A message the owner filed as not
# ours is put back to what it was, its verdict's marks taken back (the ignore route ingest.veto reads, the line it taught, the correction
# evidence triage weighs) - and pipe.clear then marks it read like any other row.
FILED = ('filed_not_ours', 'not_mine')            # the audit actions that keep what a message was before it was filed as not ours


def filed_not_ours(store, mid: int) -> bool:
    "Is this message put away by the owner's Not ours (or Archive) - its ignore route standing?"
    return bool(store._one("SELECT 1 x FROM route WHERE MessageId=? AND Decision='ignore' AND RoutedBy='owner' LIMIT 1", (int(mid),)))


def unfile(store, mid: int, actor: str = 'owner') -> bool:
    """Take back the owner's Not ours on one message: its status back, the ignore route, the taught line and the evidence withdrawn."""
    import json
    from . import memorylines
    if not filed_not_ours(store, mid): return False
    a = store._one(f"SELECT Detail FROM audit WHERE EntityType='message' AND EntityId=? AND Action IN ({','.join('?' * len(FILED))}) "
                   "ORDER BY Id DESC LIMIT 1", (int(mid), *FILED)) or {}
    try: was = (json.loads(a.get('Detail') or '{}') or {}).get('was')
    except ValueError: was = None
    store._exec("DELETE FROM route WHERE MessageId=? AND Decision='ignore' AND RoutedBy='owner'", (int(mid),))
    store.set_message_status(mid, was if was and was != 'ignored' else 'filed')
    for op in store.operations_for(message_ids=[int(mid)]):
        if op['Kind'] in ('message.file', 'message.archive') and op.get('Evidence') == 'recorded':
            store._exec('DELETE FROM correction WHERE OpId=?', (op['OpId'],)); store.update_operation(op['OpId'], {'Evidence': 'withdrawn'})
    memorylines.untaught(store, f'msg{mid}')
    store.audit('message', int(mid), 'not_ours_taken_back', actor, detail={'status': was or 'filed'})
    return True


SAID = {'remove': 'Filed as not ours', 'block': 'Blocked', 'mine': 'Put on your list'}
AFTER = {'remove': 'Filed, not deleted - search still finds them; open one to put it back.',
         'block': f"Their mail no longer reaches triage - a rule each under {words.name('rules')}.",
         'mine': 'Each is a task of yours now - no agent was started.'}


def receipt(verb: str, out: dict, refused: list, learn: bool = False) -> str:
    """Every row it touched, as its link, then what it left and why - the bulk act's whole receipt."""
    done, stuck = out['done'], out['stuck']
    n = len(done)
    head = (f"{SAID[verb]}: {n} {'row' if n == 1 else 'rows'}" + (f" from {out['rules']} {'sender' if out['rules'] == 1 else 'senders'}" if verb == 'block' else '')
            + '.' if n else 'Nothing went.')
    parts = [head] + ([listing(done), AFTER[verb] + (' Triage learns from it too, from now on.' if learn and verb == 'remove' else '')] if n else [])
    if stuck: parts += [f"{len(stuck)} would not go just then:", listing(stuck)]
    if refused:
        why = {}
        for i, w in refused: why.setdefault(w, []).append(i)
        parts += [f"Left alone - {w}: " + ', '.join(handle_of(link(i)) for i in rs[:12]) + (' …' if len(rs) > 12 else '') for w, rs in why.items()]
    return '\n'.join(p for p in parts if p)


# STOP AGENTS IN BULK (the capability map, 2026-10-28: "stop all the agents"): the set is the model's - the TQ refs agents.now or pipe.read
# printed, or every one running - and each goes by the task page's own Stop and save (agent.stop, wrap): written up and saved, never
# thrown away. Only an agent at work is stopped; a ref with none running is said, never pressed.
def running(store) -> list:
    """The tasks an agent is on now - a live session (terminal or assistant chat) or a run in the background - in task order."""
    from . import terminal
    try: live = {int(i['taskId']) for i in terminal.live_sessions(0, details=False) if i.get('taskId')}
    except Exception: live = set()
    return sorted(live | {int(r['TaskId']) for r in (store.running_runs() or []) if r.get('TaskId')})


def tids(refs) -> list:
    "'TQ-0012', 12, 'task:12' -> 12; a handle that names no task is dropped."
    return sorted({int(k[5:]) for k in handles(refs) if k.startswith('task:')})


def stop(store, ts: list, actor: str = 'owner') -> dict:
    "Each by the page's Stop and save. {done: [rows], stuck: [rows]} - audited with every task."
    from .general import handles as is_chat
    done, stuck = [], []
    for t in ts:
        task = store.get_task(t) or {}
        (done if _run(store, 'agent.stop', t, {'wrap': True}, actor) else stuck).append({'tid': t, 'title': task.get('Title') or '', 'chat': is_chat(task)})
    store.audit('pipe', 0, 'bulk_stop', actor, detail={'tasks': [i['tid'] for i in done], 'stuck': [i['tid'] for i in stuck]})
    return {'done': done, 'stuck': stuck}


STOP_AFTER = 'Each was written up and saved on its task, which stays open - {how} where it left off.'
def stop_receipt(out: dict, idle: list = ()) -> str:
    "Every agent it stopped, as its task's link, then any that would not stop, then the refs with none running."
    n, stuck = len(out['done']), out['stuck']
    parts = [f"Stopped and saved: {n} {'agent' if n == 1 else 'agents'}." if n else 'Nothing was stopped.']
    # ...in the words of each kind: a chat task carries on by typing, a coding one by Continue (general.carry_on, the owner 2026-11-07)
    chats = {bool(r.get('chat')) for r in out['done']}
    how = ('typing in its chat carries it on' if chats == {True} else f"{L('continue')} picks it up" if chats == {False}
           else f"typing in its chat carries it on (a coding agent: {L('continue')})")
    if n: parts += [listing(out['done']), STOP_AFTER.format(how=how)]
    if stuck: parts += [f'{len(stuck)} would not stop just then:', listing(stuck)]
    if idle: parts.append('No agent running on: ' + ', '.join(task_ref(t) for t in idle[:12]) + (' …' if len(idle) > 12 else '') + '.')
    return '\n'.join(parts)
