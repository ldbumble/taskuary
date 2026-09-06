"""Ingest: anything -> the funnel. No vendor connectors baked in - push messages via the
HTTP API (POST /api/ingest/push) or your own plugin; report connections run on schedule.

Pipeline per message: dedup -> deterministic policy -> route to a task -> intent triage
(task / reply_only / fyi) -> file or create. Real tasks NEVER get an auto reply-draft:
answering is the responder's job (reply_only), doing is the coder's.
"""
import contextlib, json, re, threading, time
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


def auto_start_ok(store, msg: dict, mid: int, kind: str) -> tuple:
    """May this task start ITS worker by itself? (ok, why-not). Both kinds start by default (owner,
    2026-09-05, PW-069): coding opens its CLI, general opens its assistant session, a personal `task`
    is the owner's and starts nothing. Each kind has its own switch; a kind needs its worker to be
    configured; and the stranger gate (senders.known) is last because it is the expensive one - a
    Sent Items search no task already staying on the Board should pay for. A hold is about the
    unattended start only: the task is still triaged, shown and dispatchable by hand."""
    cfg = store.get_settings()
    if kind == 'general':
        if cfg.get('general_auto_enabled', '1') != '1': return False, 'auto-start is off for the assistant (Settings) - open it from the task'
        from . import general
        if not general.provider_options(store): return False, 'no assistant provider is configured (Settings -> AI) - open it from the task once one is'
    elif kind == 'coding':
        if cfg.get('coder_auto_enabled') != '1': return False, 'auto-dispatch is off (Settings) - start the session from the task'
    else: return False, 'a person has to do this one - on your list for you'
    ok, why = senders.known(store, msg, exclude_mid=mid, deep=True)
    if ok or not why.startswith('first message from'): return ok, why
    return False, f'{why} - not one of your domains, and this mailbox has never written to them; send it yourself if real'


# One drain at a time: a conversation's second line must find the task its first one opened.
# Fresh chat channels go to the front of the line (the chat lane in server.py names them, and a
# drain already running is told through mark_fresh); within a channel the order stays arrival.
_DRAIN_LOCK = threading.Lock()
_FRESH, _FRESH_LOCK = set(), threading.Lock()
_ALL = 1_000_000                 # pending_triage's LIMIT when the whole queue has to be seen to reorder it


class DrainTicket:
    """Completion handle for one request handed to :class:`DrainWorker`."""

    def __init__(self):
        self._done = threading.Event()
        self.count = 0
        self.error = None

    def wait(self, timeout=None) -> bool:
        return self._done.wait(timeout)


class DrainWorker:
    """One ordered, short-lived drain thread for one store.

    Connector fetch clocks only enqueue here.  That leaves them free to fetch the next batch
    while slow model triage continues, without allowing two conversations to be judged beside
    each other.  The worker exits whenever its queue is empty; ``close`` makes its captured store
    and model factory explicitly releasable by server shutdown and isolated tests.
    """

    def __init__(self, store, llm_factory):
        self.store = store
        self._llm_factory = llm_factory
        self._cv = threading.Condition()
        self._requests = []
        self._active_requests = []
        self._active_channel = None
        self._thread = None
        self._closed = False

    @property
    def active(self) -> bool:
        with self._cv:
            return bool(self._thread and self._thread.is_alive())

    def submit(self, *, fresh=(), only_fresh=False, progress=None) -> DrainTicket:
        ticket = DrainTicket()
        channels = tuple(dict.fromkeys(fresh))
        # Wake a drain which is already between backlog rows before waiting for this request's
        # turn in the worker queue.  _FRESH and the request queue each have their own lock, so the
        # running drain either observes this now or the queued pass observes it afterwards.
        mark_fresh(channels)
        pending = bool(channels and any(r['Channel'] in channels
                                        for r in self.store.pending_triage(_ALL)))
        with self._cv:
            if self._closed:
                raise RuntimeError('drain worker is closed')
            # A successful fetch which found nothing has nothing to wait behind.  Keep the
            # exception for a row of that channel whose final route writes are still running.
            if only_fresh and not pending and self._active_channel not in channels:
                ticket._done.set()
                return ticket
            request = (ticket, channels, bool(only_fresh), progress)
            self._requests.append(request)
            if not self._thread or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name='taskuary-triage', daemon=True)
                try:
                    self._thread.start()
                except Exception as exc:
                    self._thread = None
                    self._requests.remove(request)
                    ticket.error = exc
                    ticket._done.set()
                    self._cv.notify_all()
                    raise
            self._cv.notify_all()
        return ticket

    def _run(self):
        while True:
            with self._cv:
                if not self._requests:
                    self._thread = None
                    self._cv.notify_all()
                    return
                requests, self._requests = self._requests, []
                self._active_requests = requests
            fresh = tuple(dict.fromkeys(ch for _, channels, _, _ in requests for ch in channels))
            # Any full request widens this pass to the complete backlog.  A quick-only batch
            # leaves unrelated mail for the full lane, exactly as synchronous drain did.
            only_fresh = all(r[2] for r in requests)
            progress = next((r[3] for r in requests if r[3] is not None), None)
            count, error = 0, None
            try:
                count = drain(self.store, self._llm_factory(), progress=progress,
                              fresh=fresh, only_fresh=only_fresh,
                              on_start=self._message_start, on_complete=self._message_complete)
            except Exception as exc:
                error = exc
                logger.warning(f'deferred triage drain failed: {exc}')
            for ticket, _, _, _ in requests:
                if not ticket._done.is_set():
                    ticket.count, ticket.error = count, error
                    ticket._done.set()
            with self._cv:
                self._active_requests = []

    def _message_start(self, row):
        with self._cv:
            self._active_channel = row.get('Channel')

    def _message_complete(self, row):
        """Release quick tickets after their last fetched row's route/review writes finish.

        A quick request can arrive while a full backlog pass is already running.  mark_fresh()
        moves its rows forward; completing the ticket here lets the context gate proceed after
        those rows, without waiting for unrelated mail still behind them.
        """
        channel = row.get('Channel')
        with self._cv:
            self._active_channel = None
            candidates = [r for r in self._active_requests + self._requests
                          if r[2] and channel in r[1] and not r[0]._done.is_set()]
        if not candidates: return
        pending_channels = {r['Channel'] for r in self.store.pending_triage(_ALL)}
        completed = [r for r in candidates if not any(ch in pending_channels for ch in r[1])]
        if not completed: return
        with self._cv:
            for request in completed:
                ticket = request[0]
                if ticket._done.is_set(): continue
                ticket._done.set()
                if request in self._requests: self._requests.remove(request)
            self._cv.notify_all()

    def join(self, timeout=None) -> bool:
        """Wait until all submitted requests finish, without closing the reusable worker."""
        end = None if timeout is None else time.monotonic() + timeout
        with self._cv:
            while self._thread or self._requests:
                left = None if end is None else end - time.monotonic()
                if left is not None and left <= 0: return False
                self._cv.wait(left)
        return True

    def close(self, timeout=None) -> bool:
        """Reject new requests and wait for the captured store to leave the worker thread."""
        with self._cv:
            self._closed = True
        return self.join(timeout)


def mark_fresh(channels):
    """Tell the running drain (or the next one) that these channels have lines that just landed."""
    with _FRESH_LOCK: _FRESH.update(channels)


def _take_fresh() -> set:
    with _FRESH_LOCK:
        got = set(_FRESH); _FRESH.clear()
        return got


def _queue(store, done: set, first: set, only_first: bool, limit: int) -> list:
    rows = [r for r in store.pending_triage(_ALL) if r['MessageId'] not in done]
    head = [r for r in rows if r['Channel'] in first]
    return (head if only_first else head + [r for r in rows if r['Channel'] not in first])[:limit]


def await_quiet(store, channels, timeout: float) -> bool:
    """True once no line of these channels is still waiting to be judged; False when the timeout passes first."""
    end = time.monotonic() + timeout
    while True:
        if not any(r['Channel'] in channels for r in store.pending_triage(_ALL)): return True
        if time.monotonic() >= end: return False
        time.sleep(0.2)


def drain(store, llm=None, progress=None, limit: int = 500, fresh=(), only_fresh: bool = False,
          wait: bool = True, on_start=None, on_complete=None) -> int:
    """Judge what deferred() stored - oldest first, one at a time, because a thread's second
    message must find the task its first one opened. A message whose triage raises is filed
    with the error on its route rather than left spinning; the next one still gets judged.

    `fresh` names channels whose lines just landed: they are judged first, and a drain that is
    already running takes them at its next row. only_fresh judges just those and leaves the
    backlog to the full lane; wait=False returns at once when another drain holds the lock."""
    mark_fresh(fresh)
    if not _DRAIN_LOCK.acquire(blocking=wait): return 0
    try:
        done, first, n = set(), _take_fresh() | set(fresh), 0
        rows = _queue(store, done, first, only_fresh, limit)
        with store.freeze_snapshots():
            while rows:
                more = _take_fresh()
                if more:
                    first |= more
                    rows = _queue(store, done, first, only_fresh, limit - n)
                    if not rows: break
                r = rows.pop(0)
                mid = r['MessageId']
                done.add(mid); n += 1
                with _PENDING_LOCK: held = _PENDING.pop(mid, None)
                msg = {**(held or _from_row(r)), '_mid': mid}
                if on_start: on_start(r)
                try:
                    ingest_message(store, msg, llm=llm)
                except Exception as e:
                    logger.warning(f'deferred triage failed for message {mid}: {e}')
                    # a row whose judgement blew up keeps whatever task the router gave it and says
                    # triage failed - an error with a retry, never a filed "nothing to do" (PW-036)
                    tid = (store.get_message(mid) or {}).get('TaskId')
                    store.place_message(mid, tid, 'error')
                    store.add_route(mid, tid, 'file', None, f'triage failed ({str(e)[:160]}) - unclassified; retry available', [], 'triage',
                                    parse_error=str(e)[:1000])
                    store.set_setting('triage_last_error', str(e)[:200], 'system')
                if on_complete: on_complete(r)
                if progress: progress(len(rows))
        return n
    finally:
        _DRAIN_LOCK.release()


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
    # the owner's ruling on this very thread leads the evidence; it is history the model weighs,
    # not a verdict carried forward (it used to file the reply before any model saw it)
    ruled = thread_ruling(store, msg)
    if ruled: notes = [ruled] + notes
    # the owner's past corrections on this sender or topic: evidence beside the notes, never a rule (PW-131)
    try:
        from . import operations
        notes = notes + operations.evidence_lines(store, msg)
    except Exception as e: logger.debug(f'correction evidence skipped: {e}')
    thread = others_on_thread(store, msg, mine)
    candidates = chat_candidates(store, msg) if is_chat(msg) else None
    repos = repo_candidates(store)
    # ...and what was actually SAID before this, theirs and ours. A mail quotes its own thread
    # underneath it - until it does not: a reply typed on a phone, or one whose quote we stripped,
    # arrives with the ask two messages back invisible. A chat line quotes nothing at all, so
    # triage read "nope. new" with no idea what had been asked two minutes earlier.
    lines = exchange_lines(store, msg)
    if lines: thread = {**thread, 'exchange': lines}
    # an assistant idea carries where it came from and what it is about (PW-199): the report, the task
    # it names and whether a worker has that task - facts the model needs to judge a generated line
    if msg.get('idea_context'): thread = {**thread, 'idea_context': msg['idea_context']}
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
                             playbooks=_playbook_menu(), project=project, candidates=candidates, repos=repos or None)
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

    # a chat opener with nothing behind it yet: on the timeline, and no task, no draft, no agent.
    # The line that follows it carries the ask, and the reader is shown this one as its opening.
    if is_opener(msg):
        mid = _land(store, msg, None, 'filed')
        store.add_route(mid, None, 'file', None, 'an opening line on a chat - waiting for the ask it opens', [], 'triage')
        logger.info(f"ingest: chat opener filed, waiting for the point - {(msg.get('body') or '')[:40]}")
        return {'status': 'filed', 'task_id': None, 'message_id': mid}
    mine = owner_addresses(store)        # every mailbox the funnel reads - excludes the owner's own replies from "others"
    me = own_addresses(store)            # the owner's own address - what the To/Cc lines are measured against
    # a judgement made BEFORE routing rides in on the message (an assistant idea judged by triage_ideas,
    # a chat line judged by chat_route) and is reused below - never a second model call for one message
    verdict = msg.pop('_verdict', None)
    if is_chat(msg):
        # a room is not a topic: nothing joins on the room id alone. Two facts join without a
        # model (a line typed seconds after the last, an answer to a live agent); everything else
        # is the verdict's `relationship`, among this room's lines from this same day (PW-031..034)
        r, chat_verdict = chat_route(store, msg, cfg, llm, mine, me)
        verdict = verdict or chat_verdict
    else:
        # mail and tracker items join by IDENTITY - the conversation their own headers name - never by
        # resemblance (PW-016); the closed task of a thread stays closed and the reply stays on the
        # thread, judged afresh (PW-017)
        r = identity_route(store, msg)
    new_rid = None                     # set when a fresh reply task opens a review below
    held = ''                            # why the coding agent was NOT auto-started (a robot or a stranger)
    notes, notes_left = [], 0            # standing notes the classifier saw, and any that did not fit
    def _notes_note():
        # a cap that goes unmentioned reads as "everything you told me was applied". It was
        # not, and only the owner can judge whether the notes that missed out mattered - so
        # every verdict this funnel writes down says it happened.
        return (f' · {len(notes)} of {len(notes) + notes_left} past verdicts shown as evidence '
                '(the rest did not fit)' if notes_left else '')
    from .outbound import send_block
    if r['decision'] == 'attach':
        tid = r['task_id']
        # No ruling on the thread decides here any more: an owner's earlier "not ours" on this
        # conversation used to file every later reply unread (PW-020). It reaches the model below
        # as evidence (judge), and the model says what THIS message is.
        busy = any(x['Status'] == 'running' for x in store.list_runs(tid))
        # A reply INHERITS the task's kind and nothing used to ask what it actually says, so
        # "Thank you!" on an open coding task read as "asked you" in the pipe. Triage judges it
        # like any other message (the owner, 2026-09-03: "the triage should realize that"); an
        # fyi verdict keeps it on the task for the chain and off the owner's pile. Never while an
        # agent is waiting on this thread: that round trip IS the answer it asked for.
        follow, _fail = None, {}
        # a chat line was judged once already, before routing (chat_route): that verdict is the follow-up's
        if verdict is not None: follow, _fail = verdict
        # a chat line joined on a FACT (burst, live agent) was not read and is not re-judged here
        elif not busy and cfg.get('intent_classify_enabled', '1') == '1' and llm is not None and not is_chat(msg) and not decided_intent(msg, mine):
            try: follow, _fail = judge(store, msg, llm, mine, me)
            except Exception as e:
                logger.warning(f'ingest: the follow-up verdict failed - {e}')
                _fail = {'err': str(e)[:200]}
            # triage never read it: say so on the thread's task instead of passing it off as classified
            # work (PW-036). The task link stays; Retry re-judges it in place.
            if _fail:
                mid = _land(store, msg, tid, 'error')
                store.add_route(mid, tid, 'attach', r.get('score'),
                                f"AI triage failed ({_fail['err']}) - kept on {task_ref(tid)}, unclassified; retry available",
                                [], 'triage', parse_error=_fail['err'])
                store.set_setting('triage_last_error', _fail['err'][:200], 'system')
                return {'status': 'error', 'task_id': tid, 'message_id': mid}
            if follow and follow.get('degraded'):
                mid = _land(store, msg, tid, 'error')
                store.add_route(mid, tid, 'attach', r.get('score'),
                                f'AI triage returned an answer it could not read as a verdict - kept on {task_ref(tid)}, unclassified; retry available',
                                [], 'triage', raw_output=follow.get('raw_output'), parse_error=follow.get('parse_error'))
                return {'status': 'error', 'task_id': tid, 'message_id': mid}
        if follow and follow.get('intent') == 'fyi' and not follow.get('degraded'):
            mid = _land(store, msg, tid, 'filed')
            store.add_route(mid, tid, 'attach', r.get('score'),
                            f"triage: fyi - {follow.get('why') or 'nothing to do'} · kept on {task_ref(tid)} for the chain", [], 'triage')
            store.add_comment(tid, actor, 'agent', f"New {msg.get('channel')} from {msg.get('from_email') or 'unknown'}: {msg.get('subject') or ''} - fyi, nothing to do")
            logger.info(f"ingest: filed onto {task_ref(tid)} as fyi - {msg.get('subject') or ''}")
            return {'status': 'filed', 'task_id': tid, 'message_id': mid}
        mid = _land(store, msg, tid, 'routed')
        store.add_comment(tid, actor, 'agent', f"New {msg.get('channel')} from {msg.get('from_email') or 'unknown'}: {msg.get('subject') or ''}")
        if follow and follow.get('checklist'):
            # a later message that asks for something new adds boxes; nothing moves or unticks, and the
            # change is said on the task rather than made silently (PW-076)
            added = store.merge_task_checklist(tid, follow['checklist'], 'triage')
            if added: store.add_comment(tid, 'triage', 'agent', 'New from the latest message:\n' + '\n'.join(f"- [ ] {i['text']}" for i in added))
        if follow and follow.get('intent') == 'reply_only' and not follow.get('degraded') and not store.pending_review(tid):
            # a fresh question on an existing task is reply-needed there: one pending review for
            # this message, drafted at once, whatever the channel can carry (PW-043)
            unsendable = send_block(store, msg.get('channel'))
            rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                    'Reason': f"needs a reply: {follow.get('why') or 'question for you'}" + (f' · {unsendable}' if unsendable else '')})
            _spawn(_auto_draft, store, tid, rid)
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
        # Nothing the owner said before decides here without a model. A ruling on THIS thread used
        # to (ingest.ruled_on_thread, until PW-020): every later reply on a dismissed email thread
        # was filed unread, so a thread that came back asking the owner something never reached
        # triage. It is evidence now, like every other verdict - shown to the classifier with the
        # sender and subject it was given on (judge), and the model judges how alike THIS message
        # really is. Only a saved policy (above) and a feed connection still decide mechanically.
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
                # no brain is not a verdict: the row waits, visibly, for triage (PW-040) - it used to
                # be filed, wearing the same face as "nothing to do"
                mid = _land(store, msg, None, 'error')
                store.add_route(mid, None, 'file', None,
                                'awaiting AI triage - connect an AI connector (Connections → AI) to classify inbound automatically', [], 'triage')
                logger.debug(f"ingest: awaiting triage (no AI connector) - {msg.get('subject') or ''}")
                return {'status': 'error', 'task_id': None, 'message_id': mid}
            else:
                intent, fail = verdict if verdict is not None else judge(store, msg, llm, mine, me)
                notes, notes_left = intent.get('notes') or [], intent.get('notes_left') or 0
                if fail:
                    # the AI errored: an ERROR the owner can see and retry, never a filed row that
                    # reads as "nothing to do" (PW-036). The error is also kept as a setting so the
                    # Timeline's caption can say the brain is failing: a codex profile carrying a flag
                    # its codex does not know failed every call, and the only sign was rows that
                    # stayed on "triaging…"
                    mid = _land(store, msg, None, 'error')
                    store.add_route(mid, None, 'file', None,
                                    f"AI triage failed ({fail['err']}) - unclassified; fix the AI connector and retry",
                                    [], 'triage', parse_error=fail['err'])
                    store.set_setting('triage_last_error', fail['err'][:200], 'system')
                    logger.warning(f"ingest: AI triage failed - {fail['err']}")
                    return {'status': 'error', 'task_id': None, 'message_id': mid}
                if cfg.get('triage_last_error'): store.set_setting('triage_last_error', '', 'system')   # it answered: the brain is back
                if intent.get('degraded'):
                    # the call SUCCEEDED and came back unusable, so `fail` is empty and the old
                    # code sailed on with a keyword guess that reads none of the standing notes
                    # above. Same situation as a failed call, same answer: an error with a retry.
                    mid = _land(store, msg, None, 'error')
                    store.add_route(mid, None, 'file', None,
                                    'AI triage returned an answer it could not read as a verdict - unclassified, '
                                    'not assumed to be work; retry available' + _notes_note(), [], 'triage',
                                    raw_output=intent.get('raw_output'), parse_error=intent.get('parse_error'))
                    logger.warning(f"ingest: unusable AI verdict - {msg.get('subject') or ''}")
                    return {'status': 'error', 'task_id': None, 'message_id': mid}
        else:
            intent = {'intent': 'task', 'why': ''}
        if intent['intent'] == 'fyi':
            mid = _land(store, msg, None, 'filed')
            store.add_route(mid, None, 'file', None,
                            f"triage: fyi - {intent.get('why') or 'informational'}" + _notes_note(), [], 'triage')
            return {'status': 'filed', 'task_id': None, 'message_id': mid}
        # a question is reply-needed whatever the channel can carry (PW-042): sending capability
        # decides whether the draft can be SENT from here, never whether it is written - it used to
        # be filed on a channel with replies off, a question wearing the "nothing to do" face
        unsendable = send_block(store, msg.get('channel')) if intent['intent'] == 'reply_only' else ''
        # 'escalate' was declared in the policy precedence and then read by nobody. It IS
        # the urgency rule: the owner names the senders whose mail jumps the queue, and that
        # is the only thing that marks a task urgent.
        # `kind` ROUTES the work: coding = an agent on a checkout, general = a non-coding agent
        # conversation, task = the owner's own list, reply = the responder and Review. It is
        # triage's judgement, made against TRIAGE.md, and
        # the keyword scan in draft_task_fields is only the fallback for a brain that did not say
        # (or triage switched off). Nothing downstream second-guesses it - see auto_code_ok.
        # a kind the brain did not name is general (PW-067): draft_task_fields makes that call
        f = draft_task_fields(msg, urgent=pol['action'] == 'escalate', kind=intent.get('kind'))
        if intent['intent'] == 'reply_only': f['kind'] = 'reply'
        from . import playbooks as _pb
        # the verdict's own title/summary lead (PW-074); the router's subject/body cut is the fallback
        if intent.get('title'): f['title'] = intent['title']
        if intent.get('summary'): f['summary'] = intent['summary']
        tid = store.create_task({'Title': f['title'], 'Summary': f['summary'], 'Kind': f['kind'],
                                 'Priority': f['priority'], 'Source': msg.get('channel') or 'api',
                                 'SourceRef': msg.get('source_link'),
                                 **({'Tags': _pb.tag(intent['playbook'])} if intent.get('playbook') else {})}, actor)
        store.audit('task', tid, 'create', actor, 'agent', {'from': msg.get('from_email'), 'reason': r['reason']})
        if intent.get('checklist'): store.set_task_checklist(tid, intent['checklist'], 'triage')
        # the repository, decided here and written down, so startup uses it instead of guessing again
        # (PW-092); an owner's repo: tag and a GitHub item's own repository still outrank it (terminal.guess_repo)
        if intent.get('repository'):
            store.tag_task(tid, f"{TRIAGE_REPO_TAG}{intent['repository']}", actor='triage')
            store.add_comment(tid, 'triage', 'agent', f"Triage picked repository {intent['repository']}: {intent.get('repo_reason') or 'named in the request'}")
        elif intent.get('needs_repo_choice'):
            store.tag_task(tid, NEEDS_REPO_TAG, actor='triage')
            store.add_comment(tid, 'triage', 'agent', f"Triage could not tell which repository: {intent.get('repo_reason') or 'more than one is plausible'} - pick one before an agent starts")
        mid = _land(store, msg, tid, 'routed')
        # the same-day lines this one continues or answers that had no task yet join the task it opens:
        # the fyi that opened a subject belongs with the ask that followed it (PW-031)
        for rel_mid in (intent.get('related_message_ids') or []):
            prior = store.get_message(rel_mid) or {}
            if prior and prior.get('TaskId') is None and prior.get('Status') not in ('context', 'skipped'):
                store.attach_message(rel_mid, tid)
        # the agents actually pick work up here:
        # - reply tasks ALWAYS enter the review queue ("needs me"); auto_draft_enabled
        #   additionally has the responder write the draft in the background
        # - CODING tasks auto-dispatch to the coder when coder_auto_enabled is on
        # - anything else that is real work queues as needs-you, for you to route
        if f['kind'] == 'reply':
            new_rid = rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                              'Reason': f"needs a reply: {intent.get('why') or 'question for you'}"
                                                        + (f' · {unsendable}' if unsendable else '')})
            _spawn(_auto_draft, store, tid, rid)        # always drafted (PW-043); auto_draft_enabled no longer gates it
        # Almost everything a keyboard can do goes to the agent - the owner's rule (2026-08-27,
        # restated 2026-08-29): it does what it is supposed to, or says "nothing to do here" and
        # stops, and a job left on a list does not. Only CODING self-dispatches: `general` is a
        # conversation the owner opens when they want it (starting a chat per inbound message
        # would be noise), and `task` is theirs by definition. Both still land on the Board.
        elif f['kind'] in ('coding', 'general') and not msg.get('no_auto'):
            # no_auto = the channel opted out of self-dispatch (github items always do: an
            # open repo would start an agent per drive-by PR) - the task queues as needs-you.
            # The rest of the gate is auto_start_ok: what may start a worker on this machine, for
            # either kind (PW-069/071). A coding job whose repository triage could not tell waits
            # for the owner's choice - a visible hold, not a session in the wrong checkout.
            if f['kind'] == 'coding' and intent.get('needs_repo_choice'):
                ok, who = False, 'needs a repository choice - pick one on the task before an agent starts'
            else: ok, who = auto_start_ok(store, msg, mid, f['kind'])
            if ok:
                # the trust rule that let it through is said on the task (PW-080), so 'why did an agent start on
                # a stranger's mail' has an answer
                store.add_comment(tid, 'router', 'agent', f'Unattended start allowed: {who}.')
                _spawn(_auto_code if f['kind'] == 'coding' else _auto_general, store, tid)
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
                worker = 'Coding agent' if f['kind'] == 'coding' else 'Assistant'
                store.add_comment(tid, 'router', 'agent', f'{worker} not auto-started: {who}. '
                                                          + ('Send it to the coding agent yourself if an agent can do it.' if f['kind'] == 'coding'
                                                             else 'Open it from the task when you want the assistant on it.'))
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
        act = (('a reply draft goes to Review for you' + (f' - {unsendable}, so it cannot be sent from here' if unsendable else '')) if f['kind'] == 'reply'
               else 'yours to do - nothing is working it' if f['kind'] == 'task'
               else 'not auto-worked: github items queue for you to promote' if msg.get('no_auto')
               else f'not auto-worked: {held}' if held
               else 'sent to the coding agent' if f['kind'] == 'coding'
               else 'sent to the assistant')
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
    # both worker kinds are auto-dispatched (PW-069); a personal task or a held one still waits on the owner
    dispatched = kind in ('coding', 'general') and not held and not msg.get('no_auto') and (
        cfg.get('coder_auto_enabled') == '1' if kind == 'coding' else cfg.get('general_auto_enabled', '1') == '1')
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


def thread_ruling(store, msg: dict) -> str:
    """The owner's own "this is not work" on an earlier message of THIS email thread, phrased as
    one more piece of evidence for the classifier - never a decision (PW-020/021). A chat id is a
    relationship, not a topic, so a chat ruling says nothing about the next line
    (store.owner_verdict_on_thread); an email thread is a topic, and what the owner said about
    it is worth knowing when reading the reply - but a thread that now asks something new is new."""
    on_thread = store.owner_verdict_on_thread(msg.get('conversation_id'), msg.get('sent_at'),
                                              sender=msg.get('from_email') or msg.get('from_name'),
                                              channel=msg.get('channel'))
    return f'On this very conversation you ruled earlier: "{on_thread}" - weigh whether this message changes that' if on_thread else ''


def identity_route(store, msg: dict) -> dict:
    """Where a mail or tracker item goes: the OPEN task its own conversation already belongs to, else
    new work. The router used to score subject words, sender and body cosine against every open
    task, so two unrelated mails with one subject line joined a task, a rewritten References header
    landed a reply on a look-alike, and a bounce joined the task its text resembled (the wrong-thread
    reply of 2026-09-03). Identity is Graph's conversationId, IMAP's References/Message-ID, a tracker
    item's own id (PW-016); without one, resemblance never decides. A closed task's thread does not
    reopen it: the reply is kept on the conversation and evaluated on its own (PW-017)."""
    conv = msg.get('conversation_id')
    if not conv:
        return {'decision': 'create', 'task_id': None, 'score': 0.0, 'candidates': [],
                'reason': 'new task - no conversation identity to join on, and resemblance never decides'}
    home = store.task_for_conversation(conv)
    if not home:
        return {'decision': 'create', 'task_id': None, 'score': 0.0, 'candidates': [], 'reason': 'new task - no open task on this conversation'}
    t = store.get_task(home) or {}
    if t.get('Status') in ('done', 'dropped'):
        logger.info(f"ingest: this thread's task {task_ref(home)} is closed - new work, not a reopening")
        return {'decision': 'create', 'task_id': None, 'score': 0.0, 'candidates': [],
                'reason': f"this thread's task {task_ref(home)} is closed - judged as new; the reply stays on the thread"}
    return {'decision': 'attach', 'task_id': home, 'score': 1.0, 'candidates': [], 'reason': 'attached: same conversation thread'}


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


# "hey" is not an ask. On WhatsApp it became a reply task with a drafted "Hey - what's up?", the
# real question arrived two lines later and attached to it, and the pipe offered the GREETING for
# approval (the 2026-09-03 break test). A chat opener waits for the sentence it opens: it is filed
# on the timeline, and the next line - which exchange_lines hands the reader as context - is the ask.
_OPENER = re.compile(r"^\s*(hi|hey+|hello+|yo|sup|hiya|morning|good (morning|afternoon|evening)|shalom|hey there|you there|u there"
                     r"|quick (q|question)|got a (sec|second|minute|min)|are you (there|around|free)|can i ask you something"
                     r"|knock knock|\W*)\W*$", re.I)

def is_opener(msg: dict) -> bool:
    """A chat line that opens a conversation and asks nothing - the greeting before the point."""
    if not is_chat(msg): return False
    body = ' '.join(str(msg.get('body') or '').split())
    if not body or len(body) > 60: return False
    return bool(_OPENER.match(body))


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


def exchange_lines(store, msg: dict, budget: int = None, limit: int = 200) -> list:
    """The conversation as a person scrolling up would read it - theirs and OURS, oldest first,
    each marked with who said it, each message's own words once. The owner's own half was in the
    database all along and no classifier was ever shown it, which is why triage read every chat
    line as if it had arrived out of nowhere.

    It used to be twelve lines of 300 characters, silently (PW-026). Now every message's cleaned,
    de-quoted words are kept whole under a character budget (triage.EXCHANGE_BUDGET); when the
    budget is exceeded the OLDEST go first and the first line says how many were dropped - the
    model is never left to assume it saw the whole thread."""
    from .triage import strip_boilerplate, dedupe_quoted, EXCHANGE_BUDGET
    budget = EXCHANGE_BUDGET if budget is None else budget
    out, priors = [], []
    for m in store.thread_messages(msg.get('conversation_id'), msg.get('subject'), limit=limit):
        # ...never the line being judged, and never the ones AFTER it. Under deferred() a whole
        # poll is on the timeline as 'triaging' before any of it is judged, so without this the
        # reader would be shown the rest of the conversation as context for its own beginning.
        if m.get('Status') == 'skipped' or (msg.get('_mid') and m['MessageId'] == msg['_mid']): continue
        if msg.get('sent_at') and str(m.get('SentAt') or '') > str(msg['sent_at']): continue
        who = 'you' if is_ours(m) else (m.get('FromName') or m.get('FromEmail') or 'them')
        clean = strip_boilerplate(str(m.get('BodyText') or ''))
        body = ' '.join(dedupe_quoted(clean, priors).split())
        priors.append(clean)
        if body: out.append(f"{who} · {str(m.get('SentAt') or '')[5:16]}: {body}")
    # a conversation whose history could not be completed says so (PW-013): the model sees what is
    # stored and is told it is not the whole thread
    try: cov = store.chain_coverage(msg.get('conversation_id')) if msg.get('conversation_id') else None
    except Exception: cov = None
    if cov and not cov.get('complete'):
        out.insert(0, f"… history incomplete - {cov.get('error') or 'not all of this thread could be retrieved'}; what follows is what is stored, not the whole thread")
    dropped = 0
    while len(out) > 1 and sum(len(l) for l in out) > budget:
        out.pop(0); dropped += 1
    if dropped: out.insert(0, f'… {dropped} earlier message{"s" if dropped != 1 else ""} not shown (context budget) - the thread is longer than what follows')
    return out


TRIAGE_REPO_TAG, NEEDS_REPO_TAG = 'triage-repo:', 'needs-repo-choice'


def repo_candidates(store) -> list:
    """The repositories triage may name (PW-092): the learned project graph's repository edges, with
    what each project is, plus the SOUL.md repo map. Only these can be chosen; anything else is dropped."""
    from .projects import REPO_KIND
    out = {}
    try:
        for link in store.project_links(kind=REPO_KIND):
            repo = str(link.get('Value') or '').strip()
            if repo and repo not in out: out[repo] = str(link.get('ProjectDescription') or link.get('ProjectName') or '')
    except Exception as e: logger.debug(f'ingest: project repositories unavailable - {e}')
    try:
        from .terminal import repo_map
        for repo, about in repo_map(store).items():
            if repo not in out: out[repo] = about
    except Exception as e: logger.debug(f'ingest: SOUL repo map unavailable - {e}')
    return [{'repo': r, 'about': a} for r, a in out.items()]


def chat_candidates(store, msg: dict) -> list:
    """The lines of THIS room on the SAME local calendar day as the message - by the message's own
    stamp, never the clock (a delayed sync is still yesterday's conversation) - and never a line
    that came after it. The only lines a relationship may name (PW-032). Ours are included: an
    answer to what we asked is a relationship too."""
    from .store import norm_stamp
    at = norm_stamp(msg.get('sent_at')); day = at[:10]
    out = []
    for m in store.thread_messages(msg.get('conversation_id'), None, limit=60):
        if m.get('Status') == 'skipped' or (msg.get('_mid') and m['MessageId'] == msg['_mid']): continue
        when = str(m.get('SentAt') or '')
        if when[:10] != day or when > at: continue
        who = 'you' if is_ours(m) else (m.get('FromName') or m.get('FromEmail') or 'them')
        out.append({'id': m['MessageId'], 'who': who, 'when': when[11:16],
                    'text': ' '.join(str(m.get('BodyText') or '').split())[:300], 'task_id': m.get('TaskId')})
    return out[-20:]


def _open_task(store, tid):
    t = store.get_task(tid) if tid else None
    return tid if t and t.get('Status') not in ('done', 'dropped') else None


def chat_route(store, msg: dict, cfg: dict, llm, mine=(), me=()) -> tuple:
    """Where a chat line goes: (route dict, (verdict, fail) or None).

    Two FACTS join without a model: a line typed within BURST_SECONDS of the room's last inbound
    line is the same thought finished, and a line arriving while an agent is live on the room's
    task is the round trip it asked for. Everything else is the one triage verdict's
    `relationship`, judged among this room's same-day lines (chat_candidates): continues/answers
    with a valid related line or task joins that task; new and uncertain open work of their own.
    The room id alone never joins (PW-018/PW-032); without a brain, nothing but the facts does."""
    cands = chat_candidates(store, msg)
    last = next((c for c in reversed(cands) if c['who'] != 'you'), None)
    if last and _open_task(store, last['task_id']) and _secs(store.get_message(last['id']).get('SentAt'), msg.get('sent_at')) <= BURST_SECONDS:
        return ({'decision': 'attach', 'task_id': last['task_id'], 'score': 1.0, 'candidates': [],
                 'reason': 'typed seconds after their last line - one thought, two messages'}, None)
    live = next((c['task_id'] for c in reversed(cands) if _open_task(store, c['task_id'])
                 and any(x['Status'] == 'running' for x in store.list_runs(c['task_id']))), None)
    if live:
        return ({'decision': 'attach', 'task_id': live, 'score': 1.0, 'candidates': [],
                 'reason': 'an agent is working this and asked on this chat'}, None)
    room = next((c['task_id'] for c in reversed(cands) if _open_task(store, c['task_id'])), None)
    apart = f", so it did not join {task_ref(room)}" if room else ''
    if cfg.get('intent_classify_enabled', '1') != '1' or llm is None:
        why = 'triage is off' if cfg.get('intent_classify_enabled', '1') != '1' else 'no brain to judge it'
        return ({'decision': 'create', 'task_id': None, 'score': 0.0, 'candidates': [],
                 'reason': f'a chat line on its own - {why}, and a room is not a topic{apart}'}, None)
    intent, fail = judge(store, msg, llm, mine, me)
    rel = intent.get('relationship') or 'uncertain'
    target = _open_task(store, intent.get('existing_task_id'))
    for rel_mid in (intent.get('related_message_ids') or []):
        if target: break
        target = _open_task(store, (store.get_message(rel_mid) or {}).get('TaskId'))
    if rel in ('continues', 'answers') and target:
        return ({'decision': 'attach', 'task_id': target, 'score': 1.0, 'candidates': [],
                 'reason': f'{rel} the ask on {task_ref(target)} (same chat, same day)'}, (intent, fail))
    why = ('a separate ask in the same chat' if rel == 'new' else
           'uncertain whether it continues an ask in this chat - not joined on a guess')
    return ({'decision': 'create', 'task_id': None, 'score': 0.0, 'candidates': [], 'reason': why + apart}, (intent, fail))


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
    # what was said about THIS message before it was work travels with it (operations.py, PW-133)
    from . import operations
    operations.link_discussion(store, tid, [mid])
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


def _auto_general(store, tid, brief: str = None):
    """Auto-dispatch for a GENERAL task: the assistant's own per-task session, the same one the
    owner sees when they open the task (PW-069). A full house queues it like a coding task; the
    queue drain knows the kind. A live conversation is reused - the ask is put once."""
    from . import terminal as term
    cap = auto_sessions(store)
    if len([t for t in list(term.SESSIONS.values()) if t.alive]) >= cap:
        store.enqueue_dispatch(tid, None, 'assistant', f'{cap} agent sessions are already live')
        store.add_comment(tid, 'router', 'agent', f'Queued: {cap} agent sessions are already live - it starts by itself when one ends.')
        return
    _start_general(store, tid, brief)


def _start_general(store, tid, brief: str = None):
    """Open (or reuse) the assistant session and put the task to it - once. A failure is written on
    the task as a failure, never left looking like nobody got round to it (PW-073)."""
    from . import general
    try:
        t = store.get_task(tid) or {}
        session = general.start_session(store, tid, actor='router')
        fresh = not general.history(store, tid)
        store.add_comment(tid, 'router', 'agent', 'auto-started the assistant on this task (general_auto_enabled)'
                          + ('' if fresh else ' - the conversation already open on it continues'))
        if fresh:
            ask = (brief or str(t.get('Summary') or '').strip() or str(t.get('Title') or '').strip())
            if ask: session.send_prompt(ask)
    except Exception as e:
        logger.warning(f'assistant auto-start failed for task {tid}: {e}')
        store.add_comment(tid, 'router', 'agent', f'Assistant start failed: {str(e)[:200]}')


def _auto_draft(store, tid, rid):
    """A reply needs an answer, not an agent: the MAIN AI writes it and it waits for approval.
    A CLI agent named `responder` takes over only if the owner deliberately configured one.
    A draft that could not be written says so on the review (PW-046) - the item stays reply-needed
    and the owner can retry or write it; it never passes for an fyi or a draft that exists."""
    from . import responder
    try: responder.write_draft(store, tid, rid, actor='auto-draft')
    except Exception as e:
        logger.warning(f'auto-draft failed for task {tid}: {e}')
        try: store.set_review_draft_error(rid, str(e)[:300])
        except Exception as e2: logger.warning(f'could not record the draft failure on review {rid}: {e2}')


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
