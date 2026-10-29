"""The assistant's look-ups past the first ten (concierge.read_op): open work, one message in full, a
sender at a glance, the docs, what the agents are doing, what waits for approval, the calendar,
what happened, what failed, what is kept about the owner and the rules that filter their mail. Each
reads what is already recorded and changes nothing - the assistant stays light because it asks for
what it needs instead of carrying a memory in its prompt
(the owner, 2026-09-24: "it should be able to search ... using lookup tools")."""
import hashlib, json, math, re
from datetime import datetime, timedelta
from pathlib import Path
from .store import task_ref
from . import textsim
from .timewords import plural

NL = chr(10)
ACTIVE = ('open', 'in_progress', 'waiting')
# the help pages the website is built from; present in a checkout, absent from a wheel
SITE_DOCS = Path(__file__).resolve().parent.parent / 'docs' / 'site'
_H2 = re.compile(r'^## ', re.M)

def _cut(s, n):
    # a short field reads as one line; a body keeps its own lines
    s = ' '.join(str(s or '').split()) if n < 600 else str(s or '').strip()
    return s if len(s) <= n else s[:n] + ' […]'

def _day(s): return str(s or '')[:16]

def _limit(p, default, cap):
    try: limit = int(p.get('limit') or default)
    except (TypeError, ValueError, OverflowError): limit = default
    return max(1, min(limit, cap))

def tasks_list(store, p: dict) -> str:
    status, limit = str(p.get('status') or 'open').strip().lower(), _limit(p, 25, 60)
    q = str(p.get('contains') or '').strip() or None
    rows = store.list_tasks(status=None if status in ('open', 'all') else status, q=q)
    if status == 'open': rows = [t for t in rows if t.get('Status') in ACTIVE]
    # ...and a task named by its person and subject, not the literal sentence: "Omar Spendly lockout" missed the task whose mail
    # says "locked me out" (the 2026-10-01 press audit). By MEANING (embeddings, context.alike), best first - a count of shared
    # word stems decided it once (the owner, 2026-10-28: no hard-coded words). No embedder: the literal find above is all.
    if not rows and q:
        from .context import alike
        pool = [t for t in store.list_tasks(status=None if status in ('open', 'all') else status) if status != 'open' or t.get('Status') in ACTIVE]
        near = alike(store, q, pool)
        rows = sorted((t for t in pool if t['TaskId'] in near), key=lambda t: -near[t['TaskId']])
    if not rows: return f'No {"" if status == "all" else status + " "}tasks match that.'
    run = lambda t: f" - agent {t['RunAgent']} {t['RunStatus']}" if t.get('RunStatus') in ('running', 'queued') else ''
    out = [f"{task_ref(t['TaskId'])} [{t.get('Status')}/{t.get('Kind')}] {_cut(t.get('Title'), 120)} - updated {_day(t.get('UpdatedAt') or t.get('CreatedAt'))}{run(t)}"
           for t in rows[:limit]]
    return NL.join(out + ([f'…and {len(rows) - limit} more - narrow it with contains.'] if len(rows) > limit else []))

def message_read(store, p: dict) -> str:
    m = re.search(r'\d+', str(p.get('mid') or p.get('id') or ''))
    r = store.get_message(int(m.group())) if m else None
    if not r: return f"There is no message {p.get('mid') or p.get('id')}."
    head = (f"m{r['MessageId']} {r.get('Channel')} from {r.get('FromName') or ''} <{r.get('FromEmail') or ''}> at {_day(r.get('SentAt'))}"
            f"{' on ' + task_ref(r['TaskId']) if r.get('TaskId') else ''} [{r.get('Status')}]{NL}subject: {r.get('Subject') or ''}")
    own = str(r.get('OwnText') or '').strip()
    body = (f'their own words:{NL}{_cut(own, 2500)}{NL}' if own else '') + f"the message as received:{NL}{_cut(r.get('BodyText'), 4000 if not own else 1500)}"
    return head + NL + body

def sender_read(store, p: dict) -> str:
    who = str(p.get('who') or p.get('sender') or '').strip()
    hits = store.senders_like(who) if who else []
    if not hits:
        # ...but someone the owner only ever WROTE TO is somebody too (people.resolve): "email Gail" needs Gail's address
        from . import people
        found, sent = people.resolve(store, who) if who else {}, None
        addrs = [found['address']] if found.get('address') else found.get('candidates') or []
        if addrs:
            sent = people.written_to(store)
            return NL.join(f"{a} - you wrote to them {sent.get(a, (0, ''))[0]} time(s), last {_day(sent.get(a, (0, ''))[1])}; "
                           'they have not written in' for a in addrs)
        return f'Nobody by "{who}" has written in, and you have not written to anyone by that name.'
    s = next((h for h in hits if h['Email'] == who.lower()), hits[0])
    em, since = s['Email'], (datetime.now() - timedelta(days=3650)).isoformat(' ', 'seconds')
    out = [f"{s['Name'] or em} <{em}> - {plural(s['N'], 'message')}, first {_day(s['First'])}, last {_day(s['Last'])}"]
    recent = store.messages_from(em, since, 8)
    if recent: out += ['recent:'] + [f"  m{r['MessageId']} {_day(r.get('SentAt'))} {task_ref(r['TaskId']) if r.get('TaskId') else '-'} "
                                     f"[{r.get('Status')}] {_cut(r.get('Subject'), 110)}" for r in recent]
    tasks = store.open_tasks_from(em)
    out.append('open tasks: ' + ('; '.join(f"{task_ref(t['TaskId'])} {_cut(t['Title'], 80)} ({t['Status']})" for t in tasks) if tasks else 'none'))
    replies = store.own_replies_to(em, since, 3)
    if replies: out.append('you last wrote back ' + _day(replies[0].get('SentAt')))
    from . import memorylines                  # what LEARNED.md holds about them (2026-10-27: the one memory)
    from .learned_cut import names
    notes = [m['Note'] for m in memorylines.notes(store) if str(m.get('ScopeKey') or '').lower() == em or em in names(m['Note'])]
    if notes: out += ['what you told me about them:'] + [f'  - {_cut(n, 300)}' for n in notes[:8]]
    from . import orgchart
    if (rel := orgchart.relation_of(store, em, s.get('Name') or '')): out.append(f'to you: {rel}')
    others = [h for h in hits if h['Email'] != em]
    if others: out.append('also matching: ' + ', '.join(f"{h['Name'] or h['Email']} <{h['Email']}> ({h['N']})" for h in others))
    return NL.join(out)

_COMMENT = re.compile(r'<!--.*?-->', re.S)
CHUNK = 1200

def _key(kind: str, text: str) -> str: return f"{kind}:{hashlib.sha1(str(text).encode('utf-8', 'replace')).hexdigest()[:16]}"


def _find(store, q: str, items: list) -> list:
    """The keys of [(key, text)] that bear on `q`, best first: alike in MEANING (embeddings, textsim) - a set of shared word stems
    decided it once (the owner, 2026-10-28: no hard-coded words). No embedder: the ones that carry `q` whole, found literally."""
    got = textsim.rank(store, q, items)
    if got is not None: return [k for k, _ in got]
    want = ' '.join(str(q or '').split()).lower()
    return [k for k, t in items if want and want in ' '.join(str(t or '').split()).lower()]

def _sections(name: str, text: str):
    """A doc cut at its `##` headings, and a long section at its paragraphs - a passage is what an answer quotes."""
    parts = _H2.split(_COMMENT.sub('', text))
    for n, part in enumerate(parts):
        where = name if n == 0 else f"{name} > {part.splitlines()[0].strip()}"
        body, buf = ('## ' + part) if n else part, ''
        for para in re.split(r'\n\s*\n', body):
            if buf and len(buf) + len(para) > CHUNK: yield where, buf; buf = ''
            buf += para + NL * 2
        if buf.strip(): yield where, buf

def _corpus(store):
    if SITE_DOCS.is_dir():
        for f in sorted(SITE_DOCS.glob('*.md')): yield from _sections(f'help/{f.stem}', f.read_text(encoding='utf-8'))
    for n in store.doc_names(): yield from _sections(f'your doc {n}', store.doc(n) or '')

def docs_search(store, p: dict) -> str:
    q = ' '.join(str(p.get('query') or '').split())
    if not q: return 'docs.search needs the words to look for.'
    chunks = {f'doc:{where}#{i}': (where, t) for i, (where, t) in enumerate(_corpus(store))}
    hits = _find(store, q, [(k, t) for k, (_, t) in chunks.items()])[:4]
    if not hits: return f'Nothing in the help pages or your docs bears on "{q}".'
    return (NL * 2).join(f'[{chunks[k][0]}]{NL}{_cut(chunks[k][1], CHUNK)}' for k in hits)

def _days(p, default):
    try: days = float(p.get('days') or default)
    except (TypeError, ValueError): return None
    return max(1, min(days, 31)) if math.isfinite(days) else None

def _since(days) -> str: return (datetime.now() - timedelta(days=days)).isoformat(' ', 'seconds')

def _title(store, tid) -> str:
    t = store.get_task(int(tid)) if tid else None
    return f"{task_ref(tid)} {_cut(t.get('Title'), 80)}" if t else (task_ref(tid) if tid else 'no task')

def agents_now(store, p: dict) -> str:
    from . import terminal
    live = terminal.live_sessions(0, details=False)
    out = []
    for i in live:
        req = (i.get('request') or {}).get('text') if isinstance(i.get('request'), dict) else ''
        state = i.get('line') or {'parked': 'idle, waiting for its next instruction'}.get(i.get('phase'), i.get('phase') or 'working')
        out.append(f"{_title(store, i.get('taskId'))} - {i.get('agent') or i.get('cli') or 'agent'} ({i.get('cli') or '?'}), "
                   f"started {_day(i.get('started'))}: {state}" + (f' | asking: {_cut(req, 240)}' if req and req not in state else ''))
    on = {str(i.get('taskId')) for i in live}
    out += [f"{_title(store, r['TaskId'])} - {r['AgentName']}: running in the background since {_day(r['StartedAt'])}"
            for r in store.running_runs() if str(r['TaskId']) not in on]
    return NL.join(out) if out else 'No agent is working on anything right now.'

def approvals_list(store, p: dict) -> str:
    rows = store.list_reviews(status='pending')
    if not rows: return 'Nothing is waiting for your approval.'
    def what(r):
        if r.get('Kind') == 'action':
            try: return 'the agent proposes to ' + str(json.loads(r.get('DraftText') or '{}').get('action') or 'act')
            except ValueError: return 'an agent proposal'
        return f"a {str(r.get('Kind') or 'draft').replace('_', ' ')} to {r.get('FromName') or r.get('FromEmail') or 'them'}"
    return NL.join(f"{_title(store, r.get('TaskId'))} - {what(r)}, since {_day(r.get('CreatedAt'))}"
                   + (f" | {_cut(r.get('Reason'), 160)}" if r.get('Reason') else '') for r in rows[:30])

def pipe_list(store, p: dict) -> str:
    """Everything waiting on the owner, lane by lane - the rail itself. "What's waiting on me" was answered out of
    approvals.list alone: one draft, while replies, asks and stopped agents sat on the rail unnamed (2026-09-24 audit)."""
    from . import funnel
    items = [i for i in (funnel.pile(store).get('items') or []) if not i.get('settling')]
    if not items: return 'The pipe is empty - nothing is waiting on you.'
    # BY THE RAIL'S OWN SECTIONS, the headings the owner sees (funnel.level_of) - each row still says its lane. Grouped by
    # lane, "For later" never appeared: it is a section, not a lane, and "what is waiting in later" was answered "nothing is
    # parked in Later" over four rows sitting under that heading (the owner, 2026-09-30)
    # ...and each row in the words the rail and the phone give it (funnel_presentation.shows)
    from .funnel_presentation import back_in, shows
    out = []
    for sec in funnel.lanes.LEVEL_ORDER:
        xs = [i for i in items if funnel.level_of(i) == sec]
        if not xs: continue
        out.append(f"{funnel.SECTION_WORDS[sec].upper()} ({len(xs)}):")
        def row(i):
            back, sh = back_in(i.get('back_at') or i.get('defer_until')) if sec == 'later' else '', i.get('shows') or shows(i)
            return (f"  {task_ref(i['tid']) + ' ' if i.get('tid') else ''}{sh['who']} - {_cut(i.get('title'), 100)}"
                    f" [{sh['state']}{', back ' + back if back else ''}]")
        out += [row(i) for i in xs[:15]]
        if len(xs) > 15: out.append(f'  ...and {len(xs) - 15} more')
    return NL.join(out)

RAIL_READ_CHARS, OWN_CHARS, OWN_FLOOR = 18_000, 600, 160    # one call holds a whole lane; a long lane gets shorter quotes before fewer rows

def rail_counts(items) -> str:
    """'Tasks 4, Reports 2, FYI 23' - the rail's sections, in its order."""
    from . import funnel
    n = {}
    for i in items: n[funnel.level_of(i)] = n.get(funnel.level_of(i), 0) + 1
    return ', '.join(f'{funnel.SECTION_WORDS[s]} {n[s]}' for s in funnel.lanes.LEVEL_ORDER if n.get(s))

def _own(store, i) -> str:
    # the sender's own words, the chain under them cut off - what the FYI batch card shows of each member (concierge._context)
    from .triage import own_words
    m = store.get_message(i['mid']) if i.get('mid') else None
    return ' '.join((str((m or {}).get('OwnText') or '').strip() or own_words(str((m or {}).get('BodyText') or i.get('preview') or ''))).split())

def pipe_read(store, p: dict) -> str:
    """EVERY ROW ON THE RAIL WITH WHAT IT SAYS (the owner, 2026-10-28: "summarize the FYI emails" - "it should know everything on the work
    rail"): pipe.list names rows by subject and the turn's rail block stops at twenty, so a summary of the FYI lane took a message.read
    per mail and ran out of look-ups. One call reads a whole section; past the size it holds it says how many it left out."""
    from . import funnel
    from .funnel_presentation import shows
    from .timewords import ago
    pl, want, who = funnel.pile(store), str(p.get('section') or p.get('lane') or '').strip().lower(), str(p.get('who') or '').strip().lower()
    items = [i for i in pl.get('items') or [] if not i.get('settling')]
    if not items: return 'The rail is empty - nothing is on it.'
    words = {**{s: s for s in funnel.lanes.LEVEL_ORDER}, **{w.lower(): s for s, w in funnel.SECTION_WORDS.items()}, 'tasks': 'task', 'report': 'reports'}
    if want in ('', 'all', 'everything', 'rail'): xs, said = items, 'every row'
    elif want in words: xs, said = [i for i in items if funnel.level_of(i) == words[want]], funnel.SECTION_WORDS[words[want]]
    elif want in funnel.LANE_WORDS: xs, said = [i for i in items if i.get('lane') == want], f'lane {want}'
    else: return f'There is no rail section {want!r} - section: {" | ".join(funnel.lanes.LEVEL_ORDER)} (or a lane: {", ".join(funnel.LANE_WORDS)}).'
    if who: xs = [i for i in xs if who in f"{shows(i)['who']} {i.get('who') or ''} {i.get('email') or ''}".lower()]
    # ...and what the rail's own limit (Settings, funnel_max) holds back is said too: those rows are not on it yet
    held = f" {pl['hidden']} more wait behind the rail's limit and come on as these go." if pl.get('hidden') else ''
    head = f"THE RAIL: {len(items)} rows ({rail_counts(items)}).{held} {said}{' from ' + who if who else ''}: {len(xs)}."
    if not xs: return head + ' None.'
    n = max(OWN_FLOOR, min(OWN_CHARS, RAIL_READ_CHARS // len(xs) - 140))
    out, used, left = [head], len(head), 0
    for k, i in enumerate(xs):
        own = _own(store, i)
        row = (f"- {task_ref(i['tid']) + ' · ' if i.get('tid') else ''}{'m' + str(i['mid']) + ' · ' if i.get('mid') else ''}{shows(i)['who']} · "
               f"{_cut(i.get('title'), 120)} [{funnel.LANE_WORDS.get(i.get('lane'), (i.get('lane'),))[0]}, {ago(i.get('since') or i.get('when')) or '?'}]"
               + (f"{NL}  {own[:n] + ' […]' if len(own) > n else own}" if own else ''))
        if used + len(row) > RAIL_READ_CHARS: left = len(xs) - k; break
        out.append(row); used += len(row) + 1
    if left: out.append(f'...and {left} more not shown - narrow it: section (one of {", ".join(funnel.lanes.LEVEL_ORDER)}) or who (a sender).')
    return NL.join(out)

def calendar_read(store, p: dict) -> str:
    from . import calendar as cal
    if store.get_setting('calendar_enabled', '1') != '1': return 'The calendar is switched off in Settings.'
    when, days = str(p.get('from') or 'today').strip().lower(), _days(p, 7)
    if days is None: return 'calendar.read needs days to be a number.'
    start = datetime.now(cal.tz_of(store)).replace(hour=0, minute=0, second=0, microsecond=0)
    if when == 'tomorrow': start += timedelta(days=1)
    elif re.fullmatch(r'\d{4}-\d{2}-\d{2}', when):
        try: start = start.replace(year=int(when[:4]), month=int(when[5:7]), day=int(when[8:]))
        except ValueError: return f'calendar.read cannot use {when}; that is not a real date.'
    ag = cal.agenda(store, days=int(days), start=start)
    # WHICH calendars, said every time (2026-10-26): asked "what calendar did you check?" the model could only say the read did not
    # name one - and a Gmail card read over IMAP brings no calendar at all, which "an Outlook or Google mail connection brings its
    # calendar" told it the opposite of
    blind = cal.unread_mail(store)
    unread = (f"NOT read - no calendar comes with these cards: {'; '.join(blind)} (a Gmail card reads its calendar only once "
              f"Sign in with Google for the calendar is done on it; IMAP carries none). An event there is not in this answer either way." if blind else '')
    if not ag['sources']: return NL.join(['No calendar is connected - an Outlook card brings its calendar with it, a Gmail card once '
                                          'Sign in with Google for the calendar is done on it.'] + ([unread] if unread else []))
    ev = [f"{e['start']}{'-' + e['end'][11:] if e.get('end') and not e['all_day'] else ''} {'(all day) ' if e['all_day'] else ''}"
          f"{e['subject']}{' @ ' + e['where'] if e.get('where') else ''}{' with ' + ', '.join(e['who'][:5]) if e.get('who') else ''}"
          for e in ag['events']]
    return NL.join([f"{ag['start'][:10]} to {ag['end'][:10]} ({ag['tz']}), read from {'; '.join(ag['sources'])}:"] + (ev or ['nothing booked'])
                   + [f'could not read one calendar: {x}' for x in ag['errors']] + ([unread] if unread else []))

def activity_list(store, p: dict) -> str:
    """What happened, from the audit trail - the owner and the agents apart."""
    days, who = _days(p, 1), str(p.get('who') or 'all').strip().lower()
    if days is None: return 'activity.list needs days to be a number.'
    rows = [r for r in store.audit_since(_since(days)) if who == 'all' or (r['ActorType'] == 'agent') == (who == 'agents')]
    if not rows: return 'Nothing was recorded in that period.'
    counts = {}
    for r in rows: k = (r['ActorType'] == 'agent', r['EntityType'], r['Action']); counts[k] = counts.get(k, 0) + 1
    summary = [f"{'agents' if a else 'you'}: {n} x {e} {act.replace('_', ' ')}" for (a, e, act), n in sorted(counts.items(), key=lambda kv: -kv[1])[:20]]
    ref = lambda r: task_ref(r['EntityId']) if r['EntityType'] == 'task' and r['EntityId'] else f"{r['EntityType']} {r['EntityId'] or ''}".strip()
    last = [f"  {_day(r['CreatedAt'])} {r['Actor']}: {r['Action'].replace('_', ' ')} {ref(r)}{' - ' + _cut(r['Detail'], 100) if r.get('Detail') else ''}"
            for r in rows[:15]]
    return NL.join([f'{len(rows)} things in the last {days:g} day(s):'] + summary + ['most recent:'] + last)

LOG_TAIL = 400_000     # bytes read off the end of the log: a few days of a busy install

def log_path():
    from . import config
    return config.home() / 'taskuary.log'

def _log_errors(n=12) -> list:
    f = log_path()
    if not f.exists(): return []
    with open(f, 'rb') as fh:
        fh.seek(max(0, f.stat().st_size - LOG_TAIL)); text = fh.read().decode('utf-8', 'replace')
    return [l for l in text.splitlines() if ' ERROR ' in l or ' CRITICAL ' in l][-n:]

def errors_list(store, p: dict) -> str:
    """Everything written down as failing: the bell first, then each table that records a failure, then the log."""
    from . import problems
    days, down = _days(p, 3), problems._dismissed(store)
    if days is None: return 'errors.list needs days to be a number.'
    bell = [f"{'(you dismissed this) ' if down.get(x['key']) == problems.signature(x) else ''}{x['title']} - {_cut(x['detail'], 300)}"
            f"{' (' + _cut(x['error'], 200) + ')' if x.get('error') else ''}"
            f"{' since ' + _day(x['since']) if x.get('since') else ''} - fix: {x['fix']} on {x['where']}" for x in problems.collect(store, all_of_them=True)]
    out = (['FAILING NOW:'] + bell) if bell else ['Nothing is failing right now.']
    # ...and what ended by itself in the last few hours, in the words the bell used
    back = [f"{x['title']} {x['detail']}" for x in problems.news(store)]
    if back: out += ['RECOVERED IN THE LAST FEW HOURS:'] + back
    for what, rows in store.failures_since(_since(days)).items():
        if rows: out += [f'{what.upper()} THAT FAILED ({len(rows)}):'] + [
            f"  {_day(r['At'])} {_title(store, r['TaskId']) + ' ' if r.get('TaskId') else ''}{r['Who'] or ''}: {_cut(r['Error'], 240)}" for r in rows[:8]]
    logged = _log_errors()
    if logged: out += ['LAST ERRORS IN THE LOG:'] + [f'  {_cut(l, 300)}' for l in logged]
    return NL.join(out)

def _about(p) -> str: return ' '.join(str(p.get('about') or '').split())


def _bearing(store, want: str, texts) -> set:
    """Which of `texts` bear on `want` (_find), as the texts themselves - every one when nothing was asked about."""
    texts = [str(t) for t in texts if str(t or '').strip()]
    if not want: return set(texts)
    by = {_key('line', t): t for t in texts}
    return {by[k] for k in _find(store, want, list(by.items()))}

def memory_list(store, p: dict) -> str:
    """Everything kept about the owner: LEARNED.md - their verdicts and what they told the Assistant are lines in it (2026-10-27)."""
    from . import learn
    want = _about(p)
    doc = store.doc(learn.DOC) or ''
    learned, testing = learn.injectable(doc), learn._block(doc, learn.HYP_START, learn.HYP_END)
    from . import orgchart
    lines, org = learned.splitlines(), orgchart.block(store).splitlines()
    near = _bearing(store, want, lines + org)
    if want: learned = NL.join(l for l in lines if l in near)
    out = ['YOUR MEMORY (LEARNED.md - what you said and what I learned from what you did):' + NL + _cut(learned, 4000) if learned.strip()
           else 'LEARNED.md has nothing' + (' that matches.' if want else ' in it yet.')]
    if testing and not want: out.append('STILL BEING TESTED, not trusted yet:' + NL + _cut(testing, 1200))
    org = NL.join(l for l in org if l in near)
    if org: out.append('YOUR PEOPLE (the org chart - your manager, your reports, who owns what):' + NL + org)
    return NL.join(out)

ACTION_SAYS = {'skip': 'never shown at all', 'ignore': 'shown, marked nothing to do', 'escalate': 'raised to you',
               'auto_answer': 'answered automatically', 'draft': 'a reply drafted', 'task_only': 'made a task, no reply'}

def rules_list(store, p: dict) -> str:
    """The standing filters: queue mutes (said with a reason) and the policy rules, which decide before any model reads the mail."""
    from . import funnel
    want = _about(p)
    says = lambda *xs: ' '.join(str(x or '') for x in xs)
    mutes, pols = funnel.mutes(store), store.list_policies(active_only=False)
    near = _bearing(store, want, [says(m.get('sender'), ' '.join(m.get('words') or []), m.get('why')) for m in mutes]
                    + [says(x.get('Name'), x.get('Pattern'), x.get('Reason')) for x in pols])
    hit = lambda *xs: not want or says(*xs) in near
    mutes = [m for m in mutes if hit(m.get('sender'), ' '.join(m.get('words') or []), m.get('why'))]
    out = [f'QUEUE MUTES ({len(mutes)}) - set when you cleared items with a reason:'] if mutes else ['No queue mutes.']
    out += [f"  {m.get('sender') or 'anyone'}{' about ' + ' '.join(m['words']) if m.get('words') else ''}{' - ' + _cut(m['why'], 160) if m.get('why') else ''}"
            for m in mutes]
    pols = [x for x in pols if hit(x.get('Name'), x.get('Pattern'), x.get('Reason'))]
    off = sum(1 for x in pols if not x.get('Active', 1))
    out.append(f'POLICY RULES ({len(pols) - off} on{f", {off} off" if off else ""}) - checked before any model reads the mail:' if pols else 'No policy rules.')
    for act in ACTION_SAYS:
        seen = {}
        for x in pols:
            if x.get('Active', 1) and x['Action'] == act: seen.setdefault((x['Kind'], (x.get('Pattern') or '').lower()), x)
        if not seen: continue
        out.append(f'  {act} ({ACTION_SAYS[act]}): {len(seen)}')
        out += [f"    {k}{': ' + pat if pat else ''}{' - ' + _cut(x['Reason'], 120) if x.get('Reason') else ''}" for (k, pat), x in list(seen.items())[:40]]
    return NL.join(out)

def asks_list(store, p: dict) -> str:
    from . import asks
    return asks.listing(store, p)

def memory_about(store, p: dict) -> str:
    """WHO SOMEONE IS TO THE OWNER (slice 7, 2026-10-25: "who's Gail to me"): the memory's lines about them, each with its key, and the
    org chart's word - read, never guessed; nothing known is said so."""
    from . import memoryedit
    a = memoryedit.about(store, str(p.get('who') or p.get('sender') or ''))
    out = [f"ABOUT {a['who']}" + (f" ({', '.join(n for n in a['names'] if '@' in n)})" if any('@' in n for n in a['names']) else '')
           + (f" - the org chart: {a['relation']}" if a['relation'] else '')]
    out += [f"  [key: {l['key']}] ({l['section']}{', yours' if l['own'] else ''}{', still being tested' if l['status'] == 'watching' else ''}) {_cut(l['text'], 300)}"
            for l in a['lines']]
    if not a['lines']: out.append('  The memory holds nothing about them yet' + (' beyond the org chart.' if a['relation'] else '.'))
    return NL.join(out)


def missed_check(store, p: dict) -> str:
    """"Did I miss anything?" - the morning brief's unanswered and waiting-on-them checks, and what could not be seen."""
    from . import welcome
    d = welcome.missed(store)
    facts = ([f"ASKED, NO ANSWER FROM YOU: {a['facts']}" for a in d['asked']] + [f"NOT JUDGED: {u['facts']}" for u in d.get('unjudged') or []]
             + [f"WAITING ON THEM: {w['facts']}" for w in d['waiting']] + ([f"NOT TRACKED: {d['untracked']}"] if d.get('untracked') else [])
             + [f"COULD NOT CHECK: {n} (not answering since {_day(at) or '?'})" for n, at in d['blind']]
             + [f"URGENT: {task_ref(t['TaskId'])} {_cut(t.get('Title'), 100)}" for t in d['urgent']])
    return NL.join(facts + ['', 'SAY IT LIKE THIS (keep every fact, in your own words if you like):', welcome.missed_says(d)])

def deleted_list(store, p: dict) -> str:
    """RECENTLY DELETED (recentlydeleted.py): what Restore can still bring back - reports, workflows, dashboards, rules, profiles - and when it
    goes for good. deleted.restore names one by its title."""
    from . import recentlydeleted
    rows = recentlydeleted.listing(store)
    if not rows: return 'Recently deleted is empty - nothing removed in the last 30 days can be restored.'
    return NL.join([f'RECENTLY DELETED ({len(rows)}) - each comes back with deleted.restore:']
                   + [f"  {r['kind']}: {_cut(r['title'], 100)} ({r['days_left']} days left)" for r in rows[:30]])

def outputs_find(store, p: dict) -> str:
    """THE FILE AN AGENT MADE, by what it is about (outputs.find): its name, its task, when, and the link the Result's Download uses -
    one tap saves it - with its task's own link. On a phone no link opens, so the file and its task are named instead."""
    from . import outputs
    from .concierge import DELIVERY, PHONE
    m = re.search(r'\d+', str(p.get('ref') or ''))
    hits = outputs.find(store, str(p.get('query') or p.get('contains') or ''), str(p.get('kind') or ''), int(m.group()) if m else None)
    if not hits:
        return ('No file an agent made matches that' + (f" on {task_ref(int(m.group()))}" if m else '')
                + (' of that kind' if p.get('kind') else '') + ' - try fewer words, or none with the kind alone.')
    phone = DELIVERY.get() == PHONE
    out = [f'FILES AGENTS MADE ({len(hits)}, best match first) - ' + (
        "no link opens on a phone: name the file and its task; the task's card sends the file itself" if phone else
        'answer with the one that fits as [its name](its link) - one tap downloads it - and its task as [TQ-n](#task=n)') + ':']
    for h in hits:
        ref, url = task_ref(h['tid']), h.get('url') or h.get('external_url') or ''
        more = f" ({plural(len(h['earlier']), 'earlier version')} behind it)" if h.get('earlier') else ''
        out.append(f"  {h['name']} - {ref} \"{_cut(h['title'], 90)}\" (#task={h['tid']}) - {_day(h.get('at') or h.get('created_at'))}{more}"
                   + ('' if phone or not url else f' - link: {url}'))
    return NL.join(out)

READ = {'deleted.list': deleted_list, 'outputs.find': outputs_find, 'tasks.list': tasks_list, 'message.read': message_read, 'sender.read': sender_read, 'docs.search': docs_search,
        'agents.now': agents_now, 'approvals.list': approvals_list, 'pipe.list': pipe_list, 'pipe.read': pipe_read, 'calendar.read': calendar_read,
        'activity.list': activity_list, 'errors.list': errors_list,
        'memory.list': memory_list, 'memory.about': memory_about, 'rules.list': rules_list, 'asks.list': asks_list, 'missed.check': missed_check}

def read(store, kind: str, p: dict) -> str:
    f = READ.get(kind)
    return f(store, p or {}) if f else f'{kind} is not a look-up this app has.'
