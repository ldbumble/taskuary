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

from .routing import norm_subject
from .triage import _ASK, _ACT, _FYI, addressed_to_you

LABELS = ('task', 'reply_only', 'fyi')
RETRIES = 2                  # a model call that fails or garbles is retried this often before it counts as unusable
ACCEPT_AFTER_DAYS = 3        # an untouched triage call this old is taken as accepted (weakly)
_INTENT = re.compile(r'triage: (task|reply_only|fyi)')


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
    labels, calls = _labels(store, mine), _triage_call(store)
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


class _AsOf:
    """The store as it stood when a message arrived: only the notes written BEFORE it. Every
    verdict note in the table was written about some message in this same set, so scoring with
    today's notes tells the classifier the answer for that very message - the honest question
    is whether the notes it HAD helped, and this is the view that answers it."""
    def __init__(self, store, until): self.s, self.until = store, until or ''
    def list_memories(self, active_only=True):
        return [m for m in self.s.list_memories(active_only) if str(m.get('CreatedAt') or '') < self.until]
    def __getattr__(self, k): return getattr(self.s, k)


MEMORY_ARMS = {                      # what the classifier is allowed to remember, per arm
    'bare':  dict(notes='none',  learned=False),   # the prompt and the message alone
    'asof':  dict(notes='asof',  learned=False),   # the notes that existed when the message arrived (what the funnel really had)
    'notes': dict(notes='today', learned=False),   # every note on file today, LEARNED.md withheld
    'today': dict(notes='today', learned=True),    # everything - what `evaluate` measures
}


def evaluate(store, cases: list, llm, verbose=True, notes: str = 'today', learned: bool = True, system: str = None) -> dict:
    """The configured classifier over the local (full-text) cases, told what the funnel would
    have told it. `notes` = 'today' (every standing note on file), 'asof' (only those written
    before the message arrived - see _AsOf) or 'none'; `learned` = whether LEARNED.md's
    promoted sections ride along (the doc has no history, so it is all or nothing). `system`
    replaces the install's TRIAGE.md for the run - how a wording change is scored before it ships."""
    from .ingest import decided_intent, others_on_thread, owner_addresses, relevant_notes
    from .learn import injectable
    from .routing import draft_task_fields
    from .triage import classify_intent
    mine = owner_addresses(store)
    from .ingest import own_addresses
    me = own_addresses(store)          # the To/Cc signal is measured against the owner, not the shared boxes
    soul, system = store.doc('soul'), (system if system is not None else store.doc('triage'))
    lrn = injectable(store.doc('learned') or '') if learned else ''
    conf, rows, by_signal = Counter(), [], {'colleague_replied': Counter(), 'alone': Counter()}
    by_channel = {}
    for c in cases:
        if not c.get('body'): continue
        msg = as_message(c)
        thread = others_on_thread(thread_store(c), msg, mine)
        src = store if notes == 'today' else _AsOf(store, c.get('sent_at')) if notes == 'asof' else None
        ns, left = relevant_notes(src, [msg['from_email'] or ''], f"{msg['subject']} {msg['body']}"[:4000], subject=msg['subject']) if src else ([], 0)
        v = decided_intent(msg, mine)
        for attempt in range(RETRIES + 1):
            if v and not v.get('degraded'): break
            # a throttled or garbled call is not a verdict: try again before scoring it as one
            if attempt: time.sleep(2 * attempt)
            v = classify_intent(msg, llm=llm, soul=soul, thread=thread, learned=lrn, notes=ns,
                                notes_left=left, system=system, mine=me)
        # the funnel FILES an answer it cannot read (ingest: 'degraded' -> filed, never assumed
        # work); scored as the keyword fallback, a transient model error looked like a wrong verdict
        got = 'fyi' if v.get('degraded') else v['intent']
        conf[(c['label'], got)] += 1
        by_signal['colleague_replied' if thread.get('others_replied') else 'alone'][got == c['label']] += 1
        by_channel.setdefault(c.get('channel') or '?', Counter())[got == c['label']] += 1
        rows.append({'id': c['id'], 'label': c['label'], 'got': got, 'ok': got == c['label'], 'source': c['label_source'],
                     'channel': c.get('channel'), 'notes_seen': len(ns), 'why': v.get('why') or '', 'degraded': bool(v.get('degraded')),
                     # what the regex layer would make of a task (coding/general) - the second, unmeasured verdict
                     'regex_kind': draft_task_fields(msg)['kind'], 'model_kind': v.get('kind'),
                     'others_replied': thread.get('others_replied') or [], 'subject': c.get('subject')})
    n = sum(conf.values()); ok = sum(v for (a, b), v in conf.items() if a == b)
    out = {'n': n, 'accuracy': (ok / n) if n else None, 'confusion': {f'{a}->{b}': v for (a, b), v in sorted(conf.items())},
           'degraded': sum(r['degraded'] for r in rows),
           'by_signal': {k: {'right': v[True], 'wrong': v[False]} for k, v in by_signal.items()},
           'by_channel': {k: {'right': v[True], 'wrong': v[False]} for k, v in sorted(by_channel.items())}, 'rows': rows}
    if verbose:
        print(f"{n} cases, accuracy {out['accuracy']:.0%}" + (f" ({out['degraded']} model answers unusable - scored as filed)" if out['degraded'] else '')
              if n else 'no cases with a body to classify')
        for k, v in out['confusion'].items(): print(f'  {k:22s} {v}')
        for k, v in out['by_signal'].items(): print(f"  {k:18s} right {v['right']:3d}  wrong {v['wrong']:3d}")
        for k, v in out['by_channel'].items(): print(f"  {k:18s} right {v['right']:3d}  wrong {v['wrong']:3d}")
        for r in rows:
            if not r['ok']: print(f"  MISS {r['id']:7s} owner={r['label']:10s} triage={r['got']:10s} [{r['source']}] {r['subject'][:60]}")
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
    if what in ('evaluate', 'ablate'):
        if llm is None:
            from .llm import build_llm
            llm = build_llm(store)
        if llm is None: raise SystemExit('no AI connector is configured - connect one under Connectors -> AI first')
        strong = [c for c in cases if not c['weak']]
        return evaluate(store, strong, llm) if what == 'evaluate' else ablate(store, strong, llm, save=Path(home) / 'eval' / 'ablate_last.json')
    raise SystemExit(f'unknown evalset action {what!r}: build | share | evaluate | ablate')
