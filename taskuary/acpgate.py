"""TASKUARY'S OWN ANSWER TO AN ACP PERMISSION REQUEST (the owner, 2026-11-06: "more control - every tool call and permission is a
typed request we can see and refuse").

On the argv road a headless run carries the CLI's bypass flag, and the only fences are the ones the CLI enforces for us - Claude's
--disallowedTools, a PreToolUse hook that can refuse (shellgate), and on Codex nothing that can refuse at all. Over ACP
the agent ASKS (clis.ADAPTERS sets the mode that makes it ask) and the answer is ours, given here, in code, before the call runs:

  - Taskuary's own tools (agenttools, the `taskuary` MCP server) are allowed: none of them sends - a propose tool lights a button.
  - Any other MCP tool runs only when the send filter judged it not to send (sendfilter.verdicts - the same verdicts that build
    Claude's --disallowedTools and Codex's disabled_tools). A tool it has not judged, or a server it does not know, is refused:
    "never sent without the owner's press" outranks keeping a tool, as it does there.
  - A shell step that goes out or deletes outside the agent's folder is HELD (shellgate.check: on the task as a proposal for the
    owner's Approve), and so is an HTTP client that writes to a host off this machine (curl -X POST, -d, Invoke-RestMethod -Method
    Post...) - by each tool's own grammar, never by words in a mail. The hook road reads the same command by the same function
    (shellgate.acts), so one command is held alike on both.
  - A read or a search outside the task's own folders is held the same way (readgate.py); Taskuary's own home and the sign-in places
    are refused outright.
  - Everything else - reads in its folders, edits there, a page fetched - is allowed, as the bypass allowed it.

THE OWNER'S BUTTONS (step 3, permissions.py). With Developer mode on, what these rules HOLD is put to the owner as it happens: Allow once
/ Reject in the task chat and on a chat bound to the task (agentchannels.py), the agent waiting on the answer. The rules above still
answer first - an allowed or refused call never reaches the owner. Allowed is that one call (allow_once, always); refused is said to the
agent; no answer in time files the old Approve card (shellgate.check) and refuses, so the step can still run on the owner's later press.
Every answer is said in the run trace (`permission`) and logged.
"""
import re
from loguru import logger

from . import acp

OWN = 'taskuary'
ALLOWED, REFUSED, HELD = 'allowed', 'refused', 'held'
CARD = 'card'           # held, and already the owner's button (the landing card's Push): never asked a second time with Allow once / Reject


def tool_of(tc: dict) -> dict:
    """{'name', 'server', 'tool', 'command', 'kind'} of an ACP toolCall, in either adapter's spelling (and a native CLI's)."""
    raw = tc.get('rawInput') if isinstance(tc.get('rawInput'), dict) else {}
    name = str(((tc.get('_meta') or {}).get('claudeCode') or {}).get('toolName') or tc.get('name') or '')
    server, tool = '', ''
    if (m := re.match(r'^mcp__(.+?)__(.+)$', name)): server, tool = m.groups()
    elif raw.get('server') and raw.get('tool'): server, tool = str(raw['server']), str(raw['tool'])
    elif (m := re.match(r'^mcp\.([^.]+)\.(.+)$', str(tc.get('title') or ''))): server, tool = m.groups()
    cmd = raw.get('command') or raw.get('cmd') or ''
    argv = [str(x) for x in cmd] if isinstance(cmd, list) else None        # the call as its brain made it: replayed as it is (shellgate.replay)
    if argv: cmd = ' '.join(argv)
    return {'name': name or str(tc.get('title') or ''), 'server': server, 'tool': tool, 'command': str(cmd), 'kind': str(tc.get('kind') or ''), 'argv': argv}


def _mcp(store, cli: str, server: str, tool: str) -> tuple:
    if server == OWN: return ALLOWED, "Taskuary's own tool - it never sends"
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


def decide(tc: dict, ctx: dict) -> tuple:
    """(answer, why) for one toolCall. ctx: store, task_id, cli, cwd, sid."""
    t, store = tool_of(tc), ctx.get('store')
    if t['server']: return _mcp(store, ctx.get('cli') or '', t['server'], t['tool'])
    from . import shellgate
    raw = tc.get('rawInput') if isinstance(tc.get('rawInput'), dict) else {}
    cwd, tid = str(raw.get('cwd') or ctx.get('cwd') or ''), ctx.get('task_id')
    reads, never = reads_of(tc, ctx)
    if never: return REFUSED, never
    todo = (shellgate.acts(t['command'], cwd) if t['command'] else []) + reads
    shell = 'PowerShell' if re.search(r'powershell|pwsh', t['name'] + t['command'], re.I) else 'Bash'
    if not todo: return ALLOWED, ''        # ...a press in the browser or on the desktop is held where it runs (gatecmd)
    if store is None or not str(tid or '').isdigit(): return REFUSED, '; '.join(dict.fromkeys(a['what'] for a in todo)) + ' - it waits for the owner'
    from . import actrule
    how, said = actrule.decide(store, int(tid), todo, cwd)              # the one rule: trusted, or decided by him already on this task
    if how == 'dismissed': return REFUSED, said
    if not how:
        from . import landing
        # a push of the task's own work is the landing card's Push (landing.push_asked) - before any other button is drawn for it
        if t['command'] and (lands := landing.push_asked(store, int(tid), t['command'], cwd, str(raw.get('description') or ''))): return (CARD if lands[0] else REFUSED), lands[1]
        # ...put to the owner as buttons (answerer): the Approve card is filed only if they do not answer, so nothing waits twice
        if ctx.get('owner_asks'): return HELD, '; '.join(dict.fromkeys(a['what'] for a in todo)) + ' - it waits for your answer'
    said = shellgate.check(store, int(tid), str(ctx.get('sid') or ''), t['command'], shell=shell, cwd=cwd, ask=False, about=str(raw.get('description') or ''),
                           reads=reads, argv=t['argv'])
    if not said: return ALLOWED, 'a repo the owner trusts to act on its own' if how == 'trusted' else 'the owner approved the same earlier in this task'
    return HELD, said['hookSpecificOutput']['permissionDecisionReason']


def reads_of(tc: dict, ctx: dict) -> tuple:
    "(held, never) for what one toolCall reads outside its task's folders (readgate): a shell line's paths, else a file tool's own."
    from . import readgate
    t, raw = tool_of(tc), tc.get('rawInput') if isinstance(tc.get('rawInput'), dict) else {}
    cwd = str(raw.get('cwd') or ctx.get('cwd') or '')
    if t['command']: return readgate.of_command(ctx.get('store'), ctx.get('task_id'), t['command'], cwd)
    if t['kind'] not in ('read', 'search') and t['name'] not in readgate.READ_TOOLS: return [], ''
    return readgate.judge(ctx.get('store'), ctx.get('task_id'), readgate.tool_paths(raw, tc.get('locations'), cwd), cwd)


def owner_asks(ctx: dict) -> bool:
    """A held call goes to the owner's buttons: a coding task to show it on, and Developer mode on (with it off the Approve card stays the
    road). A CHAT AGENT'S TASK DRAWS NO SUCH BUTTONS (recorded 2026-11-12: Developer mode on, a chat agent's delete waited on Allow once /
    Reject that only a coding chat draws - "working" for ten minutes with nothing to press): its held step is the Approve card at once."""
    from . import agents, general, terminal
    st, tid = ctx.get('store'), str(ctx.get('task_id') or '')
    if st is None or not tid.isdigit() or not agents.developer_mode(st): return False
    # ...a coding session's own chat (acpcoding), or a run on a task that is no chat agent's
    return terminal.is_acp(terminal.SESSIONS.get(str(ctx.get('sid') or ''))) or not general.handles(st.get_task(int(tid)) or {})


# THE OWNER'S OWN NO ON THE STEP, in their voice (the owner, 2026-11-10): it read "Taskuary refused it: the owner said no" - the app
# taking the credit for their press
YOU_REJECTED = 'You rejected this'
# ...and a step nobody answered is no one's no: it was still waiting when the chat moved past it (permissions.set_aside)
STILL_WAITING = ('It was still waiting for the owner when the conversation moved on - nobody said no to it, so never say they did. Raise '
                 'it again if it is still needed')
# ...and one closed by his Stop (permissions.STOPPED_SAID) is heard in the step's own answer only: told as the next words, the note began a new
# turn - the agent he had just stopped ran again and asked again
YOU_STOPPED = 'The owner stopped you before answering this, so it was not run - nobody said no to it. Raise it again if it is still needed'


def put_to_owner(ctx: dict, params: dict, why: str) -> tuple:
    "(answer, why) once the owner has answered a held call (permissions.ask) - or not: then the Approve card, and a refusal."
    from . import permissions, shellgate, workerstate as ws
    store, tid, late, past = ctx['store'], int(ctx['task_id']), [], []
    req = {**permissions.from_acp(params), 'sid': str(ctx.get('sid') or (params or {}).get('sessionId') or '')}
    got = permissions.ask(store, tid, req, timed_out=lambda: late.append(1), moved_on=past.append)
    if past: return REFUSED, YOU_STOPPED if past[0] == permissions.STOPPED_SAID else STILL_WAITING
    tc = (params or {}).get('toolCall') or {}
    reads = reads_of(tc, ctx)[0]
    from . import actrule
    t, cwd_ = tool_of(tc), str(((tc.get('rawInput') or {}) if isinstance(tc.get('rawInput'), dict) else {}).get('cwd') or ctx.get('cwd') or '')
    ks = actrule.keys(shellgate.acts(t['command'], cwd_), cwd_) if t['command'] else []
    if not late: actrule.remember(store, tid, ks, 'approved' if got.startswith('allow') else 'dismissed')     # his answer stands for the task
    if got.startswith('allow'):
        from . import readgate
        readgate.grant(store, tid, [a['folder'] for a in reads if a.get('folder')])      # ...a folder he let it read stays the task's
        return ALLOWED, 'the owner allowed it'
    if not late:
        # ...and the agent hears WHOSE no it was: the adapter's refusal reads the same for Taskuary's own block (browsergate.OWNER_NO). Into
        # the turn it is in where the adapter steers, else as its next words; a run with no session of ours hears it with the owner's next line
        if ws._live(tid):
            r = permissions.normal(req)
            shellgate.declined(store, tid, {'what': permissions.asked(r | permissions.held_for(r, str(ctx.get('cwd') or ''))), 'command': r['command']})
        return REFUSED, YOU_REJECTED
    raw = tc.get('rawInput') if isinstance(tc.get('rawInput'), dict) else {}
    t, cwd = tool_of(tc), str(raw.get('cwd') or ctx.get('cwd') or '')
    shell = 'PowerShell' if re.search(r'powershell|pwsh', t['name'] + t['command'], re.I) else 'Bash'
    said = shellgate.check(store, tid, str(ctx.get('sid') or ''), t['command'], shell=shell, cwd=cwd, ask=False, about=str(raw.get('description') or ''),
                           reads=reads, argv=t['argv']) if t['command'] or reads else {}
    return HELD, (said.get('hookSpecificOutput') or {}).get('permissionDecisionReason') or why


def answerer(ctx: dict, trace=None, held: dict = None, told: list = None):
    """The ACPClient `permit` callback for one turn: decide, answer with the matching option, and say it in the trace. `held`
    gets Taskuary's own words for each call it did not allow (id -> words), which the step shows instead of the adapter's "the user
    refused": a held one reads "held for the owner" (shellgate.HELD), not "failed".
    `told`: the turn's own list of what the agent is to hear of each no ({'words', 'tell'}) - the turn says it (agents.run_acp): as the words
    it goes on with where the no ended its turn, else by the one road (`tell`: a refusal's reason, which the adapter's answer drops)."""
    def permit(params):
        tc = params.get('toolCall') or {}
        asks = owner_asks(ctx)
        answer, why = decide(tc, {**ctx, 'owner_asks': asks})
        if answer == HELD and asks: answer, why = put_to_owner(ctx, params, why)
        out = acp.pick(params.get('options'), answer == ALLOWED)
        iid = str(tc.get('toolCallId') or '')
        if answer != ALLOWED and held is not None: held[iid] = why if answer in (HELD, CARD) or why in (YOU_REJECTED, STILL_WAITING, YOU_STOPPED) else f'Taskuary refused it: {why}'
        # ...AND THE AGENT HEARS TASKUARY'S OWN REASON (recorded on the real CLI, 2026-11-15): the adapter's answer is "User refused permission
        # to run tool" whoever said no, so a push refused with the way on ("call propose_land") reached only the page's trace - the agent
        # told the owner "once you approve, I'll push" over nothing to approve. Said as the owner's own no is (put_to_owner), by the one road
        cmd = tool_of(tc)['command']
        step = f'`{cmd[:200]}`' if cmd else 'That step'
        tell = answer in (REFUSED, CARD) and why and why not in (YOU_REJECTED, YOU_STOPPED) and ctx.get('store') is not None and str(ctx.get('task_id') or '').isdigit()
        if tell:
            from .actrule import DISMISSED
            words = f'{step} was not run - ' + (why if why == STILL_WAITING or why.startswith(DISMISSED) else f"Taskuary's own answer, not the owner's: {why}")
            if told is not None: told.append({'words': words, 'tell': True})
            else:
                from .browsergate import _tell
                _tell(ctx['store'], int(ctx['task_id']), words)
        # ...a hold's own words, which the agent hears in the step's answer where its adapter goes on - and nowhere where the no ended its turn
        elif answer == HELD and why and told is not None: told.append({'words': f'{step} was not run yet - {why}', 'tell': False})
        name = tool_of(tc)['name'] or str(tc.get('title') or 'tool')
        (logger.info if answer == ALLOWED else logger.warning)(f'acp permission: {name} {answer}' + (f' - {why}' if why else ''))
        if trace: trace('permission', name, {'tool_call_id': iid, 'answer': answer, 'why': why, 'title': str(tc.get('title') or '')[:200]})
        return out
    return permit
