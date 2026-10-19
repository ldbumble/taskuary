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
from . import buttons, concierge
from .llm import build_llm, ask_json
L = buttons.label        # the prompt names a button by its one label (buttons.json)

ON_KEY, CAP_KEY, CAP_DEFAULT = 'advisor_events', 'advisor_event_cap', 30
BACKGROUND = True        # the suite turns this off (tests/conftest.py): a judgement runs only when a test asks for it inline
def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def key_of(target_kind: str, target_id) -> str: return f"{'task' if target_kind == 'task' else 'msg'}:{int(target_id)}"
def target_of(store, key: str):
    """A rail key -> (target kind, id), or None for a key with nothing to advise on (a connection, a meeting, a batch)."""
    m = re.match(r'^(task|agent|wrap|msg|report):(\d+)$', str(key or ''))
    if m: return ('task' if m.group(1) in ('task', 'agent', 'wrap') else 'message', int(m.group(2)))
    # a draft waiting for your yes is keyed by its review (funnel's review:N, in a bare store and the demo): advised as the
    # task it answers for, else the message - read as "nothing to advise on", every draft on the demo's rail had an empty bar
    m = re.match(r'^review:(\d+)$', str(key or ''))
    if m:
        r = store.get_review(int(m.group(1))) or {}
        return ('task', int(r['TaskId'])) if r.get('TaskId') else ('message', int(r['MessageId'])) if r.get('MessageId') else None
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
    # ...and every act on it: a line judged "Send" before the send failed stood over the failure, advising the same Send (2026-10-18);
    # one judged "Reply" before the reply WENT stood over "Sent" on the close-out, still saying the sender was waiting (2026-10-19)
    base += f"|{_acted(store, target_kind, target_id)}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def _acted(store, target_kind, target_id) -> str:
    """What the owner's acts left on the target: each draft - there or not, how it was decided, whether it went - and the newest
    operation that ran on it, done, failed or declined (a proposal still waiting for its yes is no act yet). DeliveryState alone
    skipped every NULL, so a reply sent with no delivery receipt (Status approved, DeliveryState NULL) changed nothing it saw."""
    col = 'TaskId' if target_kind == 'task' else 'MessageId'
    rv = store._one(f"SELECT GROUP_CONCAT(ReviewId || ':' || IFNULL(Status,'') || ':' || IFNULL(DeliveryState,''), ',') AS d FROM "
                    f"(SELECT * FROM review WHERE {col}=? ORDER BY ReviewId)", (int(target_id),)) or {}
    op = store._one("SELECT OpId, Status FROM operation WHERE TargetKind=? AND TargetId=? AND Status<>'proposed' ORDER BY rowid DESC LIMIT 1",
                    (target_kind, int(target_id))) or {}
    return f"{rv.get('d') or ''}/{op.get('OpId') or ''}:{op.get('Status') or ''}"


def _write(store, *, target_kind, target_id, key, event, revision, tier=1, line='', verb=None, label=None, count=(0, 0),
           evidence=(), model=None, dropped=None) -> int:
    return store._exec('INSERT INTO advice (TargetKind,TargetId,Key,Event,Revision,Tier,Line,Verb,Label,CountJson,EvidenceJson,Model,Dropped,CreatedAt) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (target_kind, int(target_id), key, event, revision, int(tier), line or '', verb, label, json.dumps(list(count)),
                        json.dumps(list(evidence)), model, dropped, _now()))
# A drop for an OUTSIDE reason is not a verdict on the item: with no AI, opening an item wrote "no brain" and the line never
# came once one was connected; 30 reads in an hour left every later item a "cap" for good (2026-10-17 audit). The next look
# tries again. "nothing to say", "verb not offered", "no item", "no actions" stand for the revision.
RETRY = ('no brain', 'cap', 'no answer')
def retryable(r) -> bool: return bool(r) and not r.get('Verb') and str(r.get('Dropped') or '').startswith(RETRY)
def _at(store, target_kind, target_id, revision, own=None) -> list:
    """The rows at this revision - only those written for the item whose keys are `own`, when given."""
    rs = store._rows('SELECT * FROM advice WHERE TargetKind=? AND TargetId=? AND Revision=? ORDER BY Id DESC', (target_kind, int(target_id), revision))
    return rs if own is None else [r for r in rs if r.get('Key') in own]
def row(store, target_kind: str, target_id, revision: str, own=None):
    """The row that stands at this revision: the newest with a verb at any tier - a later tier-2 drop sorted first by tier hid
    a good tier-1 line - else the newest verdict. Retryable drops are never it."""
    rs = _at(store, target_kind, target_id, revision, own)
    return next((r for r in rs if r.get('Verb')), None) or next((r for r in rs if not retryable(r)), None)


# ADVICE IS KEYED TO ITS ITEM: one task can stand on the rail twice - its draft (review:N) and its agent (agent:N) - and a line
# written for one, with a verb only that one's row carries, stood over the other (2026-10-18). A row belongs to the item it was
# judged as: its rail key, or a key that names that same item (its aliases: task:N for the processing inventory's key).
def keys_of(item: dict | None, key: str = None) -> set:
    return {k for k in (key, *((item or {}).get('key'), *((item or {}).get('aliases') or []))) if k}
def _own(store, tgt, key: str, rs: list) -> set:
    """The keys whose rows are `key`'s - read off the item only when a row at this revision was written under another key."""
    return {key} if all(r.get('Key') == key for r in rs) else keys_of(_item(store, *tgt, key=key), key)
def rows(store, target_kind: str, target_id, limit: int = 10) -> list:
    return store._rows('SELECT * FROM advice WHERE TargetKind=? AND TargetId=? ORDER BY Id DESC LIMIT ?', (target_kind, int(target_id), limit))


SYSTEM = (
    "You are the Advisor inside Taskuary, speaking as the owner's own assistant. ONE item just changed. Say what the owner should do "
    "with it now, as ONE of the VERBS OFFERED (exactly as written) and one short sentence in the second person that says why, naming "
    "the habit or the fact it rests on - or say nothing. Say nothing unless the owner's own habits (LEARNED), the outcome ledger or "
    "the item's own facts point at one verb. Never invent a number: the numbers in the ledger lines are the only ones you may use, "
    "and you cite their ids. A ledger line says what HAPPENED, never whether it worked: \"continued\" means the session was started "
    "again, nothing more - never call it a success, and never say something was merged, sent or fixed unless a line says exactly that. "
    "The line is plain words for the owner, who may never have written code: the ids go in \"evidence\" only, the verb is named by "
    "its label, never its id, and never a word from the item's own bookkeeping (lane, kind, triage, session, model, an event name). "
    "The reason must be the fact that makes THIS verb right, and it must hold up on its own: someone or an agent waiting on the "
    "owner is a reason to answer, never a reason to put it off. Ending an agent's session is right when its work is done or no "
    "longer wanted; when it has finished something for the owner to review or send, the move is the one that reviews or sends it. If none of the verbs offered is the right move, say nothing - a "
    "wrong suggestion is worse than none. The line is at most 80 characters, so it is read whole. "
    "Answer with JSON only:{\"verb\": \"<one of the verbs>\" or null, \"line\": \"<sentence>\" or \"\", "
    "\"evidence\": [\"<ids from the lines below>\"]}. "
    "EXCEPT when the EVENT is item.shown: the owner is looking at this item right now and is owed a next step, so pick the verb the "
    f"item's own facts make right (a person waiting on them: {L('reply')}; an agent asking them something: {L('answer_agent')}; nothing "
    f"for them to do: {L('close')} or {L('let_go')}; work an agent left: {L('continue')} or {L('approve')}; a draft waiting: {L('approve')}; "
    f"a reply already sent (an A REPLY WAS ALREADY SENT line) - sending never closes the task - and nothing left to do: {L('close')}, "
    "never an answer the sent reply already gave - someone is waiting only when they wrote again after it; a reply that failed to "
    "send: the fix offered with it) - whichever of those is "
    "OFFERED - and say why in plain words - say nothing only when no verb offered fits at all. "
    "WHEN SOMETHING FAILED (a WHAT FAILED line below), the owner is owed the way past it, at any event: say in plain words what went "
    "wrong, and pick the move that fixes it - the fix offered when there is one (it opens the place that fixes it); else a verb offered "
    "that gets round it; else, when nothing here can fix it, the one that makes a task to fix it. Never advise the act that failed again "
    "unchanged - unless the failure says the cause has passed - and never Send again when nobody knows whether the first send went.")
def _system(store) -> str:
    """SYSTEM plus the owner's own Voice section of COUNSEL: the Advisor's line sits in the same box as the chat's, so it
    speaks by the same rules - it never had them, and said "lane" and "session" to a finance user (2026-10-17 audit)."""
    from . import counsel
    try: voice = counsel.sections(counsel.load(store)).get(counsel.VOICE_HEAD, '').strip()
    except Exception: voice = ''
    return f"{SYSTEM}\n\nHOW THE LINE SPEAKS (the owner's own rules):\n{voice}" if voice else SYSTEM
# the event every item on the table gets, when no other event judged it at its current revision (Advisor audit, 2026-10-15)
SHOWN = 'item.shown'
WANT = {'type': 'object', 'properties': {'verb': {'type': ['string', 'null']}, 'line': {'type': 'string'},
                                         'evidence': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['verb', 'line', 'evidence']}
_EV = re.compile(r'^(out|mem|rv|task)\d+$')


def _item(store, target_kind, target_id, key: str = None):
    """The card the rail would show for this target - the one keyed `key` when asked for an item (keys_of), else found by its task
    or message id, since the rail's key spelling is the processing inventory's (`processing:...`) in a real install and a legacy
    alias in a bare store."""
    from . import funnel
    if target_kind == 'task':
        t = store.get_task(target_id) or {}
        if not t or (t.get('Status') in ('done', 'dropped') and not store.resumable_session(target_id)): return None
    try:
        pile = funnel.pile(store, quiet=True).get('items') or []
        items = (funnel.full_items(store) or []) + pile                      # read items kept: the one on the table is often read
    except Exception: items = []
    f = 'tid' if target_kind == 'task' else 'mid'
    mine = [i for i in items if i.get(f) == int(target_id)]
    return (next((i for i in mine if key and key in keys_of(i)), None) or next(iter(mine), None)
            or funnel.item_for_key(store, key_of(target_kind, target_id)))


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
# ...and what each count MEASURES, said so: "You chose Mark done 2 of 3 times in a moment like this" was read off closes that
# held and answers to nudges, counted over every item, not this kind of moment (2026-10-17 audit)
MEASURES = {'continue': 'You picked the work back up {n} of the last {m} times an agent stopped',
            'approve': 'You sent {n} of your last {m} drafts as written',
            'close': '{n} of the last {m} tasks you closed stayed closed',
            'chase': '{n} of your last {m} nudges got an answer'}
def says(verb: str, count) -> str:
    n, m = (list(count) + [0, 0])[:2]
    return MEASURES[verb].format(n=n, m=m) + '.' if verb in MEASURES and m >= 2 else ''
def pill(label: str, count) -> str:
    n, m = (list(count) + [0, 0])[:2]
    return f'{label} · {n} of {m} times' if m >= 2 else str(label or '')


def _prompt(store, event, item, verbs, tier, target_kind, target_id) -> str:
    from .learn import injectable
    from . import outcomes
    from . import funnel
    facts = {k: item.get(k) for k in ('ref', 'title', 'who', 'when', 'why', 'channel') if item.get(k)}
    # where it stands, in the rail's own words - a lane id handed over as-is came back in the line ("the lane is blocked")
    kinds = {k['key']: k['word'] for k in funnel._VOCAB['kinds']}
    stands = kinds.get(item.get('kind')) or funnel.LANE_WORDS.get(item.get('lane'), ('',))[0]
    if stands: facts['where it stands'] = stands
    lines = [f'EVENT: {event}', 'THE ITEM: ' + json.dumps(facts), f"PREVIEW: {str(item.get('preview') or '')[:300]}",
             'VERBS OFFERED: ' + ', '.join(f"{v['verb']} ({v['label']})" for v in verbs)]
    try: f = failure(store, item)
    except Exception as e: logger.debug(f'advisor: no failure read for {item.get("key")} - {e}'); f = None
    if f: lines.append(f"WHAT FAILED: {f['what']} - {f['why'] or 'no reason was given'}"
                       + (' (nobody knows whether it went: check before sending again)' if f.get('unknown') else '')
                       + (f". The fix offered: {f['fix']['label']}" if f.get('fix') else ''))
    try: sent = sent_line(store, target_kind, target_id)
    except Exception as e: logger.debug(f'advisor: no sent reply read for {item.get("key")} - {e}'); sent = ''
    if sent: lines.append(sent)
    if target_kind == 'task':
        # what the agent itself last said and is asking: the card's preview is the sender's mail, so five stops in a row were
        # judged "stop the agent" over an agent whose last words were "the reply above is ready for you to review and send"
        from . import workerstate
        try: st = workerstate.status(store, int(target_id))
        except Exception: st = {}
        if st.get('said'): lines.append('THE AGENT LAST SAID: ' + ' '.join(str(st['said']).split())[:600])
        asks = [r.get('text') for r in st.get('requests') or [] if r.get('text')]
        if asks: lines.append('THE AGENT IS ASKING: ' + ' | '.join(' '.join(str(q).split())[:200] for q in asks[:3]))
        # THE WHOLE STORY of a task that came back: the agent finished, the reply went, then new mail reopened it. Read from the card
        # alone ("paused ... ready to resume") it advised Continue for a reason that was not true, and never said what the new mail
        # wanted (the owner, 2026-10-14: "the advisor should just realize what's going on ... as long as it has full context")
        from . import continuity
        at = continuity.last_agent_turn(store, int(target_id))
        mail = continuity.mail_since(store, int(target_id), at) if at else []
        if mail:
            lines.append(f"NEW SINCE THE AGENT'S LAST TURN ({at}) - its saved conversation is from BEFORE these; {buttons.label('continue')} hands "
                         "them to it first:\n" + '\n'.join(f"- {m.get('FromName') or m.get('FromEmail')} ({m.get('CreatedAt')}): {m.get('Subject') or ''}"
                                                             f" - {' '.join(str(m.get('BodyText') or '').split())[:500]}" for m in mail[-3:]))
        t = store.get_task(int(target_id)) or {}
        try: todo = [c.get('text') for c in json.loads(t.get('Checklist') or '[]') if isinstance(c, dict) and not c.get('done') and c.get('text')]
        except ValueError: todo = []
        if todo: lines.append('STILL TO DO ON THE TASK: ' + ' | '.join(' '.join(str(x).split())[:160] for x in todo[:6]))
    lrn = injectable(store.doc('learned') or '')
    if lrn.strip(): lines.append('LEARNED (the owner, from their own verdicts):\n' + lrn[:2000])
    led = [f"out{r['Id']}: {outcomes._sentence(store, r)}" for r in outcomes.rows_for(store, target_kind, target_id) if r.get('ResolvedAt')][:5]
    led += [f"{v['label']}: {says(v['verb'], c)}" for v in verbs for c in [habit(store, v['verb'], item)] if says(v['verb'], c)]
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


def sent_line(store, target_kind, target_id) -> str:
    """WHAT WAS SENT, as evidence: the newest reply that went on the item, when, to whom, its words, and what came in since. The
    preview is the sender's ask, so with no word of the reply the line still said "Marcus is waiting for your clarifications"
    over a close-out reading Sent (2026-10-19) - the model reads whether anything is still owed; code only says what went."""
    r = store.sent_reply(task_id=int(target_id)) if target_kind == 'task' else store.sent_reply(message_id=int(target_id))
    if not r: return ''
    at = r.get('DecidedAt') or r.get('CreatedAt') or ''
    m = store.get_message(r['MessageId']) if r.get('MessageId') else None
    to = (m or {}).get('FromName') or (m or {}).get('FromEmail') or 'the sender'
    body = ' '.join(str(r.get('FinalText') or r.get('DraftText') or '').split())[:400]
    out = f'A REPLY WAS ALREADY SENT ({at}) to {to}: "{body}"'
    msgs = store.list_messages(int(target_id)) if target_kind == 'task' else [m] if m else []
    later = [x for x in msgs if x and str(x.get('Direction') or 'in') != 'out' and str(x.get('SentAt') or x.get('CreatedAt') or '') > str(at)]
    return out + ('\nWRITTEN TO THE OWNER SINCE: ' + ' | '.join(f"{x.get('FromName') or x.get('FromEmail')} ({x.get('SentAt') or x.get('CreatedAt')}): "
                                                            f"{' '.join(str(x.get('BodyText') or '').split())[:240]}" for x in later[-3:])
                  if later else '\nNOTHING HAS COME IN SINCE IT WENT.')


_ID = r'\b(?:out|mem|rv|task)\d+\b'
def plain(line: str, verb: str, label: str) -> str:
    """The owner reads the line, not the prompt: "You should stop_agent because out13 shows..." put the verb's id and the ledger's
    row id in the prompt box (2026-10-13). An id-shaped verb becomes its label; a cited id in brackets goes, one in the sentence
    becomes what it is."""
    t = re.sub(rf'\b{re.escape(verb)}\b', f'"{label}"', line) if '_' in verb else line
    t = re.sub(rf'\s*\((?:{_ID}[,\s]*)+\)', '', t)
    return ' '.join(re.sub(_ID, 'an earlier outcome', t).split())


def _offered(verbs: list, said: str):
    """The verb the model named, as the prompt listed it: "approve (Send)" copied whole, the bare id, or the label alone -
    an exact-id match dropped three right answers as "verb not offered" (2026-10-13)."""
    w = ' '.join(str(said or '').split()).lower(); bare = re.sub(r'\s*\(.*\)\s*$', '', w)
    return next((v for v in verbs if w in (v['verb'].lower(), f"{v['verb']} ({v['label']})".lower(), str(v['label']).lower())
                 or bare == v['verb'].lower()), None)


def judge(store, event: str,target_kind: str, target_id, rev: str, tier: int = 1, llm=None, key: str = None) -> int:
    """Judge one item at one revision - the item keyed `key` when the strip asked for it, else the target's first card - and
    write the row under that item's own key (keys_of), so it is never read back over another item of the same task."""
    item = _item(store, target_kind, target_id, key)
    key = (item or {}).get('key') or key or key_of(target_kind, target_id)
    own = keys_of(item, key)
    def W(**kw): return _write(store, target_kind=target_kind, target_id=target_id, key=key, event=event, revision=rev, tier=tier, **kw)
    if not item: return W(dropped='no item')
    if quiet(item): return W(dropped='left to the item')
    verbs = offered(store, item)
    if not verbs: return W(dropped='no actions')
    have = row(store, target_kind, target_id, rev, own)                      # two events in one poll: the second finds the first's row
    if judged(have, tier): return have['Id']
    brain = llm or build_llm(store)
    if not brain:
        # once per revision, and said: the strip asks for an AI (for_key's {"none": "no_ai"}) - a repeat would loop the re-read
        last = next(iter(_at(store, target_kind, target_id, rev, own)), None)
        if last and last.get('Dropped') == 'no brain': return last['Id']
        rid = W(dropped='no brain'); _emit(key, target_kind, target_id); return rid
    model = getattr(brain, 'last_pick', None) or getattr(brain, 'model', None) or 'light'
    ans = ask_json(brain, _system(store), _prompt(store, event, item, verbs, tier, target_kind, target_id), want=WANT, max_tokens=200)
    d = ans.data if isinstance(ans.data, dict) else {}
    # a line that landed while this one was thinking stands: a tier-2 answer, drop or not, never replaces a line the owner may
    # already be reaching for (B5 - the filled button moved under the cursor seconds after the item opened)
    now = row(store, target_kind, target_id, rev, own)
    if now and now.get('Verb'): return now['Id']
    if not d: return W(dropped=f'no answer: {ans.error or "not an object"}'[:200], model=model)
    verb, line = d.get('verb'), ' '.join(str(d.get('line') or '').split())[:200]
    ev = [e for e in (d.get('evidence') or []) if isinstance(e, str) and _EV.match(e)][:6]
    if not verb or not line: return W(dropped='nothing to say', model=model, evidence=ev)
    hit = _offered(verbs, verb)
    verb = hit['verb'] if hit else verb
    if not hit: return W(dropped=f'verb not offered: {verb}'[:120], model=model, line=line, evidence=ev)
    line = plain(line, verb, hit['label'])
    rid = W(line=line, verb=verb, label=hit['label'],count=habit(store, verb, item), evidence=ev, model=model)
    _emit(key, target_kind, target_id); return rid


def _emit(key, target_kind, target_id):
    try:
        from . import live
        live.emit(live.ADVICE, key=key, target_kind=target_kind, target_id=int(target_id))
    except Exception: pass


def judged(have, tier: int) -> bool:
    """A line stands at any tier (the bigger read runs only where the first one found none); a verdict drop stands for its own
    tier and below, so the item on the table still earns the bigger read after the small one said nothing."""
    return bool(have) and (bool(have.get('Verb')) or int(have.get('Tier') or 1) >= tier)


def quiet(item: dict) -> bool:
    """Where the Advisor keeps out of it. Mail the AI never sorted: the row's own Sort it again is the move, and the Advisor,
    offered only Make a task / Send to agent / Not ours, put the dark button on "Not ours" for mail nobody read. A report that
    ran fine: it is read, not acted on, and the only verbs it carries create work (2026-10-17 audit)."""
    return item.get('lane') == 'unjudged' or (item.get('kind') == 'report' and not item.get('bad'))


def failure(store, item: dict) -> dict | None:
    """What last failed on the item - {what, why, fix, unknown, kind} - or None: a draft whose send failed or never answered, else the
    newest act on it that ended in an error. The Advisor was never told, so it advised the Send that had just failed (2026-10-18)."""
    ok = lambda f: f if isinstance(f, dict) and f.get('label') and f.get('href') else None
    r = (store.get_review(int(item['rid'])) if item.get('rid') else None) or {}
    if r.get('DeliveryState') in ('failed', 'unknown'):
        try: env = json.loads(r.get('Deliver') or '{}') or {}
        except (TypeError, ValueError): env = {}
        why = re.sub(r'^Not sent:\s*', '', str(r.get('Reason') or '')).rstrip('.')
        return {'what': 'the reply was not sent' if r['DeliveryState'] == 'failed' else 'the reply may not have gone',
                'why': why, 'fix': ok(env.get('fix')) if isinstance(env, dict) else None, 'unknown': r['DeliveryState'] == 'unknown', 'kind': 'send'}
    # ...and a report's card or a connection's row has no task: its failure lives on the report or the connector (failures.standing)
    from . import failures
    if (on := failures.target_of(item)) and (f := failures.standing(store, *on)): return f
    try: ops = store.operations_for(item.get('tid'), [item['mid']] if item.get('mid') else [])
    except Exception: ops = []
    last = ops[-1] if ops else {}
    # ...and an act the demo refused (demo.refused): it went nowhere, so the Send just refused is not advised again (2026-10-19)
    if last.get('Status') not in ('error', 'refused'): return None
    try: out = json.loads(last.get('OutcomeJson') or '{}') or {}
    except (TypeError, ValueError): out = {}
    out = out if isinstance(out, dict) else {}
    # the record's own words lead (failures.record - the workflow runner's step says which step stopped); else the act, described
    if out.get('what'): what = str(out['what'])
    else:
        try:
            from . import operations
            what = f'"{concierge.describe_op(store, operations.get(store, last["OpId"]))[0]}" did not happen'
        except Exception: what = f'"{last.get("Kind") or "the last action"}" did not happen'
    from .failures import area_fix
    return {'what': what, 'why': str(last.get('Error') or ''), 'fix': ok(out.get('fix')) or area_fix(out.get('area')),
            'unknown': out.get('delivery') == 'unknown', 'kind': last.get('Kind'), 'source': out.get('source') or 'app',
            'cause': out.get('cause') or 'taskuary'}


def fix_task(store, item: dict, f: dict) -> dict:
    """The task "New task to fix this" makes: what failed, why, and on what - in the owner's words, for an agent or for them."""
    on = ' '.join(filter(None, (item.get('ref'), item.get('title'))))
    return {'title': f"Fix: {f['what']}"[:120], 'text': f"{f['what'][:1].upper()}{f['what'][1:]} on {on or 'an item'}. What came back: "
            f"{f['why'] or 'no reason was given'}. Find why, and fix it so it does not fail again."}


def delivery_fix(store, item: dict) -> dict | None:
    """{label, href} of the place that fixes the item's failed send - the draft's envelope (Deliver.fix, kept across a reload),
    else the newest act on the item when it failed with one (OutcomeJson.fix). None when nothing failed, or it named no place."""
    ok = lambda f: f if isinstance(f, dict) and f.get('label') and f.get('href') else None
    r = (store.get_review(int(item['rid'])) if item.get('rid') else None) or {}
    try: env = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): env = {}
    if isinstance(env, dict) and (r.get('DeliveryState') or env.get('delivery')) == 'failed' and ok(env.get('fix')): return ok(env['fix'])
    try: ops = store.operations_for(item.get('tid'), [item['mid']] if item.get('mid') else [])
    except Exception: ops = []
    last = ops[-1] if ops else {}
    try: out = json.loads(last.get('OutcomeJson') or '{}') if last.get('Status') == 'error' else {}
    except (TypeError, ValueError): out = {}
    return ok((out or {}).get('fix')) if isinstance(out, dict) else None


def offered(store, item: dict) -> list:
    """THE ITEM'S REAL BUTTONS, AND NOTHING IT CANNOT DO: the verbs its row carries minus Next - chips_for, which already drops
    what this install cannot do (capabilities.py: no Send on a draft whose channel cannot send, no coding agent with no
    coding tool) - plus the row's own fix when a send failed and named the place that fixes it, under that place's own name.
    An agent waiting on the owner carries Answer it there (chips_for) - its card once offered only End and Remind me, which the
    prompt forbids for someone waiting, so the Advisor stood silent (2026-10-17 audit). Not added here: a paused, stalled or
    stopped agent has nobody listening, and the row knows which is which."""
    verbs = [c for c in concierge.chips_for(store, item) if c.get('verb') != 'next']
    try: fix = delivery_fix(store, item)
    except Exception as e:
        logger.debug(f'advisor: no fix read for {item.get("key")} - {e}'); fix = None
    # the fix leads: a send that failed is fixed before it is sent again (ReviewDecision.jsx draws it as '<rid>:fix')
    lead = [buttons.chip('fix') | {'label': fix['label'], 'href': fix['href']}] if fix else []
    # A FAILURE NOTHING HERE FIXES (no fix named, not a send that may yet have gone) can still be made somebody's work: New task, in its
    # "fix" state, carrying what failed (the owner, 2026-10-18: "if it's a more complicated fix, the assistant should create a task")
    try: f = failure(store, item)
    except Exception: f = None
    if not fix and f and f.get('fix'): fix = f['fix']; lead = [buttons.chip('fix') | {'label': fix['label'], 'href': fix['href']}]
    if fix and f and f.get('cause') != 'step' and f.get('source') != 'workflow': f = None      # a fix is the way on; no task besides it
    # ...except a workflow run, which already IS a task: a second one to fix it would be the same work twice - it carries Report
    # this bug instead (agreed with the workflow runner, taskhub-ca, 2026-10-18)
    # ...and nothing for what the demo refused: no task or bug report makes the demo send
    if f and f.get('cause') == 'demo': pass
    elif f and (f.get('cause') == 'step' or f.get('source') == 'workflow'): lead.append(buttons.chip('report_bug'))
    elif f and not f.get('unknown'): lead.append(buttons.chip('new_task', 'fix') | {'task': fix_task(store, item, f)})
    return lead + verbs


def _capped(store) -> bool:
    cap = int(store.get_setting(CAP_KEY, CAP_DEFAULT) or CAP_DEFAULT)
    since = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    n = (store._one("SELECT COUNT(*) AS n FROM advice WHERE CreatedAt>=? AND Model IS NOT NULL", (since,)) or {}).get('n') or 0
    return n >= cap


_INFLIGHT, _LOCK = set(), threading.Lock()      # (kind, id, revision, tier) being judged right now


def notice(store, event: str, target_kind: str, target_id, *, tier: int = 1, wait: bool = False, llm=None, key: str = None):
    """The one door every event calls. Never raises: a hook, a close or a poll must not fail for advice. `key` is the item the
    strip asked for (for_key): only that item's rows count as judged. An event names a target, and any row at its revision does.
    Returns the row id when judged inline (tests, `wait=True`), None when skipped or sent to the background."""
    try:
        if str(store.get_setting(ON_KEY, '1') or '1') != '1' or not target_id: return None
        rev = revision(store, target_kind, target_id)
        own = _own(store, (target_kind, target_id), key, _at(store, target_kind, target_id, rev)) if key else None
        if judged(row(store, target_kind, target_id, rev, own), tier): return None    # judged at this revision already
        if _capped(store):
            last = next(iter(_at(store, target_kind, target_id, rev, own)), None)
            if last and last.get('Dropped') == 'cap': return last['Id']          # one cap row per revision, retried next look
            return _write(store, target_kind=target_kind, target_id=target_id, key=key or key_of(target_kind, target_id), event=event, revision=rev, tier=tier, dropped='cap')
        mark = (target_kind, int(target_id), rev, int(tier), key)
        with _LOCK:
            if mark in _INFLIGHT: return None                                   # the same moment, judged on another thread
            _INFLIGHT.add(mark)
        def done():
            with _LOCK: _INFLIGHT.discard(mark)
        if wait:
            try: return judge(store, event, target_kind, target_id, rev, tier, llm, key)
            finally: done()
        if not BACKGROUND: done(); return None
        def go():
            try: judge(store, event, target_kind, target_id, rev, tier, llm, key)
            except Exception as e: logger.warning(f'advisor: {event} on {target_kind} {target_id} not judged - {e}')
            finally: done()
        threading.Thread(target=go, daemon=True, name=f'advise-{target_kind}-{target_id}').start()
    except Exception as e: logger.warning(f'advisor: {event} on {target_kind} {target_id} skipped - {e}')
    return None


def _payload(r: dict) -> dict:
    count = json.loads(r.get('CountJson') or '[0,0]')
    # a row judged under an older wording ("Take it myself", "Close out") shows today's name; a state's name (Approve) is kept
    verb = concierge.canon_verb(r['Verb']) if r.get('Verb') else r.get('Verb')
    if r.get('Verb') and not verb: r = {**r, 'Line': ''}                  # its button is gone (Prep me): the line pointed at nothing
    # a fix is named by the place it opens ("Connect a mailbox"), never the generic button word
    lbl = r['Label'] if r.get('Label') in buttons.labels() or (verb == 'fix' and r.get('Label')) else buttons.label(verb or '') or r.get('Label')
    return {'key': r['Key'], 'line': plain(r['Line'] or '', r['Verb'] or '', lbl or '') if r.get('Line') else r.get('Line'), 'verb': verb, 'label': lbl, 'pill': pill(lbl, count), 'count': count,
            'says': says(r['Verb'] or '', count), 'evidence': json.loads(r.get('EvidenceJson') or '[]'), 'revision': r['Revision'], 'tier': r['Tier'], 'at': r['CreatedAt']}


def _at_work(store, target_kind: str, target_id) -> bool:
    """An agent at work on the task is nothing for the owner to do. Its continue writes no event the revision sees until the
    prompt lands, so "the agent stopped and is waiting on you" stood over an agent already continued (the owner, 2026-10-13)."""
    if target_kind != 'task': return False
    from . import workerstate
    try: return workerstate.status(store, int(target_id)).get('state') == 'working'
    except Exception: return False


def for_key(store, key: str) -> dict:
    """What the prompt box shows for the item on the table: the row at the item's CURRENT revision, or nothing. A changed
    item drops its old pill by this one comparison - no cleanup pass. The item on the table earns the bigger read, once, and
    only where the small read left no line: a tier-2 answer swapped the line and moved the filled button seconds after the item
    opened, under the owner's hand (B5, 2026-10-17). {"none": "no_ai"} is the strip's cue to ask for an AI."""
    tgt = target_of(store, key)
    if not tgt or _at_work(store, *tgt): return {}
    rev = revision(store, *tgt); rs = _at(store, tgt[0], tgt[1], rev)
    # only the rows written for THIS item (keys_of): a line judged over the same task's other card is not this one's
    own = _own(store, tgt, key, rs); rs = [x for x in rs if x.get('Key') in own]; r = row(store, tgt[0], tgt[1], rev, own)
    if r and r.get('Verb'):
        out = _payload(r) | {'key': key}
        # a fix is a place, not a proposal: the page opens its href where the row has no '<rid>:fix' of its own to press (a failed
        # act with no draft on the table) - read live, so a fix already made carries no stale link
        if out.get('verb') == 'fix':
            try: f = delivery_fix(store, _item(store, *tgt, key=key) or {})
            except Exception: f = None
            if f: out['href'] = f['href']
        # ...and the task "New task to fix this" makes, read live the same way
        if out.get('verb') == 'new_task':
            try: it = _item(store, *tgt, key=key) or {}; f = failure(store, it)
            except Exception: f = None
            if f: out['task'] = fix_task(store, it, f)
        return out
    # NEVER LEFT GUESSING (the owner, 2026-10-15: "the advisor ... should be guiding at all times never leaving it guessing"): only
    # eight events ever judged an item, so a fresh email or a task that moved since its last event had an empty bar for good. The
    # item on the table is judged now, at this revision, once - the line arrives by the `advice` live event the page already reads
    if not judged(r, 2): notice(store, r['Event'] if r else SHOWN, tgt[0], tgt[1], tier=2, key=key)
    return {'none': 'no_ai'} if rs and rs[0].get('Dropped') == 'no brain' else {}


# WHY THE STRIP IS EMPTY, in one word the page reads: "Thinking about this one..." ran 20 s and then showed nothing, over an item the
# Advisor keeps out of (unsorted mail, a report that ran fine) as much as over one it was judging (error sweep, 2026-10-18)
QUIET = {'left to the item': 'quiet', 'no actions': 'no_actions', 'cap': 'cap', 'no brain': 'no_ai'}
# ...and each reason is said on the strip as one sentence with one lit move (words.json advice_none): every one must have it
REASONS = (*QUIET.values(), 'nothing', 'working', 'off')
def status(store, key: str) -> dict:
    """for_key, and when it has no line: {'pending': True} while a judgement of this item is in flight, else {'none': why}."""
    out = for_key(store, key)
    if out.get('verb') or out.get('none'): return out
    tgt = target_of(store, key)
    if not tgt: return {'none': 'nothing'}
    if _at_work(store, *tgt): return {'none': 'working'}
    if str(store.get_setting(ON_KEY, '1') or '1') != '1': return {'none': 'off'}
    rev = revision(store, *tgt)
    with _LOCK: busy = any(m[:3] == (tgt[0], int(tgt[1]), rev) for m in _INFLIGHT)
    if busy: return {'pending': True}
    rs = _at(store, tgt[0], tgt[1], rev); own = _own(store, tgt, key, rs) if rs else {key}
    last = next((r for r in rs if r.get('Key') in own), None)
    if not last: return {'pending': True} if BACKGROUND else {'none': 'nothing'}
    return {'none': QUIET.get(str(last.get('Dropped') or ''), 'cap' if str(last.get('Dropped') or '').startswith('cap') else 'nothing')}


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
    if not d.get('verb'): return ''
    # the button's name and what the evidence SAYS: "verb stop_agent; evidence: out13" was handed to the chat as-is, and came
    # back to the owner in its answer (2026-10-17 audit)
    ev = '; '.join(filter(None, (evidence_words(store, e) for e in d['evidence']))) or 'the item itself'
    return (f"THE ADVISOR'S LINE on this item (if the owner asks why, this is the answer; the numbers are the ledger's): "
            f"\"{d['line']}\" - its button is {d['label']}" + (f" ({d['says']})" if d.get('says') else '') + f"; it rests on: {ev}.")


def evidence_words(store, ev_id: str) -> str:
    """One evidence id as what it says: an outcome as the ledger's own sentence, anything else as the label it resolves to."""
    try:
        if str(ev_id).startswith('out'):
            from . import outcomes
            r = store._one('SELECT * FROM outcome WHERE Id=?', (int(ev_id[3:]),))
            return outcomes._sentence(store, r) if r else ''
        from .learnedgraph import _resolve
        lbl = _resolve(store, ev_id).get('label')
        return '' if lbl == ev_id else str(lbl or '')
    except Exception: return ''
