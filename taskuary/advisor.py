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
BACKGROUND = True        # the suite turns this off (tests/conftest.py): a judgement runs only when a test asks for it inline
def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def key_of(target_kind: str, target_id) -> str: return f"{'task' if target_kind == 'task' else 'msg'}:{int(target_id)}"
def target_of(store, key: str):
    """A rail key -> (target kind, id), or None for a key with nothing to advise on (a connection, a meeting, a batch)."""
    m = re.match(r'^(task|agent|wrap|msg|report):(\d+)$', str(key or ''))
    if m: return ('task' if m.group(1) in ('task', 'agent', 'wrap') else 'message', int(m.group(2)))
    if str(key or '').startswith('processing:'):
        # the inventory's key names an ITEM; its members say what it is made of (a task outranks its mail rows)
        try:
            with store._processing_read() as cur:
                hit = store._processing_read_target(cur, key)
                rows = cur.execute("SELECT EntityKind, LocalId FROM processing_member WHERE ItemId=? AND RetiredAt IS NULL", (hit[0],)).fetchall() if hit else []
        except Exception: rows = []
        for kind in ('task', 'message'):
            m = next((r for r in rows if r['EntityKind'] == kind), None)
            if m: return (kind, int(m['LocalId']))
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
    "and you cite their ids. A ledger line says what HAPPENED, never whether it worked: \"continued\" means the session was started "
    "again, nothing more - never call it a success, and never say something was merged, sent or fixed unless a line says exactly that. "
    "The line is plain words for the owner: the ids go in \"evidence\" only, and the verb is named by its label, never its id. "
    "The reason must be the fact that makes THIS verb right, and it must hold up on its own: someone or an agent waiting on the "
    "owner is a reason to answer, never a reason to put it off. If none of the verbs offered is the right move, say nothing - a "
    "wrong suggestion is worse than none. The line is at most 80 characters, so it is read whole. "
    "Answer with JSON only:{\"verb\": \"<one of the verbs>\" or null, \"line\": \"<sentence>\" or \"\", "
    "\"evidence\": [\"<ids from the lines below>\"]}.")
WANT = {'type': 'object', 'properties': {'verb': {'type': ['string', 'null']}, 'line': {'type': 'string'},
                                         'evidence': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['verb', 'line', 'evidence']}
_EV = re.compile(r'^(out|mem|rv|task)\d+$')


def _item(store, target_kind, target_id):
    """The card the rail would show for this target - found by its task or message id, since the rail's key spelling is the
    processing inventory's (`processing:...`) in a real install and a legacy alias in a bare store."""
    from . import funnel
    if target_kind == 'task':
        t = store.get_task(target_id) or {}
        if not t or (t.get('Status') in ('done', 'dropped') and not store.resumable_session(target_id)): return None
    try:
        pile = funnel.pile(store, quiet=True).get('items') or []
        items = (funnel.full_items(store) or []) + pile                      # read items kept: the one on the table is often read
    except Exception: items = []
    f = 'tid' if target_kind == 'task' else 'mid'
    return next((i for i in items if i.get(f) == int(target_id)), None) or funnel.item_for_key(store, key_of(target_kind, target_id))


def habit(store, verb: str, item: dict) -> tuple:
    """(n, m): how often the owner's next move after THIS kind of moment was this verb - read from the ledger, never from the model.
    continue: stops that ended in a continue, over every stop that resolved; approve: replies sent as drafted, over every reply;
    close: closes that held, over every close that resolved. Any other verb has no count yet."""
    q = {'continue': ("SELECT Verdict AS v FROM outcome WHERE Kind='agent.stopped' AND ResolvedAt IS NOT NULL", lambda r: r['v'] == 'continued'),
         'approve': ("SELECT FactsJson AS f FROM outcome WHERE Kind='reply.sent' AND ResolvedAt IS NOT NULL", lambda r: json.loads(r['f'] or '{}').get('verb') == 'approve'),
         'close': ("SELECT Verdict AS v FROM outcome WHERE Kind='task.closed' AND ResolvedAt IS NOT NULL", lambda r: r['v'] == 'held'),
         'chase': ("SELECT FactsJson AS f FROM outcome WHERE Kind='reply.sent' AND ResolvedAt IS NOT NULL AND json_extract(FactsJson, '$.chase')=1",
                   lambda r: json.loads(r['f'] or '{}').get('answer_days') is not None)}.get(verb)
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


_ID = r'\b(?:out|mem|rv|task)\d+\b'
def plain(line: str, verb: str, label: str) -> str:
    """The owner reads the line, not the prompt: "You should stop_agent because out13 shows..." put the verb's id and the ledger's
    row id in the prompt box (2026-10-13). An id-shaped verb becomes its label; a cited id in brackets goes, one in the sentence
    becomes what it is."""
    t = re.sub(rf'\b{re.escape(verb)}\b', f'"{label}"', line) if '_' in verb else line
    t = re.sub(rf'\s*\((?:{_ID}[,\s]*)+\)', '', t)
    return ' '.join(re.sub(_ID, 'an earlier outcome', t).split())


def judge(store, event: str,target_kind: str, target_id, rev: str, tier: int = 1, llm=None) -> int:
    key = key_of(target_kind, target_id)
    def W(**kw): return _write(store, target_kind=target_kind, target_id=target_id, key=key, event=event, revision=rev, tier=tier, **kw)
    item = _item(store, target_kind, target_id)
    if not item: return W(dropped='no item')
    verbs = [c for c in concierge.chips_for(store, item) if c.get('verb') != 'next']
    if not verbs: return W(dropped='no actions')
    brain = llm or build_llm(store)
    if not brain: return W(dropped='no brain')
    have = row(store, target_kind, target_id, rev)                           # two events in one poll: the second finds the first's row
    if have and int(have.get('Tier') or 1) >= tier: return have['Id']
    model = getattr(brain, 'last_pick', None) or getattr(brain, 'model', None) or 'light'
    ans = ask_json(brain, SYSTEM, _prompt(store, event, item, verbs, tier, target_kind, target_id), want=WANT, max_tokens=200)
    d = ans.data if isinstance(ans.data, dict) else {}
    if not d: return W(dropped=f'no answer: {ans.error or "not an object"}'[:200], model=model)
    verb, line = d.get('verb'), ' '.join(str(d.get('line') or '').split())[:200]
    ev = [e for e in (d.get('evidence') or []) if isinstance(e, str) and _EV.match(e)][:6]
    if not verb or not line: return W(dropped='nothing to say', model=model, evidence=ev)
    hit = next((v for v in verbs if v['verb'] == verb), None)
    if not hit: return W(dropped=f'verb not offered: {verb}'[:120], model=model, line=line, evidence=ev)
    line = plain(line, verb, hit['label'])
    rid = W(line=line, verb=verb, label=hit['label'],count=habit(store, verb, item), evidence=ev, model=model)
    try:
        from . import live
        live.emit(live.ADVICE, key=key, target_kind=target_kind, target_id=int(target_id))
    except Exception: pass
    return rid


def _capped(store) -> bool:
    cap = int(store.get_setting(CAP_KEY, CAP_DEFAULT) or CAP_DEFAULT)
    since = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    n = (store._one("SELECT COUNT(*) AS n FROM advice WHERE CreatedAt>=? AND Model IS NOT NULL", (since,)) or {}).get('n') or 0
    return n >= cap


_INFLIGHT, _LOCK = set(), threading.Lock()      # (kind, id, revision, tier) being judged right now


def notice(store, event: str, target_kind: str, target_id, *, tier: int = 1, wait: bool = False, llm=None):
    """The one door every event calls. Never raises: a hook, a close or a poll must not fail for advice.
    Returns the row id when judged inline (tests, `wait=True`), None when skipped or sent to the background."""
    try:
        if str(store.get_setting(ON_KEY, '1') or '1') != '1' or not target_id: return None
        rev = revision(store, target_kind, target_id)
        have = row(store, target_kind, target_id, rev)
        if have and int(have.get('Tier') or 1) >= tier: return None             # judged at this revision already
        if _capped(store): return _write(store, target_kind=target_kind, target_id=target_id, key=key_of(target_kind, target_id), event=event, revision=rev, tier=tier, dropped='cap')
        mark = (target_kind, int(target_id), rev, int(tier))
        with _LOCK:
            if mark in _INFLIGHT: return None                                   # the same moment, judged on another thread
            _INFLIGHT.add(mark)
        def done():
            with _LOCK: _INFLIGHT.discard(mark)
        if wait:
            try: return judge(store, event, target_kind, target_id, rev, tier, llm)
            finally: done()
        if not BACKGROUND: done(); return None
        def go():
            try: judge(store, event, target_kind, target_id, rev, tier, llm)
            except Exception as e: logger.warning(f'advisor: {event} on {target_kind} {target_id} not judged - {e}')
            finally: done()
        threading.Thread(target=go, daemon=True, name=f'advise-{target_kind}-{target_id}').start()
    except Exception as e: logger.warning(f'advisor: {event} on {target_kind} {target_id} skipped - {e}')
    return None


def _payload(r: dict) -> dict:
    count = json.loads(r.get('CountJson') or '[0,0]')
    return {'key': r['Key'], 'line': plain(r['Line'] or '', r['Verb'] or '', r['Label'] or '') if r.get('Line') else r.get('Line'), 'verb': r['Verb'], 'label': r['Label'], 'pill': pill(r['Label'], count), 'count': count,
            'evidence': json.loads(r.get('EvidenceJson') or '[]'), 'revision': r['Revision'], 'tier': r['Tier'], 'at': r['CreatedAt']}


def _at_work(store, target_kind: str, target_id) -> bool:
    """An agent at work on the task is nothing for the owner to do. Its continue writes no event the revision sees until the
    prompt lands, so "the coder stopped and is waiting on you" stood over a coder already continued (the owner, 2026-10-13)."""
    if target_kind != 'task': return False
    from . import workerstate
    try: return workerstate.status(store, int(target_id)).get('state') == 'working'
    except Exception: return False


def for_key(store, key: str) -> dict:
    """What the prompt box shows for the item on the table: the row at the item's CURRENT revision, or nothing. A changed
    item drops its old pill by this one comparison - no cleanup pass. The item on the table earns the bigger read, once."""
    tgt = target_of(store, key)
    if not tgt or _at_work(store, *tgt): return {}
    rev = revision(store, *tgt); r = row(store, tgt[0], tgt[1], rev)
    if r and int(r.get('Tier') or 1) < 2: notice(store, r['Event'], tgt[0], tgt[1], tier=2)
    return _payload(r) if r and r.get('Verb') else {}


def notes(store, key: str, limit: int = 10) -> list:
    """The receipt: what it decided and what it dropped, per revision, with the evidence resolved to labels."""
    from .learnedgraph import _resolve
    tgt = target_of(store, key)
    if not tgt: return []
    out = []
    for r in rows(store, tgt[0], tgt[1], limit):
        ev = [{'id': e, **{k: v for k, v in _resolve(store, e).items() if k in ('kind', 'label')}} for e in json.loads(r.get('EvidenceJson') or '[]')]
        out.append({'at': r['CreatedAt'], 'event': r['Event'], 'tier': r['Tier'], 'line': r['Line'], 'verb': r['Verb'], 'label': r['Label'],
                    'pill': pill(r['Label'], json.loads(r.get('CountJson') or '[0,0]')) if r.get('Verb') else '', 'dropped': r['Dropped'],
                    'model': r['Model'], 'evidence': ev})
    return out


def block(store, item: dict) -> str:
    """The Advisor's line for the chat's system prompt, so 'why?' is answered from its evidence - a lookup, not a think."""
    d = for_key(store, (item or {}).get('key') or '') if item else {}
    if not d: return ''
    ev = ', '.join(d['evidence']) or 'the item itself'
    return (f"THE ADVISOR'S LINE on this item (if the owner asks why, this is the answer; the numbers are the ledger's): "
            f"\"{d['line']}\" - the pill offers {d['pill']} (verb {d['verb']}); evidence: {ev}.")
