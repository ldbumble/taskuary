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
from . import buttons, concierge, words
from .llm import build_llm, ask_json
L = buttons.label        # the prompt names a button by its one label (buttons.json)

ON_KEY, CAP_KEY, CAP_DEFAULT = 'advisor_events', 'advisor_event_cap', 30
BACKGROUND = True        # the suite turns this off (tests/conftest.py): a judgement runs only when a test asks for it inline
def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def key_of(target_kind: str, target_id) -> str:
    return f"{'task' if target_kind == 'task' else 'idea' if target_kind == 'idea' else 'msg'}:{int(target_id)}"
def target_of(store, key: str):
    """A rail key -> (target kind, id), or None for a key with nothing to advise on (a connection, a meeting, a batch). An idea - the
    Advisor's own line, a slipped follow-up - is a target of its own: it was None, so no idea ever had a line (the deep dive, 2026-10-20)."""
    m = re.match(r'^(task|agent|wrap|msg|report|idea):(\d+)$', str(key or ''))
    if m: return ('task' if m.group(1) in ('task', 'agent', 'wrap') else 'idea' if m.group(1) == 'idea' else 'message', int(m.group(2)))
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
        for kind in ('task', 'message', 'idea'):
            m = next((r for r in rows if r['EntityKind'] == kind), None)
            if m: return (kind, int(m['LocalId']))
    return None


def revision(store, target_kind: str, target_id) -> str:
    """The stamp advice is pinned to: the proposal's own context revision (messages and status) joined with what that
    revision leaves out and an event changes - the task's state and the newest word its agent said."""
    from .operations import context_revision
    base = context_revision(store, target_kind, target_id)
    if target_kind == 'idea':                         # an idea moves with its own state and words, and the thread it is about
        i = store.get_idea(int(target_id)) or {}
        try: a = json.loads(i.get('ActionJson') or '{}') or {}
        except ValueError: a = {}
        base = f"{i.get('Status')}|{i.get('LastSaid')}|{i.get('Text')}|{i.get('ActionJson')}"
        if a.get('mid'): base += '|' + context_revision(store, 'message', int(a['mid']))
        if a.get('tid'): base += '|' + context_revision(store, 'task', int(a['tid']))
    if target_kind == 'task':
        t = store.get_task(target_id) or {}
        ev = store._one('SELECT MAX(Id) AS Id FROM worker_event WHERE TaskId=?', (int(target_id),)) or {}
        base += f"|{t.get('Status')}|{t.get('Assignee')}|{t.get('DueAt')}|{ev.get('Id')}|{t.get('WaitingOn')}|{t.get('WokeMid')}"
    # ...and every act on it: a line judged "Send" before the send failed stood over the failure, advising the same Send (2026-10-18);
    # one judged "Reply" before the reply WENT stood over "Sent" on the close-out, still saying the sender was waiting (2026-10-19)
    base += f"|{_acted(store, target_kind, target_id)}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def _acted(store, target_kind, target_id) -> str:
    """What the owner's acts left on the target: each draft - there or not, how it was decided, whether it went - and the newest
    operation that ran on it, done, failed or declined (a proposal still waiting for its yes is no act yet). DeliveryState alone
    skipped every NULL, so a reply sent with no delivery receipt (Status approved, DeliveryState NULL) changed nothing it saw."""
    col = 'TaskId' if target_kind == 'task' else 'MessageId'
    if target_kind == 'idea':                         # an idea carries no draft; its acts are its own operations
        op = store._one("SELECT OpId, Status FROM operation WHERE TargetKind='idea' AND TargetId=? AND Status<>'proposed' ORDER BY rowid DESC LIMIT 1", (int(target_id),)) or {}
        return f"/{op.get('OpId') or ''}:{op.get('Status') or ''}"
    # ...and whether its draft could not be written: a Reply whose draft failed left the line it was judged before standing (2026-10-19)
    rv = store._one(f"SELECT GROUP_CONCAT(ReviewId || ':' || IFNULL(Status,'') || ':' || IFNULL(DeliveryState,'') || ':' || (IFNULL(DraftError,'')<>''), ',') AS d FROM "
                    f"(SELECT * FROM review WHERE {col}=? ORDER BY ReviewId)", (int(target_id),)) or {}
    op = store._one("SELECT OpId, Status FROM operation WHERE TargetKind=? AND TargetId=? AND Status<>'proposed' ORDER BY rowid DESC LIMIT 1",
                    (target_kind, int(target_id))) or {}
    return f"{rv.get('d') or ''}/{op.get('OpId') or ''}:{op.get('Status') or ''}"


def _write(store, *, target_kind, target_id, key, event, revision, tier=1, line='', verb=None, label=None, count=(0, 0),
           evidence=(), model=None, dropped=None, kind=None) -> int:
    return store._exec('INSERT INTO advice (TargetKind,TargetId,Key,Event,Revision,Tier,Line,Verb,Label,CountJson,EvidenceJson,Model,Dropped,CreatedAt,Kind) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (target_kind, int(target_id), key, event, revision, int(tier), line or '', verb, label, json.dumps(list(count)),
                        json.dumps(list(evidence)), model, dropped, _now(), kind))
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
    "with it now, as ONE of the VERBS OFFERED (exactly as written) and the LINE: the one checkable fact it rests on that the card does "
    "not already show - an age, a clash, a failure, a promise nothing backs, someone else who owns it - or an empty line when the move "
    "is plain; the lit button does the talking, so never a sentence explaining the button or what it does - or say nothing. Say nothing unless the owner's own habits (LEARNED), the outcome ledger or "
    "the item's own facts point at one verb. Never invent a number: the numbers in the ledger lines and in the HOW SOON YOU ANSWER, "
    "WHEN YOU PUT THEIR MAIL OFF and WHOM YOU HANDED lines are the only ones you may use, and you cite their ids. "
    # MEMORY IS A REASON TOO, IN ONE LINE (the owner, 2026-10-25: "Reply: you usually answer Erin within the hour; this is 3h")
    "What you know about how the owner works is a checkable fact when it bears on THIS item - say it as the line, short: \"Ray handles "
    f"payroll for you\" over {L('forward')}, when this ask is that kind of work and the owner handed such asks to that person. "
    "What a sender says about themselves is never such a fact. "
    # ...BUT ONLY WHEN THE ITEM IS ABOUT IT (the live memory A/B, 2026-10-26): "Friday's payment run is Ray's" sent a draft promising a
    # payment date nobody had set, "Erin's mail bounced" lit Reply over a dead address, "Ray handles overtime" stood over an agent
    "A memory line counts only when something CURRENT in this item is about it: a line about a person supports a move only when THIS "
    "ask is that person's kind of work - it never makes a draft that promises what nothing here shows ready to send, never answers a "
    "failure (a refused address is fixed, not replied to, however soon the owner answers that person). "
    f"A line saying whom the owner hands a kind of ask to is the reason for {L('forward')} and nothing else - never said over "
    "another verb. When your line rests on a memory line or a usual line, cite its id. "
    # ...and A REPORT NOBODY WANTS (the owner, 2026-10-27: the Advisor may suggest switching a report off) - the press stays the owner's
    f"{L('report_off')} only over a report run whose findings are all about something a What you care about line says the owner does "
    "not care about - cite that line, and the line says what it is about; never over a run that failed, never on a guess. "
    "A ledger line says what HAPPENED, never whether it worked: \"continued\" means the session was started "
    "again, nothing more - never call it a success, and never say something was merged, sent or fixed unless a line says exactly that. "
    "The line is plain words for the owner, who may never have written code: the ids go in \"evidence\" only, the verb is named by "
    "its label, never its id, and never a word from the item's own bookkeeping (lane, kind, triage, session, model, an event name). "
    "The reason must be the fact that makes THIS verb right, and it must hold up on its own: someone or an agent waiting on the "
    "owner is a reason to answer, never a reason to put it off. Ending an agent's session is right when its work is done or no "
    "longer wanted; when it has finished something for the owner to review or send, the move is the one that reviews or sends it. If none of the verbs offered is the right move, say nothing - a "
    "wrong suggestion is worse than none. The line is at most 60 characters, so it is read whole on a phone. "
    # ...AND WHAT KIND OF FACT THE LINE IS (the Advisor audit's judge, 2026-10-26): a caution about the draft stood beside a lit Send - the
    # check after the answer reads this field, never the line's words, to refuse a verb that contradicts its own reason
    "Answer with JSON only:{\"verb\": \"<one of the verbs>\" or null, \"line\": \"<sentence>\" or \"\", "
    "\"evidence\": [\"<ids from the lines below>\"], \"kind\": \"<what the line's fact is>\"}. The kind is one of: late (an answer or a "
    "wait past its time), same_ask (another task holds this same ask), draft_caution (the draft is not ready to send as written), "
    "handoff (someone else does this work), failure (something failed), memory (another fact about how the owner works), other - "
    "\"other\" with an empty line. "
    "EXCEPT when the EVENT is item.shown: the owner is looking at this item right now and is owed a next step, so pick the verb the "
    f"item's own facts make right (a person waiting on them: {L('reply')}; an agent asking them something is answered in its own pane, "
    "not by a verb - pick what else its facts make right, or nothing; nothing "
    f"for them to do: {L('close')} or {L('let_go')}; work an agent left: {L('continue')} or {L('approve')}; a draft waiting: {L('approve')}; "
    f"a reply already sent (an A REPLY WAS ALREADY SENT line) - sending never closes the task - and nothing left to do: {L('close')}, "
    "never an answer the sent reply already gave - someone is waiting only when they wrote again after it; a reply that failed to "
    "send: the fix offered with it) - whichever of those is "
    "OFFERED - the line only for a fact the card does not show - say nothing only when no verb offered fits at all. "
    "WHEN SOMETHING FAILED (a WHAT FAILED line below), the owner is owed the way past it, at any event: say in plain words what went "
    "wrong, and pick the move that fixes it - the fix offered when there is one (it opens the place that fixes it); else a verb offered "
    "that gets round it; else, when nothing here can fix it, the one that makes a task to fix it. Never advise the act that failed again "
    "unchanged - unless the failure says the cause has passed - and never Send again when nobody knows whether the first send went. "
    # THE RULES THE DEEP DIVE FOUND MISSING (2026-10-20), each about a moment it got wrong
    "AN AGENT'S RUN THAT FAILED is a failure like any other (a WHAT FAILED line names it): Continue only when something here says "
    "the cause has passed; else say what stopped it and pick the fix offered, else the one that makes a task to fix it. "
    "A SEND THE MAIL SERVER REFUSED FOR ITS ADDRESS (no such user, unknown or refused recipient, a bounce): the address is what "
    "is wrong, not the words - pick the fix offered, else the one that makes a task to fix the address; never Redraft. "
    "A DRAFT THAT PROMISES WHAT NOTHING HERE SHOWS - a payment date nobody set, a file the ATTACHED line does not list, \"sending "
    "it now\" with nothing attached - is not ready: say what it promises, and pick Redraft (or Reply to write it again) - never "
    "Send. "
    f"WORK AN AGENT CAN DO - an issue or bug report with a traceback or steps to reproduce, a reconciliation, a lookup - is "
    f"{L('regular_agent')} when it is offered and nobody needs the owner's own words; an answer the person waits on is still "
    f"{L('reply')}. "
    f"SOMEONE THE OWNER WAITS ON IS QUIET PAST THEIR DAY (the item says how long, and {L('chase')} is offered): {L('chase')} - a short "
    f"nudge for the owner's yes - unless the item says they answered or are away. "
    # ...AND THE VERB AGREES WITH IT (the UI audit's C2, 2026-10-21): "TQ-0006 may already cover it, and an agent is on that" stood over a
    # dark Reply - the line said don't answer twice and the button said answer
    "A POSSIBLE DUPLICATE with an agent already on it is said in the line, so the owner does not answer the same ask twice - and then "
    f"the verb is never {L('reply')}: it is {L('defer')}, to look again once that agent is done, when offered; else say nothing. "
    f"A GOAL (a THE GOAL line): a step past its day, or held by someone late, is named in the line with the move offered that gets it "
    f"going ({L('chase')} when offered, else {L('defer')} to look again on a day); a goal with no news says so, and the move is "
    f"{L('defer')}. AN IDEA (a THE IDEA line, the assistant's own suggestion): {L('mine')} when it names work worth doing now, "
    f"{L('defer')} when it is for later, {L('not_ours')} when it is nothing for the owner.")
def _system(store) -> str:
    """SYSTEM plus the owner's own Voice section of COUNSEL: the Advisor's line sits in the same box as the chat's, so it
    speaks by the same rules - it never had them, and said "lane" and "session" to a finance user (2026-10-17 audit)."""
    from . import counsel
    try: voice = counsel.sections(counsel.load(store)).get(counsel.VOICE_HEAD, '').strip()
    except Exception: voice = ''
    return f"{SYSTEM}\n\nHOW THE LINE SPEAKS (the owner's own rules):\n{voice}" if voice else SYSTEM
# the event every item on the table gets, when no other event judged it at its current revision (Advisor audit, 2026-10-15)
SHOWN = 'item.shown'
KINDS = ('late', 'same_ask', 'draft_caution', 'handoff', 'failure', 'memory', 'other')
WANT = {'type': 'object', 'properties': {'verb': {'type': ['string', 'null']}, 'line': {'type': 'string'},
                                         'evidence': {'type': 'array', 'items': {'type': 'string'}}, 'kind': {'type': 'string', 'enum': list(KINDS)}},
        'required': ['verb', 'line', 'evidence']}
_EV = re.compile(r'^(out|mem|rv|task|msg|fs|sv|idea|lrn)\d+$')   # ...and the owner's own acts the usual is counted from (usual.py), and a memory line


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
    f = 'tid' if target_kind == 'task' else 'idea' if target_kind == 'idea' else 'mid'
    mine = [i for i in items if i.get(f) == int(target_id)]
    return (next((i for i in mine if key and key in keys_of(i)), None) or next(iter(mine), None)
            or funnel.item_for_key(store, key_of(target_kind, target_id)))


def habit(store, verb: str, item: dict) -> tuple:
    """(n, m, where): what came of this verb before, with this sender's domain - read from the outcome ledger, never from the model
    and never from presses (the owner, 2026-10-25: stop learning from presses). continue: stops that ended in a continue; approve:
    replies sent as drafted; close: closes that held; chase: nudges answered. Evidence the model reads (_prompt), never a line on the
    strip. (0, 0, '') when nothing is counted there."""
    w = who_of(store, item or {})
    if not w['domain']: return (0, 0, '')
    on = "IFNULL(json_extract(FactsJson,'$.who'),'') LIKE ?"
    by_task = "EXISTS (SELECT 1 FROM message m WHERE m.TaskId=outcome.TargetId AND LOWER(IFNULL(m.FromEmail,'')) LIKE ?)"
    q = {'continue': (f"SELECT Verdict AS v FROM outcome WHERE Kind='agent.stopped' AND ResolvedAt IS NOT NULL AND {by_task}", lambda r: r['v'] == 'continued'),
         'approve': (f"SELECT FactsJson AS f FROM outcome WHERE Kind='reply.sent' AND ResolvedAt IS NOT NULL AND {on}", lambda r: json.loads(r['f'] or '{}').get('verb') == 'approve'),
         'close': (f"SELECT Verdict AS v FROM outcome WHERE Kind='task.closed' AND ResolvedAt IS NOT NULL AND {by_task}", lambda r: r['v'] == 'held'),
         'chase': (f"SELECT FactsJson AS f FROM outcome WHERE Kind='reply.sent' AND ResolvedAt IS NOT NULL AND json_extract(FactsJson, '$.chase')=1 AND {on}",
                   lambda r: json.loads(r['f'] or '{}').get('answer_days') is not None)}.get(verb)
    if not q: return (0, 0, '')
    rs = store._rows(q[0], (f"%@{w['domain']}",))
    return (sum(1 for r in rs if q[1](r)), len(rs), f"with {w['domain']}")
# ...and what each count MEASURES, said so: "You chose Mark done 2 of 3 times in a moment like this" was read off closes that
# held and answers to nudges, counted over every item, not this kind of moment (2026-10-17 audit). The counts are EVIDENCE the model
# weighs, in the prompt's ledger - the "Your own habit..." line and the "· n of m times" mark left the strip (the owner, 2026-10-25)
MEASURES = {'continue': 'the owner picked the work back up {n} of the last {m} times an agent stopped',
            'approve': 'the owner sent {n} of their last {m} drafts as written',
            'close': '{n} of the last {m} tasks the owner closed stayed closed',
            'chase': '{n} of the owner\'s last {m} nudges got an answer'}
def measured(verb: str, count) -> str:
    """A ledger count as the evidence sentence the model reads - '' under two, or for a verb nothing measures."""
    n, m, where = (list(count) + [0, 0, ''])[:3]
    if m < 2 or verb not in MEASURES: return ''
    return MEASURES[verb].format(n=n, m=m) + (f' {where}' if where else '') + '.'


ADVISOR_FILE_CHARS = (600, 1200)     # per file, per item - the Advisor writes one line, so it reads the gist


def attached(store, target_kind, target_id) -> str:
    "ATTACHED FILES for the item: the newest three inbound messages' documents, scrubbed and fenced (attachtext)."
    from . import attachtext
    mids = ([m['MessageId'] for m in store.list_messages(int(target_id)) if m.get('Status') != 'context' and m.get('Direction') != 'out'][-3:][::-1]
            if target_kind == 'task' else [int(target_id)])
    got = [e for mid in mids for e in attachtext.of_message(store, mid)]
    return attachtext.block(got, 'ATTACHED FILES', cap=ADVISOR_FILE_CHARS[1], file_cap=ADVISOR_FILE_CHARS[0])



# THE PROMPT IS BOUNDED: every section has its own cap, and past PROMPT_CAP characters whole sections go from the end - the least
# pointed first (the month's outcomes, the hub's dossier, the owner's documents) - never a cut through a line. The item, its verbs,
# what failed and what was sent always stay.
PROMPT_CAP = 9000
_KEEP = 4                # EVENT, THE ITEM, PREVIEW, VERBS OFFERED


def _one(s, n: int) -> str: return ' '.join(str(s or '').split())[:n]


def _learned(store, item: dict = None) -> str:
    """What LEARNED.md knows about how the owner works that the Advisor reads (learned_cut.READS: their people, what they care about,
    how they work, their promises), its in-use lines ranked closest to this item first (this sender, their domain or repository)
    within its budget. '' while no section has a line: an empty heading is nothing known."""
    from . import learned_cut
    about = {}
    if item:
        try: w, on = who_of(store, item), people_on(store, item)
        except Exception: w, on = {}, set()
        m = store.get_message(int(item['mid'])) if item.get('mid') else None
        name = ' '.join(str((m or {}).get('FromName') or '').split())
        about = {'sender': w.get('sender'), 'domain': w.get('domain'), 'scope': w.get('scope'), 'people': sorted(on),
                 'sender_name': name if len(name.split()) >= 2 else '', 'topic': str(item.get('title') or '')}
    return learned_cut.for_reader(store, 'advisor', about, target=(item or {}).get('key') or '', cite=True)


def people_on(store, item: dict) -> set:
    """Everyone on the item as the app knows them, lowercased, never the owner: each address on its mail (from, To, Cc - the owner's own
    mail to them too) and each sender's full name, whom it waits on, and who holds an open step of its goal. Facts the app keeps, never
    the words of the mail - what a memory line is matched against (rulebook.memory_on) and ranked by (_learned)."""
    from . import learned_cut
    from .processing_unread import holder_name
    it = item or {}
    tk, ti = ('task', it['tid']) if it.get('tid') else ('message', it.get('mid'))
    out = {str(it['who_email']).lower()} if it.get('who_email') else set()
    for m in (_msgs(store, it, tk, ti) if ti else []):
        out |= learned_cut.people_of(m)
        if len((n := ' '.join(str(m.get('FromName') or '').split())).split()) >= 2: out.add(n.lower())
    t = store.get_task(int(it['tid'])) if it.get('tid') else None
    held = [t.get('WaitingOn'), t.get('Assignee')] if t else []
    if t and is_goal(t): held += [(x.get('child') or {}).get('Assignee') for x in store.goal_steps(int(t['TaskId'])) if not x['done']]
    for h in filter(None, held):
        if '@' in str(h): out.add(str(h).split(':', 1)[-1].strip().lower())
        if len(n := str(holder_name(h) or '').split()) >= 2: out.add(' '.join(n).lower())
    # ...and each address's own name, as its mail last signed it: whom a task waits on has often never written on that task
    for a in [p for p in out if '@' in p]:
        r = store._one("SELECT FromName FROM message WHERE LOWER(FromEmail)=? AND IFNULL(FromName,'')<>'' ORDER BY MessageId DESC LIMIT 1", (a,)) or {}
        if len(n := str(r.get('FromName') or '').split()) >= 2: out.add(' '.join(n).lower())
    me = {str(store.get_setting(k) or '').strip().lower() for k in ('owner_email', 'owner_name')}
    return {p for p in out if p and p not in me}


def _usual(store, item, target_kind, target_id) -> tuple:
    """(lines, handed ids): the owner's own usual with this item's sender, counted from what they did (usual.py) - how soon they answer,
    when they put this mail off to, whom they hand it to - and the ids the hand-off count rests on (a line resting on those is a reason
    for Hand it to a person, never for another verb)."""
    from . import usual
    try:
        last = next((m for m in reversed(_msgs(store, item, target_kind, target_id)) if str(m.get('Direction') or 'in') != 'out' and m.get('Status') != 'context'), None)
        ls = usual.prompt_lines(store, last, item.get('tid'))
        h = usual.handed_to(store, str((last or {}).get('FromEmail') or '').lower(), skip=item.get('tid')) if last else None
        return ls, set((h or {}).get('evidence') or [])
    except Exception as e:
        logger.debug(f'advisor: no usual read for {item.get("key")} - {e}'); return [], set()


def memory_ids(store, item, target_kind, target_id) -> set:
    """The ids an answer cites when its line rests on what the app knows about how the owner works: every LEARNED line the Advisor reads
    (its cite id, and the episodes its own tag names) and the owner's counted usual with this sender. A line citing none of them rests on
    the item's own facts."""
    from . import learned_cut
    from .learnedgraph import TAG
    doc = store.doc('learned') or ''
    out = set(re.findall(_ID, '\n'.join(_usual(store, item, target_kind, target_id)[0]))) if target_kind in ('task', 'message') else set()
    for s in learned_cut.READS['advisor']:
        for raw, k in learned_cut.lines(doc, learned_cut.SECTIONS[s]):
            out.add(learned_cut.cite_of(k))
            if (m := TAG.match(raw)): out |= {e.strip() for e in m.group('ev').split(',') if e.strip()}
    return out


def _msgs(store, item, target_kind, target_id) -> list:
    """The item's messages, oldest first: the task's own, else the message's thread - any channel, a chat's as much as a mail's."""
    if target_kind == 'task': ms = store.list_messages(int(target_id))
    else:
        m = store.get_message(int(target_id)) or {}
        try: ms = store.thread_messages(m['ConversationId'], m.get('Subject'), limit=12) if m.get('ConversationId') else [m]
        except Exception: ms = [m]
    return sorted([m for m in ms if m], key=lambda m: str(m.get('SentAt') or m.get('CreatedAt') or ''))


def _draft(store, item, target_kind, target_id):
    """The draft waiting for the owner's yes on this item, or None."""
    r = store.get_review(int(item['rid'])) if item.get('rid') else None
    if not r and target_kind == 'task': r = store.pending_review(int(target_id))
    if not r and target_kind == 'message': r = store._one("SELECT * FROM review WHERE MessageId=? AND Status='pending' ORDER BY ReviewId DESC LIMIT 1", (int(target_id),))
    return r if r and r.get('Status') in ('pending', 'held') and (r.get('FinalText') or r.get('DraftText')) else None


def draft_line(store, item, target_kind, target_id) -> str:
    """THE DRAFT ITSELF, and what goes with it: the line said "read it, then send it" over a draft it had never seen - one promising a
    payment date nobody had set, another saying "sending it now" with nothing attached (the Advisor deep dive, 2026-10-20)."""
    r = _draft(store, item, target_kind, target_id)
    if not r: return ''
    try: files = [f.get('name') for f in (json.loads(r.get('Deliver') or '{}') or {}).get('attachments') or [] if isinstance(f, dict)]
    except (TypeError, ValueError, AttributeError): files = []
    return (f"THE DRAFT WAITING FOR THE OWNER'S YES: \"{_one(r.get('FinalText') or r.get('DraftText'), 900)}\"\n"
            f"ATTACHED TO THE DRAFT: {', '.join(filter(None, files)) or 'nothing'}")


def thread_line(store, item, target_kind, target_id, n: int = 3) -> str:
    """The last few messages on it, theirs and the owner's: the preview is one message's first 300 characters, and the ask two
    messages back - or the owner's own answer - was never seen."""
    # ...but not on a task an agent has worked: what came before its last turn is in its own conversation, and what came after is
    # NEW SINCE THE AGENT'S LAST TURN - said twice it was read as news (test_reopened_conversation)
    if target_kind == 'task':
        from . import continuity
        if continuity.last_agent_turn(store, int(target_id)): return ''
    ms = _msgs(store, item, target_kind, target_id)[-n:]
    if len(ms) < 2: return ''
    who = lambda m: 'the owner' if str(m.get('Direction') or 'in') == 'out' else (m.get('FromName') or m.get('FromEmail') or 'someone')
    return f'THE LAST {len(ms)} MESSAGES ON IT, oldest first:\n' + '\n'.join(
        f"- {who(m)} ({str(m.get('SentAt') or m.get('CreatedAt') or '')[:16]}, {m.get('Channel') or 'email'}): {_one(m.get('Subject'), 80)} - {_one(m.get('BodyText'), 300)}" for m in ms)


def related_line(store, item, target_kind, target_id, cap: int = 5) -> str:
    """OTHER OPEN TASKS on the same sender, thread or subject, flagged as possible duplicates: the same ask filed twice was advised
    twice, Reply on each, with the agent already working the other one (the deep dive, 2026-10-20)."""
    from .ingest import topic_hit
    ms = _msgs(store, item, target_kind, target_id)
    own = int(target_id) if target_kind == 'task' else next((m.get('TaskId') for m in ms if m.get('TaskId')), None)
    senders = {str(m.get('FromEmail') or '').lower() for m in ms if m.get('FromEmail') and str(m.get('Direction') or 'in') != 'out'}
    cids = {m.get('ConversationId') for m in ms if m.get('ConversationId')}
    subj = str(item.get('title') or next((m.get('Subject') for m in ms if m.get('Subject')), '') or '')
    hits = {}
    if senders or cids:
        q = ' OR '.join(['LOWER(m.FromEmail) IN (%s)' % ','.join('?' * len(senders))] * bool(senders) + ['m.ConversationId IN (%s)' % ','.join('?' * len(cids))] * bool(cids))
        for r in store._rows(f"SELECT m.TaskId, LOWER(m.FromEmail) AS e, m.ConversationId AS c FROM message m JOIN task t ON t.TaskId=m.TaskId "
                             f"WHERE t.Status NOT IN ('done','dropped') AND ({q})", (*senders, *cids)):
            # THE SAME SENDER ALONE IS NO DUPLICATE (the design, 2026-10-23): one person asks for many things - the thread, or the
            # subject the model then reads, is the evidence; the sender only names who
            if r['TaskId'] == own or r['c'] not in cids: continue
            hits.setdefault(r['TaskId'], set()).add('same thread')
    if subj:
        for t in store.list_tasks(active_only=True):
            if t['TaskId'] != own and t.get('Title') and topic_hit(subj, t['Title']) and topic_hit(t['Title'], subj): hits.setdefault(t['TaskId'], set()).add('same subject')
    out = []
    from .store import task_ref
    from .funnel import working_tids
    from .workerstate import _live
    running = working_tids(store, live_state=[])                  # a headless run still going; a live session is _live's
    for tid, why in sorted(hits.items(), key=lambda kv: (-len(kv[1]), -kv[0]))[:cap]:
        t = store.get_task(tid) or {}
        if t.get('Status') in ('done', 'dropped'): continue
        # ...on it means a live session or run: `in_progress` outlives a stopped or failed agent, and the Advisor told the owner
        # to "look again later" about work nobody was doing (2026-10-22 walk)
        held = ' - an agent is on it' if _live(tid) or tid in running else ''
        out.append(f"- {task_ref(tid)} {t.get('Status')}: {_one(t.get('Title'), 100)} ({', '.join(sorted(why))}){held}")
    return ('POSSIBLE DUPLICATES - other open tasks on its thread or subject (one may already cover this ask):\n' + '\n'.join(out)) if out else ''


def notes_line(store, item, target_kind, target_id) -> str:
    """The owner's standing notes and past verdicts about this sender or topic, and their corrections of triage on it - the same
    evidence triage is handed (ingest.relevant_notes, operations.evidence_lines), so the Advisor never advises against a "not ours"
    the owner already gave."""
    from .ingest import relevant_notes
    from . import operations
    ms = [m for m in _msgs(store, item, target_kind, target_id) if str(m.get('Direction') or 'in') != 'out']
    m = ms[-1] if ms else {}
    senders = [str(x.get('FromEmail') or '') for x in ms]
    subj = str(m.get('Subject') or item.get('title') or '')
    try: notes, _ = relevant_notes(store, senders, f"{subj} {m.get('BodyText') or ''}"[:3000], cap=6, budget=900, subject=subj, source=m.get('SourceName') or '')
    except Exception: notes = []
    try: fixes = operations.evidence_lines(store, {'from_email': m.get('FromEmail') or '', 'subject': subj}, cap=3) if m else []
    except Exception: fixes = []
    got = [f'- {_one(n, 300)}' for n in notes + fixes]
    return ('THE OWNER\'S STANDING NOTES AND PAST VERDICTS on this sender or topic:\n' + '\n'.join(got)) if got else ''


def owner_line(store) -> str:
    """The head of SOUL.md and JOB.md: who the owner is and what their job is - the line weighs an ask by whom it serves."""
    def head(d):
        t = re.sub(r'<!--.*?-->|_\([^)]*\)_', '', str(store.doc(d) or ''), flags=re.S)       # comments and the template's placeholders
        t = re.sub(r'\n\s*\n+', '\n', t).strip()
        return t[:600].rsplit('\n', 1)[0] if len(t) > 600 else t
    bits = [f"{n} (its opening):\n{h}" for d, n in (('soul', 'SOUL.md'), ('job', 'JOB.md')) if (h := head(d))]
    return ('WHO THE OWNER IS:\n' + '\n'.join(bits)) if bits else ''


def playbook_line(store, target_kind, target_id) -> str:
    if target_kind != 'task': return ''
    from . import playbooks
    try: pb = playbooks.for_task(store.get_task(int(target_id)) or {})
    except Exception: pb = None
    if not pb: return ''
    return f"THE PLAYBOOK FOR THIS KIND OF JOB (\"{pb.get('title') or pb['slug']}\"): " + _one(' '.join(f"{f}: {pb[f]}" for f in playbooks.FIELDS if pb.get(f)), 600)


def _bounded(lines: list, cap: int = PROMPT_CAP) -> str:
    """Whole sections dropped from the end until it fits - the first _KEEP never."""
    lines = [l for l in lines if l]
    while len('\n\n'.join(lines)) > cap and len(lines) > _KEEP: lines.pop()
    return '\n\n'.join(lines)[:cap]


def _prompt(store, event, item, verbs, tier, target_kind, target_id) -> str:
    from . import outcomes
    from . import funnel
    facts = {k: item.get(k) for k in ('ref', 'title', 'who', 'when', 'why', 'channel') if item.get(k)}
    # where it stands, in the rail's own words - a lane id handed over as-is came back in the line ("the lane is blocked")
    kinds = {k['key']: k['word'] for k in funnel._VOCAB['kinds']}
    stands = kinds.get(item.get('kind')) or funnel.LANE_WORDS.get(item.get('lane'), ('',))[0]
    if stands: facts['where it stands'] = stands
    # ...and the task's own dates and weight: "due Friday" and "remind me Thursday" were on the task and never in the prompt
    t = store.get_task(int(target_id)) if target_kind == 'task' else (store.get_task(int(item['tid'])) if item.get('tid') else None)
    for k, col in (('due', 'DueAt'), ('priority', 'Priority'), ('remind me on', 'RemindAt'), ('done when', 'DoneWhen')):
        if (t or {}).get(col): facts[k] = str(t[col])[:160]
    if item.get('priority') and 'priority' not in facts: facts['priority'] = item['priority']
    if facts.get('priority'):
        from .processing_order import level
        facts['priority'] = level(facts['priority'])          # regular, important or urgent - the three words (2026-10-25)
    lines = [f'EVENT: {event}', 'THE ITEM: ' + json.dumps(facts), f"PREVIEW: {str(item.get('preview') or '')[:300]}",
             'VERBS OFFERED: ' + ', '.join(f"{v['verb']} ({v['label']})" for v in verbs)]
    # AN IDEA AND A GOAL ARE ADVISED TOO (the deep dive, 2026-10-20): an idea had no target at all, and a goal's card said "0 of 2" with
    # nothing of which step was late or when anything last moved. An idea's context is the task or mail it is about.
    if target_kind == 'idea':
        lines.append(idea_line(store, target_id, item))
        target_kind, target_id = ('task', int(item['tid'])) if item.get('tid') else ('message', int(item['mid'])) if item.get('mid') else ('none', 0)
    try: lines.append(goal_line(store, t) if t and is_goal(t) else '')
    except Exception as e: logger.debug(f'advisor: no goal read for {item.get("key")} - {e}')
    # what the files on it SAY, small (ADVISOR_FILE_CHARS): the preview is the mail's words, and "see attached" weighed blind
    try: att = attached(store, target_kind, target_id)
    except Exception as e: logger.debug(f'advisor: no attachment text for {item.get("key")} - {e}'); att = ''
    if att: lines.append(att)
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
        # ...and WHETHER ITS RUN IS OVER, and how: a finished agent's result came only as a 'finished' event, which the prompt never
        # carried - the line over "the agent finished" had nothing to say (the advisor matrix, 2026-10-19)
        if st.get('state') in ('finished', 'failed', 'stopped'):
            last = next((e for e in reversed(workerstate.events(store, int(target_id), st.get('sid'))) if e['Kind'] == st['state']), {})
            said = ' '.join(str(st.get('result') or last.get('Text') or '').split())[:400]
            lines.append(f"THE AGENT'S RUN ENDED ({st['state']})" + (f': {said}' if said else ' - it left no words'))
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
        # ...and WHO it was waiting on (waiton.py): the agent said only that person could answer, and their answer is in - or not yet
        from . import waiton
        if waiton.waiting(t): lines.append(f"THE AGENT IS WAITING ON {waiton.name_of(t['WaitingOn'])}'S ANSWER - they have not written since; nothing here moves it")
        elif mail and waiton.woke_by(t, mail[-1]):
            lines.append(f"THE AGENT WAS WAITING ON {mail[-1].get('FromName') or mail[-1].get('FromEmail')}'S ANSWER, AND IT IS THE NEWEST LINE ABOVE - "
                         f"{buttons.label('continue')} hands it to the agent's saved conversation")
        todo = [c.get('text') + (f" (note: {c['note']})" if c.get('note') else '') for c in _checklist(t) if not c.get('done') and c.get('text')]
        if todo: lines.append('STILL TO DO ON THE TASK: ' + ' | '.join(' '.join(str(x).split())[:160] for x in todo[:6]))
        # ...and a list with nothing left on it, said: with no line at all the model could not tell it from a task with no list
        elif (ticked := [c for c in _checklist(t) if c.get('done')]): lines.append(f'EVERY TODO ON THE TASK IS TICKED ({len(ticked)} of {len(ticked)})')
    # THE FULL CONTEXT (the deep dive, 2026-10-20): the draft, the thread, the tasks that may already cover it, the owner's notes on
    # the sender, the playbook - each bounded, each read the same for a mail, a chat line or anything the chat put on the table
    for f_ in (draft_line, thread_line, related_line, notes_line):
        try: lines.append(f_(store, item, target_kind, target_id))
        except Exception as e: logger.debug(f'advisor: {f_.__name__} skipped for {item.get("key")} - {e}')
    # THE OWNER'S OWN USUAL with this sender, counted from what they did (usual.py): how soon they answer, when they put this mail off
    # to, whom they hand it to - so a line can say "you usually answer Erin within the hour; this is 3h", and Hand it to a person can
    # rest on whom the owner hands this kind of ask to
    lines += _usual(store, item, target_kind, target_id)[0]
    lrn = _learned(store, item)
    if lrn: lines.append("WHAT YOU KNOW ABOUT HOW THE OWNER WORKS (learned from what they did; weigh it against this item's facts; cite a line by "
                         "its id when your line rests on it):\n" + lrn)
    led = [f"out{r['Id']}: {outcomes._sentence(store, r)}" for r in outcomes.rows_for(store, target_kind, target_id) if r.get('ResolvedAt')][:5]
    led += [f"{v['label']}: {measured(v['verb'], c)}" for v in verbs for c in [habit(store, v['verb'], item)] if measured(v['verb'], c)]
    if led: lines.append('THE OUTCOME LEDGER (what came of actions like this):\n' + '\n'.join(led))
    try: lines += [playbook_line(store, target_kind, target_id), owner_line(store)]
    except Exception as e: logger.debug(f'advisor: no playbook or owner docs for {item.get("key")} - {e}')
    if tier >= 2:                                         # the bigger read, only for the item on the table
        from .counsel import dossier
        m = store.get_message(item.get('mid')) if item.get('mid') else None
        try: dos = dossier(store, {'from_email': (m or {}).get('FromEmail', ''), 'from_name': (m or {}).get('FromName', ''), 'subject': (m or {}).get('Subject', '')}, calendar=False) if m else ''
        except Exception: dos = ''
        if dos: lines.append('WHAT THE HUB KNOWS:\n' + dos[:1500])
        more = outcomes.evidence(store, (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'), limit=15)
        if more: lines.append('RECENT OUTCOMES:\n' + '\n'.join(more))
    return _bounded(lines)


def is_goal(t) -> bool:
    from .store import is_goal as g
    return g(t)


def idea_line(store, idea_id, item: dict) -> str:
    """THE IDEA: what the Advisor raised, why, and - for a follow-up - whom it waits on and how long they have been quiet."""
    i = store.get_idea(int(idea_id)) or {}
    try: a = json.loads(i.get('ActionJson') or '{}') or {}
    except ValueError: a = {}
    bits = [f"\"{_one(i.get('Text') or item.get('title'), 300)}\"", f"raised {str(i.get('LastSaid') or i.get('FirstSeen') or '')[:16]}"]
    if a.get('why'): bits.append(f"why: {_one(a['why'], 200)}")
    # ...a follow-up says how long they have been quiet against their own day (funnel.slipped_followup, the rail's one rule)
    if a.get('type') == 'followup':
        from . import funnel
        try: lane, late, quiet, day = funnel.slipped_followup(store, a)
        except Exception: lane = None
        if lane == 'forgotten': bits.append(f"{a.get('who_email') or 'they'} quiet {quiet} days - late for them after {day}")
        elif lane == 'answered': bits.append('they have answered since')
    return f"THE IDEA (the assistant raised it; {i.get('Kind') or 'idea'}): " + '; '.join(bits)


def goal_line(store, t: dict) -> str:
    """THE GOAL: what done looks like, each open step with who holds it and its day (late said in days), and when anything last moved -
    or that nothing has."""
    from .processing_unread import goal_facts, holder_name
    now, tid = datetime.now(), int(t['TaskId'])
    g = goal_facts(store, t, tid, now)
    today, steps = now.strftime('%Y-%m-%d'), []
    for k, x in enumerate(store.goal_steps(tid), 1):
        if x['done']: continue
        c = x.get('child') or {}
        who = holder_name(c.get('Assignee')) or ('you' if not c or c.get('Status') == 'open' else '')
        due = str(c.get('DueAt') or '')[:10]
        late = (now - datetime.strptime(due, '%Y-%m-%d')).days if due and due < today else 0
        steps.append(f"step {k} \"{_one(x['text'], 80)}\"" + (f" held by {who}" if who else '') + (f", due {due}" if due else '')
                     + (f" - {late} days late" if late else ''))
    news = f"last news {g['news_at'][:10]}" if g.get('news_at') else f"no news since it was set ({str(t.get('CreatedAt') or '')[:10]})"
    return (f"THE GOAL: done when {_one(t.get('DoneWhen'), 200)}; {g.get('steps_done', 0)} of {g.get('steps', 0)} steps done; {news}"
            + (f"; due {g['due']}" if g.get('due') else '') + ('\nOPEN STEPS: ' + ' | '.join(steps[:6]) if steps else ''))


def _checklist(t: dict) -> list:
    try: return [c for c in json.loads((t or {}).get('Checklist') or '[]') if isinstance(c, dict)]
    except (TypeError, ValueError): return []


def sent_line(store, target_kind, target_id) -> str:
    """WHAT WAS SENT, as evidence: the newest reply that went on the item, when, to whom, its words, and what came in since. The
    preview is the sender's ask, so with no word of the reply the line still said "Marcus is waiting for your clarifications"
    over a close-out reading Sent (2026-10-19) - the model reads whether anything is still owed; code only says what went."""
    r = store.sent_reply(task_id=int(target_id)) if target_kind == 'task' else store.sent_reply(message_id=int(target_id))
    # ...and a new message on a task whose reply already went: the reply was on the task, not on this message, and the line read the
    # new mail with no word of what the owner had already said (the deep dive, 2026-10-20)
    if not r and target_kind == 'message' and (tid := (store.get_message(int(target_id)) or {}).get('TaskId')):
        r = store.sent_reply(task_id=int(tid)); target_kind, target_id = ('task', tid) if r else (target_kind, target_id)
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


_ID = r'\b(?:out|mem|rv|task|msg|fs|sv|idea|lrn)\d+\b'
def plain(line: str, verb: str, label: str) -> str:
    """The owner reads the line, not the prompt: "You should stop_agent because out13 shows..." put the verb's id and the ledger's
    row id in the prompt box (2026-10-13). An id-shaped verb becomes its label; a cited id in brackets goes, one in the sentence
    becomes what it is."""
    t = re.sub(rf'\b{re.escape(verb)}\b', f'"{label}"', line) if '_' in verb else line
    t = re.sub(rf'\s*\((?:{_ID}[,\s]*)+\)', '', t)
    return ' '.join(re.sub(_ID, 'an earlier outcome', t).split())


_WORD = re.compile(r"[a-z0-9][a-z0-9'#./-]*")
_FILLER = frozenset('the and for you your with that this from have will what which when where should would could into about there their they '
                    'them then than also just does did can are was were has had its it is be to of on in at or an a do so if me my we us our'.split())
def _content(text: str) -> set:
    return {w.strip("'.-/") for w in _WORD.findall(str(text or '').lower()) if len(w) > 2 and w not in _FILLER}


def repeats_ask(line: str, asks: list) -> bool:
    """WHETHER THE LINE ONLY ASKS THE AGENT'S QUESTION AGAIN (the owner, 2026-10-21: "the Advisor must not repeat a question the agent
    is already asking"). An agent asking is answered in its own pane, right above the strip - the line over it says what ELSE the item's
    facts make right, or nothing. A line repeats a question when it carries most of the question's own words: its text whole (two
    words or more), or at least two thirds of its content words (and three or more)."""
    said = ' '.join(str(line or '').lower().split()); words = _content(said)
    for q in asks or []:
        q = ' '.join(str(q or '').lower().split()).rstrip('?. ')
        if not q: continue
        if ' ' in q and q in said: return True
        own = _content(q)
        if len(own) >= 3 and len(own & words) * 3 >= len(own) * 2: return True
    return False


def _asking(store, target_id) -> list:
    """The questions the task's agent is asking right now (workerstate: its open input_needed requests) - not a permission or a wall."""
    from . import workerstate
    try: st = workerstate.status(store, int(target_id))
    except Exception: return []
    return [r.get('text') for r in st.get('requests') or [] if r.get('kind') == 'input_needed' and r.get('text')]


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
    verbs = offered(store, item)
    if not verbs: return W(dropped='no actions')
    have = row(store, target_kind, target_id, rev, own)                      # two events in one poll: the second finds the first's row
    if judged(have, tier): return have['Id']
    # THE RULE DECIDES FIRST (the design, phase A): the model reads only where intent must be read - every other state is the
    # rulebook's, at once and outside the hourly cap, so an event on it asks nothing of the model
    from . import rulebook
    if not rulebook.decide(store, item, verbs)['ask']: return W(dropped='left to the rule')
    brain = llm or build_llm(store, job='advisor')
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
    # ...a verb with no line is an answer now: the obvious move is said by its lit button alone (the owner, 2026-10-23)
    if not verb: return W(dropped='nothing to say', model=model, evidence=ev)
    hit = _offered(verbs, verb)
    verb = hit['verb'] if hit else verb
    if not hit: return W(dropped=f'verb not offered: {verb}'[:120], model=model, line=line, evidence=ev)
    line = plain(line, verb, hit['label'])
    # the agent's own question is already on the owner's screen, in its pane: a line that asks it again is noise (the owner, 2026-10-21)
    if target_kind == 'task' and repeats_ask(line, _asking(store, target_id)):
        return W(dropped="repeats the agent's question", model=model, line=line, evidence=ev)
    # A HAND-OFF IS THE REASON FOR HAND IT TO A PERSON, NOTHING ELSE (the live memory A/B, 2026-10-26): "Ray handles overtime-rate
    # questions for you" stood over an agent's button, citing the very hand-offs it was counted from - the line said one move, the button
    # another. The rule's move stands instead
    if verb != 'forward' and target_kind in ('task', 'message') and set(ev) & _usual(store, item, target_kind, target_id)[1]:
        return W(dropped='a hand-off reason over another verb', model=model, line=line, evidence=ev)
    kind = d.get('kind') if d.get('kind') in KINDS else 'other'
    rid = W(line=line, verb=verb, label=hit['label'],count=habit(store, verb, item), evidence=ev, model=model, kind=kind)
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



def failure(store, item: dict) -> dict | None:
    """What last failed on the item - {what, why, fix, unknown, kind} - or None: a draft whose send failed or never answered, else the
    newest act on it that ended in an error. The Advisor was never told, so it advised the Send that had just failed (2026-10-18)."""
    ok = lambda f: f if isinstance(f, dict) and f.get('label') and f.get('href') else None
    r = (store.get_review(int(item['rid'])) if item.get('rid') else None) or (store.pending_review(int(item['tid'])) if item.get('tid') else None) or {}
    try: ops = store.operations_for(item.get('tid'), [item['mid']] if item.get('mid') else [])
    except Exception: ops = []
    last = ops[-1] if ops else {}
    try: out = json.loads(last.get('OutcomeJson') or '{}') or {}
    except (TypeError, ValueError): out = {}
    out = out if isinstance(out, dict) else {}
    drafted_wrong = r.get('Status') == 'pending' and r.get('DraftError')
    # ...WHICHEVER FAILED LAST (the matrix, 2026-10-20): a failure newer than the draft's error is what the screen shows now
    newer = last.get('Status') in ('error', 'refused') and out.get('source') != 'draft'
    # A DRAFT THAT COULD NOT BE WRITTEN is what failed (2026-10-19): with no AI to write it, Reply left an empty box and an error, and
    # the Advisor - never told - read the box with no Send as a chat's draft and said "copy it ... then mark it done" over an email
    if drafted_wrong and not newer:
        from .failures import classify
        c = classify(str(r['DraftError']))
        return {'what': 'the reply could not be drafted', 'why': c['sentence'], 'fix': ok(c['fix']), 'unknown': False, 'kind': 'draft'}
    if r.get('DeliveryState') in ('failed', 'unknown'):
        try: env = json.loads(r.get('Deliver') or '{}') or {}
        except (TypeError, ValueError): env = {}
        why = re.sub(r'^Not sent:\s*', '', str(r.get('Reason') or '')).rstrip('.')
        return {'what': 'the reply was not sent' if r['DeliveryState'] == 'failed' else 'the reply may not have gone',
                'why': why, 'fix': ok(env.get('fix')) if isinstance(env, dict) else None, 'unknown': r['DeliveryState'] == 'unknown', 'kind': 'send'}
    # ...and a report's card or a connection's row has no task: its failure lives on the report or the connector (failures.standing)
    from . import failures
    if (on := failures.target_of(item)) and (f := failures.standing(store, *on)): return f
    # ...and AN AGENT'S RUN THAT FAILED (the deep dive, 2026-10-20): it reached the prompt only as "run ended (failed)", so the line said
    # "it stopped partway - pick it up" and lit Continue into the same unreachable database. An act that failed since outranks it.
    if last.get('Status') not in ('error', 'refused') and (ran := agent_failed(store, item)): return ran
    # ...and an act the demo refused (demo.refused): it went nowhere, so the Send just refused is not advised again (2026-10-19)
    if last.get('Status') not in ('error', 'refused'): return None
    if out.get('source') == 'draft': return None          # a draft written since cleared it
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


def agent_failed(store, item: dict) -> dict | None:
    """The task's agent run, when its last state is failed: {what, why, ...} in failure()'s shape, its why the run's own last words."""
    if not item.get('tid'): return None
    from . import workerstate
    try: st = workerstate.status(store, int(item['tid']))
    except Exception: return None
    if st.get('state') != 'failed': return None
    last = next((e for e in reversed(workerstate.events(store, int(item['tid']), st.get('sid'))) if e['Kind'] == 'failed'), {})
    # ...in plain words, with the place that fixes it (failures.classify): an agent with no AI to run on is fixed by connecting one -
    # it lit "New task to fix this" and turned connecting an AI into another task (owner-approved, 2026-10-21)
    from .failures import classify
    c = classify(_one(st.get('result') or last.get('Text'), 300) or 'it stopped without saying why')
    return {'what': "the agent's run failed", 'why': c['sentence'], 'fix': c['fix'], 'unknown': False,
            'kind': 'agent', 'source': 'agent', 'cause': 'taskuary'}


def _retryable_agent(store, item: dict) -> bool:
    """Can the failed run be tried again from its step: a general agent's saved conversation, with nothing live on it."""
    tid = item.get('tid')
    if not tid: return False
    from . import workerstate
    return workerstate._live(int(tid)) is None and concierge._general(store, item)


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


NOT_MOVES = frozenset({'priority', 'assign', 'change_kind', 'pick_repo', 'attach', 'close_note', 'next'})


def offered(store, item: dict) -> list:
    """THE ITEM'S REAL BUTTONS, AND NOTHING IT CANNOT DO: the verbs its row carries minus Next - chips_for, which already drops
    what this install cannot do (capabilities.py: no Send on a draft whose channel cannot send, no coding agent with no
    coding tool) - plus the row's own fix when a send failed and named the place that fixes it, under that place's own name.
    An agent waiting on the owner carries Answer it there (chips_for) - its card once offered only End and Remind me, which the
    prompt forbids for someone waiting, so the Advisor stood silent (2026-10-17 audit). Not added here: a paused, stalled or
    stopped agent has nobody listening, and the row knows which is which.
    THE BUTTONS THE ROW ACTUALLY DRAWS (the design, phase A, 2026-10-23): the verbs came from chips_for while the row drew row_buttons -
    why Review changes, Chase and Accept could never be lit, and why "Not ours" was picked on a task whose row has no Not ours. Only
    the row's moves count: its pickers (who does it, priority, assignee, the code's place), Attach and Close with a note set a field or
    add to a move, and are never the move. Chase joins where the rulebook says a wait has run past its day (rulebook.adds)."""
    from . import rulebook
    verbs = [buttons.chip(b['verb']) | {'label': b['label']} for b in concierge.row_buttons(store, item) if b['verb'] not in NOT_MOVES]
    # ...in the item's own order (its vocabulary, chips_for - a draft's Send first), the row's other moves after it
    first = [c['verb'] for c in concierge.chips_for(store, item)]
    verbs.sort(key=lambda v: first.index(v['verb']) if v['verb'] in first else len(first))
    verbs += [buttons.chip(v) for v in rulebook.adds(store, item) if v not in {x['verb'] for x in verbs}]
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
    # ...and A GENERAL AGENT'S RUN THAT FAILED with nothing named to fix is tried again from its saved conversation - the step's own
    # Continue, said as Try again (owner-approved, 2026-10-21). A coding agent's keeps New task: Continue reopened it into the same
    # unreachable database (the 2026-10-20 deep dive)
    # ...when it can start again from here: with no brain to run on, Try again is greyed on the page, and New task stands in for it (the
    # Advisor audit's judge, 2026-10-26 - a lit Try again nobody could press left nothing lit at all)
    elif f and f.get('kind') == 'agent' and _retryable_agent(store, item) and not _agent_ready(store, item):
        lead.append(buttons.chip('continue') | {'label': buttons.label('try_again'), 'hint': buttons.hint('try_again')})
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
    return {'key': r['Key'], 'line': plain(r['Line'] or '', r['Verb'] or '', lbl or '') if r.get('Line') else r.get('Line'), 'verb': verb, 'label': lbl, 'pill': lbl or '', 'count': count[:2],
            'evidence': json.loads(r.get('EvidenceJson') or '[]'), 'revision': r['Revision'], 'tier': r['Tier'], 'at': r['CreatedAt']}


def _at_work(store, target_kind: str, target_id) -> bool:
    """An agent at work on the task is nothing for the owner to do. Its continue writes no event the revision sees until the
    prompt lands, so "the agent stopped and is waiting on you" stood over an agent already continued (the owner, 2026-10-13)."""
    if target_kind != 'task': return False
    from . import workerstate
    try: return workerstate.status(store, int(target_id)).get('state') == 'working'
    except Exception: return False


def for_key(store, key: str) -> dict: return decide(store, key)


# ── ONE DECISION (the design, phase A; the owner's rulings, 2026-10-23) ──────────────────────────────────────────────────────────────
# Every surface - the desk canvas, the Tasks tab, a phone chat, the desk at phone width - reads THIS: the button lit and the line said,
# picked only from the buttons the row draws (offered). Two tiers, the higher outranking the lower but never a safety rule (the press
# habit that lit a button by itself, with its mark, went with the press learning - the owner, 2026-10-25):
#   model  where intent must be read (rulebook `ask`): its verb stands where it differs from the rule's, with its line - and what the
#          memory knows about how the owner works is in what it read
#   rule   rulebook.py - every other state, at once, from facts the app keeps, with no "Thinking..." and outside the hourly cap
# A line is said only for a fact the card does not show; the obvious move is an empty strip and its button lit (ruling 1). The item on
# the table earns the model's bigger read, once (B5); the next two on the walk are read ahead, so their lines are there when Next is.
PREREAD = 2



def _whole_words(s: str, n: int) -> str:
    """At most n characters, cut at a word: "she's your manag…" read as a slip (the live memory A/B, 2026-10-26)."""
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[:n - 1].rsplit(' ', 1)[0].rstrip(',;:-– ') + '…'


def _label(verbs: list, verb: str, item: dict) -> str:
    if verb == 'next': return buttons.label('next', 'batch') if (item or {}).get('kind') == 'fyis' else buttons.label('next')
    return next((v['label'] for v in verbs if v['verb'] == verb), None) or buttons.label(verb) or verb


def decide(store, key: str, preread: bool = True) -> dict:
    """The Advisor's one decision for the item keyed `key`: {key, state, verb, label, line, by, revision, ...} - `verb` None lights
    nothing (an agent asking is answered in its pane, a closed task's Reopen stays outlined), `line` '' says nothing. {} for a key with
    nothing to decide on; {"none": "no_ai"} where the move needs an AI and none is connected; {"none": "off"} with the Advisor off."""
    from . import rulebook
    tgt = target_of(store, key)
    if not tgt: return {}
    if str(store.get_setting(ON_KEY, '1') or '1') != '1': return {'key': key, 'none': 'off'}
    rev = revision(store, *tgt)
    # an agent at work is nothing for the owner to do, whatever the card was judged as (the owner, 2026-10-13)
    if _at_work(store, *tgt): return {'key': key, 'state': 'working', 'verb': 'next', 'label': buttons.label('next'), 'line': '', 'by': 'rule',
                                      'revision': rev, 'pill': '', 'evidence': [], 'ask': False, 'needs_ai': False}
    item = _item(store, *tgt, key=key)
    if not item: return {}
    verbs = offered(store, item)
    r = rulebook.decide(store, item, verbs)
    verb, line, by, ev = r['verb'], r['line'], 'rule', list(r.get('evidence') or [])
    kind = rulebook.KIND.get(r['state'], 'rule')
    rs = _at(store, tgt[0], tgt[1], rev)
    # only the rows written for THIS item (keys_of): a line judged over the same task's other card is not this one's
    own = _own(store, tgt, key, rs); rs = [x for x in rs if x.get('Key') in own]
    m = row(store, tgt[0], tgt[1], rev, own)
    if r['ask']:
        mv = concierge.canon_verb(m['Verb']) if m and m.get('Verb') else None
        hit = next((v for v in verbs if v['verb'] == mv), None) if mv else None
        # ...A STATE ASKED ONLY FOR ITS MEMORY (rulebook.memory_on) is changed only by an answer resting on that memory: asked about a late
        # step because a line named its holder, the model swapped Chase's Remind me for "Ask the sender" on the age alone (live A/B, 2026-10-26)
        if hit and r.get('memory') and not set(json.loads(m.get('EvidenceJson') or '[]')) & memory_ids(store, item, *tgt): hit = None
        # ...AND AN ANSWER RESTING ON A MEMORY LINE THE OWNER PUT DOWN rests on nothing (the Advisor audit's judge, 2026-10-26): Wrong on
        # a line left the task saying it - the rule's move stands until the item changes and the model reads it again
        if hit and withdrawn(store, json.loads(m.get('EvidenceJson') or '[]')): hit = None
        # the model's verb stands where it differs from the rule's - with its line, the reason the lit button is not the one you would
        # guess; agreeing, the rule's fact stands and the model's sentence goes (ruling 1: no explanation of the obvious button)
        if hit and mv != verb:
            verb, by, ev, kind = mv, 'model', json.loads(m.get('EvidenceJson') or '[]'), m.get('Kind') or 'other'
            line = '' if r['state'] == 'idea' else _one(plain(m.get('Line') or '', m['Verb'], hit['label']), 64)
        # ...AND AGREEING, A MEMORY REASON IS SAID (the live memory A/B, 2026-10-26): "You answer Erin the same day" and "Paula takes
        # W-9s now" were read, used, and dropped for agreeing with the lit button - the memory never reached the strip. A line that cites
        # a memory line or a counted usual (memory_ids) is a fact the card does not show; it stands in the rule's place, one line - unless
        # the rule's own line is already a counted usual (asked_late: it carries its evidence)
        elif hit and r['state'] != 'idea' and m.get('Line') and not (line and r.get('evidence')):
            mev = json.loads(m.get('EvidenceJson') or '[]')
            if set(mev) & memory_ids(store, item, *tgt):
                by, ev, line, kind = 'model', mev, _whole_words(plain(m['Line'], m['Verb'], hit['label']), 60), m.get('Kind') or 'memory'

        # NEVER LEFT GUESSING (the owner, 2026-10-15): the item on the table is read now, at this revision, once - the rule's button
        # stands lit meanwhile, and the model's answer arrives by the `advice` live event the page already reads
        if not mv and not judged(m, 2): notice(store, m['Event'] if m else SHOWN, tgt[0], tgt[1], tier=2, key=key)
        if not mv and r['state'] in rulebook.NEEDS_AI and rs and rs[0].get('Dropped') == 'no brain':
            return {'key': key, 'none': 'no_ai', 'state': r['state'], 'revision': rev, 'line': ''}
    if preread: _preread(store, key)
    d = checked(store, item, verbs, {'key': key, 'state': r['state'], 'verb': verb, 'line': line, 'by': by, 'evidence': ev, 'kind': kind},
                {'verb': r['verb'], 'line': r['line'], 'evidence': list(r.get('evidence') or [])})
    verb, line, by, ev = d['verb'], d['line'], d['by'], d['evidence']
    lbl = _label(verbs, verb, item) if verb else ''
    out = {'key': key, 'state': r['state'], 'verb': verb, 'label': lbl, 'line': line, 'by': by, 'revision': rev, 'pill': lbl, 'evidence': ev,
           'ask': r['ask'], 'needs_ai': r['state'] in rulebook.NEEDS_AI, 'kind': d['kind'], **({'checked': d['checked']} if d.get('checked') else {})}
    # a fix is a place, not a proposal: the page opens its href where the row has no '<rid>:fix' of its own to press (a failed act with
    # no draft on the table) - read live, so a fix already made carries no stale link
    if verb == 'fix':
        try: f = delivery_fix(store, item) or (failure(store, item) or {}).get('fix')
        except Exception: f = None
        if f: out['href'] = f['href']
    # ...and the task "New task to fix this" makes, read live the same way
    if verb == 'new_task':
        try: f = failure(store, item)
        except Exception: f = None
        if f: out['task'] = fix_task(store, item, f)
    kept(store, out)
    return out


# ── THE CHECK AFTER THE ADVISOR DECIDES (the Advisor audit's judge, 2026-10-26) ─────────────────────────────────────────────────────────
# The model still decides; this only refuses a pick the owner could not press or that contradicts its own reason's KIND (the model states
# it, a rule's state carries it - never the line's words), and falls to the next sensible move the row can press. Four failures it ends:
# a lit Try again greyed for want of an AI (nothing lit at all), "the draft promises Friday" beside a dark Send, a late line on a drafted
# task lighting Reply over the draft's own Send, and the survivor of a duplicate pair folded into its own twin. Each refusal is logged.
AGENT_VERBS = frozenset({'continue', 'regular_agent', 'run_another', 'strong_again'})
AGENT_CHECK = True       # the suite turns this off (tests/conftest.py): a bare store has no brain, and its agents' buttons are not the subject


def _agent_ready(store, item: dict) -> str:
    """'' when an agent can start on the item from here, else why not - the page's own check (capabilities.cannotStart: an AI, and a brain a
    general hand-off can choose), so the Advisor never lights a button the page greys."""
    if not AGENT_CHECK: return ''
    from . import capabilities, general, agents as ha
    try:
        if not capabilities.has_ai(store): return 'no AI is connected'
        brains = dict(ha.connection_brains(store))
        ok = any(o.get('type') != 'cli' or ha.runs_here(brains.get(o['pick'][4:])) for o in general.provider_options(store))
        return '' if ok else 'no brain an agent can run on'
    except Exception as e: logger.debug(f'advisor: no agent check for {item.get("key")} - {e}'); return ''


def pressable(store, item: dict, verb: str, verbs: list) -> str:
    """'' when the row carries `verb` and it can be pressed now, else why not."""
    if not verb or verb == 'next': return ''
    if verb not in {v['verb'] for v in verbs}: return 'not on the row'
    return _agent_ready(store, item) if verb in AGENT_VERBS else ''


def checked(store, item: dict, verbs: list, d: dict, rule: dict) -> dict:
    """`d` ({verb, line, by, evidence, kind, state}) as the owner may be shown it: unchanged, or its verb refused (`checked` says why) and the
    next sensible pressable move lit - the line kept where it is still the reason for that move, else the rule's own line."""
    from . import rulebook
    verb, kind, why, instead = d['verb'], d.get('kind') or 'other', '', []
    drafted = 'approve' in {v['verb'] for v in verbs}
    if (no := pressable(store, item, verb, verbs)): why = f'{verb}: {no}'
    elif kind == 'draft_caution' and verb == 'approve': why, instead = 'a caution about the draft over its Send', ['redraft']
    elif kind == 'late' and verb == 'reply' and drafted: why, instead = 'late on a drafted task: the draft is the answer', ['approve']
    elif kind == 'same_ask' and verb in ('remove', 'split') and _survives(store, item): why = 'the survivor of a duplicate pair is never folded'
    if not why: return {**d, 'kind': kind}
    lit = (rulebook.RULES.get(d.get('state')) or {}).get('lit') or []
    pick = next((v for v in [*instead, rule['verb'], *lit] if v and v != verb and not pressable(store, item, v, verbs)
                 and not (kind == 'draft_caution' and v == 'approve')), 'next')
    keep = pick in instead                       # the line is still this move's reason
    logger.info(f"advisor: {d['key']} {verb} refused ({why}) - {pick} lit instead")
    if keep: return {**d, 'verb': pick, 'kind': kind, 'checked': why}
    same = pick == rule['verb']
    return {**d, 'verb': pick, 'by': 'rule', 'kind': rulebook.KIND.get(d.get('state'), 'rule'), 'checked': why,
            # ...a failure is the fact whatever is lit (rulebook.decide), so its line stays over the move that gets past it
            'line': rule['line'] if (same and pick != 'next') or d.get('state') in rulebook.FAILED else '', 'evidence': rule['evidence'] if same else []}


def _survives(store, item: dict) -> bool:
    from . import rulebook
    tid = item.get('tid')
    dup = rulebook.same_thread(store, item) if tid else None
    return bool(dup) and rulebook.survivor(store, tid, dup) == int(tid)


def withdrawn(store, ev: list) -> bool:
    """Whether an answer cites a memory line no longer in the document - put down (Wrong, Forget) or replaced since it was read."""
    from . import learned_cut
    want = [e for e in ev or [] if str(e).startswith('lrn')]
    return bool(want) and not set(want) <= set(learned_cut.cited(store, want))


# THE DECISION, KEPT (the Advisor audit's judge, 2026-10-26): every surface reads decide - the stored row is what a Wrong or Forget on a
# memory line finds to re-read: the items whose decision rested on it are named in the `advice` event, and their pages ask again
def kept(store, d: dict):
    try: store._exec('INSERT OR REPLACE INTO advice_decision (Key, Stamp, Json, At) VALUES (?,?,?,?)', (d['key'], d.get('revision') or '', json.dumps(d), _now()))
    except Exception as e: logger.debug(f"advisor: decision for {d.get('key')} not kept - {e}")


def resting_on(store, ids) -> list:
    """The keys whose kept decision cites any of `ids` (a memory line's cite id, its evidence)."""
    want = {str(i) for i in ids or () if i}
    out = []
    for r in store._rows("SELECT Key, Json FROM advice_decision WHERE Key NOT LIKE 'pair:%'"):
        try: ev = set(json.loads(r['Json']).get('evidence') or [])
        except ValueError: continue
        if ev & want: out.append(r['Key'])
    return out


def forgot(store, cite: str, ev=()) -> list:
    """A memory line put down: each item whose decision rested on it is re-read (its `advice` event), so it stops saying it. The keys."""
    keys = resting_on(store, [cite, *(e for e in ev if not str(e).startswith('msg'))]) if cite else []
    for k in keys:
        store._exec('DELETE FROM advice_decision WHERE Key=?', (k,))
        tgt = target_of(store, k)
        if tgt: _emit(k, *tgt)
    return keys


def rests(store, d: dict) -> list:
    """What a decision rests on, in words, for Why?: each evidence id as its label, and a memory line with its key - so Keep, Wrong and
    Forget can be pressed on it from the task (the judge's F5)."""
    from . import learned_cut
    from .learnedgraph import _resolve, TAG
    ev = list(d.get('evidence') or [])
    hits = learned_cut.cited(store, [e for e in ev if str(e).startswith('lrn')])
    out = []
    for e in ev:
        if e in hits:
            raw, k, s = hits[e]
            m = TAG.match(raw)
            out.append({'id': e, 'kind': 'memory', 'key': k, 'own': not m, 'section': s,
                        'label': (m.group('text') if m else raw.strip().lstrip('-* ')).strip()})
        else:
            try: r = _resolve(store, e)
            except Exception: r = {}
            if r.get('label') and r.get('label') != e: out.append({'id': e, 'kind': r.get('kind') or '', 'label': r['label']})
    return out


def _preread(store, key: str):
    """THE NEXT TWO, READ AHEAD (the design, 1.1): where their state asks the model, it is asked now, in the background, so the line is
    there when Next brings them - never a button that changes under the owner's hand a moment after the item opens."""
    if not BACKGROUND: return
    def go():
        try:
            from . import funnel, rulebook
            items = funnel.pile(store, quiet=True).get('items') or []
            at = next((n for n, i in enumerate(items) if key in keys_of(i)), None)
            for it in (items[at + 1:at + 1 + PREREAD] if at is not None else []):
                tgt = target_of(store, it.get('key'))
                if tgt and rulebook.decide(store, it, offered(store, it))['ask']: notice(store, SHOWN, tgt[0], tgt[1], tier=1, key=it['key'])
        except Exception as e: logger.debug(f'advisor: no read ahead of {key} - {e}')
    threading.Thread(target=go, daemon=True, name='advise-ahead').start()


# WHY NOTHING IS LIT, in one word the page reads - only no AI is said, with its way out (words.json advice_none): "Thinking...", "No
# suggestion...", "Nothing to decide..." went (the owner, 2026-10-23); every other state is the rule's lit button, or silence
REASONS = tuple(words.ADVICE_NONE)
def status(store, key: str) -> dict:
    """decide, or {'none': 'nothing'} for a key nothing is decided on (a meeting row, a connection): the page lights Next, silent."""
    d = decide(store, key)
    if not d: return {'none': 'nothing'}
    # ...with what its line rests on, in words: the Advisor section's Why? and the clock menu read THIS, never older rows (the judge, 2026-10-26)
    if d.get('line'):
        try: d['rests'] = rests(store, d)
        except Exception as e: logger.debug(f'advisor: no rests for {key} - {e}')
    return d


# ── LIT AND PRESSED (the deep dive, 2026-10-20) ─────────────────────────────────────────────────────────────────────────────────
# Nothing recorded whether the button the Advisor lit was the one pressed, so its record and the owner's habits were the same guess.
# Every press sends the advised verb (if a line showed) and the revision it was judged at; the row keeps what the item was and whom it
# was from. Since phase B (2026-10-23) every press on every surface is kept, lit or not (presses.py) - as a record: nothing is learned
# from a press any more (the owner, 2026-10-25). Nothing on screen changes.
_ROW = {r: v for v, d in buttons.VERBS.items() for r in d.get('row') or []}


def pressed_verb(pressed: str) -> str:
    """A row id or a verb -> the verb: `done` is close, `<rid>:approve` is approve, an old word lands on today's."""
    p = str(pressed or '').strip()
    last = p.split(':')[-1]
    return concierge.canon_verb(_ROW.get(last) or last) or last


def who_of(store, item: dict) -> dict:
    """{sender, domain, scope, thread} for an item: its newest inbound message's address and domain, and its SCOPE - the repository a
    code item came from (its connection's name), else the sender's domain, else the channel - the grain a move is learned at."""
    mid = item.get('mid')
    m = store.get_message(int(mid)) if mid else None
    if not m and item.get('tid'):
        ms = [x for x in store.list_messages(int(item['tid'])) if str(x.get('Direction') or 'in') != 'out']
        m = ms[-1] if ms else None
    m = m or {}
    sender = str(m.get('FromEmail') or m.get('FromName') or '').lower()          # a chat or an issue has a name, not an address
    domain = sender.rsplit('@', 1)[1] if '@' in sender and not sender.startswith('@') else ''
    channel = str(item.get('channel') or m.get('Channel') or '').lower()
    scope = (m.get('SourceName') if channel in ('github', 'gitlab', 'azdo', 'bitbucket') and m.get('SourceName') else '') or domain or channel
    return {'sender': sender, 'domain': domain, 'scope': str(scope or '').lower(), 'thread': m.get('ConversationId') or '', 'channel': channel}


def press(store, key: str, advised: str, pressed: str, rev: str = None, surface: str = 'desk', lit: str = None, live: list = None,
          item: dict = None) -> int:
    """One press on `key`, on any surface, lit or not (presses.record keeps it - phase B, 2026-10-23: only a desk press under a line was
    kept). `advised`: the Advisor's verb if its line showed, judged at `rev`. Returns the row id, or 0 when nothing was kept."""
    from . import presses
    rid, _ = presses.kept(store, key, pressed, surface, lit=lit, live=live, rev=rev, advised=advised or '', item=item)
    # ...and nothing more: a press is not a fact about how the owner works (the owner, 2026-10-25), and never a correction for the
    # reflection, which writes what TRIAGE reads (2026-10-23)
    return rid


def notes(store, key: str, limit: int = 10) -> list:
    """The receipt: what it decided and what it dropped, per revision, with the evidence resolved to labels."""
    from .learnedgraph import _resolve
    tgt = target_of(store, key)
    if not tgt: return []
    out = []
    for r in rows(store, tgt[0], tgt[1], limit):
        ev = [{'id': e, **{k: v for k, v in (_memory_line(store, e) or _resolve(store, e)).items() if k in ('kind', 'label')}}
              for e in json.loads(r.get('EvidenceJson') or '[]')]
        out.append({'at': r['CreatedAt'], 'event': r['Event'], 'tier': r['Tier'], 'line': r['Line'], 'verb': r['Verb'], 'label': r['Label'],
                    'pill': (r['Label'] or '') if r.get('Verb') else '', 'dropped': r['Dropped'],
                    'model': r['Model'], 'evidence': ev})
    return out


def block(store, item: dict, d: dict | None = None) -> str:
    """The Advisor's line for the chat's system prompt, so 'why?' is answered from its evidence - a lookup, not a think. `d`: the
    decision already read for the item (the chat's CANVAS reads it once for its lit button and this line)."""
    if d is None: d = decide(store, (item or {}).get('key') or '', preread=False) if item else {}
    if not d.get('verb'): return ''
    # the button's name and what the evidence SAYS: "verb stop_agent; evidence: out13" was handed to the chat as-is, and came
    # back to the owner in its answer (2026-10-17 audit)
    ev = '; '.join(filter(None, (evidence_words(store, e) for e in d.get('evidence') or []))) or 'the item itself'
    # ...a silent decision is its lit button alone (the owner, 2026-10-23), decided by the rule from the item's own facts
    said = f"\"{d['line']}\" - its button is {d['label']}" if d.get('line') else f"no line - its lit button is {d['label']}"
    return (f"THE ADVISOR'S LINE on this item (if the owner asks why, this is the answer; the numbers are the ledger's): "
            f"{said}; it rests on: {ev}.")


def evidence_words(store, ev_id: str) -> str:
    """One evidence id as what it says: an outcome as the ledger's own sentence, anything else as the label it resolves to."""
    try:
        if str(ev_id).startswith('out'):
            from . import outcomes
            r = store._one('SELECT * FROM outcome WHERE Id=?', (int(ev_id[3:]),))
            return outcomes._sentence(store, r) if r else ''
        from .learnedgraph import _resolve
        lbl = (_memory_line(store, ev_id) or _resolve(store, ev_id)).get('label')
        return '' if lbl == ev_id else str(lbl or '')
    except Exception: return ''


def _memory_line(store, ev_id: str) -> dict | None:
    """A cited memory line (learned_cut.cite_of) as what it says - {kind: 'memory', label: the line without its tag} - or None for any
    other id. Why? said "lrn123" to someone who never wrote code."""
    if not str(ev_id).startswith('lrn'): return None
    from . import learned_cut
    from .learnedgraph import TAG
    hit = learned_cut.cited(store, [ev_id]).get(ev_id)
    if not hit: return {'kind': 'memory', 'label': ''}           # Forgotten or replaced since: it rests on nothing now
    m = TAG.match(hit[0])
    return {'kind': 'memory', 'label': (m.group('text') if m else hit[0].strip().lstrip('-* ')).strip()}
