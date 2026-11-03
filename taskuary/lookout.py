"""LOOKING OUT FOR YOU (the owner, 2026-11-02: "update the Advisor not to just improve Taskuary but to improve their JOB ... what could they
tell their boss - 'I see pain X and here is a solution'. It has to be truly novel ... not generic 'communicate more'. Someone had an idea
for a consumer assistant that checks anything you bought recently, sees if the price dropped and requests a refund. I want something like
that for your job ... a real proactive thinker looking out for you, trying to get you more credit for your work, solving pain points for
others, or seeing real issues developing").

Once every EVERY_DAYS (the Advisor's clock calls `tick` each run; it is cheap until due), two model calls - CALLS caps it at three, as
ask_json re-asks once for an answer that was not JSON:

  1. PROPOSE   the model reads JOB.md, SOUL.md, the window - the last DAYS of mail, chat, tasks and reports, COUNTED and grouped (each group
               with ids it can cite), the weekly pattern of the people the owner writes to most - and what it raised before and how the owner
               answered. It proposes at most MAX_IDEAS ideas in five FAMILIES, each with its evidence, the ids it rests on, the next step
               and the one sentence for the boss
  2. CHECK     a second, short call reads each idea beside the messages its ids name and keeps only what is specific, supported,
               non-obvious, worth a boss's time, and - about a person - factual, private and kind. What it holds is fed back next time

No word list decides anything: the quality bar is the two prompts. Code only checks what is checkable - the ids an idea cites were in the
window it was shown, nothing rests on a personal workstream, and a family the owner said No more ideas like this to is not asked for.

What passes lands as the Advisor's ordinary idea row (Key idea:lookout-<slug>, Kind = its family): Send to agent drafts the pitch or
builds the fix, Make a task, Remind me, Not ours, No more ideas like this - the verbs every idea has. The owner's verdicts
(assistant.verdicts) and how each earlier idea graded (ideagrade) are the next pass's evidence, and each family is held to the same 80%
bar as the Advisor's own kinds (ideagrade.quiet_kinds)."""
import json, re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from loguru import logger

FAMILIES = {
    'credit': "work the owner did that leadership likely does not see, with the numbers from the window, and a concrete way to show it",
    'pitch': "a recurring pain for OTHERS - the same question asked again, the same report fixed by hand, the same failure or vendor problem "
             "coming back - with a specific fix the owner could build or propose",
    'money': "money or time left on the table - the work version of asking for a refund when a price dropped: a duplicate charge or record, "
             "a credit owed, an unused licence, an SLA breach, a late fee, a double payment, a retirement or renewal date with a cost on it",
    'early_warning': "a developing problem - a process drifting, a recurring job that will fail again on a date you can name, a deadline at "
                     "risk, a report that stopped arriving, a colleague whose pattern changed sharply",
    'leverage': "who depends on the owner, who to loop in, an introduction that would unblock something"}
KEY = 'idea:lookout-'
EVERY_DAYS, RETRY_H = 7, 24          # a week between passes (setting lookout_every_days); a pass that got no answer tries again a day later
DAYS, MAX_IDEAS, MAX_OPEN, CALLS = 30, 2, 2, 3     # CALLS: the two, and one re-ask of an answer that was not JSON (llm.ask_json)
GROUPS, OWN_GROUPS, PEOPLE, WEEKS = 40, 20, 12, 6
TASKS_SHOWN, GIST, WINDOW_CHARS = 25, 200, 22000
PROPOSE_TOKENS, CHECK_TOKENS = 1800, 700
LAST_KEY, TRIED_KEY, HELD_KEY, HELD_CAP = 'lookout_last_run', 'lookout_tried_at', 'lookout_held', 20
CLOCK = True               # the suite turns this off (tests/conftest.py): a bare store's Advisor run is not about this pass
_ID = re.compile(r'^(msg|task)(\d+)$')


def _now(): return datetime.now()
def _ts(d): return d.strftime('%Y-%m-%d %H:%M:%S')
def _ago(**k): return _ts(_now() - timedelta(**k))
def _one(s, n): return ' '.join(str(s or '').split())[:n]
def _subj(s): return re.sub(r'\d+', '#', re.sub(r'^\s*((re|fw|fwd|aw)\s*:\s*|\[[^\]]{1,20}\]\s*)+', '', str(s or ''), flags=re.I)).strip().lower()[:80]


SYSTEM = (
    "You are the owner's chief of staff: a sharp, proactive thinker looking out for them at work. You read their job, the last "
    f"{DAYS} days of their mail, chats, tasks and reports - counted and grouped, each group with ids - the weekly pattern of the people "
    "they deal with most, and what you raised before and how they answered. You propose ideas that would make a real difference to the "
    "owner's standing or their organisation, from these families:\n"
    + '\n'.join(f"- {k}: {v}" for k, v in FAMILIES.items()) +
    "\nTHE BAR. An idea rests on specific evidence in the window - counts, dates, the same thing again and again - and joins things the "
    "owner could not see from any single message. Generic advice is worthless here: 'communicate more', 'document the process', 'hold a "
    "meeting', 'improve monitoring', 'automate it' - unless the evidence makes it specific and new (what exactly, from which counts, saving "
    "what). Never restate one message, never raise what the owner is visibly already doing, never repeat or rephrase an idea under BEFORE. "
    "Think like the assistant that notices a price dropped and asks for the refund: what is owed, wasted, at risk or uncredited, in numbers.\n"
    "ABOUT A PERSON: only the observed pattern (counts, dates, what changed), never a diagnosis, motive, blame or a guess about health, "
    "family or private life; the next step is private and kind - a check-in, an offer of help - and nothing that would embarrass them.\n"
    "Each idea: family (one of the families), title (one line to the owner, under 100 characters), evidence (what was seen, with the "
    "counts and dates, in plain words - no ids), refs (the ids from the window it rests on, like msg12 or task7 - at least one), why "
    "(one sentence: why it matters, at what scale), next_step (concrete enough for an agent to start: a draft, a query, a fix to build), "
    "pitch (one sentence the owner could say to their boss: what they noticed and what they propose). "
    "Fewer is better; none is a good answer when nothing clears the bar. "
    'Answer JSON only: {"ideas": [{"family": "...", "title": "...", "evidence": "...", "refs": ["msg1"], "why": "...", "next_step": "...", "pitch": "..."}]}')
WANT = {'name': 'lookout', 'schema': {'type': 'object', 'additionalProperties': False, 'required': ['ideas'], 'properties': {'ideas': {
    'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                               'required': ['family', 'title', 'evidence', 'refs', 'why', 'next_step', 'pitch'],
                               'properties': {'family': {'type': 'string', 'enum': list(FAMILIES)}, 'title': {'type': 'string'},
                                              'evidence': {'type': 'string'}, 'refs': {'type': 'array', 'items': {'type': 'string'}},
                                              'why': {'type': 'string'}, 'next_step': {'type': 'string'}, 'pitch': {'type': 'string'}}}}}}}
CHECK = (
    "You review ideas a chief of staff wants to put in front of a busy owner, one by one, beside the messages and tasks each one cites. "
    "Keep an idea only when ALL of these hold: (1) SPECIFIC - it names counts, dates or items, not a general practice; (2) SUPPORTED - the "
    "cited lines really show what it claims, nothing is invented or stretched; (3) NON-OBVIOUS - the owner could not see it from one "
    "message, and their own sent words do not show them already on it; (4) WORTH A BOSS'S TIME - money, time, risk or credit at a scale "
    "that matters; (5) about a person: factual, private and kind - no diagnosis, motive, blame or private life. Reject anything generic "
    "('communicate more', 'hold a meeting', 'document it', 'monitor more') however well it is worded. "
    'Answer JSON only: {"keep": [<numbers of the ideas to keep>], "why": {"<number>": "<one line: why it was rejected>"}}')
CHECK_WANT = {'name': 'lookout_check', 'schema': {'type': 'object', 'additionalProperties': False, 'required': ['keep', 'why'], 'properties': {
    'keep': {'type': 'array', 'items': {'type': 'integer'}}, 'why': {'type': 'object', 'additionalProperties': {'type': 'string'}}}}}


# ── WHEN ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _every(store) -> float:
    try: return max(1.0, float(store.get_setting('lookout_every_days') or EVERY_DAYS))
    except (TypeError, ValueError): return float(EVERY_DAYS)
def open_ideas(store) -> list: return store._rows("SELECT * FROM idea WHERE Key LIKE ? AND Status IN ('open','snoozed')", (KEY + '%',))


def due(store) -> bool:
    """A week (lookout_every_days) since the last pass that got an answer, a day since one that did not, and room on the rail: never more
    than MAX_OPEN of these waiting at once."""
    if len(open_ideas(store)) >= MAX_OPEN: return False
    last, tried = store.get_setting(LAST_KEY) or '', store.get_setting(TRIED_KEY) or ''
    return (not last or last <= _ago(days=_every(store))) and (not tried or tried <= _ago(hours=RETRY_H))


# ── WHAT IT READS ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _rows(store, days):
    from . import workstreams as W
    ps = W.personal(store)
    rows = store._rows("SELECT MessageId, TaskId, ConversationId, Channel, SourceName, Subject, FromName, FromEmail, RecipientsJson, Direction, "
                       "Status, SentAt, Workstream, substr(BodyText, 1, 400) BodyText FROM message WHERE SentAt>=? AND IFNULL(Channel,'') <> 'assistant' "
                       "ORDER BY SentAt", (_ago(days=days),))
    return [m for m in rows if not (m.get('Workstream') and m['Workstream'] in ps)]       # nothing personal is read, so nothing personal is raised


def groups(store, rows) -> list:
    """The window as groups of the same subject - a recurring report, a thread, a notice that keeps coming - each counted: how many, from
    whom, how many the owner wrote, the first and last day, ids to cite and the last words. The largest, then the ones the owner wrote most on."""
    from .wsboot import _own
    g = defaultdict(lambda: {'n': 0, 'own': 0, 'who': Counter(), 'ids': [], 'first': '', 'last': '', 'gist': '', 'subject': ''})
    for m in rows:
        k = _subj(m.get('Subject')) or f"({m.get('Channel') or 'message'} with {(m.get('FromName') or m.get('FromEmail') or '?')[:40]})"
        x = g[k]; x['n'] += 1; x['ids'].append(m['MessageId']); x['subject'] = _one(m.get('Subject'), 90) or k      # the latest wording
        x['first'], x['last'] = x['first'] or str(m['SentAt'])[:10], str(m['SentAt'])[:10]
        if _own(m): x['own'] += 1
        else: x['who'][(m.get('FromName') or m.get('FromEmail') or '?')[:40]] += 1; x['gist'] = _one(m.get('BodyText'), GIST)
    xs = sorted(g.values(), key=lambda x: -x['n'])
    top, mine = xs[:GROUPS], sorted((x for x in xs[GROUPS:] if x['own']), key=lambda x: -x['own'])[:OWN_GROUPS]
    return top + mine


def group_line(x) -> str:
    ids = x['ids'] if len(x['ids']) <= 3 else [x['ids'][0], x['ids'][len(x['ids']) // 2], x['ids'][-1]]
    who = ', '.join(f"{w} x{n}" if n > 1 else w for w, n in x['who'].most_common(4))
    return (f"- \"{x['subject']}\": {x['n']} message(s) {x['first']}..{x['last']}" + (f", the owner wrote {x['own']}" if x['own'] else '')
            + (f"; from {who}" if who else '') + f"; ids {' '.join(f'msg{i}' for i in ids)}" + (f"; last said: {x['gist']}" if x['gist'] else ''))


def people(store, rows) -> list:
    """The people the owner writes to most, with how many messages came from each in each of the last WEEKS weeks (oldest first) - the
    counts a changed pattern shows in. Counted, never read."""
    from .wsboot import _own, _recipients, _mine
    me, sent, names = _mine(store), Counter(), {}
    for m in rows:
        if _own(m): sent.update(a for a in _recipients(m) if a not in me)
        elif m.get('FromEmail'): names[m['FromEmail'].lower()] = m.get('FromName') or m['FromEmail']
    start, out = _now() - timedelta(weeks=WEEKS), []
    for a, n in sent.most_common(PEOPLE):
        wk = [0] * WEEKS
        for m in rows:
            if (m.get('FromEmail') or '').lower() == a and not _own(m):
                i = int((datetime.fromisoformat(str(m['SentAt'])[:19]) - start).days // 7)
                if 0 <= i < WEEKS: wk[i] += 1
        out.append(f"- {names.get(a, a)}: the owner wrote to them {n} time(s); from them each week, oldest first: {' '.join(map(str, wk))}")
    return out


def tasks(store) -> tuple:
    """(lines, the task ids they show): how many closed in the window by kind, the latest closed, and what is open."""
    since = _ago(days=DAYS)
    done = store._rows("SELECT TaskId, Title, Kind, Status, COALESCE(ClosedAt, UpdatedAt, CreatedAt) At FROM task WHERE Status IN ('done','dropped') AND "
                       "COALESCE(ClosedAt, UpdatedAt, CreatedAt)>=? ORDER BY At DESC", (since,))
    live = store._rows("SELECT TaskId, Title, Kind, Status, CreatedAt FROM task WHERE Status NOT IN ('done','dropped') ORDER BY TaskId DESC LIMIT ?", (TASKS_SHOWN,))
    kinds, ids = Counter(t.get('Kind') or 'task' for t in done), {f"task{t['TaskId']}" for t in done[:TASKS_SHOWN] + live}
    return ([f"Closed in the window: {len(done)} ({', '.join(f'{k} {n}' for k, n in kinds.most_common())})"]
            + [f"- task{t['TaskId']} closed {str(t['At'])[:10]}: {_one(t['Title'], 100)}" for t in done[:TASKS_SHOWN]]
            + ([f"Open now: {len(live)}"] + [f"- task{t['TaskId']} open since {str(t['CreatedAt'])[:10]}: {_one(t['Title'], 100)}" for t in live] if live else [])), ids


def _verdicts(store) -> dict:
    from .assistant import verdicts
    return {r.get('key'): r for r in verdicts(store) if str(r.get('key') or '').startswith(KEY)}


def turned_down(store) -> set:
    """The families the owner said No more ideas like this to - never asked for again."""
    v = _verdicts(store)
    return {i.get('Kind') for i in store._rows('SELECT Key, Kind FROM idea WHERE Key LIKE ?', (KEY + '%',))
            if (v.get(i['Key']) or {}).get('verdict') == 'dismiss_kind'}


def families(store) -> list:
    """The families it may raise now: not one the owner turned down, nor one the owner's record holds under the 80% bar (ideagrade)."""
    from . import ideagrade
    try: quiet = ideagrade.quiet_kinds(store)
    except Exception: quiet = set()
    return [f for f in FAMILIES if f not in turned_down(store) and f not in quiet]


def before(store) -> list:
    """What it raised before and what the owner did with each - and what its own check held back - as evidence for the next pass."""
    from . import ideagrade
    from .assistant import VERDICT_WORD
    v, now = _verdicts(store), _ts(_now())
    word = {'taken': 'took it up', 'handled': 'handled it', 'wrong': 'turned it down', 'walked': 'walked past it', 'pending': 'not answered yet'}
    out = []
    for i in store._rows('SELECT * FROM idea WHERE Key LIKE ? ORDER BY IdeaId DESC LIMIT 20', (KEY + '%',)):
        said = VERDICT_WORD.get((v.get(i['Key']) or {}).get('verdict')) or word.get(ideagrade.grade(store._rows, i, now), 'not answered yet')
        out.append(f"- [{i.get('Kind')}] {_one(i.get('Text'), 140)} - the owner: {said}")
    out += [f"- [{h.get('family')}] {_one(h.get('title'), 140)} - held by the check: {_one(h.get('why'), 120)}" for h in held(store)]
    return out


def held(store) -> list:
    try: return json.loads(store.get_setting(HELD_KEY) or '[]') or []
    except ValueError: return []


def window(store, days: int = DAYS) -> tuple:
    """(the prompt's user text, the ids it shows). Each block bounded; the whole cut at WINDOW_CHARS from the end."""
    from .triage import job_doc
    wide = _rows(store, max(days, WEEKS * 7))                     # the people's weeks reach further back than the window
    rows = [m for m in wide if str(m['SentAt']) >= _ago(days=days)]
    gs, (tl, tids) = groups(store, rows), tasks(store)
    shown = {f'msg{i}' for x in gs for i in x['ids']} | tids
    soul = re.sub(r'<!--.*?-->|_\([^)]*\)_', '', str(store.doc('soul') or ''), flags=re.S).strip()        # comments and the template's placeholders
    job, fams = job_doc(store, 6000), families(store)
    parts = [f"TODAY: {_now():%A %Y-%m-%d}",
             f"FAMILIES YOU MAY RAISE NOW: {', '.join(fams)}" + (f" (the owner turned down or does not use: {', '.join(f for f in FAMILIES if f not in fams)})"
                                                                 if len(fams) < len(FAMILIES) else ''),
             f"THE OWNER'S JOB (JOB.md):\n{job}" if job else '', f"WHO THE OWNER IS (SOUL.md):\n{soul[:4000]}" if soul else '',
             "BEFORE - what you raised and how the owner answered (raise more like what they took up, nothing like what they turned down):\n"
             + ('\n'.join(before(store)) or '- nothing yet'),
             f"WHAT CAME AND WENT, LAST {days} DAYS, grouped by subject ({len(rows)} messages):\n" + '\n'.join(group_line(x) for x in gs),
             "THE PEOPLE THE OWNER WRITES TO MOST:\n" + ('\n'.join(people(store, wide)) or '- none'),
             "TASKS:\n" + '\n'.join(tl)]
    text = '\n\n'.join(p for p in parts if p)
    return text[:WINDOW_CHARS], shown


# ── THE TWO CALLS ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _clean(store, d: dict, shown: set, fams: list) -> dict | None:
    """An idea as the code can check it: a family it may raise, every part said, and at least one id it cites that was in the window -
    an id the model made up is dropped, and an idea resting on nothing real is not raised."""
    from .workstreams import is_personal
    if not isinstance(d, dict) or d.get('family') not in fams: return None
    x = {k: _one(d.get(k), 600) for k in ('title', 'evidence', 'why', 'next_step', 'pitch')}
    if not all(x.values()): return None
    refs = [r for r in dict.fromkeys(str(r).strip().lower() for r in d.get('refs') or []) if r in shown][:6]
    if not refs or any(is_personal(store, src=r) for r in refs): return None
    return x | {'family': d['family'], 'title': x['title'][:140], 'refs': refs}


def ref_line(store, ref: str) -> str:
    """What one cited id is, for the check and the card: a message's day, sender and subject, a task's title."""
    k, n = _ID.match(ref).groups()
    if k == 'msg':
        m = store.get_message(int(n)) or {}
        who = 'the owner' if (m.get('Direction') or 'in') == 'out' else (m.get('FromName') or m.get('FromEmail') or 'someone')
        return f"{str(m.get('SentAt') or '')[:10]} {who}: {_one(m.get('Subject'), 90)}"
    t = store.get_task(int(n)) or {}
    return f"task {t.get('Status') or ''}: {_one(t.get('Title'), 90)}"


def propose(store, llm, user: str, shown: set) -> list | None:
    """The first call. None when it gave no answer at all (the pass is tried again in a day), else the ideas the code could check."""
    from .llm import ask_json
    got = ask_json(llm, SYSTEM, user, want=WANT, max_tokens=PROPOSE_TOKENS)     # no `need`: no ideas is an answer, never a retry
    if not isinstance(got.data, dict): logger.info(f'lookout: no answer - {got.error}'); return None
    fams = families(store)
    return [x for x in (_clean(store, d, shown, fams) for d in (got.data.get('ideas') or [])[:MAX_IDEAS * 2]) if x][:MAX_IDEAS]


def check(store, llm, ideas: list) -> tuple:
    """The second call: (kept, [(idea, why held)]). A check that cannot run holds everything - an unchecked idea is never raised."""
    from .llm import ask_json
    if not ideas: return [], []
    user = '\n\n'.join(f"IDEA {n} [{x['family']}]: {x['title']}\nevidence: {x['evidence']}\nwhy: {x['why']}\nnext step: {x['next_step']}\n"
                       f"pitch: {x['pitch']}\nwhat it cites:\n" + '\n'.join(f"  {r}: {ref_line(store, r)}" for r in x['refs'])
                       for n, x in enumerate(ideas, 1))
    try:
        got = ask_json(llm, CHECK, user, want=CHECK_WANT, max_tokens=CHECK_TOKENS)
        if not isinstance(got.data, dict): raise ValueError(got.error or 'no answer')
    except Exception as e:
        logger.info(f'lookout: the check did not run, nothing is raised - {e}')
        return [], [(x, 'the check did not run') for x in ideas]
    keep, why = {int(k) for k in got.data.get('keep') or [] if str(k).lstrip('-').isdigit()}, got.data.get('why') or {}
    return ([x for n, x in enumerate(ideas, 1) if n in keep],
            [(x, _one(why.get(str(n)) or 'it did not clear the bar', 160)) for n, x in enumerate(ideas, 1) if n not in keep])


# ── WHERE IT LANDS ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def key_of(x: dict) -> str:
    from .workstreams import slugify
    return KEY + slugify(x['title'])


def land(store, x: dict) -> dict | None:
    """The Advisor's ordinary idea row: the title, then Whose move, the Suggestion (the next step and the pitch) and Based on (the
    evidence), with the ids it rests on kept on the action for the agent and the card. A key said before is never said again."""
    k = key_of(x)
    if store._one('SELECT 1 x FROM idea WHERE Key=?', (k,)): return None
    ev = [{'ref': r, 'label': ref_line(store, r)} for r in x['refs']]
    # ...the pitch on a line of its own, apart from the next step (the owner, 2026-11-02)
    act = {'type': 'lookout', 'family': x['family'], 'title': x['title'], 'whose': 'yours - nobody asked for it',
           'suggest': f"{x['next_step']}\nPitch: \"{x['pitch']}\"", 'why': f"{x['evidence']} {x['why']}", 'next_step': x['next_step'],
           'pitch': x['pitch'], 'evidence': ev}
    r = store.upsert_idea({'key': k, 'kind': x['family'], 'text': x['title'], 'sig': k, 'action': act}, _ts(_now()))
    store.audit('idea', r['IdeaId'], 'lookout_raised', 'advisor', 'agent', {'family': x['family'], 'refs': x['refs']})
    return r


def brief(a: dict) -> str:
    """What Send to agent adds to the agent's brief for one of these: the next step, the pitch, and the ids it rests on to read first."""
    return ((f"\n\nThe next step it suggested: {a['next_step']}" if a.get('next_step') else '')
            + (f"\nThe one line for the owner's boss: {a['pitch']}" if a.get('pitch') else '')
            + ('\n\nWhat it rests on (read these first): ' + '; '.join(f"{e['ref']} - {e.get('label') or ''}" for e in a['evidence'])
               if a.get('evidence') else ''))


def _hold(store, held_: list):
    if not held_: return
    rows = [{'family': x['family'], 'title': x['title'], 'why': w, 'at': _ts(_now())} for x, w in held_]
    store.set_setting(HELD_KEY, json.dumps((rows + held(store))[:HELD_CAP]), 'advisor')


def tick(store, llm=None, force: bool = False) -> dict:
    """One pass when due (or `force`): {ran, raised: [idea ids], held: [titles], calls}. At most CALLS model calls. Never raises."""
    out = {'ran': False, 'raised': [], 'held': [], 'calls': 0}
    try:
        if not force and not due(store): return out
        if llm is None:
            from .firstrun import unchosen
            if unchosen(store): return out
            from .llm import build_llm
            llm = build_llm(store, job='advisor')
        if llm is None: return out
        n = [0]
        def counted(system, user, **kw):
            if n[0] >= CALLS: raise RuntimeError('the lookout pass is at most three calls')
            n[0] += 1
            return llm(system, user, **kw)
        counted.takes_want = getattr(llm, 'takes_want', None)       # ask_json hands the schema to a brain that carries one
        store.set_setting(TRIED_KEY, _ts(_now()), 'advisor')
        user, shown = window(store)
        ideas = propose(store, counted, user, shown)
        out |= {'ran': True}
        if ideas is None: return out | {'calls': n[0]}
        store.set_setting(LAST_KEY, _ts(_now()), 'advisor')
        kept, held_ = check(store, counted, ideas)
        _hold(store, held_)
        rows = [r for r in (land(store, x) for x in kept[:max(0, MAX_OPEN - len(open_ideas(store)))]) if r]
        if rows:
            from .habits import _woke
            _woke(store)
        logger.info(f'lookout: {len(ideas)} proposed, {len(rows)} raised, {len(held_)} held')
        return out | {'raised': [r['IdeaId'] for r in rows], 'held': [x['title'] for x, _ in held_], 'calls': n[0]}
    except Exception as e:
        logger.warning(f'lookout: the pass failed - {e}'); return out
