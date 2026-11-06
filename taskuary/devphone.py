"""THE PHONE INTO THE RUNNING CODING AGENTS (the owner, 2026-11-06: "the phone should be able to connect not to all tasks but developer
mode and send messages directly into running agents remotely").

Three tools the Assistant has in the owner's private phone chat, and only there, and only with Developer mode on - with it off they do
not exist: not in the prompt, not callable.
  coding_agents         every coding agent live now: its task, repo, branch, state, files changed and last line
  tell_agent(task, text) the owner's words into that agent exactly as typed in its box (the waiting room), filed as the owner's
  land(task, how?)      the landing question asked back in the chat - its answers are picks, and only the owner's pick lands anything

They are look-ups run in the turn, so the Assistant answers with what they say. The phone still speaks only while the owner talks there:
nothing here sends a line on its own - no pings about tasks, agents finishing or notes between agents.
"""
import contextlib, re, threading

from .store import task_ref

KINDS = ('coding_agents', 'tell_agent', 'land')
_ON = threading.local()                      # armed for one phone turn (remote_assistant.respond), on the thread that runs it
_REF = re.compile(r'(?:tq-?)?0*(\d+)', re.I)
LAND_ACT = 'land'


@contextlib.contextmanager
def armed(store):
    from . import agents
    _ON.on, _ON.choices = agents.developer_mode(store), []
    try: yield
    finally: _ON.on, _ON.choices = False, []


def live() -> bool:
    from . import concierge
    return bool(getattr(_ON, 'on', False)) and concierge.DELIVERY.get() == concierge.PHONE


def runs(kind: str) -> bool: return kind in KINDS and live()


def valid(kind: str, p: dict) -> str:
    miss = {'tell_agent': ('task', 'text'), 'land': ('task',)}.get(kind, ())
    gone = [k for k in miss if not str((p or {}).get(k) or (p or {}).get('ref' if k == 'task' else '') or '').strip()]
    return f"{kind} needs {', '.join(gone)}" if gone else ''


def block() -> str:
    "What the phone's Assistant is told it can do with the coding agents - '' off the phone or with Developer mode off."
    if not live(): return ''
    return ('THE CODING AGENTS, FROM HERE (Developer mode): coding_agents {} lists every coding agent live now - task, repo, branch, state, '
            'files changed, last line; tell_agent {"task": "TQ-0123", "text": "..."} puts the owner\'s words into that agent as if typed in '
            'its box - their words as they said them, never yours; land {"task": "TQ-0123"} asks how its branch lands - the answers come up '
            'as choices under your line and only the owner\'s pick lands it, so never say it landed.\n\n')


def _tid(p: dict) -> int:
    m = _REF.fullmatch(str((p or {}).get('task') or (p or {}).get('ref') or '').strip())
    if not m: raise LookupError('name the task as TQ-0123 - coding_agents lists them')
    return int(m.group(1))


def rows(store) -> list:
    "Each live coding agent, as the phone describes it."
    from . import landing, peers, terminal as term, waitroom
    out = []
    for t in peers._cli_sessions():
        st = waitroom.state(store, t.task_id)[0]
        r = landing.record(store, t.task_id)
        try: files = len(t.files())
        except Exception: files = 0
        try: last = next((l.strip() for l in reversed(term.asking_lines(t.sid, 3)) if l.strip()), '')
        except Exception: last = ''
        out.append({'tid': t.task_id, 'ref': task_ref(t.task_id), 'title': (store.get_task(t.task_id) or {}).get('Title') or '',
                    'repo': peers.repo_label(t.cwd), 'branch': r.get('branch') or landing.head_branch(t.cwd) or '',
                    'state': {'parked': 'idle at its prompt', 'asking': 'asking you'}.get(st, st), 'files': files, 'last': last[:160]})
    return out


def agents_text(store) -> str:
    rs = rows(store)
    if not rs: return 'No coding agent is running right now.'
    return '\n'.join(f"{r['ref']} {r['title'][:60]} - {r['repo'] or 'no repo'} on {r['branch'] or '?'}, {r['state']}, "
                     f"{r['files']} file{'s' if r['files'] != 1 else ''} changed" + (f" - last: {r['last']}" if r['last'] else '') for r in rs)


def tell(store, p: dict) -> str:
    """The owner's words into the agent on that task, the road its box takes (waitroom.add) - typed at once when it is idle, as the answer
    when it is asking, else at its next stop - and filed on the task as the owner's own message."""
    from . import peers, waitroom
    tid, text = _tid(p), ' '.join(str((p or {}).get('text') or '').split())
    if not text: raise LookupError('tell_agent needs `text` - the owner\'s words for the agent')
    if not any(t.task_id == tid for t in peers._cli_sessions()):
        return f"No coding agent is running on {task_ref(tid)} - nothing was sent. coding_agents lists the ones that are."
    store.add_comment(tid, 'owner', 'human', text)
    o = waitroom.add(store, tid, text, 'owner')
    store.audit('task', tid, 'phone_tell_agent', 'owner', detail={'chars': len(text)})
    when = ('it has them now' if o.get('delivered') else 'they go in when it stops at its prompt')
    return f"Told the agent on {task_ref(tid)}: “{text[:160]}” - {when}."


def land(store, p: dict) -> str:
    """The landing question, asked back here: what the branch is and changed, and the answers as picks (take). Lands nothing itself."""
    from . import landing
    tid = _tid(p)
    s = landing.state(store, tid)
    if not s: return f'{task_ref(tid)} has no branch Taskuary saw it start from - nothing to land.'
    if not s['ask']: return f"{task_ref(tid)}: {s['line']}"
    prop = s.get('proposal') or {}
    _ON.choices = [(f"{a['label']} {task_ref(tid)}", {'t': LAND_ACT, 'tid': tid, 'how': a['how']}) for a in s['answers']]
    return (f"{task_ref(tid)}: {s['line']}" + (f" The agent proposes {landing.HOW[prop['how']]}" + (f" - {prop['why']}" if prop.get('why') else '') + '.' if prop.get('how') else '')
            + ' The answers are under your line; ask the owner which - it lands only on their pick.')


def take() -> list:
    "The landing picks this turn raised, for the message's choices (remote_assistant.respond) - spent once taken."
    got, _ON.choices = list(getattr(_ON, 'choices', None) or []), []
    return got


def read(store, kind: str, p: dict) -> str:
    try:
        if kind == 'coding_agents': return agents_text(store)
        if kind == 'tell_agent': return tell(store, p)
        if kind == 'land': return land(store, p)
    except LookupError as e: return str(e)
    return f'{kind} is not a tool here'


def typed(question: str, offered: list, acts: dict) -> dict | None:
    """A landing answer TYPED instead of tapped ("merge commit") while the question is up: the same pick, when it names exactly one."""
    said = ' '.join(str(question or '').lower().split()).strip(' .!')
    hits = [acts[w] for w in offered if (acts.get(w) or {}).get('t') == LAND_ACT and said in (w.lower(), w.lower().rsplit(' tq-', 1)[0])]
    return hits[0] if len(hits) == 1 else None


def picked(store, act: dict, actor: str = 'owner') -> str:
    "The owner's pick of a landing answer, on the phone: carried out, and said."
    from . import landing
    if not live(): return 'Developer mode is off - nothing landed.'
    try: out = landing.land(store, int(act['tid']), str(act.get('how') or ''), actor)
    except (landing.Refused, ValueError, RuntimeError) as e: return f'Nothing landed - {e}'
    return out['says']
