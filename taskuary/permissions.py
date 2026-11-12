"""AN AGENT'S PERMISSION REQUEST, PUT TO THE OWNER (the owner, 2026-11-06: permission requests as buttons, in the task chat and on a
bound channel - "only the owner's answer counts").

ONE SEAM: ask(store, tid, request) -> answer, blocking until it is answered. request is
    {tool, kind, title, locations, options: [allow_once|allow_always|reject_once|reject_always], input?, sid?}
and the answer is one of its options.

1. Taskuary's own rules answer first (`auto`): an "always" the owner gave before on this task and tool pattern, and a read, search or
   think inside the task's own checkout. A send, post, pay, push or publish (`risky`) is never allowed by a rule - not even by a
   remembered "always", which is never offered for one.
2. What is left is the OWNER's: a small card in the task chat (the one task chat, GeneralWorkspace.jsx, POST /api/tasks/<tid>/permission) and, on every channel
   bound to the task (agentchannels.py), a message with the choices as numbered words - answered only by the owner's own reply there.
   It is a held ask (workerstate.hold), so the rail reads the agent as waiting on you, and the generic answer road resolves it too.
3. No answer in TIMEOUT is a refusal, said plainly in the task and on the channel.

THE ACP ROAD (step 1, acpgate.answerer): what acpgate would HOLD for the owner comes here through `acp(store, tid, params)` - the
session/request_permission params in, the ACP outcome out. ACP is always answered allow_once / reject_once: an "always" is kept here,
so the next call still reaches Taskuary's rules first.
"""
import re, threading, time, uuid
from loguru import logger

from .store import task_ref

OPTIONS = ('allow_once', 'allow_always', 'reject_once', 'reject_always')
LABEL = {'allow_once': 'Allow once', 'allow_always': 'Always allow', 'reject_once': 'Reject', 'reject_always': 'Always reject'}
TIMEOUT = 10 * 60                 # under an ACP turn's own 20 minutes, so the agent hears the refusal rather than a dead connection
RISKY = re.compile(r'\b(push|send|sends|post|posts|pay|payment|publish|deploy|release|upload|e-?mail|tweet|charge|transfer|wire)\b', re.I)
READS = ('read', 'search', 'think')
PENDING, _LOCK = {}, threading.Lock()


def normal(r: dict) -> dict:
    r = dict(r or {})
    opts = [o for o in (r.get('options') or OPTIONS) if o in OPTIONS] or ['allow_once', 'reject_once']
    locs, inp = [str(l) for l in (r.get('locations') or []) if str(l or '').strip()], r.get('input') if isinstance(r.get('input'), dict) else {}
    out = {'tool': str(r.get('tool') or r.get('kind') or 'a tool'), 'kind': str(r.get('kind') or 'other').lower(), 'title': str(r.get('title') or r.get('tool') or ''),
           'locations': locs, 'input': inp, 'sid': str(r.get('sid') or ''), 'command': str(r.get('command') or inp.get('command') or ''),
           'about': cut(' '.join(str(inp.get('description') or '').split()), 300), 'what': '', 'why': ''}        # what/why: held_for, once it is the owner's
    out['risky'] = risky(out)
    if out['risky']: opts = [o for o in opts if o != 'allow_always']            # an "always" for a push is a push nobody saw
    out['options'] = opts
    return out


# A COMMAND IS READ FOR WHAT IT DOES, not for its words (the owner, 2026-11-10): `git log --grep push` read as a push and lost its
# "Always allow", and a send worded any other way kept it. The gates' own reading decides - a step that goes out or deletes outside
# the agent's folder, a web write (shellgate.acts). A tool with no command to read is still known by its name
def risky(r: dict) -> bool:
    if (cmd := r.get('command')):
        from . import shellgate
        return bool(shellgate.acts(cmd))
    return bool(RISKY.search(' '.join((r.get('tool') or '', r.get('title') or ''))))


def pattern(r: dict) -> str:
    "What an 'always' covers: a command by its first two words, a fetch by its host, anything else by its kind and tool."
    if r['command']: return f"{r['kind']}:" + ' '.join(r['command'].split()[:2]).lower()
    if r['kind'] == 'fetch' and (m := re.search(r'https?://([^/\s]+)', ' '.join([r['title']] + r['locations']))): return f'fetch:{m[1].lower()}'
    return f"{r['kind']}:{r['tool'].lower()}"


def _cwd(store, tid) -> str:
    from . import agentchannels
    return agentchannels.cwd_of(store, tid)


def _inside(path: str, root: str) -> bool:
    import os
    if not path or not root: return False
    try: return os.path.commonpath([os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))]) == os.path.normcase(os.path.abspath(root))
    except ValueError: return False


def _pick(r: dict, allow: bool, always: bool = False) -> str:
    want = (('allow_always', 'allow_once') if always else ('allow_once', 'allow_always')) if allow else (('reject_always', 'reject_once') if always else ('reject_once', 'reject_always'))
    return next((o for o in want if o in r['options']), want[-1])          # never the other side's option when its own is not offered


def auto(store, tid: int, r: dict) -> tuple:
    "(answer, why) from Taskuary's own rules, or ('', '') when the owner has to answer."
    kept = store.perm_rule(tid, pattern(r))
    if kept == 'reject': return _pick(r, False), 'you said always reject for this'
    if kept == 'allow' and not r['risky']: return _pick(r, True), 'you said always allow for this'
    if r['kind'] in READS and not r['risky'] and (root := _cwd(store, tid)) and r['locations'] and all(_inside(l, root) for l in r['locations']):
        return _pick(r, True), 'a read inside its own checkout'
    return '', ''


def kind_of(said, offered) -> str:
    "An answer as one of the offered options - its id, its label (a generic answer road gives the label) or its number."
    w = ' '.join(str(said or '').split()).strip(' .!').lower()
    for i, o in enumerate(offered, 1):
        if w in (o, LABEL[o].lower(), str(i)): return o
    return ''


# WHAT IS ASKED, IN WORDS (the agent walk, 2026-11-09). A long shell line reached the owner as 'It wants to run "git add ... | tail -1; gi"':
# cut mid-word, and the step it was held for - the push at its end - past the cut. The card leads with the agent's own words for the step
# (`about`: its description) and what the shell gate holds in it (`what`, `why`), the command whole under a fold; a line of text (a bound
# chat, the rail) is cut on a word and says so
def cut(x, n: int) -> str:
    t = str(x or '')
    return t if len(t) <= n else (t[:n].rsplit(None, 1)[0] if any(c.isspace() for c in t[:n]) else t[:n]).rstrip() + '\u2026'


def held_for(r: dict, cwd: str = '') -> dict:
    "{'what', 'why'} of a command, in the shell gate's own words - '' where it holds nothing in it."
    from . import shellgate
    todo = shellgate.acts(r['command'], str(r['input'].get('cwd') or cwd or '')) if r['command'] else []
    return {k: '; '.join(dict.fromkeys(a[k] for a in todo)) for k in ('what', 'why')}


def asked(r: dict) -> str:
    "The step in a few words, for the line the owner's answer leaves in the chat: the agent's own, else what it does, else its title."
    return cut(r.get('about') or r.get('what') or (r['title'] if r['title'] != r['command'] else '') or (f"run `{r['command']}`" if r['command'] else r['tool']), 160)


def line(r: dict) -> str:
    where = f" ({', '.join(r['locations'][:3])})" if r['locations'] else ''
    what = r['title'] or r['tool']
    return f"wants to {what}{where}" if not r['command'] else f"wants to run `{cut(r['command'], 300)}`{where}"


def pending(tid: int = None, store=None) -> list:
    "The requests waiting on the owner, as the task chat draws them - of one store's tasks when it is named (a task id is per home)."
    with _LOCK: rows = [dict(p) for p in PENDING.values() if (tid is None or p['tid'] == int(tid)) and (store is None or p['store'] is store)]
    return [{'id': p['id'], 'tid': p['tid'], 'ref': task_ref(p['tid']), 'line': line(p['req']), 'title': p['req']['title'], 'tool': p['req']['tool'],
             'kind': p['req']['kind'], 'locations': p['req']['locations'], 'at': p['at'], 'until': p['until'], 'risky': p['req']['risky'],
             **{k: p['req'][k] for k in ('about', 'what', 'why', 'command')},
             'options': [{'kind': o, 'label': LABEL[o]} for o in p['req']['options']]} for p in sorted(rows, key=lambda p: p['at'])]


def ask(store, tid: int, request: dict, wait: float = None, timed_out=None) -> str:
    """THE SEAM. Blocks until answered (call it off an event loop). Returns one of the request's options. `timed_out()` is called when
    nobody answered - the refusal returned then is no owner's word, and a caller may file it for later (acpgate)."""
    from . import agents, agentchannels, workerstate as ws
    tid, r = int(tid), normal(request)
    if not agents.developer_mode(store): return _pick(r, False)
    got, why = auto(store, tid, r)
    if got:
        store.audit('task', tid, 'permission_auto', 'taskuary', 'system', {'pattern': pattern(r), 'answer': got, 'why': why})
        return got
    pid, wait = uuid.uuid4().hex[:12], TIMEOUT if wait is None else wait
    try: r.update(held_for(r, _cwd(store, tid)))
    except Exception as e: logger.debug(f'permission on {task_ref(tid)}: its step not read - {e}')
    g = ws.group_key(f'perm:{tid}:{pid}')
    live = ws._live(tid)            # the run that owns the task keys its requests (workerstate.record), else the asking session's
    rid, sid = ws.question_id(g, 1), (str(live.sid) if live else '') or r['sid'] or ws.current_sid(store, tid) or f'perm-{pid}'
    ws.hold(tid, sid, g, [rid])
    # on the rail first, then the card: what draws the card can already read the agent as waiting on the owner
    try: ws.record(store, tid, sid, 'approval_needed', request_id=rid, text=f'The agent {line(r)}', choices=[LABEL[o] for o in r['options']], source='permission')
    except Exception as e: logger.debug(f'permission on {task_ref(tid)}: not on the rail - {e}')
    with _LOCK: PENDING[pid] = {'id': pid, 'tid': tid, 'store': store, 'req': r, 'g': g, 'rid': rid, 'sid': sid, 'at': time.strftime('%Y-%m-%d %H:%M:%S'),
                                'until': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + wait))}
    try:
        store.audit('task', tid, 'permission_asked', 'agent', 'agent', {'pid': pid, 'pattern': pattern(r)})
        try: agentchannels.permission_asked(store, tid, pid, r)
        except Exception as e: logger.warning(f'permission on {task_ref(tid)}: not put on its channel - {e}')
        out = ws.wait_held(g, wait)
    finally:
        with _LOCK: PENDING.pop(pid, None)
    ans = kind_of((out or {}).get(rid), r['options'])
    if not ans:
        ans = _pick(r, False)
        said = (f"No answer in {round(wait / 60) or 1} min{'s' if round(wait / 60) != 1 else ''} - the agent's request was refused: it {line(r)}."
                if out is None and not ws.STOP.is_set() else CLOSED_FIRST.format(line(r)))
        try: ws.record(store, tid, sid, 'answered', request_id=rid, text='timed out - refused', source='permission')
        except Exception: pass
        store.add_comment(tid, 'taskuary', 'agent', said)
        try: agentchannels.permission_done(store, tid, pid, said)
        except Exception as e: logger.debug(f'permission on {task_ref(tid)}: timeout line not posted - {e}')
        if timed_out: timed_out()
        return ans
    if ans.endswith('_always'): store.set_perm_rule(tid, pattern(r), 'allow' if ans.startswith('allow') else 'reject')
    store.audit('task', tid, 'permission_answered', 'owner', detail={'pid': pid, 'answer': ans, 'pattern': pattern(r), 'asked': asked(r)})
    try:                                           # ...the turn that waited on it hears it now: his press stands where he made it
        from . import conversation
        conversation.hear_press(store, tid, 'permission_answered')
    except Exception as e: logger.debug(f'permission on {task_ref(tid)}: its answer not written as heard - {e}')
    return ans


def answer(store, tid: int, pid: str, option: str, actor: str = 'owner') -> dict:
    """The OWNER's answer - the task chat's button, or the owner's own reply on a bound channel (agentchannels checks who wrote it). A
    teammate's never reaches here: no road hands one in."""
    from . import agentchannels, workerstate as ws
    if actor != 'owner': raise PermissionError("only the owner answers an agent's permission request")
    with _LOCK: p = PENDING.get(str(pid))
    if not p or p['tid'] != int(tid) or p['store'] is not store: return {'ok': False, 'why': 'that request is no longer waiting'}
    o = kind_of(option, p['req']['options'])
    if not o: raise ValueError(f"answer one of: {', '.join(LABEL[x] for x in p['req']['options'])}")
    h = ws.HELD.get(p['g'])
    if not h: return {'ok': False, 'why': 'that request is no longer waiting'}
    ws._answer_held(store, int(tid), h, {p['rid']: o}, actor)
    said = f"{LABEL[o]} - {task_ref(tid)} {line(p['req'])}."
    try: agentchannels.permission_done(store, int(tid), pid, said)
    except Exception as e: logger.debug(f'permission on {task_ref(tid)}: answer line not posted - {e}')
    return {'ok': True, 'answer': o, 'says': said}


SET_ASIDE_SAID = 'Set aside when you moved on - the agent was refused: it {}. Ask it to bring it back if it is still wanted.'
def set_aside(store, tid: int) -> list:
    """The conversation on task `tid` moved on past its waiting permission cards (proposals.move_on, the owner 2026-11-10: "once youa re passed
    it, it should stay where it is with buttons grayed out"): each is refused - never allowed on nobody's press - and the line stays in its place."""
    from . import agentchannels, workerstate as ws
    with _LOCK: ps = [p for p in PENDING.values() if p['tid'] == int(tid) and p['store'] is store]
    out = []
    for p in ps:
        if not (h := ws.HELD.get(p['g'])): continue
        ws._answer_held(store, int(tid), h, {p['rid']: _pick(p['req'], False)}, 'taskuary')
        said = SET_ASIDE_SAID.format(line(p['req']))
        store.add_comment(int(tid), 'taskuary', 'agent', said); out.append(p['id'])
        try: agentchannels.permission_done(store, int(tid), p['id'], said)
        except Exception as e: logger.debug(f'permission on {task_ref(tid)}: set-aside line not posted - {e}')
    return out


# A REQUEST WHOSE ASKER IS GONE (the agent walk, 2026-11-09). PENDING is this process's own: Taskuary killed while an agent waited on the
# owner's Allow, the next run found the request open in the worker's record with nothing holding it - no card, no line, and the step it
# had asked for stood in the transcript as the last thing the agent did. A clean close says the request was refused (ask's own ending);
# a kill says nothing, so the next start says it, before the run's ending is written (terminal.recover_after_restart): the request is
# closed in the record and the task reads that it was never run. A run the record already ended is history, and is left as it reads
CLOSED_FIRST = "The agent's request was refused - Taskuary closed first: it {}."
def refuse_orphans(store) -> list:
    "Every permission request the record holds open with nobody in this process asking it: refused, and said on its task - [task ids]."
    from . import workerstate as ws
    with _LOCK: held = {p['rid'] for p in PENDING.values() if p['store'] is store}
    tids = [r['TaskId'] for r in store._rows(
        "SELECT DISTINCT e.TaskId FROM worker_event e WHERE e.Kind='approval_needed' AND e.Source='permission' AND NOT EXISTS "
        "(SELECT 1 FROM worker_event a WHERE a.TaskId=e.TaskId AND a.Kind='answered' AND a.RequestId=e.RequestId)")]
    out = []
    for tid in tids:
        evs = ws.events(store, tid); said = [e for e in evs if e['Kind'] not in ws.NOTES]
        if not said or said[-1]['Kind'] in ws.TERMINAL: continue
        for e in ws.open_requests(evs):
            if e.get('Source') != 'permission' or e['RequestId'] in held: continue
            ws.record(store, tid, e['Sid'], 'answered', request_id=e['RequestId'], text='Taskuary closed first - refused', source='permission')
            store.add_comment(tid, 'taskuary', 'agent', CLOSED_FIRST.format(str(e.get('Text') or '').removeprefix('The agent ') or 'asked for your OK'))
            out.append(tid)
    return out


# ── the ACP road (acpgate) ─────────────────────────────────────────────────────────────────────────────────────────────────
def from_acp(params: dict) -> dict:
    "session/request_permission params as a request."
    tc = (params or {}).get('toolCall') or {}
    raw = tc.get('rawInput') if isinstance(tc.get('rawInput'), dict) else {}
    cmd = raw.get('command') or raw.get('cmd') or ''
    if isinstance(cmd, list): cmd = ' '.join(map(str, cmd))
    return {'tool': str(((tc.get('_meta') or {}).get('claudeCode') or {}).get('toolName') or tc.get('title') or tc.get('kind') or 'a tool'),
            'kind': tc.get('kind') or 'other', 'title': tc.get('title') or '', 'input': raw, 'command': str(cmd), 'sid': (params or {}).get('sessionId') or '',
            'locations': [l.get('path') for l in tc.get('locations') or [] if isinstance(l, dict) and l.get('path')],
            'options': [o.get('kind') for o in (params or {}).get('options') or [] if o.get('kind') in OPTIONS] or ['allow_once', 'reject_once']}


def to_acp(params: dict, answer: str) -> dict:
    "The ACP outcome for an answer - always the ONCE option of its side: an 'always' is ours to keep, never the agent's."
    from . import acp as acp_mod
    return acp_mod.pick((params or {}).get('options'), str(answer).startswith('allow'))


def acp(store, tid: int, params: dict, wait: float = None) -> tuple:
    "(outcome, answer) for one ACP permission request put to the owner - the whole of it, for a caller with no rules of its own."
    a = ask(store, tid, from_acp(params), wait=wait)
    return to_acp(params, a), a
