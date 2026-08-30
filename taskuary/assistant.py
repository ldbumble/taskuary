"""The assistant on the Timeline: a check every 20 minutes, a post only when it has something to say.

Triage judges each message as it arrives and then nothing ever spoke up later - the reply the
owner sent on Monday and never heard back on, the meeting in two hours with five mails of
history behind it, the task that went quiet. This is the voice that does: on its own clock it gathers what the hub can see
(followups: the owner wrote last and asked for something; prep: meetings ahead, with what came
before them; cold: work nothing has touched; and its own ideas
from the day's mail), asks the model for its read GIVEN WHAT IT ALREADY SAID, and posts only what
is new as ONE row on the Timeline - each line with its buttons on the panel: Follow up (the chase
is drafted in the owner's voice, into Review), Make it a task (the agent starts), Not this, Snooze.

It never repeats itself: every idea has a key and a state (idea table). Said once with the same
facts is said; dismissed stays dismissed until the facts change; snoozed sleeps. Not this / Snooze
are verdicts, so LEARNED.md hears which kinds of nudges this owner never wants.

Nothing sits pinned above the Timeline: the assistant IS its rows, each posted for something
specific, and what is open, in flight and waiting on the owner is the Morning digest's job on its
own clock (the owner, 2026-08-30: the status strip with its counts and 'ask now' was noise). The
thresholds and the producers are settings (assistant_*); the clock and the instruction are the
'Assistant' report on the Reports tab.

It also leaves itself a NOTE: each check ends with what it looked at and found nothing in, when
something becomes worth raising, whatever it would otherwise work out again - and the next check
starts by reading it (assistant_notes). Twenty-minute checks are cheap only if each one does not
start from zero; a quiet check still rewrites the note, it just posts nothing.
"""
import json, re
from datetime import datetime, timedelta
from loguru import logger

from .store import task_ref

CHANNEL = 'assistant'
PRODUCERS = ('followup', 'promise', 'prep', 'cold', 'idea')
DAYS = 30                  # how far back followups and promises are read
MAX_LINES = 5              # lines per post by default - a post nobody reads to the end is a post that failed
POST_TOKENS = 700
# the owner's last word on a thread ASKED for something - that is what a chase is for...
_ASKS = re.compile(r'\?|\b(let me know|could you|can you|would you|please (send|confirm|share|advise|review|check)|get back to me|'
                   r'by (monday|tuesday|wednesday|thursday|friday|eod|end of (day|week)|tomorrow|next week))\b', re.I)
# ...or PROMISED something, which is the owner's own open item, not the other side's
_PROMISE = re.compile(r"\b(i('ll| will)|i'?m going to|let me) (send|get|have|follow|circle|check|share|update|confirm|look|review|come back|revert)\b", re.I)

# The editable instruction - what a real assistant watches for. Seeded as the 'Assistant' report
# on the Reports tab (store.__init__), so the owner edits it there like the Morning digest's;
# this copy is the default and the fallback. CONTRACT (the JSON shape) stays in code.
PROMPT = (
    'You are my assistant. Every 20 minutes you check in; tell me only what a sharp human assistant would lean over and say - '
    'nothing I can already see in my inbox. Watch for, in this order of worth:\n'
    '1. What I am waiting on from others and have not chased (the CANDIDATES marked followup): name who and what, and '
    'whether it is worth a nudge yet - a vendor who always takes a week is not news at day two.\n'
    '2. What I promised and have not done (promise): the date I gave, and whether it has passed.\n'
    '3. Meetings in the next day (prep): who is in the room, the last exchange I had with each, the one open item, and '
    'the question worth asking. A recurring standup with nothing new needs no line.\n'
    '4. Work that has gone quiet (cold): push it or drop it - say which I would do.\n'
    '5. Dates and deadlines buried in what arrived today - a renewal, a due date, an RSVP - that nobody made a task.\n'
    '6. Patterns: the same person asking twice, a thread past six messages with no decision, two people asking me '
    'the same thing, a system failing twice this week.\n'
    '7. Getting ahead: the thing to do now so the next ask never comes.\n'
    'Be useful, not busy: a quiet check gets no post - most checks should. Never repeat anything under ALREADY SAID, reworded or not.\n'
    'End every check with a note to your next one: what you looked at and found nothing in, when something becomes worth '
    'raising (a date, a length of silence), anything you would otherwise have to work out again.')
OLD_PROMPT_HEAD = 'You are my assistant. Once an hour,'      # a stock prompt still starting like this is healed to PROMPT (store.__init__)


def cfg(store) -> dict:
    s = store.get_settings()
    def n(k, d):
        try: return max(0, int(s.get(k) or d))
        except (TypeError, ValueError): return d
    raw = s.get('assistant_producers')
    prod = {p.strip() for p in (raw if raw is not None else ','.join(PRODUCERS)).split(',') if p.strip()}
    return {'followup_h': n('assistant_followup_hours', 24), 'cold_d': n('assistant_cold_days', 3), 'max': max(1, n('assistant_max_lines', MAX_LINES)),
            'producers': prod, 'last': s.get('assistant_last_run') or ''}


def source(store) -> dict | None:
    """The 'Assistant' row on the Reports tab: its schedule, its instruction, and whether it is on at
    all - the same three things the Morning digest keeps there. None when the owner deleted it."""
    for src in store.list_sources(active_only=False):
        if src.get('Channel') != 'report': continue
        try: c = json.loads(src.get('ConfigJson') or '{}')
        except ValueError: continue
        if c.get('type') == 'assistant': return src | {'cfg': c}
    return None


def _ts(s): return str(s or '')[:19].replace('T', ' ')
def _since(days): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
def _short(s, n=90): return ' '.join(str(s or '').split())[:n]
def _dt(s):
    try: return datetime.fromisoformat(_ts(s))
    except ValueError: return None


# ── the candidates: facts the hub can find without a model ───────────────────────────────────
def followups(store, hours: int, want=('followup', 'promise')) -> list:
    """Threads where the last word is the owner's, `hours` old or more, and that word ASKED for
    something (followup - theirs to answer, ours to chase) or PROMISED something (promise - the
    owner's own open item). Silence after a plain "thanks" is neither."""
    from .triage import strip_boilerplate
    cut = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    out = []
    for r in store.owner_last_words(_since(DAYS), cut):
        body = strip_boilerplate(str(r.get('BodyText') or ''))
        kind = 'promise' if _PROMISE.search(body) else 'followup' if _ASKS.search(body) else None
        if not kind or kind not in want: continue
        inbound = store.last_inbound_in(r['ConversationId'])
        if not inbound: continue                                    # nothing of theirs to answer under
        who = inbound.get('FromName') or inbound.get('FromEmail') or 'them'
        sent = _dt(r['SentAt']) or datetime.now()
        days = max(1, int((datetime.now() - sent).total_seconds() // 86400))
        subj = _short(inbound.get('Subject'), 60)
        if kind == 'promise':
            out.append({'key': f"promise:{r['ConversationId']}", 'kind': 'promise', 'sig': _ts(r['SentAt']),
                        'facts': f"You told {who} on {_ts(r['SentAt'])[:10]} re \"{_short(r.get('Subject'), 70)}\": \"{_short(body, 160)}\" - {days} day(s) ago, and the thread has not moved.",
                        'text': f"You told {who} you would - \"{_short(body, 70)}\" - {days} day{'s' if days != 1 else ''} ago on \"{subj}\". Done?",
                        'action': {'type': 'message', 'mid': inbound['MessageId'], 'tid': inbound.get('TaskId')}})
        else:
            out.append({'key': f"followup:{r['ConversationId']}", 'kind': 'followup', 'sig': _ts(r['SentAt']),
                        'facts': (f"You wrote {who} on {_ts(r['SentAt'])[:10]} re \"{_short(r.get('Subject'), 70)}\": \"{_short(body, 160)}\" "
                                  f"- nothing has come back in {days} day(s)."),
                        'text': f"No answer from {who} in {days} day{'s' if days != 1 else ''} on \"{subj}\" - follow up?",
                        'action': {'type': 'followup', 'mid': inbound['MessageId'], 'tid': inbound.get('TaskId')}})
    return out


def cold(store, days: int) -> list:
    """Open work nothing has touched for `days`: no comment, no message, no run. A live agent on
    it is activity; a draft waiting in Review is the owner's to move."""
    cut = _since(days)
    out = []
    for t in store.list_tasks(active_only=True):
        if t.get('Status') not in ('open', 'in_progress', 'waiting') or t.get('RunStatus') == 'running': continue
        last = _ts(store.task_last_activity(t['TaskId']) or t.get('UpdatedAt') or t.get('CreatedAt'))
        if not last or last > cut: continue
        age = max(days, (datetime.now() - (_dt(last) or datetime.now())).days)
        wait = t.get('Status') == 'waiting' or t.get('ReviewStatus') == 'pending'
        ref = task_ref(t['TaskId'])
        out.append({'key': f'cold:{ref}', 'kind': 'cold', 'sig': last,
                    'facts': f"{ref} \"{_short(t.get('Title'), 80)}\" [{t['Status']}, kind {t.get('Kind')}] - nothing has happened on it for {age} days"
                             + (' and a draft waits for you in Review' if wait else ''),
                    'text': (f"{ref} has a reply waiting on you for {age} days - \"{_short(t.get('Title'), 60)}\"" if wait
                             else f"{ref} has sat quiet for {age} days - \"{_short(t.get('Title'), 60)}\". Push it or drop it?"),
                    'action': {'type': 'task', 'tid': t['TaskId']}})
    return out


def prep(store) -> list:
    """Meetings in the next two days, each with what the hub already knows about the people in it
    and the subject - the prep note counsel writes for an invite, written for the ones already
    on the calendar."""
    if store.get_settings().get('calendar_enabled', '1') != '1': return []
    from . import calendar as cal
    from .counsel import dossier
    try: ag = cal.agenda(store, days=2)
    except Exception as e:
        logger.debug(f'assistant: calendar skipped - {e}'); return []
    out = []
    for e in (ag.get('events') or [])[:6]:
        if e.get('all_day'): continue
        who = list(e.get('who') or [])
        dos = dossier(store, {'from_email': '', 'from_name': ' '.join(who[:4]), 'subject': e.get('subject') or ''}, calendar=False)
        out.append({'key': f"prep:{e['start'][:16]}:{_short(e.get('subject'), 40)}", 'kind': 'prep', 'sig': e['start'][:16],
                    'facts': f"MEETING {e['start'][:16]} \"{e.get('subject')}\"" + (f" with {', '.join(who[:6])}" if who else '')
                             + (f" - about: {e['about']}" if e.get('about') else '')
                             + (f"\n  what the hub knows:\n  {dos[:1200]}" if dos else '\n  (nothing on file about these people or this subject)'),
                    'text': f"{cal.span(e['start'], e.get('end') or '')} {e.get('subject')}"
                            + (f" with {', '.join(w.split()[0] for w in who[:3])}" if who else '')
                            + (' - here is what came before it' if dos else ' - nothing on file, walk in fresh'),
                    'action': {'type': 'meeting', 'event': {k: e.get(k) for k in ('start', 'end', 'subject', 'who', 'where', 'about', 'join', 'organizer')}}})
    return out


def candidates(store, c: dict) -> list:
    out = []
    want = tuple(k for k in ('followup', 'promise') if k in c['producers'])
    for name, fn in (('followup/promise', lambda: followups(store, c['followup_h'], want) if want else []),
                     ('prep', lambda: prep(store) if 'prep' in c['producers'] else []),
                     ('cold', lambda: cold(store, c['cold_d']) if 'cold' in c['producers'] else [])):
        try: out += fn()
        except Exception as e: logger.warning(f'assistant: {name} candidates failed - {e}')
    return out


def fresh(state: dict, cand: dict, now: datetime) -> bool:
    """Worth saying now? Never said: yes. Said with these facts: no. Dismissed or done: only when
    the facts changed (a new last word on the thread, a moved meeting). Snoozed: when it wakes."""
    i = state.get(cand['key'])
    if not i: return True
    if i.get('Status') == 'snoozed': return bool(i.get('SnoozeUntil')) and _ts(i['SnoozeUntil']) <= now.strftime('%Y-%m-%d %H:%M:%S')
    return (i.get('Sig') or '') != (cand.get('sig') or '')


# ── the model's pass: its own read, given what it already said ───────────────────────────────
CONTRACT = ('\n\nYou are writing your POST on the owner\'s Timeline - the short list of things worth saying right now. You get '
            'CANDIDATES the hub found itself (each with a key), what arrived today, what is open, and WHAT YOU ALREADY SAID. '
            'Answer JSON only: {"say": [{"key": "<a candidate key, or idea:<short-slug> for a thought of your own>", '
            '"text": "<one line, under 30 words, first person: the fact and what I would do>", '
            '"why": "<one line: what this rests on - the mail, the date, the silence, the pattern - named as it appears in what you '
            'were given (sender, subject, mid, TQ-ref), so the owner can check it>", "mid": <the message id it is '
            'about, or null>, "task": "<idea:* only - a task title the owner could accept as-is, or null>"}], '
            '"notes": "<your note to the next check, under 120 words: what you looked at and found nothing in, when something becomes '
            'worth raising, what you settled so it need not be worked out again. Rewrite it whole each time; empty if nothing>"}.\n'
            'At most {max_lines} entries. Skip a candidate that is not worth the owner\'s eye (a standing standup needs no prep; a '
            'one-day silence from someone who always takes a week is not news) - skipping is free, repeating is not: never say '
            'again, reworded or not, anything under ALREADY SAID. Your own ideas are the point: a thread going in circles, a '
            'promise buried in a mail, two people asking the same thing, the thing to do now so the next ask never comes. '
            'Facts only from what you are given; never invent a name, a date or a number. Nothing new to say -> {"say": []}.')


def _today(store) -> str:
    rows = store.feed(limit=40, days=1)
    return '\n'.join(f"- [{r.get('Category')}] {r.get('FromName') or r.get('FromEmail') or r.get('SourceName') or '?'}: "
                     f"\"{_short(r.get('Subject'), 70)}\" (mid {r['MessageId']}" + (f", {task_ref(r['TaskId'])}" if r.get('TaskId') else '') + ')'
                     for r in rows if r.get('Channel') != CHANNEL) or '(nothing arrived today)'


def _open(store) -> str:
    ts = [t for t in store.list_tasks(active_only=True) if t.get('Status') in ('open', 'in_progress', 'waiting')]
    return '\n'.join(f"- {task_ref(t['TaskId'])} [{t['Status']}] {_short(t.get('Title'), 80)}" for t in ts[:20]) or '(nothing open)'


def _said(store) -> str:
    rows = [i for i in store.list_ideas() if i.get('Status') in ('open', 'dismissed', 'snoozed')][:40]
    return '\n'.join(f"- ({i['Status']}) {i['Text']}" for i in rows) or '(nothing yet)'


def parse(text: str, cands: list, max_lines: int = MAX_LINES) -> list:
    """The model's list, kept honest: a key it invents must be idea:*, a candidate key keeps its
    kind and its buttons, and the text is the model's when it gave one. Every line keeps its WHY -
    the hub's facts for a candidate (plus the model's read on them), the model's own for an idea -
    so the owner can see what it rests on (the owner, 2026-08-30: "why it brings up something,
    what is driving it")."""
    try: j = json.loads(re.sub(r'^```(json)?|```$', '', (text or '').strip(), flags=re.M))
    except ValueError: return []
    by = {c['key']: c for c in cands}
    out, seen = [], set()
    for s in (j.get('say') or []) if isinstance(j, dict) else []:
        if not isinstance(s, dict): continue
        key, txt, why = str(s.get('key') or '').strip(), _short(s.get('text'), 240), _short(s.get('why'), 400)
        if not key or key in seen or not txt: continue
        if key in by:
            out.append({**by[key], 'text': txt, 'why': by[key]['facts'] + (f"\nThe model's read: {why}" if why else '')})
        elif key.startswith('idea:') and len(key) > 5:
            mid = s.get('mid') if isinstance(s.get('mid'), int) else None
            title = _short(s.get('task'), 120) or None
            act = {'type': 'task', 'mid': mid, 'title': title} if title and mid else {'type': 'message', 'mid': mid} if mid else {'type': 'note'}
            out.append({'key': key[:120], 'kind': 'idea', 'sig': txt[:60], 'text': txt, 'action': act,
                        'why': why or 'the model gave no reason - treat it as a hunch' + (f' (about mid {mid})' if mid else '')})
        else: continue
        seen.add(key)
        if len(out) >= max_lines: break
    return out


def think(store, cands: list, llm, instruction: str = None, max_lines: int = MAX_LINES) -> list:
    """One call: COUNSEL.md's voice, the owner's instruction (the Reports tab), the candidates, the
    day, what was already said."""
    doc = re.sub(r'<!--.*?-->', '', store.doc('counsel') or '', flags=re.S).strip()
    soul = store.doc('soul') or ''
    system = (doc + f"\n\nYOUR INSTRUCTION (the owner's, from the Reports tab):\n{(instruction or PROMPT).strip()}" + CONTRACT.replace('{max_lines}', str(max_lines))
              + (f"\n\nWho the owner is (their own document; its reply rules are for text sent to OTHERS):\n{soul[:1500]}" if soul else ''))
    user = ('CANDIDATES:\n' + ('\n'.join(f"[{c['key']}] {c['facts']}" for c in cands) or '(none)')
            + f"\n\nARRIVED TODAY:\n{_today(store)}\n\nOPEN WORK:\n{_open(store)}\n\nALREADY SAID (never repeat):\n{_said(store)}"
            + f"\n\n{_notes_block(store)}")
    text = llm(system, user, max_tokens=POST_TOKENS)
    return parse(text, cands, max_lines), _notes(text)


def facts(store) -> str:
    """What a run would hand the model, as text - the Reports tab's Preview (reports.run_assistant)."""
    c = cfg(store); now = datetime.now()
    state = {i['Key']: i for i in store.list_ideas()}
    cands = [x for x in candidates(store, c) if fresh(state, x, now)]
    return ('CANDIDATES (new since the last post):\n' + ('\n'.join(f"[{c_['key']}] {c_['facts']}" for c_ in cands) or '(none)')
            + f"\n\nARRIVED TODAY:\n{_today(store)}\n\nOPEN WORK:\n{_open(store)}\n\nALREADY SAID:\n{_said(store)}\n\n{_notes_block(store)}")


# ── the note to the next check ───────────────────────────────────────────────────────────────
def notes(store) -> tuple:
    """(text, when) of the note the last check left - '' if none yet."""
    s = store.get_settings()
    return (s.get('assistant_notes') or '').strip(), s.get('assistant_notes_at') or ''

def _notes_block(store) -> str:
    n, at = notes(store)
    return (f"YOUR NOTES FROM YOUR LAST CHECK ({_ts(at)}; yours - trust them, then rewrite them for the next check):\n{n}" if n
            else 'YOUR NOTES FROM YOUR LAST CHECK: (none yet - this is your first check, or the last one left none)')

def _notes(text: str) -> str:
    try: j = json.loads(re.sub(r'^```(json)?|```$', '', (text or '').strip(), flags=re.M))
    except ValueError: return ''
    return ' '.join(str(j.get('notes') or '').split())[:900] if isinstance(j, dict) else ''


# ── the post ─────────────────────────────────────────────────────────────────────────────────
def _public(i: dict) -> dict:
    try: a = json.loads(i.get('ActionJson') or '{}')
    except ValueError: a = {}
    return {'id': i['IdeaId'], 'key': i['Key'], 'kind': i['Kind'], 'text': i['Text'], 'why': a.pop('why', ''), 'action': a, 'status': i.get('Status')}


def reviewed(cands: list, say: list, today: str, open_: str, said: str, model: bool) -> dict:
    """What this post was built from, so the owner can judge it: the candidates by kind, the ones it
    looked at and let go (with their facts), how much of the day and the open work it read, how many
    of its own lines it was told not to repeat. Stored on the post (Brief.reviewed) and written
    under it in plain text."""
    kept = {s_['key'] for s_ in say}
    n = lambda txt: 0 if txt.startswith('(') else txt.count('\n') + 1
    by = {}
    for c in cands: by[c['kind']] = by.get(c['kind'], 0) + 1
    return {'candidates': by, 'skipped': [{'key': c['key'], 'kind': c['kind'], 'facts': c['facts']} for c in cands if c['key'] not in kept],
            'today': n(today), 'open': n(open_), 'said': n(said), 'model': model}


def _footer(r: dict) -> str:
    kinds = ', '.join(f"{v} {k}" for k, v in r['candidates'].items()) or 'no candidates'
    skip = f"; let go: {len(r['skipped'])}" if r['skipped'] else ''
    return (f"Reviewed: {kinds}{skip} - {r['today']} message(s) from today, {r['open']} open task(s), {r['said']} line(s) already said"
            + ('' if r['model'] else " - no model: the facts in the hub's own words"))


def run(store, llm=None, force: bool = False, instruction: str = None) -> dict:
    """One post. The Reports tab's scheduler calls this when the 'Assistant' report is due
    (reports.run_report_source) and its "Run now" calls it forced; the instruction is the report's
    editable prompt. Deleting or switching off that report is the off switch - a forced run still
    answers. Posts nothing when nothing is new."""
    c = cfg(store); now = datetime.now()
    src = source(store)
    if not force and not (src and src.get('Active')): return {'ran': False, 'said': 0}
    if instruction is None and src: instruction = (src['cfg'].get('ai_prompt') or '').strip() or None
    store.set_setting('assistant_last_run', now.isoformat(timespec='seconds'), 'assistant')
    state = {i['Key']: i for i in store.list_ideas()}
    cands = [x for x in candidates(store, c) if fresh(state, x, now)]
    if llm is None:
        from .llm import build_llm
        try: llm = build_llm(store)
        except Exception as e:
            logger.debug(f'assistant: no model - {e}'); llm = None
    used, note = bool(llm and 'idea' in c['producers']), ''
    if used:
        try: say, note = think(store, cands, llm, instruction, c['max'])
        except Exception as e:
            logger.warning(f'assistant: the model pass failed, posting the facts alone - {e}'); say, used = cands[:c['max']], False
    else: say = cands[:c['max']]          # no model: the facts still stand, in the hub's own words
    # the note outlives the post: a quiet check leaves one too, so the next check starts where this one stopped
    if note:
        store.set_setting('assistant_notes', note, 'assistant'); store.set_setting('assistant_notes_at', now.strftime('%Y-%m-%d %H:%M:%S'), 'assistant')
    say = [s | {'why': s.get('why') or s.get('facts') or ''} for s in say if fresh(state, s, now)]   # a model echoing a dismissed key changes nothing
    rv = reviewed(cands, say, _today(store), _open(store), _said(store), used) | {'notes': note}
    if not say: return {'ran': True, 'said': 0, 'reviewed': rv}
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    rows = [store.upsert_idea(s | {'action': (s.get('action') or {}) | {'why': s['why']}}, stamp) for s in say]
    body = ('\n'.join(f"- {i['Text']}\n    why: {s_['why']}" for i, s_ in zip(rows, say)) + '\n\n' + _footer(rv)
            + (f"\nNote to my next check: {note}" if note else ''))
    subj = rows[0]['Text'][:90] + (f' (+{len(rows) - 1} more)' if len(rows) > 1 else '')
    mid = store.add_message({'TaskId': None, 'ExternalId': f'assistant:{stamp}', 'ConversationId': 'assistant', 'Channel': CHANNEL,
                             'SourceName': 'Assistant', 'Subject': subj, 'FromName': 'Assistant', 'SentAt': stamp,
                             'BodyText': body, 'Status': 'feed'})
    store.add_route(mid, None, 'feed', None, "the assistant's post: what it noticed and what it would do - each line has its buttons on the panel",
                    [], 'assistant')
    store.set_brief(mid, json.dumps({'ideas': [_public(i) for i in rows], 'reviewed': rv}))
    store.set_ideas_message([i['IdeaId'] for i in rows], mid)
    store.audit('message', mid, 'assistant_post', 'assistant', 'agent', {'ideas': len(rows)})
    logger.info(f'assistant: posted {len(rows)} idea(s) as message {mid}')
    return {'ran': True, 'said': len(rows), 'message_id': mid, 'reviewed': rv}


# ── the buttons ──────────────────────────────────────────────────────────────────────────────
def nudge(store, mid: int, why: str, actor: str = 'owner', llm=None) -> dict:
    """The chase, drafted in the owner's voice and parked in Review - never sent by itself."""
    from .ingest import task_from_message
    from . import responder
    m = store.get_message(mid)
    if not m: raise ValueError(f'no message {mid}')
    tid = m.get('TaskId') or task_from_message(store, mid, actor, 'reply')
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): store.update_task(tid, {'Status': 'waiting'}, actor)
    rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                            'Reason': f'follow-up the assistant suggested: {why[:160]}'})
    try: responder.write_draft(store, tid, rid, actor=actor, llm=llm, nudge=why)
    except Exception as e: logger.warning(f'follow-up draft failed for review {rid}: {e}')   # Review keeps the empty draft; 'Draft with AI' retries
    store.add_comment(tid, 'assistant', 'agent', f'FOLLOW-UP\n{why}\nThe chase is drafted in Review - approving sends it.')
    return {'taskId': tid, 'ref': task_ref(tid), 'reviewId': rid}


def act(store, idea_id: int, verb: str, actor: str = 'owner', llm=None, days: int = 1, learn_async=None) -> dict:
    """One click on the panel. followup / task DO the thing and close the idea; dismiss and snooze
    are verdicts (dismiss teaches LEARNED.md which nudges this owner never wants); done says the
    owner handled it themselves."""
    i = store.get_idea(idea_id)
    if not i: raise ValueError(f'no idea {idea_id}')
    try: a = json.loads(i.get('ActionJson') or '{}')
    except ValueError: a = {}
    out = {'ideaId': idea_id, 'verb': verb}
    if verb == 'followup':
        if not a.get('mid'): raise ValueError('this idea is not about a message, so there is nothing to follow up on')
        out |= nudge(store, a['mid'], i['Text'], actor, llm)
    elif verb == 'task':
        if not a.get('mid'): raise ValueError('this idea is not about a message, so there is nothing to make a task from')
        from . import ingest
        tid = ingest.task_from_message(store, a['mid'], actor, 'coding')
        if a.get('title'): store.update_task(tid, {'Title': str(a['title'])[:200]}, actor)
        if store.get_settings().get('coder_auto_enabled') == '1': ingest._spawn(ingest._auto_code, store, tid)
        out |= {'taskId': tid, 'ref': task_ref(tid)}
    elif verb == 'snooze':
        until = (datetime.now() + timedelta(days=max(1, int(days or 1)))).strftime('%Y-%m-%d %H:%M:%S')
        store.set_idea_status(idea_id, 'snoozed', actor, until)
        store.audit('idea', idea_id, verb, actor, detail={'until': until})
        return out | {'until': until}
    elif verb not in ('dismiss', 'done'): raise ValueError(f'unknown verb: {verb}')
    store.set_idea_status(idea_id, 'dismissed' if verb == 'dismiss' else 'done', actor)
    if verb == 'dismiss':
        from . import learn
        ev = f"idea{idea_id}: the owner dismissed the assistant's {i.get('Kind')} suggestion \"{i['Text'][:200]}\" - not worth their eye"
        if learn_async: learn_async(learn.learn_from, store, ev)
        else: learn.learn_from(store, ev)
    store.audit('idea', idea_id, verb, actor, detail={'kind': i.get('Kind')})
    return out

