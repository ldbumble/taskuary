"""The assistant on the Timeline: an hourly post of what it noticed and what it would do.

counsel.py briefs the owner on ONE message as it arrives. Nothing ever spoke up later - the reply
the owner sent on Monday and never heard back on, the meeting in two hours with five mails of
history behind it, the task that went quiet, the "bites in a week" line a brief wrote and nobody
read again. This is the voice that does: on its own clock it gathers what the hub can see
(followups: the owner wrote last and asked for something; prep: meetings ahead, with what came
before them; cold: work nothing has touched; ahead: the briefs' dated warnings; and its own ideas
from the day's mail), asks the model for its read GIVEN WHAT IT ALREADY SAID, and posts only what
is new as ONE row on the Timeline - each line with its buttons on the panel: Follow up (the chase
is drafted in the owner's voice, into Review), Make it a task (the agent starts), Not this, Snooze.

It never repeats itself: every idea has a key and a state (idea table). Said once with the same
facts is said; dismissed stays dismissed until the facts change; snoozed sleeps. Not this / Snooze
are verdicts, so LEARNED.md hears which kinds of nudges this owner never wants.

The pinned card at the top of the Timeline is deliberately NOT this: it is a quiet status line
(status()) - what is being worked, what waits on the owner, what is next on the calendar. The
recommendations live in the rows, where they can scroll away. Everything here is a setting
(assistant_*): the clock, the producers, the thresholds, the card.
"""
import json, re
from datetime import datetime, timedelta
from loguru import logger

from .store import task_ref

CHANNEL = 'assistant'
PRODUCERS = ('followup', 'prep', 'cold', 'ahead', 'idea')
DAYS = 30                  # how far back followups and briefs are read
MAX_SAY = 6                # lines per post - a post nobody reads to the end is a post that failed
POST_TOKENS = 700
# the owner's last word on a thread asked or promised something - that is what a chase is for
_ASKS = re.compile(r'\?|\b(let me know|could you|can you|would you|please (send|confirm|share|advise|review|check)|get back to me|'
                   r'by (monday|tuesday|wednesday|thursday|friday|eod|end of (day|week)|tomorrow|next week)|'
                   r'i will (send|get|have|follow|circle))\b', re.I)


def cfg(store) -> dict:
    s = store.get_settings()
    def n(k, d):
        try: return max(0, int(s.get(k) or d))
        except (TypeError, ValueError): return d
    raw = s.get('assistant_producers')
    prod = {p.strip() for p in (raw if raw is not None else ','.join(PRODUCERS)).split(',') if p.strip()}
    return {'on': s.get('assistant_enabled', '1') == '1', 'every': n('assistant_every_minutes', 60),
            'followup_h': n('assistant_followup_hours', 24), 'cold_d': n('assistant_cold_days', 3),
            'card': s.get('assistant_card', '1') == '1', 'producers': prod, 'last': s.get('assistant_last_run') or ''}


def _ts(s): return str(s or '')[:19].replace('T', ' ')
def _since(days): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
def _short(s, n=90): return ' '.join(str(s or '').split())[:n]
def _dt(s):
    try: return datetime.fromisoformat(_ts(s))
    except ValueError: return None


# ── the candidates: facts the hub can find without a model ───────────────────────────────────
def followups(store, hours: int) -> list:
    """Threads where the last word is the owner's, `hours` old or more, and that word asked for
    or promised something. Silence after a plain "thanks" is not a followup."""
    from .triage import strip_boilerplate
    cut = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    out = []
    for r in store.owner_last_words(_since(DAYS), cut):
        body = strip_boilerplate(str(r.get('BodyText') or ''))
        if not _ASKS.search(body): continue
        inbound = store.last_inbound_in(r['ConversationId'])
        if not inbound: continue                                    # nothing of theirs to answer under
        who = inbound.get('FromName') or inbound.get('FromEmail') or 'them'
        sent = _dt(r['SentAt']) or datetime.now()
        days = max(1, int((datetime.now() - sent).total_seconds() // 86400))
        out.append({'key': f"followup:{r['ConversationId']}", 'kind': 'followup', 'sig': _ts(r['SentAt']),
                    'facts': (f"You wrote {who} on {_ts(r['SentAt'])[:10]} re \"{_short(r.get('Subject'), 70)}\": \"{_short(body, 160)}\" "
                              f"- nothing has come back in {days} day(s)."),
                    'text': f"No answer from {who} in {days} day{'s' if days != 1 else ''} on \"{_short(inbound.get('Subject'), 60)}\" - follow up?",
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


def ahead(store) -> list:
    """What the briefs said would bite later - read once when they were written, never again."""
    out = []
    for r in store.briefed_messages(_since(DAYS)):
        try: b = json.loads(r.get('Brief') or '{}')
        except ValueError: continue
        for i, a in enumerate((b.get('ahead') or [])[:3]):
            out.append({'key': f"ahead:{r['MessageId']}:{i}", 'kind': 'ahead', 'sig': _short(a, 60),
                        'facts': f"From the brief on \"{_short(r.get('Subject'), 60)}\" ({r.get('FromName') or '?'}, {_ts(r['SentAt'])[:10]}): {a}",
                        'text': str(a).strip(), 'action': {'type': 'message', 'mid': r['MessageId'], 'tid': r.get('TaskId')}})
    return out


def candidates(store, c: dict) -> list:
    out = []
    for name, fn in (('followup', lambda: followups(store, c['followup_h'])), ('prep', lambda: prep(store)),
                     ('cold', lambda: cold(store, c['cold_d'])), ('ahead', lambda: ahead(store))):
        if name not in c['producers']: continue
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
            '"text": "<one line, under 30 words, first person: the fact and what I would do>", "mid": <the message id it is '
            'about, or null>, "task": "<idea:* only - a task title the owner could accept as-is, or null>"}]}.\n'
            f'At most {MAX_SAY} entries. Skip a candidate that is not worth the owner\'s eye (a standing standup needs no prep; a '
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


def parse(text: str, cands: list) -> list:
    """The model's list, kept honest: a key it invents must be idea:*, a candidate key keeps its
    kind and its buttons, and the text is the model's when it gave one."""
    try: j = json.loads(re.sub(r'^```(json)?|```$', '', (text or '').strip(), flags=re.M))
    except ValueError: return []
    by = {c['key']: c for c in cands}
    out, seen = [], set()
    for s in (j.get('say') or []) if isinstance(j, dict) else []:
        if not isinstance(s, dict): continue
        key, txt = str(s.get('key') or '').strip(), _short(s.get('text'), 240)
        if not key or key in seen or not txt: continue
        if key in by:
            out.append({**by[key], 'text': txt})
        elif key.startswith('idea:') and len(key) > 5:
            mid = s.get('mid') if isinstance(s.get('mid'), int) else None
            title = _short(s.get('task'), 120) or None
            act = {'type': 'task', 'mid': mid, 'title': title} if title and mid else {'type': 'message', 'mid': mid} if mid else {'type': 'note'}
            out.append({'key': key[:120], 'kind': 'idea', 'sig': txt[:60], 'text': txt, 'action': act})
        else: continue
        seen.add(key)
        if len(out) >= MAX_SAY: break
    return out


def think(store, cands: list, llm) -> list:
    """One call: COUNSEL.md's voice, the candidates, the day, what was already said."""
    doc = re.sub(r'<!--.*?-->', '', store.doc('counsel') or '', flags=re.S).strip()
    soul = store.doc('soul') or ''
    system = doc + CONTRACT + (f"\n\nWho the owner is (their own document; its reply rules are for text sent to OTHERS):\n{soul[:1500]}" if soul else '')
    user = ('CANDIDATES:\n' + ('\n'.join(f"[{c['key']}] {c['facts']}" for c in cands) or '(none)')
            + f"\n\nARRIVED TODAY:\n{_today(store)}\n\nOPEN WORK:\n{_open(store)}\n\nALREADY SAID (never repeat):\n{_said(store)}")
    return parse(llm(system, user, max_tokens=POST_TOKENS), cands)


# ── the post ─────────────────────────────────────────────────────────────────────────────────
def due(c: dict, now: datetime) -> bool:
    last = _dt(c['last'])
    return not last or (now - last).total_seconds() >= c['every'] * 60


def _public(i: dict) -> dict:
    try: a = json.loads(i.get('ActionJson') or '{}')
    except ValueError: a = {}
    return {'id': i['IdeaId'], 'key': i['Key'], 'kind': i['Kind'], 'text': i['Text'], 'action': a, 'status': i.get('Status')}


def run(store, llm=None, force: bool = False) -> dict:
    """The clock's entry (server._poll_reports) and the panel's "Ask now". Gated by the switch and
    the cadence unless forced; never raises out of the poll. Posts nothing when nothing is new."""
    c = cfg(store); now = datetime.now()
    if not c['on'] or (not force and not due(c, now)): return {'ran': False, 'said': 0}
    store.set_setting('assistant_last_run', now.isoformat(timespec='seconds'), 'assistant')
    state = {i['Key']: i for i in store.list_ideas()}
    cands = [x for x in candidates(store, c) if fresh(state, x, now)]
    if llm is None:
        from .llm import build_llm
        try: llm = build_llm(store)
        except Exception as e:
            logger.debug(f'assistant: no model - {e}'); llm = None
    if llm and 'idea' in c['producers']:
        try: say = think(store, cands, llm)
        except Exception as e:
            logger.warning(f'assistant: the model pass failed, posting the facts alone - {e}'); say = cands[:MAX_SAY]
    else: say = cands[:MAX_SAY]           # no model: the facts still stand, in the hub's own words
    say = [s for s in say if fresh(state, s, now)]         # a model echoing a dismissed key changes nothing
    if not say: return {'ran': True, 'said': 0}
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    rows = [store.upsert_idea(s, stamp) for s in say]
    body = '\n'.join(f"- {i['Text']}" for i in rows)
    subj = rows[0]['Text'][:90] + (f' (+{len(rows) - 1} more)' if len(rows) > 1 else '')
    mid = store.add_message({'TaskId': None, 'ExternalId': f'assistant:{stamp}', 'ConversationId': 'assistant', 'Channel': CHANNEL,
                             'SourceName': 'Assistant', 'Subject': subj, 'FromName': 'Assistant', 'SentAt': stamp,
                             'BodyText': body, 'Status': 'feed'})
    store.add_route(mid, None, 'feed', None, "the assistant's post: what it noticed and what it would do - each line has its buttons on the panel",
                    [], 'assistant')
    store.set_brief(mid, json.dumps({'ideas': [_public(i) for i in rows]}))
    store.set_ideas_message([i['IdeaId'] for i in rows], mid)
    store.audit('message', mid, 'assistant_post', 'assistant', 'agent', {'ideas': len(rows)})
    logger.info(f'assistant: posted {len(rows)} idea(s) as message {mid}')
    return {'ran': True, 'said': len(rows), 'message_id': mid}


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


# ── the pinned card: status, not advice ──────────────────────────────────────────────────────
def status(store) -> dict:
    c = cfg(store)
    live = {r['TaskId']: r.get('AgentName') or 'agent' for r in store.running_runs()}
    try:
        from . import terminal as term
        live.update({t['taskId']: t.get('agent') or t.get('label') or 'coder' for t in term.live_sessions(tail=0) if t.get('taskId')})
    except Exception:
        pass
    act_ = [t for t in store.list_tasks(active_only=True) if t.get('Status') in ('open', 'in_progress', 'waiting')]
    row = lambda t: {'tid': t['TaskId'], 'ref': task_ref(t['TaskId']), 'title': t.get('Title')}
    working = [row(t) | {'agent': live[t['TaskId']]} for t in act_ if t['TaskId'] in live]
    waiting = [row(t) for t in act_ if t['TaskId'] not in live and (t.get('Status') == 'waiting' or t.get('ReviewStatus') == 'pending')]
    meetings = []
    try:
        from . import calendar as cal
        meetings = (cal.upcoming(store, hours=36).get('events') or [])[:3]
    except Exception:
        pass
    return {'card': c['card'], 'enabled': c['on'], 'every': c['every'], 'last_run': c['last'],
            'working': working, 'waiting': waiting, 'open': len([t for t in act_ if t['TaskId'] not in live]),
            'reviews': len(store.list_reviews('pending')), 'meetings': meetings, 'ideas': len(store.list_ideas('open'))}
