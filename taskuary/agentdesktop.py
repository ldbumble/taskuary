"""AGENT DESKTOP: an agent reads and operates the owner's desktop apps through the OS accessibility tree (the owner, 2026-10-31: "agent
desktop from the same vercel package we use for browser ... have it built in connector if it works").

agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0, npm `agent-desktop`) is agent-browser's sibling: a Rust CLI for
Windows, macOS and Linux that prints an app's UI as JSON with a ref per control (`snapshot --app X -i`) and acts on a ref (`click`,
`set-value`, `press`...). Not pixels: the structured rung docs/browser-vs-computer-use.md asked for first. Verified on the owner's
Windows 11 box 2026-10-31 with 1.0.2: list-apps, snapshot, click (Calculator 7 + 5 = 12), set-value into a WinForms box, screenshot.
Ref actions there are UI Automation calls that neither move the mouse nor take focus; `type`, `focus` and the multi-clicks need
`--headed`, which takes the owner's foreground - and Windows refuses that from a background process, so set-value is the road.

WHAT KEEPS IT SAFE, the browser's rules applied to the desktop:
- OFF BY DEFAULT. Its connector card is seeded off (store.py); off, or not installed, no agent is told of it and every act of
  agent-desktop in one of our sessions is refused where it runs (gate).
- ONLY ON A TASK MARKED "needs desktop" (WANTS, the owner 2026-10-31): the card on is not enough - an unmarked task's agent is told
  nothing and its acts are refused.
- NEVER ON A STRANGER'S TASK: a stranger's words do not get the owner's desktop to drive, as they do not get the browser.
- AN ACT THAT CAN'T BE UNDONE WAITS FOR THE OWNER'S PRESS. A command that only looks (LOOKS: snapshot, find, get, list-...) passes.
  Any other goes to the model with the control it names (`get <ref>`); send, pay, delete, submit - or unsure, or no verdict - is held
  as a proposal (proposals.ACTIONS 'desktop_act'), Approve and Dismiss. Approved, Taskuary runs that exact command; a ref names one
  control, and agent-desktop itself refuses it (STALE_REF) once that control is gone - never another control in its place (its
  README; measured: an older snapshot's ref to a button still there still presses that button).
- With no AI connected, plain typing (set-value, type) with no line break passes and every other act waits.
- The sign-in vault is the browser's alone: agents are told never to type a password into an app and to hand a sign-in to the owner.

Every act is caught at the command, on every AI (gate: the `agent-desktop` first on a task session's PATH is Taskuary's). What this
does not cover, said as browsergate says it: an agent that drives the desktop some other way than that command.
"""
import json, re, subprocess
from loguru import logger

TYPE, EXE = 'agent_desktop', 'agent-desktop'
DOCS = 'https://github.com/vercel-labs/agent-desktop'
INSTALL = 'npm install -g agent-desktop'
# its commands that only LOOK - its grammar, from `agent-desktop --help` (1.0.2). Every other command is judged.
LOOKS = frozenset('''snapshot find get is screenshot list-surfaces list-apps list-windows list-displays list-notifications wait status
permissions version skills help trace session scroll scroll-to hover'''.split())
# its options that take a value, so the value is not read as the command
VALUED = frozenset('--session --agent-id --trace --screenshot --wait-for --wait-for-gone --wait-timeout --property --app --window-id '
                   '--timeout --arg --env --cwd --surface --root --max-depth'.split())
TYPES = frozenset('set-value type'.split())     # what passes when no AI is connected to judge: typing into a box
JUDGE_WAIT = 45.0
from .gate import HELD_SAID as HELD, NOT_RUN_SAID as NOT_RUN          # ...one wording for every road's hold (gate.py)


# ── is it here, and is it on ──────────────────────────────────────────────────────────────────────────────────────────────
def _unsure() -> str:
    from .say import HELD
    return HELD['unsure_undo']          # his words for the judge's doubt (say.owner), never "the AI could not tell"


def path() -> str:
    from . import pathcache
    return pathcache.which(EXE) or ''
def installed() -> bool: return bool(path())
def card(store) -> dict: return (store.get_connector_by_type(TYPE) or {}) if store else {}
def on(store) -> bool: return bool(card(store).get('Active')) and installed()


# A TASK MARKED "needs desktop" is the only one that gets it (the owner, 2026-10-31): the card on is not enough. The mark is a tag,
# as "needs a browser" is (browserview.WANTS): the New sheet's box, the task's mark (POST /api/tasks/{id}/desktop), or triage reading
# the work as done in a desktop app with the card on (mark_from_triage). Unmarked, the agent is told nothing and the hook refuses.
WANTS = 'needs:desktop'
HOW = 'To use it, turn the Agent Desktop card on and mark a task "needs desktop".'


def wanted(task: dict | None) -> bool:
    "Is this task marked \"needs desktop\"?"
    return bool(re.search(rf'(^|[\s,]){re.escape(WANTS)}([\s,]|$)', str((task or {}).get('Tags') or '')))


def offered(store, tid: int, pick: str = '') -> bool:
    "Does this task's agent get the desktop? The card on, the task marked, a CLI with hands, the owner's own task - never the dock or a stranger's."
    if not on(store) or not wanted(store.get_task(tid)): return False
    from . import general
    return general.browser_offered(store, tid, pick)


def mark(store, tid: int, want: bool = True, actor: str = 'owner') -> bool:
    "Mark (or unmark) a task \"needs desktop\". True when it now carries the mark."
    if not store.get_task(tid): raise ValueError('task not found')
    store.tag_task(tid, WANTS, on=want, actor=actor)
    return want


def mark_from_triage(store, tid) -> bool:
    """Mark the task when triage said its work is done in a desktop app (its verdict's needs_desktop) - only with the card on, never on a
    stranger's task, said once on the task. True when it now wants the desktop. The doors that start an agent call it (ingest.mark_browser's)."""
    t = store.get_task(tid) if tid else None
    if not t: return False
    if wanted(t): return True
    if not on(store): return False
    for r in store._rows("SELECT VerdictJson FROM route WHERE TaskId=? AND VerdictJson LIKE '%\"needs_desktop\"%' ORDER BY RouteId DESC LIMIT 5", (tid,)):
        try: v = json.loads(r.get('VerdictJson') or 'null') or {}
        except (TypeError, ValueError): continue
        if not isinstance(v, dict) or not isinstance(v.get('needs_desktop'), bool): continue
        if not v['needs_desktop']: return False
        from . import origin
        try:
            if origin.of_task(store, tid)[0] == 'stranger': return False
        except Exception as e: logger.debug(f'desktop: origin unread on task {tid}, not marked - {e}'); return False
        store.tag_task(tid, WANTS, actor='triage')
        store.add_comment(tid, 'triage', 'agent', 'Triage read this as work in a desktop app - the agent may use Agent Desktop on it, '
                          'and anything that would send, pay or delete waits for your Approve.')
        return True
    return False


def _run(args: list, wait: float) -> tuple:
    "(exit code, output). Output to a file (spawn.output): on macOS the CLI keeps a command host that would inherit a pipe and never let it end."
    from . import spawn
    exe = path()
    if not exe: raise RuntimeError(f'agent-desktop is not installed - {INSTALL}')
    try: return spawn.output([exe, *args], wait)
    except subprocess.TimeoutExpired: raise RuntimeError('agent-desktop did not answer in time')


def _envelope(said: str) -> dict:
    "Its one JSON envelope ({ok, data} or {ok, error}); {} when the output is not one."
    try: return json.loads(said.strip().splitlines()[-1]) if said.strip() else {}
    except (ValueError, IndexError): return {}


def test() -> str:
    "The card's Test: the installed version and what the OS lets it do, in its own words."
    rc, said = _run(['status'], 30)
    st = _envelope(said)
    if rc != 0 or not st.get('ok'): raise RuntimeError(f"agent-desktop answered: {((st.get('error') or {}).get('message') or said)[-300:]}")
    d = st.get('data') or {}
    acc = ((d.get('permissions') or {}).get('accessibility') or {}).get('state') or 'unknown'
    tip = ' - on macOS run `agent-desktop permissions --guide` to grant it' if acc not in ('granted', 'not_required') else ''
    return f"agent-desktop {d.get('version') or '?'} on {d.get('platform') or '?'} - accessibility {acc}{tip}. {HOW}"


# ── what the agent is told ────────────────────────────────────────────────────────────────────────────────────────────────
# ...and THE LAST PRESS IS THE OWNER'S, IN THE APP (the owner, 2026-11-05): the work is set up in the app and they press it there (ready())
def _hold_line() -> str:
    from .gate import brief
    return brief('desktop')


def brief() -> str:
    "What an agent with the owner's desktop needs to know: how to drive it, and where the line is."
    return ('THE OWNER\'S DESKTOP APPS are yours to read and operate with `agent-desktop` (the owner turned it on) - for a desktop app that '
            'has no connector and no web page: prefer a connector, then the browser, then this. It reads the app\'s real UI through '
            'the accessibility tree, not pixels. Before the first use run `agent-desktop skills get desktop` and `agent-desktop skills '
            'get platform` and follow them. The loop: `agent-desktop list-apps`, `agent-desktop snapshot --app <name> -i --compact` '
            '(every control with a ref like @s8f3k2p9:e8), act on ONE ref, snapshot again to check. A ref belongs to its snapshot: '
            'after STALE_REF, snapshot again. Prefer `set-value <ref> <text>` to `type`, and NEVER pass --headed, run focus-window, or '
            'press a shortcut that switches windows: the owner is using this screen, and the default acts without moving their mouse or '
            'taking their focus. In PowerShell quote every ref (\'@s8f3k2p9:e8\'). Every command prints one JSON envelope: judge it by '
            '`ok` and the exit code, retry only when error.disposition.retry is "safe". Never type a password, code or card number '
            'into an app, never read the clipboard for one, and never touch Taskuary\'s own window: a sign-in is the owner\'s - end '
            'your turn and say what they need to do. Snapshots can hold private text: never paste one into a reply, a file or a post. '
            + _hold_line())


# ── which part of a shell command is a desktop act ────────────────────────────────────────────────────────────────────────
def _verb_at(a: list) -> int:
    i = 0
    while i < len(a) and a[i].startswith('-'): i += 2 if a[i] in VALUED and '=' not in a[i] else 1
    return i


def acts(cmd: str) -> list:
    """Every agent-desktop call in a shell command that is not only a look: [{'args': [...], 'verb': 'click'}]. One that cannot be read
    is an act with verb '?' - judged like any other, never let through for being hard to read (browsergate.acts)."""
    from .browsergate import _head, _segments, broke, names
    if not names(cmd, EXE): return []
    segs = _segments(cmd)
    if segs is None: return [{'args': [], 'verb': '?', 'raw': str(cmd)[:400]}]
    out = []
    for argv in segs:
        a = _head(argv, EXE)
        if a is None:
            for t in argv[1:]:                  # `powershell -Command "agent-desktop click '@s1:e2'"`: a command of its own
                if names(t, EXE) and ' ' in t.strip(): out += acts(t)
            continue
        i = _verb_at(a)
        verb = a[i].lower() if i < len(a) else ''
        if verb and verb not in LOOKS: out.append({'args': a, 'verb': verb, **({'nl': True} if broke(a) else {})})
    return out


def typing(act: dict) -> bool:
    "Only typing into a box? By the verb, never the text - and text that breaks a line is not plain typing (its Enter can send)."
    a = act.get('args') or []
    i = _verb_at(a)
    return i < len(a) and a[i].lower() in TYPES and act.get('verb') in TYPES and not act.get('nl') and not any('\n' in t or '\r' in t for t in a)


def _ref(act: dict) -> str: return next((t for t in act.get('args') or [] if re.match(r'^@[\w-]+:e\d+$', t)), '')


def control(act: dict) -> dict:
    "{role, name} of the control the act names, asked of agent-desktop itself; {} when it names none or cannot be read."
    ref = _ref(act)
    if not ref: return {}
    a = act['args']
    own = ('--session', '--agent-id')            # its ref lives in the agent's snapshot namespace, so it is asked there
    scope = [t for i, t in enumerate(a) if t in own or t.split('=', 1)[0] in own or (i and a[i - 1] in own)]
    out = {}
    for prop in ('role', 'text'):
        try: rc, said = _run(['get', ref, '--property', prop, *scope], 15)
        except Exception as e: logger.debug(f'desktop: no {prop} of {ref} - {e}'); continue
        v = (_envelope(said).get('data') or {}) if rc == 0 else {}
        val = v.get('value') if isinstance(v, dict) else v
        if val not in (None, ''): out['role' if prop == 'role' else 'name'] = str(val)[:200]
    return out


def what(act: dict, ctl: dict) -> str:
    "'click the \"Send\" button' - the act said by the control it names; the command itself when it names none."
    from .browsergate import _cmd
    if not ctl: return _cmd(act, EXE)
    return f"{act['verb']} the \"{ctl.get('name') or ''}\" {ctl.get('role') or 'control'}".replace(' "" ', ' ')


# THE SAME QUESTION AS THE BROWSER'S (redesign R5, 2026-11-23): its own list - "change a setting, install, close unsaved work" - held what the owner's
# rule lets run; one table (gate.TABLE) says what waits, and the same separate guard model reads the app's control as fenced data
def _system() -> str:
    from .browsergate import system
    return system('desktop', 'APP') + ' Also name "app": the app, as its window says it.'


def judge(store, todo: list, ctls: list, brain=None, wait: float = None) -> list:
    "[{hold, what, why}] for each act of the line, in order, from one ask under JUDGE_WAIT (browsergate.judge's road, each act with its control)."
    from .browsergate import _late, once, timed
    keys = [('desktop', _cmd_of(a) if not c else f"{c.get('role')} {c.get('name')}", a.get('verb') or '') for a, c in zip(todo, ctls)]
    return once(keys, lambda: timed(lambda: _judge(store, todo, ctls, brain), JUDGE_WAIT if wait is None else wait, [_late(what(a, c)) for a, c in zip(todo, ctls)]))
def _cmd_of(a: dict) -> str:
    from .browsergate import _cmd
    return _cmd(a, EXE)


def _judge(store, todo: list, ctls: list, brain=None) -> list:
    from .browsergate import _cmd, _late, ask_acts, wants
    from .terminal import fence
    user = 'THE COMMANDS THE AGENT IS ABOUT TO RUN, IN THIS ORDER, EACH WITH THE CONTROL IT NAMES:\n' + ''.join(
        f"ACT {i}: {fence(_cmd(a, EXE))}\n  ITS CONTROL: {fence(json.dumps(c) if c else '(none, or it could not be read)')}\n" for i, (a, c) in enumerate(zip(todo, ctls), 1))
    try: vs = ask_acts(store, brain, _system(), user, wants(_item_app()), len(todo))
    except Exception as e:
        logger.debug(f'desktop: no verdict on {[a["verb"] for a in todo]} - {e}')
        return [_late(what(a, c)) for a, c in zip(todo, ctls)]
    if vs is None: return [{'hold': False, 'what': what(a, c), 'why': ''} if typing(a) else
                           {'hold': True, 'what': what(a, c), 'why': 'no AI is set up to judge it, so it waits for you'} for a, c in zip(todo, ctls)]
    return [_verdict(v, what(a, c)) for a, c, v in zip(todo, ctls, vs)]


def _verdict(v: dict | None, w: str) -> dict:
    "One verdict read by the table (browsergate.rule_of), as the browser's is."
    from .browsergate import rule_of
    if v is None: return {'hold': True, 'what': w, 'why': "the AI's answer could not be read, so it waits for you"}
    said, app = ' '.join(str(v.get('what') or '').split())[:200] or w, ' '.join(str(v.get('app') or '').split())[:60]
    hold, why, _k = rule_of(v)
    if not hold: return {'hold': False, 'what': said, 'why': ''}
    return {'hold': True, 'what': said, 'why': _unsure() if why == rule_of({})[1] else why, **({'app': app} if app else {})}


def key(act: dict, ctl: dict, v: dict) -> str:
    "What makes two desktop presses the same decision (gate.key): the app, the verb and the control it names - its command where it names none."
    on_ = f"{ctl.get('role') or ''} {ctl.get('name') or ''}".strip() or ' '.join(act.get('args') or [])
    return f"desktop|{_app(act, v).lower()}|{act.get('verb') or ''} {on_}"


# ── the hook's answer ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _pending(store, tid: int, sid: str, args: list):
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,)):
        try: p = json.loads(r.get('DraftText') or '{}')
        except ValueError: continue
        if p.get('action') == 'desktop_act' and p.get('sid') == str(sid) and p.get('args') == args: return r
    return None


def check(store, tid: int, sid: str, cmd: str, brain=None) -> dict:
    """{} lets the command run; a refusal holds it. Off, or a stranger's task: every act refused. ONE act held holds the whole line."""
    from .browsergate import _deny
    from . import origin
    todo = acts(cmd)
    if not todo: return {}
    if not on(store): return _deny('Agent Desktop is off on this computer - the owner turns it on under Connections. Do not drive desktop '
                                   'apps another way; say what you would have done instead.')
    try: stranger = origin.of_task(store, tid)[0] == 'stranger'
    except Exception: stranger = True                                  # unreadable is not a vouch
    if stranger: return _deny('This task carries a message from someone the owner has not vouched for, so it does not drive the '
                              "owner's desktop. Say what you would have done instead.")
    if not wanted(store.get_task(tid)):
        return _deny('This task is not marked "needs desktop", so it does not drive the owner\'s desktop. Say in one line that the owner can '
                     'mark it "needs desktop" if the work needs a desktop app, and what you would have done there.')
    ctls = [control(a) for a in todo]
    for a, c, v in zip(todo, ctls, judge(store, todo, ctls, brain)):
        if not v['hold']: continue
        if not a['args']: return _deny(f'{NOT_RUN}: a desktop command it could not read. Run each agent-desktop command on its own line.')
        # ...THE ONE RULE (gate.decide), as the browser's: the same press on the same control of the same app he already approved on this
        # task runs; one he dismissed since his last line is his no, never a second card
        from . import gate
        step = {'what': v['what'], 'why': v['why'], 'key': key(a, c, v)}
        how, told = gate.decide(store, tid, [step])
        if how == 'approved':
            if told: store.add_comment_once(tid, 'taskuary', 'agent', told)
            continue
        if how == 'dismissed': return _deny(told)
        if watched(tid, sid): return ready(store, tid, sid, a, v)
        if not _pending(store, tid, sid, a['args']):
            from . import proposals
            proposals.queue(store, tid, {'action': 'desktop_act', 'sid': str(sid), 'args': a['args'], 'command': ' '.join([EXE, *a['args']]),
                                         'what': v['what'], 'why': v['why'], 'keys': [step['key']]}, 'agent')
            store.audit('task', tid, 'desktop_act_held', 'taskuary', 'system', {'verb': a['verb'], 'why': v['why']})
        from .selfclose import CARD_TAIL
        return _deny(f"{HELD}: {v['what']} ({v['why']}). {CARD_TAIL}")
    return {}


# ── where the owner is there: it's ready in the app, and they press it there ──────────────────────────────────────────────
# THE OWNER'S OWN PRESS, IN THEIR OWN APP (the owner, 2026-11-05: "if it's a browser agent or desktop agent just show it and hit the approval
# there"). The app is already on the owner's screen - agent-desktop drives their real windows - so there is nothing to show and nothing
# Taskuary watches: one plain line in the chat, the agent waits, and the owner's next typed line is its next turn. A run nobody watches
# keeps the Approve card.
READY = 'desk:'                 # its request id's prefix: an ask the owner answers by typing, never a page to draw (browserview.TURN_PREFIX)
READY_LINE = "It's ready in {app}; press it there."
def _item_app() -> dict:
    from .browsergate import ITEM
    return {**ITEM, 'properties': {**ITEM['properties'], 'app': {'type': 'string'}}}


def watched(tid: int, sid: str) -> bool:
    "Is the owner there: a live session of ours on this task (a chat, a pane) - where a line to them is read?"
    from . import terminal as term
    s = term.SESSIONS.get(str(sid))
    return bool(s is not None and getattr(s, 'alive', False) and getattr(s, 'task_id', None) == tid)


def _app(act: dict, v: dict) -> str:
    "The app the act is in: the command's own --app, else the one the judge named, else 'the app'."
    a = act.get('args') or []
    named = next((a[i + 1] for i, t in enumerate(a[:-1]) if t == '--app'), '') or next((t.split('=', 1)[1] for t in a if t.startswith('--app=')), '')
    return ' '.join(str(named or v.get('app') or '').split())[:60] or 'the app'


def ready(store, tid: int, sid: str, act: dict, v: dict) -> dict:
    "Say it's ready in the app, as an ask the owner answers by typing, and refuse the agent: it ends its turn and waits."
    from . import workerstate as ws
    from .browsergate import _deny
    text = READY_LINE.format(app=_app(act, v))
    rid = READY + ws.request_id_for(f'{sid} {text}')
    if ws.record(store, tid, sid, 'input_needed', request_id=rid, text=text, source='api'):
        store.audit('task', tid, 'desktop_act_ready', 'taskuary', 'system', {'verb': act.get('verb'), 'why': v.get('why')})
    return _deny(f"{HELD}: {v['what']} ({v['why']}) is the owner's own press, in the app on their screen. Taskuary told them \"{text}\" - "
                 "do not say it again. Go on with the rest of the job; you are told what happened once they press it.")


# ── approved: run it; dismissed: say so ───────────────────────────────────────────────────────────────────────────────────
def perform(store, tid: int, p: dict, run=None) -> dict:
    """The owner's yes: run the held command as it was. A control gone since makes agent-desktop refuse its ref (STALE_REF) - said
    as "nothing was done", never retried on a guess. `run`: the runner (tests stand one in)."""
    from .browsergate import _tell, NEXT
    from . import gate
    gate.remember(store, tid, p.get('keys'), 'approved')       # his yes to this press on this control stands for the task
    args = list(p.get('args') or [])
    if not args: raise RuntimeError('this held act names no desktop command')
    if not on(store): raise RuntimeError('Agent Desktop is off on this computer now - nothing was done. Turn it on under Connections, and '
                                         'the agent holds the step anew.')
    rc, said = (run or (lambda a: _run(a, 60)))(args)
    env = _envelope(said)
    if rc != 0 or env.get('ok') is False:
        err = env.get('error') or {}
        if err.get('code') in ('STALE_REF', 'AMBIGUOUS_TARGET', 'APP_NOT_FOUND', 'WINDOW_NOT_FOUND'):
            raise RuntimeError(f"the app has changed since this was held ({err.get('code')}) - nothing was done. Nothing on this card waits "
                               'now: the agent looks again and holds the step anew.')
        raise RuntimeError(f"agent-desktop refused it: {(err.get('message') or ' '.join(str(said or '').split()))[-300:]}")
    _tell(store, tid, f"The owner approved it and Taskuary ran `{p.get('command')}`. It said: {' '.join(str(said).split())[-300:] or 'done'}. "
                      'Snapshot the app again, then ' + NEXT[0].lower() + NEXT[1:], wake=True)
    store.audit('task', tid, 'desktop_act_done', 'owner', 'human', {'what': p.get('what'), 'command': str(p.get('command') or '')[:300]})
    return {'performed': p.get('what') or p.get('command')}


def declined(store, tid: int, p: dict) -> None:
    from .browsergate import declined as said
    said(store, tid, p)
