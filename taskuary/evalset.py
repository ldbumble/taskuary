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
            redacted subjects, the body reduced to the signals triage keys on - so a set can
            leave the machine (tests/data/triage_cases.jsonl, which the tests replay)
  evaluate  run the CONFIGURED classifier over the local cases, with the thread and the
            standing notes it would have had, and print accuracy, the confusion table, and
            how it does when a colleague had already replied - the number that was missing

A case carries the thread AS IT STOOD when the message arrived (who had spoken, whether one of
them was the owner) and, for mail ingested since RecipientsJson existed, the To/Cc relationship.
"""
import json, re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from .routing import norm_subject
from .triage import _ASK, _ACT, _FYI, addressed_to_you

LABELS = ('task', 'reply_only', 'fyi')
ACCEPT_AFTER_DAYS = 3        # an untouched triage call this old is taken as accepted (weakly)
_INTENT = re.compile(r'triage: (task|reply_only|fyi)')


# ── labels: what the owner said ─────────────────────────────────────────────────────────
def _labels(store) -> dict:
    """MessageId -> (label, source, weak). Explicit verdicts first; an untouched call the owner
    let stand for ACCEPT_AFTER_DAYS is a weak label - agreement by silence, not by hand."""
    out = {}
    q = store._rows
    for r in q("SELECT MessageId, Reason FROM route WHERE RoutedBy='owner' AND Decision='ignore' ORDER BY RouteId"):
        why = (r['Reason'] or '').lower()
        src = 'owner:not_ours' if why.startswith('not ours') else 'owner:not_a_task' if why.startswith('not a task') else 'owner:nothing_to_do'
        out[r['MessageId']] = ('fyi', src, False)
    for r in q("SELECT r.MessageId, t.Kind FROM route r LEFT JOIN task t ON t.TaskId=r.TaskId "
               "WHERE r.RoutedBy='owner' AND r.Decision='create' ORDER BY r.RouteId"):
        out[r['MessageId']] = ('reply_only' if r['Kind'] == 'reply' else 'task', 'owner:promoted', False)
    for r in q("SELECT MessageId, Status FROM review WHERE DecidedBy='owner' AND MessageId IS NOT NULL "
               "AND Status IN ('approved','edited','no_reply') ORDER BY ReviewId"):
        out[r['MessageId']] = (('fyi', 'review:no_reply', False) if r['Status'] == 'no_reply'
                               else ('reply_only', f"review:{r['Status']}", False))
    cutoff = (datetime.now() - timedelta(days=ACCEPT_AFTER_DAYS)).isoformat(sep=' ', timespec='seconds')
    for r in q("SELECT m.MessageId, m.Status, r.Reason, r.Decision FROM message m JOIN route r ON r.MessageId=m.MessageId "
               "WHERE r.RoutedBy IN ('router','triage') AND m.CreatedAt < ? ORDER BY r.RouteId", (cutoff,)):
        if r['MessageId'] in out: continue
        m = _INTENT.search(r['Reason'] or '')
        if r['Decision'] == 'file' and m: out[r['MessageId']] = ('fyi', 'accepted', True)
        elif r['Decision'] == 'create' and m and r['Status'] == 'routed': out[r['MessageId']] = (m.group(1), 'accepted', True)
    return out


def _triage_call(store) -> dict:
    """MessageId -> the funnel's OWN first call on it: decision, intent, and which layer spoke."""
    out = {}
    for r in store._rows("SELECT MessageId, Decision, Reason, RoutedBy FROM route WHERE RoutedBy != 'owner' ORDER BY RouteId"):
        if r['MessageId'] in out: continue
        m = _INTENT.search(r['Reason'] or '')
        out[r['MessageId']] = {'decision': r['Decision'], 'intent': m.group(1) if m else None, 'by': r['RoutedBy']}
    return out


def _owner_ruled_before(store, conv, before_mid) -> bool:
    if not conv: return False
    return bool(store._rows("SELECT 1 FROM route r JOIN message m ON m.MessageId=r.MessageId WHERE m.ConversationId=? "
                            "AND r.RoutedBy='owner' AND r.Decision='ignore' AND r.MessageId<? LIMIT 1", (conv, before_mid)))


# ── the cases ───────────────────────────────────────────────────────────────────────────
def body_signals(body: str) -> dict:
    """The body as the keyword layer sees it - enough to replay heuristic_intent without the prose."""
    b, low = (body or '').strip(), (body or '')[:600]
    return {'chars': len(b), 'question': b.rstrip().endswith('?'), 'ask': bool(_ASK.search(low)),
            'act': bool(_ACT.search(low)), 'fyi_marker': bool(_FYI.search(low))}


def _kind_of(email: str, name: str, mine: set, domains: set) -> str:
    e = (email or '').lower()
    if e in mine or (name or '').strip().lower() == 'you': return 'owner'
    return 'internal' if e.rsplit('@', 1)[-1] in domains else 'external'


def build(store, include_weak: bool = True) -> list:
    from .ingest import owner_addresses
    mine = owner_addresses(store)
    domains = {a.rsplit('@', 1)[-1] for a in mine if '@' in a}
    labels, calls = _labels(store), _triage_call(store)
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
            'subject': m.get('Subject') or '', 'body': m.get('BodyText') or '',
            'to': msg['to'], 'cc': msg['cc'],
            'addressed_to_you': addressed_to_you(msg, mine) if rec else None,
            'recipients': (len(msg['to'] or []) + len(msg['cc'] or [])) if rec else None,
            'thread_before': [{'from': p.get('FromEmail'), 'from_name': p.get('FromName'), 'sent_at': p.get('SentAt'),
                               'from_kind': _kind_of(p.get('FromEmail'), p.get('FromName'), mine, domains)} for p in prior[-12:]],
            'owner_ruled_thread_before': _owner_ruled_before(store, m.get('ConversationId'), m['MessageId']),
            'body_signals': body_signals(m.get('BodyText') or ''),
            'triage': calls.get(m['MessageId']) or {'decision': None, 'intent': None, 'by': None},
            'label': label, 'label_source': source, 'weak': weak})
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
    is replaced by body_signals. Conversation ids are renumbered."""
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
                if len(part) >= 3 and part.isalpha(): s = re.sub(rf'{re.escape(part)}', '[x]', s, flags=re.I)
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


def evaluate(store, cases: list, llm, verbose=True) -> dict:
    """The configured classifier over the local (full-text) cases, told what the funnel would
    have told it. Standing notes are today's, not that day's - the one thing this cannot replay."""
    from .ingest import decided_intent, others_on_thread, owner_addresses, relevant_notes
    from .learn import injectable
    from .triage import classify_intent
    mine = owner_addresses(store)
    soul, learned, system = store.doc('soul'), injectable(store.doc('learned') or ''), store.doc('triage')
    conf, rows, by_signal = Counter(), [], {'colleague_replied': Counter(), 'alone': Counter()}
    for c in cases:
        if not c.get('body'): continue
        msg = as_message(c)
        thread = others_on_thread(thread_store(c), msg, mine)
        notes, left = relevant_notes(store, [msg['from_email'] or ''], f"{msg['subject']} {msg['body']}"[:4000], subject=msg['subject'])
        got = (decided_intent(msg, mine) or classify_intent(msg, llm=llm, soul=soul, thread=thread, learned=learned, notes=notes,
                                                            notes_left=left, system=system, mine=mine))['intent']
        conf[(c['label'], got)] += 1
        by_signal['colleague_replied' if thread.get('others_replied') else 'alone'][got == c['label']] += 1
        rows.append({'id': c['id'], 'label': c['label'], 'got': got, 'ok': got == c['label'], 'source': c['label_source'],
                     'others_replied': thread.get('others_replied') or [], 'subject': c.get('subject')})
    n = sum(conf.values()); ok = sum(v for (a, b), v in conf.items() if a == b)
    out = {'n': n, 'accuracy': (ok / n) if n else None, 'confusion': {f'{a}->{b}': v for (a, b), v in sorted(conf.items())},
           'by_signal': {k: {'right': v[True], 'wrong': v[False]} for k, v in by_signal.items()}, 'rows': rows}
    if verbose:
        print(f"{n} cases, accuracy {out['accuracy']:.0%}" if n else 'no cases with a body to classify')
        for k, v in out['confusion'].items(): print(f'  {k:22s} {v}')
        for k, v in out['by_signal'].items(): print(f"  {k:18s} right {v['right']:3d}  wrong {v['wrong']:3d}")
        for r in rows:
            if not r['ok']: print(f"  MISS {r['id']:7s} owner={r['label']:10s} triage={r['got']:10s} [{r['source']}] {r['subject'][:60]}")
    return out


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
    if what == 'evaluate':
        if llm is None:
            from .llm import build_llm
            llm = build_llm(store)
        if llm is None: raise SystemExit('no AI connector is configured - connect one under Connectors -> AI first')
        return evaluate(store, [c for c in cases if not c['weak']], llm)
    raise SystemExit(f'unknown evalset action {what!r}: build | share | evaluate')
