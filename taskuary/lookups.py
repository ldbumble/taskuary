"""The assistant's look-ups past the first ten (concierge.read_op): open work, one message in full, a
sender at a glance, the docs, what the agents are doing, what waits for approval, the calendar,
what happened, what failed, what is kept about the owner and the rules that filter their mail. Each
reads what is already recorded and changes nothing - the assistant stays light because it asks for
what it needs instead of carrying a memory in its prompt
(the owner, 2026-09-24: "it should be able to search ... using lookup tools")."""
import json, math, re
from datetime import datetime, timedelta
from pathlib import Path
from .routing import tokens
from .store import task_ref

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

def tasks_list(store, p: dict) -> str:
    status, limit = str(p.get('status') or 'open').strip().lower(), max(1, min(int(p.get('limit') or 25), 60))
    rows = store.list_tasks(status=None if status in ('open', 'all') else status, q=str(p.get('contains') or '').strip() or None)
    if status == 'open': rows = [t for t in rows if t.get('Status') in ACTIVE]
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
    if not hits: return f'Nobody by "{who}" has written in.'
    s = next((h for h in hits if h['Email'] == who.lower()), hits[0])
    em, since = s['Email'], (datetime.now() - timedelta(days=3650)).isoformat(' ', 'seconds')
    out = [f"{s['Name'] or em} <{em}> - {s['N']} messages, first {_day(s['First'])}, last {_day(s['Last'])}"]
    recent = store.messages_from(em, since, 8)
    if recent: out += ['recent:'] + [f"  m{r['MessageId']} {_day(r.get('SentAt'))} {task_ref(r['TaskId']) if r.get('TaskId') else '-'} "
                                     f"[{r.get('Status')}] {_cut(r.get('Subject'), 110)}" for r in recent]
    tasks = store.open_tasks_from(em)
    out.append('open tasks: ' + ('; '.join(f"{task_ref(t['TaskId'])} {_cut(t['Title'], 80)} ({t['Status']})" for t in tasks) if tasks else 'none'))
    replies = store.own_replies_to(em, since, 3)
    if replies: out.append('you last wrote back ' + _day(replies[0].get('SentAt')))
    notes = [m['Note'] for m in store.list_memories() if str(m.get('ScopeKey') or '').lower() == em]
    if notes: out += ['what you told me about them:'] + [f'  - {_cut(n, 300)}' for n in notes[:8]]
    others = [h for h in hits if h['Email'] != em]
    if others: out.append('also matching: ' + ', '.join(f"{h['Name'] or h['Email']} <{h['Email']}> ({h['N']})" for h in others))
    return NL.join(out)

_COMMENT = re.compile(r'<!--.*?-->', re.S)
CHUNK = 1200

def _stem(w): return w[:-1] if len(w) > 4 and w.endswith('s') else w
def _words(text): return {_stem(w) for w in tokens(text) if len(w) > 2}

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
    q = str(p.get('query') or '')
    want = _words(q)
    if not want: return 'docs.search needs the words to look for.'
    chunks = [(w, t, _words(t)) for w, t in _corpus(store)]
    # a word most passages share says little about which one is meant; a rare one says a lot
    df = {w: sum(w in have for _, _, have in chunks) for w in want}
    idf = {w: math.log((len(chunks) + 1) / (df[w] + 0.5)) for w in want if df[w]}
    scored = sorted(((sum(idf[w] for w in idf if w in have), where, t) for where, t, have in chunks if want & have), key=lambda s: -s[0])
    if not scored: return f'Nothing in the help pages or your docs mentions "{q}".'
    return (NL * 2).join(f'[{w}]{NL}{_cut(t, CHUNK)}' for sc, w, t in scored[:4] if sc >= scored[0][0] / 2)

def _since(days) -> str: return (datetime.now() - timedelta(days=float(days))).isoformat(' ', 'seconds')

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

def calendar_read(store, p: dict) -> str:
    from . import calendar as cal
    if store.get_settings().get('calendar_enabled', '1') != '1': return 'The calendar is switched off in Settings.'
    when, days = str(p.get('from') or 'today').strip().lower(), max(1, min(int(p.get('days') or 7), 31))
    start = datetime.now(cal.tz_of(store)).replace(hour=0, minute=0, second=0, microsecond=0)
    if when == 'tomorrow': start += timedelta(days=1)
    elif re.fullmatch(r'\d{4}-\d{2}-\d{2}', when): start = start.replace(year=int(when[:4]), month=int(when[5:7]), day=int(when[8:]))
    ag = cal.agenda(store, days=days, start=start)
    if not ag['sources']: return 'No calendar is connected - an Outlook or Google mail connection brings its calendar with it.'
    ev = [f"{e['start']}{'-' + e['end'][11:] if e.get('end') and not e['all_day'] else ''} {'(all day) ' if e['all_day'] else ''}"
          f"{e['subject']}{' @ ' + e['where'] if e.get('where') else ''}{' with ' + ', '.join(e['who'][:5]) if e.get('who') else ''}"
          for e in ag['events']]
    return NL.join([f"{ag['start'][:10]} to {ag['end'][:10]} ({ag['tz']}):"] + (ev or ['nothing booked'])
                   + [f'could not read one calendar: {x}' for x in ag['errors']])

def activity_list(store, p: dict) -> str:
    """What happened, from the audit trail - the owner and the agents apart."""
    days, who = float(p.get('days') or 1), str(p.get('who') or 'all').strip().lower()
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
    days, down = float(p.get('days') or 3), problems._dismissed(store)
    bell = [f"{'(you dismissed this) ' if down.get(x['key']) == problems.signature(x) else ''}{x['title']} - {_cut(x['detail'], 300)}"
            f"{' since ' + _day(x['since']) if x.get('since') else ''} - fix: {x['fix']} on {x['where']}" for x in problems.collect(store, all_of_them=True)]
    out = (['FAILING NOW:'] + bell) if bell else ['Nothing is failing right now.']
    for what, rows in store.failures_since(_since(days)).items():
        if rows: out += [f'{what.upper()} THAT FAILED ({len(rows)}):'] + [
            f"  {_day(r['At'])} {_title(store, r['TaskId']) + ' ' if r.get('TaskId') else ''}{r['Who'] or ''}: {_cut(r['Error'], 240)}" for r in rows[:8]]
    logged = _log_errors()
    if logged: out += ['LAST ERRORS IN THE LOG:'] + [f'  {_cut(l, 300)}' for l in logged]
    return NL.join(out)

def _about(p) -> set: return _words(str(p.get('about') or ''))

def memory_list(store, p: dict) -> str:
    """Everything kept about the owner: the saved notes (chat, verdicts, Settings) and LEARNED.md."""
    from . import learn
    want = _about(p)
    hit = lambda *xs: not want or bool(want & _words(' '.join(str(x or '') for x in xs)))
    notes = [m for m in store.list_memories() if hit(m.get('ScopeKey'), m.get('Note'))]
    out = [f'SAVED NOTES ({len(notes)}):' if notes else 'No saved notes' + (' match that.' if want else '.')]
    out += [f"  mem{m['MemoryId']} {_day(m.get('CreatedAt'))} [{m.get('Source') or 'manual'}, {m.get('Scope')}"
            f"{': ' + m['ScopeKey'] if m.get('ScopeKey') else ''}] {_cut(m.get('Note'), 300)}" for m in notes[:25]]
    doc = store.doc(learn.DOC) or ''
    learned, testing = learn.injectable(doc), learn._block(doc, learn.HYP_START, learn.HYP_END)
    if want: learned = NL.join(l for l in learned.splitlines() if hit(l))
    out.append('WHAT I LEARNED FROM YOUR VERDICTS (LEARNED.md):' + NL + _cut(learned, 3000) if learned.strip() else 'LEARNED.md has nothing learned yet.')
    if testing and not want: out.append('STILL BEING TESTED, not trusted yet:' + NL + _cut(testing, 1200))
    return NL.join(out)

ACTION_SAYS = {'skip': 'never shown at all', 'ignore': 'shown, marked nothing to do', 'escalate': 'raised to you',
               'auto_answer': 'answered automatically', 'draft': 'a reply drafted', 'task_only': 'made a task, no reply'}

def rules_list(store, p: dict) -> str:
    """The standing filters: queue mutes (said with a reason) and the policy rules, which decide before any model reads the mail."""
    from . import funnel
    want = _about(p)
    hit = lambda *xs: not want or bool(want & _words(' '.join(str(x or '') for x in xs)))
    mutes = [m for m in funnel.mutes(store) if hit(m.get('sender'), ' '.join(m.get('words') or []), m.get('why'))]
    out = [f'QUEUE MUTES ({len(mutes)}) - set when you cleared items with a reason:'] if mutes else ['No queue mutes.']
    out += [f"  {m.get('sender') or 'anyone'}{' about ' + ' '.join(m['words']) if m.get('words') else ''}{' - ' + _cut(m['why'], 160) if m.get('why') else ''}"
            for m in mutes]
    pols = [x for x in store.list_policies(active_only=False) if hit(x.get('Name'), x.get('Pattern'), x.get('Reason'))]
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

READ = {'tasks.list': tasks_list, 'message.read': message_read, 'sender.read': sender_read, 'docs.search': docs_search,
        'agents.now': agents_now, 'approvals.list': approvals_list, 'calendar.read': calendar_read,
        'activity.list': activity_list, 'errors.list': errors_list,
        'memory.list': memory_list, 'rules.list': rules_list}

def read(store, kind: str, p: dict) -> str:
    f = READ.get(kind)
    return f(store, p or {}) if f else f'{kind} is not a look-up this app has.'
