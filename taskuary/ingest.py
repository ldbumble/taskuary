"""Ingest: anything -> the funnel. No vendor connectors baked in - push messages via the
HTTP API (POST /api/ingest/push) or your own plugin; report connections run on schedule.

Pipeline per message: dedup -> deterministic policy -> route to a task -> intent triage
(task / reply_only / fyi) -> file or create. Real tasks NEVER get an auto reply-draft:
answering is the responder's job (reply_only), doing is the coder's.
"""
import contextlib, json, re, threading
from loguru import logger
from .routing import ask_line, route, draft_task_fields, tokens
from .policy import evaluate
from .triage import classify_intent, heuristic_intent
from .store import task_ref
from . import senders

# A task the stranger gate held back (senders.known). It is a TAG rather than a column because
# it is exactly as durable as it needs to be - the feed row reads it to say "held · new sender",
# the release drops it, and nothing else in the schema had to move.
HOLD_TAG = 'hold:new-sender'


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


# ── show first, judge next ────────────────────────────────────────────────────────────────
# A sync used to be one long silence: every message waited for its own AI call before it
# appeared, so a 40-mail catch-up was five minutes of "syncing" and then everything at once.
# Inside deferred(), ingest_message STORES the message (status 'triaging') and returns; the
# timeline shows it at once wearing a "triaging" pill; drain() then judges the queue in arrival
# order and each row lands where its verdict puts it. Dedupe, feeds and policies stay immediate:
# they cost nothing and their answer is final.
# The ON/OFF is thread-local: a TestClient that starts the mailbox clock must not make the
# next unittest on MainThread store-instead-of-judge. Poll workers are other threads, so they
# wrap themselves in deferred() when the parent poll is already deferring (see channels).
# Nesting is a counter so an inner deferred() cannot turn the outer off.
_DEFER = threading.local()
_DEFER_DEPTH = 0
_DEFER_LOCK = threading.Lock()
_PENDING = {}        # MessageId -> the message as it arrived (images, no_auto...), for drain in this process
_PENDING_LOCK = threading.Lock()


@contextlib.contextmanager
def deferred():
    global _DEFER_DEPTH
    prev = getattr(_DEFER, 'on', False)
    _DEFER.on = True
    with _DEFER_LOCK: _DEFER_DEPTH += 1
    try: yield
    finally:
        _DEFER.on = prev
        with _DEFER_LOCK: _DEFER_DEPTH -= 1


def _deferring() -> bool:
    return getattr(_DEFER, 'on', False)


def _parent_deferring() -> bool:
    """True while SOME thread is inside deferred() - poll workers inherit that, MainThread does not."""
    with _DEFER_LOCK:
        return _DEFER_DEPTH > 0


def _land(store, msg: dict, task_id, status: str) -> int:
    """Where the judged message goes: the row deferred() already showed, or a new one."""
    if msg.get('_mid'): store.place_message(msg['_mid'], task_id, status); return msg['_mid']
    return store.add_message({**_fields(msg, task_id), 'Status': status})


_ASSOC = re.compile(r'^\[(?:pull request|issue) by [^\]]*? - association: ([A-Z_]+)\]', re.I)

def _gh_no_auto(store, r: dict) -> bool:
    """A GitHub row's dispatch right, re-derived from its own head line and its repo's picker
    (the in-process pending dict carries it directly; a drain in a later process has to look)."""
    if r.get('Channel') != 'github': return False
    from .channels import gh_auto_ok
    src = next((s for s in store.list_sources(active_only=False) if s['Channel'] == 'github' and s['Address'] == r.get('SourceName')), None)
    m = _ASSOC.match(str(r.get('BodyText') or ''))
    return not gh_auto_ok(src, m.group(1) if m else 'NONE')


def _from_row(r: dict, store=None) -> dict:
    """A pending row back into a message, for a drain in a later process (no images then)."""
    rec = json.loads(r.get('RecipientsJson') or 'null') or {}
    return {'external_id': r.get('ExternalId'), 'channel': r.get('Channel'), 'conversation_id': r.get('ConversationId'),
            'subject': r.get('Subject'), 'from_name': r.get('FromName'), 'from_email': r.get('FromEmail'), 'sent_at': r.get('SentAt'),
            'body': r.get('BodyText'), 'source_link': r.get('SourceLink'), 'source_name': r.get('SourceName'),
            'to': rec.get('to'), 'cc': rec.get('cc'), 'no_auto': _gh_no_auto(store, r)}


def _playbook_menu() -> str:
    """What triage is shown of the owner's playbooks - '' when there are none, so no words are spent."""
    try:
        from . import playbooks
        return playbooks.menu()
    except Exception as e:
        logger.debug(f'ingest: playbook menu skipped - {e}'); return ''


def auto_code_ok(store, msg: dict, mid: int, kind: str) -> tuple:
    """May this task start a coding session by ITSELF? (ok, why-not) - two gates, cheapest first.

    The first is the WORK, and it is not decided here (owner, 2026-08-30): a job that is clearly
    not a coding job - a course to sit, a form to sign, a call somebody has to make - goes on the
    Board and waits for a click. Sending it to an agent buys a session, a wrap-up and a drafted
    reply for an agent that can only read it and say "nothing to do here" (TQ-0252 is what that
    costs from outside). `kind` IS that judgement, made in triage against TRIAGE.md where the
    owner can argue with it - there is no keyword, sender or category rule about it in this file,
    because a rule here could not be argued with and would disagree with the document by lunch.

    Then the stranger gate: a first-time sender's mail can be a task, it cannot start an agent on
    this machine (senders.known). Second because it is the expensive one - a Sent Items search -
    which no task already staying on the Board should pay for."""
    if kind == 'general': return False, 'nothing to type at a system - talk it through with the assistant'
    if kind != 'coding': return False, 'a person has to do this one - on your list for you'
    ok, why = senders.known(store, msg, exclude_mid=mid, deep=True)
    return ok, why if ok else (f'{why} - not one of your domains, and this mailbox has never '
                               'written to them; send it yourself if real')


def drain(store, llm=None, progress=None, limit: int = 500) -> int:
    """Judge what deferred() stored - oldest first, one at a time, because a thread's second
    message must find the task its first one opened. A message whose triage raises is filed
    with the error on its route rather than left spinning; the next one still gets judged."""
    rows = store.pending_triage(limit)
    with store.freeze_snapshots():
        for i, r in enumerate(rows):
            mid = r['MessageId']
            with _PENDING_LOCK: held = _PENDING.pop(mid, None)
            msg = {**(held or _from_row(r)), '_mid': mid}
            try:
                ingest_message(store, msg, llm=llm)
            except Exception as e:
                logger.warning(f'deferred triage failed for message {mid}: {e}')
                store.place_message(mid, None, 'filed')
                store.add_route(mid, None, 'file', None, f'triage failed ({str(e)[:160]}) - filed; it can be promoted by hand', [], 'triage')
                store.set_setting('triage_last_error', str(e)[:200], 'system')
            if progress: progress(len(rows) - i - 1)
    return len(rows)


def judge(store, msg: dict, llm, mine=(), me=()) -> tuple[dict, dict]:
    """What IS this message - triage's verdict, with everything around the message as evidence:
    the standing notes, who else has spoken on the thread, what the assistant already said about
    it, the playbooks. Returns (intent, fail); `fail` carries the model's error when it threw.

    One brain, one question, wherever the message landed: a reply that joins an open task gets
    judged exactly like one that opens a new one (the owner, 2026-09-03: "the triage should
    realize that")."""
    fail = {}
    # **kw, not two positional args: a message with a picture on it calls the brain
    # as llm(system, user, images=[...]) - a screenshot of the error IS the request
    # (triage.classify_intent) - and this wrapper refused the keyword it had never
    # been told about. Every mail carrying an image had its verdict thrown away as
    # unusable and was filed, which is the one outcome that looks like the model
    # being stupid rather than like a TypeError three frames down
    def _guarded(sys_, usr_, **kw):
        try:
            return llm(sys_, usr_, **kw)
        except Exception as e:
            fail['err'] = str(e)[:200]
            raise
    from .learn import injectable
    notes, notes_left = relevant_notes(store, [msg.get('from_email') or ''],
                                       f"{msg.get('subject') or ''} {msg.get('body') or ''}"[:4000],
                                       subject=msg.get('subject') or '',
                                       source=msg.get('source_name') or '')
    thread = others_on_thread(store, msg, mine)
    # ...and what was actually SAID before this, theirs and ours. A mail quotes its own thread
    # underneath it - until it does not: a reply typed on a phone, or one whose quote we stripped,
    # arrives with the ask two messages back invisible. A chat line quotes nothing at all, so
    # triage read "nope. new" with no idea what had been asked two minutes earlier.
    lines = exchange_lines(store, msg)
    if lines: thread = {**thread, 'exchange': lines}
    # ...and what the ASSISTANT has already said about this thread (a chase it suggested,
    # an ask it flagged, and what the owner did with it) - the other brain's last word
    from .assistant import said_about
    said = said_about(store, msg.get('conversation_id'))
    if said: thread = {**thread, 'assistant_said': said}
    from .projects import context_for_message
    project = context_for_message(store, msg)
    intent = classify_intent(msg, llm=_guarded, soul=store.doc('soul'), thread=thread,
                             learned=injectable(store.doc('learned') or ''),
                             notes=notes, notes_left=notes_left, images=msg.get('images'),
                             system=store.doc('triage'), mine=me,
                             # a scheduled report carries its own brief - what the owner
                             # set it up to catch (reports.py: the card's watch_for)
                             watch=msg.get('watch_for'),
                             # ...and the playbooks: a message that is an instance of one is
                             # tagged with it, and the agent is seeded from it (playbooks.py)
                             playbooks=_playbook_menu(), project=project)
    intent['notes'], intent['notes_left'] = notes, notes_left
    return intent, fail


def ingest_message(store, msg: dict, actor: str = 'router', llm=None, file_only: bool = False) -> dict:
    """file_only = this connection is a FEED, not a trigger: the item is shown on the
    timeline and nothing else happens to it - no triage, no AI call, no task. It is a
    cheaper and quieter path than 'ignore', which is a verdict about the message.

    A message with `_mid` is one deferred() already stored and drain() is now judging: the
    checks above the judgement (dedupe, feed, policy) were made when it arrived."""
    cfg = store.get_settings()
    fresh = not msg.get('_mid')
    # a message seen twice is dropped on the first line - before any policy pass, before any AI
    if fresh and store.message_exists(msg.get('external_id') or ''):
        return {'status': 'duplicate', 'task_id': None, 'message_id': None}
    if fresh and file_only:
        mid = store.add_message({**_fields(msg, None), 'Status': 'feed'})
        # a voice note nothing could transcribe is filed too - and the reason says so, not "a feed"
        store.add_route(mid, None, 'feed', None,
                        msg.get('file_reason') or 'shown for information - this connection is a feed, not a task trigger', [], 'feed')
        return {'status': 'feed', 'task_id': None, 'message_id': mid}
    # the policy answer is needed on both passes (escalate marks the task urgent below); it is
    # an in-memory match, cheap enough to make twice
    pol = evaluate(msg, store.list_policies(), store.known_sender(msg.get('from_email')),
                   cfg.get('default_action', 'draft'))
    if fresh:
        if pol['action'] in ('skip', 'ignore'):
            # skip = stored for dedupe but NEVER shown (flood senders); ignore = shown, no task
            mid = store.add_message({**_fields(msg, None), 'Status': 'skipped' if pol['action'] == 'skip' else 'ignored'})
            store.add_route(mid, None, pol['action'], None, f"policy '{pol['rule']}': {pol['reason']}", [], 'policy')
            return {'status': pol['action'] + ('ped' if pol['action'] == 'skip' else 'd'), 'task_id': None, 'message_id': mid}
        if _deferring():
            mid = store.add_message({**_fields(msg, None), 'Status': 'triaging'})
            store.add_route(mid, None, 'queued', None, 'on the timeline first - triage decides next', [], actor)
            with _PENDING_LOCK: _PENDING[mid] = msg
            return {'status': 'queued', 'task_id': None, 'message_id': mid}

    r = route(msg, store.snapshots(), float(cfg.get('attach_threshold', 0.42)))
    r = own_thread_only(store, msg, r)
    # ...and on a chat, the room it shares with the task is not a reason to join it
    # (chat_continues). Off with triage: an owner who has switched the classifier off has said
    # they do not want the brain reading their messages, and this is the brain reading them.
    if r['decision'] == 'attach' and is_chat(msg) and cfg.get('intent_classify_enabled', '1') == '1':
        cont = chat_continues(store, msg, r['task_id'], llm)
        if not cont['same']:
            logger.info(f"ingest: a separate ask in the same chat - not joining {task_ref(r['task_id'])}")
            r = {**r, 'decision': 'create', 'task_id': None,
                 'reason': f"a separate ask in the same chat, so it did not join {task_ref(r['task_id'])}"
                           + (f" - {cont['why']}" if cont['why'] else '')}
    new_rid = None                     # set when a fresh reply task opens a review below
    held = ''                            # why the coding agent was NOT auto-started (a robot or a stranger)
    notes, notes_left = [], 0            # standing notes the classifier saw, and any that did not fit
    mine = owner_addresses(store)        # every mailbox the funnel reads - excludes the owner's own replies from "others"
    me = own_addresses(store)            # the owner's own address - what the To/Cc lines are measured against
    def _notes_note():
        # a cap that goes unmentioned reads as "everything you told me was applied". It was
        # not, and only the owner can judge whether the notes that missed out mattered - so
        # every verdict this funnel writes down says it happened.
        return (f' · {len(notes)} of {len(notes) + notes_left} past verdicts shown as evidence '
                '(the rest did not fit)' if notes_left else '')
    if r['decision'] == 'attach':
        tid = r['task_id']
        # ...unless the owner has already ruled on this kind of mail. A live agent session is
        # the one exception: it asked a question on this thread and the answer is arriving, so
        # the round trip outranks a standing verdict about the topic.
        busy = any(x['Status'] == 'running' for x in store.list_runs(tid))
        ruled = '' if busy else ruled_on_thread(store, msg)
        if ruled:
            mid = _land(store, msg, None, 'filed')
            store.add_route(mid, None, 'file', None,
                            f'you already ruled on this conversation, so it did not join {task_ref(tid)}: "{ruled[:200]}"',
                            [], 'memory')
            logger.info(f'ingest: filed by your ruling on the thread instead of attaching to {task_ref(tid)}')
            return {'status': 'filed', 'task_id': None, 'message_id': mid}
        # A reply INHERITS the task's kind and nothing used to ask what it actually says, so
        # "Thank you!" on an open coding task read as "asked you" in the pipe. Triage judges it
        # like any other message (the owner, 2026-09-03: "the triage should realize that"); an
        # fyi verdict keeps it on the task for the chain and off the owner's pile. Never while an
        # agent is waiting on this thread: that round trip IS the answer it asked for.
        follow = None
        # chat has its own reader for this (chat_continues/same_ask): a room is not a topic, and a
        # fragment typed seconds later is one thought in two messages, not a thing to re-judge
        if not busy and cfg.get('intent_classify_enabled', '1') == '1' and llm is not None and not is_chat(msg) and not decided_intent(msg, mine):
            try: follow, _fail = judge(store, msg, llm, mine, me)
            except Exception as e: logger.debug(f'ingest: the follow-up verdict failed, keeping it as work - {e}')
        if follow and follow.get('intent') == 'fyi' and not follow.get('degraded'):
            mid = _land(store, msg, tid, 'filed')
            store.add_route(mid, tid, 'attach', r.get('score'),
                            f"triage: fyi - {follow.get('why') or 'nothing to do'} · kept on {task_ref(tid)} for the chain", [], 'triage')
            store.add_comment(tid, actor, 'agent', f"New {msg.get('channel')} from {msg.get('from_email') or 'unknown'}: {msg.get('subject') or ''} - fyi, nothing to do")
            logger.info(f"ingest: filed onto {task_ref(tid)} as fyi - {msg.get('subject') or ''}")
            return {'status': 'filed', 'task_id': tid, 'message_id': mid}
        mid = _land(store, msg, tid, 'routed')
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
        # The one verdict that decides without a model: you already ruled on THIS email THREAD.
        # A chat carries nothing forward - a room is a relationship, not a topic, and "nothing to
        # do here" is about the line it was said on. Everything else you have
        # ever said - about a sender, about a topic - reaches the classifier below as EVIDENCE,
        # with the sender and subject it was given on, and the model judges how alike this
        # message really is. The owner's call (2026-08-27): a topic rule that decided
        # mechanically ("veto") was too blunt - it could not tell a new refund thread from a
        # refund thread that this time was asking him something.
        ruled = ruled_on_thread(store, msg)
        if ruled:
            mid = _land(store, msg, None, 'filed')
            store.add_route(mid, None, 'file', None,
                            f'you already ruled on this conversation, so no task was opened: "{ruled[:200]}"', [], 'memory')
            logger.info(f"ingest: filed by your ruling on the thread - {msg.get('subject') or ''}")
            return {'status': 'filed', 'task_id': None, 'message_id': mid}
        # AI-gated triage: without an active AI connector, nothing becomes a task on its
        # own - messages FILE onto the timeline (visible, promotable by hand) instead of
        # heuristics spraying tasks for every automated notification. Heuristics still
        # short-circuit the obvious fyi noise before spending an AI call.
        if cfg.get('intent_classify_enabled', '1') == '1':
            pre = decided_intent(msg, mine)              # tracker items and obvious noise: no AI call needed
            # a calendar invite is never work to triage - it is a meeting to be READY for: the
            # assistant's post preps it before it starts (assistant.prep); the owner promotes it
            # by hand if the meeting itself needs something prepared.
            if msg.get('invite'): pre = {'intent': 'fyi', 'why': 'a calendar invite - a meeting to be ready for, not work'}
            if pre:
                intent = pre
            elif llm is None:
                mid = _land(store, msg, None, 'filed')
                store.add_route(mid, None, 'file', None,
                                'awaiting AI triage - connect an AI connector (Connections → AI) to classify inbound automatically', [], 'triage')
                logger.debug(f"ingest: filed (no AI connector) - {msg.get('subject') or ''}")
                return {'status': 'filed', 'task_id': None, 'message_id': mid}
            else:
                intent, fail = judge(store, msg, llm, mine, me)
                notes, notes_left = intent.get('notes') or [], intent.get('notes_left') or 0
                if fail:
                    # the AI errored - filing beats the old default-to-task heuristic. The error is
                    # also kept as a setting so the Timeline's caption can say the brain is failing:
                    # a codex profile carrying a flag its codex does not know failed every call,
                    # and the only sign was rows that stayed on "triaging…"
                    mid = _land(store, msg, None, 'filed')
                    store.add_route(mid, None, 'file', None,
                                    f"AI triage failed ({fail['err']}) - filed; fix the AI connector and it will classify new mail",
                                    [], 'triage', parse_error=fail['err'])
                    store.set_setting('triage_last_error', fail['err'][:200], 'system')
                    logger.warning(f"ingest: AI triage failed, filed - {fail['err']}")
                    return {'status': 'filed', 'task_id': None, 'message_id': mid}
                if cfg.get('triage_last_error'): store.set_setting('triage_last_error', '', 'system')   # it answered: the brain is back
                if intent.get('degraded'):
                    # the call SUCCEEDED and came back unusable, so `fail` is empty and the old
                    # code sailed on with a keyword guess that reads none of the standing notes
                    # above. Same situation as no AI connector, same answer: file it.
                    mid = _land(store, msg, None, 'filed')
                    store.add_route(mid, None, 'file', None,
                                    'AI triage returned an answer it could not read as a verdict - filed rather than '
                                    'assumed to be work' + _notes_note(), [], 'triage',
                                    raw_output=intent.get('raw_output'), parse_error=intent.get('parse_error'))
                    logger.warning(f"ingest: unusable AI verdict, filed - {msg.get('subject') or ''}")
                    return {'status': 'filed', 'task_id': None, 'message_id': mid}
        else:
            intent = {'intent': 'task', 'why': ''}
        if intent['intent'] == 'fyi':
            mid = _land(store, msg, None, 'filed')
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
            mid = _land(store, msg, None, 'filed')
            store.add_route(mid, None, 'file', None,
                            f"triage: reply_only - {intent.get('why') or 'a question'} · {why}, "
                            'so it is filed instead of drafted', [], 'triage')
            return {'status': 'filed', 'task_id': None, 'message_id': mid}
        # 'escalate' was declared in the policy precedence and then read by nobody. It IS
        # the urgency rule: the owner names the senders whose mail jumps the queue, and that
        # is the only thing that marks a task urgent.
        # `kind` ROUTES the work: coding = an agent on a checkout, general = a non-coding agent
        # conversation, task = the owner's own list, reply = the responder and Review. It is
        # triage's judgement, made against TRIAGE.md, and
        # the keyword scan in draft_task_fields is only the fallback for a brain that did not say
        # (or triage switched off). Nothing downstream second-guesses it - see auto_code_ok.
        judged = cfg.get('intent_classify_enabled', '1') == '1'       # a brain (or a by-construction rule) said 'task'
        f = draft_task_fields(msg, urgent=pol['action'] == 'escalate',
                              kind=intent.get('kind') or ('coding' if judged and intent['intent'] == 'task' else None))
        if intent['intent'] == 'reply_only': f['kind'] = 'reply'
        from . import playbooks as _pb
        tid = store.create_task({'Title': f['title'], 'Summary': f['summary'], 'Kind': f['kind'],
                                 'Priority': f['priority'], 'Source': msg.get('channel') or 'api',
                                 'SourceRef': msg.get('source_link'),
                                 **({'Tags': _pb.tag(intent['playbook'])} if intent.get('playbook') else {})}, actor)
        store.audit('task', tid, 'create', actor, 'agent', {'from': msg.get('from_email'), 'reason': r['reason']})
        mid = _land(store, msg, tid, 'routed')
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
        # Almost everything a keyboard can do goes to the agent - the owner's rule (2026-08-27,
        # restated 2026-08-29): it does what it is supposed to, or says "nothing to do here" and
        # stops, and a job left on a list does not. Only CODING self-dispatches: `general` is a
        # conversation the owner opens when they want it (starting a chat per inbound message
        # would be noise), and `task` is theirs by definition. Both still land on the Board.
        elif f['kind'] == 'coding' and cfg.get('coder_auto_enabled') == '1' and not msg.get('no_auto'):
            # no_auto = the channel opted out of self-dispatch (github items always do: an
            # open repo would start an agent per drive-by PR) - the task queues as needs-you.
            # The rest of the gate is auto_code_ok: what may start a session on this machine.
            ok, who = auto_code_ok(store, msg, mid, f['kind'])
            if ok:
                _spawn(_auto_code, store, tid)
                if is_chat(msg): _spawn(_ack_chat, store, msg, mid, tid)   # they hear at once that somebody is on it
            else:
                held = who
                # A stranger's first message is its own state, not just an absent session. An
                # inbound message is a PROMPT, and this one is a prompt from an address that has
                # never written before - so the timeline says so in as many words and offers one
                # button, instead of a task that merely looks like nobody got round to it. The
                # tag rides on the task because that is what the feed row and the release both
                # read (senders.known decided it; HOLD_TAG only records the decision).
                if who.startswith('first message from'): store.tag_task(tid, HOLD_TAG)
                store.add_comment(tid, 'router', 'agent', f'Coding agent not auto-started: {who}. '
                                                          'Send it to the coding agent yourself if an agent can do it.')
                store.audit('task', tid, 'auto_code_held', actor, 'agent', {'from': msg.get('from_email'), 'why': who})
    # the route row is the JUDGEMENT's record, and the timeline panel quotes it verbatim: the
    # verdict leads (what the classifier decided and why), routing explains new-vs-attached,
    # and the tail says what happened NEXT - "it's a task" without "and who is working it"
    # answered a question nobody asked
    reason = r['reason']
    if r['decision'] != 'attach':
        # every kind names its OWN ending. Without the two lines in the middle a general or a
        # task fell through to "sent to the coding agent" - which nothing had done - and the
        # Timeline quotes this verbatim, so the panel would have stated a lie under the verdict.
        act = ('a reply draft goes to Review for you' if f['kind'] == 'reply'
               else 'talk it through with the assistant - nothing is working it' if f['kind'] == 'general'
               else 'yours to do - nothing is working it' if f['kind'] == 'task'
               else 'not auto-worked: github items queue for you to promote' if msg.get('no_auto')
               else f'not auto-worked: {held}' if held
               else 'sent to the coding agent' if cfg.get('coder_auto_enabled') == '1'
               else 'auto-dispatch is off (Settings) - start the session from the task')
        reason = (f"triage: {intent['intent']}" + (f" - {intent['why']}" if intent.get('why') else '')
                  + (f" · playbook {intent['playbook']}" if intent.get('playbook') else '')
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
    # only CODING is ever auto-dispatched now, so anything else is still waiting on the owner
    dispatched = kind == 'coding' and cfg.get('coder_auto_enabled') == '1' and not held
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


# Work by construction on the owner's repo (channels.ingest_github_issues writes the author line
# first): a PULL REQUEST - somebody is asking for a review and a merge, which is the only reason
# a PR exists - and an issue the owner filed themselves. Asked whether a contributor's PR was
# work, the classifier said 'fyi' for five of five and the owner promoted every one by hand.
# Other people's ISSUES stay the classifier's call: a drive-by question is a reply, and whether
# the repo takes replies at all is decided downstream. A repo whose PR picker says 'feed' never
# reaches this at all (file_only).
_GH_WORK = re.compile(r'^\[(pull request by [^\]]*|issue by [^\]]*? - association: OWNER)\]', re.I)


def decided_intent(msg: dict, mine=()) -> dict | None:
    """The verdicts no model is needed for: the owner's own issue is a task, and obvious automated
    noise is fyi (heuristic_intent's short-circuit). None means: ask. Shared with evalset.evaluate
    so the measured accuracy is the funnel's, not the bare model's."""
    if msg.get('channel') == 'github' and _GH_WORK.match(str(msg.get('body') or '')):
        what = 'a pull request' if 'pull request' in str(msg.get('body') or '')[:16].lower() else 'an issue you filed'
        return {'intent': 'task', 'why': f'{what} on your own repository is work by construction - no classifier needed'}
    h = heuristic_intent(msg, mine)
    return h if h['intent'] == 'fyi' else None


def own_addresses(store) -> set:
    """The owner's OWN address(es) - what "addressed to you" is measured against. Settings ->
    owner_email when it is set; otherwise every polled mailbox, which is all we know. Distinct
    from owner_addresses: a shared log mailbox the funnel polls is a place the owner READS, not a
    name the owner IS, and mail sent there is not mail sent to them."""
    own = (store.get_settings().get('owner_email') or '').strip().lower()
    return {own} if own else owner_addresses(store)


def owner_addresses(store) -> set:
    """Every address that IS the owner: each mailbox Taskuary polls. Needed because the mailbox
    a message ARRIVED at is not always the owner's own - a shared or journal mailbox receives
    copies of mail addressed to them personally, and only their real address is on the Cc line."""
    return {(s['Address'] or '').lower() for s in store.list_sources()
            if s.get('Channel') == 'email' and s.get('Address')}


def ruled_on_thread(store, msg: dict) -> str:
    """The owner's own "this is not work" on THIS email thread, if they gave one - the route
    reason they left, so the timeline can quote what decided it. Same thread = same topic for
    life; a chat id is a relationship, not a topic, so a chat ruling decides nothing about the
    next line (see store.owner_verdict_on_thread). This is the only verdict that decides
    without a model:
    a verdict about a person or a topic is EVIDENCE for the classifier (relevant_notes), because
    the same topic can arrive asking something new, and only a reader can tell."""
    on_thread = store.owner_verdict_on_thread(msg.get('conversation_id'), msg.get('sent_at'),
                                              sender=msg.get('from_email') or msg.get('from_name'),
                                              channel=msg.get('channel'))
    return f'you already ruled on this conversation: {on_thread}' if on_thread else ''


def own_thread_only(store, msg: dict, r: dict) -> dict:
    """A message may only join the task ITS OWN THREAD belongs to - never a third task that merely
    looks similar.

    route() scores content: sender 1.0 plus a decent body cosine can clear the bar on its own. So
    when a thread's task has CLOSED, its next reply had no thread signal to win with and landed on
    whatever open task looked most like it. That is how "RE: July 2026 Financials" (and the
    undeliverable bounce behind it) joined the PointClickCare task - and the reply drafted for that
    task was then about Rene Gomez's full mailbox, correctly written from the newest message on the
    wrong pile (the owner, 2026-09-03: "the reply was about another task? How does this happen").

    The rule that was already written down (routing.py) is kept: their reply on a closed thread is
    NEW WORK. This only stops it becoming somebody else's work. A chat room is exempt - its
    conversation id names the room, and chat_continues does that reading."""
    if r.get('decision') != 'attach' or is_chat(msg): return r
    home = store.task_for_conversation(msg.get('conversation_id'), msg.get('subject'))
    if not home or home == r.get('task_id'): return r
    t = store.get_task(home) or {}
    if t.get('Status') not in ('done', 'dropped'):
        logger.info(f"ingest: this thread already belongs to {task_ref(home)} - joining it, not {task_ref(r['task_id'])}")
        return {**r, 'task_id': home, 'reason': f"this thread already belongs to {task_ref(home)}"}
    logger.info(f"ingest: this thread's task {task_ref(home)} is closed - opening new work, not joining {task_ref(r['task_id'])}")
    return {**r, 'decision': 'create', 'task_id': None,
            'reason': (f"a reply on the thread of {task_ref(home)}, which is closed - so this is new work, "
                       f"not part of {task_ref(r['task_id'])}")}


def others_on_thread(store, msg: dict, mine=()) -> dict:
    """Has somebody ELSE already answered on this thread?

    A colleague replying is the strongest everyday sign that a request is not waiting on the
    owner - and it is precisely the fact a classifier cannot get from the message, because it
    lives in the messages AROUND it. Without it, every "can you add a column?" on a
    seventeen-person thread lands on the owner even when a colleague answered it an hour ago.

    Only people who actually SENT something count. Being cc'd is not answering. The owner's own
    replies are excluded (that is not somebody else picking it up) and so is this message's own
    sender (a follow-up from the asker is still the asker).

    Identity is the address OR the name: a Teams line carries no address for most participants,
    and the owner's own lines arrive as 'You' - keyed on addresses alone, a twenty-message group
    chat read as a thread nobody had spoken on, and the one signal the classifier gets right
    every time (5/5 on the owner's own mail) never reached it for chats."""
    prior = store.thread_messages(msg.get('conversation_id'), msg.get('subject'))
    if not prior: return {}
    me = {(a or '').lower() for a in mine if a} | {(msg.get('source_name') or '').lower()} - {''}
    ident = lambda m: (m.get('FromEmail') or m.get('FromName') or '').strip().lower()
    is_me = lambda m: ident(m) in me or (m.get('FromName') or '').strip().lower() == 'you'
    sender = {(msg.get('from_email') or '').lower(), (msg.get('from_name') or '').strip().lower()} - {''}
    who = lambda m: (m.get('FromName') or (m.get('FromEmail') or '').split('@')[0] or 'someone')
    others = []
    for m in prior:
        if not ident(m) or ident(m) in sender or is_me(m): continue
        if who(m) not in others: others.append(who(m))
    if not others: return {}
    last = prior[-1]
    return {'others_replied': others[-3:], 'last_on_thread': who(last), 'last_on_thread_is_you': is_me(last)}


# ── a chat room is not a task ────────────────────────────────────────────────────────────
# Mail threads itself: a reply carries References and belongs to what came before it. A chat
# does not - teams:<chat>, whatsapp:<jid> and imessage:<guid> name a ROOM, and every line anyone
# ever types in it shares that one id. Routing reads it as the thread signal (routing.WEIGHTS:
# thread=1.0 clears the attach bar on its own), so a person's whole day landed on whichever task
# the room opened first: eleven lines, four different problems and a screenshot, ONE task - and
# the agent sent at it only ever saw the first ask (owner, 2026-09-02).
#
# So on chat channels the room buys nothing. Each arriving line is asked the one question that
# matters - is this the ask already open, or a new one - by the only thing that can tell an
# unfinished sentence from "Also, separate thing:": a reader, holding the exchange, OURS AND
# THEIRS. Our own replies are the strongest boundary in the conversation and nothing ever showed
# them to a classifier before.
CHAT_CHANNELS = {'teams', 'slack', 'telegram', 'whatsapp', 'discord', 'imessage'}
BURST_SECONDS = 120     # a line typed this soon after the last is the same sentence, finished


def is_chat(msg: dict) -> bool:
    return str(msg.get('channel') or '').lower() in CHAT_CHANNELS


def _secs(a: str, b: str) -> float:
    """Seconds between two 'YYYY-MM-DD HH:MM:SS' stamps; inf when either is unreadable, so a
    missing timestamp never passes for "typed a moment ago"."""
    from datetime import datetime
    try: return abs((datetime.fromisoformat(str(b)[:19]) - datetime.fromisoformat(str(a)[:19])).total_seconds())
    except (TypeError, ValueError): return float('inf')


def is_ours(m: dict) -> bool:
    """A line WE sent: the owner's own reply, wherever they typed it (channels.ingest_own_message
    stores those as `context`), or one Taskuary sent itself."""
    return (m.get('Status') == 'context' or m.get('Direction') == 'out'
            or str(m.get('FromName') or '').strip().lower() == 'you')


def exchange_lines(store, msg: dict, limit: int = 12, chars: int = 300) -> list:
    """The last lines of this conversation as a person scrolling up would read them - theirs and
    OURS, oldest last, each marked with who said it. The owner's own half was in the database all
    along and no classifier was ever shown it, which is why triage read every chat line as if it
    had arrived out of nowhere."""
    out = []
    for m in store.thread_messages(msg.get('conversation_id'), msg.get('subject'), limit=limit):
        # ...never the line being judged, and never the ones AFTER it. Under deferred() a whole
        # poll is on the timeline as 'triaging' before any of it is judged, so without this the
        # reader would be shown the rest of the conversation as context for its own beginning.
        if m.get('Status') == 'skipped' or (msg.get('_mid') and m['MessageId'] == msg['_mid']): continue
        if msg.get('sent_at') and str(m.get('SentAt') or '') > str(msg['sent_at']): continue
        who = 'you' if is_ours(m) else (m.get('FromName') or m.get('FromEmail') or 'them')
        from .triage import strip_boilerplate
        body = ' '.join(strip_boilerplate(str(m.get('BodyText') or '')).split())[:chars]
        if body: out.append(f"{who} · {str(m.get('SentAt') or '')[5:16]}: {body}")
    return out


def chat_continues(store, msg: dict, tid: int, llm=None) -> dict:
    """Is this chat line part of the task the room already has open? {'same', 'why', 'asked'}.

    Two things answer without spending a call, because they are facts rather than judgements:
    a line typed seconds after the last one is one thought in two messages, and an answer
    arriving while an agent is live on the task is the round trip it asked for. Everything else
    is a reading, and triage.same_ask does the reading."""
    from .triage import same_ask
    prior = store.list_messages(tid)
    last = prior[-1] if prior else None
    if last and not is_ours(last) and _secs(last.get('SentAt'), msg.get('sent_at')) <= BURST_SECONDS:
        return {'same': True, 'why': 'typed seconds after their last line - one thought, two messages', 'asked': False}
    if any(x['Status'] == 'running' for x in store.list_runs(tid)):
        return {'same': True, 'why': 'an agent is working this and asked on this chat', 'asked': False}
    return same_ask((store.get_task(tid) or {}).get('Title') or '', exchange_lines(store, msg),
                    msg.get('body') or '', llm)


# ── the first thing they hear ───────────────────────────────────────────────────────────
# In chat, "the agent isn't working" is a task AND a question. The task starts a coder, and the
# person hears nothing until it wraps - ten minutes if it is quick, an hour of silence if not.
# So the moment an agent actually starts on a chat ask, one line goes back into the chat. Fixed
# words the owner chose (Settings - Replies), never a drafted answer: it promises nothing but
# attention, which is the one thing that is true at that moment. Not twice in half an hour on one
# chat, and never over a line of the owner's own - they have already heard from us.
ACK_DEFAULT = "On it - I'll get back to you here."
ACK_QUIET_MIN = 30
ACK_FRESH_MIN = 10      # only an ask that just arrived: a startup catch-up must not answer yesterday's chat
ECHOES = {'teams', 'imessage'}      # channels that hand our own sends back as context rows (no local copy needed)


def _ack_chat(store, msg: dict, mid: int, tid: int) -> bool:
    cfg = store.get_settings()
    if not is_chat(msg) or cfg.get('chat_ack_enabled', '1') != '1': return False
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if _secs(msg.get('sent_at'), now) > ACK_FRESH_MIN * 60: return False
    from .outbound import can_reply, reply_to_message
    if not can_reply(store, msg.get('channel')): return False
    for m in store.thread_messages(msg.get('conversation_id'), None, limit=12):
        if is_ours(m) and _secs(m.get('SentAt'), msg.get('sent_at')) <= ACK_QUIET_MIN * 60: return False
    text = (cfg.get('chat_ack_text') or ACK_DEFAULT).strip()
    try: reply_to_message(store, store.get_message(mid) or {}, text)
    except Exception as e:
        logger.warning(f'chat acknowledgement failed for {task_ref(tid)}: {e}'); return False
    if msg.get('channel') not in ECHOES:
        store.add_message({'TaskId': tid, 'ExternalId': f'ack:{mid}', 'ConversationId': msg.get('conversation_id'),
                           'Channel': msg.get('channel'), 'SourceName': msg.get('source_name'), 'Subject': msg.get('subject'),
                           'FromName': 'You', 'SentAt': now, 'BodyText': text, 'Status': 'context', 'Direction': 'out'})
    store.add_comment(tid, 'router', 'agent', f"Acknowledged in {msg.get('channel')}: \"{text}\"")
    return True


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
        title = ask_line(body) or title
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
    from . import terminal as term, blackboard as bb, rank, agents as hub_agents
    agent = hub_agents.default_agent(store)
    # Rank mode (the connector's bulk setting): the task does not race for a slot, it joins
    # ONE value-ordered queue and the drain picks the most valuable waiting task whenever a
    # slot is free - see rank.py. Clear mode is everything below, unchanged.
    msgs = store.list_messages(tid)
    if rank.mode_for(store, msgs[0] if msgs else None) == 'rank':
        try:
            rank.enqueue(store, tid, agent)
            rank.rerank(store)
            bb.drain(store)
        except Exception as e:
            logger.warning(f'ranked dispatch failed for task {tid}: {e}')
        return
    # the note belongs INSIDE the worker: written before the thread started, a task could
    # claim "auto-dispatched" with no session behind it whenever the process died first
    cap = auto_sessions(store)
    if len([t for t in list(term.SESSIONS.values()) if t.alive]) >= cap:
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
            'BodyText': msg.get('body'), 'SourceLink': msg.get('source_link'), 'Status': 'routed',
            'MailMetaJson': json.dumps(msg.get('mail_meta')) if msg.get('mail_meta') else None,
            # kept so a verdict can be replayed against the lines that decided it (evalset.py)
            'RecipientsJson': json.dumps({'to': list(msg.get('to') or []), 'cc': list(msg.get('cc') or [])})
                              if (msg.get('to') or msg.get('cc')) else None}
