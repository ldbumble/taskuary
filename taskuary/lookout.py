"""LOOKING OUT FOR YOU (the owner, 2026-11-02: "update the Advisor not to just improve Taskuary but to improve their JOB ... what could they
tell their boss - 'I see pain X and here is a solution'. It has to be truly novel ... not generic 'communicate more'. Someone had an idea
for a consumer assistant that checks anything you bought recently, sees if the price dropped and requests a refund. I want something like
that for your job ... a real proactive thinker looking out for you, trying to get you more credit for your work, solving pain points for
others, or seeing real issues developing").

Once every EVERY_DAYS - a day (the owner, 2026-11-03: "once a week is too inoften ... once a day, but if you said something yesterday
don't say it again": BEFORE carries every recent idea, and the check holds a repeat) - the Advisor's clock calls `tick` every 15 minutes
(server.advisor_pass -> assistant.clock, on the reports' clock); it is cheap until due - two model calls. The Assistant's advisor.ideas
starts one now (`start`). CALLS caps it at three, as ask_json re-asks once for an answer that was not JSON:

  1. PROPOSE   the model reads ONE context (window): JOB.md, SOUL.md, his memory, everything the Advisor raised before and what he did with
               it, a light pass (mail in and his sent mail since the last pass, what is owed either way, open tasks) and a DEEP look at two
               areas - a source or a workstream - chosen in turn by plain code (pick) with the angle not taken there longest (lens_of). It
               proposes at most MAX_IDEAS in the FAMILIES, each with its evidence, the ids it rests on, the next step and the pitch. Since
               2026-11-23 the afternoon Advisor look runs a second pass when new mail or data arrived (why_not); a skip says why
  2. CHECK     a second, short call reads each idea beside the messages its ids name and keeps only what is specific, supported,
               non-obvious, worth a boss's time, and - about a person - factual, private and kind. What it holds is fed back next time

No word list decides anything: the quality bar is the two prompts. Code only checks what is checkable - the ids an idea cites were in the
window it was shown, nothing rests on a personal workstream, and a family the owner said No more ideas like this to is not asked for.

What passes lands as the Advisor's ordinary idea row (Key idea:lookout-<slug>, Kind = its family): Send to agent drafts the pitch or
builds the fix, Make a task, Remind me, Not ours, No more ideas like this - the verbs every idea has. The owner's verdicts
(assistant.verdicts) and how each earlier idea graded (ideagrade) are the next pass's evidence, and each family is held to the same 80%
bar as the Advisor's own kinds (ideagrade.quiet_kinds)."""
import json, re, threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from loguru import logger
from . import aiusage

FAMILIES = {
    'money': "money or time left on the table - the work version of asking for a refund when a price dropped: a duplicate charge or record, "
             "two tools or subscriptions doing one job, a credit owed, an unused licence, a better plan, an SLA breach, a late fee, a renewal with a cost on it",
    'pitch': "a recurring pain for the owner or others - the same question asked again, the same report fixed by hand, the same failure coming "
             "back - with its ROOT fix: what to change so it stops, not that it failed again",
    'reminder': "something the owner let slip: an ask in his mail he never answered, a promise in his own sent mail not yet kept, a date a "
                "message named that is near or past - how long it has been, and what is owed",
    'connection': "two things the owner has not put together: one thread's answer settles another, the same issue from two systems or people, "
                  "a meeting or deadline that bears on an open ask",
    'new_idea': "a better way to do part of the job the evidence points to - a report, check or automation that removes a weekly chore, a "
                "process worth proposing",
    'credit': "work the owner did that leadership likely does not see, with the numbers from the window, and a concrete way to show it",
    'early_warning': "a developing problem - a process drifting, a recurring job that will fail again on a date you can name, a deadline at "
                     "risk, a report that stopped arriving, a colleague whose pattern changed sharply",
    'leverage': "who depends on the owner, who to loop in, an introduction that would unblock something"}
KEY = 'idea:lookout-'
EVERY_DAYS, RETRY_H = 1, 6           # a day between passes (setting lookout_every_days); a pass that got no answer tries again in 6 hours
# FOUR, NOT TWO (the owner, 2026-11-05: "where is the advisor ideas about your pain points ... don't see any in my advisor today"): two
# proposals a day, both held by the check, left the Advisor empty for days. MORNING_H: the day's pass runs from the morning, not 24 hours
# after the last one - it had drifted to 5:53 PM
# 2-3 A DAY (the owner, 2026-11-23: "need 2-3 really good ideas about different parts of your job almost every day"): up to MAX_RAISE land a
# pass, the morning's and the afternoon look's (`look`, when something moved since) - never more than MAX_OPEN waiting on the rail
DAYS, MAX_IDEAS, MAX_RAISE, MAX_OPEN, CALLS, MORNING_H = 30, 5, 3, 6, 3, 7     # CALLS: the two, and one re-ask of an answer that was not JSON
GROUPS, OWN_GROUPS, PEOPLE, WEEKS = 40, 20, 12, 6
TASKS_SHOWN, GIST, WINDOW_CHARS = 25, 200, 40000
PROPOSE_TOKENS, CHECK_TOKENS = 2600, 900
LAST_KEY, TRIED_KEY, HELD_KEY, HELD_CAP = 'lookout_last_run', 'lookout_tried_at', 'lookout_held', 20
# ROTATION (the owner, 2026-11-23: "it can't take in all the data from every system ... it should rotate through them"): each pass reads
# DEEP areas whole - the one looked at longest ago, and the one with the most new since its last look (NOTABLE or more) - and only a light
# pass over the rest. AREAS_KEY: when each was last looked at; STAMP_KEY: the newest message a pass read; SKIP_KEY: the last skip and why
DEEP, NOTABLE, AREA_GROUPS, AREA_LATEST, LIGHT_LINES, LIGHT_MAX_DAYS = 2, 10, 25, 8, 60, 4
AREAS_KEY, STAMP_KEY, SKIP_KEY = 'lookout_areas', 'lookout_stamp', 'lookout_skip'
CLOCK = True               # the suite turns this off (tests/conftest.py): a bare store's Advisor run is not about this pass
_BUSY = threading.Lock()   # one pass at a time: the clock's and one the owner asked for never both pay for the same day
_ID = re.compile(r'^(msg|task)(\d+)$')


def _now(): return datetime.now()
def _ts(d): return d.strftime('%Y-%m-%d %H:%M:%S')
def _ago(**k): return _ts(_now() - timedelta(**k))
def _one(s, n): return ' '.join(str(s or '').split())[:n]
def _subj(s): return re.sub(r'\d+', '#', re.sub(r'^\s*((re|fw|fwd|aw)\s*:\s*|\[[^\]]{1,20}\]\s*)+', '', str(s or ''), flags=re.I)).strip().lower()[:80]


SYSTEM = (
    "You are the owner's chief of staff: a sharp, proactive thinker looking out for them at work. You read their job, who they are, what "
    "they asked you to remember, what you raised before and how they answered, a light pass over what came and went since your last look "
    "(mail in, their own sent mail, what is owed either way, open tasks and how long each has sat), and a THOROUGH look at one or two parts "
    f"of their work - a system, a mailbox, a feed, a workstream, the last {DAYS} days counted and grouped with ids - taken in turn, so every "
    "part gets a deep read over a week. You propose what would make a real difference to the owner's day, standing or organisation - up "
    "to three, each about a different part of the job where the evidence allows - from these families:\n"
    + '\n'.join(f"- {k}: {v}" for k, v in FAMILIES.items()) +
    "\nTHE BAR. An idea rests on specific evidence in the window - counts, dates, the same thing again and again - and joins things the "
    "owner could not see from any single message. Generic advice is worthless here: 'communicate more', 'document the process', 'hold a "
    "meeting', 'improve monitoring', 'automate it' - unless the evidence makes it specific and new (what exactly, from which counts, saving "
    "what). A failure notice is not an idea; the pattern across failures and the fix that ends them can be. Never restate one message "
    "unless it is something the owner let slip, never raise what the owner is visibly already doing, never repeat or rephrase an idea "
    "under BEFORE - coming back to an area from another angle (cost, process, risk, a person) is new when new evidence supports it. Before naming a person, look for signs they have left - a departure notice, a removed account, mail that stops after bounces - and say nothing about someone who has gone. "
    "Think like the assistant that notices a price dropped and asks for the refund: what is owed, wasted, at risk or uncredited, in numbers.\n"
    "ABOUT A PERSON: only the observed pattern (counts, dates, what changed), never a diagnosis, motive, blame or a guess about health, "
    "family or private life; the next step is private and kind - a check-in, an offer of help - and nothing that would embarrass them.\n"
    "Each idea: family (one of the families), title (one line to the owner, under 100 characters), evidence (what was seen, with the "
    "counts and dates, in plain words - no ids), refs (the ids from the window it rests on, like msg12 or task7 - at least one), why "
    "(one sentence: why it matters, at what scale), next_step (concrete enough for an agent to start: a draft, a query, a fix to build), "
    "pitch (one sentence the owner could say to their boss: what they noticed and what they propose). "
    "Spread them: one idea per theme, and different families where the evidence allows - never two takes on the same threads. "
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
    "cited lines really show what it claims, nothing is invented or stretched; (3) NON-OBVIOUS - the owner would not get there from what "
    "is in front of them: it joins things, or it brings back something they let slip (its date and the silence since are its evidence), "
    "and their own sent words do not show them already on it; (4) WORTH A BOSS'S TIME - money, time, risk or credit at a scale "
    "that matters - for a CREDIT idea, the work and its size must be in the cited lines; that leadership has not seen it is the idea's premise, not something the lines must prove; (5) about a person: factual, private and kind - no diagnosis, motive, blame or private life; (6) NEW - not the same point as one under ALREADY RAISED, however reworded, unless the cited lines show something has changed since; the same area from a different angle (cost, process, risk, a person) is a new point; (7) STILL TRUE TODAY - a person it names still works with the owner (the window has no departure notice, account removal or 'no longer with' reply, and they still write or are written to), and a process it names still runs. Reject anything generic "
    "('communicate more', 'hold a meeting', 'document it', 'monitor more') however well it is worded. "
    "An idea ALREADY RAISED to the owner passes only when it brings evidence that is new since - then name the earlier one it replaces. "
    'Answer JSON only: {"keep": [<numbers of the ideas to keep>], "why": {"<number>": "<one line: why it was rejected>"}, '
    '"replaces": {"<number of a kept idea>": "<the earlier idea, word for word as listed>"}}')
CHECK_WANT = {'name': 'lookout_check', 'schema': {'type': 'object', 'additionalProperties': False, 'required': ['keep', 'why'], 'properties': {
    'keep': {'type': 'array', 'items': {'type': 'integer'}}, 'why': {'type': 'object', 'additionalProperties': {'type': 'string'}},
    'replaces': {'type': 'object', 'additionalProperties': {'type': 'string'}}}}}


# ── WHEN ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _every(store) -> float:
    try: return max(1.0, float(store.get_setting('lookout_every_days') or EVERY_DAYS))
    except (TypeError, ValueError): return float(EVERY_DAYS)
def open_ideas(store) -> list: return store._rows("SELECT * FROM idea WHERE Key LIKE ? AND Status IN ('open','snoozed')", (KEY + '%',))


def waiting(store) -> list:
    """The open ones the rail still draws - unread, or put away till a later day. WAITING IS ON THE RAIL: an idea the owner opened and
    read leaves the rail but stays open, and four such ideas read on one morning stopped every pass after it - six days without an
    idea for the owner's job (2026-11-12). A rail that cannot be read counts every open one, as before."""
    ids = open_ideas(store)
    if not ids: return []
    try:
        from . import funnel
        on = {x.get('idea') for x in funnel.pile(store, quiet=True)['items']}
    except Exception as e: logger.debug(f'lookout: the rail was not read - {e}'); return ids
    return [i for i in ids if i['IdeaId'] in on or i.get('Status') == 'snoozed']


def stamp(store) -> int:
    "The newest message a pass would read - what moved since the last pass, as one number."
    return int((store._one("SELECT MAX(MessageId) m FROM message WHERE IFNULL(Channel,'') <> 'assistant'") or {}).get('m') or 0)


def why_not(store, look: bool = False) -> str:
    """'' when a pass is due, else why not, in words. Once a calendar day from MORNING_H (or a whole day gone by) whatever moved; `look` (the
    scheduled Advisor look's own call) also when new mail or data arrived since the last pass and RETRY_H have passed - a day passed or new
    data is never skipped for facts that look the same. Never more than MAX_OPEN waiting - the rail read last."""
    last, tried, now = store.get_setting(LAST_KEY) or '', store.get_setting(TRIED_KEY) or '', _ts(_now())
    if tried and tried > _ago(hours=RETRY_H): return f'the last pass started at {tried[11:16]} - the next one {RETRY_H} hours after it'
    every = _every(store)
    new_day = not last or (last[:10] < now[:10] and (_now().hour >= MORNING_H or last <= _ago(days=1)) if every <= 1 else last <= _ago(days=every))
    if not new_day:
        moved = stamp(store) > int(store.get_setting(STAMP_KEY) or 0)
        if not look: return f'ran at {last[:16]} - the day\'s pass is done; the next Advisor look runs it again when something new arrived'
        if not moved: return f'ran at {last[:16]} and nothing new has arrived since'
    n = len(waiting(store))
    return f'{n} ideas already wait on the rail (at most {MAX_OPEN})' if n >= MAX_OPEN else ''


def due(store, look: bool = False) -> bool: return not why_not(store, look)


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
    live = store._rows("SELECT TaskId, Title, Kind, Status, CreatedAt, UpdatedAt FROM task WHERE Status NOT IN ('done','dropped') ORDER BY TaskId DESC LIMIT ?", (TASKS_SHOWN,))
    kinds, ids = Counter(t.get('Kind') or 'task' for t in done), {f"task{t['TaskId']}" for t in done[:TASKS_SHOWN] + live}
    return ([f"Closed in the window: {len(done)} ({', '.join(f'{k} {n}' for k, n in kinds.most_common())})"]
            + [f"- task{t['TaskId']} closed {str(t['At'])[:10]}: {_one(t['Title'], 100)}" for t in done[:TASKS_SHOWN]]
            + ([f"Open now: {len(live)}"] + [f"- task{t['TaskId']} {t.get('Status')} since {str(t['CreatedAt'])[:10]}, last moved {str(t.get('UpdatedAt') or t['CreatedAt'])[:10]}: "
                                       f"{_one(t['Title'], 100)}" for t in live] if live else [])), ids


def _verdicts(store, every: bool = False) -> dict:
    from .assistant import verdicts
    return {r.get('key'): r for r in verdicts(store) if every or str(r.get('key') or '').startswith(KEY)}


def turned_down(store) -> set:
    """The families the owner said No more ideas like this to - never asked for again."""
    v = _verdicts(store)
    return {i.get('Kind') for i in store._rows('SELECT Key, Kind FROM idea WHERE Key LIKE ?', (KEY + '%',))
            if (v.get(i['Key']) or {}).get('verdict') == 'dismiss_kind'}


def families(store) -> list:
    """The families it may raise now: not one the owner turned down, nor one under the 80% bar (ideagrade) that raised its one today."""
    from . import ideagrade
    try: quiet = ideagrade.spent_today(store, ideagrade.quiet_kinds(store))
    except Exception: quiet = set()
    return [f for f in FAMILIES if f not in turned_down(store) and f not in quiet]


def before(store, held_too: bool = True) -> list:
    """What it raised before and what the owner did with each - and what its own check held back - as evidence for the next pass.
    `held_too` False for the check: what it held never reached the owner, so it is no "already raised" - read as one, a theme held once
    was held as a repeat every morning after (the owner's live Advisor, 2026-11-14..18: 14 of 15 ideas held, 10 of them so)."""
    from . import ideagrade
    from .assistant import VERDICT_WORD
    v, now = _verdicts(store, every=True), _ts(_now())
    word = {'taken': 'took it up', 'handled': 'handled it', 'wrong': 'turned it down', 'walked': 'walked past it', 'pending': 'not answered yet'}
    out = []
    # ...EVERY line the Advisor raised, not only this pass's own: a chase or a promise its twice-a-day look raised is not a "reminder" to raise again
    for i in store._rows("SELECT * FROM idea WHERE Key NOT LIKE 'report:%' ORDER BY IdeaId DESC LIMIT 60"):
        said = VERDICT_WORD.get((v.get(i['Key']) or {}).get('verdict')) or word.get(ideagrade.grade(store._rows, i, now), 'not answered yet')
        out.append(f"- [{i.get('Kind')}] {_one(i.get('Text'), 140)} - the owner: {said}")
    out += [f"- [{h.get('family')}] {_one(h.get('title'), 140)} - held by the check: {_one(h.get('why'), 120)}" for h in held(store)] if held_too else []
    return out


def held(store) -> list:
    try: return json.loads(store.get_setting(HELD_KEY) or '[]') or []
    except ValueError: return []


def _line(m) -> str:
    "One message for the light pass: its id, day, who wrote whom, the subject and its first words."
    who = (f"the owner wrote to {', '.join(_to(m)[:3]) or 'someone'}" if (m.get('Direction') or 'in') == 'out'
           else f"from {(m.get('FromName') or m.get('FromEmail') or '?')[:40]}")
    return f"- msg{m['MessageId']} {str(m['SentAt'])[:16]} {who} [{m.get('Channel') or 'message'}]: \"{_one(m.get('Subject'), 90)}\" - {_one(m.get('BodyText'), GIST)}"


def _to(m) -> list:
    try: r = json.loads(m.get('RecipientsJson') or '{}') or {}
    except ValueError: r = {}
    return [str(a) for a in (r.get('to') or []) if a] if isinstance(r, dict) else []


def light(store, rows: list) -> tuple:
    """(lines, ids) of what came and went since the last pass - at least the last day, at most LIGHT_MAX_DAYS when the app was shut - the
    owner's own sent mail first (his promises and asks are in it), then the newest arrivals, LIGHT_LINES in all."""
    last = store.get_setting(LAST_KEY) or ''
    since = max(min(last or _ago(days=1), _ago(days=1)), _ago(days=LIGHT_MAX_DAYS))
    xs = [m for m in rows if str(m['SentAt']) >= since]
    out = [m for m in xs if (m.get('Direction') or 'in') == 'out'][-LIGHT_LINES // 2:]
    mine = {m['MessageId'] for m in out}
    xs = sorted(out + [m for m in xs if m['MessageId'] not in mine][-(LIGHT_LINES - len(out)):], key=lambda m: str(m['SentAt']))
    return [_line(m) for m in xs], {f"msg{m['MessageId']}" for m in xs}


def owed(store) -> tuple:
    """(lines, ids) of what is owed either way - the Advisor's own facts (assistant.candidates): an ask of the owner's nobody answered, a
    promise in his sent mail not kept, a meeting that needs something, work gone quiet. Read, never judged here."""
    from . import assistant
    try: cs = assistant.candidates(store, assistant.cfg(store))
    except Exception as e: logger.info(f'lookout: what is owed was not read - {e}'); return [], set()
    ids = {f"msg{c['action']['mid']}" for c in cs if (c.get('action') or {}).get('mid')}
    return [f"- [{c.get('kind')}] {_one(c.get('facts') or c.get('text'), 300)}" + (f" (msg{c['action']['mid']})" if (c.get('action') or {}).get('mid') else '')
            for c in cs], ids


def areas(store, rows: list) -> dict:
    """{area id: its rows} - the parts of the owner's work the window holds: each source the mail and data came by (a mailbox, a chat, a
    connected system, a recurring report or feed) and each workstream of JOB.md its messages were placed under."""
    out = defaultdict(list)
    for m in rows:
        if (src := m.get('SourceName') or m.get('Channel')): out[f'source:{src}'].append(m)
        if m.get('Workstream'): out[f"workstream:{m['Workstream']}"].append(m)
    return dict(out)


# THE ANGLES (the owner, 2026-11-23: "it should not say the same thing twice but there is usually another angle to explore"): a deep look
# at an area is told which of these it took there before and which it has not taken longest - the question, never what to conclude
LENSES = {'money': 'what is paid here - twice, late, for nothing; what renews and when',
          'time': 'what is done by hand here, how often, how long',
          'failure': 'what breaks here again and again, and what would stop it',
          'people': 'who waits on whom here, who asks the same thing, who went quiet',
          'credit': 'what the owner did here that leadership has not seen, in numbers',
          'comparison': 'this month against last, one vendor or system against another',
          'absence': 'what should be here and is not - a report that stopped, a renewal with no thread'}


def coverage(store) -> dict:
    "{area: {'at': its last deep look, 'lens': {lens: when it was taken there}}} - an older record's bare time read as its look."
    try: c = json.loads(store.get_setting(AREAS_KEY) or '{}') or {}
    except ValueError: c = {}
    return {a: v if isinstance(v, dict) else {'at': str(v), 'lens': {}} for a, v in c.items()}


def looked(store) -> dict: return {a: v.get('at') or '' for a, v in coverage(store).items()}


def lens_of(store, aid: str) -> str:
    "The angle not taken on this area for longest: never taken first, in LENSES' order."
    used = (coverage(store).get(aid) or {}).get('lens') or {}
    return min(LENSES, key=lambda l: (used.get(l, ''), list(LENSES).index(l)))


def record_looks(store, deep: list):
    c, now = coverage(store), _ts(_now())
    for a in deep:
        v = c.setdefault(a, {'at': '', 'lens': {}})
        v['lens'][lens_of(store, a)] = now; v['at'] = now
    store.set_setting(AREAS_KEY, json.dumps(c), 'advisor')


def pick(store, xs: dict) -> list:
    """The DEEP areas this pass reads whole, by plain code: the one looked at longest ago (never first, then by name), then the one with the
    most new since its own last look when that is NOTABLE or more, else the next longest ago. Over a week every area has its turn."""
    seen = looked(store)
    order = sorted(xs, key=lambda a: (seen.get(a, ''), a))
    if not order: return []
    first, rest = order[0], [a for a in order[1:]]
    new = {a: sum(1 for m in xs[a] if str(m['SentAt']) > seen.get(a, '')) for a in rest}
    busy = sorted(rest, key=lambda a: (-new[a], seen.get(a, ''), a))
    second = busy[0] if busy and new[busy[0]] >= NOTABLE else (rest[0] if rest else None)
    return [a for a in (first, second) if a][:DEEP]


def area_block(store, aid: str, ms: list) -> tuple:
    "(the deep look at one area, the ids it shows): its JOB.md section for a workstream, its subjects counted, its latest messages in words."
    from . import workstreams as W
    kind, name = aid.split(':', 1)
    at = looked(store).get(aid, '')
    head = (f"=== {kind} {W.names(store).get(name, name) if kind == 'workstream' else name}: {len(ms)} message(s) in {DAYS} days; "
            + (f"you last looked closely on {at[:10]}, {sum(1 for m in ms if str(m['SentAt']) > at)} new since" if at else 'never looked at closely before') + ' ===')
    sec = W.section(store, name) if kind == 'workstream' else ''
    used, lens = (coverage(store).get(aid) or {}).get('lens') or {}, lens_of(store, aid)
    head += ('\nAngles taken here before: ' + (', '.join(f'{l} ({t[:10]})' for l, t in sorted(used.items(), key=lambda x: x[1])) or 'none')
             + f'. The one not taken longest: {lens} - {LENSES[lens]}.')
    gs, latest = groups(store, ms)[:AREA_GROUPS], ms[-AREA_LATEST:]
    text = '\n'.join([head] + ([f"What JOB.md says about it:\n{_one(sec, 1500)}"] if sec else []) + ['Its subjects, counted:']
                     + [group_line(x) for x in gs] + ['Its latest messages:'] + [_line(m) for m in latest])
    return text, {f'msg{i}' for x in gs for i in x['ids']} | {f"msg{m['MessageId']}" for m in latest}


def window(store, days: int = DAYS) -> tuple:
    """(the prompt's user text, the ids it shows, the areas it read deep). ONE context, facts only: the owner (JOB, SOUL, his memory), what
    was raised before and what he did with it, the light pass (since the last pass, what is owed, people, tasks) and the deep look at the
    areas `pick` chose. Each block bounded; the whole cut at WINDOW_CHARS from the end, the deep look and the people last."""
    from .triage import job_doc
    wide = _rows(store, max(days, WEEKS * 7))                     # the people's weeks reach further back than the window
    rows = [m for m in wide if str(m['SentAt']) >= _ago(days=days)]
    (ll, lids), (ol, oids), (tl, tids) = light(store, rows), owed(store), tasks(store)
    xs = areas(store, rows)
    deep = pick(store, xs)
    blocks = [area_block(store, a, xs[a]) for a in deep]
    shown = lids | oids | tids | {i for _, ids in blocks for i in ids}
    soul = re.sub(r'<!--.*?-->|_\([^)]*\)_', '', str(store.doc('soul') or ''), flags=re.S).strip()        # comments and the template's placeholders
    memory = re.sub(r'<!--.*?-->', '', str(store.doc('learned') or ''), flags=re.S).strip()
    job, fams = job_doc(store, 6000), families(store)
    others = sorted(set(xs) - set(deep))
    parts = [f"TODAY: {_now():%A %Y-%m-%d %H:%M}",
             f"FAMILIES YOU MAY RAISE NOW: {', '.join(fams)}" + (f" (the owner turned down or does not use: {', '.join(f for f in FAMILIES if f not in fams)})"
                                                                 if len(fams) < len(FAMILIES) else ''),
             f"THE OWNER'S JOB (JOB.md):\n{job}" if job else '', f"WHO THE OWNER IS (SOUL.md):\n{soul[:4000]}" if soul else '',
             f"WHAT THE OWNER ASKED YOU TO REMEMBER (his memory):\n{memory[:3000]}" if memory else '',
             "BEFORE - what you raised and how the owner answered (raise more like what they took up, nothing like what they turned down):\n"
             + ('\n'.join(before(store)) or '- nothing yet'),
             f"SINCE YOUR LAST LOOK - mail in and the owner's own sent mail ({len(ll)}):\n" + ('\n'.join(ll) or '- nothing'),
             "WHAT IS OWED, EITHER WAY (the hub's own facts):\n" + ('\n'.join(ol) or '- nothing'),
             "TASKS:\n" + '\n'.join(tl),
             f"THE DEEP LOOK THIS TIME ({len(deep)} of {len(xs)} parts of the work; the rest get theirs on later passes"
             + (f": {', '.join(others[:30])}" if others else '') + "):\n" + ('\n\n'.join(t for t, _ in blocks) or '- nothing in the window'),
             "THE PEOPLE THE OWNER WRITES TO MOST:\n" + ('\n'.join(people(store, wide)) or '- none')]
    text = '\n\n'.join(p for p in parts if p)
    return text[:WINDOW_CHARS], shown, deep


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


def counted(store, days: int = DAYS) -> dict:
    """Each message id of the window -> its subject group's counted line, as the proposing call read it: the check was shown single messages
    only, and held every idea resting on a count ("the cited lines do not support the 39-message pattern") it had no way to see."""
    rows = [m for m in _rows(store, days) if str(m['SentAt']) >= _ago(days=days)]
    return {f'msg{i}': group_line(g) for g in groups(store, rows) for i in g['ids']}


def ref_line(store, ref: str) -> str:
    """What one cited id is, for the check and the card: a message's day, sender and subject, a task's title."""
    k, n = _ID.match(ref).groups()
    if k == 'msg':
        m = store.get_message(int(n)) or {}
        who = 'the owner' if (m.get('Direction') or 'in') == 'out' else (m.get('FromName') or m.get('FromEmail') or 'someone')
        return f"{str(m.get('SentAt') or '')[:10]} {who}: {_one(m.get('Subject'), 90)}"
    t = store.get_task(int(n)) or {}
    return f"task {t.get('Status') or ''}: {_one(t.get('Title'), 90)}"


@aiusage.named('advisor.propose')
def propose(store, llm, user: str, shown: set) -> list | None:
    """The first call. None when it gave no answer at all (the pass is tried again in a day), else the ideas the code could check."""
    from .llm import ask_json
    got = ask_json(llm, SYSTEM, user, want=WANT, max_tokens=PROPOSE_TOKENS)     # no `need`: no ideas is an answer, never a retry
    if not isinstance(got.data, dict): logger.info(f'lookout: no answer - {got.error}'); return None
    fams = families(store)
    return [x for x in (_clean(store, d, shown, fams) for d in (got.data.get('ideas') or [])[:MAX_IDEAS * 2]) if x][:MAX_IDEAS]


@aiusage.named('advisor.check')
def check(store, llm, ideas: list) -> tuple:
    """The second call: (kept, [(idea, why held)]). A check that cannot run holds everything - an unchecked idea is never raised."""
    from .llm import ask_json
    if not ideas: return [], []
    seen = counted(store)
    user = '\n\n'.join(f"IDEA {n} [{x['family']}]: {x['title']}\nevidence: {x['evidence']}\nwhy: {x['why']}\nnext step: {x['next_step']}\n"
                       f"pitch: {x['pitch']}\nwhat it cites:\n" + '\n'.join(f"  {r}: {ref_line(store, r)}" for r in x['refs'])
                       + ''.join(f"\n  counted, as the proposal saw it: {g}" for g in dict.fromkeys(seen[r] for r in x['refs'] if r in seen))
                       for n, x in enumerate(ideas, 1))
    said = before(store, held_too=False)
    if said: user += '\n\nALREADY RAISED (and how the owner answered):\n' + '\n'.join(said)
    try:
        got = ask_json(llm, CHECK, user, want=CHECK_WANT, max_tokens=CHECK_TOKENS)
        if not isinstance(got.data, dict): raise ValueError(got.error or 'no answer')
    except Exception as e:
        logger.info(f'lookout: the check did not run, nothing is raised - {e}')
        return [], [(x, 'the check did not run') for x in ideas]
    keep, why = {int(k) for k in got.data.get('keep') or [] if str(k).lstrip('-').isdigit()}, got.data.get('why') or {}
    swap = got.data.get('replaces') or {}
    return ([x | ({'replaces': str(swap[str(n)])} if swap.get(str(n)) else {}) for n, x in enumerate(ideas, 1) if n in keep],
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
    # ...A NEWER IDEA ON A THEME REPLACES THE OLDER (the owner, 2026-11-18: "when you run the next advisor it replaces it or does not say the
    # same thing twice"): the one it names is put down, and the new one stands in its place, unread
    if (old := x.get('replaces')) and (was := store._one("SELECT IdeaId FROM idea WHERE Key LIKE ? AND Status IN ('open','snoozed') AND Text=?",
                                                         (KEY + '%', ' '.join(str(old).split())))):
        store.set_idea_status(was['IdeaId'], 'done', 'advisor')
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


def _skipped(store, why: str, loud: bool):
    "A pass that did not run says why - at INFO from a scheduled look, and once per new reason from the clock's quarter-hour tick."
    try: was = (json.loads(store.get_setting(SKIP_KEY) or '{}') or {}).get('why')
    except ValueError: was = None
    if loud or was != why:
        (logger.info if loud else logger.debug)(f'lookout: skipped - {why}')
        store.set_setting(SKIP_KEY, json.dumps({'at': _ts(_now()), 'why': why}), 'advisor')


def brain(store):
    """The Advisor's brain, or None: no AI chosen at first run, or none connected - a pass never runs without one."""
    try:
        from .firstrun import unchosen
        if unchosen(store): return None
        from .llm import build_llm
        return build_llm(store, job='advisor')
    except Exception as e:
        logger.info(f'lookout: no brain - {e}'); return None


def tick(store, llm=None, force: bool = False, wait: bool = False) -> dict:
    """One pass when due (or `force`): {ran, raised: [idea ids], held: [titles], calls}. At most CALLS model calls. Never raises.
    `wait`: the scheduled Advisor look's own call (assistant.job_ideas) - a pass already running is waited for, and it runs again later in
    the day when something new arrived (why_not's `look`). A skip says why: in the log, and on SKIP_KEY."""
    out = {'ran': False, 'raised': [], 'held': [], 'calls': 0}
    if not _BUSY.acquire(blocking=wait): return out
    try:
        if not force and (why := why_not(store, look=wait)):
            _skipped(store, why, loud=wait); return out | {'skipped': why}
        if llm is None: llm = brain(store)
        if llm is None: return out
        n = [0]
        def counted(system, user, **kw):
            if n[0] >= CALLS: raise RuntimeError('the lookout pass is at most three calls')
            n[0] += 1
            return llm(system, user, **kw)
        counted.takes_want = getattr(llm, 'takes_want', None)       # ask_json hands the schema to a brain that carries one
        store.set_setting(TRIED_KEY, _ts(_now()), 'advisor')
        mark, (user, shown, deep) = stamp(store), window(store)
        ideas = propose(store, counted, user, shown)
        out |= {'ran': True, 'deep': deep}
        if ideas is None: return out | {'calls': n[0]}
        store.set_setting(LAST_KEY, _ts(_now()), 'advisor'); store.set_setting(STAMP_KEY, str(mark), 'advisor')
        record_looks(store, deep)
        kept, held_ = check(store, counted, ideas)
        # ...and a family under the 80% bar raises one a day (ideagrade.spent_today)
        from . import ideagrade
        quiet, seen = ideagrade.quiet_kinds(store), set()
        def once(f): return f not in quiet or (f not in seen and not seen.add(f))
        kept = [x for x in kept if once(x['family'])]
        _hold(store, held_)
        rows = [r for r in (land(store, x) for x in kept[:max(0, min(MAX_RAISE, MAX_OPEN - len(waiting(store))))]) if r]
        if rows:
            from .learning import _woke
            _woke(store)
        logger.info(f"lookout: read {', '.join(deep) or 'no area'} deep - {len(ideas)} proposed, {len(rows)} raised, {len(held_)} held")
        return out | {'raised': [r['IdeaId'] for r in rows], 'held': [x['title'] for x, _ in held_], 'calls': n[0]}
    except Exception as e:
        logger.warning(f'lookout: the pass failed - {e}'); return out
    finally: _BUSY.release()


# ── NOW, WHEN THE OWNER ASKS ──────────────────────────────────────────────────────────────────────────────────────────────────────────
# "look for ideas for my job now" (the owner, 2026-11-03: the daily pass had never run, and they wanted a way to start one) - the
# Assistant's advisor.ideas. Every guard but the day still holds: two waiting, no AI, one pass at a time.
def start(store, said) -> tuple:
    """(started, the line said at once). Started, the pass runs on a thread of its own and `said(line)` is handed what it raised."""
    from .words import name
    from . import demo
    if demo.enabled(): return False, "Nothing started: the demo world runs no Advisor passes - in your own Taskuary this starts one."
    n = len(waiting(store))
    if n >= MAX_OPEN:
        return False, (f"Nothing started: {n} ideas for your job already wait under Advisor, and it keeps at most {MAX_OPEN} at once. "
                       "Answer one of them and ask again.")
    if _BUSY.locked(): return False, 'Nothing started: a pass for ideas for your job is already running - what it raises lands under Advisor.'
    llm = brain(store)
    if llm is None: return False, f"Nothing started: no AI is connected. Connect one under {name('ai')} and ask again."
    def go():
        before = store.get_setting(LAST_KEY) or ''
        out = tick(store, llm, force=True)
        try: said(outcome(out, (store.get_setting(LAST_KEY) or '') != before))
        except Exception as e: logger.warning(f'lookout: the outcome was not said - {e}')
    threading.Thread(target=go, daemon=True, name='lookout-now').start()
    return True, 'Started a pass for ideas for your job - I will say here what it raised.'


def outcome(out: dict, answered: bool) -> str:
    "What a pass the owner asked for came to, in one line."
    if not out.get('ran'): return 'The pass for ideas for your job did not run - nothing raised.'
    if not answered: return 'The pass for ideas for your job got no answer from the AI - nothing raised. Ask again in a while.'
    k, h = len(out.get('raised') or []), len(out.get('held') or [])
    held_ = f", {h} held back by the second look" if h else ''
    if not k: return f"The pass for ideas for your job raised nothing{held_} - nothing cleared the bar today."
    return f"The pass for ideas for your job raised {k} idea{'s' if k > 1 else ''}{held_} - under Advisor."
