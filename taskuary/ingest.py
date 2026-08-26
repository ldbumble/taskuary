"""Ingest: anything -> the funnel. No vendor connectors baked in - push messages via the
HTTP API (POST /api/ingest/push) or your own plugin; report connections run on schedule.

Pipeline per message: dedup -> deterministic policy -> route to a task -> intent triage
(task / reply_only / fyi) -> file or create. Real tasks NEVER get an auto reply-draft:
answering is the responder's job (reply_only), doing is the coder's.
"""
import json, re, threading
from loguru import logger
from .routing import route, draft_task_fields, tokens
from .policy import evaluate
from .triage import classify_intent, heuristic_intent
from .store import task_ref


# What the agent is TOLD about work from each kind of source. An email needs nothing -
# the mail is the prompt - but a pull request is a judgement call before it is a coding
# task, and the judging instructions should not depend on whoever typed the dispatch.
# Both are defaults: the GitHub card's prompt_pr / prompt_issue fields override them, and
# any other trigger connector can set task_prompt for its own items.
PR_RULES = (
    'This task came from a PULL REQUEST, possibly by an outside contributor. Judge it before '
    'touching anything: does it solve a real problem worth having? Is the change minimal, safe '
    'and in keeping with the codebase - no license or dependency swaps, nothing touching CI, '
    'release or security-sensitive files unless that is explicitly the point? Check out the PR '
    'branch, read the WHOLE diff, run the tests. Do NOT merge, close or push anything: end with '
    'a clear verdict - accept, request changes (say exactly which), or reject - and your reasons.')
ISSUE_RULES = (
    'This task came from a GITHUB ISSUE. Reproduce it first if you can. Judge whether it is a '
    'real defect or a feature worth building; fix it when the fix is contained and safe, '
    'otherwise report plainly what it would take and what the risks are.')


def source_rules(store, msg: dict) -> str:
    """The standing instruction for work from this message's source, if its connector has one.
    Resolution: the message's own source row names its connector (an email can be Outlook OR
    Gmail); otherwise the channel's type-named connector. GitHub picks PR vs issue rules off
    the ingest header and falls back to the shipped defaults above."""
    ch = (msg or {}).get('Channel')
    if not ch or ch == 'report': return ''
    src = next((s for s in store.list_sources(active_only=False)
                if s.get('Channel') == ch and s.get('Address') == msg.get('SourceName')), None)
    c = (store.get_connector(src['ConnectorId']) if src and src.get('ConnectorId') else None) \
        or store.get_connector_by_type(ch) or {}
    try: cfg = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    if ch == 'github':
        is_pr = '[pull request by' in str(msg.get('BodyText') or '')[:200]
        own = str((cfg.get('prompt_pr') if is_pr else cfg.get('prompt_issue')) or '').strip()
        return own or (PR_RULES if is_pr else ISSUE_RULES)
    return str(cfg.get('task_prompt') or '').strip()


def ingest_message(store, msg: dict, actor: str = 'router', llm=None, file_only: bool = False) -> dict:
    """file_only = this connection is a FEED, not a trigger: the item is shown on the
    timeline and nothing else happens to it - no triage, no AI call, no task. It is a
    cheaper and quieter path than 'ignore', which is a verdict about the message."""
    if store.message_exists(msg.get('external_id') or ''):
        return {'status': 'duplicate', 'task_id': None, 'message_id': None}
    if file_only:
        mid = store.add_message({**_fields(msg, None), 'Status': 'feed'})
        store.add_route(mid, None, 'feed', None,
                        'shown for information - this connection is a feed, not a task trigger', [], 'feed')
        return {'status': 'feed', 'task_id': None, 'message_id': mid}
    cfg = store.get_settings()
    pol = evaluate(msg, store.list_policies(), store.known_sender(msg.get('from_email')),
                   cfg.get('default_action', 'draft'))
    if pol['action'] in ('skip', 'ignore'):
        # skip = stored for dedupe but NEVER shown (flood senders); ignore = shown, no task
        mid = store.add_message({**_fields(msg, None), 'Status': 'skipped' if pol['action'] == 'skip' else 'ignored'})
        store.add_route(mid, None, pol['action'], None, f"policy '{pol['rule']}': {pol['reason']}", [], 'policy')
        return {'status': pol['action'] + ('ped' if pol['action'] == 'skip' else 'd'), 'task_id': None, 'message_id': mid}

    r = route(msg, store.snapshots(), float(cfg.get('attach_threshold', 0.42)))
    new_rid = None                       # set when a fresh reply task opens a review below
    notes, notes_left = [], 0            # standing notes the classifier saw, and any that did not fit
    mine = owner_addresses(store)        # who "you" is on the To/Cc lines - every mailbox, not just this one
    def _notes_note():
        # a cap that goes unmentioned reads as "everything you told me was applied". It was
        # not, and only the owner can judge whether the notes that missed out mattered - so
        # every verdict this funnel writes down says it happened.
        return (f' · {len(notes)} of {len(notes) + notes_left} standing notes applied '
                '(the rest did not fit)' if notes_left else '')
    if r['decision'] == 'attach':
        tid = r['task_id']
        # ...unless the owner has already ruled on this kind of mail. A live agent session is
        # the one exception: it asked a question on this thread and the answer is arriving, so
        # the round trip outranks a standing verdict about the topic.
        busy = any(x['Status'] == 'running' for x in store.list_runs(tid))
        vetoed = '' if busy else veto(store, msg)
        if vetoed:
            mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
            store.add_route(mid, None, 'file', None,
                            f'your standing verdict says this is not ours, so it did not join '
                            f'{task_ref(tid)}: "{vetoed[:200]}"', [], 'memory')
            logger.info(f'ingest: filed by your own verdict instead of attaching to {task_ref(tid)}')
            return {'status': 'filed', 'task_id': None, 'message_id': mid}
        mid = store.add_message(_fields(msg, tid))
        store.add_comment(tid, actor, 'agent', f"New {msg.get('channel')} from {msg.get('from_email') or 'unknown'}: {msg.get('subject') or ''}")
        # the classic round trip: the agent asked something, the hub asked the person, and
        # THIS is their answer arriving on the same thread. With answer_to_agent=auto it is
        # typed straight into the live session; 'ask' leaves the one-click offer in the
        # panel; 'off' does neither. A dead session just means False - nothing breaks.
        if cfg.get('answer_to_agent', 'ask') == 'auto':
            try:
                from . import terminal
                terminal.say_to_task(store, tid, msg, actor)
            except Exception as e:
                logger.warning(f'answer_to_agent failed for task {tid}: {e}')
    else:
        # A standing verdict stops a task OPENING, not just a message attaching. This is where
        # "I have said twenty times that resident refunds are not ours" went wrong: veto() only
        # ever guarded the attach branch, so the same topic arriving on a fresh thread reached
        # the classifier as a NOTE - advice a model can weigh and, when its answer degrades
        # below, not read at all. A verdict the owner typed is not advice; it decides.
        vetoed = veto(store, msg, topic_only=True)
        if vetoed:
            mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
            store.add_route(mid, None, 'file', None,
                            f'your standing verdict says this is not ours, so no task was opened: '
                            f'"{vetoed[:200]}"', [], 'memory')
            logger.info(f"ingest: filed by your own verdict - {msg.get('subject') or ''}")
            return {'status': 'filed', 'task_id': None, 'message_id': mid}
        # AI-gated triage: without an active AI connector, nothing becomes a task on its
        # own - messages FILE onto the timeline (visible, promotable by hand) instead of
        # heuristics spraying tasks for every automated notification. Heuristics still
        # short-circuit the obvious fyi noise before spending an AI call.
        if cfg.get('intent_classify_enabled', '1') == '1':
            h = heuristic_intent(msg, mine)
            if h['intent'] == 'fyi':                     # obvious automated noise: no AI call needed
                intent = h
            elif llm is None:
                mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
                store.add_route(mid, None, 'file', None,
                                'awaiting AI triage - connect an AI connector (Connectors → AI) to classify inbound automatically', [], 'triage')
                logger.debug(f"ingest: filed (no AI connector) - {msg.get('subject') or ''}")
                return {'status': 'filed', 'task_id': None, 'message_id': mid}
            else:
                fail = {}
                def _guarded(sys_, usr_):
                    try:
                        return llm(sys_, usr_)
                    except Exception as e:
                        fail['err'] = str(e)[:200]
                        raise
                from .learn import injectable
                notes, notes_left = relevant_notes(store, [msg.get('from_email') or ''],
                                                   f"{msg.get('subject') or ''} {msg.get('body') or ''}"[:4000],
                                                   subject=msg.get('subject') or '',
                                                   source=msg.get('source_name') or '')
                thread = others_on_thread(store, msg, mine)
                intent = classify_intent(msg, llm=_guarded, soul=store.doc('soul'), thread=thread,
                                         learned=injectable(store.doc('learned') or ''),
                                         notes=notes, notes_left=notes_left, images=msg.get('images'),
                                         system=store.doc('triage'), mine=mine)
                if fail:
                    # the AI errored - filing beats the old default-to-task heuristic
                    mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
                    store.add_route(mid, None, 'file', None,
                                    f"AI triage failed ({fail['err']}) - filed; fix the AI connector and it will classify new mail", [], 'triage')
                    logger.warning(f"ingest: AI triage failed, filed - {fail['err']}")
                    return {'status': 'filed', 'task_id': None, 'message_id': mid}
                if intent.get('degraded'):
                    # the call SUCCEEDED and came back unusable, so `fail` is empty and the old
                    # code sailed on with a keyword guess that reads none of the standing notes
                    # above. Same situation as no AI connector, same answer: file it.
                    mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
                    store.add_route(mid, None, 'file', None,
                                    'AI triage returned an answer it could not read as a verdict - filed rather than '
                                    'assumed to be work' + _notes_note(), [], 'triage')
                    logger.warning(f"ingest: unusable AI verdict, filed - {msg.get('subject') or ''}")
                    return {'status': 'filed', 'task_id': None, 'message_id': mid}
        else:
            intent = {'intent': 'task', 'why': ''}
        if intent['intent'] == 'fyi':
            mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
            store.add_route(mid, None, 'file', None,
                            f"triage: fyi - {intent.get('why') or 'informational'}" + _notes_note(), [], 'triage')
            return {'status': 'filed', 'task_id': None, 'message_id': mid}
        from .outbound import can_reply
        if intent['intent'] == 'reply_only' and not can_reply(store, msg.get('channel')):
            # a question on a channel replies are OFF for: filing beats opening a reply task
            # whose draft could never be sent anywhere (see outbound.can_reply for who decides)
            ch = msg.get('channel') or 'this channel'
            why = ('GitHub replies are off (GitHub card)' if ch == 'github'
                   else f'replies are off for {ch} (Settings → Replies)')
            mid = store.add_message({**_fields(msg, None), 'Status': 'filed'})
            store.add_route(mid, None, 'file', None,
                            f"triage: reply_only - {intent.get('why') or 'a question'} · {why}, "
                            'so it is filed instead of drafted', [], 'triage')
            return {'status': 'filed', 'task_id': None, 'message_id': mid}
        # 'escalate' was declared in the policy precedence and then read by nobody. It IS
        # the urgency rule: the owner names the senders whose mail jumps the queue, and that
        # is the only thing that marks a task urgent.
        f = draft_task_fields(msg, urgent=pol['action'] == 'escalate')
        if intent['intent'] == 'reply_only': f['kind'] = 'reply'
        tid = store.create_task({'Title': f['title'], 'Summary': f['summary'], 'Kind': f['kind'],
                                 'Priority': f['priority'], 'Source': msg.get('channel') or 'api',
                                 'SourceRef': msg.get('source_link')}, actor)
        store.audit('task', tid, 'create', actor, 'agent', {'from': msg.get('from_email'), 'reason': r['reason']})
        mid = store.add_message(_fields(msg, tid))
        # the agents actually pick work up here:
        # - reply tasks ALWAYS enter the review queue ("needs me"); auto_draft_enabled
        #   additionally has the responder write the draft in the background
        # - CODING tasks auto-dispatch to the coder when coder_auto_enabled is on
        # - anything else that is real work queues as needs-you, for you to route
        if f['kind'] == 'reply':
            new_rid = rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                              'Reason': f"needs a reply: {intent.get('why') or 'question for you'}"})
            if cfg.get('auto_draft_enabled') == '1':
                _spawn(_auto_draft, store, tid, rid)
        # KIND is the gate, not "anything that is not a reply". This used to dispatch a coding
        # agent at every non-reply task, so a Teams message about someone's job scope - real
        # work, no repository anywhere in it - opened a CLI session on a checkout and started
        # editing code. A coding agent belongs on a coding task; the rest is yours to place.
        elif f['kind'] == 'coding' and cfg.get('coder_auto_enabled') == '1' and not msg.get('no_auto'):
            # no_auto = the channel opted out of self-dispatch (github items always do: an
            # open repo would start an agent per drive-by PR) - the task queues as needs-you
            _spawn(_auto_code, store, tid)
    # the route row is the JUDGEMENT's record, and the timeline panel quotes it verbatim: the
    # verdict leads (what the classifier decided and why), routing explains new-vs-attached,
    # and the tail says what happened NEXT - "it's a task" without "and who is working it"
    # answered a question nobody asked
    reason = r['reason']
    if r['decision'] != 'attach':
        act = ('a reply draft goes to Review for you' if f['kind'] == 'reply'
               else 'not auto-worked: github items queue for you to promote' if msg.get('no_auto')
               # said per KIND, because the line is read as a promise about what just happened
               else 'no code in it - it waits on your list, no agent dispatched' if f['kind'] != 'coding'
               else 'sent to the coding agent' if cfg.get('coder_auto_enabled') == '1'
               else 'auto-dispatch is off (Settings) - start the session from the task')
        reason = (f"triage: {intent['intent']}" + (f" - {intent['why']}" if intent.get('why') else '')
                  + _notes_note()
                  + f" · {r['reason']} · {act}")
    store.add_route(mid, tid, r['decision'], r['score'], reason, r['candidates'], actor)
    logger.info(f"ingest: {r['decision']} -> {task_ref(tid)}")
    # the timeline pushed INTO a chat: 'needs_me' pings only what is waiting on YOU - a question
    # to answer, or a task nobody was dispatched at. A task an agent just started is being
    # handled; the ping for those comes later, when its reply is drafted (coder.raise_reply).
    lvl = cfg.get('notify_level') or 'needs_me'
    # on an attach there was no fresh triage (`f` only exists on create) - the task itself knows
    kind = f['kind'] if r['decision'] != 'attach' else (store.get_task(tid) or {}).get('Kind')
    dispatched = kind != 'reply' and cfg.get('coder_auto_enabled') == '1'
    if lvl == 'all' or (lvl == 'needs_me' and not dispatched):
        _notify_new(store, msg, tid, mid,
                    'a question for you' if kind == 'reply' else 'new task on your list', rid=new_rid)
    return {'status': 'attached' if r['decision'] == 'attach' else 'created', 'task_id': tid, 'message_id': mid}


def _notify_new(store, msg: dict, tid, mid, why: str, rid=None):
    """One short line to the notify channels. With phone approvals on, a question's ping
    also carries the [rvN] tag so replying in the chat decides it (phone.py). Failure is a
    log line, never a broken ingest."""
    from .outbound import notify
    from .store import task_ref
    try:
        who = msg.get('from_name') or msg.get('from_email') or msg.get('source_name') or 'someone'
        body_head = str(msg.get('body') or '').strip().splitlines()
        head = msg.get('subject') or (body_head[0][:80] if body_head else '(no subject)')
        line = f"{task_ref(tid)} - {why}\n{head}\nfrom {who} on {msg.get('channel') or 'api'}"
        if rid:
            from .phone import ping_tail
            line += ping_tail(store, rid, (store.get_review(rid) or {}).get('DraftText'))
        notify(store, line, about={'Channel': msg.get('channel'), 'ConversationId': msg.get('conversation_id')})
    except Exception as e:
        logger.warning(f'notify failed for message {mid}: {e}')


# ── which standing notes reach a prompt ─────────────────────────────────────────────────
# Notes used to be taken in ROW ORDER and the joined text cut at 2000 characters, so past the
# twentieth note - or the two-thousandth character - verdicts the owner had already given
# silently stopped being applied. The silence is the real bug: triage gets it wrong and the
# reason is invisible, because a note that fell off the end looks exactly like a note that was
# never written. Now the notes most likely to decide THIS message go first, whole notes only,
# and whatever did not fit is counted so the caller can say so out loud.
#
# No FTS index behind this on purpose: standing notes are one owner's hand-given verdicts -
# hundreds, not millions - and scoring a few hundred short strings in Python costs less than a
# millisecond. A virtual table would buy nothing here and would add a schema to keep in sync.
NOTE_CAP = 20            # how many notes one prompt carries...
NOTE_BUDGET = 2000       # ...and how many characters, whichever runs out first

# A verdict is usually about a KIND OF WORK, not about a person. "Resident refunds are not our
# task" is the shape of nearly every one of them - and there was nowhere to put it. The scopes
# on offer were this sender, their whole domain, or everybody, so a topic rule got filed under
# whichever colleague happened to be on screen and never fired again: a 17-person thread has 17
# senders, and the next mail arrives from the sixteenth.
#
# 'subject' scope keys on the subject the verdict was given on and matches by OVERLAP, because
# the varying part is exactly what you must ignore - "Resident Refund Request - Doe" and
# "Resident Refund Request - PAYNE" are the same standing decision with a different resident.
TOPIC_MATCH = 0.5        # this fraction of the remembered subject's words present = the same topic


def topic_hit(key: str, subject: str, text: str = '') -> bool:
    kt = set(tokens(key))
    if not kt: return False
    hay = set(tokens(subject or text))
    return len(kt & hay) / len(kt) >= TOPIC_MATCH


def _note_score(n: dict, words: set) -> float:
    """How likely this note is to change the verdict on the message in hand. Three signals, and
    the weights say which one wins: the message's OWN words turning up in the note (one quoting
    the subject you are looking at is the strongest evidence there is), how narrowly the note
    was scoped, and whether the owner gave it as a verdict or a model distilled it. MemoryId
    breaks the ties, so a later verdict outranks the one it supersedes."""
    nw = set(tokens(n.get('Note')))
    overlap = len(nw & words) / len(nw) if nw else 0.0
    # 'subject' ranks with 'sender': a topic note is only a candidate because it already matched
    # the topic, which is as pointed as knowing the person
    return (4 * overlap + {'sender': 3.0, 'subject': 3.0, 'sender_domain': 1.5, 'source': 1.5}.get(n['Scope'], 0.0)
            + (1.0 if n.get('Source') == 'verdict' else 0.0) + n['MemoryId'] / 1e6)


def applicable_notes(store, senders, subject: str = '', text: str = '', source: str = '') -> list:
    """Every ACTIVE note that bears on this message - by sender, by their domain, by the topic
    it is about, by the connection it arrived on, or globally. A switched-off note is silent.

    'source' was accepted by POST /api/memory and matched by NOTHING, so a note saved against a
    mailbox or a repo was written, listed in the UI, and then never applied to anything. It is a
    useful scope - everything landing in a shared log mailbox being somebody else's work - so it
    is honoured here rather than taken away from whatever notes already carry it."""
    who = {(s or '').lower() for s in senders if s}
    doms = {s.rsplit('@', 1)[-1] for s in who if '@' in s}
    src = (source or '').lower()
    return [n for n in store.list_memories()
            if n['Scope'] == 'global'
            or (n['Scope'] == 'sender' and (n.get('ScopeKey') or '').lower() in who)
            or (n['Scope'] == 'sender_domain' and (n.get('ScopeKey') or '').lower() in doms)
            or (n['Scope'] == 'subject' and topic_hit(n.get('ScopeKey') or '', subject, text))
            or (n['Scope'] == 'source' and src and (n.get('ScopeKey') or '').lower() == src)]


def relevant_notes(store, senders, text: str, cap: int = NOTE_CAP, budget: int = NOTE_BUDGET,
                   subject: str = '', source: str = '') -> tuple:
    """(the notes to put in a prompt, most pointed first; how many matched but were left out).

    `senders` is every address on the thread - one message's sender, or a whole chain's."""
    hits = applicable_notes(store, senders, subject, text, source)
    words = set(tokens(text))
    hits.sort(key=lambda n: _note_score(n, words), reverse=True)
    out, used = [], 0
    for n in hits[:cap]:
        note = (n['Note'] or '').strip()
        # a verdict cut in half reads as a DIFFERENT verdict, so notes go in whole or not at all
        if not note or (out and used + len(note) > budget): break
        out.append(note); used += len(note)
    return out, len(hits) - len(out)


def owner_addresses(store) -> set:
    """Every address that IS the owner: each mailbox Taskuary polls. Needed because the mailbox
    a message ARRIVED at is not always the owner's own - a shared or journal mailbox receives
    copies of mail addressed to them personally, and only their real address is on the Cc line."""
    return {(s['Address'] or '').lower() for s in store.list_sources()
            if s.get('Channel') == 'email' and s.get('Address')}


def veto(store, msg: dict, topic_only: bool = False) -> str:
    """The owner's own verdict that this message is not work, if they have given one - the note
    itself, so the timeline can quote what decided it.

    Only Source='verdict' counts: that is written when the owner presses "Not our task" or "Not
    a task", and nothing else writes it. A pattern LEARNED.md distilled is a hint for the
    classifier, never a standing refusal.

    This exists because ATTACHING skipped every judgement. A thread with a task already open
    absorbed each new message straight onto it - no triage, no notes, no AI call - so the task
    stayed 'needs you' no matter how many times the owner said the topic was not theirs. The
    verdict was unreachable by design, and giving it again could not help.

    `topic_only` keeps just the 'subject'-scoped verdicts - "this KIND of work is not ours".
    Those are the ones that must decide rather than advise, because the whole reason the topic
    scope exists is that the sender changes every time (a refund thread carries a different
    resident and a different colleague on each message), so nothing else can catch them.

    A verdict about a PERSON stays advice, deliberately: someone whose last message was not
    yours can still send you something that is, and the classifier weighing the note is the
    right shape for that. A 'global' verdict would mean "never open a task again for anyone",
    which nobody has ever meant by pressing Not our task.

    One key outranks the scope question entirely: the THREAD. "Collection %" has one usable
    word, so the verdict on it could only be saved against the sender - advice - and the same
    conversation opened a task on the very next reply, with the colleague's answer sitting
    right there in it. A verdict given on a thread decides that thread, however it was filed."""
    on_thread = store.owner_verdict_on_thread(msg.get('conversation_id'))
    if on_thread: return re.sub(r'^not ours\s*-\s*', '', on_thread).strip() or on_thread
    hits = applicable_notes(store, [msg.get('from_email') or ''], msg.get('subject') or '',
                            f"{msg.get('subject') or ''} {msg.get('body') or ''}"[:4000],
                            msg.get('source_name') or '')
    return next((n['Note'] for n in hits if n.get('Source') == 'verdict'
                 and not (topic_only and (n['Scope'] != 'subject' or not n.get('ScopeKey')))), '')


def others_on_thread(store, msg: dict, mine=()) -> dict:
    """Has somebody ELSE already answered on this thread?

    A colleague replying is the strongest everyday sign that a request is not waiting on the
    owner - and it is precisely the fact a classifier cannot get from the message, because it
    lives in the messages AROUND it. Without it, every "can you add a column?" on a
    seventeen-person thread lands on the owner even when a colleague answered it an hour ago.

    Only people who actually SENT something count. Being cc'd is not answering. The owner's own
    replies are excluded (that is not somebody else picking it up) and so is this message's own
    sender (a follow-up from the asker is still the asker)."""
    prior = store.thread_messages(msg.get('conversation_id'), msg.get('subject'))
    if not prior: return {}
    me = {(a or '').lower() for a in mine if a} | {(msg.get('source_name') or '').lower()}
    sender = (msg.get('from_email') or '').lower()
    who = lambda m: (m.get('FromName') or (m.get('FromEmail') or '').split('@')[0] or 'someone')
    others = []
    for m in prior:
        e = (m.get('FromEmail') or '').lower()
        if not e or e == sender or e in me: continue
        if who(m) not in others: others.append(who(m))
    if not others: return {}
    last = prior[-1]
    return {'others_replied': others[-3:], 'last_on_thread': who(last),
            'last_on_thread_is_you': (last.get('FromEmail') or '').lower() in me}


def notes_for(store, msg: dict, cap: int = NOTE_CAP, budget: int = NOTE_BUDGET) -> list:
    """The owner's standing notes that apply to this message - global ones plus anything
    learned about this sender or their domain, ranked against what the message actually says.
    Triage reads them, so a verdict given once ("this kind of mail is not ours") applies to
    every message like it afterwards."""
    return relevant_notes(store, [msg.get('from_email') or ''],
                          f"{msg.get('subject') or ''} {msg.get('body') or ''}"[:4000], cap, budget,
                          subject=msg.get('subject') or '', source=msg.get('source_name') or '')[0]


def task_from_message(store, mid: int, actor: str = 'owner', kind: str = 'coding', assignee: str = None) -> int:
    """Promote a filed/ignored/report message into a real task: to hand to an agent, or - with
    `assignee` - to keep on your own list, because plenty of work is real work no agent can do
    (go into some web app and click the thing). Already-routed messages keep the task they are on."""
    m = store.get_message(mid)
    if not m: raise ValueError(f'no message {mid}')
    if m.get('TaskId'): return m['TaskId']
    title = (m.get('Subject') or f"{m.get('FromName') or m.get('FromEmail') or m.get('Channel')} message")[:200]
    tid = store.create_task({'Title': title, 'Summary': str(m.get('BodyText') or '')[:1000], 'Kind': kind,
                             'Source': m.get('Channel') or 'api', 'SourceRef': m.get('SourceLink'),
                             **({'Assignee': assignee} if assignee else {})}, actor)
    store.attach_message(mid, tid)
    store.add_route(mid, tid, 'create', None,
                    f"promoted by the owner - {'theirs to do' if assignee else 'to hand it to an agent'}", [], actor)
    store.audit('task', tid, 'create_from_message', actor, detail={'message_id': mid, 'subject': title})
    return tid


GREETING = re.compile(r'^(hi|hello|hey|dear|good (morning|afternoon|evening))\b', re.I)

def ask_line(body: str) -> str:
    """The line that carries the ask - never the greeting it opens with."""
    lines = [l.strip() for l in (body or '').splitlines() if l.strip()]
    real = [l for l in lines if not GREETING.match(l) and len(l) > 12]
    return (real or lines or [''])[0][:120]


def split_message(store, mid: int, actor: str = 'owner', kind: str = None) -> int:
    """Pull one message OUT of the task it was threaded onto and give it its own. Two asks
    that arrived in the same chat are one conversation but two jobs - and an agent sent at
    the task only ever gets the first one's prompt."""
    m = store.get_message(mid)
    if not m: raise ValueError(f'no message {mid}')
    old = m.get('TaskId')
    parent = store.get_task(old) if old else None
    title = (m.get('Subject') or m.get('FromName') or 'message')[:200]
    body = str(m.get('BodyText') or '')
    # the ask itself is the title when the subject is just the chat's name every message
    # shares - and the ask is never the greeting line it opens with
    if parent and (parent.get('Title') or '').strip().lower() == title.strip().lower():
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        greet = re.compile(r'^(hi|hello|hey|dear|good (morning|afternoon|evening))\b', re.I)
        title = next((l for l in lines if not greet.match(l) and len(l) > 12), lines[0] if lines else title)[:120]
    tid = store.create_task({'Title': title, 'Summary': body[:2000],
                             'Kind': kind or (parent or {}).get('Kind') or 'coding',
                             'Source': m.get('Channel') or 'api', 'SourceRef': m.get('SourceLink')}, actor)
    store.attach_message(mid, tid)
    store.add_route(mid, tid, 'create', None,
                    f'split off {task_ref(old)} - a separate ask in the same thread' if old else 'made its own task',
                    [], actor)
    if old: store.add_comment(old, actor, 'human', f'Split "{title}" out into {task_ref(tid)} - unrelated ask.')
    store.audit('task', tid, 'split_from_message', actor, detail={'message_id': mid, 'from_task': old})
    return tid


def _spawn(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


AUTO_SESSIONS = 4      # DEFAULT unattended sessions to keep alive at once; past this it waits for you


def auto_sessions(store) -> int:
    """How many unattended agent sessions may run at once. Was a module constant, which meant
    the one number that decides how much work the machine takes on could only be changed by
    editing the source - so it is a setting now, and AUTO_SESSIONS is just its default."""
    try: n = int(store.get_settings().get('auto_sessions') or AUTO_SESSIONS)
    except (ValueError, TypeError): return AUTO_SESSIONS
    return max(1, min(16, n))

def _auto_code(store, tid):
    """Auto-dispatch puts the CLI on the task in a REAL session - the same one you see when
    you open the task. Nothing runs where you cannot watch it, interrupt it or answer it.

    A task LIKELY to collide with one already being worked in the same checkout queues behind
    it instead of racing it (affinity routing - the first agent in has control), and a full
    house queues for the next free slot. Both drain automatically as sessions end - the card
    on the board says what it is waiting for."""
    from . import terminal as term, blackboard as bb
    agent = store.get_settings().get('default_agent') or 'coder'
    # the note belongs INSIDE the worker: written before the thread started, a task could
    # claim "auto-dispatched" with no session behind it whenever the process died first
    cap = auto_sessions(store)
    if len([t for t in term.SESSIONS.values() if t.alive]) >= cap:
        store.enqueue_dispatch(tid, None, agent, f'{cap} agent sessions are already live')
        store.add_comment(tid, 'router', 'agent',
                          f'Queued: {cap} agent sessions are already live - '
                          'it starts by itself when one ends.')
        return
    try:
        cwd = bb.target_cwd(store, tid, agent)
        ps = bb.peers(store, cwd, exclude_tid=tid) if cwd else []
        if ps:
            hit, why = bb.likely_overlap(store, tid, ps)
            if hit:
                store.enqueue_dispatch(tid, hit['tid'], agent, why or 'likely to touch the same files')
                store.add_comment(tid, 'router', 'agent',
                                  f"Queued behind {hit['ref']} \"{hit['title'][:80]}\" - "
                                  f"{why or 'likely to touch the same files'}. It starts by itself "
                                  'when that agent finishes.')
                return
        term.start_on_task(store, tid, agent, actor='router')
        store.add_comment(tid, 'router', 'agent', 'auto-started a live coder session (coder_auto_enabled)'
                          + (f' - told it about the {len(ps)} agent(s) already in the checkout' if ps else ''))
    except Exception as e:
        logger.warning(f'auto dispatch failed for task {tid}: {e}')
        store.add_comment(tid, 'router', 'agent', f'Auto-start failed: {str(e)[:200]}')


def _auto_draft(store, tid, rid):
    """A reply needs an answer, not an agent: the MAIN AI writes it and it waits for approval.
    A CLI agent named `responder` takes over only if the owner deliberately configured one."""
    from . import responder
    try: responder.write_draft(store, tid, rid, actor='auto-draft')
    except Exception as e:
        logger.warning(f'auto-draft failed for task {tid}: {e}')


def _fields(msg, task_id):
    from .store import norm_stamp
    return {'TaskId': task_id, 'ExternalId': msg.get('external_id'), 'ConversationId': msg.get('conversation_id'),
            'Channel': msg.get('channel') or 'api', 'SourceName': msg.get('source_name'),
            'Subject': (msg.get('subject') or '')[:500], 'FromName': msg.get('from_name'),
            # normalized HERE, the one gate every channel funnels through: a UTC ISO stamp from
            # any single path sorts the whole timeline out of order (see store.norm_stamp)
            'FromEmail': msg.get('from_email'), 'SentAt': norm_stamp(msg.get('sent_at')),
            'BodyText': msg.get('body'), 'SourceLink': msg.get('source_link'), 'Status': 'routed'}
