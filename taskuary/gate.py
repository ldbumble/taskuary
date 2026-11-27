"""THE GATE: ONE TABLE OF WHAT WAITS FOR THE OWNER'S PRESS, ONE CHECK POINT EVERY ROAD CALLS (redesign R5, 2026-11-23).

The owner's rule: the agent does everything it can. Only an act that spends his money, sends his own private details, speaks for him to
other people, or deletes or cancels something of his waits for his press - one action card - and so does a permission (a read outside the
task's folders; a stranger's task never drives his browser or desktop). His press on that card, or the same step he approved earlier on the
task, or a connection he trusts to act on its own, covers it; his no stands until he writes again. That is TABLE below, and nothing else.

Six modules used to decide overlapping parts of this (browsergate, shellgate, readgate, acpgate, actrule, gatecmd, plus hooks' wiring), with
the brief to the agent written three times over in prose. Now:
  - TABLE is the one list of act kinds: whether each waits, why (in his words, on the card) and what it is (in the agent's brief and the
    judge's question). brief() writes every road's hold line from it; browsergate.SYSTEM writes the judge's question from it.
  - check() is the ONE check point: a CLI's PreToolUse hook (hooks.browser), the ACP road (tool_call), the API agent (apiagent) and the
    `agent-browser` / `agent-desktop` launcher first on every task session's PATH (main -> /api/agent/gate -> judge) all call it.
  - decide() is the one rule every held step meets before a card is filed: trusted, already approved on this task, or his no.
WHERE CODE CAN KNOW THE ACT IT DECIDES (the owner, 2026-11-23): a push, a publish, a mail from a script, a web write, a delete outside the
agent's folder, a read outside the task's folders - by each tool's own grammar (shellgate, readgate) - is held by code, whatever the agent
thinks. A BROWSER OR DESKTOP PRESS is the one place code cannot tell what a click does: there a SEPARATE guard model (llm job 'judge', never
the working agent) reads the page as fenced data, once per control per page, cached (browsergate.judge), and plain facts decide first where
they can - typing and filling a form's fields send nothing, a password box the agent typed makes a form an account's, his saved name and
the email he named are covered by his ask.

The readers of each road's grammar stay where they are (shellgate: the shell's; browsergate: the browser's and the page's; agentdesktop:
the desktop's; readgate: paths), and so do the runners of a pressed card (perform); none of them decides on its own.
"""
import collections, json, os, shlex, sys
from pathlib import Path
from loguru import logger

# ── THE TABLE ────────────────────────────────────────────────────────────────────────────────────────────────────────────
# press: True - one card for his press; None - refused outright, even on his yes; False - runs. why: said on the card and to the agent.
# head + more: what the act is, as the brief and the judge's question say it (head in capitals where the judge reads it).
Row = collections.namedtuple('Row', 'press why head more')
TABLE = {
    'money':   Row(True, 'it spends your money, so it waits for your press', 'SPENDS HIS MONEY',
                   '(pays, buys, orders, subscribes, upgrades a plan, enters or confirms a payment card)'),
    'private': Row(True, 'it sends your own details, so it waits for your press', 'SENDS HIS OWN PRIVATE DETAILS',
                   '(his real phone number, card, home address, ID or date of birth, anything personal of his - never a made-up value or a '
                   'login Taskuary generated)'),
    'speaks':  Row(True, 'it speaks for you to other people, so it waits for your press', 'SPEAKS FOR HIM', 'to other people (sends a message, posts, invites)'),
    'deletes': Row(True, 'it deletes or cancels something of yours, so it waits for your press', 'DELETES OR CANCELS', 'something of his'),
    'out':     Row(True, 'it leaves this computer', 'LEAVES THIS COMPUTER',
                   'from a shell (a push, a merge, a pull request, a publish, a mail from a script, data sent to a web address)'),
    'erase':   Row(True, "it can't be undone", 'DELETES FILES', 'outside your working folder'),
    'reads':   Row(True, "it is outside this task's own folders", 'READS', "outside this task's own folders"),
    'never':   Row(None, "Taskuary's own data and the places sign-ins are kept are never read by an agent - not even with the owner's yes.", 'READS', "Taskuary's own data or where sign-ins are kept"),
    'writes':  Row(True, "it is outside this task's own folders", 'WRITES', "outside this task's own folders"),
    'settings': Row(True, 'your next session or git command runs it or reads it as settings', 'CHANGES SETTINGS',
                    "that a later session or git command runs (git hooks and config, a CLI's settings and hooks)"),
    'unwritable': Row(None, "Taskuary's own data and settings, and the places sign-ins are kept, are never changed by an agent - not even with the "
                      "owner's yes; this task's own folders are written freely", 'WRITES', "to Taskuary's own data or where sign-ins are kept"),
    'fills':   Row(False, '', 'FILLS', 'a form - types, ticks or chooses in its boxes (the press that sends it is judged on its own)'),
    'looks':   Row(False, '', 'LOOKS', '- a snapshot, a read, a page opened'),
}
BIG = ('money', 'private', 'speaks', 'deletes')            # the four the owner named; the judge reads which of them a press is
def says(k: str, caps: bool = False) -> str: r = TABLE[k]; return f'{r.head if caps else r.head.lower()} {r.more}'
def _any(ks, caps=False) -> str: xs = [says(k, caps) for k in ks]; return ', '.join(xs[:-1]) + (', or ' if len(xs) > 2 else ' or ') + xs[-1]


def brief(road: str) -> str:
    "What the agent is told about the hold on this road ('browser', 'desktop', 'shell') - written from TABLE, never prose of its own."
    if road == 'browser':
        return ('A PAYMENT IS HIS: Pay, Buy or Order and a card typed are not an agent\'s - hand_over hands him that page. A press that '
                f'{_any(BIG[1:])} is refused with "held for the owner" and stands as one card in this chat: running the command for that '
                'button is what raises the card, his press on it runs it, and you are told what the page shows. A free sign-up or trial with '
                'made-up details, a form or a search runs. ')
    if road == 'desktop':
        return (f'A PRESS THAT {_any(BIG)} is HELD for the owner: running the command for it raises his action card, he presses it in the app, '
                'and you are told what happened. ')
    return (f"A step that {says('out')}, one that {says('erase')} and one that {says('reads')} is HELD for the owner's press: running it raises "
            "his action card - Taskuary's hold, never his no - and his press runs it; you are told what happened.")


def deny(why: str) -> dict:
    "The check point's no, in the PreToolUse hook's own shape (every road reads it so)."
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': why}}
def reason(out: dict) -> str: return ((out or {}).get('hookSpecificOutput') or {}).get('permissionDecisionReason') or ''


# ── THE ONE CHECK POINT ──────────────────────────────────────────────────────────────────────────────────────────────────
def check(store, tid: int, sid: str, cmd: str = '', cwd: str = '', shell: str = 'Bash', ask='', about: str = '', argv: list = None,
          paths: list = None, run: bool = False, brain=None, write: bool = False) -> dict:
    """{} lets the call run; else it is held (its card filed on the task) or refused, said in permissionDecisionReason - or `ask`, a CLI's
    own prompt where the owner sits at it (shellgate.asks). Every road calls this:
      - before a shell line runs (a hook, ACP, the API agent): what it does by the shell's grammar - a step out of this computer, a delete
        outside its folder - and what it reads outside the task's folders (`paths`: a file tool's own paths instead of a line);
      - `run`: where an `agent-browser` / `agent-desktop` command runs (the launcher, the API agent's browser): its press, judged on the page
        or the app it lands on - never before, when the line's earlier commands have not yet moved the page."""
    from . import agentdesktop, browsergate, readgate, shellgate
    if run:
        if browsergate.names(cmd, agentdesktop.EXE): return agentdesktop.check(store, tid, sid, cmd, brain)
        return browsergate.check(store, tid, sid, cmd, brain, cwd)
    if cmd and (no := browsergate.devtools(cmd)): return deny(no)
    reads, never = readgate.judge(store, tid, paths, cwd, write) if paths is not None else readgate.of_command(store, tid, cmd, cwd)
    if never: return deny(never)
    if not reads and not (cmd and shellgate.acts(cmd, cwd)): return {}
    return shellgate.check(store, tid, sid, cmd, shell, cwd, ask, about=about, reads=reads, argv=argv)


def judge(store, tid: int, sid: str, cmd: str, cwd: str = '', brain=None) -> str:
    """check() where a session's own `agent-browser` / `agent-desktop` runs (main -> /api/agent/gate), as words: '' runs it, else why it
    waits. The browser comes up here, at the agent's first navigate, never before it has an address (browserview.on_demand)."""
    from . import agentdesktop, browsergate, browserview
    if not browsergate.names(cmd, agentdesktop.EXE):
        # ...and A START THAT FAILED IS SAID AT THE STEP, with why: run on, the open waited out agent-browser's own attach to a Chrome
        # that was never there, and failed in its words, not why
        try: browserview.began(sid); browserview.FAILED.pop(str(sid), None); browserview.on_demand(sid, cmd)
        except Exception as e: logger.warning(f'the browser for {sid} did not start on its first page - {e}')
        if (why := browserview.FAILED.get(str(sid))): return f'{NOT_RUN_SAID}: the browser did not start - {why}. Run it again to try once more.'
    out = check(store, tid, sid, cmd, cwd, run=True, brain=brain)
    return (reason(out) or HELD_SAID) if out else ''


HELD_SAID = 'Taskuary held this for the owner'
# ...AND A REFUSAL THAT RAISES NO CARD SAYS SO (walk 13: a click refused as a payment was told "held this for the owner" - the agent said
# "Taskuary held that click as a payment ... please don't press it" over no card, and the step read "waits for your yes"): only a card held
NOT_RUN_SAID = 'Taskuary did not run this, and no card was raised for it'
def unjudged(why: str = '') -> str:
    "What a step is told when the gate had no answer for it (hooks.GATE_WAIT): it did not run - a gate that cannot answer holds."
    return f"{NOT_RUN_SAID}: Taskuary could not judge it{f' ({why})' if why else ''}, so nothing was done. Run it again."


# ── THE ONE RULE every held step meets (was actrule.py) ──────────────────────────────────────────────────────────────────
# 1. ALREADY ALLOWED: a trusted connection that acts on its own (the repo's code-host card at write or full Authority - shellgate.trusted),
#    or the same kind of step on the same target he approved earlier on this task: it runs, and the task says so in one line.
# 2. HIS NO: the same step dismissed since his last line on the task - refused, said as his no, never a second card.
# 3. ELSE one card for his press, filed by the road that knows the step. What he decided is written where he decided it (remember): audit
#    rows on the task - stored facts, never a model call.
DECIDED = 'act_decided'
DISMISSED = 'The owner dismissed this same step'      # ...his no, said as his: never "Taskuary's own answer"


def target(a: dict, cwd: str = '') -> tuple:
    "(repo, branch) a push goes to - ('', '') for a step that is not one; '' for either part not known."
    if a.get('refs') is None: return '', ''
    try: return _target(a, cwd)
    except Exception as e:
        logger.debug(f'gate: where a push goes was not read - {e}')
        return '', ''


def _target(a: dict, cwd: str) -> tuple:
    from . import landing, shellgate
    at, to = shellgate.folder(cwd, a.get('to') or ''), str(a.get('to') or '')
    repo = shellgate.repo_of(at) if to in ('',) or to.startswith('@') else to if to != '?' else ''
    refs = [r for r in a['refs'] if r]
    dst = refs[-1].lstrip('+').split(':')[-1] if refs else ''
    if dst in ('', 'HEAD') and at: dst = landing.head_branch(at)
    return repo, dst.removeprefix('refs/heads/')


def key(a: dict, cwd: str = '') -> str:
    "What makes two steps the same decision: what it does, and where - a push by its repo and branch, a road's own key where it names one."
    if a.get('key'): return str(a['key'])
    if a.get('refs') is not None:
        repo, br = target(a, cwd)
        return f'push|{repo.lower()}|{br}' if repo and br else ''
    return f"{a.get('what') or ''}|{str(a.get('to') or '').lower()}"


def keys(todo: list, cwd: str = '') -> list:
    "One key per step - [] when any step has none (it cannot be matched, so it is asked)."
    ks = [key(a, cwd) for a in todo]
    return ks if all(ks) else []


def words(a: dict, cwd: str = '') -> str:
    "A step in the owner's words - a push names its commits, repo and branch ('push 3 commits to northwind/ledger deploy')."
    if a.get('refs') is None: return a.get('what') or ''
    from . import landing, shellgate
    repo, br = target(a, cwd)
    if not (repo and br): return a.get('what') or ''
    at, refs = shellgate.folder(cwd, a.get('to') or ''), [r for r in a['refs'] if r]
    src = (refs[-1].lstrip('+').split(':')[0] if refs else '') or 'HEAD'
    try: n = landing._git(at, 'rev-list', '--count', f'origin/{br}..{src}') if at else ''
    except Exception: n = ''
    return f"push {n} commit{'' if n == '1' else 's'} to {repo} {br}" if n.isdigit() and n != '0' else f'push to {repo} {br}'


def _rows(store, tid: int) -> list:
    out = []
    for r in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId IN (?,?) AND Action=? ORDER BY Id", (int(tid), str(tid), DECIDED)):
        try: out.append(json.loads(r.get('Detail') or '{}'))
        except (TypeError, ValueError): pass
    return out


def remember(store, tid: int, ks: list, answer: str) -> None:
    "Write down his decision on these steps: 'approved' or 'dismissed'."
    if not ks or not str(tid or '').isdigit(): return
    from .shellgate import turn_of
    try: store.audit('task', int(tid), DECIDED, 'owner', 'human', {'keys': list(ks), 'answer': answer, 'turn': turn_of(store, int(tid))})
    except Exception as e: logger.warning(f'gate: task {tid} - his {answer} was not written down - {e}')


def card_key(p: dict) -> str:
    """What makes two proposed cards the same step (an email, a post, a payment, a PR): what it does, on which tool, with what - the same
    proposal again, word for word. A changed one is another step, and is put to him."""
    import hashlib
    bare = {k: v for k, v in p.items() if k != 'why'}
    return f"card|{p.get('action') or ''}|{p.get('type') or ''}|" + hashlib.sha1(json.dumps(bare, sort_keys=True, default=str).encode()).hexdigest()[:16]


def decide(store, tid: int, todo: list, cwd: str = '', big: bool = False) -> tuple:
    """(how, words) for steps a road would hold: ('trusted' | 'approved', a line for the task) runs them; ('dismissed', words for the agent)
    refuses them as his no; ('', '') - put them to him as one card. `big`: a card an agent proposes (an email, a post, a payment, a PR -
    proposals.queue) stays a card whatever he approved before or a connection allows; only his no is read for it."""
    from . import shellgate
    if not todo: return 'approved', ''
    if not big and (repo := shellgate.trusted(store, cwd, todo)):
        return 'trusted', f"The agent went on to {'; '.join(dict.fromkeys(words(a, cwd) for a in todo))} on {repo} - a repo you trust to act on its own."
    ks = keys(todo, cwd)
    if not ks: return '', ''
    rows, turn = _rows(store, tid), shellgate.turn_of(store, tid)
    yes = {k for r in rows if r.get('answer') == 'approved' for k in r.get('keys') or []}
    no = {k for r in rows if r.get('answer') == 'dismissed' and int(r.get('turn') or 0) >= turn for k in r.get('keys') or []}
    what = '; '.join(dict.fromkeys(words(a, cwd) for a in todo))
    if set(ks) & no: return 'dismissed', (f"{DISMISSED} ({what}) on an earlier card since he last wrote - it was NOT run, "
                                          "and it is not put to him again until he writes.")
    if big: return '', ''
    if set(ks) <= yes: return 'approved', f"The agent went on to {what} - you approved the same earlier in this task."
    return '', ''


# ── THE ACP ROAD (was acpgate.py): every tool call an ACP agent asks to make is answered here, in code, before it runs ─────
# Taskuary's own tools (the `taskuary` MCP server) are allowed: none of them sends - a propose tool lights a button. Any other MCP tool runs
# only where the send filter judged it not to send (sendfilter.verdicts); one it has not judged is refused. A shell line or a file tool goes
# through check() like every other road's. With Developer mode on, what check() holds on a coding task is put to the owner as Allow once /
# Reject (permissions.ask); no answer in time files the Approve card and refuses, so the step can still run on his later press.
OWN_SERVER = 'taskuary'
ALLOWED, REFUSED, HELD = 'allowed', 'refused', 'held'
CARD = 'card'           # held, and already the owner's button (the landing card's Push): never asked a second time with Allow once / Reject


def tool_of(tc: dict) -> dict:
    """{'name', 'server', 'tool', 'command', 'kind', 'argv', 'shell'} of an ACP toolCall, in either adapter's spelling (and a native CLI's)."""
    import re
    from .shellgate import unwrap, _name
    raw = tc.get('rawInput') if isinstance(tc.get('rawInput'), dict) else {}
    name = str(((tc.get('_meta') or {}).get('claudeCode') or {}).get('toolName') or tc.get('name') or '')
    server, tool = '', ''
    if (m := re.match(r'^mcp__(.+?)__(.+)$', name)): server, tool = m.groups()
    elif raw.get('server') and raw.get('tool'): server, tool = str(raw['server']), str(raw['tool'])
    elif (m := re.match(r'^mcp\.([^.]+)\.(.+)$', str(tc.get('title') or ''))): server, tool = m.groups()
    cmd = raw.get('command') or raw.get('cmd') or ''
    argv = [str(x) for x in cmd] if isinstance(cmd, list) else None        # the call as its brain made it: replayed as it is (shellgate.replay)
    # ...and a line that is a shell started on a script (Codex's every call) is that argv, and that script in that shell
    if argv is None: argv, cmd = unwrap(cmd)
    elif len(argv) > 2 and _name(argv[0]) in ('bash', 'sh', 'zsh', 'powershell', 'pwsh', 'cmd') and argv[-2].lower() in ('-c', '-lc', '-command', '/c'): cmd = argv[-1]
    else: cmd = ' '.join(argv)
    sh = _name(argv[0]) if argv else ''
    shell = 'PowerShell' if sh in ('powershell', 'pwsh') or (not sh and re.search(r'powershell|pwsh', name + str(cmd), re.I)) else 'Bash'
    return {'name': name or str(tc.get('title') or ''), 'server': server, 'tool': tool, 'command': str(cmd), 'kind': str(tc.get('kind') or ''),
            'argv': argv, 'shell': shell}


def _mcp(store, cli: str, server: str, tool: str) -> tuple:
    if server == OWN_SERVER: return ALLOWED, "Taskuary's own tool - it never sends"
    if store is None: return REFUSED, 'the send filter could not be read, so an outside tool waits'
    from . import sendfilter
    bare = sendfilter._bare
    for s in sendfilter.verdicts(store, cli):
        if bare(s['server']) != bare(server) and s['server'] != server: continue
        if s['blocked']: return REFUSED, f"{server} is left out until its tools are judged ({s.get('error') or 'not judged'})"
        t = next((t for t in s['tools'] if t['name'] == tool), None)
        if not t: return REFUSED, f'{server}/{tool} has not been judged yet'
        return (REFUSED, f"{server}/{tool} sends - sending goes through Taskuary's propose tools") if t['blocked'] else (ALLOWED, 'it does not send')
    return REFUSED, f'{server} is not a server the send filter knows'


def _raw(tc: dict) -> dict: return tc.get('rawInput') if isinstance(tc.get('rawInput'), dict) else {}
def _writes(tc: dict) -> bool:
    "Is this ACP toolCall a file tool that writes (an edit, a delete, a move - by its kind or its name)?"
    from . import readgate
    t = tool_of(tc)
    return not t['command'] and (t['kind'] in ('edit', 'delete', 'move') or t['name'] in readgate.WRITE_TOOLS)
def _paths(tc: dict, cwd: str):
    "A file tool's own paths - what it reads, or what it writes (_writes) - else None: a shell line, or a tool that touches no file."
    from . import readgate
    t = tool_of(tc)
    if t['command'] or (t['kind'] not in ('read', 'search') and t['name'] not in readgate.READ_TOOLS and not _writes(tc)): return None
    ps = readgate.tool_paths(_raw(tc), tc.get('locations'), cwd)
    return readgate.listed(ps) if t['name'] in readgate.LIST_TOOLS else ps


def tool_call(tc: dict, ctx: dict) -> tuple:
    """(answer, why) for one ACP toolCall. ctx: store, task_id, cli, cwd, sid, owner_asks."""
    t, store = tool_of(tc), ctx.get('store')
    if t['server']: return _mcp(store, ctx.get('cli') or '', t['server'], t['tool'])
    from . import browsergate, readgate, shellgate
    raw = _raw(tc)
    cwd, tid = str(raw.get('cwd') or ctx.get('cwd') or ''), ctx.get('task_id')
    paths, w = _paths(tc, cwd), _writes(tc)
    if not t['command'] and paths is None: return ALLOWED, ''          # ...a press in the browser or on the desktop is held where it runs
    if t['command'] and (no := browsergate.devtools(t['command'])): return REFUSED, no
    reads, never = readgate.judge(store, tid, paths, cwd, w) if paths is not None else readgate.of_command(store, tid, t['command'], cwd)
    if never: return REFUSED, never
    todo = (shellgate.acts(t['command'], cwd) if t['command'] else []) + reads
    if not todo: return ALLOWED, ''
    if store is None or not str(tid or '').isdigit(): return REFUSED, '; '.join(dict.fromkeys(a['what'] for a in todo)) + ' - it waits for the owner'
    how, said = decide(store, int(tid), todo, cwd)
    if how == 'dismissed': return REFUSED, said
    if not how:
        from . import landing
        # a push of the task's own work is the landing card's Push (landing.push_asked) - before any other button is drawn for it
        if t['command'] and (lands := landing.push_asked(store, int(tid), t['command'], cwd, str(raw.get('description') or ''))): return (CARD if lands[0] else REFUSED), lands[1]
        # ...put to the owner as buttons (answerer): the Approve card is filed only if they do not answer, so nothing waits twice
        if ctx.get('owner_asks'): return HELD, '; '.join(dict.fromkeys(a['what'] for a in todo)) + ' - it waits for your answer'
    out = check(store, int(tid), str(ctx.get('sid') or ''), t['command'], cwd, t['shell'], about=str(raw.get('description') or ''), argv=t['argv'], paths=paths, write=w)
    if not out: return ALLOWED, 'a repo the owner trusts to act on its own' if how == 'trusted' else 'the owner approved the same earlier in this task'
    return HELD, reason(out)


def owner_asks(ctx: dict) -> bool:
    """A held call goes to the owner's buttons: a coding task to show it on, and Developer mode on (with it off the Approve card stays the
    road). A chat agent's task draws no such buttons: its held step is the Approve card at once."""
    from . import agents, general, terminal
    st, tid = ctx.get('store'), str(ctx.get('task_id') or '')
    if st is None or not tid.isdigit() or not agents.developer_mode(st): return False
    return terminal.is_acp(terminal.SESSIONS.get(str(ctx.get('sid') or ''))) or not general.handles(st.get_task(int(tid)) or {})


# THE OWNER'S OWN NO ON THE STEP, in their voice: never "Taskuary refused it: the owner said no"
YOU_REJECTED = 'You rejected this'
# ...and a step nobody answered is no one's no: it was still waiting when the chat moved past it (permissions.set_aside)
STILL_WAITING = 'It was still waiting for the owner when the conversation moved on - nobody said no to it, and it can be raised again'
# ...and one closed by his Stop (permissions.STOPPED_SAID) is heard in the step's own answer only
YOU_STOPPED = 'The owner stopped you before answering this, so it was not run - nobody said no to it, and it can be raised again'


def put_to_owner(ctx: dict, params: dict, why: str) -> tuple:
    "(answer, why) once the owner has answered a held call (permissions.ask) - or not: then the Approve card, and a refusal."
    from . import permissions, readgate, shellgate, workerstate as ws
    store, tid, late, past = ctx['store'], int(ctx['task_id']), [], []
    req = {**permissions.from_acp(params), 'sid': str(ctx.get('sid') or (params or {}).get('sessionId') or '')}
    got = permissions.ask(store, tid, req, timed_out=lambda: late.append(1), moved_on=past.append)
    if past: return REFUSED, YOU_STOPPED if past[0] == permissions.STOPPED_SAID else STILL_WAITING
    tc = (params or {}).get('toolCall') or {}
    t, cwd = tool_of(tc), str(_raw(tc).get('cwd') or ctx.get('cwd') or '')
    paths = _paths(tc, cwd)
    reads = (readgate.judge(store, tid, paths, cwd, _writes(tc)) if paths is not None else readgate.of_command(store, tid, t['command'], cwd))[0]
    ks = keys(shellgate.acts(t['command'], cwd), cwd) if t['command'] else []
    if not late: remember(store, tid, ks, 'approved' if got.startswith('allow') else 'dismissed')     # his answer stands for the task
    if got.startswith('allow'):
        readgate.grant(store, tid, [a['folder'] for a in reads if a.get('folder')])      # ...a folder he let it read stays the task's
        return ALLOWED, 'the owner allowed it'
    if not late:
        # ...and the agent hears WHOSE no it was: into the turn it is in where the adapter steers, else as its next words
        if ws._live(tid):
            r = permissions.normal(req)
            # ...(the turn at work on this very call: no card's Dismiss, which wakes nobody - shellgate.declined)
            from .browsergate import _tell, not_approved
            _tell(store, tid, not_approved(f"{permissions.asked(r | permissions.held_for(r, str(ctx.get('cwd') or ''))) or 'the step'} (`{str(r['command'] or '')[:200]}`)"))
        return REFUSED, YOU_REJECTED
    out = check(store, tid, str(ctx.get('sid') or ''), t['command'], cwd, t['shell'], about=str(_raw(tc).get('description') or ''), argv=t['argv'],
                paths=paths) if t['command'] or reads else {}
    return HELD, reason(out) or why


def answerer(ctx: dict, trace=None, held: dict = None, told: list = None):
    """The ACPClient `permit` callback for one turn: decide, answer with the matching option, and say it in the trace. `held` gets
    Taskuary's own words for each call it did not allow (id -> words). `told`: the turn's own list of what the agent is to hear of each no
    ({'words', 'tell'}) - said as the words it goes on with where the no ended its turn, else by the one road (`tell`)."""
    from . import acp, readgate
    def permit(params):
        tc = params.get('toolCall') or {}
        asks = owner_asks(ctx)
        answer, why = tool_call(tc, {**ctx, 'owner_asks': asks})
        if answer == HELD and asks: answer, why = put_to_owner(ctx, params, why)
        out = acp.pick(params.get('options'), answer == ALLOWED)
        iid, t = str(tc.get('toolCallId') or ''), tool_of(tc)
        # ...a file it was let write is its own work from now on: reading it back is never asked (readgate.wrote)
        if answer == ALLOWED and (t['kind'] == 'edit' or t['name'] in readgate.WRITE_TOOLS):
            readgate.wrote(ctx.get('task_id'), readgate.tool_paths(_raw(tc), tc.get('locations'), str(_raw(tc).get('cwd') or ctx.get('cwd') or '')))
        if answer != ALLOWED and held is not None: held[iid] = why if answer in (HELD, CARD) or why in (YOU_REJECTED, STILL_WAITING, YOU_STOPPED) else f'Taskuary refused it: {why}'
        # ...AND THE AGENT HEARS TASKUARY'S OWN REASON: the adapter's answer is "User refused permission to run tool" whoever said no
        step = f"`{t['command'][:200]}`" if t['command'] else 'That step'
        tell = answer in (REFUSED, CARD) and why and why not in (YOU_REJECTED, YOU_STOPPED) and ctx.get('store') is not None and str(ctx.get('task_id') or '').isdigit()
        if tell:
            words_ = f'{step} was not run - ' + (why if why == STILL_WAITING or why.startswith(DISMISSED) else f"Taskuary's own answer, not the owner's: {why}")
            if told is not None: told.append({'words': words_, 'tell': True})
            else:
                from .browsergate import _tell
                _tell(ctx['store'], int(ctx['task_id']), words_)
        elif answer == HELD and why and told is not None: told.append({'words': f'{step} was not run yet - {why}', 'tell': False})
        name = t['name'] or str(tc.get('title') or 'tool')
        (logger.info if answer == ALLOWED else logger.warning)(f'acp permission: {name} {answer}' + (f' - {why}' if why else ''))
        if trace: trace('permission', name, {'tool_call_id': iid, 'answer': answer, 'why': why, 'title': str(tc.get('title') or '')[:200]})
        return out
    return permit


# ── THE LAUNCHER (was gatecmd.py): every task session's `agent-browser` and `agent-desktop` is Taskuary's own ────────────
# A folder first on every task session's PATH (terminal.session_env) holds an `agent-browser` and an `agent-desktop` that run main() here:
# a command that only looks goes straight to the real program; every other one asks the server (/api/agent/gate -> judge) BEFORE it runs.
# Held, it prints why and exits 1 without running; Taskuary unreachable, an act fails closed the same way. Not covered, said plainly: an
# agent that reaches the real program by its full path, or drives Chrome or the desktop some other way.
GATED = ('agent-browser', 'agent-desktop')
MARK = '/api/agent/gate'
WAIT = 150                      # a snapshot and one verdict (browsergate.JUDGE_WAIT), and a page launched for its first open
OWN_WAIT = 300                  # ...and Taskuary's own verb: a verdict, the form sent, and a code the site emails waited for
OWN_VERBS = ('signup',)         # done by the server in this session's browser, never by the real program (signin.signup)
_DIR: dict = {}
LAUNCHER = b'-m taskuary.gate'          # ...in every launcher folder() writes (the older `taskuary.gatecmd` ones too): how one is told from the real program


def is_gate(p) -> bool:
    "Is this file one of the launchers folder() writes - never the real program."
    try: return LAUNCHER in Path(p).read_bytes()[:400]
    except OSError: return False


def folder() -> str:
    """The folder put first on a task session's PATH: one launcher per gated program, each running main() with this interpreter and this
    server's own code, naming its own folder so the real program is found past it. '' where it could not be written."""
    if 'd' in _DIR: return _DIR['d']
    from . import config
    d, py = config.home() / 'bin' / 'gate', sys.executable
    root = str(Path(__file__).resolve().parent.parent)
    try:
        d.mkdir(parents=True, exist_ok=True)
        for n in GATED:
            _write(d / f'{n}.cmd', f'@set "PYTHONPATH={root};%PYTHONPATH%"\r\n@"{py}" -m taskuary.gate "%~dp0." {n} %*\r\n')
            _write(d / n, f'#!/bin/sh\nPYTHONPATH="{root.replace(chr(92), "/")}:$PYTHONPATH" exec "{py.replace(chr(92), "/")}" -m taskuary.gate '
                          f'"$(dirname "$0")" {n} "$@"\n', 0o755)
        _DIR['d'] = str(d)
    except OSError as e:
        logger.warning(f'the browser and desktop hold could not be put on the agents\' PATH - {e}'); _DIR['d'] = ''
    return _DIR['d']


def _write(p, text: str, mode: int = None):
    try:
        if p.read_text(encoding='utf-8') == text: return
    except OSError: pass
    p.write_text(text, encoding='utf-8', newline='')
    if mode: os.chmod(p, mode)


def _same(a: str, b: str) -> bool: return os.path.normcase(os.path.realpath(a or '.')) == os.path.normcase(os.path.realpath(b or '.'))


def real(name: str, gate: str) -> str:
    "The real program behind `name`, looked up on a PATH without the gate's folder (os.environ's is cut, so what it runs is cut too)."
    os.environ['PATH'] = os.pathsep.join(p for p in os.environ.get('PATH', '').split(os.pathsep) if p and not _same(p, gate))
    if name == 'agent-browser':
        from . import browserview
        return browserview.program()
    from . import agentdesktop
    return agentdesktop.path()


def asks(name: str, cmd: str) -> tuple:
    "(is it a press to judge, must the server see it at all): a look runs untouched; an open goes by the server, which brings the page up."
    from . import agentdesktop, browsergate
    if name == agentdesktop.EXE: return (bool(agentdesktop.acts(cmd)),) * 2
    # ...a refusal is an act: Taskuary unreachable, it fails closed - and so is an address that carries a query, which only the server can
    # judge against where this session has been (browsergate.sends; red team round 6: unasked, such an open ran)
    act = bool(browsergate.acts(cmd, ()) or browsergate.refused(cmd))
    return act, act or bool(browsergate.opens(cmd))


def _own(cmd: str) -> list:
    "The arguments of Taskuary's own verb this agent-browser line asks for (OWN_VERBS), past agent-browser's options - [] for none."
    from . import browsergate
    for argv in browsergate._segments(cmd) or []:
        a = browsergate._own_args(browsergate._head(argv) or [])
        if a and a[0].lower() in OWN_VERBS: return a
    return []
def own(cmd: str) -> str: return a[0].lower() if (a := _own(cmd)) else ''


# ...ITS USAGE ASKED IS NO ACT (walk 12: `agent-browser signup --help`, run while the agent read up on its tools, was taken for the sign-up
# itself - the form judged, and a card "Submit your Proton Mail sign-up through checkout (it spends your money)" put to the owner)
def usage(verb: str) -> str:
    from .browserview import SIGNUP_LINE
    return {'signup': f'Usage: agent-browser signup (no arguments). {SIGNUP_LINE.strip()}'}.get(verb, f'agent-browser {verb} is not a command')


def run_own(store, tid: int, sid: str, verb: str, cmd: str = '') -> tuple:
    "(done, what the command prints) of Taskuary's own verb - its usage where the line asks for help."
    from . import browsergate, signin
    if browsergate.helps(_own(cmd)[1:]): return True, usage(verb)
    if verb == 'signup': return signin.signup(store, tid, sid)
    return False, f'agent-browser {verb} is not a command'


def ask(name: str, args: list, after: bool = False, rc: int = 0) -> str:
    """'' runs the command; else why it was not run - asked of the server this session belongs to. `after`: the browser command has run
    (exit code `rc`) - what the site did where it is no working page, and what the command did in his words (browsergate.after)."""
    cmd = shlex.join([name, *args])
    act, call = asks(name, cmd)
    if not (name == 'agent-browser' if after else call): return ''
    try: return str(post(cmd, after, rc=rc).get('why') or '')
    except Exception as e:
        if not act or after: return ''
        return (f'{NOT_RUN_SAID}: it could not be asked whether this press may run ({str(e)[:120]}), so nothing was done. Run it again to ask again.')


def post(cmd: str, after: bool = False, wait: float = WAIT, rc: int = 0) -> dict:
    "The server's answer on one line of this session's (/api/agent/gate)."
    from . import config, hooks
    from .guard import TASK_ENV, TASK_HDR
    env, srv = os.environ, config.load()['server']
    body = json.dumps({'task': env.get('TASKUARY_TASK') or '', 'sid': env.get('TASKUARY_SID') or '', 'cmd': cmd, 'cwd': os.getcwd(), **({'after': True, 'rc': rc} if after else {})}).encode()
    hdr = {'Content-Type': 'application/json', **({'X-Taskuary-Token': srv['token']} if srv.get('token') else {}),
           **({TASK_HDR: env[TASK_ENV]} if env.get(TASK_ENV) else {})}
    import urllib.request
    req = urllib.request.Request((env.get('TASKUARY_URL') or hooks.base_url()) + MARK, body, hdr)
    with urllib.request.urlopen(req, timeout=wait) as r: return json.load(r)


def main(argv: list = None) -> int:
    gate, name, *args = sys.argv[1:] if argv is None else argv
    # ...ITS OWN LINES IN UTF-8, as the program's beside them are: Windows wrote them in the console's code page, so a "€3.60" the page named came
    # to the agent - and to his step row - as "?3.60" in the middle of agent-browser's own UTF-8 (walk 11)
    for f in (sys.stdout, sys.stderr):
        try: f.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError): pass
    exe = real(name, gate)
    if not exe: print(f'{name} is not installed on this computer.', file=sys.stderr); return 127
    if name == 'agent-browser' and (verb := own(shlex.join([name, *args]))):
        try: r = post(shlex.join([name, *args]), wait=OWN_WAIT)
        except Exception as e: print(f'Taskuary could not be reached ({str(e)[:120]}) - nothing was done. Run it again.', file=sys.stderr); return 1
        print(r.get('said') or r.get('why') or f'{verb}: no answer'); return 0 if r.get('ok') else 1
    why = ask(name, args)
    if why: print(why, file=sys.stderr); return 1
    from . import browserview, spawn
    # ...its output handed on by name: started with no console, a real program behind a .cmd wrote nothing to handles it only inherited.
    # ...and the real program alone is told the browser's DevTools port, never the agent's shell (browserview.env)
    env = {**os.environ, **browserview.kept_cdp(os.environ.get('AGENT_BROWSER_SESSION') or '')} if name == 'agent-browser' else None
    rc = spawn.run([exe, *args], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, **({'env': env} if env else {})).returncode
    if (said := ask(name, args, after=True, rc=rc)): print(said, file=sys.stderr)
    return rc


if __name__ == '__main__': sys.exit(main())
