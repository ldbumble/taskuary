"""The Advisor on the event (spec 2026-10-12, build step 3).

The clock pass (assistant.py) finds what only a window shows and files rows. This is the other entry point into the same
brain: when ONE item changes, one small prompt on the light gear says what to do about it - a verb the item already
carries, one line, the evidence ids - or nothing. The answer lands as an `advice` row stamped with the item's revision;
the prompt box reads it as ghost text and a pill that presses the card's own button; the rail never reads it.

Gates are on WHEN the model runs, never on whether: only on a state change (the revision), once per item per revision,
a per-hour cap, the light gear, a small prompt, the bigger read only for the item on the table, silence when nothing.
"""
import hashlib, json, re, threading
from datetime import datetime, timedelta
from loguru import logger
from . import concierge
from .llm import build_llm, ask_json

ON_KEY, CAP_KEY, CAP_DEFAULT = 'advisor_events', 'advisor_event_cap', 30
def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def key_of(target_kind: str, target_id) -> str: return f"{'task' if target_kind == 'task' else 'msg'}:{int(target_id)}"
def target_of(store, key: str):
    """A rail key -> (target kind, id), or None for a key with nothing to advise on (a connection, a meeting, a batch)."""
    m = re.match(r'^(task|agent|wrap|msg|report):(\d+)$', str(key or ''))
    if m: return ('task' if m.group(1) in ('task', 'agent', 'wrap') else 'message', int(m.group(2)))
    if str(key or '').startswith('processing:'):
        try:
            with store._processing_read() as cur: hit = store._processing_read_target(cur, key)
        except Exception: hit = None
        if hit and hit[1] in ('task', 'message'): return (hit[1], int(hit[2]))
    return None


def revision(store, target_kind: str, target_id) -> str:
    """The stamp advice is pinned to: the proposal's own context revision (messages and status) joined with what that
    revision leaves out and an event changes - the task's state and the newest word its agent said."""
    from .operations import context_revision
    base = context_revision(store, target_kind, target_id)
    if target_kind == 'task':
        t = store.get_task(target_id) or {}
        ev = store._one('SELECT MAX(Id) AS Id FROM worker_event WHERE TaskId=?', (int(target_id),)) or {}
        base += f"|{t.get('Status')}|{t.get('Assignee')}|{t.get('DueAt')}|{ev.get('Id')}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def _write(store, *, target_kind, target_id, key, event, revision, tier=1, line='', verb=None, label=None, count=(0, 0),
           evidence=(), model=None, dropped=None) -> int:
    return store._exec('INSERT INTO advice (TargetKind,TargetId,Key,Event,Revision,Tier,Line,Verb,Label,CountJson,EvidenceJson,Model,Dropped,CreatedAt) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (target_kind, int(target_id), key, event, revision, int(tier), line or '', verb, label, json.dumps(list(count)),
                        json.dumps(list(evidence)), model, dropped, _now()))
def row(store, target_kind: str, target_id, revision: str):
    return store._one('SELECT * FROM advice WHERE TargetKind=? AND TargetId=? AND Revision=? ORDER BY Tier DESC, Id DESC LIMIT 1',
                      (target_kind, int(target_id), revision))
def rows(store, target_kind: str, target_id, limit: int = 10) -> list:
    return store._rows('SELECT * FROM advice WHERE TargetKind=? AND TargetId=? ORDER BY Id DESC LIMIT ?', (target_kind, int(target_id), limit))


SYSTEM = (
    "You are the Advisor inside Taskuary, speaking as the owner's own assistant. ONE item just changed. Say what the owner should do "
    "with it now, as ONE of the VERBS OFFERED (exactly as written) and one short sentence in the second person that says why, naming "
    "the habit or the fact it rests on - or say nothing. Say nothing unless the owner's own habits (LEARNED), the outcome ledger or "
    "the item's own facts point at one verb. Never invent a number: the numbers in the ledger lines are the only ones you may use, "
    "and you cite their ids. Answer with JSON only: {\"verb\": \"<one of the verbs>\" or null, \"line\": \"<sentence>\" or \"\", "
    "\"evidence\": [\"<ids from the lines below>\"]}.")
WANT = {'type': 'object', 'properties': {'verb': {'type': ['string', 'null']}, 'line': {'type': 'string'},
                                         'evidence': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['verb', 'line', 'evidence']}
_EV = re.compile(r'^(out|mem|rv|task)\d+$')


def _item(store, target_kind, target_id):
    """The card the rail would show for this target - found by its task or message id, since the rail's key spelling is the
    processing inventory's (`processing:...`) in a real install and a legacy alias in a bare store."""
    from . import funnel
    try: items = funnel.pile(store, quiet=True).get('items') or []
    except Exception: items = []
    f = 'tid' if target_kind == 'task' else 'mid'
    return next((i for i in items if i.get(f) == int(target_id)), None) or funnel.item_for_key(store, key_of(target_kind, target_id))


def habit(store, verb: str, item: dict) -> tuple:
    """(n, m): how often the owner's next move after THIS kind of moment was this verb - read from the ledger, never from the model.
    continue: stops that ended in a continue, over every stop that resolved; approve: replies sent as drafted, over every reply;
    close: closes that held, over every close that resolved. Any other verb has no count yet."""
    q = {'continue': ("SELECT Verdict AS v FROM outcome WHERE Kind='agent.stopped' AND ResolvedAt IS NOT NULL", lambda r: r['v'] == 'continued'),
         'approve': ("SELECT FactsJson AS f FROM outcome WHERE Kind='reply.sent' AND ResolvedAt IS NOT NULL", lambda r: json.loads(r['f'] or '{}').get('verb') == 'approve'),
         'close': ("SELECT Verdict AS v FROM outcome WHERE Kind='task.closed' AND ResolvedAt IS NOT NULL", lambda r: r['v'] == 'held')}.get(verb)
    if not q: return (0, 0)
    rs = store._rows(q[0]); return (sum(1 for r in rs if q[1](r)), len(rs))
def pill(label: str, count) -> str:
    n, m = (list(count) + [0, 0])[:2]
    return f'{label} · {n} of {m} times' if m >= 2 else str(label or '')


def _prompt(store, event, item, verbs, tier, target_kind, target_id) -> str:
    from .learn import injectable
    from . import outcomes
    facts = {k: item.get(k) for k in ('ref', 'kind', 'lane', 'title', 'who', 'when', 'why', 'channel') if item.get(k)}
    lines = [f'EVENT: {event}', 'THE ITEM: ' + json.dumps(facts), f"PREVIEW: {str(item.get('preview') or '')[:300]}",
             'VERBS OFFERED: ' + ', '.join(f"{v['verb']} ({v['label']})" for v in verbs)]
    lrn = injectable(store.doc('learned') or '')
    if lrn.strip(): lines.append('LEARNED (the owner, from their own verdicts):\n' + lrn[:2000])
    led = [f"out{r['Id']}: {outcomes._sentence(store, r)}" for r in outcomes.rows_for(store, target_kind, target_id) if r.get('ResolvedAt')][:5]
    led += [f"{v['verb']}: this move {n} of {m} times" for v in verbs for n, m in [habit(store, v['verb'], item)] if m >= 2]
    if led: lines.append('THE OUTCOME LEDGER (what came of actions like this):\n' + '\n'.join(led))
    if tier >= 2:                                         # the bigger read, only for the item on the table
        from .counsel import dossier
        m = store.get_message(item.get('mid')) if item.get('mid') else None
        try: dos = dossier(store, {'from_email': (m or {}).get('FromEmail', ''), 'from_name': (m or {}).get('FromName', ''), 'subject': (m or {}).get('Subject', '')}, calendar=False) if m else ''
        except Exception: dos = ''
        if dos: lines.append('WHAT THE HUB KNOWS:\n' + dos[:1500])
        more = outcomes.evidence(store, (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'), limit=15)
        if more: lines.append('RECENT OUTCOMES:\n' + '\n'.join(more))
    return '\n\n'.join(lines)


def judge(store, event: str, target_kind: str, target_id, rev: str, tier: int = 1, llm=None) -> int:
    key = key_of(target_kind, target_id)
    def W(**kw): return _write(store, target_kind=target_kind, target_id=target_id, key=key, event=event, revision=rev, tier=tier, **kw)
    item = _item(store, target_kind, target_id)
    if not item: return W(dropped='no item')
    verbs = [c for c in concierge.chips_for(store, item) if c.get('verb') != 'next']
    if not verbs: return W(dropped='no actions')
    brain = llm or build_llm(store)
    if not brain: return W(dropped='no brain')
    model = getattr(brain, 'last_pick', None) or getattr(brain, 'model', None) or 'light'
    ans = ask_json(brain, SYSTEM, _prompt(store, event, item, verbs, tier, target_kind, target_id), want=WANT, need=('verb', 'line'), max_tokens=200)
    d = ans.data or {}
    if ans.error and not d: return W(dropped=f'no answer: {ans.error}'[:200], model=model)
    verb, line = d.get('verb'), ' '.join(str(d.get('line') or '').split())[:200]
    ev = [e for e in (d.get('evidence') or []) if isinstance(e, str) and _EV.match(e)][:6]
    if not verb or not line: return W(dropped='nothing to say', model=model, evidence=ev)
    hit = next((v for v in verbs if v['verb'] == verb), None)
    if not hit: return W(dropped=f'verb not offered: {verb}'[:120], model=model, line=line, evidence=ev)
    rid = W(line=line, verb=verb, label=hit['label'], count=habit(store, verb, item), evidence=ev, model=model)
    try:
        from . import live
        live.emit(live.ADVICE, key=key, target_kind=target_kind, target_id=int(target_id))
    except Exception: pass
    return rid


def _capped(store) -> bool:
    cap = int(store.get_setting(CAP_KEY, CAP_DEFAULT) or CAP_DEFAULT)
    since = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    n = (store._one("SELECT COUNT(*) AS n FROM advice WHERE CreatedAt>=? AND (Dropped IS NULL OR Dropped!='cap')", (since,)) or {}).get('n') or 0
    return n >= cap


def notice(store, event: str, target_kind: str, target_id, *, tier: int = 1, wait: bool = False, llm=None):
    """The one door every event calls. Never raises: a hook, a close or a poll must not fail for advice.
    Returns the row id when judged inline (tests, `wait=True`), None when skipped or sent to the background."""
    try:
        if str(store.get_setting(ON_KEY, '1') or '1') != '1' or not target_id: return None
        rev = revision(store, target_kind, target_id)
        have = row(store, target_kind, target_id, rev)
        if have and int(have.get('Tier') or 1) >= tier: return None             # judged at this revision already
        if _capped(store): return _write(store, target_kind=target_kind, target_id=target_id, key=key_of(target_kind, target_id), event=event, revision=rev, tier=tier, dropped='cap')
        if wait: return judge(store, event, target_kind, target_id, rev, tier, llm)
        def go():
            try: judge(store, event, target_kind, target_id, rev, tier, llm)
            except Exception as e: logger.warning(f'advisor: {event} on {target_kind} {target_id} not judged - {e}')
        threading.Thread(target=go, daemon=True, name=f'advise-{target_kind}-{target_id}').start()
    except Exception as e: logger.warning(f'advisor: {event} on {target_kind} {target_id} skipped - {e}')
    return None
