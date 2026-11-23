"""LOOKING OUT FOR YOU (the owner, 2026-11-02: "update the Advisor not to just improve Taskuary but to improve their JOB ... what could they
tell their boss - 'I see pain X and here is a solution'. It has to be truly novel ... not generic 'communicate more'. Someone had an idea
for a consumer assistant that checks anything you bought recently, sees if the price dropped and requests a refund. I want something like
that for your job ... a real proactive thinker looking out for you, trying to get you more credit for your work, solving pain points for
others, or seeing real issues developing").

Once every EVERY_DAYS - a day (the owner, 2026-11-03: "once a week is too inoften ... once a day, but if you said something yesterday
don't say it again") - the Advisor's clock calls `tick` every 15 minutes (server.advisor_pass -> assistant.clock, on the reports' clock);
it is cheap until due. Since 2026-11-23 the afternoon Advisor look runs a second pass when new mail or data arrived (why_not); a skip says
why. The Assistant's advisor.ideas starts one now (`start`). ONE RUN, at most CALLS model calls (the design review, 2026-11-23):

  1. READ      the model reads ONE context (window): JOB.md, SOUL.md, his memory, everything the Advisor raised before and what he did with
               it, leads task agents handed it (note_lead), a light pass (mail in and his sent mail since the last pass, what is owed either
               way, open tasks) and a DEEP look at two areas - a source or a workstream - chosen in turn by plain code (pick) with the angle
               not taken there longest (lens_of)
  2. LOOK      it may ask for READS - search the mail in and out, read a message, a task, a report's or system's data, his memory -
               for a few turns (STEPS), read-only, before it answers at most MAX_IDEAS in the FAMILIES
  3. VERIFY    plain code checks every claim against what the run actually read (verify): each quote word for word in the id it cites,
               each count run again, each number in what it cites. A claim that fails drops the idea - no second model
  4. LAND      an idea's identity is its subjects and its family (same): one raised before on the same subjects is updated in place when
               the evidence is new, else held as said; a new angle is another family. Each run leaves its line (runs, run_line), and three
               runs with nothing raised say so once on the rail

No word list decides anything: the quality bar is the prompt. Code checks only what is checkable - quotes, counts, numbers, ids, that
nothing rests on a personal workstream, and that a family the owner said No more ideas like this to is not asked for.

What passes lands as the Advisor's ordinary idea row (Key idea:lookout-<slug>, Kind = its family): Do it (Send to agent) hands it to a
task agent briefed with the idea and the words it rests on, which does the job as the job needs; Make a task, Remind me, Not ours, No more ideas like this - the verbs every idea has. The owner's verdicts
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
# STEPS: the run's turns - reads, then its ideas; CALLS: those, and a re-ask or two of an answer that was not JSON
DAYS, MAX_IDEAS, MAX_RAISE, MAX_OPEN, STEPS, CALLS, MORNING_H = 30, 5, 3, 6, 4, 6, 7
GROUPS, OWN_GROUPS, PEOPLE, WEEKS = 40, 20, 12, 6
TASKS_SHOWN, GIST, WINDOW_CHARS = 25, 200, 40000
PROPOSE_TOKENS = 2600
LAST_KEY, TRIED_KEY, HELD_KEY, HELD_CAP = 'lookout_last_run', 'lookout_tried_at', 'lookout_held', 20
# ROTATION (the owner, 2026-11-23: "it can't take in all the data from every system ... it should rotate through them"): each pass reads
# DEEP areas whole - the one looked at longest ago, and the one with the most new since its last look (NOTABLE or more) - and only a light
# pass over the rest. AREAS_KEY: when each was last looked at; STAMP_KEY: the newest message a pass read; SKIP_KEY: the last skip and why
DEEP, NOTABLE, AREA_GROUPS, AREA_LATEST, LIGHT_LINES, LIGHT_MAX_DAYS = 2, 10, 25, 8, 60, 4
AREAS_KEY, STAMP_KEY, SKIP_KEY = 'lookout_areas', 'lookout_stamp', 'lookout_skip'
# LEADS: what task agents handed it (note_lead); RUNS: each run's line; QUIET: the one "nothing for three looks" line, said once
LEADS_KEY, LEADS_CAP, RUNS_KEY, RUNS_CAP, QUIET_KEY, QUIET_RUNS = 'lookout_leads', 30, 'lookout_runs', 14, 'lookout_quiet_said', 3
CLOCK = True               # the suite turns this off (tests/conftest.py): a bare store's Advisor run is not about this pass
_BUSY = threading.Lock()   # one pass at a time: the clock's and one the owner asked for never both pay for the same day
_ID = re.compile(r'^(msg|task)(\d+)$')


def _now(): return datetime.now()
def _ts(d): return d.strftime('%Y-%m-%d %H:%M:%S')
def _ago(**k): return _ts(_now() - timedelta(**k))
def _one(s, n): return ' '.join(str(s or '').split())[:n]
def _subj(s): return re.sub(r'\d+', '#', re.sub(r'^\s*((re|fw|fwd|aw)\s*:\s*|\[[^\]]{1,20}\]\s*)+', '', str(s or ''), flags=re.I)).strip().lower()[:80]


READS = {'search_mail': 'search_mail {q, sent, days}: messages in and out whose subject, sender or words hold every word of q - sent true for '
                        "the owner's own sent mail only, false for mail to him only, null for both; days back (default 30). Says how many match",
         'read_message': 'read_message {id}: one message in full, by its id (msg12)',
         'read_task': 'read_task {id}: one task - its title, status, summary and latest comments (task7)',
         'read_source': "read_source {name}: a report's, dashboard's or connected system's latest data in full - name as the window gives it after 'source:'",
         'memory': "memory {q}: the lines of the owner's memory and JOB.md that hold any word of q"}
READ_CHARS, READS_PER_STEP, HITS = 4000, 6, 15

SYSTEM = (
    "You are the owner's chief of staff: a sharp, proactive thinker looking out for them at work. You read their job, who they are, what "
    "they asked you to remember, what you raised before and how they answered, a light pass over what came and went since your last look "
    "(mail in, their own sent mail, what is owed either way, open tasks and how long each has sat), and a THOROUGH look at one or two parts "
    f"of their work - a system, a mailbox, a feed, a workstream, the last {DAYS} days counted and grouped with ids - taken in turn, so every "
    "part gets a deep read over a week. You propose what would make a real difference to the owner's day, standing or organisation - up "
    "to three, each about a different part of the job where the evidence allows - from these families:\n"
    + '\n'.join(f"- {k}: {v}" for k, v in FAMILIES.items()) +
    "\nTHE BAR. An idea rests on specific evidence - counts, dates, the same thing again and again - and joins things the owner could not "
    "see from any single message. Generic advice is worthless here: 'communicate more', 'document the process', 'hold a meeting', 'improve "
    "monitoring', 'automate it' - unless the evidence makes it specific and new (what exactly, from which counts, saving what). A failure "
    "notice is not an idea; the pattern across failures and the fix that ends them can be. Never restate one message unless it is something "
    "the owner let slip, never raise what the owner's own sent words show him already doing, never repeat or rephrase an idea under BEFORE - "
    "coming back to the same subjects from another angle (cost, process, risk, a person) is a new idea in another family when new evidence "
    "supports it. Before naming a person, look for signs they have left - a departure notice, a removed account, mail that stops after "
    "bounces - and say nothing about someone who has gone. Think like the assistant that notices a price dropped and asks for the refund: "
    "what is owed, wasted, at risk or uncredited, in numbers.\n"
    "ABOUT A PERSON: only the observed pattern (counts, dates, what changed), never a diagnosis, motive, blame or a guess about health, "
    "family or private life; the next step is private and kind - a check-in, an offer of help - and nothing that would embarrass them.\n"
    "LOOK BEFORE YOU PROPOSE. You may read further first, up to six reads a turn, a few turns in all - only reading, nothing moves:\n"
    + '\n'.join(f"- {v}" for v in READS.values()) +
    "\nEVIDENCE IS CHECKED WORD FOR WORD. Each idea quotes what it rests on: quotes (at least one) are {ref, quote} - an id you were shown or "
    "read (msg12, task7, memory) and words copied exactly from what you saw of it. Every number in the title, evidence, why or pitch must "
    "be in what you quote from, or be a count you claim in counts ({search, sent, days, n} - a search_mail you made, and its count), or the "
    "days since a cited message. An idea whose quote or number does not hold is dropped.\n"
    "Each idea: family, title (one line to the owner, under 100 characters), evidence (what was seen, with the counts and dates, in plain "
    "words - no ids), quotes, counts ([] when none), why (one sentence: why it matters, at what scale), next_step (concrete enough for an "
    "agent to start: a draft, a query, a fix to build), pitch (one sentence the owner could say to their boss: what they noticed and what "
    "they propose). Spread them: one idea per theme, different families where the evidence allows. Fewer is better; none is a good answer "
    "when nothing clears the bar - never make one up.\n"
    'Answer JSON only: {"reads": [{"tool": "search_mail", "q": "...", "sent": null, "days": null, "id": null, "name": null}], "ideas": []} '
    'to read more, or {"reads": [], "ideas": [{"family": "...", "title": "...", "evidence": "...", "quotes": [{"ref": "msg1", "quote": "..."}], '
    '"counts": [], "why": "...", "next_step": "...", "pitch": "..."}]} when done.')
_N = lambda t: {'type': [t, 'null']}
_OBJ = lambda need, props: {'type': 'object', 'additionalProperties': False, 'required': need, 'properties': props}
WANT = {'name': 'lookout', 'schema': _OBJ(['reads', 'ideas'], {
    'reads': {'type': 'array', 'items': _OBJ(['tool', 'q', 'sent', 'days', 'id', 'name'], {
        'tool': {'type': 'string', 'enum': list(READS)}, 'q': _N('string'), 'sent': _N('boolean'), 'days': _N('integer'), 'id': _N('string'), 'name': _N('string')})},
    'ideas': {'type': 'array', 'items': _OBJ(['family', 'title', 'evidence', 'quotes', 'counts', 'why', 'next_step', 'pitch'], {
        'family': {'type': 'string', 'enum': list(FAMILIES)}, **{k: {'type': 'string'} for k in ('title', 'evidence', 'why', 'next_step', 'pitch')},
        'quotes': {'type': 'array', 'items': _OBJ(['ref', 'quote'], {'ref': {'type': 'string'}, 'quote': {'type': 'string'}})},
        'counts': {'type': 'array', 'items': _OBJ(['search', 'sent', 'days', 'n'], {'search': {'type': 'string'}, 'sent': _N('boolean'),
                                                                                 'days': _N('integer'), 'n': {'type': 'integer'}})}})}})}


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


def before(store) -> list:
    """What it raised before and what the owner did with each - and what the code held back and why - as evidence for the next run. An
    idea he left without a verdict says so, nothing more: walking past is not an answer (ideagrade, 2026-11-23)."""
    from . import ideagrade
    from .assistant import VERDICT_WORD
    v, now = _verdicts(store, every=True), _ts(_now())
    word = {'taken': 'took it up', 'handled': 'handled it', 'wrong': 'turned it down', 'walked': 'no answer', 'pending': 'not answered yet'}
    out = []
    # ...EVERY line the Advisor raised, not only this pass's own: a chase or a promise its twice-a-day look raised is not a "reminder" to raise again
    for i in store._rows("SELECT * FROM idea WHERE Key NOT LIKE 'report:%' ORDER BY IdeaId DESC LIMIT 60"):
        said = VERDICT_WORD.get((v.get(i['Key']) or {}).get('verdict')) or word.get(ideagrade.grade(store._rows, i, now), 'not answered yet')
        out.append(f"- [{i.get('Kind')}] {_one(i.get('Text'), 140)} - the owner: {said}")
    out += [f"- [{h.get('family')}] {_one(h.get('title'), 140)} - held back: {_one(h.get('why'), 120)}" for h in held(store)]
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
    (ll, _), (ol, _), (tl, _) = light(store, rows), owed(store), tasks(store)
    xs = areas(store, rows)
    deep = pick(store, xs)
    blocks = [area_block(store, a, xs[a]) for a in deep]
    soul = re.sub(r'<!--.*?-->|_\([^)]*\)_', '', str(store.doc('soul') or ''), flags=re.S).strip()        # comments and the template's placeholders
    memory = re.sub(r'<!--.*?-->', '', str(store.doc('learned') or ''), flags=re.S).strip()
    job, fams = job_doc(store, 6000), families(store)
    others = sorted(set(xs) - set(deep))
    parts = [f"TODAY: {_now():%A %Y-%m-%d %H:%M}",
             f"FAMILIES YOU MAY RAISE NOW: {', '.join(fams)}" + (f" (the owner turned down or does not use: {', '.join(f for f in FAMILIES if f not in fams)})"
                                                                 if len(fams) < len(FAMILIES) else ''),
             f"THE OWNER'S JOB (JOB.md):\n{job}" if job else '', f"WHO THE OWNER IS (SOUL.md):\n{soul[:4000]}" if soul else '',
             f"WHAT THE OWNER ASKED YOU TO REMEMBER (his memory):\n{memory[:3000]}" if memory else '',
             (said := "BEFORE - what you raised and how the owner answered (raise more like what they took up, nothing like what they turned down):\n"
                      + ('\n'.join(before(store)) or '- nothing yet')), (lead := _leads_block(store)),
             f"SINCE YOUR LAST LOOK - mail in and the owner's own sent mail ({len(ll)}):\n" + ('\n'.join(ll) or '- nothing'),
             "WHAT IS OWED, EITHER WAY (the hub's own facts):\n" + ('\n'.join(ol) or '- nothing'),
             "TASKS:\n" + '\n'.join(tl),
             f"THE DEEP LOOK THIS TIME ({len(deep)} of {len(xs)} parts of the work; the rest get theirs on later passes"
             + (f": {', '.join(others[:30])}" if others else '') + "):\n" + ('\n\n'.join(t for t, _ in blocks) or '- nothing in the window'),
             "THE PEOPLE THE OWNER WRITES TO MOST:\n" + ('\n'.join(people(store, wide)) or '- none')]
    text = '\n\n'.join(p for p in parts if p)[:WINDOW_CHARS]
    # ...and what the run may cite is what it was SHOWN of each id - never an id named only in what it said before or in a lead
    return text, seen_of(text.replace(said, '').replace(lead, '\n') if lead else text.replace(said, '')), deep


# ── THE RUN: ONE AGENT, READ-ONLY TOOLS ────────────────────────────────────────────────────────────────────────────────────────────────
# ONE ENGINE (the design review, 2026-11-23): a proposal, then a second model judging it, read only what the window showed - the check held
# ideas on counts it could not see, and nothing could look a step further. The run now investigates for itself with tools that only read
# (READS), and what it claims is checked in plain code against what it actually read (verify) - a failing claim is dropped, no second model.

_DATE = re.compile(r'\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?|\b\d{1,2}:\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|'
                   r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}(?:st|nd|rd|th)?\b|'
                   r'\b\d{1,2}(?:st|nd|rd|th)? (?:of )?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b', re.I)
_NUM = re.compile(r'(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.,])\d+(?:\.\d+)?')
_REF = re.compile(r'\b((?:msg|task)\d+)\b')


def _norm(s) -> str: return ' '.join(re.sub(r'[‘’]', "'", re.sub(r'[“”]', '"', str(s or ''))).lower().split())
def numbers(s) -> set:
    "The numbers a text states, dates and times left out (a date is its structure, not a count), each as plain digits."
    return {n.replace(',', '').rstrip('0').rstrip('.') if '.' in n else n.replace(',', '') for n in _NUM.findall(_DATE.sub(' ', str(s or '')))}


def seen_of(text: str) -> dict:
    "{ref: the lines that showed it} - what a run was shown about each id, parsed from the markers the app itself wrote (msg12, task7)."
    out = defaultdict(str)
    for l in text.splitlines():
        for r in dict.fromkeys(_REF.findall(l)): out[r] += l + '\n'
    return dict(out)


def _all(store, days: int = DAYS) -> list:
    "The window's messages with their whole words, nothing personal and none of the Advisor's own."
    from . import workstreams as W
    ps = W.personal(store)
    rows = store._rows("SELECT MessageId, Channel, SourceName, Subject, FromName, FromEmail, RecipientsJson, Direction, SentAt, Workstream, BodyText "
                       "FROM message WHERE SentAt>=? AND IFNULL(Channel,'') <> 'assistant' ORDER BY SentAt", (_ago(days=days),))
    return [m for m in rows if not (m.get('Workstream') and m['Workstream'] in ps)]


def count(store, q: str, sent=None, days: int = DAYS) -> list:
    "The messages a search_mail finds - what a claimed count is recomputed from."
    ws = _norm(q).split()
    def hit(m): return all(w in _norm(' '.join(str(m.get(k) or '') for k in ('Subject', 'FromName', 'FromEmail', 'BodyText'))) for w in ws)
    def side(m): return sent is None or ((m.get('Direction') or 'in') == 'out') == bool(sent)
    return [m for m in _all(store, max(1, min(int(days or DAYS), 365))) if ws and side(m) and hit(m)]


def _days(d) -> int:
    try: return max(1, min(int(d or DAYS), 365))
    except (TypeError, ValueError): return DAYS


def read(store, r: dict, seen: dict, counts: dict) -> str:
    """One read-only tool call: its answer in words, and what it showed added to `seen` (per id) and `counts` (per search). Nothing moves."""
    from .workstreams import is_personal
    t = str(r.get('tool') or '')
    if t == 'search_mail':
        q, sent, days = _one(r.get('q'), 120), r.get('sent'), _days(r.get('days'))
        if not q: return 'search_mail: say what to search for'
        ms = count(store, q, sent, days)
        counts[(_norm(q), sent if sent is None else bool(sent), days)] = len(ms)
        head = f'search_mail "{q}" ({"his sent mail" if sent else "mail to him" if sent is False else "in and out"}, {days} days): {len(ms)} match'
        lines = [_line(m) for m in ms[-HITS:]]
        for l in lines: seen_add(seen, l)
        return '\n'.join([head + (f', the newest {HITS} shown' if len(ms) > HITS else '')] + lines)
    if t in ('read_message', 'read_task'):
        ref = str(r.get('id') or '').strip().lower()
        if not (hit := _ID.match(ref)) or (hit.group(1) == 'msg') != (t == 'read_message'): return f'{t}: no such id "{_one(ref, 30)}"'
        if is_personal(store, src=ref): return f'{t} {ref}: personal - not read'
        if t == 'read_message':
            m = store.get_message(int(hit.group(2)))
            if not m or m.get('Channel') == 'assistant': return f'read_message {ref}: no such message'
            text = (f"{ref} {str(m.get('SentAt'))[:16]} " + ('the owner wrote' if (m.get('Direction') or 'in') == 'out' else f"from {m.get('FromName') or m.get('FromEmail') or '?'}")
                    + f" [{m.get('SourceName') or m.get('Channel') or 'message'}]\nSubject: {m.get('Subject') or ''}\n{str(m.get('BodyText') or '')[:READ_CHARS]}")
        else:
            k = store.get_task(int(hit.group(2)))
            if not k: return f'read_task {ref}: no such task'
            cs = [f"- {c.get('Actor')}: {_one(c.get('Body') or c.get('Text'), 300)}" for c in store.list_comments(k['TaskId'])[-5:]]
            text = f"{ref} {k.get('Status')}: {k.get('Title')}\n{str(k.get('Summary') or '')[:2000]}" + ('\nLatest comments:\n' + '\n'.join(cs) if cs else '')
        seen[ref] = seen.get(ref, '') + text + '\n'
        return text
    if t == 'read_source':
        name = _one(r.get('name'), 80).removeprefix('source:')
        ms = [m for m in _all(store) if name and name in (m.get('SourceName'), m.get('Channel'))][-3:]
        if not ms: return f'read_source "{name}": nothing from it in {DAYS} days'
        out = []
        for m in ms:
            text = f"msg{m['MessageId']} {str(m['SentAt'])[:16]} {m.get('Subject') or ''}\n{str(m.get('BodyText') or '')[:READ_CHARS // 2]}"
            seen[f"msg{m['MessageId']}"] = seen.get(f"msg{m['MessageId']}", '') + text + '\n'; out.append(text)
        return f'read_source "{name}", its latest {len(ms)}:\n' + '\n\n'.join(out)
    if t == 'memory':
        from .triage import job_doc
        ws = set(_norm(r.get('q')).split())
        ls = [l.strip() for l in (str(store.doc('learned') or '') + '\n' + str(job_doc(store, 20000) or '')).splitlines()
              if l.strip() and ws & set(_norm(l).split())][:20]
        text = '\n'.join(ls) or 'nothing'
        if ls: seen['memory'] = seen.get('memory', '') + text + '\n'
        return f'memory "{_one(r.get("q"), 60)}" (cite it as memory):\n{text}'
    return f'no tool "{_one(t, 30)}" - the tools are {", ".join(READS)}'


def seen_add(seen: dict, line: str):
    for r in dict.fromkeys(_REF.findall(line)): seen[r] = seen.get(r, '') + line + '\n'


def _age(store, ref: str) -> set:
    "How many days (and weeks) ago a cited message was sent or a task was opened - the ages a claim may state."
    k, n = _ID.match(ref).groups() if _ID.match(ref) else ('', 0)
    row = (store.get_message(int(n)) or {}).get('SentAt') if k == 'msg' else (store.get_task(int(n)) or {}).get('CreatedAt') if k == 'task' else None
    try: d = (_now() - datetime.fromisoformat(str(row)[:19])).days
    except ValueError: return set()
    return {str(x) for x in (d - 1, d, d + 1, d // 7, (d + 6) // 7) if x >= 0}


def verify(store, d: dict, seen: dict, counts: dict, fams: list) -> tuple:
    """(the idea as the code checked it, None) or (None, why it was dropped). Every quote must stand word for word in what the run read of
    the id it cites; every count it claims is run again and must match; every number it states must be in what it cites, a count that
    held, or a cited item's age. Checked in code - no second model - and anything that fails drops the idea."""
    from .workstreams import is_personal
    if not isinstance(d, dict) or d.get('family') not in fams: return None, 'not a family it may raise now'
    x = {k: _one(d.get(k), 600) for k in ('title', 'evidence', 'why', 'next_step', 'pitch')}
    if not all(x.values()): return None, 'a part of it was left empty'
    qs = [{'ref': str(q.get('ref') or '').strip().lower(), 'quote': _one(q.get('quote'), 300)} for q in d.get('quotes') or [] if isinstance(q, dict)]
    if not qs: return None, 'it quotes nothing it read'
    for q in qs:
        if q['ref'] not in seen: return None, f"it cites {q['ref'] or 'nothing'}, which the run never read"
        if len(q['quote']) < 8 or _norm(q['quote']) not in _norm(seen[q['ref']]): return None, f"the words \"{_one(q['quote'], 60)}\" are not in {q['ref']} as read"
    refs = list(dict.fromkeys(q['ref'] for q in qs))[:6]
    if any(is_personal(store, src=r) for r in refs): return None, 'it rests on something personal'
    held = set()
    for c in d.get('counts') or []:
        if not isinstance(c, dict): continue
        k = (_norm(c.get('search')), c.get('sent') if c.get('sent') is None else bool(c.get('sent')), _days(c.get('days')))
        n = len(count(store, c.get('search') or '', k[1], k[2]))
        if k not in counts: return None, f"it counts \"{_one(c.get('search'), 40)}\", a search the run never made"
        if str(c.get('n')) != str(n): return None, f"it says {c.get('n')} for \"{_one(c.get('search'), 40)}\"; the mail holds {n}"
        held.add(str(n))
    backed = held | {str(len(refs))} | {n for r in refs for n in numbers(seen[r]) | _age(store, r)}
    if (loose := sorted(numbers(' '.join((x['title'], x['evidence'], x['why'], x['pitch']))) - backed)):
        return None, f"the number {loose[0]} is not in what it cites"
    return x | {'family': d['family'], 'title': x['title'][:140], 'refs': refs, 'quotes': [q for q in qs if q['ref'] in refs]}, None


# ── IDENTITY: THE SAME SUBJECTS IN THE SAME FAMILY ARE ONE IDEA ─────────────────────────────────────────────────────────────────────────
def subjects(store, refs) -> list:
    "What an idea is about, as a set: each message's thread subject (or its conversation), each task, the memory."
    out = set()
    for r in refs:
        k, n = _ID.match(r).groups() if _ID.match(r) else (r, '')
        if k == 'msg':
            m = store.get_message(int(n)) or {}
            out.add('s:' + (_subj(m.get('Subject')) or str(m.get('ConversationId') or r)))
        else: out.add(r)
    return sorted(out)


def same(store, family: str, subs: list) -> dict | None:
    """The idea raised before on these subjects in this family - half or more of the subjects shared - or None. A new angle on the same
    subjects is another family, and a new idea."""
    b = set(subs)
    for i in store._rows('SELECT * FROM idea WHERE Key LIKE ? AND Kind=? ORDER BY IdeaId DESC', (KEY + '%', family)):
        try: a = json.loads(i.get('ActionJson') or '{}') or {}
        except ValueError: a = {}
        was = set(a.get('subjects') or subjects(store, [e.get('ref') for e in a.get('evidence') or [] if e.get('ref')]))
        if was and b and len(was & b) * 2 >= len(was | b): return i | {'act': a}
    return None


def ref_line(store, ref: str) -> str:
    """What one cited id is, for the card: a message's day, sender and subject, a task's title."""
    if ref == 'memory': return "the owner's memory"
    k, n = _ID.match(ref).groups()
    if k == 'msg':
        m = store.get_message(int(n)) or {}
        who = 'the owner' if (m.get('Direction') or 'in') == 'out' else (m.get('FromName') or m.get('FromEmail') or 'someone')
        return f"{str(m.get('SentAt') or '')[:10]} {who}: {_one(m.get('Subject'), 90)}"
    t = store.get_task(int(n)) or {}
    return f"task {t.get('Status') or ''}: {_one(t.get('Title'), 90)}"


@aiusage.named('advisor.lookout')
def investigate(store, llm, user: str, seen: dict) -> dict | None:
    """The run: the model reads the window, asks for reads (STEPS turns at most), and answers its ideas. None when it never answered;
    else {'ideas': as checked, 'dropped': [(idea, why)], 'reads': what it read}."""
    from .llm import ask_json
    counts, reads, said, fams = {}, [], user, families(store)
    for step in range(STEPS):
        last = step == STEPS - 1
        got = ask_json(llm, SYSTEM, said + ('\n\nThis is your last turn: answer your ideas now, no reads.' if last else ''),
                       want=WANT, max_tokens=PROPOSE_TOKENS)
        if not isinstance(got.data, dict):
            logger.info(f'lookout: no answer - {got.error}')
            return None if step == 0 else {'ideas': [], 'dropped': [], 'reads': reads}
        asks = [r for r in got.data.get('reads') or [] if isinstance(r, dict)][:READS_PER_STEP]
        if asks and not last:
            out = []
            for r in asks:
                reads.append(f"{r.get('tool')} {_one(r.get('q') or r.get('id') or r.get('name'), 60)}".strip())
                out.append(read(store, r, seen, counts))
            said += f'\n\nWHAT YOU READ (turn {step + 1}):\n' + '\n\n'.join(out)
            continue
        ok, dropped = [], []
        for d in (got.data.get('ideas') or [])[:MAX_IDEAS * 2]:
            x, why = verify(store, d, seen, counts, fams)
            if x: ok.append(x)
            elif isinstance(d, dict) and d.get('title'): dropped.append(({'family': d.get('family'), 'title': _one(d.get('title'), 140)}, why))
        return {'ideas': ok[:MAX_IDEAS], 'dropped': dropped, 'reads': reads}
    return {'ideas': [], 'dropped': [], 'reads': reads}


# ── WHERE IT LANDS ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def key_of(x: dict) -> str:
    from .workstreams import slugify
    return KEY + slugify(x['title'])


def _evidence(store, x) -> list:
    q = {}
    for c in x.get('quotes') or []: q.setdefault(c['ref'], c['quote'])
    return [{'ref': r, 'label': ref_line(store, r), **({'quote': q[r]} if r in q else {})} for r in x['refs']]


def land(store, x: dict) -> tuple:
    """(what happened, the row): 'raised' a new idea row, 'updated' the one already on these subjects in this family when new evidence came
    (in place, never said twice), or 'repeat' with the earlier row when nothing is new or it was already put down."""
    subs, was = subjects(store, x['refs']), None
    if (old := same(store, x['family'], subs)) or (was := store._one('SELECT * FROM idea WHERE Key=?', (key_of(x),))):
        old = old or was | {'act': json.loads(was.get('ActionJson') or '{}') or {}}
        a, new = old['act'], [r for r in x['refs'] if r not in {e.get('ref') for e in old['act'].get('evidence') or []}]
        if old.get('Status') not in ('open', 'snoozed') or not new: return 'repeat', old
        ev = (a.get('evidence') or []) + [e for e in _evidence(store, x) if e['ref'] in new]
        act = a | {'title': x['title'], 'suggest': f"{x['next_step']}\nPitch: \"{x['pitch']}\"", 'why': f"{x['evidence']} {x['why']}",
                   'next_step': x['next_step'], 'pitch': x['pitch'], 'evidence': ev, 'subjects': sorted(set(a.get('subjects') or []) | set(subs))}
        store._exec('UPDATE idea SET Text=?, ActionJson=?, LastSaid=? WHERE IdeaId=?', (x['title'], json.dumps(act), _ts(_now()), old['IdeaId']))
        store.audit('idea', old['IdeaId'], 'lookout_updated', 'advisor', 'agent', {'family': x['family'], 'new': new})
        return 'updated', store.get_idea(old['IdeaId'])
    # ...the pitch on a line of its own, apart from the next step (the owner, 2026-11-02)
    act = {'type': 'lookout', 'family': x['family'], 'title': x['title'], 'whose': 'yours - nobody asked for it',
           'suggest': f"{x['next_step']}\nPitch: \"{x['pitch']}\"", 'why': f"{x['evidence']} {x['why']}", 'next_step': x['next_step'],
           'pitch': x['pitch'], 'evidence': _evidence(store, x), 'subjects': subs}
    r = store.upsert_idea({'key': key_of(x), 'kind': x['family'], 'text': x['title'], 'sig': key_of(x), 'action': act}, _ts(_now()))
    store.audit('idea', r['IdeaId'], 'lookout_raised', 'advisor', 'agent', {'family': x['family'], 'refs': x['refs']})
    return 'raised', r


def brief(a: dict) -> str:
    """What Do it (Send to agent) adds to the agent's brief for one of these: the next step, the pitch, and what it rests on - each id with
    the words the Advisor read there - to read first. How the agent's turn ends is its own call."""
    return ((f"\n\nThe next step it suggested: {a['next_step']}" if a.get('next_step') else '')
            + (f"\nThe one line for the owner's boss: {a['pitch']}" if a.get('pitch') else '')
            + ('\n\nWhat it rests on (read these first): ' + '; '.join(f"{e['ref']} - {e.get('label') or ''}" + (f" (\"{e['quote']}\")" if e.get('quote') else '')
                                                                  for e in a['evidence']) if a.get('evidence') else ''))


def _hold(store, held_: list):
    if not held_: return
    rows = [{'family': x.get('family'), 'title': x.get('title'), 'why': w, 'at': _ts(_now())} for x, w in held_]
    store.set_setting(HELD_KEY, json.dumps((rows + held(store))[:HELD_CAP]), 'advisor')


def _skipped(store, why: str, loud: bool):
    "A pass that did not run says why - at INFO from a scheduled look, and once per new reason from the clock's quarter-hour tick."
    try: was = (json.loads(store.get_setting(SKIP_KEY) or '{}') or {}).get('why')
    except ValueError: was = None
    if loud or was != why:
        (logger.info if loud else logger.debug)(f'lookout: skipped - {why}')
        store.set_setting(SKIP_KEY, json.dumps({'at': _ts(_now()), 'why': why}), 'advisor')


# ── LEADS: WHAT A TASK'S AGENT NOTICED, HANDED TO THE ADVISOR ───────────────────────────────────────────────────────────────────────────
def leads(store, fresh: bool = True) -> list:
    try: ls = json.loads(store.get_setting(LEADS_KEY) or '[]') or []
    except ValueError: ls = []
    return [l for l in ls if not (fresh and l.get('used'))]


def note_lead(store, tid: int, text: str, refs=()) -> dict:
    """A task's agent hands the Advisor something it noticed beyond its own task (agenttools note_lead). Kept for the next run to look
    into - a pointer, never evidence: the run reads what it points at before it may cite it."""
    text = _one(text, 400)
    if len(text) < 12: raise ValueError('say what you noticed in a sentence - what, where, and why it may matter')
    refs = [r for r in (str(x).strip().lower() for x in refs or []) if _ID.match(r)][:6]
    ls = leads(store, fresh=False)
    if any(_norm(l.get('text')) == _norm(text) for l in ls): return {'kept': True, 'already': True}
    store.set_setting(LEADS_KEY, json.dumps(([{'at': _ts(_now()), 'tid': tid, 'text': text, 'refs': refs}] + ls)[:LEADS_CAP]), 'advisor')
    return {'kept': True}


def _leads_block(store) -> str:
    ls = leads(store)
    return ("LEADS FROM THE OWNER'S TASK AGENTS - things they noticed beyond their own task; pointers only: read what one points at before "
            "you cite it:\n" + '\n'.join(f"- from task {l['tid']} ({l['at'][:10]}): {l['text']}" + (f" (points at {', '.join(r.replace('msg', 'message ').replace('task', 'task ') for r in l['refs'])})" if l.get('refs') else '')
                                         for l in ls[:10])) if ls else ''


def _used_leads(store):
    ls = leads(store, fresh=False)
    if any(not l.get('used') for l in ls): store.set_setting(LEADS_KEY, json.dumps([l | {'used': True} for l in ls]), 'advisor')


# ── THE RUN LINE: WHAT IT LOOKED AT, WHAT IT HELD AND WHY ───────────────────────────────────────────────────────────────────────────────
def runs(store) -> list:
    try: return json.loads(store.get_setting(RUNS_KEY) or '[]') or []
    except ValueError: return []


def run_line(r: dict) -> str:
    "One run in words - what the owner opens to see what the Advisor looked at and why it held what it held."
    said = (f"raised {len(r['raised'])}" if r.get('raised') else 'raised nothing') + (f", updated {len(r['updated'])}" if r.get('updated') else '')
    return (f"{r['at'][:16]}: looked closely at {', '.join(f'{a} ({l})' for a, l in r.get('deep') or []) or 'nothing new'}"
            + (f"; read {len(r['reads'])} more ({'; '.join(r['reads'][:6])})" if r.get('reads') else '') + f" - {said}"
            + (f"; held {'; '.join(f'{h[0]!r}: {h[1]}' for h in r['held'][:5])}" if r.get('held') else ''))


def _record_run(store, r: dict):
    rs = ([r] + runs(store))[:RUNS_CAP]
    store.set_setting(RUNS_KEY, json.dumps(rs), 'advisor')
    if r.get('raised') or r.get('updated'): store.set_setting(QUIET_KEY, '', 'advisor'); return
    # ...and THREE LOOKS WITH NOTHING, SAID ONCE (the design review, 2026-11-23): the owner reads silence as nothing looking - one line
    # says the Advisor looked and found nothing worth his time, with the looks behind it, and is not said again until something is raised
    if len(rs) >= QUIET_RUNS and not any(x.get('raised') or x.get('updated') for x in rs[:QUIET_RUNS]) and not store.get_setting(QUIET_KEY):
        looked_ = sorted({a for x in rs[:QUIET_RUNS] for a, _ in x.get('deep') or []})
        text = f"My last {QUIET_RUNS} looks for ideas about your job found nothing worth your time - I looked closely at {', '.join(looked_) or 'what arrived'}"
        i = store.upsert_idea({'key': f'advisor:lookout-quiet:{r["at"][:10]}', 'kind': 'lookout_quiet', 'text': text[:240], 'sig': 'quiet',
                               'action': {'type': 'note', 'section': 'ideas', 'whose': 'nobody yet',
                                          'why': '\n'.join(run_line(x) for x in rs[:QUIET_RUNS])}}, _ts(_now()))
        store.set_setting(QUIET_KEY, str(i['IdeaId']), 'advisor')


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
    """One pass when due (or `force`): {ran, raised: [idea ids], updated, held: [titles], calls}. At most CALLS model calls. Never raises.
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
            if n[0] >= CALLS: raise RuntimeError(f'the lookout pass is at most {CALLS} calls')
            n[0] += 1
            return llm(system, user, **kw)
        counted.takes_want = getattr(llm, 'takes_want', None)       # ask_json hands the schema to a brain that carries one
        store.set_setting(TRIED_KEY, _ts(_now()), 'advisor')
        mark, (user, seen, deep) = stamp(store), window(store)
        lenses = [(a, lens_of(store, a)) for a in deep]
        try: got = investigate(store, counted, user, seen)
        except RuntimeError as e: logger.info(f'lookout: {e}'); got = {'ideas': [], 'dropped': [], 'reads': []}
        out |= {'ran': True, 'deep': deep}
        if got is None: return out | {'calls': n[0]}
        store.set_setting(LAST_KEY, _ts(_now()), 'advisor'); store.set_setting(STAMP_KEY, str(mark), 'advisor')
        record_looks(store, deep); _used_leads(store)
        # ...and a family under the 80% bar raises one a day (ideagrade.spent_today)
        from . import ideagrade
        quiet, once_, held_ = ideagrade.quiet_kinds(store), set(), list(got['dropped'])
        room, raised, updated = max(0, min(MAX_RAISE, MAX_OPEN - len(waiting(store)))), [], []
        for x in got['ideas']:
            if x['family'] in quiet and x['family'] in once_: held_.append((x, 'its kind raises one a day while under the bar')); continue
            if len(raised) >= room: held_.append((x, 'enough raised for now')); continue
            what, r = land(store, x)
            if what == 'repeat': held_.append((x, f"said before as \"{_one(r.get('Text'), 80)}\" - nothing new since")); continue
            (raised if what == 'raised' else updated).append(r['IdeaId']); once_.add(x['family'])
        _hold(store, held_)
        if raised:
            from .learning import _woke
            _woke(store)
        _record_run(store, {'at': _ts(_now()), 'deep': lenses, 'reads': got['reads'], 'proposed': len(got['ideas']) + len(got['dropped']),
                            'raised': [store.get_idea(i)['Text'] for i in raised], 'updated': [store.get_idea(i)['Text'] for i in updated],
                            'held': [(x.get('title'), w) for x, w in held_]})
        logger.info(f"lookout: read {', '.join(deep) or 'no area'} deep, {len(got['reads'])} reads - {len(raised)} raised, {len(updated)} updated, {len(held_)} held")
        return out | {'raised': raised, 'updated': updated, 'held': [x.get('title') for x, _ in held_], 'calls': n[0]}
    except Exception as e:
        logger.opt(exception=True).warning(f'lookout: the pass failed - {e}'); return out
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
    held_ = f", {h} held back - its evidence did not hold or it was said before" if h else ''
    if not k: return f"The pass for ideas for your job raised nothing{held_} - nothing cleared the bar today."
    return f"The pass for ideas for your job raised {k} idea{'s' if k > 1 else ''}{held_} - under Advisor."
