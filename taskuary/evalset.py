"""The triage dataset: what really arrived, what triage did, what the owner then said.

"The triage is always wrong even after memory" is a claim about a rate, and nothing measured
the rate. Every owner verdict - Not our task, Not a task, a reply approved or edited, a filed
item promoted to a task - is a labelled example already sitting in the database; this module
turns them into cases and puts the two things next to each other that the funnel never sees
together: the classifier's call and the owner's.

Three uses, same rows:
  build     every inbound message with a definitive owner verdict (plus the untouched ones,
            weakly labelled with the call the owner let stand) -> ~/.taskuary/eval/triage_cases.jsonl,
            FULL TEXT, local, private
  share     the same cases with the people and the prose taken out - pseudonymous addresses,
            redacted subjects, no body at all - so a set can
            leave the machine (tests/data/triage_cases.jsonl, which the tests replay)
  evaluate  run the CONFIGURED classifier over the local cases, with the thread and the
            standing notes it would have had, and print accuracy, the confusion table, and
            how it does when a colleague had already replied - the number that was missing
  ablate    the same, four times: no memory / the notes that existed when each message
            arrived / every note today / notes + LEARNED.md - so "memory makes it better"
            is a measured claim (MEMORY_ARMS), not a felt one

A case carries the thread AS IT STOOD when the message arrived (who had spoken, whether one of
them was the owner) and, for mail ingested since RecipientsJson existed, the To/Cc relationship.
"""
import json, re, time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from . import words
from .routing import norm_subject
from .triage import addressed_to_you
from .categories import route_intent

LABELS = ('task', 'reply_only', 'fyi')
RETRIES = 2                  # a model call that fails or garbles is retried this often before it counts as unusable
ACCEPT_AFTER_DAYS = 3        # an untouched triage call this old is taken as accepted (weakly)


# ── labels: what the owner said ─────────────────────────────────────────────────────────
ANSWERED_WITHIN_DAYS = 2     # a "no reply" followed by the owner's own line in the channel this soon = answered there


def _labels(store, mine=()) -> dict:
    """MessageId -> (label, source, weak). Explicit verdicts first; an untouched call the owner
    let stand for ACCEPT_AFTER_DAYS is a weak label - agreement by silence, not by hand.

    "No reply" is two verdicts wearing one button. Seven of eleven were followed within hours by
    the owner's OWN line in the same chat - they answered in Teams and dismissed the draft - so
    the ask WAS a reply_only and triage had it right; scored as fyi, the funnel looked wrong for
    doing its job. The owner's later lines on the conversation tell the two apart."""
    out = {}
    q = store._rows
    me = tuple(a.lower() for a in mine if a)
    def answered_in_channel(mid):
        m = store.get_message(mid) or {}
        if not m.get('ConversationId') or not m.get('SentAt'): return False
        ph = ','.join('?' * len(me)) or "''"
        return bool(q(f"SELECT 1 FROM message WHERE ConversationId=? AND SentAt>? AND SentAt<=datetime(?, '+{ANSWERED_WITHIN_DAYS} days') "
                     f"AND (FromName='You' OR Status='context' OR Direction='out' OR lower(FromEmail) IN ({ph})) LIMIT 1",
                     (m['ConversationId'], m['SentAt'], m['SentAt'], *me)))
    for r in q("SELECT MessageId, Reason FROM route WHERE RoutedBy='owner' AND Decision='ignore' ORDER BY RouteId"):
        why = (r['Reason'] or '').lower()
        src = 'owner:not_ours' if why.startswith('not ours') else 'owner:not_a_task' if why.startswith('not a task') else 'owner:nothing_to_do'
        out[r['MessageId']] = ('fyi', src, False)
    for r in q("SELECT r.MessageId, t.Kind FROM route r LEFT JOIN task t ON t.TaskId=r.TaskId "
               "WHERE r.RoutedBy='owner' AND r.Decision='create' ORDER BY r.RouteId"):
        out[r['MessageId']] = ('reply_only' if r['Kind'] == 'reply' else 'task', 'owner:promoted', False)
    for r in q("SELECT MessageId, Status FROM review WHERE DecidedBy='owner' AND MessageId IS NOT NULL "
               "AND Status IN ('approved','edited','no_reply') ORDER BY ReviewId"):
        if r['Status'] == 'no_reply':
            out[r['MessageId']] = (('reply_only', 'review:no_reply_answered_in_channel', False) if answered_in_channel(r['MessageId'])
                                   else ('fyi', 'review:no_reply', False))
        else: out[r['MessageId']] = ('reply_only', f"review:{r['Status']}", False)
    cutoff = (datetime.now() - timedelta(days=ACCEPT_AFTER_DAYS)).isoformat(sep=' ', timespec='seconds')
    for r in q("SELECT m.MessageId, m.Status, r.Reason, r.Decision FROM message m JOIN route r ON r.MessageId=m.MessageId "
               "WHERE r.RoutedBy IN ('router','triage') AND m.CreatedAt < ? ORDER BY r.RouteId", (cutoff,)):
        if r['MessageId'] in out: continue
        said = route_intent(r['Reason'])
        if r['Decision'] == 'file' and said: out[r['MessageId']] = ('fyi', 'accepted', True)
        elif r['Decision'] == 'create' and said and r['Status'] == 'routed': out[r['MessageId']] = (said, 'accepted', True)
    return out


def _priority_labels(store) -> dict:
    """MessageId -> the priority the OWNER set by hand on the task that mail made (their last word on it), in the three words - the
    labels that say whether triage's regular / important / urgent matches the owner (the owner, 2026-10-25). Only the first inbound
    mail of a task carries it: the later ones only joined."""
    from .processing_order import level
    out = {}
    for a in store._rows("SELECT EntityId, Detail FROM audit WHERE EntityType='task' AND Action='priority' AND Actor='owner' ORDER BY Id"):
        try: to = (json.loads(a.get('Detail') or '{}') or {}).get('to')
        except ValueError: continue
        m = store._one("SELECT MessageId FROM message WHERE TaskId=? AND IFNULL(Direction,'in')<>'out' ORDER BY MessageId LIMIT 1", (a['EntityId'],))
        if m and to: out[m['MessageId']] = level(to)
    return out


def _triage_call(store) -> dict:
    """MessageId -> the funnel's OWN first call on it: decision, intent, and which layer spoke."""
    out = {}
    for r in store._rows("SELECT MessageId, Decision, Reason, RoutedBy FROM route WHERE RoutedBy != 'owner' ORDER BY RouteId"):
        if r['MessageId'] in out: continue
        out[r['MessageId']] = {'decision': r['Decision'], 'intent': route_intent(r['Reason']) or None, 'by': r['RoutedBy']}
    return out


def _owner_ruled_before(store, conv, before_mid) -> bool:
    if not conv: return False
    return bool(store._rows("SELECT 1 FROM route r JOIN message m ON m.MessageId=r.MessageId WHERE m.ConversationId=? "
                            "AND r.RoutedBy='owner' AND r.Decision='ignore' AND r.MessageId<? LIMIT 1", (conv, before_mid)))


# ── the cases ───────────────────────────────────────────────────────────────────────────
def _kind_of(email: str, name: str, mine: set, domains: set) -> str:
    e = (email or '').lower()
    if e in mine or (name or '').strip().lower() == 'you': return 'owner'
    return 'internal' if e.rsplit('@', 1)[-1] in domains else 'external'


def build(store, include_weak: bool = True) -> list:
    from .ingest import owner_addresses
    mine = owner_addresses(store)
    domains = {a.rsplit('@', 1)[-1] for a in mine if '@' in a}
    labels, calls, pri = _labels(store, mine), _triage_call(store), _priority_labels(store)
    rows = store._rows("SELECT * FROM message WHERE (Direction='in' OR Direction IS NULL) AND Status != 'skipped' ORDER BY MessageId")
    by_conv = {}
    for m in rows: by_conv.setdefault(m.get('ConversationId'), []).append(m)
    cases = []
    for m in rows:
        lab = labels.get(m['MessageId'])
        if not lab or (lab[2] and not include_weak): continue
        label, source, weak = lab
        # spoken order, not ingestion order: the owner's own chat lines arrive later as 'context'
        prior = sorted([p for p in by_conv.get(m.get('ConversationId'), []) if m.get('ConversationId')
                        and ((p['SentAt'] or '') < (m['SentAt'] or '') or ((p['SentAt'] or '') == (m['SentAt'] or '') and p['MessageId'] < m['MessageId']))],
                       key=lambda p: (p['SentAt'] or '', p['MessageId']))
        rec = json.loads(m.get('RecipientsJson') or 'null') or None
        msg = {'from_email': m.get('FromEmail'), 'source_name': m.get('SourceName'), 'to': (rec or {}).get('to'), 'cc': (rec or {}).get('cc')}
        cases.append({
            'id': f"m{m['MessageId']}", 'channel': m.get('Channel'), 'conv': m.get('ConversationId'), 'sent_at': m.get('SentAt'),
            'from': m.get('FromEmail'), 'from_name': m.get('FromName'),
            'from_kind': _kind_of(m.get('FromEmail'), m.get('FromName'), mine, domains),
            'subject': m.get('Subject') or '', 'body': m.get('BodyText') or '', 'own_text': m.get('OwnText') or '',
            'to': msg['to'], 'cc': msg['cc'],
            'addressed_to_you': addressed_to_you(msg, mine) if rec else None,
            'recipients': (len(msg['to'] or []) + len(msg['cc'] or [])) if rec else None,
            'thread_before': [{'from': p.get('FromEmail'), 'from_name': p.get('FromName'), 'sent_at': p.get('SentAt'),
                               'from_kind': _kind_of(p.get('FromEmail'), p.get('FromName'), mine, domains)} for p in prior[-12:]],
            'owner_ruled_thread_before': _owner_ruled_before(store, m.get('ConversationId'), m['MessageId']),
            'triage': calls.get(m['MessageId']) or {'decision': None, 'intent': None, 'by': None},
            'label': label, 'label_source': source, 'weak': weak, **({'priority_label': pri[m['MessageId']]} if m['MessageId'] in pri else {})})
    return cases


# ── leaving the machine ─────────────────────────────────────────────────────────────────
_TAIL = re.compile(r'\s+[-–—]\s+[^-–—]{1,60}$')
_CAP = re.compile(r"\b[A-Z][a-z]{2,}(?:'s)?\b")
_KEEP = {'Re', 'Fw', 'Fwd', 'The', 'For', 'And', 'Not', 'New', 'Please', 'Request', 'Update', 'Question', 'Report',
         'Reminder', 'Invoice', 'Payment', 'Budget', 'Review', 'Approval', 'Refund', 'Resident', 'Check', 'Rows',
         'Failed', 'Error', 'Process', 'Vendor', 'Create', 'Chat', 'With', 'Teams', 'Help', 'Security', 'App',
         'Collection', 'Import', 'File', 'Files', 'Payroll', 'System', 'Access', 'Password', 'Account', 'Meeting'}


def anonymise(cases: list) -> list:
    """People and prose out, signals in. Addresses become p<n>@<kind>.example (stable within
    the set, so a thread still reads as a thread); names become Person <n>; a subject keeps its
    common words and loses its proper nouns, its ' - Name, Name' tail and its digits; the body
    goes. It used to leave body_signals behind - what the keyword layer saw - and that layer is gone
    (2026-10-11). Conversation ids are renumbered."""
    people, convs = {}, {}
    def who(email, name, kind):
        key = (email or name or '').lower()
        if not key: return None, None
        if key not in people: people[key] = (f'p{len(people) + 1}@{kind}.example', f'Person {len(people) + 1}')
        return people[key]
    def conv(c): return convs.setdefault(c, f'c{len(convs) + 1}') if c else None
    def subject(s, names):
        # proper nouns first, on the original casing (a subject capitalises its names already),
        # then the people we know by name whatever their casing, then the tail and the digits
        s = _CAP.sub(lambda m: m.group(0) if m.group(0) in _KEEP else '[x]', _TAIL.sub(' - [x]', s or ''))
        for n in names:
            for part in re.split(r'[\s,]+', n or ''):
                if len(part) >= 3 and part.isalpha(): s = re.sub(rf'\b{re.escape(part)}\b', '[x]', s, flags=re.I)
        s = re.sub(r'(\[x\]\s*)+', '[x] ', re.sub(r'\d', '#', s))
        return norm_subject(s)
    out = []
    for c in cases:
        names = [c.get('from_name') or ''] + [p.get('from_name') or '' for p in c.get('thread_before') or []]
        em, nm = who(c.get('from'), c.get('from_name'), c['from_kind'])
        a = {**c, 'from': em, 'from_name': nm, 'conv': conv(c.get('conv')), 'subject': subject(c.get('subject') or '', names),
             'to': None, 'cc': None, 'body': None,
             'thread_before': [{**p, 'from': who(p.get('from'), p.get('from_name'), p['from_kind'])[0],
                                'from_name': who(p.get('from'), p.get('from_name'), p['from_kind'])[1]} for p in c.get('thread_before') or []]}
        out.append(a)
    return out


def write(path, cases: list) -> Path:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cases), encoding='utf-8')
    return p


def read(path) -> list:
    p = Path(path)
    return [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()] if p.exists() else []


# ── replaying one case against the funnel's own pieces ──────────────────────────────────
def thread_store(case: dict):
    """A MemoryStore holding the thread as it stood - what others_on_thread reads."""
    from .store import MemoryStore
    s = MemoryStore()
    for i, p in enumerate(case.get('thread_before') or []):
        s.add_message({'ExternalId': f"{case['id']}-prior-{i}", 'ConversationId': case.get('conv') or f"conv-{case['id']}",
                       'Channel': case.get('channel') or 'email', 'Subject': case.get('subject') or '',
                       'FromEmail': p.get('from'), 'FromName': p.get('from_name'), 'SentAt': p.get('sent_at'), 'Status': 'filed'})
    return s


def as_message(case: dict) -> dict:
    return {'external_id': case['id'], 'channel': case.get('channel') or 'email', 'conversation_id': case.get('conv') or f"conv-{case['id']}",
            'from_email': case.get('from'), 'from_name': case.get('from_name'), 'subject': case.get('subject') or '',
            'body': case.get('body') or '', 'sent_at': case.get('sent_at'), 'to': case.get('to'), 'cc': case.get('cc')}


class _AsOf:
    """The store as it stood when a message arrived: only the notes written BEFORE it. Every
    verdict note in the table was written about some message in this same set, so scoring with
    today's notes tells the classifier the answer for that very message - the honest question
    is whether the notes it HAD helped, and this is the view that answers it."""
    def __init__(self, store, until): self.s, self.until = store, until or ''
    def get_doc(self, name):
        """LEARNED.md without the verdict lines written after it (a verdict is a line there since 2026-10-27, memorylines.teach)."""
        d = self.s.get_doc(name)
        if name != 'learned' or not d: return d
        later = {str(r['Text'] or '').strip() for r in self.s._rows("SELECT Text FROM learned_history WHERE Action='said' AND At>=?", (self.until,))}
        return '\n'.join(l for l in d.splitlines() if l.strip() not in later)
    def __getattr__(self, k): return getattr(self.s, k)


MEMORY_ARMS = {                      # what the classifier is allowed to remember, per arm
    'bare':  dict(notes='none',  learned=False),   # the prompt and the message alone
    'asof':  dict(notes='asof',  learned=False),   # the notes that existed when the message arrived (what the funnel really had)
    'notes': dict(notes='today', learned=False),   # every note on file today, LEARNED.md withheld
    'today': dict(notes='today', learned=True),    # everything - what `evaluate` measures
    # ...and everything but the people lines (2026-10-25): triage reads who the sender is to the owner for the priority alone, and
    # this arm against `today` is what shows the intent does not get worse for it
    'nopeople': dict(notes='today', learned=True, people=False),
}


def evaluate(store, cases: list, llm, verbose=True, notes: str = 'today', learned: bool = True, system: str = None, people: bool = True) -> dict:
    """The configured classifier over the local (full-text) cases, told what the funnel would
    have told it. `notes` = 'today' (every standing note on file), 'asof' (only those written
    before the message arrived - see _AsOf) or 'none'; `learned` = whether LEARNED.md's
    promoted sections ride along (the doc has no history, so it is all or nothing). `system`
    replaces the install's TRIAGE.md for the run - how a wording change is scored before it ships."""
    from .ingest import others_on_thread, owner_addresses, relevant_notes
    from . import learned_cut
    from .routing import draft_task_fields
    from .triage import classify_intent, job_doc
    mine = owner_addresses(store)
    from .ingest import own_addresses
    me = own_addresses(store)          # the To/Cc signal is measured against the owner, not the shared boxes
    soul, job, system = store.doc('soul'), job_doc(store), (system if system is not None else store.doc('triage'))
    conf, rows, by_signal = Counter(), [], {'colleague_replied': Counter(), 'alone': Counter()}
    pconf = Counter()                  # (the owner's priority, triage's) where the owner set one by hand
    by_channel = {}
    for c in cases:
        if not c.get('body'): continue
        msg = as_message(c)
        thread = others_on_thread(thread_store(c), msg, mine)
        src = store if notes == 'today' else _AsOf(store, c.get('sent_at')) if notes == 'asof' else None
        ns, left = relevant_notes(src, [msg['from_email'] or ''], f"{msg['subject']} {msg['body']}"[:4000], subject=msg['subject']) if src else ([], 0)
        # the memory as the funnel reads it for THIS mail: what the owner cares about, and the people lines about whoever is on it
        lrn = (learned_cut.for_reader(store, 'triage', learned_cut.about_mail(msg), people=learned_cut.people_of(msg),
                                      sections=None if people else ('care',)) if learned else '')
        v = {'intent': 'fyi', 'why': 'a calendar invite'} if msg.get('invite') else None      # the funnel's only no-model verdict
        for attempt in range(RETRIES + 1):
            if v and not v.get('degraded'): break
            # a throttled or garbled call is not a verdict: try again before scoring it as one
            if attempt: time.sleep(2 * attempt)
            v = classify_intent(msg, llm=llm, soul=soul, job=job, thread=thread, learned=lrn, notes=ns,
                                notes_left=left, system=system, mine=me)
        # the funnel FILES an answer it cannot read (ingest: 'degraded' -> filed, never assumed
        # work); no model at all is no verdict - scored as such, never as a keyword guess (2026-10-11)
        got = 'fyi' if v.get('degraded') else v.get('intent') or 'unjudged'
        conf[(c['label'], got)] += 1
        if c.get('priority_label'): pconf[(c['priority_label'], v.get('priority') or 'regular')] += 1
        by_signal['colleague_replied' if thread.get('others_replied') else 'alone'][got == c['label']] += 1
        by_channel.setdefault(c.get('channel') or '?', Counter())[got == c['label']] += 1
        rows.append({'id': c['id'], 'label': c['label'], 'got': got, 'ok': got == c['label'], 'source': c['label_source'],
                     'channel': c.get('channel'), 'notes_seen': len(ns), 'why': v.get('why') or '', 'degraded': bool(v.get('degraded')),
                     # what the regex layer would make of a task (coding/general) - the second, unmeasured verdict
                     'regex_kind': draft_task_fields(msg)['kind'], 'model_kind': v.get('kind'),
                     # how hard and how sure the reader said it was (the router's judgements, 2026-10-25) - unlabelled, so shown, not scored
                     'difficulty': v.get('difficulty'), 'sure': v.get('sure'),
                     'others_replied': thread.get('others_replied') or [], 'subject': c.get('subject')})
    n = sum(conf.values()); ok = sum(v for (a, b), v in conf.items() if a == b)
    out = {'n': n, 'accuracy': (ok / n) if n else None, 'confusion': {f'{a}->{b}': v for (a, b), v in sorted(conf.items())},
           'degraded': sum(r['degraded'] for r in rows),
           'by_signal': {k: {'right': v[True], 'wrong': v[False]} for k, v in by_signal.items()},
           'by_channel': {k: {'right': v[True], 'wrong': v[False]} for k, v in sorted(by_channel.items())}, 'rows': rows,
           'priority': {'n': sum(pconf.values()), 'right': sum(v for (a, b), v in pconf.items() if a == b),
                        'confusion': {f'{a}->{b}': v for (a, b), v in sorted(pconf.items())}}}
    if verbose:
        print(f"{n} cases, accuracy {out['accuracy']:.0%}" + (f" ({out['degraded']} model answers unusable - scored as filed)" if out['degraded'] else '')
              if n else 'no cases with a body to classify')
        for k, v in out['confusion'].items(): print(f'  {k:22s} {v}')
        for k, v in out['by_signal'].items(): print(f"  {k:18s} right {v['right']:3d}  wrong {v['wrong']:3d}")
        for k, v in out['by_channel'].items(): print(f"  {k:18s} right {v['right']:3d}  wrong {v['wrong']:3d}")
        if out['priority']['n']: print(f"  priority (where you set one by hand): {out['priority']['right']} of {out['priority']['n']} {out['priority']['confusion']}")
        for r in rows:
            if not r['ok']: print(f"  MISS {r['id']:7s} owner={r['label']:10s} triage={r['got']:10s} [{r['source']}] {r['subject'][:60]}")
    return out


def jev_state(c: dict, thread: dict, soul: str = '', learned: str = '', notes=()) -> str:
    """One case as the decision model reads it: the owner's own judgement first (profile, learned, past verdicts), then the message
    and the thread signals the funnel would supply - the same evidence classify_intent hands the chat brain."""
    from .triage import sender_body
    body, _ = sender_body(c.get('body') or '', c.get('own_text') or None)
    sig = {k: thread[k] for k in ('others_replied', 'last_on_thread', 'recently_closed') if thread.get(k)}
    msg = json.dumps({'from': c.get('from_name') or c.get('from'), 'subject': c.get('subject'), 'addressed_to_you': c.get('addressed_to_you'),
                      'recipients': c.get('recipients'), **sig, 'body': body}, ensure_ascii=False, default=str)
    return (f"OWNER PROFILE:\n{soul[:2500]}\n\nLEARNED (patterns from their past verdicts):\n{learned}\n\n"
            "PAST VERDICTS on related mail:\n" + ('\n'.join(f'- {n}' for n in notes) or '(none)') + f"\n\nTHE MESSAGE:\n{msg}")


def evaluate_jev(store, cases: list, key: str, notes: str = 'asof', learned: bool = True, verbose=True) -> dict:
    """The same cases through the decision model, told what evaluate tells the chat brain: SOUL, LEARNED and the past verdicts
    ('asof' = only those on file when the message arrived)."""
    from . import jev
    from .ingest import others_on_thread, owner_addresses, relevant_notes
    from . import learned_cut
    mine, conf, rows = owner_addresses(store), Counter(), []
    soul, lrn = store.doc('soul') or '', learned_cut.for_reader(store, 'triage') if learned else ''
    for c in cases:
        if not c.get('body'): continue
        msg = as_message(c)
        thread = others_on_thread(thread_store(c), msg, mine)
        src = store if notes == 'today' else _AsOf(store, c.get('sent_at')) if notes == 'asof' else None
        ns, _ = relevant_notes(src, [msg['from_email'] or ''], f"{msg['subject']} {msg['body']}"[:4000], subject=msg['subject']) if src else ([], 0)
        try: r = jev.triage(key, jev_state(c, thread, soul, lrn, ns))
        except Exception as e: print(f"  ERR {c['id']}: {e}"); continue
        conf[(c['label'], r['intent'])] += 1
        rows.append({'id': c['id'], 'label': c['label'], 'got': r['intent'], 'ok': r['intent'] == c['label'], 'kind': r['kind'], 'p': r['p'],
                     'urgent': r['urgent'], 'notes_seen': len(ns), 'subject': c.get('subject')})
    n = len(rows); ok = sum(r['ok'] for r in rows)
    out = {'n': n, 'accuracy': ok / n if n else None, 'confusion': {f'{a}->{b}': v for (a, b), v in sorted(conf.items())},
           'kinds': dict(Counter(r['kind'] for r in rows if r['kind'])), 'rows': rows}
    if verbose:
        print(f"jev ({notes} notes, learned={learned}): {n} cases, accuracy {out['accuracy']:.0%}" if n else 'no cases')
        for k, v in out['confusion'].items(): print(f'  {k:22s} {v}')
        print('  kinds picked on tasks:', out['kinds'])
    return out


def ablate(store, cases: list, llm, arms=MEMORY_ARMS, verbose=True, save=None) -> dict:
    """Does memory help? The same cases under each MEMORY_ARMS setting, side by side."""
    # one arm at a time: four arms in parallel throttled an Azure deployment hard enough that a
    # third of one arm's calls failed and were scored as keyword fallbacks - a fast wrong number
    res = {k: evaluate(store, cases, llm, verbose=False, **kw) for k, kw in arms.items()}
    # saved BEFORE anything is printed: a run is minutes of LLM calls, and a printing bug once lost one
    if save:
        Path(save).parent.mkdir(parents=True, exist_ok=True)
        Path(save).write_text(json.dumps(res, indent=1, default=str), encoding='utf-8')
    if verbose:
        first = next(iter(res.values()))
        print(f"{'arm':7s} {'acc':>5s}  " + '  '.join(f'{ch:>8s}' for ch in sorted(first['by_channel'])))
        for k, r in res.items():
            chs = '  '.join(f"{v['right']:3d}/{v['right'] + v['wrong']:<4d}" for _, v in sorted(r['by_channel'].items()))
            opts = {k2: v2 for k2, v2 in arms[k].items() if k2 != 'system'}
            print(f"{k:7s} {r['accuracy']:5.0%}  {chs}   {opts}" + (f"  ({r['degraded']} unusable)" if r['degraded'] else ''))
        # where the arms DISAGREE is where memory acted - list those cases, verdict per arm
        got = {k: {r['id']: r for r in v['rows']} for k, v in res.items()}
        print('\ncases where memory changed the verdict (label | ' + ' | '.join(res) + '):')
        for r0 in first['rows']:
            vs = [got[k][r0['id']]['got'] for k in res]
            if len(set(vs)) > 1:
                print(f"  {r0['id']:7s} {r0['channel'] or '?':6s} {r0['label']:10s} | " + ' | '.join(f'{v:10s}' for v in vs) + f"  {r0['subject'][:50]}")
    return res


def run(store, what: str, home: Path, share_to=None, llm=None):
    """The CLI face: build | share | evaluate."""
    local = Path(home) / 'eval' / 'triage_cases.jsonl'
    if what == 'build':
        cases = build(store); write(local, cases)
        strong = sum(1 for c in cases if not c['weak'])
        print(f'{len(cases)} cases ({strong} owner-labelled, {len(cases) - strong} accepted-by-silence) -> {local}')
        return cases
    cases = read(local) or build(store)
    if what == 'share':
        p = write(share_to or Path.cwd() / 'tests' / 'data' / 'triage_cases.jsonl', anonymise(cases))
        print(f'{len(cases)} anonymised cases -> {p}  (review it before it leaves the machine)')
        return p
    if what == 'jev':
        row = next((c for c in store.list_connectors() if c['Type'] == 'typesafe' and c['Active']), None)
        if not row: raise SystemExit(f"no active TypeSafe Jev connector - add one under {words.name('ai')} first")
        key, strong = store.get_connector(row['ConnectorId'], with_secret=True)['Secret'] or '', [c for c in cases if not c['weak']]
        out = {k: evaluate_jev(store, strong, key, **kw) for k, kw in {'asof': dict(notes='asof'), 'bare': dict(notes='none', learned=False)}.items()}
        Path(home, 'eval').mkdir(parents=True, exist_ok=True); (Path(home) / 'eval' / 'jev_last.json').write_text(json.dumps(out, indent=1, default=str), encoding='utf-8')
        return out
    if what in ('evaluate', 'ablate'):
        if llm is None:
            from .llm import build_llm
            llm = build_llm(store, job='triage')
        if llm is None: raise SystemExit(f"no AI connector is configured - connect one under {words.name('ai')} first")
        strong = [c for c in cases if not c['weak']]
        return evaluate(store, strong, llm) if what == 'evaluate' else ablate(store, strong, llm, save=Path(home) / 'eval' / 'ablate_last.json')
    raise SystemExit(f'unknown evalset action {what!r}: build | share | evaluate | ablate | jev')
