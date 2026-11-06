"""AGENT CHANNELS: ONE CHAT INTO ONE RUNNING AGENT (the owner, 2026-11-06: "a way to share the coding agent on my machine through you sending
me slack or teams to that channel that would just keep talking to same agents" ... "it would be protected to only people on your team" ...
"so i can get a bunch of people to code project together through whatsapp").

WhatsApp, Telegram, Slack and Teams are the same kind of doorway. A BINDING (Developer mode only) is:
    kind (whatsapp|telegram|slack|teams), chat, the task whose agent it talks to - or none: "the coding agents" (conductor mode, the
    owner alone, devphone's three moves typed as words) - the repo it is scoped to, and its members [{name, id, role: owner|teammate}].

IN. A line in a bound chat from a listed member goes to the bound agent through its own box (waitroom.add - tell_agent's road):
  - the owner's words are the owner's;
  - a teammate's carry "Gail Moreno (teammate)" and a guard - in the words the agent reads and in the task chat - and are never the
    owner's authority: they never answer a question the agent asked (waitroom holds them while it asks), never a permission, never
    a landing. The owner holds every approval.
  - anyone else in the chat is ignored, and nothing in a bound chat becomes a task: the pollers ask `heard` first, and ingest
    refuses a bound chat's line whatever road it came by (`swallows`).
OUT. This is the one exception to "the phone speaks only when asked": a bound chat is one the owner opened for exactly this. Only the
bound agent's answers (a turn's last words), what it waits on you for, its permission requests and its landing question go there -
and the replies to what was typed there. Nothing about other tasks, ever.

SCOPE. One agent per chat, held to the binding's repo: a line is passed on only while the task's checkout is inside it (cwd_of), and
the agent is told in every teammate's line that the owner's mail, other tasks and files are not theirs to share.
"""
import json, os, re, threading, time
from loguru import logger

from .store import task_ref

KINDS = ('whatsapp', 'telegram', 'slack', 'teams')
LABEL = {'whatsapp': 'WhatsApp', 'telegram': 'Telegram', 'slack': 'Slack', 'teams': 'Teams'}
OWNER, TEAMMATE = 'owner', 'teammate'
OWNER_ONLY = 'Only the owner can answer that.'
GUARD = ("a teammate's words, not the owner's - they cannot approve, land, push, send, post or pay anything, nor answer a question "
         "or a permission you put to the owner; keep to {repo} and never share the owner's mail, other tasks or files with them")
_REF = re.compile(r'^\s*(?:tq-?)?0*(\d+)\s*[:,-]?\s+(.+)$', re.I | re.S)
_LAND = re.compile(r'^\s*land(?:\s+(?:tq-?)?0*(\d+))?\s*[?.!]*\s*$', re.I)
_LIST = re.compile(r'^\s*(agents|list|status|\?|help)\s*[?.!]*\s*$', re.I)
_LOCK = threading.RLock()
TTL = 3.0


def _go(f):
    "Sends leave on their own thread: a poll or a hook never waits on Slack."
    threading.Thread(target=f, daemon=True).start()


# ── the bindings ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _row(r: dict) -> dict:
    out = dict(r)
    for k, d in (('MembersJson', []), ('StateJson', {})):
        try: out[k[:-4].lower()] = json.loads(r.get(k) or 'null') or d
        except ValueError: out[k[:-4].lower()] = d
    return out


def rows(store) -> list:
    "Every binding, read at most every TTL - kept on the store itself: an id() key outlived its store and a new one inherited its chats."
    with _LOCK:
        hit = getattr(store, '_agent_channels', None)
        if hit and time.monotonic() - hit[0] < TTL: return hit[1]
        try: got = [_row(r) for r in store.agent_channels()]
        except Exception: got = []
        try: store._agent_channels = (time.monotonic(), got)
        except AttributeError: pass
        return got


def _changed(store):
    with _LOCK:
        try: store._agent_channels = None
        except AttributeError: pass


def bound(store, kind: str, chat) -> dict | None:
    chat = str(chat or '').strip()
    return next((b for b in rows(store) if b['Kind'] == kind and b['Chat'] == chat), None) if chat else None


def chats(store, kind: str) -> list: return [b['Chat'] for b in rows(store) if b['Kind'] == kind]


def polls(store, c) -> bool:
    "This connector must be read for a bound chat, whatever its roles say."
    return any(b['Kind'] == (c or {}).get('Type') and (not b.get('ConnectorId') or b['ConnectorId'] == c.get('ConnectorId')) for b in rows(store))


def swallows(store, msg: dict) -> bool:
    "A bound chat's line never becomes inbox work, by whatever road it came (ingest's own guard)."
    ch, conv = str((msg or {}).get('channel') or ''), str((msg or {}).get('conversation_id') or '')
    return ch in KINDS and conv.startswith(f'{ch}:') and bool(bound(store, ch, conv[len(ch) + 1:]))


def following(store, tid: int) -> list:
    "The bindings that hear this task's agent: bound to it, or a conductor chat the owner told it from."
    return [b for b in rows(store) if b.get('TaskId') == int(tid) or (b.get('TaskId') is None and int(tid) in (b['state'].get('follow') or []))]


def _save_state(store, b: dict, **kw):
    with _LOCK:
        cur = _row(store.agent_channel(b['ChannelId']) or {})
        st = {**(cur.get('state') or {}), **kw}
        store.set_agent_channel(b['ChannelId'], StateJson=json.dumps(st))
        b['state'] = st
        _changed(store)


# ── who is speaking ───────────────────────────────────────────────────────────────────────────────────────────────────
def norm_id(kind: str, x) -> str:
    "A member's id as the channel spells its sender: a WhatsApp number's digits, a Slack member id, a Telegram number, a Teams id or address."
    x = str(x or '').strip()
    if kind == 'whatsapp':
        x = x.split(':', 1)[1] if x.lower().startswith('whatsapp:') else x
        return re.sub(r'[^0-9a-z]', '', x.partition('@')[0].split(':')[0].lower())
    return x.upper() if kind == 'slack' else x.lower()


def member(b: dict, senders, from_me: bool = False) -> dict | None:
    """The listed member who wrote this, or None. `from_me` is the platform's own word that the owner's account sent it (WhatsApp's
    fromMe, Teams' own id) - the owner. A Telegram or Slack owner is matched by the id the owner gave, like anyone."""
    ms = b.get('members') or []
    if from_me: return next((m for m in ms if m.get('role') == OWNER), None)
    ids = {norm_id(b['Kind'], s) for s in ([senders] if isinstance(senders, str) else senders or ()) if str(s or '').strip()} - {''}
    hits = [m for m in ms if norm_id(b['Kind'], m.get('id')) in ids]
    # the owner's account only ever speaks as the owner: a teammate entry carrying the owner's own id is not a second door
    return next((m for m in hits if m.get('role') == OWNER), None) or (hits[0] if hits else None)


def label(m: dict) -> str: return 'the owner' if m.get('role') == OWNER else f"{m.get('name') or 'someone'} (teammate)"


# ── scope ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def cwd_of(store, tid) -> str:
    "The checkout the task's agent works in: its live session, else the last one, else where its work started (landing)."
    from . import peers, landing
    try: c = peers._cwd_of(int(tid))
    except Exception: c = ''
    if not c:
        try: c = (store.last_transcript(int(tid)) or {}).get('Cwd') or ''
        except Exception: c = ''
    return c or landing.record(store, tid).get('cwd') or ''


def inside(path: str, root: str) -> bool:
    if not path or not root: return False
    a, r = (os.path.normcase(os.path.realpath(os.path.abspath(x))) for x in (path, root))
    try: return os.path.commonpath([a, r]) == r
    except ValueError: return False


def in_repo(store, b: dict, tid: int) -> tuple:
    "(ok, why) - the hard check: the task's checkout lies inside the binding's repo."
    repo = b.get('Repo') or ''
    if not repo: return (b.get('TaskId') is None, 'this channel names no repo')    # a conductor chat may reach any repo; a bound task may not
    c = cwd_of(store, tid)
    if not c: return False, f'Taskuary sees no checkout for {task_ref(tid)} - start its agent on the desktop first'
    return (True, '') if inside(c, repo) else (False, f'the agent on {task_ref(tid)} works outside {repo_name(repo)}')


def repo_name(repo: str) -> str:
    from . import peers
    try: return peers.repo_label(repo) or repo
    except Exception: return repo


# ── setting one up ────────────────────────────────────────────────────────────────────────────────────────────────────
def _connector(store, kind: str, cid=None):
    cs = [c for c in (store.connectors_by_type(kind) or []) if c and c.get('Active')]
    return next((c for c in cs if not cid or c['ConnectorId'] == int(cid)), None)


def default_owner_id(store, kind: str, c) -> str:
    "Where the platform cannot say 'the owner sent it', the owner's own id - Telegram's private Assistant chat id IS their user id."
    if kind == 'telegram':
        from . import remote_assistant
        x = str(remote_assistant.chat_of(c) or '') if c else ''
        return x if x.isdigit() else ''
    return ''


def bind(store, kind: str, chat: str, task_id=None, repo: str = '', members: list = None, connector_id=None, actor: str = 'owner') -> dict:
    from . import agents
    if not agents.developer_mode(store): raise PermissionError('agent channels are part of Developer mode - it is off')
    kind, chat = str(kind or '').lower(), str(chat or '').strip()
    if kind not in KINDS: raise ValueError(f"the channel is one of: {', '.join(KINDS)}")
    if not chat: raise ValueError('name the chat')
    c = _connector(store, kind, connector_id)
    if not c: raise ValueError(f'no {LABEL[kind]} connection is switched on')
    if kind in ('whatsapp', 'telegram'):
        from . import remote_assistant
        if str(remote_assistant.chat_of(store.get_connector(c['ConnectorId'], with_secret=True) or c) or '') == chat:
            raise ValueError('that chat is your Assistant chat - it already reaches the coding agents (Developer mode)')
    if bound(store, kind, chat) or any(r['Kind'] == kind and r['Chat'] == chat for r in store.agent_channels()):
        raise ValueError('that chat already talks to an agent - one agent per chat')
    tid = int(task_id) if str(task_id or '').strip() else None
    if tid is not None:
        t = store.get_task(tid)
        if not t: raise ValueError(f'there is no task {task_ref(tid)}')
        if (t.get('Kind') or '') != 'coding': raise ValueError('only a coding task has an agent a chat can talk to')
    repo = str(repo or '').strip() or (cwd_of(store, tid) if tid else '')
    if tid is not None and not repo: raise ValueError(f'name the repo {task_ref(tid)} works in - Taskuary sees no checkout for it yet')
    if repo and not os.path.isdir(repo): raise ValueError(f'{repo} is not a folder on this computer')
    ms, seen = [], set()
    for m in members or []:
        name, mid, role = ' '.join(str(m.get('name') or '').split())[:80], str(m.get('id') or '').strip()[:120], str(m.get('role') or TEAMMATE)
        if role not in (OWNER, TEAMMATE): raise ValueError('a member is the owner or a teammate')
        if role == TEAMMATE and not (name and mid): raise ValueError(f'a teammate needs a name and their {LABEL[kind]} id')
        if norm_id(kind, mid) in seen and mid: raise ValueError(f'{mid} is listed twice')
        seen.add(norm_id(kind, mid)); ms.append({'name': name, 'id': mid, 'role': role})
    if sum(m['role'] == OWNER for m in ms) > 1: raise ValueError('there is one owner')
    if not any(m['role'] == OWNER for m in ms):
        ms.insert(0, {'name': store.owner().get('owner') or 'the owner', 'id': default_owner_id(store, kind, c), 'role': OWNER})
    own = next(m for m in ms if m['role'] == OWNER)
    if kind in ('telegram', 'slack') and not own['id']:
        raise ValueError(f"{LABEL[kind]} cannot tell Taskuary which messages are yours - add your own {LABEL[kind]} id")
    if tid is None and any(m['role'] == TEAMMATE for m in ms):
        raise ValueError('"the coding agents" reach every agent you run - that chat is yours alone; bind a task to code with teammates')
    cid = store.add_agent_channel({'Kind': kind, 'Chat': chat, 'ConnectorId': c['ConnectorId'], 'TaskId': tid, 'Repo': repo,
                                   'MembersJson': json.dumps(ms), 'StateJson': json.dumps({'since': time.time()})})
    _changed(store)
    store.audit('agentchannel', cid, 'agent_channel_bound', actor, detail={'kind': kind, 'task': tid, 'teammates': sum(m['role'] == TEAMMATE for m in ms)})
    if tid: store.add_comment(tid, 'taskuary', 'agent', f"This agent now talks on {LABEL[kind]} too" + (f" - with {', '.join(m['name'] for m in ms if m['role'] == TEAMMATE)} (teammates)" if len(ms) > 1 else '') + '.')
    return view_one(store.agent_channel(cid))


def unbind(store, cid: int, actor: str = 'owner') -> dict:
    b = store.agent_channel(cid)
    if not b: raise LookupError('no such channel')
    store.delete_agent_channel(cid); _changed(store)
    store.audit('agentchannel', cid, 'agent_channel_unbound', actor, detail={'kind': b['Kind'], 'task': b.get('TaskId')})
    if b.get('TaskId'): store.add_comment(b['TaskId'], 'taskuary', 'agent', f"This agent no longer talks on {LABEL.get(b['Kind'], b['Kind'])}.")
    return {'ok': True}


def view_one(r: dict) -> dict:
    b = _row(r)
    return {'id': b['ChannelId'], 'kind': b['Kind'], 'label': LABEL.get(b['Kind'], b['Kind']), 'chat': b['Chat'], 'task': b.get('TaskId'),
            'ref': task_ref(b['TaskId']) if b.get('TaskId') else '', 'repo': b.get('Repo') or '', 'repoName': repo_name(b.get('Repo') or '') if b.get('Repo') else '',
            'members': b['members'], 'at': b.get('CreatedAt')}


def view(store, task_id=None) -> dict:
    "What the setup card draws: the bindings (this task's, or all), the connections it can use and the chats Taskuary already knows."
    bs = [view_one(r) for r in store.agent_channels() if task_id is None or r.get('TaskId') == int(task_id)]
    kinds = []
    for k in KINDS:
        c = _connector(store, k)
        if not c: continue
        known = [{'chat': s['Address'], 'name': str(s.get('Owner') or s.get('Name') or '').replace('discovered: ', '') or s['Address']}
                 for s in store.list_sources(active_only=False) if s.get('Channel') == k and s.get('Address') and s['Address'] not in ('*',)]
        kinds.append({'kind': k, 'label': LABEL[k], 'connector': c['ConnectorId'], 'chats': known[:40],
                      'ownerId': default_owner_id(store, k, store.get_connector(c['ConnectorId'], with_secret=True)),
                      'needsOwnerId': k in ('telegram', 'slack')})
    return {'channels': bs, 'kinds': kinds, 'owner': store.owner().get('owner') or 'the owner',
            'repo': cwd_of(store, task_id) if task_id else ''}


# ── in ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def heard(store, kind: str, chat, senders, text: str, ext: str, from_me: bool = False, name: str = '') -> bool:
    """One line from a chat. False when the chat is not bound (the poller goes on as before); True when it is - routed, refused or
    ignored, it is never the inbox's."""
    b = bound(store, kind, chat)
    if not b: return False
    from . import agents
    m = member(b, senders, from_me)
    text = str(text or '').strip()
    if not store.agent_channel_log(b['ChannelId'], ext or f'{kind}:{chat}:{time.time_ns()}', 'in', (m or {}).get('name') or '',
                                   (m or {}).get('role') or 'ignored', b.get('TaskId'), text[:4000] if m else ''):
        return True                                                     # read before, or our own post read back
    if not m:
        store.audit('agentchannel', b['ChannelId'], 'agent_channel_ignored', 'router', 'system', {'kind': kind})
        return True
    if not text or not agents.developer_mode(store): return True
    if m['role'] == OWNER and _echo(store, b, text): return True
    try: (_owner if m['role'] == OWNER else _teammate)(store, b, m, text)
    except Exception as e:
        logger.warning(f"agent channel {b['ChannelId']}: a line was not passed on - {e}")
        say(store, b, f'That did not reach the agent - {e}')
    return True


def _echo(store, b: dict, text: str) -> bool:
    "Our own post read back as the owner's (a Slack user token, Teams' own sign-in), where its id did not match: the same words, just now."
    w = ' '.join(text.split())
    return any(r['Dir'] == 'out' and ' '.join(str(r.get('Text') or '').split()) == w for r in store.agent_channel_msgs(b['ChannelId'], 20))


def _picked(b: dict, text: str):
    "The option a reply names while a question is up: its number, or its words."
    q = (b.get('state') or {}).get('ask')
    if not q: return None, None
    w = ' '.join(text.split()).strip(' .!').lower()
    for i, (lbl, act) in enumerate(q.get('options') or [], 1):
        if w in (str(i), lbl.lower()): return q, act
    return q, None


def _owner(store, b, m, text):
    from . import permissions, landing
    q, act = _picked(b, text)
    if act is not None:
        if q['kind'] == 'perm':
            out = permissions.answer(store, q['tid'], q['pid'], act, 'owner')
            if not out.get('ok'): say(store, b, f"Nothing changed - {out.get('why')}."); _save_state(store, b, ask=None)
            return
        if q['kind'] == 'land':
            _save_state(store, b, ask=None)
            try: out = landing.land(store, int(q['tid']), act, 'owner')
            except (landing.Refused, ValueError, RuntimeError) as e: return say(store, b, f'Nothing landed - {e}')
            return say(store, b, out['says'])
    tid = b.get('TaskId')
    if (lm := _LAND.match(text)) and (tid or lm.group(1)): return ask_landing(store, b, int(lm.group(1) or tid))
    if tid is None:                                                     # the coding agents, as words
        if _LIST.match(text): return say(store, b, _agents(store, b))
        if not (rm := _REF.match(text)): return say(store, b, 'Say "agents" for the list, "TQ-0123 your words" to tell one, or "land TQ-0123".')
        tid, text = int(rm.group(1)), rm.group(2).strip()
        ok, why = in_repo(store, b, tid)
        if not ok: return say(store, b, f'Nothing was sent - {why}.')
        _save_state(store, b, follow=list(dict.fromkeys((b['state'].get('follow') or []) + [tid]))[-20:])
    return _tell(store, b, tid, text, None)


def _teammate(store, b, m, text):
    q, act = _picked(b, text)
    if q and act is not None: return say(store, b, f"{OWNER_ONLY} {m.get('name') or 'A teammate'}'s reply was not taken as an answer.")
    if _LAND.match(text): return say(store, b, f'{OWNER_ONLY} Landing is the owner\'s.')
    if not b.get('TaskId'): return                                     # never reached: a conductor chat has no teammates
    return _tell(store, b, b['TaskId'], text, m)


def framed(b: dict, m: dict, text: str) -> str:
    "A teammate's line as the agent reads it - one line, a newline is Enter in a TUI."
    return ' '.join(f"[{label(m)} on {LABEL[b['Kind']]} - {GUARD.format(repo=repo_name(b.get('Repo') or '') or 'this repo')}] {text}".split())


def _tell(store, b, tid: int, text: str, m):
    from . import waitroom
    ok, why = in_repo(store, b, tid)
    if not ok: return say(store, b, f'Nothing was sent - {why}.')
    if not store.get_task(tid): return say(store, b, f'There is no task {task_ref(tid)}.')
    from . import terminal as term
    if (why := term.stranger_now(store, tid)): return say(store, b, f'Nothing was sent to {task_ref(tid)} - {why}.')
    if m is None:
        store.add_comment(tid, 'owner', 'human', text)
        o = waitroom.add(store, tid, text, 'owner')
    else:
        store.add_comment(tid, 'teammate', 'human', f"{label(m)} on {LABEL[b['Kind']]}: {text}")
        o = waitroom.add(store, tid, framed(b, m, text), TEAMMATE)
    store.audit('task', tid, 'agent_channel_tell', 'owner' if m is None else 'teammate', detail={'channel': b['ChannelId'], 'chars': len(text)})
    if b.get('TaskId') is None:
        say(store, b, f"Told {task_ref(tid)} - " + ('it has it now.' if o.get('delivered') else 'it goes in when the agent stops.'))


def _agents(store, b) -> str:
    from . import devphone
    rs = [r for r in devphone.rows(store) if not b.get('Repo') or in_repo(store, b, r['tid'])[0]]
    if not rs: return 'No coding agent is running' + (f" in {repo_name(b['Repo'])}" if b.get('Repo') else '') + ' right now.'
    return '\n'.join(f"{r['ref']} {r['title'][:60]} - {r['repo'] or 'no repo'} on {r['branch'] or '?'}, {r['state']}" for r in rs)


# ── out ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _send(store, b: dict, body: str) -> str:
    "One message to the bound chat, by the channel's own sender; the provider's id of it when it gives one back."
    k, chat, cid = b['Kind'], b['Chat'], b.get('ConnectorId')
    if k in ('whatsapp', 'telegram'):
        from . import messengers
        (messengers.wa_send if k == 'whatsapp' else messengers.tg_send)(store, chat, body, connector_id=cid)
        return ''
    from . import outbound
    if k == 'slack': return f"slack:{chat}:{outbound.send_slack(store, chat, body, cid).get('ts') or ''}"
    return f"teams:{chat}:{outbound.send_teams(store, chat, body, cid, want_id=True).get('id') or ''}"


def say(store, b: dict, text: str, tid=None):
    "Everything that reaches a bound chat leaves through here."
    from . import chatformat
    body = chatformat.render(str(text or '').strip(), b['Kind'])
    if not body: return
    def go():
        for part in chatformat.split(body, 3500):
            try: ext = _send(store, b, part)
            except Exception as e:
                logger.warning(f"agent channel {b['ChannelId']} ({b['Kind']}): not posted - {e}"); return
            store.agent_channel_log(b['ChannelId'], ext if ext and not ext.endswith(':') else f"out:{time.time_ns()}", 'out', 'taskuary', '', tid or b.get('TaskId'), part)
    _go(go)


def on_event(store, tid: int, kind: str, text: str = '', source: str = ''):
    """workerstate.record's word that a turn ended or the agent asks the owner something: the answer, or what it waits on, to the chats
    that hear this task. A permission request says itself (permission_asked)."""
    if source == 'permission' or not rows(store): return
    bs = following(store, tid)
    if not bs: return
    from . import agents
    if not agents.developer_mode(store): return
    words = str(text or '').strip()
    if kind == 'turn_end':
        if not words or words == 'interrupted': return
        line = words
    else: line = f'{task_ref(tid)} is waiting on you: {words}' if words else f'{task_ref(tid)} is waiting on you.'
    for b in bs: say(store, b, (f'{task_ref(tid)}: ' if b.get('TaskId') is None and kind == 'turn_end' else '') + line, tid)


def _numbered(options: list) -> str: return '\n'.join(f'{i}. {lbl}' for i, (lbl, _) in enumerate(options, 1))


def permission_asked(store, tid: int, pid: str, r: dict):
    from . import permissions
    bs = following(store, tid)
    for b in bs:
        opts = [(permissions.LABEL[o], o) for o in r['options']]
        _save_state(store, b, ask={'kind': 'perm', 'tid': int(tid), 'pid': pid, 'options': opts})
        own = next((x.get('name') for x in b['members'] if x.get('role') == OWNER), '') or 'the owner'
        say(store, b, f"{task_ref(tid)} asks permission: it {permissions.line(r)}.\nReply with a number - only {own} can answer:\n{_numbered(opts)}", tid)


def permission_done(store, tid: int, pid: str, said: str):
    for b in following(store, tid):
        if ((b.get('state') or {}).get('ask') or {}).get('pid') == pid:
            _save_state(store, b, ask=None)
            say(store, b, said, tid)


def ask_landing(store, b: dict, tid: int):
    from . import landing
    ok, why = in_repo(store, b, tid)
    if not ok: return say(store, b, f'Nothing to ask - {why}.')
    s = landing.state(store, tid)
    if not s: return say(store, b, f'{task_ref(tid)} has no branch Taskuary saw it start from - nothing to land.')
    if not s['ask']: return say(store, b, f"{task_ref(tid)}: {s['line']}")
    opts = [(a['label'], a['how']) for a in s['answers']]
    _save_state(store, b, ask={'kind': 'land', 'tid': int(tid), 'options': opts})
    prop = s.get('proposal') or {}
    said = f" The agent proposes {landing.HOW[prop['how']]}." if prop.get('how') else ''
    own = next((x.get('name') for x in b['members'] if x.get('role') == OWNER), '') or 'the owner'
    say(store, b, f"{task_ref(tid)}: {s['line']}{said}\nReply with a number - it lands only on {own}'s pick:\n{_numbered(opts)}", tid)


def landing_proposed(store, tid: int):
    "The agent proposed how its branch lands: the question goes to the chats that hear it."
    for b in following(store, tid): ask_landing(store, b, tid)


# ── Slack: a bound channel is read here, by its own cursor ───────────────────────────────────────────────────────────
def poll_slack(store, c: dict, tok: str) -> int:
    "Each Slack channel bound on this connection, read since its cursor; top-level lines only (a thread's replies are not in history)."
    from .channels import _slack
    n = 0
    for b in [x for x in rows(store) if x['Kind'] == 'slack' and x.get('ConnectorId') in (None, c['ConnectorId'])]:
        since = float(b['state'].get('cursor') or b['state'].get('since') or time.time())
        try: hist = _slack(tok, 'conversations.history', channel=b['Chat'], oldest=since, limit=100)
        except Exception as e:
            logger.warning(f"slack agent channel {b['Chat']}: not read - {e}"); continue
        msgs = sorted(hist.get('messages') or [], key=lambda m: float(m.get('ts') or 0))
        for m in msgs:
            if m.get('subtype') or m.get('bot_id'): continue           # the app's own posts, joins, edits
            n += heard(store, 'slack', b['Chat'], [m.get('user')], m.get('text') or '', f"slack:{b['Chat']}:{m.get('ts')}")
        if msgs: _save_state(store, b, cursor=max(float(m.get('ts') or 0) for m in msgs))
    return n
