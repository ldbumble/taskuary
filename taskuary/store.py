"""Storage: one small dict-shaped contract, two bindings - SQLite (stdlib, the local-first
default) and in-memory (tests/demo). Every mutation is meant to be paired with .audit();
the audit log is a Buzz-style tamper-evident hash chain (each row hashes the previous).
"""
import contextlib, contextvars, copy, hashlib, json, os, re, sqlite3, sys, threading, time, uuid
from datetime import datetime, timedelta
import weakref
from loguru import logger
from . import vault
from .inboxes import TYPES as INBOXES, NAMES as INBOX_NAMES     # the helpdesks and newer trackers: seeded and triggering like the rest
from .apireads import types as _read_types                     # a vendor's REST API read (apireads.json): each row a card
from .connectorcatalog import map_secrets, secret_keys         # the config fields a card declares secret: sealed like the Secret column
def _posts() -> set:
    from .connectorcatalog import cards
    return {c['type'] for c in cards() for a in c.get('actions') or [] if a.get('road') == 'run_tool'}
from .kinds import SHOWN, shown as shown_agent   # the name a chip says for whoever works a task: Taskuary, never the profile

# WHO HELD THE STORE, AND FOR HOW LONG (2026-10-23): three freezes in a day left a log where unrelated requests all finished in
# the same second after 20-150 s, and nothing said what they had waited on. The writer's lock now says it: a wait over
# LOCK_SLOW_WAIT names the waiter and the holder's call site, a hold over LOCK_SLOW_HOLD names the holder, and a request reads
# its own total wait (lock_wait_meter) for its log line. A free lock costs one non-blocking acquire and a short frame walk.
# ...and says it ONCE A MINUTE per call site (2026-10-28): a busy census put 6-8 waiters behind it every few seconds and the
# console was nothing but these lines. A wait under 2 s is not news; the first one over it is logged, the rest of that minute
# from the same site are counted and ride on the next line from it (LOCK_LOG_EVERY).
LOCK_SLOW_WAIT, LOCK_SLOW_HOLD, LOCK_LOG_EVERY = 2.0, 2.0, 60.0
_LOCK_WAITED = contextvars.ContextVar('taskuary_lock_waited', default=None)
_HERE, _CTX = __file__, contextlib.__file__
_LOGGED, _LOGGED_LOCK = {}, threading.Lock()   # (kind, site) -> [last logged at, waits since, seconds since, worst since]

def _call_site() -> str:
    "The first frame outside this file (and contextlib's, which a `with store.x():` puts between): who asked the store."
    f = sys._getframe(1)
    while f is not None and f.f_code.co_filename in (_HERE, _CTX): f = f.f_back
    return f'{os.path.basename(f.f_code.co_filename)}:{f.f_lineno} {f.f_code.co_name}' if f else '?'

def _throttled(kind, site, took, line):
    "Log `line()` unless this site logged one within LOCK_LOG_EVERY; then it is counted, and the next line says how many."
    now = time.monotonic()
    with _LOGGED_LOCK:
        e = _LOGGED.get((kind, site))
        if e is not None and now - e[0] < LOCK_LOG_EVERY: e[1] += 1; e[2] += took; e[3] = max(e[3], took); return
        _LOGGED[(kind, site)] = [now, 0, 0.0, 0.0]
    more = f' (+{e[1]} more in the last {now - e[0]:.0f}s, {e[2]:.1f}s in all, worst {e[3]:.1f}s)' if e and e[1] else ''
    logger.warning(line() + more)

@contextlib.contextmanager
def lock_wait_meter():
    "Seconds this request (its thread and anything it hands its context to) spent waiting on a store's lock: m[0]."
    m = [0.0]; tok = _LOCK_WAITED.set(m)
    try: yield m
    finally: _LOCK_WAITED.reset(tok)


class _Writer(sqlite3.Connection):
    """THE STORE'S WRITER, CLOSED ONE WAY ONLY (the release runs, 2026-11-19: a background job of the chat log mid-statement on a store whose
    connection a test's cleanup closed - an access violation, twice): however its close() is reached - store.close(), a test closing `cx`, a
    teardown - its store is marked closing, the chat log's worker lets go of it first (chatlog.let_go), and the close waits for the store's
    lock, so it never lands under a statement another thread is running."""
    _owner = None
    def close(self):
        st = o() if (o := getattr(self, '_owner', None)) else None
        if st is None: return super().close()
        st._closing = True
        # ...waiting for the worker's job only where this thread does not hold the store's lock: a job at work may need it to finish, and a
        # close under the lock (store.close, a caller's own hold) would wait out let_go's timeout on every close (the release run's 20 min)
        if not st.lock._is_owned():
            try:
                from . import chatlog; chatlog.let_go(st)
            except Exception: pass
        with st.lock: st._closed = True; return super().close()


class _TimedLock:
    """The writer's RLock, the same re-entrant lock, that writes down who held it when somebody had to wait for it."""
    def __init__(self): self._l, self._depth, self._since, self._site, self._who, self._n = threading.RLock(), 0, 0.0, '', '', 0
    def acquire(self, blocking=True, timeout=-1):
        if self._l.acquire(False): self._took(); return True
        if not blocking: return False
        site, who, since, n, t0 = self._site, self._who, self._since, self._n, time.perf_counter()     # the holder as we found it
        got = self._l.acquire(True, timeout)
        waited = time.perf_counter() - t0
        if (m := _LOCK_WAITED.get()) is not None: m[0] += waited
        if waited > LOCK_SLOW_WAIT:
            # one holder all along is one slow job; many hand-offs is a crowd of short ones (or one that keeps coming back)
            me, hand = _call_site(), self._n - n
            _throttled('wait', me, waited, lambda: f'store.lock: {threading.current_thread().name} at {me} waited {waited:.1f}s - '
                       f'held by {who or "?"} at {site or "?"} for {max(0.0, t0 - since):.1f}s before the wait began, {hand} hand-off(s) during it')
        if got: self._took()
        return got
    def _took(self):
        self._depth += 1
        if self._depth == 1: self._since, self._site, self._who, self._n = time.perf_counter(), _call_site(), threading.current_thread().name, self._n + 1
    def release(self):
        self._depth -= 1
        held, who, site = (time.perf_counter() - self._since if self._depth == 0 else 0.0), self._who, self._site
        self._l.release()
        if held > LOCK_SLOW_HOLD: _throttled('hold', site, held, lambda: f'store.lock: held {held:.1f}s by {who} at {site}')
    def _is_owned(self): return self._l._is_owned()
    def __enter__(self): return self.acquire()
    def __exit__(self, *a): self.release()


# READS OFF THE WRITER (2026-10-23): a background job that reads a lot - the Advisor's rule-promotion evidence was hundreds of
# full scans of the message table at 0.3-0.5 s each, two minutes back to back on the writer's lock - queued every request's
# every statement behind it. Inside reads_off_writer() a plain SELECT through _rows/_one runs on a pooled reader connection
# (WAL: it sees every committed write) instead; writes, and reads inside a writer transaction, still use the writer.
# ...and now EVERY plain read does (2026-10-28): a setting, the connector list, the owner's name - read a few hundred times a
# second by the pile, the doorways, the pollers - queued 1-3 s behind each membership census, 6-8 deep. A reader sees exactly
# what is committed; only the thread that holds the writer's lock (its own open transaction) reads through the writer.
_OFF_WRITER, _ON_WRITER = threading.local(), threading.local()
_PINNED = threading.local()      # pinned_read(): (the store, its reader cursor) - this thread's plain reads share one snapshot
_HELD = threading.local()        # held_settings(): (the store, {name: its row}) for this thread while a build holds them
# ...and A WRITE TO WHAT IS HELD lets go of it, whoever wrote it (_exec): the statement's own target table, read off its grammar
_HELD_TABLES = re.compile(r'^\s*(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)\s+(?:setting|doc)\b', re.I)
CENSUS_CHUNK = 500     # census writes per turn on the writer: a press waits for one turn, never the whole pass
CENSUS_TRIES = 3       # census passes raced by a write before one is run under a single lock, so a busy store still settles
_CENSUS_COUNTS = ('created_items', 'created_members', 'moved_members', 'retired_members', 'redirected_items',
                  'created_aliases', 'created_relations', 'retired_relations')
READERS_KEPT = 16      # reader connections kept open for reuse: a request pool's worth of threads reading at once

_LIVE_UNSET = object()
_POLL_UNSET = object()
# A durable claim also names its process. A second connection must not mistake a live
# sender for an interrupted one; after a restart, an abandoned claim becomes unknown.
_DELIVERY_PROCESS = f'{os.getpid()}:{uuid.uuid4().hex}:'
_DELIVERY_LOCK = threading.RLock()
_DELIVERY_CLAIMS = set()


def _delivery_claim_alive(claim):
    if not claim: return False
    if claim.startswith(_DELIVERY_PROCESS): return claim in _DELIVERY_CLAIMS
    try: pid = int(claim.split(':', 1)[0])
    except (TypeError, ValueError): return True  # an unrecognised owner is not permission to retry
    if pid == os.getpid(): return False         # a prior process whose pid was reused
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle: return ctypes.get_last_error() != 87
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally: kernel.CloseHandle(handle)
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    except PermissionError: return True
    except OSError: return True
    return True
GENESIS = '0' * 64
# the channels Taskuary writes itself - its reports and the Advisor's ideas - which carry no sender address
OWN_CHANNELS = ('report', 'assistant')
def _shown_title(fields: dict) -> dict:
    """A TITLE IS SHOWN, never a prompt (walk 19): his "post it ... password chirp-pass" became the title the rail and the phone carried. The
    Summary keeps his words - the agent signs in with them; the title is said without the password (redact.shown)."""
    if not fields.get('Title'): return fields
    from .redact import shown
    return {**fields, 'Title': shown(fields['Title'])}


TASK_COLS = ('Title', 'Summary', 'Kind', 'Status', 'Priority', 'Assignee', 'Source', 'SourceRef', 'Tags', 'RemindAt', 'AskedVia', 'DueAt',
             'DoneWhen', 'ParentId', 'OriginBase', 'TrustedThrough', 'Origin', 'OriginWhy', 'WatchedAt', 'WatchBack', 'ThreadJson',
             'CheckBackAt', 'CheckBackWhat', 'Files')
# ATTACHMENTS ARE A FIELD (the design loop, 2026-11-20): what the owner attached to a line of his (comment.Files), to the ask that made a task
# (task.Files) or to a note kept for a coding agent (waitroom.Files) is a JSON list of paths beside his words - never a block at the end of them,
# which every door wrote and ~40 readers parsed: a door that wrote it slightly differently lost his files from his bubble. The block is built
# only where a prompt needs it (general.with_files)
def files_json(files) -> str | None:
    "The list of paths as the Files column keeps it - None for none."
    got = [str(f) for f in (files or []) if str(f or '').strip()]
    return json.dumps(got) if got else None
def files_of(row) -> list:
    "The paths a row's Files column keeps - [] for none. The one reader of the column (general.his_line reads a line by it)."
    try: got = json.loads((row or {}).get('Files') or '[]')
    except (TypeError, ValueError): return []
    return [str(f) for f in got] if isinstance(got, list) else []
_LEGACY_FILES = re.compile(r'\n\nATTACHED (?:IMAGES|FILES) \(read these files\)\n(.+)\Z', re.S)
def _legacy_split(body) -> tuple:
    "A row written before the field: (its words, its files) out of the block at its end - read once, by the migration (_files_out)."
    b = str(body or ''); m = _LEGACY_FILES.search(b)
    return (b[:m.start()], [x.strip() for x in m.group(1).splitlines() if x.strip()]) if m else (b, [])
MSG_COLS = ('TaskId', 'ExternalId', 'ConversationId', 'Channel', 'SourceName', 'Subject',
            'FromName', 'FromEmail', 'SentAt', 'BodyText', 'SourceLink', 'Status', 'Direction', 'RecipientsJson',
            'MailMetaJson', 'OwnText', 'TriageTitle', 'RankValue', 'RankWhy', 'SenderClass', 'MeetJson', 'HeaderClass')
RUN_COLS = ('Status', 'TraceJson', 'Result', 'LastError', 'SessionId', 'DiffText')
def thread_pinned(thread, mid):
    # triage writes mid 0 for "the mail being judged"; a stored reading names the real message
    return {k: [{**o, 'mid': mid} if isinstance(o, dict) and o.get('mid') == 0 else o for o in v] if isinstance(v, list) else v for k, v in thread.items()}
def _fold(value):
    """Case-fold for search. casefold() beats lower() on the pairs that differ (German ss)."""
    return str(value or '').casefold()


REVIEW_COLS = ('TaskId', 'MessageId', 'RunId', 'Kind', 'DraftText', 'FinalText', 'Status', 'Reason', 'Deliver', 'Origin', 'NextStep')
EDIT_PARTS = ('text', 'cc', 'bcc', 'subject', 'vals', 'fields', 'words', 'answers')      # what a card lets him change (heldEdits.js)
def his_edit(rv) -> dict:
    "What he has typed into review `rv`'s card and not pressed yet (Store.hold_review_edit) - {} for a card as filed."
    try: e = json.loads((rv or {}).get('OwnerEdit') or '{}')
    except (TypeError, ValueError): e = {}
    return e if isinstance(e, dict) else {}
def his_words(rv) -> str: return str(his_edit(rv).get('text') or '').strip()      # ...the words among it: a box he emptied holds none
EMPTY_DRAFT = 'the draft came back empty'     # update_review_draft's refusal: the card's plain line reads it (sendState.draftState)
POLICY_COLS = ('Name', 'Kind', 'Pattern', 'Action', 'Reason', 'SortOrder', 'Active', 'Mailbox')
SOURCE_COLS = ('Channel', 'Address', 'Owner', 'ConnectorId', 'Active', 'ConfigJson')
# The reports this app seeds, as (sentinel setting, the Address the seeder writes, the config type).
# KEEP IN STEP with the seeding blocks below - tests/test_assistant_blocks.py builds a fresh store and
# asserts this table describes the rows that actually appeared. The ownership heal reads it, and
# RETIRED_SEEDS beside it; nothing else may write `Owner='template'`.
SEEDED_REPORTS = (('assistant_report_seeded', 'Advisor', 'assistant'),
                  ('evening_inbox_report_seeded', 'End of day checkup', 'evening_inbox'),
                  ('glance_dashboard_seeded', 'Taskuary at a glance', 'dashboard'))
# ...and the ones a fresh install no longer gets, which older installs still carry and the heal still
# owes. The Morning digest: the walk now opens with who wants what (the owner, 2026-09-23: "remove the
# morning digest as report by default if the walk through does that"). An install that has one keeps
# it until its owner deletes it; the report type itself is still there to make one by hand.
RETIRED_SEEDS = (('digest_report_seeded', 'Morning digest', 'digest'),
                 # the Advisor was seeded as 'Assistant' until 2026-09-23 - the name the Assistant TAB
                 # also answers to (the owner: "rename assistant that reviews everything in the reports
                 # tab and gives you ideas ... since assistant is the one that walks you through")
                 ('assistant_report_seeded', 'Assistant', 'assistant'),
                 # Automation ideas: the Advisor reads the same month of counts once a week ([taskuary.automation]) and
                 # raises what is worth automating as an idea of its own (the owner, 2026-09-25: one voice, not two)
                 ('automate_report_seeded', 'Automation ideas', 'automate'))
PROJECT_COLS = ('Name', 'Description', 'Active', 'CreatedBy', 'UpdatedBy')
ROUTING_FACT_COLS = ('Field', 'Signal', 'SignalKey', 'Value', 'Confidence', 'EvidenceCount',
                     'Confirmed', 'Source')
PROJECT_LINK_COLS = ('ProjectId', 'Kind', 'Value', 'Label', 'Confidence', 'EvidenceCount',
                     'Confirmed', 'Source')
ATT_COLS = ('MessageId', 'ExternalId', 'Name', 'ContentType', 'Size', 'ContentId', 'Inline', 'Path')
ARTIFACT_COLS = ('TaskId', 'Name', 'ContentType', 'Size', 'Path', 'Kind', 'CreatedBy', 'Url', 'ExtId', 'Version')

# ── is this review live? one answer, two queries ─────────────────────────────────────────
# LEFT JOIN: a reply opened on a FILED message carries no task at all - the inner join made
# those reviews invisible everywhere, including the pending queue.
# A PENDING review must also point at work you can still SEE: a task folded away
# (dropped/done) or a message a skip policy hid would otherwise keep the badge at 1 with
# nothing on the timeline to answer - the queue self-heals instead. Decided reviews keep
# their history whatever happened to the task since.
# Both list_reviews (the queue) and pending_review (the funnel's "is a draft already
# waiting?") read these, so a review cannot be gone from one and live to the other.
_REVIEW_FROM = ('FROM review rv LEFT JOIN task t ON t.TaskId=rv.TaskId '
                'LEFT JOIN message m ON m.MessageId=COALESCE(rv.AnswersMid, rv.MessageId)')     # the message it ANSWERS (C2)
_NOT_ORPHAN = '(rv.TaskId IS NULL OR t.TaskId IS NOT NULL)'
# ...the comment kinds that are prompt machinery, not something said on the task (Store.list_comments): a kept line, a line put back in the
# owner's box, a turn's summary JSON, and a brief - a user turn filed by Taskuary (general.BRIEF_ACTOR) - each its own ActorType already
INTERNAL_TYPES = ('assistant_waiting', 'assistant_box', 'assistant_summary')
def is_internal(c) -> bool: return c.get('ActorType') in INTERNAL_TYPES or (c.get('ActorType') == 'assistant_user' and c.get('Actor') == 'taskuary')

_VISIBLE_PENDING = ("NOT (rv.Status='pending' AND (IFNULL(t.Status,'') IN ('dropped','done') "
                    "OR IFNULL(m.Status,'') IN ('context','skipped','ignored')))")

# ── one owner, one place ─────────────────────────────────────────────────────────────────
# The operator documents talk ABOUT the owner constantly ("protect John's time", "ask John in
# the session", "Sign as John Smith"). Typed literally, changing your name means finding nine
# of them, and the live docs ended up half real name and half John Smith. So the docs carry tokens
# and the name lives in one setting.
DOC_TOKENS = ('owner', 'owner_first', 'owner_email')
_TOKEN = re.compile(r'\{\{\s*(' + '|'.join(DOC_TOKENS) + r')\s*\}\}')
_SOUL_NAME = re.compile(r'You work for \*\*(?P<name>[^*]+)\*\*(?:\s*\((?P<email>[^)]*)\))?')

def render_doc(text: str, who: dict) -> str:
    return _TOKEN.sub(lambda m: str(who.get(m.group(1)) or ''), text or '')

def owner_from_soul(soul: str):
    mt = _SOUL_NAME.search(soul or '')
    name = mt.group('name').strip() if mt else None
    # a tokenized doc says "You work for **{{owner}}**" - that is not a name, it is the hole
    # the name goes in, and taking it literally rendered every doc with '{{owner}}' as the owner
    return None if (name and '{{' in name) else name

def email_from_soul(soul: str):
    mt = _SOUL_NAME.search(soul or '')
    return (mt.group('email') or '').strip() if mt else ''

# Every document that talks about the owner by name - set_owner and server._heal_owner_docs sweep the same list, and the store seeds it
# from its template. AGENT.md and CODING.md left it when no agent read them any more (2026-11-23): a copy on disk stays, unshown and unread.
# AGENTS.md ('agents', selfclose.guidance) is the one every agent reads - seeded on an install that had none, like the rest. ADVISOR.md
# ('advisor', lookout.goals) is what the Advisor looks out for, read by its look and its twice-a-day post (the owner, 2026-11-24).
OWNER_DOCS = ('soul', 'agents', 'job', 'digest', 'triage', 'style', 'counsel', 'advisor')     # LEARNED.md is written from the memory (memory.render), never a template
UNREAD_DOCS = ('agent', 'coding', 'learned-before-r10')          # ...and an old install's copies of them are never listed, searched or shown (doc_names)
TEMPLATE_OWNER = ('John Smith', 'john.smith@example.com')
NO_NAME_YET = ("THE OWNER'S NAME IS NOT SET YET. Who the owner is comes from the mailbox the mail arrived in (addressed_to_you), never "
               "from a name: an ask addressed to that mailbox is the owner's, whatever name it greets.")

def docs_hold_template_owner(store) -> bool:
    """Does any owner document still name the shipped example? Then a name saved beside it never reached the docs."""
    return any(TEMPLATE_OWNER[0] in (store.get_doc(d) or '') for d in OWNER_DOCS)

def set_owner(store, new: str, email=None, actor: str = 'owner') -> dict:
    """Your name, in ONE place (server.put_owner, and setup's About your work). SOUL.md and the rest refer to the owner by name: every literal occurrence of the OLD name becomes a {{owner}} token, so the documents never drift again."""
    was = store.owner()
    changed = []
    # 'the owner' is the fallback when no name is known, and real prose says those words - never retokenized
    if was['owner'] in ('the owner', '') or '{{' in was['owner']: was = {**was, 'owner': '', 'owner_email': ''}
    for doc in OWNER_DOCS:
        raw = store.get_doc(doc)
        if not raw: continue
        tokened = retoken_doc(raw, was['owner'], was['owner_email'])
        # a drifted doc holds BOTH names - the one typed in and the template's John Smith - so the placeholder is swept too
        tokened = retoken_doc(tokened, 'John Smith', 'john.smith@example.com')
        if tokened != raw:
            # tokenizing a name is not editing the document: one nobody touched keeps tracking the template (as _heal_owner_docs)
            store.save_doc(doc, tokened, 'template' if store.doc_owner(doc) == 'template' else actor)
            changed.append(doc)
    store.set_setting('owner_name', new, actor)
    if email is not None: store.set_setting('owner_email', str(email).strip(), actor)
    store.audit('doc', 0, 'set_owner', actor, detail={'from': was['owner'], 'to': new, 'retokened': changed})
    return {**store.owner(), 'retokened': changed}


def retoken_doc(text: str, old_name: str, old_email: str = '') -> str:
    """Turn the literal name already written into a document into {{owner}}. Longest form
    first, so "John Smith" does not become "{{owner}} Smith" - and never a name that is
    already inside a token, or one that is part of a longer word ("Johnson").

    This is what makes changing the name in ONE place change it everywhere: the document
    rewrites itself once, and from then on the name lives only in the setting."""
    out, full = text or '', (old_name or '').strip()
    if (old_email or '').strip(): out = out.replace(old_email.strip(), '{{owner_email}}')
    word = '\\b'
    if len(full) > 2: out = re.sub(word + re.escape(full) + word, '{{owner}}', out)
    first = full.split()[0] if full.split() else ''
    if len(first) > 2 and first != full:
        lhs, rhs = '(?<![{\\w])', '\\b(?![}\\w])'
        out = re.sub(lhs + re.escape(first) + rhs, '{{owner_first}}', out)
    return out


# A TQ number is the owner's: one per piece of work they can be handed. A row that only borrows the task
# table - the guide chat keeps its conversation and model session on one - takes its id from up here
# instead, or every New chat used a TQ number (125 of 261 in two weeks, 2026-10-09) and the owner's
# numbering read as skipping.
INTERNAL_TASK_BASE = 1_000_000_000
# WORK IS WHAT HAS A TQ NUMBER. The app's own conversations (the Assistant's chat) are stored as tasks above the base and are nobody's
# job: the lists triage is shown of the owner's open work leave them out, and no message lands on one (ingest.joinable). The chat was
# "the owner's own task, touched a minute ago" on every arrival, and a reply on a closed thread was read as its job and joined it
WORK = f't.TaskId<{INTERNAL_TASK_BASE}'
def task_ref(task_id): return f'TQ-{int(task_id):04d}'
# ...AND READ BACK ONE WAY (the audit, 2026-11-15: eleven regexes read a ref, and no two families agreed on the dash, the case or the zeros):
# TQ_REF finds the refs named in a sentence, TYPED_REF (fullmatch) is an id typed by itself - TQ-0004, tq4 or a bare 4. Any width: TQ-10000
TQ_REF = re.compile(r'\bTQ-?0*(\d+)\b', re.I)
TYPED_REF = re.compile(r'(?:tq-?)?0*(\d+)', re.I)
# the mails an Advisor line names in its words ("Erin mid 41 vs Gail mid 42"): Came from (idea_sources) and what its trust rests on
# (origin.idea_rests_on) read them the same way - every one, uncapped, for the trust
MID_CITE = re.compile(r'\bmids?[\s#:=]*(\d+(?:\s*(?:,|/|&|and)\s*#?\d+)*)')
def cited_mids(text) -> list: return [int(n) for g in MID_CITE.findall(str(text or '')) for n in re.findall(r'\d+', g)]
def by_sentence(s, n: int = 1200) -> str:
    """`s` whole when it fits, else cut after its last full sentence inside `n` - a reason cut at a character count ended mid-word
    on the card (walk 2026-10-29). No sentence end inside: the words up to `n`, never a broken one."""
    s = ' '.join(str(s or '').split())
    if len(s) <= n: return s
    head = s[:n]
    end = max(head.rfind(c + ' ') for c in '.!?')
    return head[:end + 1] if end > n // 3 else head.rsplit(' ', 1)[0] + '…'
ON_YOU_MAX = 300   # one box or On you step: cut on a sentence (by_sentence) - everywhere one is taken in, so none is cut twice
def is_goal(t) -> bool: return bool((t or {}).get('DoneWhen'))      # a goal is a task with a done-when sentence (spec 2026-10-12)
def agent_tickable(i) -> bool: return not (i.get('out') or i.get('tid'))   # an email box ticks when it goes, a goal's step when its task closes
def agent_tick(store, tid, item, done: bool = True, actor: str = 'agent') -> tuple:
    """THE ONE TICK ROAD for a session (`taskuary --tick`, the MCP tick tool, a shell-less chat's TICK mark): (box, None) once moved, or
    (None, (status, why)) - 404 for an id not on this task, 422 for a box that ticks itself. Only the box's state, never its words."""
    hit = next((i for i in store.task_checklist(tid) if i['id'] == str(item or '').strip()), None)
    # ...said so the agent does not carry it to the owner (recorded on the real CLI, 2026-11-15: "I could not tick the checklist item:
    # Taskuary does not recognise the to-do id" in his chat): the steps a turn leaves on him are rewritten from each turn's summary
    # (set_on_you), so an id from an earlier turn is simply gone with its step
    if not hit: return None, (404, f'no to-do {item} on this task now - the ids are in brackets in your checklist as it stands. A step from an '
                                   'earlier turn that is no longer listed needs no tick: carry on, and do not mention this to the owner')
    if not agent_tickable(hit): return None, (422, f"\"{hit['text']}\" ticks itself - when its email goes, or its task closes")
    store.tick_checklist_item(tid, hit['id'], done, actor)
    return hit, None
# THE TO-DO LIST IS THE ISSUE LIST (the owner, 2026-11-09: no new table): on a stream of reports the agent keeps triage's list accurate -
# adds what came in, rewords a box to what it really is, folds duplicates into one. Boxes that tick themselves (an email, a goal's step)
# are never reworded or folded, as never ticked by hand (agent_tickable)
def agent_todos(store, tid, add=(), reword=None, merge=(), actor: str = 'agent') -> dict:
    """{ok, checklist} with the list as written, or {ok: False, why}. `reword`: {id: new words}; `merge`: [{ids: [...], text?}] - each group
    folds into its first box (its words, or `text`), done when any of them was."""
    with store.lock:
        items = store.task_checklist(tid); by = {i['id']: i for i in items}
        bad = [k for k in [*(reword or {}), *(x for g in merge or () for x in (g.get('ids') or []))] if k not in by]
        if bad: return {'ok': False, 'why': f"no to-do {', '.join(map(str, bad))} on this task - the ids are in my_task's checklist"}
        fixed = [by[k]['text'] for k in [*(reword or {}), *(x for g in merge or () for x in (g.get('ids') or []))] if not agent_tickable(by[k])]
        if fixed: return {'ok': False, 'why': f"\"{fixed[0]}\" is an email or a step that ticks itself - its words are not yours to change"}
        for k, w in (reword or {}).items():
            if (w := ' '.join(str(w or '').split())[:300]): by[k]['text'] = w
        gone = set()
        for g in merge or ():
            ids = [k for k in dict.fromkeys(g.get('ids') or []) if k not in gone]
            if len(ids) < 2: continue
            keep = by[ids[0]]
            if (w := ' '.join(str(g.get('text') or '').split())[:300]): keep['text'] = w
            keep['done'] = any(by[k].get('done') for k in ids)
            gone.update(ids[1:])
        items = [i for i in items if i['id'] not in gone]
        have = {i['text'] for i in items}; used = {i['id'] for i in items} | gone
        for text in store.clean_checklist(list(add or ()), cap=False):
            if text in have: continue
            d = hashlib.sha1(text.encode()).hexdigest()
            items.append({'id': next((d[:n] for n in range(8, len(d) + 1) if d[:n] not in used), d), 'text': text, 'done': False})
            have.add(text); used.add(items[-1]['id'])
        store._write_checklist(tid, items, actor)
    return {'ok': True, 'checklist': [f"[{i['id']}] {'x' if i.get('done') else ' '} {i['text']}" for i in items]}
def auto_code_enabled(src) -> bool:
    """Does new coding work start its agent by itself? ONE read of `coding_auto_enabled` (a store or its settings
    dict), missing = the seeded default. Four readers used to disagree: three read missing as off, one as on."""
    cfg = src if isinstance(src, dict) else src.get_settings()
    return str(cfg.get('coding_auto_enabled', DEFAULT_SETTINGS['coding_auto_enabled'])) == '1'
def _now(): return datetime.now().isoformat(sep=' ', timespec='seconds')
# a review's words written now, when they differ from what it held (SET reads the row as it was): the same text saved again keeps its time
_DRAFT_AT = 'DraftAt=CASE WHEN DraftText IS ? THEN DraftAt ELSE ? END'
def _cfg_type(cj) -> str:
    try: return str((json.loads(cj or '{}') or {}).get('type') or '')
    except (TypeError, ValueError): return ''
# the model's own thought (idea:<slug>, or report:<id>:idea:<slug> from a report) - not a candidate the hub found
def is_model_idea(key) -> bool: return ':idea:' in f':{key}'

# The one sentence of TRIAGE.md that was wrong, and what replaces it on a doc that has stopped
# tracking the shipped template (the migration in _ensure_schema). The canonical wording lives in
# templates/triage.md; test_triage_pr_rule.py pins these two together so they cannot drift apart.
# THE CONTRACT LINE, which is the first thing the model reads and is therefore read as the whole
# schema. It named intent/kind/why, so a verdict that answered exactly that was obeying the
# document - and the title and summary every row is drawn from were asked for 16,000 characters
# later, in a block the code appends when the document forgets them. On a long forwarded mail the
# model followed the line and dropped the pair (TQ-0665). templates/triage.md carries the new
# wording; test_verdict_shape.py pins the two together so they cannot drift apart.
# The summary's wording inside that line. It used to ask for "what was said and by whom", which
# the model answered as a report of the mail; every card in the walk leads with this sentence, and
# the owner wants it to say who wants what (2026-09-23), so the ask is the first thing read.
_SUMMARY_WAS = ('"summary": "<what was said and by whom, two sentences - the point itself, never the signature, '
                'the confidentiality footer or quoted earlier mail>"')
_SUMMARY_NOW = ('"summary": "<two sentences. The first says who wants what from the owner, the asker first '
                "('Erin Blake wants the Q3 numbers before Friday'), or on an fyi who says what ('Payworth says the "
                "September statement is ready'); the second adds the one detail that matters - a date, an amount, "
                'what was already done. Never the signature, the confidentiality footer or quoted earlier mail>"')
# WHERE CODING WORK IS DONE IS NOT TRIAGE'S (the owner, 2026-11-06: "let's take repo decision out of the triage - remove it completely"):
# the coding agent picks its repository (repochoice). The guide's paragraph that asked for one comes out of an edited TRIAGE.md where it
# still reads as shipped; templates/triage.md no longer has it (test_repo_left_to_the_agent.py pins both).
_REPO_CHOICE_WAS = ("**Which repository.** For a task an agent could work from a keyboard, answer `repository` with one of `known_repositories`, "
                    "from what the request is about, with `repo_reason` saying what in the request points there. `project_context` (the sender's "
                    "past repository choices) is supporting evidence, not proof: it helps say what a message is about, it never makes an "
                    "informational message a task, it is never permission to write or send anything, and a tentative link stays tentative. "
                    "When two are plausible or none fits, answer null with `needs_repo_choice` true and the owner chooses.")
# The kind rules as shipped before 2026-09-23 and what replaced them (templates/triage.md) - kept as
# data so the swap is exact; test_kind_dispatch.py holds the template to the "now" side.
with open(__file__[:__file__.replace('\\', '/').rfind('/') + 1] + 'triage_kind_rules.json', encoding='utf-8') as _f:
    _KIND_RULES = [tuple(p) for p in json.load(_f)]
_CODING_WAS = "`coding` is for work INSIDE a system this install holds the code or the credentials for: a change to one of the owner's repositories, a query against one of their databases, a file or report produced from them, an account on a system they run."
_CODING_NOW = "`coding` is for a CHANGE inside a system this install holds the code or the credentials for: code changed in one of the owner's repositories, data changed in one of their systems, an account created or granted on a system they run. Reading from those systems - a query, a report, a look-up - changes nothing and is `general`."
_SHAPE_WAS = ('Classify one inbound work message. Answer JSON only: {"intent": "task|reply_only|fyi", '
              '"kind": "coding|general|task", "why": "<one concrete sentence: what you saw in the message '
              'and which rule it hit - the owner reads this to judge the verdict, 25 words max>"}.')
_SHAPE_NOW = (_SHAPE_WAS[:-2].rstrip('}')
              + ', "title": "<what this IS, 12 words max, in your own words - never the subject line handed back>"'
              + ', ' + _SUMMARY_NOW
              + ', "checklist": ["<on a task only: one distinct requested outcome each>"]}.\n\n'
              + 'Every row the owner reads is drawn from `title` and `summary`, so answer them WHATEVER the '
                'verdict: an fyi and a report are rows too, and "RE: RE: FW: 0 rows returned for period ending '
                '09/15" is a mail header, not a sentence.')
_PR_RULE_WAS = ("A stranger's pull request or issue is fyi (or reply_only if it asks a real question) - never "
                "task: the owner promotes what deserves work. ")
_PR_RULE_NOW = (
    "\n\nA PULL REQUEST is a task, and its kind is coding - whoever opened it. A PR exists for exactly one "
    "reason: somebody is asking for a review and a merge of a diff on a repository you own. That is a request, "
    "it names its own repository, and reading a diff is what the coding agent does; it is never fyi, and you do "
    "not need to find an ask in the description - the PR IS the ask. Association does not change this, it changes "
    "only how much the diff should be doubted, which is the reviewer's job and not yours. Nothing starts "
    "unattended on a code-host item either way, so a stranger's PR costs the owner one glance at a queued task."
    "\n\nA stranger's ISSUE is a different thing and keeps the skepticism: it is fyi (or reply_only if it asks a "
    "real question) unless it reports something that plainly needs doing - the owner promotes what deserves work."
    "\n\n")

# conversation ids that name a CHAT rather than a topic - one id for every message ever exchanged
# there, so an owner verdict on it covers an episode, not the relationship (owner_verdict_on_thread)
from .routing import CHAT_CHANNELS                 # the one list of chat channels (routing.py)
CHAT_PREFIXES = tuple(sorted(f'{c}:' for c in CHAT_CHANNELS))
# (CHAT_VERDICT_HOURS is gone: a chat ruling carries nothing forward at all - see
# owner_verdict_on_thread. "Nothing to do here" is about the message it was said on.)

def norm_stamp(s) -> str:
    """One clock for the timeline: every channel's timestamp lands as LOCAL 'YYYY-MM-DD
    HH:MM:SS'. A single path storing raw UTC ISO ('...T18:44:00Z') string-sorted ABOVE later
    local rows ('T' > ' ' at position 10) while displaying as the local afternoon - a
    timeline visibly out of order. Anything unparseable passes through untouched."""
    if not s: return _now()
    t = str(s).strip().replace('Z', '+00:00')
    # py3.10's fromisoformat accepts exactly 3 or 6 fractional digits and Graph sends TWO
    # ('...:37.94Z'), so this raised, the value was handed back untouched, and the heal below
    # has been a no-op since the day it was written. Those rows kept sorting above every later
    # message ('T' > ' ' at position 10) - which is how list_messages hands an agent a
    # three-day-old message as "the ask" and the real one never reaches it.
    t = re.sub(r'\.(\d{1,6})(?=[+-]|$)', lambda m: '.' + m.group(1).ljust(6, '0'), t)
    try: d = datetime.fromisoformat(t)
    except ValueError: return str(s)
    if d.tzinfo: d = d.astimezone()
    return d.replace(tzinfo=None).isoformat(sep=' ', timespec='seconds')

def chain_hash(prev, payload):
    return hashlib.sha256((prev + json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)).encode()).hexdigest()

def _audit_payload(et, eid, action, actor, actor_type, run_id, detail):
    return {'entity_type': et, 'entity_id': eid, 'action': action, 'actor': actor,
            'actor_type': actor_type, 'run_id': run_id, 'detail': detail}

SCHEMA = """
CREATE TABLE IF NOT EXISTS task (TaskId INTEGER PRIMARY KEY, Title TEXT, Summary TEXT,
  Kind TEXT DEFAULT 'general', Status TEXT DEFAULT 'open', Priority TEXT DEFAULT 'normal',
  Assignee TEXT, Source TEXT DEFAULT 'manual', SourceRef TEXT, Tags TEXT,
  CreatedBy TEXT, CreatedAt TEXT, UpdatedBy TEXT, UpdatedAt TEXT, ClosedAt TEXT, RemindAt TEXT,
  AskedVia TEXT, AskedTold TEXT, AskedToldAt TEXT, AskedWatch TEXT, AskedSeenMid INTEGER, RemindVia TEXT, RemindOwed TEXT,
  AskedWatchAt TEXT, AskedNudgedAt TEXT, DueAt TEXT, DueSaid TEXT, DueRaised TEXT, DoneWhen TEXT, ParentId INTEGER, Files TEXT);
CREATE TABLE IF NOT EXISTS message (MessageId INTEGER PRIMARY KEY, TaskId INTEGER, ExternalId TEXT,
  ConversationId TEXT, Channel TEXT, SourceName TEXT, Subject TEXT, FromName TEXT, FromEmail TEXT,
  SentAt TEXT, BodyText TEXT, SourceLink TEXT, Status TEXT DEFAULT 'routed', CreatedAt TEXT,
  Direction TEXT DEFAULT 'in', RecipientsJson TEXT, MailMetaJson TEXT, OwnText TEXT, SenderClass TEXT);
-- handled mail moved to its mailbox's Archive, or why it was not (filing.py): one try per message, never a retry loop
CREATE TABLE IF NOT EXISTS mail_filed (MessageId INTEGER PRIMARY KEY, FiledAt TEXT, Result TEXT);
-- mail the owner read here, marked read in its mailbox, or why not (filing.mark_read_back): once per message
CREATE TABLE IF NOT EXISTS mail_read_back (MessageId INTEGER PRIMARY KEY, At TEXT, Result TEXT);
CREATE TABLE IF NOT EXISTS attachment (AttachmentId INTEGER PRIMARY KEY, MessageId INTEGER, ExternalId TEXT,
  Name TEXT, ContentType TEXT, Size INTEGER, ContentId TEXT, Inline INTEGER DEFAULT 0, Path TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS transcript (TranscriptId INTEGER PRIMARY KEY, TaskId INTEGER, Sid TEXT,
  Agent TEXT, Cwd TEXT, Text TEXT, CreatedAt TEXT, ExtId TEXT);
CREATE TABLE IF NOT EXISTS session_resume (TaskId INTEGER PRIMARY KEY, Pick TEXT, Model TEXT,
  NativeId TEXT, ContextKey TEXT, UpdatedAt TEXT, Frozen TEXT);
CREATE TABLE IF NOT EXISTS task_artifact (ArtifactId INTEGER PRIMARY KEY, TaskId INTEGER, Name TEXT,
  ContentType TEXT, Size INTEGER, Path TEXT, Kind TEXT, CreatedBy TEXT, CreatedAt TEXT, Url TEXT, ExtId TEXT, Version TEXT);
CREATE TABLE IF NOT EXISTS route (RouteId INTEGER PRIMARY KEY, MessageId INTEGER, TaskId INTEGER,
  Decision TEXT, Score REAL, Reason TEXT, CandidatesJson TEXT, RoutedBy TEXT, CreatedAt TEXT,
  RawOutput TEXT, ParseError TEXT, VerdictJson TEXT);
CREATE TABLE IF NOT EXISTS comment (CommentId INTEGER PRIMARY KEY, TaskId INTEGER, Actor TEXT,
  ActorType TEXT, Body TEXT, CreatedAt TEXT, LineId TEXT, Files TEXT);
CREATE TABLE IF NOT EXISTS audit (Id INTEGER PRIMARY KEY, EntityType TEXT, EntityId INTEGER,
  Action TEXT, Actor TEXT, ActorType TEXT, RunId INTEGER, Detail TEXT, PrevHash TEXT, RowHash TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS agent (AgentId INTEGER PRIMARY KEY, Name TEXT UNIQUE, Kind TEXT,
  Runner TEXT, Config TEXT, Active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS run (RunId INTEGER PRIMARY KEY, TaskId INTEGER, AgentName TEXT,
  Status TEXT DEFAULT 'running', Instruction TEXT, TraceJson TEXT, Result TEXT, LastError TEXT,
  SessionId TEXT, DiffText TEXT, DispatchedBy TEXT, StartedAt TEXT, UpdatedAt TEXT, FinishedAt TEXT);
CREATE TABLE IF NOT EXISTS review (ReviewId INTEGER PRIMARY KEY, TaskId INTEGER, MessageId INTEGER,
  RunId INTEGER, Kind TEXT, DraftText TEXT, FinalText TEXT, Status TEXT DEFAULT 'pending',
  Reason TEXT, DecidedBy TEXT, DecidedAt TEXT, DecideNote TEXT, CreatedAt TEXT, Deliver TEXT, Origin TEXT);
CREATE TABLE IF NOT EXISTS policy (PolicyId INTEGER PRIMARY KEY, Name TEXT, Kind TEXT, Pattern TEXT,
  Action TEXT, Reason TEXT, SortOrder INTEGER DEFAULT 100, Active INTEGER DEFAULT 1, CreatedBy TEXT, Mailbox TEXT);
CREATE TABLE IF NOT EXISTS source (SourceId INTEGER PRIMARY KEY, Channel TEXT, Address TEXT,
  Owner TEXT, ConnectorId INTEGER, Active INTEGER DEFAULT 1, ConfigJson TEXT, LastPolledAt TEXT);
CREATE TABLE IF NOT EXISTS connector (ConnectorId INTEGER PRIMARY KEY, Type TEXT, Name TEXT,
  ConfigJson TEXT, Secret TEXT, Active INTEGER DEFAULT 0, LastSyncAt TEXT, LastError TEXT, LastErrorAt TEXT, Roles TEXT,
  Scope TEXT);
-- every write to the connectors, from any process, moves its generation: list_connectors keeps its read until it moves
CREATE TABLE IF NOT EXISTS change_gen (Tbl TEXT PRIMARY KEY, Gen INTEGER NOT NULL DEFAULT 0);
INSERT OR IGNORE INTO change_gen (Tbl, Gen) VALUES ('connector', 0);
CREATE TRIGGER IF NOT EXISTS connector_gen_ins AFTER INSERT ON connector BEGIN UPDATE change_gen SET Gen=Gen+1 WHERE Tbl='connector'; END;
CREATE TRIGGER IF NOT EXISTS connector_gen_upd AFTER UPDATE ON connector BEGIN UPDATE change_gen SET Gen=Gen+1 WHERE Tbl='connector'; END;
CREATE TRIGGER IF NOT EXISTS connector_gen_del AFTER DELETE ON connector BEGIN UPDATE change_gen SET Gen=Gen+1 WHERE Tbl='connector'; END;
CREATE TABLE IF NOT EXISTS setting (Name TEXT PRIMARY KEY, Value TEXT, Description TEXT, UpdatedBy TEXT);
CREATE TABLE IF NOT EXISTS deleted (DeletedId INTEGER PRIMARY KEY, Kind TEXT, Title TEXT, DataJson TEXT, DeletedAt REAL, KeepUntil REAL);
-- (the notes table, `memory`, is gone: an older install's rows are read into memory_line once and the table dropped - memory.migrate)
-- A small project graph. `project_link` is deliberately generic: repositories, email addresses,
-- WhatsApp JIDs and future customer/system identities all point at the same project. Evidence is
-- task-keyed so replaying startup history cannot make a guess grow more confident each launch.
CREATE TABLE IF NOT EXISTS project (ProjectId INTEGER PRIMARY KEY, Name TEXT COLLATE NOCASE UNIQUE,
  Description TEXT, Active INTEGER DEFAULT 1, CreatedBy TEXT, CreatedAt TEXT, UpdatedBy TEXT, UpdatedAt TEXT);
CREATE TABLE IF NOT EXISTS project_link (LinkId INTEGER PRIMARY KEY, ProjectId INTEGER NOT NULL,
  Kind TEXT NOT NULL, Value TEXT COLLATE NOCASE NOT NULL, Label TEXT, Confidence REAL DEFAULT 0,
  EvidenceCount INTEGER DEFAULT 0, Confirmed INTEGER DEFAULT 0, Source TEXT, CreatedAt TEXT, UpdatedAt TEXT,
  UNIQUE(ProjectId, Kind, Value));
CREATE TABLE IF NOT EXISTS project_evidence (EvidenceId INTEGER PRIMARY KEY, LinkId INTEGER NOT NULL,
  TaskId INTEGER NOT NULL, Reason TEXT, CreatedAt TEXT, UNIQUE(LinkId, TaskId));
-- What triage decided, and what the owner made of it. Deliberately project_link's shape: the
-- repository field has had exactly this loop since the project graph landed, and it is the only
-- verdict field that ever learned anything. `routing_fact` generalises it to the rest - one field
-- of the verdict, keyed to a signal the NEXT message can carry - rather than inventing a second
-- vocabulary for the same idea. Evidence is task-keyed, so a replay cannot inflate a guess.
CREATE TABLE IF NOT EXISTS routing_fact (FactId INTEGER PRIMARY KEY, Field TEXT NOT NULL,
  Signal TEXT NOT NULL, SignalKey TEXT COLLATE NOCASE NOT NULL, Value TEXT NOT NULL,
  Confidence REAL DEFAULT 0, EvidenceCount INTEGER DEFAULT 0, Confirmed INTEGER DEFAULT 0,
  Source TEXT, CreatedAt TEXT, UpdatedAt TEXT, UNIQUE(Field, Signal, SignalKey, Value));
CREATE TABLE IF NOT EXISTS routing_evidence (EvidenceId INTEGER PRIMARY KEY, FactId INTEGER NOT NULL,
  TaskId INTEGER NOT NULL, Reason TEXT, CreatedAt TEXT, UNIQUE(FactId, TaskId));
CREATE TABLE IF NOT EXISTS doc (Name TEXT PRIMARY KEY, Content TEXT, UpdatedBy TEXT, UpdatedAt TEXT);
CREATE TABLE IF NOT EXISTS dispatchq (QId INTEGER PRIMARY KEY, TaskId INTEGER, BehindTaskId INTEGER,
  Agent TEXT, Reason TEXT, CreatedAt TEXT);
-- A BATCH (batch.py): the ranked arrivals of one repository, let in together as ONE task an agent works top-down.
-- One row per item, in the order ranking put them (Place). State: waiting -> working -> needs_you | done, or ended
-- (closed or merged upstream). The task closes when every item is done or ended.
CREATE TABLE IF NOT EXISTS batch_item (ItemId INTEGER PRIMARY KEY, TaskId INTEGER NOT NULL, ConversationId TEXT NOT NULL,
  MessageId INTEGER, Place INTEGER, Title TEXT, Link TEXT, State TEXT DEFAULT 'waiting', Result TEXT, Overlap TEXT,
  EndedWhy TEXT, Sha TEXT, Propose TEXT, CreatedAt TEXT, UpdatedAt TEXT, UNIQUE(TaskId, ConversationId));
CREATE INDEX IF NOT EXISTS idx_batch_item_conv ON batch_item(ConversationId);
CREATE TABLE IF NOT EXISTS waitroom (WId INTEGER PRIMARY KEY, TaskId INTEGER, Note TEXT, CreatedBy TEXT,
  CreatedAt TEXT, DeliveredAt TEXT, How TEXT, Files TEXT);
-- WHAT THE AGENT HEARD, AND WHEN (conversation.py): one row per input handed to a task's agent - his line (by the name it was sent under), a
-- message that came in, a press - and one per turn begun. An input is in it once: that is the chat's "told once", kept by the key.
CREATE TABLE IF NOT EXISTS heard (HId INTEGER PRIMARY KEY, TaskId INTEGER, Kind TEXT, Ref TEXT, At REAL, Grp INTEGER, Seq INTEGER, Sid TEXT,
  UNIQUE(TaskId, Kind, Ref));
-- WHERE EACH ITEM OF A TASK'S CHAT FIRST STOOD (conversation.items): its place, once served, for good - a reload, a reopen and a restart
-- draw the same order, and what is new only ever goes under it
-- ...and a card, the turn it was first drawn in (`Host`): it goes down to a later turn that left it again, never back up
CREATE TABLE IF NOT EXISTS shown (TaskId INTEGER, Key TEXT, Seq INTEGER, Host TEXT, UNIQUE(TaskId, Key));
-- ONE LOG PER TASK (chatlog.py): each thing the chat draws, appended once, at the place it gets then (`Id`) - nothing renumbers, re-sorts or
-- re-dates it; what can change (a turn's state, a card pressed) is updated in place (`State`, `Body`, `Rev`). At most one card waits per task
CREATE TABLE IF NOT EXISTS chatlog (Id INTEGER PRIMARY KEY, TaskId INTEGER NOT NULL, Key TEXT NOT NULL, Kind TEXT NOT NULL, Parent INTEGER,
  At REAL NOT NULL, Src TEXT, Body TEXT NOT NULL, State TEXT, Rev INTEGER NOT NULL DEFAULT 0, UNIQUE(TaskId, Key));
CREATE INDEX IF NOT EXISTS idx_chatlog ON chatlog(TaskId, Id);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_card ON chatlog(TaskId) WHERE Kind='card' AND State='pending';
CREATE TABLE IF NOT EXISTS chatlog_task (TaskId INTEGER PRIMARY KEY, Rev INTEGER NOT NULL DEFAULT 0, Migrated TEXT);
-- WHAT A TASK'S AGENT IS TOLD BETWEEN TURNS (events.py): each fact once, written where it happens - a message on the task, his line, a card's
-- state, his press, Taskuary's note - and the one agent's cursor into them (`Upto`; `Told`: ids past it a turn at work was handed already)
CREATE TABLE IF NOT EXISTS event (Id INTEGER PRIMARY KEY, TaskId INTEGER NOT NULL, At REAL NOT NULL, Kind TEXT NOT NULL, Key TEXT NOT NULL,
  Body TEXT NOT NULL, UNIQUE(TaskId, Key));
CREATE TABLE IF NOT EXISTS event_cursor (TaskId INTEGER PRIMARY KEY, Upto INTEGER NOT NULL DEFAULT 0, Told TEXT NOT NULL DEFAULT '[]');
-- The agent wall (blackboard.py): what one agent leaves for the next one in the same
-- checkout. Derived facts (who holds which file) are read off git and the run trace and are
-- never stored; this is the part only the agent knows - what it is doing, what it found, what
-- it is about to push, and what the next one must not touch.
CREATE TABLE IF NOT EXISTS boardnote (NoteId INTEGER PRIMARY KEY, TaskId INTEGER, Agent TEXT,
  Cwd TEXT, Kind TEXT, Body TEXT, Files TEXT, CreatedAt TEXT, ReadBy TEXT);
CREATE INDEX IF NOT EXISTS idx_boardnote_cwd ON boardnote(Cwd, NoteId);
-- ...and what one agent says TO another (peers.py): one row per receiving task, fanned out when it is sent. Scope says who it was
-- addressed to (task | repo | all); ReadAt is set when it rides into that task's agent's next turn.
CREATE TABLE IF NOT EXISTS peernote (PeerNoteId INTEGER PRIMARY KEY, FromTask INTEGER, ToTask INTEGER, Scope TEXT, Repo TEXT,
  Body TEXT, CreatedAt TEXT, ReadAt TEXT);
CREATE INDEX IF NOT EXISTS idx_peernote_to ON peernote(ToTask, ReadAt);
-- AGENT CHANNELS (agentchannels.py): one chat - WhatsApp, Telegram, Slack, Teams - bound to one coding agent (TaskId) or to the coding
-- agents at large (TaskId NULL, the owner alone), its members named by the owner; StateJson holds the question up there and the read cursor.
-- Each message in or out is a row of agentchannel_msg, keyed by its provider id, so a re-read never routes a line twice.
CREATE TABLE IF NOT EXISTS agentchannel (ChannelId INTEGER PRIMARY KEY, Kind TEXT, Chat TEXT, ConnectorId INTEGER, TaskId INTEGER,
  Repo TEXT, MembersJson TEXT, StateJson TEXT, CreatedAt TEXT, UNIQUE(Kind, Chat));
CREATE TABLE IF NOT EXISTS agentchannel_msg (Id INTEGER PRIMARY KEY, ChannelId INTEGER, ExtId TEXT, Dir TEXT, Who TEXT, Role TEXT,
  TaskId INTEGER, Text TEXT, At TEXT, UNIQUE(ChannelId, ExtId));
-- ...and the owner's "always" answers to an agent's permission requests (permissions.py), per task and tool pattern
CREATE TABLE IF NOT EXISTS permrule (RuleId INTEGER PRIMARY KEY, TaskId INTEGER, Pattern TEXT, Answer TEXT, CreatedAt TEXT,
  UNIQUE(TaskId, Pattern));
CREATE TABLE IF NOT EXISTS learned_history (Id INTEGER PRIMARY KEY, Key TEXT, Text TEXT, Status TEXT, Score INTEGER,
  Ev TEXT, Action TEXT, Actor TEXT, At TEXT);
-- ...and each line's standing (phase C 2026-10-23, read once by memory.migrate): who reads it, watching / in_use / wrong / forgotten, the owner's
-- own wording, the tombstone that keeps a removed line from being written back. LEARNED.md is the readable face of the in-use rows.
CREATE TABLE IF NOT EXISTS learned_line (Key TEXT PRIMARY KEY, Reader TEXT, Text TEXT, OwnerText TEXT, Status TEXT, Score INTEGER,
  Ev TEXT, InDoc INTEGER DEFAULT 1, InUseAt TEXT, ForgotEv INTEGER, Source TEXT, UpdatedAt TEXT);
-- THE OWNER'S MEMORY (memory.py, r10 2026-11-23): what he SAID (one live line per Subject - a correction replaces), and what was INFERRED
-- from what he did (its evidence Ev and count N, used only once Confirmed). Facts are read where they are kept, never copied here.
-- learned_line and learned_history above are LEARNED.md's old bookkeeping, read once by memory.migrate.
CREATE TABLE IF NOT EXISTS memory_line (Id INTEGER PRIMARY KEY, Kind TEXT NOT NULL, Subject TEXT NOT NULL DEFAULT '', Text TEXT NOT NULL,
  People TEXT DEFAULT '', Scope TEXT DEFAULT 'global', ScopeKey TEXT DEFAULT '', Ev TEXT DEFAULT '', N INTEGER DEFAULT 1,
  Confirmed INTEGER DEFAULT 0, Status TEXT DEFAULT 'live', Source TEXT DEFAULT '', Workstream TEXT DEFAULT '', At TEXT, UpdatedAt TEXT,
  ReplacedBy INTEGER);
CREATE INDEX IF NOT EXISTS ix_memory_line ON memory_line(Status, Kind, Subject);
CREATE TABLE IF NOT EXISTS idea (IdeaId INTEGER PRIMARY KEY, Key TEXT UNIQUE, Kind TEXT, Text TEXT, ActionJson TEXT, Sig TEXT,
  Status TEXT DEFAULT 'open', SnoozeUntil TEXT, MessageId INTEGER, FirstSeen TEXT, LastSaid TEXT, SaidCount INTEGER DEFAULT 0,
  DecidedBy TEXT, DecidedAt TEXT);
-- The pipe's memory (funnel.py): what the assistant has already surfaced in this walk, what the
-- owner marked done or pushed back, and until when. Keys are the funnel item's own; the FACTS
-- behind an item are never stored here, they are recomputed - a reply approved or a task closed
-- leaves the pile on its own.
CREATE TABLE IF NOT EXISTS funnel_state (Key TEXT PRIMARY KEY, Status TEXT, Until TEXT, Note TEXT, By TEXT, At TEXT);
-- What the owner's own sent words MEAN, read once each by the model (sentjudge.py): an ask of the other side, a promise
-- of theirs - what and by when - and, for a promise, the later message of theirs that delivered it. Replaces the
-- _ASKS/_PROMISE regexes that picked which threads the Advisor could talk about (the owner, 2026-10-11).
CREATE TABLE IF NOT EXISTS sent_verdict (MessageId INTEGER PRIMARY KEY, ConversationId TEXT, AsksThem INTEGER, Promise INTEGER,
  What TEXT, Due TEXT, DeliveredBy INTEGER, JudgedAt TEXT, JudgedBy TEXT);
-- Phase 1 inventory foundation.  These tables are additive and deliberately stay empty until
-- backfill_processing is called explicitly after a consistent legacy snapshot is available.
CREATE TABLE IF NOT EXISTS processing_item (ItemId TEXT PRIMARY KEY, Kind TEXT NOT NULL,
  ContextRevision TEXT, ViewRevision TEXT, RedirectItemId TEXT, CreatedAt TEXT NOT NULL, UpdatedAt TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processing_member (MemberId INTEGER PRIMARY KEY, ItemId TEXT NOT NULL,
  EntityKind TEXT NOT NULL, LocalId TEXT NOT NULL, Role TEXT NOT NULL DEFAULT 'member',
  JoinedAt TEXT NOT NULL, RetiredAt TEXT);
CREATE TABLE IF NOT EXISTS processing_alias (AliasId INTEGER PRIMARY KEY, Namespace TEXT NOT NULL,
  Scope TEXT NOT NULL, Value TEXT NOT NULL, EntityKind TEXT NOT NULL, LocalId TEXT NOT NULL,
  Provenance TEXT NOT NULL, CreatedAt TEXT NOT NULL, RetiredAt TEXT);
CREATE TABLE IF NOT EXISTS processing_relation (RelationId INTEGER PRIMARY KEY,
  FromEntityKind TEXT NOT NULL, FromLocalId TEXT NOT NULL, ToEntityKind TEXT NOT NULL,
  ToLocalId TEXT NOT NULL, Kind TEXT NOT NULL, Provenance TEXT NOT NULL, CreatedAt TEXT NOT NULL,
  RetiredAt TEXT);
CREATE TABLE IF NOT EXISTS processing_legacy_evidence (EvidenceId INTEGER PRIMARY KEY,
  MigrationVersion TEXT NOT NULL, ItemId TEXT, EntityKind TEXT NOT NULL, LocalId TEXT NOT NULL,
  SelectedLegacyKey TEXT, ObservedUnread INTEGER, PermanentRead INTEGER, ReasonsJson TEXT NOT NULL,
  TemporaryDeferJson TEXT, ContextFingerprint TEXT NOT NULL, OriginalJson TEXT NOT NULL, CapturedAt TEXT NOT NULL,
  UNIQUE(MigrationVersion, EntityKind, LocalId));
CREATE TABLE IF NOT EXISTS processing_migration (Version TEXT PRIMARY KEY, CapturedAt TEXT NOT NULL,
  InputWatermark TEXT NOT NULL, SettingsJson TEXT NOT NULL, Completion TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processing_context_snapshot (
  MigrationVersion TEXT NOT NULL, ItemId TEXT NOT NULL, ContextRevision TEXT NOT NULL,
  ViewRevision TEXT NOT NULL, ContextJson TEXT NOT NULL, ViewJson TEXT NOT NULL,
  PRIMARY KEY (MigrationVersion, ItemId));
CREATE TABLE IF NOT EXISTS processing_read_activation (
  Singleton INTEGER PRIMARY KEY CHECK (Singleton=1), Version TEXT NOT NULL, ActivatedAt TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processing_read_receipt (
  EntityKind TEXT NOT NULL, LocalId TEXT NOT NULL, Fingerprint TEXT NOT NULL,
  Version TEXT NOT NULL, ReadAt TEXT NOT NULL, ReadBy TEXT, Origin TEXT NOT NULL,
  PRIMARY KEY (EntityKind,LocalId,Fingerprint));
CREATE TABLE IF NOT EXISTS processing_read_defer (
  Key TEXT PRIMARY KEY, TargetItemId TEXT NOT NULL, TargetEntityKind TEXT, TargetLocalId TEXT,
  Status TEXT NOT NULL, Until TEXT, At TEXT NOT NULL, By TEXT);
CREATE INDEX IF NOT EXISTS idx_processing_read_defer_entity
  ON processing_read_defer(TargetEntityKind,TargetLocalId);
CREATE TABLE IF NOT EXISTS processing_display_summary (
  Key TEXT PRIMARY KEY, ContextRevision TEXT NOT NULL, Summary TEXT NOT NULL);
-- Raw writes and canonical identity reconciliation advance independently.  A newly
-- widened database starts pending even when its old rows predate the triggers.
CREATE TABLE IF NOT EXISTS processing_reconcile_state (
  Singleton INTEGER PRIMARY KEY CHECK (Singleton=1),
  DirtyGeneration INTEGER NOT NULL DEFAULT 1,
  AttemptedGeneration INTEGER NOT NULL DEFAULT 0,
  ReconciledGeneration INTEGER NOT NULL DEFAULT 0,
  LastAttemptAt TEXT,
  ConflictsJson TEXT NOT NULL DEFAULT '[]',
  DiagnosticsJson TEXT NOT NULL DEFAULT '[]',
  MembershipGeneration INTEGER NOT NULL DEFAULT 0,
  CensusGeneration INTEGER NOT NULL DEFAULT -1);
INSERT OR IGNORE INTO processing_reconcile_state (Singleton) VALUES (1);
-- Which rows changed, for the rail (processing_rail): re-project those roots, reuse the rest.
CREATE TABLE IF NOT EXISTS processing_dirty_row (
  Id INTEGER PRIMARY KEY, Kind TEXT NOT NULL, LocalId TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS report_run (RunId INTEGER PRIMARY KEY, SourceId INTEGER, At TEXT, Type TEXT, Title TEXT, Ms INTEGER, Subject TEXT,
  MessageId INTEGER, Failed INTEGER DEFAULT 0, Error TEXT, Said INTEGER, LinesJson TEXT, ReviewedJson TEXT, Inputs TEXT, Summary TEXT,
  StepsJson TEXT, TaskId INTEGER, RepairsJson TEXT);
-- A dashboard's last run: the rows its sources returned, which the page slices (dashboards.py). One row per dashboard.
CREATE TABLE IF NOT EXISTS dashboard_result (SourceId INTEGER PRIMARY KEY, At TEXT, DataJson TEXT);
-- Stateful report workflows: a scheduled run opens one monthly batch, then each customer
-- advances independently from amount -> Zoho draft -> Review -> sent.  The unique keys are
-- the duplicate barrier: restarting Taskuary or pressing Run again cannot create another batch
-- or a second customer row for the same month.
CREATE TABLE IF NOT EXISTS invoice_batch (BatchId INTEGER PRIMARY KEY, SourceId INTEGER NOT NULL,
  Period TEXT NOT NULL, Status TEXT DEFAULT 'needs_amounts', MessageId INTEGER,
  CreatedAt TEXT, UpdatedAt TEXT, UNIQUE(SourceId, Period));
CREATE TABLE IF NOT EXISTS invoice_item (ItemId INTEGER PRIMARY KEY, BatchId INTEGER NOT NULL,
  ConnectorId INTEGER, CustomerId TEXT NOT NULL, CustomerName TEXT, Recipient TEXT,
  Currency TEXT DEFAULT 'USD', PreviousAmount REAL, Amount REAL, Description TEXT,
  Status TEXT DEFAULT 'needs_amount', Reference TEXT, TemplateInvoiceId TEXT, InvoiceId TEXT, InvoiceNumber TEXT,
  ReviewId INTEGER, Subject TEXT, Body TEXT, Error TEXT, CreatedAt TEXT, UpdatedAt TEXT,
  UNIQUE(BatchId, CustomerId));
CREATE TABLE IF NOT EXISTS kb_doc (DocId INTEGER PRIMARY KEY, ConnectorId INTEGER, Source TEXT, Path TEXT, Name TEXT, Modified TEXT,
  Size INTEGER, Chars INTEGER, IndexedAt TEXT);
CREATE TABLE IF NOT EXISTS kb_chunk (ChunkId INTEGER PRIMARY KEY, DocId INTEGER, Seq INTEGER, Text TEXT);
-- optional semantic search (kbembed.py): one unit-length float32 vector per passage, written only while the
-- owner has it switched on. Keyed by the embedding MODEL: a changed model leaves old rows unread, then re-embedded.
CREATE TABLE IF NOT EXISTS kb_vec (ChunkId INTEGER PRIMARY KEY, Model TEXT, Dim INTEGER, Vec BLOB);
-- ...and the same embedder's vectors of the hub's own short texts (textsim.py): a task's title and summary, a memory line - keyed by what
-- the text is ("task:12") and the model, with a hash of what it said, so a changed title is embedded again and an unchanged one never
CREATE TABLE IF NOT EXISTS text_vec (Key TEXT, Model TEXT, Hash TEXT, Dim INTEGER, Vec BLOB, PRIMARY KEY (Key, Model));
CREATE TABLE IF NOT EXISTS metric (MetricId INTEGER PRIMARY KEY, Name TEXT UNIQUE, Label TEXT, Grain TEXT,
  Definition TEXT, SpecJson TEXT, Notes TEXT, Status TEXT DEFAULT 'draft', ConnectorId INTEGER,
  Skill TEXT, LastCheckAt TEXT, LastCheckPass INTEGER, LastCheckNote TEXT,
  CreatedBy TEXT, CreatedAt TEXT, UpdatedBy TEXT, UpdatedAt TEXT);
CREATE TABLE IF NOT EXISTS metric_fixture (FixtureId INTEGER PRIMARY KEY, MetricId INTEGER, Scope TEXT,
  Period TEXT, Expected REAL, Tolerance REAL, Source TEXT, LastGot REAL, LastAt TEXT, LastPass INTEGER,
  LastError TEXT, CreatedBy TEXT, CreatedAt TEXT);
-- THE HANDBOOK (handbook.py): what the agents have worked out about this company, by topic.
-- Not what they DID - that is the task's record, and it goes stale the moment the task closes.
-- This is the part that is still true next month: how the deploy works, which system owns the
-- census, that the finance close is the first Wednesday. Posts are durable and commentable;
-- the wall (boardnote) stays what it is, a checkout's chatter for the next hour.
CREATE TABLE IF NOT EXISTS lore (LoreId INTEGER PRIMARY KEY, Topic TEXT, Title TEXT, Body TEXT,
  Author TEXT, Kind TEXT DEFAULT 'howto', TaskId INTEGER, Cwd TEXT, Score INTEGER DEFAULT 0,
  Status TEXT DEFAULT 'live', Sig TEXT, CreatedAt TEXT, UpdatedAt TEXT);
CREATE INDEX IF NOT EXISTS idx_lore_topic ON lore(Topic, LoreId);
CREATE TABLE IF NOT EXISTS lore_comment (CommentId INTEGER PRIMARY KEY, LoreId INTEGER, Body TEXT,
  Author TEXT, CreatedAt TEXT);
CREATE INDEX IF NOT EXISTS idx_lore_comment ON lore_comment(LoreId, CommentId);
CREATE TABLE IF NOT EXISTS lore_vote (LoreId INTEGER, Actor TEXT, Delta INTEGER, At TEXT, PRIMARY KEY (LoreId, Actor));
-- Which brain each AI call was built on, and why (brainroute.py) - never what it was asked or what it said - and what it used
-- (aiusage.py): the model that answered, tokens in / cached / out, its time, how many calls, the agent session it was. Why is
-- kept a month, the rest 90 days (brainroute.trim).
CREATE TABLE IF NOT EXISTS brainroute (Id INTEGER PRIMARY KEY, At TEXT, Job TEXT, TaskId INTEGER, MessageId INTEGER, Pick TEXT,
  Model TEXT, Tier TEXT, Rule TEXT, Why TEXT, Difficulty TEXT, DataClass TEXT, EscalatedFrom INTEGER, Outcome TEXT, Ms INTEGER,
  Ran TEXT, TokensIn INTEGER, Cached INTEGER, TokensOut INTEGER, Calls INTEGER, Sid TEXT, Caller TEXT, FellFrom TEXT, Cost REAL);
CREATE INDEX IF NOT EXISTS idx_brainroute_task ON brainroute(TaskId, Id);
-- How hard a task's work is, whether its reader could tell, and what kind of data it carries - triage's judgements, apart from the
-- priority, kept per task (brainroute.judged). `By` is 'owner' once they correct one: their word stands until they change it again.
CREATE TABLE IF NOT EXISTS task_judged (TaskId INTEGER PRIMARY KEY, Difficulty TEXT, Sure INTEGER, DataClass TEXT, By TEXT, At TEXT);
-- THE DRAFT AS A TURN LEFT IT (the owner, 2026-11-05: "keep the original draft in that turn, and then in next turn show the next draft"): the
-- agent rewrites one review in place, so a turn that kept only the review's id drew the LATER words. One row per turn that wrote or rewrote
-- it (CommentId: that turn's answer), apart from the summary - the words to a sender never sit in the summary (2026-11-04)
CREATE TABLE IF NOT EXISTS draft_snapshot (Id INTEGER PRIMARY KEY, TaskId INTEGER, ReviewId INTEGER, CommentId INTEGER, Text TEXT,
  ToName TEXT, Subject TEXT, CreatedAt TEXT);
CREATE INDEX IF NOT EXISTS idx_draft_snapshot ON draft_snapshot(TaskId, CommentId);
"""
# the knowledge base's search index (knowledge.py). A VIRTUAL table, kept out of SCHEMA: a Python
# built without FTS5 must still open the store - search then falls back to LIKE over kb_chunk.
KB_FTS = 'CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(Text, ChunkId UNINDEXED, tokenize="porter unicode61")'
# Every message ever received, searchable by its words (the assistant's timeline.search). External
# content: the index holds no second copy of the mail, and the triggers keep it in step for every
# process that writes, since they live in the database rather than in this file. Only the fields
# a person searches by - never Status, which changes on every pass and would re-index for nothing.
MSG_FTS = ('CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(Subject, FromName, FromEmail, BodyText, '
           "content='message', content_rowid='MessageId', tokenize=\"porter unicode61\")")
_MSG_COLS = 'Subject, FromName, FromEmail, BodyText'
_MSG_NEW = 'new.MessageId, new.Subject, new.FromName, new.FromEmail, new.BodyText'
_MSG_OLD = "'delete', old.MessageId, old.Subject, old.FromName, old.FromEmail, old.BodyText"
MSG_FTS_TRIGGERS = (
    f'CREATE TRIGGER IF NOT EXISTS message_fts_ai AFTER INSERT ON message BEGIN '
    f'INSERT INTO message_fts(rowid, {_MSG_COLS}) VALUES ({_MSG_NEW}); END',
    f'CREATE TRIGGER IF NOT EXISTS message_fts_ad AFTER DELETE ON message BEGIN '
    f'INSERT INTO message_fts(message_fts, rowid, {_MSG_COLS}) VALUES ({_MSG_OLD}); END',
    f'CREATE TRIGGER IF NOT EXISTS message_fts_au AFTER UPDATE OF {_MSG_COLS} ON message BEGIN '
    f'INSERT INTO message_fts(message_fts, rowid, {_MSG_COLS}) VALUES ({_MSG_OLD}); '
    f'INSERT INTO message_fts(rowid, {_MSG_COLS}) VALUES ({_MSG_NEW}); END')

# A mail's own ids, kept in its MailMetaJson so a later reply finds the thread through them (store.conversation_of_mail):
# its Message-ID (`mid`) and Gmail's thread id (`gm_thread`). One spelling for the index and the query, or SQLite never
# pairs the two; json_valid first, since one malformed row would otherwise stop the index being built at all.
def meta_expr(key: str) -> str: return f"(CASE WHEN json_valid(MailMetaJson) THEN json_extract(MailMetaJson, '$.{key}') END)"

# CREATE TABLE IF NOT EXISTS is a no-op on an existing db; these are not. IF NOT EXISTS
# so a second open (desktop + web, or a restart) does not raise. Named so EXPLAIN QUERY
# PLAN tests can see them, and so a DROP INDEX in a test is not a mystery.
# a route row a brain built and never called left (brainroute.Lazy): 'ok', no time, no tokens - older than the sweep (?)
UNCALLED_ROUTES = "Ms IS NULL AND TokensIn IS NULL AND Outcome='ok' AND At<?"

INDEXES = (
    'CREATE INDEX IF NOT EXISTS idx_message_external ON message(ExternalId)',
    'CREATE INDEX IF NOT EXISTS idx_brainroute_at ON brainroute(At)',          # the AI-use dashboard reads 90 days by time
    'CREATE INDEX IF NOT EXISTS idx_message_conversation ON message(ConversationId, SentAt)',
    # ...and by arrival: store.talked_with walks a chat from each of their lines to the owner's next one
    'CREATE INDEX IF NOT EXISTS idx_message_conversation_id ON message(ConversationId, MessageId)',
    'CREATE INDEX IF NOT EXISTS idx_message_task ON message(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_message_status ON message(Status)',
    'CREATE INDEX IF NOT EXISTS idx_message_sent ON message(SentAt, MessageId)',
    'CREATE INDEX IF NOT EXISTS idx_message_created ON message(CreatedAt)',
    'CREATE INDEX IF NOT EXISTS idx_message_from ON message(FromEmail)',
    f"CREATE INDEX IF NOT EXISTS idx_message_mail_id ON message({meta_expr('mid')})",
    f"CREATE INDEX IF NOT EXISTS idx_message_gm_thread ON message({meta_expr('gm_thread')})",
    'CREATE INDEX IF NOT EXISTS idx_project_link_identity ON project_link(Kind, Value, Confidence)',
    'CREATE INDEX IF NOT EXISTS idx_project_link_project ON project_link(ProjectId, Kind)',
    'CREATE INDEX IF NOT EXISTS idx_project_evidence_task ON project_evidence(TaskId, LinkId)',
    'CREATE INDEX IF NOT EXISTS idx_routing_fact_lookup ON routing_fact(Field, Signal, SignalKey)',
    'CREATE INDEX IF NOT EXISTS idx_routing_evidence_task ON routing_evidence(TaskId, FactId)',
    'CREATE INDEX IF NOT EXISTS idx_route_message ON route(MessageId, RouteId)',
    'CREATE INDEX IF NOT EXISTS idx_route_task ON route(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_review_message ON review(MessageId, ReviewId)',
    # Board / funnel / assistant filter on live Status (+ today's done via ClosedAt).
    # Without this, active_only is a full task-table scan (301 ms COUNT at 1M rows).
    'CREATE INDEX IF NOT EXISTS idx_task_status ON task(Status, ClosedAt, TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_review_task ON review(TaskId, Status)',
    'CREATE INDEX IF NOT EXISTS idx_run_task ON run(TaskId, Status)',
    'CREATE INDEX IF NOT EXISTS idx_attachment_message ON attachment(MessageId)',
    'CREATE INDEX IF NOT EXISTS idx_task_artifact_task ON task_artifact(TaskId, ArtifactId)',
    'CREATE INDEX IF NOT EXISTS idx_comment_task ON comment(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit(EntityType, EntityId)',
    'CREATE INDEX IF NOT EXISTS idx_dispatchq_task ON dispatchq(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_waitroom_task ON waitroom(TaskId, DeliveredAt)',
    'CREATE INDEX IF NOT EXISTS idx_idea_status ON idea(Status, MessageId)',
    'CREATE UNIQUE INDEX IF NOT EXISTS idx_processing_primary ON processing_member(ItemId) WHERE RetiredAt IS NULL AND Role="primary"',
    'CREATE UNIQUE INDEX IF NOT EXISTS idx_processing_entity ON processing_member(EntityKind, LocalId) WHERE RetiredAt IS NULL',
    'CREATE INDEX IF NOT EXISTS idx_processing_member_item ON processing_member(ItemId, RetiredAt)',
    'CREATE UNIQUE INDEX IF NOT EXISTS idx_processing_alias_active ON processing_alias(Namespace, Scope, Value) WHERE RetiredAt IS NULL',
    'CREATE INDEX IF NOT EXISTS idx_processing_alias_entity ON processing_alias(EntityKind, LocalId, RetiredAt)',
    'CREATE UNIQUE INDEX IF NOT EXISTS idx_processing_relation_active ON processing_relation(FromEntityKind, FromLocalId, ToEntityKind, ToLocalId, Kind) WHERE RetiredAt IS NULL',
    'CREATE INDEX IF NOT EXISTS idx_processing_redirect ON processing_item(RedirectItemId)',
    'CREATE INDEX IF NOT EXISTS idx_processing_evidence_item ON processing_legacy_evidence(ItemId, EvidenceId)',
    'CREATE INDEX IF NOT EXISTS idx_processing_evidence_entity ON processing_legacy_evidence(EntityKind, LocalId, EvidenceId)',
    'CREATE INDEX IF NOT EXISTS idx_processing_context_item ON processing_context_snapshot(ItemId, MigrationVersion)',
    'CREATE INDEX IF NOT EXISTS idx_connector_type ON connector(Type, ConnectorId)',
    'CREATE INDEX IF NOT EXISTS idx_invoice_batch_source ON invoice_batch(SourceId, Period)',
    'CREATE INDEX IF NOT EXISTS idx_invoice_item_batch ON invoice_item(BatchId, Status)',
    'CREATE INDEX IF NOT EXISTS idx_invoice_item_review ON invoice_item(ReviewId)',
)

# These are the persisted inputs to canonical identity or its complete presentation
# projection.  Triggers, rather than Python write hooks, also cover migrations, test
# fixtures and other direct SQL writers.  Reconciliation writes only processing_*
# tables, so it never dirties itself.
# EVERY TABLE WHOSE WRITES MUST BECOME VISIBLE HERE - which is NOT the same as "what the census
# reads". reconcile_membership reads six of these; route, funnel_state, comment, task_artifact and
# transcript it never opens, and trimming them looks like free work (2026-09-15: a pass walks ~25k
# rows under BEGIN IMMEDIATE while wait_settled holds readers).
#
# It is not free, and this is the trap: the display cache is keyed on `self._writes`, a PER-CONNECTION
# counter, so a write from ANOTHER process - an agent's comment, a CLI's route, a peer's read receipt -
# never moves it. These triggers are the only thing that turns an external write into a local
# generation change (see the cache-key comment in processing_inventory_snapshot), and
# _processing_finish_funnel_write compensates for this connection's own funnel_state write precisely
# because the trigger cannot tell the two apart. Drop one and this process serves a stale view after
# another one writes. The cost to attack is the SIZE OF THE PASS, not the length of this list.
PROCESSING_DIRTY_TABLES = (
    'task', 'message', 'review', 'idea', 'attachment', 'run', 'route',
    'funnel_state', 'comment', 'task_artifact', 'transcript',
    'batch_item',                # a batch row's progress line (batch.rail) moves as the agent reports each item
)
# WHAT A SENDER'S TRUST IS READ FROM (senders.known, origin.of_message, idea_rests_on): (table, the columns whose update moves it - '' every
# column, 'blind' every setting a pile never reads stays out). A write to any of them moves change_gen 'trust', and every task's stored hold
# is judged again on its next read (origin.hold). A table read by the trust rules and missing here serves a stale hold.
TRUST_INPUTS = (
    ('message', ''), ('review', ''), ('sender_trust', ''), ('idea', ''), ('memory_line', ''), ('doc', ''), ('agent', ''),
    ('project_link', ''), ('setting', 'blind'),
    ('source', 'Channel, Address, Owner, ConnectorId, Active, ConfigJson'), ('connector', 'Type, ConfigJson, Active, Roles, Scope'),
    ('task', 'OriginBase, TrustedThrough, Source, SourceRef, Status, Kind'),
)
PROCESSING_DIRTY_SETTINGS = (
    'feed_days', 'funnel_hours', 'funnel_mutes', 'owner_email', 'team_domains', 'processing_membership_rules',
    'reply_channels',            # read into a reply card's display backing (funnel_presentation): a change must move the stamp
)
# Settings no pile reads (funnel.pile and everything it builds from), so writing one leaves the cached pile warm. A
# prefix covers the per-dock-task keys. Only concierge, the server's own routes and the phone doorway read these - a key
# goes here only once nothing on the pile's road reads it: a missed invalidation shows a stale pile.
PILE_BLIND_SETTINGS = (
    'assistant_current:',        # concierge.CURRENT_KEY - the item on the table, written as each press puts it there
    'concierge_cli_sid:',        # concierge.SID_KEY - the CLI conversation, resumed turn to turn
    'assistant_last_undo',       # concierge.LAST_UNDO - what the phone's Undo pill runs
    'rail_walk',                 # railwalk.KEY - where the desk's walk and each phone chat's own stand, written by every walk move
    'assistant_active_at',       # welcome.ACTIVE_KEY - the owner's last press, written after every one (owner_presence)
    'landing:',                  # landing.KEY - a coding agent's edits and commits, written by its hook on every Edit (the task page's landing card
                                 # reads it; no rail card does) - each one emptied the pile while an agent worked (2026-11-09)
)

# Settings whose key changed: (old, new), moved once as the store opens (Store.__init__) so an install keeps its value.
# The coding agent's switches were named for one special profile, and no profile is special (2026-10-15).
SETTING_RENAMES = (('coder_auto_enabled', 'coding_auto_enabled'), ('coder_context_file', 'agent_context_file'))

# Out of the box Taskuary WORKS the mail: a job goes to the coding agent, a question gets a
# draft. Both stop short of anything leaving the building - a draft waits for you to send it,
# and a session is one you watch - so ON is a safe default and OFF was just a slower start.
DEFAULT_SETTINGS = {'attach_threshold': '0.42',
                    'feed_days': '14', 'intent_classify_enabled': '1', 'coding_auto_enabled': '1',
                    'developer_mode': '0',          # coding agents only for a developer who turns it on (agents.developer_mode, devmode.py)
                    'chat_keep_days': '15',        # archived assistant chats expire after this many days (retention.py, PW-158)
                    'fyi_batch': '4',             # how many fyi the assistant reads out together (funnel.fyi_batch_size)
                    'general_auto_enabled': '1',    # general tasks open their assistant session by themselves (PW-069)
                    'code_folders': '',             # where a coding agent may look for its checkout; blank = the usual homes (repochoice.folders)
                    # how much of an agent's work its task chat shows by default (chatDetail.js): every tool call for coding, the summary for the rest
                    'chat_detail_coding': 'everything', 'chat_detail_other': 'summary',
                    'concierge_fast': 'auto',   # the Assistant's CLI in fast mode: codex yes, claude no (llm.fast_on)
                    'acp_cli': '1',                 # general agents' CLI runs over ACP, argv as the fallback (agents.acp_on, gate)
                    'general_agent_hands': 'cli',   # ...with the CLI agent's own permissions unless the owner narrows it (general.full_hands)
                    # who counts as ours on a GitHub repository (batch.outside_row), and what an outsider's PR gets (cloudfix.py)
                    'repo_trust_private': 'ours', 'repo_trust_public': 'writers', 'outside_prs': 'review',
                    # a task bound to a chat with teammates runs as a stranger's unless the owner chose full power (origin.teammate_bound)
                    'teammate_chat_power': 'safe',
                    # who may start a worker UNATTENDED (senders.known, PW-079..081): the owner's own domains, verified
                    # Sent Items evidence that the receiving mailbox wrote to the exact address, chat people the owner talks
                    # with, members of a tracker's project (senders._item_known). Prior incoming mail is never a rule here.
                    'trust_own_domain': '1', 'trust_sent_history': '1', 'trust_non_email': '1', 'trust_trackers': '1',
                    'auto_sessions': '4',           # unattended agent sessions at once; the rest queue
                    'auto_sessions_light': '5',     # subagents that count as one of those (ingest.agent_load)
                    'triage_lanes': '4',            # conversations triage judges at once; one conversation's mail stays in order (ingest.drain)
                    'triage_ai': '',      # '' = first active AI connector | connector:<id> | cli:<agent>
                    'startup_sync_days': '3',       # backfill window when the app starts: catch what arrived while it was shut
                    # minutes between background polls while the app is OPEN. The Timeline said
                    # "auto-syncs every 10 min" for a long time while the only clock was a
                    # setInterval inside its own tab - see server.poll_forever. 0 = off.
                    # FOUR, because a provider forgets a cached prompt after ~5 quiet minutes (Anthropic 5; OpenAI 5-10; a Claude
                    # CLI 5): at 10 the first mail of every poll paid for the whole triage guide and the memory again, on either
                    # road. An empty poll asks no model, so the price of 4 is the mailbox being read 2.5x as often.
                    'poll_minutes': '4',
                    'vision_enabled': '1',          # send attached images to the AI, when the model can see
                    'report_images_enabled': '1',   # reports hand back a chart, and draw it in the body
                    # the ONE copy of your name. The docs say {{owner}} / {{owner_first}} /
                    # {{owner_email}} and are filled in when an AI reads them - see store.doc().
                    'owner_name': '', 'owner_email': '',
                    # the agent raised its hand (a session parked at its prompt, or asked a question):
                    # a sound in the app and the browser's own desktop notification - each its own switch
                    'hand_sound': 'chime', 'hand_desktop': '1',
                    'calendar_enabled': '1',      # a reply about time reads the owner's calendar first
                    # optional semantic search over the knowledge base (kbembed.py). OFF: nothing is embedded or imported.
                    'kb_semantic': '0', 'kb_embed_url': 'http://127.0.0.1:11434', 'kb_embed_model': 'nomic-embed-text',
                    'kb_semantic_min': '0.5',
                    # the assistant's POST on the Timeline (assistant.py): what it looks for, the silence and
                    # quiet that count as news, how much it says. Its clock and its instruction live on the
                    # Reports tab (the seeded 'Assistant' report).
                    'assistant_followup_hours': '24',
                    'assistant_cold_days': '3', 'assistant_producers': 'followup,promise,prep,cold,idea',
                    'assistant_max_lines': '5',
                    # the conversational assistant has its own saved brain. API connectors are
                    # the fast/native path; a CLI remains available for tool-heavy work.
                    'assistant_ai': '', 'assistant_model': '',
                    # which AI does each job (brainroute): auto = triage's judgement picks the model (the owner, 2026-11-06), fixed =
                    # the cards exactly as before; rules '' = the shipped ones
                    'ai_route_mode': 'auto', 'ai_route_rules': '', 'ai_route_strong_cap': '', 'auto_ai_daily_calls': '1500',
                    # ...and an AI per level for the agents' work ({quick|normal|hard: {pick, model}}) - blank = each card's own AI
                    'ai_route_brain_by_level': '',
                    # the agent's context file (context.py): history, past work and the brief, written to
                    # ~/.taskuary/context/TQ-xxxx.md and pointed at from the seed - not crammed into it
                    'agent_context_file': '1',
                    'agent_hooks': '1',           # Claude Code tells the Board what it is doing, through its own hooks (hooks.py)
                    'timeline_fade': 'normal',    # older Timeline rows rest quieter - off | gentle | normal | sharp
                    'waitroom_drip': '1',         # queued notes land one per stop (a funnel of prompts), not all at once
                    # LEGACY: the profile whose CLI worked tasks before brains named tools. Seeded blank - the coding
                    # profile is found by its kind (agents.coding_role), the CLI by default_brain; an old value is
                    # read once by agents.migrate_brain_settings and then cleared
                    'default_agent': '',
                    # WHICH CLI runs a worker session - coding and general alike. Blank derives
                    # it from default_agent's profile, so an upgrade changes nothing until the
                    # owner picks one.
                    'default_brain': '',
                    # ordered CSV of alternate CLI profiles; * means every other configured
                    # agent in roster order. A quota/login outage should move the same task to
                    # another CLI instead of leaving a dead terminal as its only outcome.
                    'backup_agents': '*',
                    # ...and the same for BRAINS, which is what a session's chain actually walks
                    # now. `backup_agents` named profiles and cannot be reused as brain keys, so
                    # an existing install starts with no backups until the owner names them.
                    'backup_brains': '*',
                    # ordered alternate brains for triage, drafts, summaries and assistant chat.
                    # Blank is deliberately opt-in: a cloud-to-CLI fallback may change cost and
                    # privacy, so the owner names the alternatives explicitly in Settings.
                    'triage_backup_ai': '',
                    # may agents open GitHub issues/tracker items for the work itself? Off by
                    # default: Taskuary is the tracker, and one issue per task is noise.
                    'agent_issues_enabled': '0',
                    # may agents push/deploy on their own? Off: commit locally, the owner pushes.
                    'agent_push_enabled': '0',
                    # when an inbound answer ATTACHES to a task whose agent session is live:
                    # ask = a one-click offer in the panel; auto = typed straight in; off = neither
                    'answer_to_agent': 'ask',
                    # replies in the notify chat decide pinged reviews (approve/reject/your text)
                    # the owner's messages in one private WhatsApp notify chat open the same
                    # durable guide conversation as the floating desktop assistant
                    'phone_assistant': '0',
                    # the phone hears only what the owner started there; ON lets an URGENT item through unasked (remote_assistant.urgent_rings)
                    'phone_urgent_unasked': '0',
                    # which channels Taskuary drafts and sends replies on (csv). github also
                    # needs its card's 'Reply to issue/PR authors'; the read-only trackers
                    # can never carry one - see outbound.can_reply
                    'reply_channels': 'email,teams,slack,telegram,whatsapp,imessage,discord,github',
                    # the owner's email signature, exactly as it goes under every email (responder.signed); read off their
                    # sent mail at setup or by Settings' button, checked by them - blank: STYLE.md's sign-off line, else the owner's name
                    'email_signature': '',
                    # that signature under every email Taskuary prepares - drafts, the owner's own typed replies, forwards (signatures.py)
                    'sign_replies': '1',
                    # the owner's own footer under every post an agent sets up, exactly as saved (signatures.post_signed) - blank: none
                    'post_signature': '',
                    # watch the CI of a task's pull request and hand red builds back to the
                    # agent that wrote the code: off | watch (status only) | feedback
                    'ci_watch': 'off',
                    # how finished work leaves the machine: 'pr' opens a DRAFT pull request,
                    # 'direct' pushes the existing commits straight onto the default branch
                    # (your own repo, no review ceremony). Either way 'Agents may push' gates it.
                    'git_flow': 'pr',
                    # an agent may PROPOSE high-impact actions (open a PR, comment publicly,
                    # close an issue, run a tool); each lands on the task for approval
                    'proposals_enabled': '1',
                    # triage matches mail to the skills, and a recurring job is proposed as one (skills.menu / draft)
                    'playbooks_enabled': '1',
                    # Share -> Shared link: a read-only page for one result on this network (sharing.py). Off: no link exists
                    'share_links_lan': '0',
                    # ...served on a port of its own (sharing.share_app), never Taskuary's: blank = sharing.SHARE_PORT
                    'share_port': '7797',
                    # the zone timestamps are stamped in (blank = this machine's local). Setting
                    # it makes every displayed time wear its label (2:44 PM EDT) and keeps a
                    # browser in another zone reading the stamps correctly.
                    'timezone': ''}

# BLANK MEANS THE DEFAULT, in one place (the 2026-10-19 UI walk): the page says "blank = default" for a number knob, and each
# reader picked its own fallback for '' - `int(get_setting('poll_minutes') or 0)` read a cleared box as 0 and turned background
# sync off. A number knob stored blank reads back as what it ships with, through get_setting and get_settings alike.
def _blank_defaults():
    from . import settings_schema
    return {k: DEFAULT_SETTINGS[k] for k, m in settings_schema.knobs().items() if m.get('type') == 'number' and k in DEFAULT_SETTINGS}
BLANK_DEFAULTS = _blank_defaults()


# What a connection IS to the hub, independent of what it can technically do:
#   trigger - polled for inbound items; they land on the Timeline and go through triage,
#             which can open tasks and draft replies
#   feed    - polled and SHOWN on the Timeline, but never becomes work: no triage, no task,
#             no AI call. "I want to see new GitHub issues, not be assigned them."
#   report  - selectable as a scheduled report source (Reports tab)
#   tool    - the agents may read from / write to it (listed for them in SOUL.md)
#   notify  - RETIRED 2026-10-02 (pushes into a chat; the phone chat now speaks only when spoken to) - still parsed
#             so a card saved with it keeps loading, and nothing reads it
# Defaults match how each system is usually used; every one is owner-configurable.
DEFAULT_ROLES = {'outlook': 'trigger,tool', 'teams': 'trigger,tool', 'slack': 'trigger,tool',
                 'telegram': 'trigger,tool', 'whatsapp': 'trigger,tool', 'imessage': 'trigger,tool',
                 'gmail': 'trigger,tool', 'imap': 'trigger,tool',
                 'github': 'tool', 'mssql': 'report,tool', 'winrm': 'report,tool',
                 'database': 'report,tool',
                 'prometheus': 'report,tool', 'datadog': 'report,tool',
                 # the books are read-only here: report and tool, never trigger. Intacct does
                 # not push, and an agent that can WRITE a journal entry is a different product
                 'intacct': 'report,tool',
                 # QuickBooks is the first Corporate system that can WRITE (a bill, an expense) -
                 # still report and tool, never trigger; the writes are gated by scope, not by role
                 'quickbooks': 'report,tool',
                 'zoho_invoice': 'report,tool',
                 'amazon_sp': 'report,tool',     # a seller's Amazon reports: data only, never work on the rail
                 'stripe': 'report,tool',        # payments and payouts: data only, never work on the rail (owner, 2026-11-01)
                 'teller': 'report,tool',          # the bank feed: transactions as a report (and "can become work"), balances as a tool
                 'simplefin': 'report,tool',       # the same feed, from the bridge anyone can sign up to
                 # market data (markets.py): four keyless cards, each a report source and an agent tool
                 'coingecko': 'report,tool', 'frankfurter': 'report,tool',
                 'alchemy': 'report,tool',
                 'yahoo': 'report,tool', 'sec_edgar': 'report,tool',
                 # twelvedata/alphavantage need a key; fred does not (fredgraph.csv is keyless)
                 'twelvedata': 'report,tool', 'alphavantage': 'report,tool', 'fred': 'report,tool',
                 # five more (2026-09-08): finnhub/polygon/tiingo/fmp key like twelvedata; alpaca
                 # needs two credentials (key_id, secret_key) and ships market DATA only, no orders
                 'finnhub': 'report,tool', 'polygon': 'report,tool', 'tiingo': 'report,tool',
                 'fmp': 'report,tool', 'alpaca': 'report,tool', 'marketstack': 'report,tool', 'eodhd': 'report,tool', 'dynamodb': 'report,tool', 'obsidian': 'report,tool',
                 **{t: 'report,tool' for t in _read_types()},      # apireads.json: reads, as reports and agent tools
                 'screen': 'report,tool',       # the strategy screen: conditions in config, matches out (markets.py)
                 # research reads the public web - a report source, and a tool an agent may use
                 'exa': 'report,tool', 'tavily': 'report,tool',
                 'firecrawl': 'report,tool', 'reader': 'report,tool',
                 # social: a public timeline is not an inbox, so these are report sources and
                 # tools - never triggers. The only verb that leaves the house is a post.
                 'bluesky': 'report,tool', 'mastodon': 'report,tool',
                 'brave_search': 'report,tool', 'serpapi': 'report,tool', 'serper': 'report,tool',
                 'scrapingbee': 'report,tool', 'apify': 'report,tool',
                 # aws/azure: the per-OBJECT picker carries the intent (report by default,
                 # which polls nothing) - the card itself is just a connection and a tool
                 'aws': 'report,tool', 'azure': 'report,tool',
                 'sharepoint': 'report,tool', 'google_sheets': 'report,tool',
                 # the first two cards that can WRITE a file (files.py): report and tool, never
                 # trigger - neither pushes, and a folder is polled by a report when that is wanted.
                 # The writes are gated by scope like QuickBooks', not by role.
                 'smb_file': 'report,tool', 'sftp': 'report,tool',
                 'knowledge': 'report,tool',       # indexed documents: a kb_search report, and a tool for agents and the drafter
                 # the handbook the agents write themselves (handbook.py). tool, because the only
                 # things that read and write it are agents; no trigger, because it never arrives.
                 'handbook': 'report,tool',
                 'jira': 'trigger', 'asana': 'trigger', 'monday': 'trigger',
                 'clickup': 'trigger', 'todoist': 'trigger',
                 'gitlab': 'trigger', 'azdo': 'trigger', 'linear': 'trigger', 'trello': 'trigger',
                 # notion edits are information, not assignments; discord is a chat channel
                 'notion': 'feed', 'discord': 'trigger,tool',
                 # the four other chat servers, same as discord: a room is a trigger, and the
                 # card is a tool because an agent may post back into it
                 'mattermost': 'trigger,tool', 'rocketchat': 'trigger,tool',
                 'matrix': 'trigger,tool', 'google_chat': 'trigger,tool',
                 'sentry': 'trigger', 'pagerduty': 'trigger',
                 # helpdesks and the newer trackers (inboxes.py): what is assigned to you is work
                 **dict.fromkeys(INBOXES, 'trigger'),
                 # ...and the ones that are both (HubSpot, Salesforce, DocuSign, Webex, WooCommerce, BigCommerce...): work comes in, and agents read the same API
                 **{t: 'trigger,report,tool' for t in INBOXES if t in _read_types()},
                 # ...and one whose card posts (a catalogue act on a tool - Reddit's): an agent proposes the post through it
                 **{t: 'trigger,tool' for t in INBOXES if t not in _read_types() and t in _posts()},
                 # speech to text: no role - the funnel and the prompt box ask the first active one
                 'gemini_stt': '', 'groq_stt': '', 'openai_stt': '', 'deepgram': '', 'elevenlabs_stt': '', 'stt_server': '', 'local_whisper': '',
                 'assemblyai': '', 'speechmatics': '', 'gladia': '', 'azure_speech': '', 'amazon_transcribe': '',
                 # image models (images.py): a tool, never a poll - a picture is drawn when
                 # something asks for one, and lands as an attachment where the owner can see it
                 'openai_image': 'tool', 'azure_openai_image': 'tool', 'xai_image': 'tool', 'image_server': 'tool',
                 'gemini_image': 'tool', 'stability_image': 'tool', 'openrouter_image': 'tool', 'replicate_image': 'tool', 'runway_image': 'tool',
                 'kling': 'tool'}     # video from a sentence (videotools.py): a tool, like the image cards
ROLES = ('trigger', 'feed', 'report', 'tool', 'notify')      # 'notify': retired, kept so old rows parse

def roles_of(c) -> set: return {r for r in (c.get('Roles') or '').split(',') if r}




def _snapcopy(o):
    """A private deep copy of an inventory snapshot, for the copy that guards the display cache.

    A snapshot holds nothing but what SQLite and json give back - dict, list, str, int, float,
    bool, None - so the generic machinery in copy.deepcopy (memo table, per-type dispatch,
    __reduce__ probing) is all overhead: 396ms against 153ms on a real 78MB store, and that ran
    on every cache HIT before the pile could answer. Same result, same isolation.
    """
    t = type(o)
    if t is dict: return {k: _snapcopy(v) for k, v in o.items()}
    if t is list: return [_snapcopy(v) for v in o]
    # anything else a snapshot can hold is immutable; a type that is not falls back to the
    # general copy rather than being aliased into the cache
    if t in (str, int, float, bool, type(None)): return o
    return copy.deepcopy(o)


def _units_of(picture):
    """A picture's read-bearing units (processing_reads.units), worked out once per picture: 2,000 fingerprints on a long chat."""
    if '_units' not in picture:
        from . import processing_reads
        picture['_units'] = processing_reads.units(picture['view'])
    return picture['_units']


_OPENED: dict = {}
def _open_sealed(v):
    "A sealed config value opened, once a process: a page's dozen card reads would each ask the OS again."
    if not vault.sealed(v): return v
    if v not in _OPENED: _OPENED[v] = vault.unseal(v)
    return _OPENED[v]
def _sealed_in(cfg) -> set:
    "Every sealed value in a config, at any depth."
    out = set(); map_secrets(cfg, lambda v: out.add(v) if vault.sealed(v) else v, within=True); return out


class SQLiteStore:
    """The local-first binding. One connection, a lock (sqlite + threads), rows as dicts."""

    def __init__(self, path):
        # timeout= is sqlite's lock wait in seconds; WAL below is what actually lets a
        # Timeline read proceed while a poll is writing. :memory: cannot WAL (it has
        # nowhere to put the -wal file), so tests keep the default journal.
        self.cx = sqlite3.connect(path, check_same_thread=False, timeout=5.0, factory=_Writer)
        try: self.cx._owner = weakref.ref(self)
        except AttributeError: pass               # ...a plain connection a caller opened in its place (a test's own connect) closes as plain
        self.cx.row_factory = sqlite3.Row
        # SQLite's own LOWER()/LIKE fold ASCII only, so "muller" finds "MULLER" and "muller" does
        # not find "MULLER" once it is spelt MULLER with an umlaut. Search folds both the column
        # and the pattern through Python instead, which knows the rest of the alphabet. It is a
        # per-row callback: fine over a mailbox this size, and the thing to revisit - a folded
        # column, indexed - if the archive ever gets big enough to feel it.
        self.cx.create_function('tq_fold', 1, _fold, deterministic=True)
        # A second, read-only connection for the rail's "did anything change?" look (processing_rail):
        # asked on the shared writer connection it would queue behind a running sync, and a cache HIT
        # is the one read that must never wait. A memory database has nowhere to open a second one.
        self._rail_cx = None
        if path != ':memory:':
            self._rail_cx = sqlite3.connect(path, check_same_thread=False, timeout=5.0)
            self._rail_cx.row_factory = sqlite3.Row
        # Its own lock, not the writer's: threads share sqlite3's cached statement for the same SQL, so two
        # concurrent reads reset each other's and one gets no row back (a 500 on the walk's table chip, 2026-10-21).
        self._rail_lock = threading.Lock()
        # Long reads - the rail's cold build, a pile's card stamps - take a reader connection from this pool (_snapshot_read)
        # instead of the writer's lock: holding that for a 71 s first build after a restart queued opening a task, the agents
        # and the problems list behind it for up to 28 s (2026-10-21). One rail build at a time (_rail_build_lock).
        self._path, self._readers, self._readers_lock, self._closed = path, [], threading.Lock(), False
        self._rail_build_lock = threading.Lock()
        self.lock = _TimedLock()
        self.idlock = threading.Lock()     # create_task: allocate-and-insert as one step (self.lock is per statement)
        if path != ':memory:':
            self.cx.execute('PRAGMA journal_mode=WAL')
            self.cx.execute('PRAGMA synchronous=NORMAL')
        # milliseconds. connect(timeout=) is the same wait in seconds; both have to be
        # set because a second connection (desktop + web, or a stuck poll) otherwise
        # fails instantly with "database is locked" instead of waiting its turn.
        self.cx.execute('PRAGMA busy_timeout=5000')
        self._poke_held = None       # one_poke(): a batch's wake-ups, held and sent once
        self._snap_hold = 0
        self._snap_cache, self._snap_gen = None, 0     # the gen counts writes, so a picture read across one is not cached
        self._processing_display_cache = {}
        self._states_cache = None     # funnel_states(): (DirtyGeneration, newest dirty row) -> the rows read at that mark
        self._conn_cache = None       # list_connectors(): (the connectors' change_gen, the rows read at it)
        self._processing_ignored_writes = 0
        self._writes = 0
        with self.lock:
            self.cx.executescript(SCHEMA)
            # columns added after a release: CREATE TABLE IF NOT EXISTS never reaches an
            # existing db, so widen it here (cheap, idempotent)
            # Work can now leave as well as arrive, so a row has to say which way it went. A
            # timeline that shows only inbound is a half-picture the moment a report is sent
            # to somebody - and 'sent to Dana' looks exactly like 'received from Dana' without
            # it. Default 'in': every row that already exists arrived.
            mcols = {r[1] for r in self.cx.execute('PRAGMA table_info(message)')}
            if 'Direction' not in mcols:
                self.cx.execute("ALTER TABLE message ADD COLUMN Direction TEXT DEFAULT 'in'")
            # WHO the mail was addressed to. triage.addressed_to_you weighed the To/Cc lines at
            # ingest and then the lines were thrown away, so no verdict could ever be replayed
            # against them - "was this cc'd mail really mine?" had no evidence left (evalset.py)
            if 'RecipientsJson' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN RecipientsJson TEXT')
            # Mailbox facts needed by the evening brief: which folder Graph returned the row
            # from, Focused/Other, its follow-up flag, and whether Graph identified an invite.
            # One JSON column keeps non-mail channels out of an Outlook-shaped schema.
            if 'MailMetaJson' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN MailMetaJson TEXT')
            # WHERE THE SENDER'S OWN WORDS END, as the mailbox itself marks them (Graph's uniqueBody).
            # Everything else has to find the chain in text, and on a forwarded mail that is a guess -
            # an 8,400-character chain read as the ask (TQ-0665). Null for every channel that offers
            # no such thing and for every row stored before this: triage.split_own still finds the cut.
            if 'OwnText' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN OwnText TEXT')
            # Keep the evidence when triage answers but breaks its JSON contract. Without the
            # raw answer another machine could only report "could not read it", not why.
            # A page a Claude session published (claude_artifacts): its claude.ai link, the tool's own id for
            # it - so a republish updates its row - and which version the local copy is
            acols = {r[1] for r in self.cx.execute('PRAGMA table_info(task_artifact)')}
            for c in ('Url', 'ExtId', 'Version'):
                if c not in acols: self.cx.execute(f'ALTER TABLE task_artifact ADD COLUMN {c} TEXT')
            # the head a batch's agent reviewed: a merge is pinned to it (batch.act), so a push after the review is refused
            bcols = {r[1] for r in self.cx.execute('PRAGMA table_info(batch_item)')}
            # ...and a fix made in GitHub's cloud (cloudfix.py): running | done | failed | nothing, when it was sent, its pull request
            # ...and a stranger's change cleared to run HERE (batch.screen): the head it was cleared at, and what the screen said
            # ...and Warn: its text read as an attempt to instruct an AI (batch.injections)
            for c in ('Sha', 'Propose', 'Fix', 'FixAt', 'FixLink', 'Trusted', 'Screen', 'Warn'):
                if c not in bcols: self.cx.execute(f'ALTER TABLE batch_item ADD COLUMN {c} TEXT')
            # a rule meant for one mailbox names it (policy.matches): blank, as every rule before it, is every mailbox
            if 'Mailbox' not in {r[1] for r in self.cx.execute('PRAGMA table_info(policy)')}:
                self.cx.execute('ALTER TABLE policy ADD COLUMN Mailbox TEXT')
            # ...and what a kept conversation was told (general.freeze), beside the id it is picked back up by
            if 'Frozen' not in {r[1] for r in self.cx.execute('PRAGMA table_info(session_resume)')}:
                self.cx.execute('ALTER TABLE session_resume ADD COLUMN Frozen TEXT')
            routecols = {r[1] for r in self.cx.execute('PRAGMA table_info(route)')}
            if 'RawOutput' not in routecols:
                self.cx.execute('ALTER TABLE route ADD COLUMN RawOutput TEXT')
            if 'ParseError' not in routecols:
                self.cx.execute('ALTER TABLE route ADD COLUMN ParseError TEXT')
            # ...and keep the verdict when triage SUCCEEDS. RawOutput cannot carry it: a non-null
            # one raises the Timeline's diagnostic panel (FeedView: the "what did triage answer"
            # box), so every task would have worn an error face. Its own column instead - the
            # before half of every correction diff, without which a rewritten summary or a
            # reassigned profile teaches nothing, because nothing remembers what was there.
            if 'VerdictJson' not in routecols:
                self.cx.execute('ALTER TABLE route ADD COLUMN VerdictJson TEXT')
            # why a reply draft could not be written (PW-046): the review stays pending and
            # reply-needed, the reason is shown beside it with a retry, never mistaken for a draft
            # the name the page gave a line it sent (general.wait_line): the page knows its own line by it, never by its words
            if 'LineId' not in {r[1] for r in self.cx.execute('PRAGMA table_info(comment)')}: self.cx.execute('ALTER TABLE comment ADD COLUMN LineId TEXT')
            # ...and what he attached, beside his words (files_json): a line's, a task's ask's, a note kept for a coding agent's
            for tbl in ('comment', 'task', 'waitroom'):
                if 'Files' not in {r[1] for r in self.cx.execute(f'PRAGMA table_info({tbl})')}: self.cx.execute(f'ALTER TABLE {tbl} ADD COLUMN Files TEXT')
            self._files_out()
            if 'Host' not in {r[1] for r in self.cx.execute('PRAGMA table_info(shown)')}: self.cx.execute('ALTER TABLE shown ADD COLUMN Host TEXT')
            rvcols ={r[1] for r in self.cx.execute('PRAGMA table_info(review)')}
            if 'DraftError' not in rvcols:
                self.cx.execute('ALTER TABLE review ADD COLUMN DraftError TEXT')
            # ...and why the writer would not draft it at all (responder.NotDrafted - its own NEEDS): work for an agent, not a failure
            if 'DraftNeeds' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN DraftNeeds TEXT')
            # what the draft was written against (PW-048): the inbound message set's revision, and whether the
            # thread has moved since - a verdict rechecks it wherever it lands (PW-055)
            if 'ContextRevision' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN ContextRevision TEXT')
            if 'Stale' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN Stale INTEGER DEFAULT 0')
            # who wrote the draft: 'agent:<name>' when the agent that did the work wrote it itself
            # (wrapup.agent_reply), NULL when the responder did - the end of the run keeps the former
            if 'DraftBy' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN DraftBy TEXT')
            # ...and the agent SESSION that wrote it (its sid), or 'owner' once the owner edited or readdressed it: a newer session holds
            # an earlier one's draft out of sight and takes its place (wrapup.stale_draft, the owner 2026-11-03)
            if 'DraftSid' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN DraftSid TEXT')
            # THE FILES THE DRAFT SAYS RIDE WITH IT, in the writer's own words (responder.FILES): JSON {"named": [...]}, NULL when it
            # promises none or nobody judged. The card's "this mentions a file" line reads this, never a word list over the text (2026-10-28)
            if 'FilesPromised' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN FilesPromised TEXT')
            # THE OWNER'S OWN WORDS FOR THE DRAFT ("shorter", "say we pay on Friday"), every one, JSON [{at, text}] - they rode into
            # the model's prompt and were gone (the owner, 2026-10-23: the typed instruction is now stored and remembered)
            if 'Instructions' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN Instructions TEXT')
            # Approval is not a provider receipt. Keep the in-flight claim and the exact
            # attempted payload separate from the UI's pending/approved review status.
            for col in ('DeliveryState', 'DeliveryClaim', 'DeliveryAttemptedAt', 'DeliveryEnvelope', 'DeliveryReceipt'):
                if col not in rvcols: self.cx.execute(f'ALTER TABLE review ADD COLUMN {col} TEXT')
            # WHICH MAIL THE DRAFT ANSWERS (the delivery target), kept apart from MessageId, the newest mail it saw (freshness); and the drafter's one line on why
            if 'AnswersMid' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN AnswersMid INTEGER')
            if 'DraftWhy' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN DraftWhy TEXT')
            # ...and WHEN ITS WORDS WERE WRITTEN, which is not when the card was raised: a reply owed is raised empty as its mail lands and
            # written later, and a line that came between read as one the draft never saw (proposals.written_past). NULL: written as raised
            if 'DraftAt' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN DraftAt TEXT')
            # ...and what an ACT's press failed on (review_act_failed): it lived only in the answer to that press - a reload drew the card as
            # if never pressed, and its agent was told nothing (the spine audit, 2026-11-09). Read only while the review still waits
            if 'ActError' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN ActError TEXT')
            # ...and WHAT HE HAS TYPED INTO A WAITING CARD, NOT PRESSED YET (hold_review_edit): it lived in the page alone, so nothing here knew
            # the card's words were his - a later draft was written over them, and a press from another surface sent the generated ones
            if 'OwnerEdit' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN OwnerEdit TEXT')
            # ...and that its failed press is his to TRY AGAIN, once (review_act_failed `retry`: a failure a second try could get past)
            if 'ActRetry' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN ActRetry INTEGER')
            # ...and the agent's word that the reply is NO LONGER NEEDED (someone else answered, the owner already did) - kept as the why
            if 'NotNeeded' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN NotNeeded TEXT')
            # ...and the BULK CARD it is one row of (bulkcard.py): many of the same act raised together, one card, one press for them all
            if 'Batch' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN Batch TEXT')
            # ...and THE VERSIONS OF ITS WORDS its agent gave for him to pick from (one call's `items` for one letter): one card, a pick on it
            if 'Versions' not in rvcols: self.cx.execute('ALTER TABLE review ADD COLUMN Versions TEXT')
            # ...and THE AGENT'S OWN STEP AFTER HIS PRESS (`then`, card.raising): his press wakes it only where there is one (general.carries_on).
            # A card left pending under a turn whose summary said `after_press: send` keeps that, once
            if 'NextStep' not in rvcols:
                self.cx.execute('ALTER TABLE review ADD COLUMN NextStep TEXT')
                self.cx.execute("UPDATE review SET NextStep='send' WHERE Status IN ('pending','held') AND TaskId IN (SELECT c.TaskId FROM comment c "
                                "WHERE c.ActorType='assistant_summary' AND c.Body LIKE '%\"after_press\": \"send\"%' AND c.CommentId=(SELECT MAX(CommentId) "
                                "FROM comment WHERE TaskId=c.TaskId AND ActorType IN ('assistant_summary','assistant_agent')))")
            # ...and WHAT FILED IT ('triage': a reply triage owes; 'chase': the owner's chase), where its kind does not say. It was read off
            # the first words of Reason - the line the card shows the owner, which a redraft rewrites (the spine audit, 2026-11-09). The rows
            # filed under those words are marked once, here
            if 'Origin' not in rvcols:
                self.cx.execute('ALTER TABLE review ADD COLUMN Origin TEXT')
                for mark, origin in (('needs a reply:%', 'triage'), ('chase:%', 'chase')): self.cx.execute('UPDATE review SET Origin=? WHERE Reason LIKE ?', (origin, mark))
            # ...which retires the draft now (verdicts.not_needed, 2026-11-09). One marked under the old rule still sat pending with Send under it:
            # it goes where a withdrawn draft goes - closed unsent, under Not sent, Bring it back still sends it
            self.cx.execute("UPDATE review SET Status='closed_unsent', DecidedBy='agent', DecidedAt=?, DecideNote='withdrawn - '||NotNeeded "
                            "WHERE Status='pending' AND IFNULL(NotNeeded,'')<>'' AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'')<>'sent'", (_now(),))
            # the triage-generated checklist (PW-075): JSON items with stable ids, separate from Status
            tcols = {r[1] for r in self.cx.execute('PRAGMA table_info(task)')}
            if 'Checklist' not in tcols:
                self.cx.execute('ALTER TABLE task ADD COLUMN Checklist TEXT')
            # Remind me (the owner, 2026-09-25): the day an open task comes back; until then it is Upcoming
            if 'RemindAt' not in tcols: self.cx.execute('ALTER TABLE task ADD COLUMN RemindAt TEXT')
            # Watch it (the owner, 2026-11-01): when the owner began watching a task that is not theirs (watch.py), and why a watch came
            # back on the walk ('moved', 'handled', 'quiet') until their next move
            for col in ('WatchedAt', 'WatchBack'):
                if col not in tcols: self.cx.execute(f'ALTER TABLE task ADD COLUMN {col} TEXT')
            # a check-back its agent set (the owner, 2026-11-05: checkback.py): when the same task's agent wakes, and what it is to verify
            for col in ('CheckBackAt', 'CheckBackWhat'):
                if col not in tcols: self.cx.execute(f'ALTER TABLE task ADD COLUMN {col} TEXT')
            # what the owner asked for, and where (asks.py): the door, and the last lane said there - kept on the task,
            # so a restart never repeats what was already told
            # ...a watch on a task nobody works (what, and the last reply already seen), and where a reminder was set
            # and whether it is still owed to a busy phone chat
            for col in ('AskedVia', 'AskedTold', 'AskedToldAt', 'AskedWatch', 'AskedSeenMid', 'RemindVia', 'RemindOwed'):
                if col not in tcols: self.cx.execute(f'ALTER TABLE task ADD COLUMN {col} TEXT')
            # a watch counts its 30 days from when it began, not from the task's age, and says its nudge once (asks.py);
            # the day the work is due, as triage read it from the mail, and the last step of it already said (remind.py)
            # ...and the priority it had before the due day raised it to urgent (B18), so a day moved weeks out puts back
            # only the assistant's own urgent - any other write of Priority clears it (update_task)
            for col in ('AskedWatchAt', 'AskedNudgedAt', 'DueAt', 'DueSaid', 'DueRaised'):
                if col not in tcols: self.cx.execute(f'ALTER TABLE task ADD COLUMN {col} TEXT')
            # a GOAL is a task with a done-when sentence and a date; its boxes may point at child tasks, which carry the
            # parent (spec 2026-10-12, goals as tasks). Derived everywhere from DoneWhen - no kind, no second object.
            if 'DoneWhen' not in tcols: self.cx.execute('ALTER TABLE task ADD COLUMN DoneWhen TEXT')
            if 'ParentId' not in tcols: self.cx.execute('ALTER TABLE task ADD COLUMN ParentId INTEGER')
            # where the task's words came from (origin.py): what the owner raised it to, through which message, and the
            # last computed answer the card reads. Computed on read from the messages, so no ingest road can skip it.
            for col in ('OriginBase', 'Origin', 'OriginWhy'):
                if col not in tcols: self.cx.execute(f'ALTER TABLE task ADD COLUMN {col} TEXT')
            # who the task waits on, since when, and the line that woke it (waiton.py)
            for col in ('WaitingOn', 'WaitingSince', 'WokeMid'):
                if col not in tcols: self.cx.execute(f'ALTER TABLE task ADD COLUMN {col} TEXT')
            if 'TrustedThrough' not in tcols: self.cx.execute('ALTER TABLE task ADD COLUMN TrustedThrough INTEGER')
            # triage's newest reading of the conversation (triage.thread_of), its mid 0 already the mail's own id
            if 'ThreadJson' not in tcols: self.cx.execute('ALTER TABLE task ADD COLUMN ThreadJson TEXT')
            # an email slot an agent addressed as "Name <address>" handed the provider the whole string (TQ-0957): the
            # recipient is the address, the name rides beside it (slots.split) - repaired once, on start
            from .slots import split
            for r in self.cx.execute("SELECT ReviewId, Deliver FROM review WHERE Kind='slot' AND Deliver LIKE '%<%' "
                                     "AND IFNULL(DeliveryState,'') NOT IN ('sending','unknown','sent')").fetchall():
                env = json.loads(r[1] or '{}') or {}
                env['to'] = [split(a)[1] for a in env.get('to') or []]
                self.cx.execute('UPDATE review SET Deliver=? WHERE ReviewId=?', (json.dumps(env), r[0]))
            for r in self.cx.execute("SELECT TaskId, Checklist FROM task WHERE Checklist LIKE '%\"out\"%<%'").fetchall():
                items = json.loads(r[1] or '[]') or []
                for i in items:
                    o = i.get('out') if isinstance(i, dict) else None
                    if isinstance(o, dict) and '<' in str(o.get('to') or ''):
                        name, o['to'] = split(o['to'])
                        if name: o['name'] = name
                self.cx.execute('UPDATE task SET Checklist=? WHERE TaskId=?', (json.dumps(items), r[0]))
            # the owner's own replies were stored as INCOMING (X1, 2026-09-25) - everything that counts senders, and the
            # triage accuracy measure, counted the owner as one. 'You' on a context row is the owner, never a bot.
            self.cx.execute("UPDATE message SET Direction='out' WHERE Status='context' AND FromName='You' AND IFNULL(Direction,'in')='in'")
            # ...and his New-box ask was filed as mail he SENT, its recipient as its source (outbox.ask_row, 2026-11-17): his line now, to them
            for r in self.cx.execute("SELECT MessageId, SourceName FROM message WHERE ExternalId LIKE 'outbox:%' AND Direction='out'").fetchall():
                to = [a.strip() for a in str(r[1] or '').split(',') if a.strip()]
                self.cx.execute("UPDATE message SET Direction='in', SourceName=NULL, RecipientsJson=COALESCE(RecipientsJson, ?) WHERE MessageId=?",
                                (json.dumps({'to': to, 'cc': []}), r[0]))
            # WHICH BRAIN ran a session, beside the role that owned it. A role is always the same
            # for coding work, so the session is the only place the actual CLI is recorded
            # (docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md)
            trcols = {r[1] for r in self.cx.execute('PRAGMA table_info(transcript)')}
            if 'Brain' not in trcols: self.cx.execute('ALTER TABLE transcript ADD COLUMN Brain TEXT')
            # how complete each email conversation is (chains.py, PW-010): listed at the provider, added
            # here, and the error when it could not be completed - never guessed from what is stored
            self.cx.execute('CREATE TABLE IF NOT EXISTS chain (Mailbox TEXT NOT NULL DEFAULT "", ConversationId TEXT NOT NULL, Channel TEXT, '
                            'CheckedAt TEXT, Complete INTEGER, Listed INTEGER, Added INTEGER, Error TEXT, PRIMARY KEY (Mailbox, ConversationId))')
            # coverage belongs to the mailbox that checked it (PW-011): a table keyed by the bare conversation id let
            # two accounts sharing one share one row; an older database is re-keyed once, rows kept
            chain_sql = str((self.cx.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='chain'").fetchone() or [''])[0] or '')
            if 'ConversationId TEXT PRIMARY KEY' in chain_sql:
                self.cx.execute('ALTER TABLE chain RENAME TO chain_v1')
                self.cx.execute('CREATE TABLE chain (Mailbox TEXT NOT NULL DEFAULT "", ConversationId TEXT NOT NULL, Channel TEXT, '
                                'CheckedAt TEXT, Complete INTEGER, Listed INTEGER, Added INTEGER, Error TEXT, PRIMARY KEY (Mailbox, ConversationId))')
                self.cx.execute("INSERT OR IGNORE INTO chain (Mailbox, ConversationId, Channel, CheckedAt, Complete, Listed, Added, Error) "
                                "SELECT LOWER(IFNULL(Mailbox,'')), ConversationId, Channel, CheckedAt, Complete, Listed, Added, Error FROM chain_v1")
                self.cx.execute('DROP TABLE chain_v1')
            # shared operations (operations.py, PW-129..134): a proposal with its confirmation version and the
            # context it was judged on, its one execution and real outcome; correction EVIDENCE keyed to the
            # operation (never a memory note or a rule); discussion kept against the source item and its task
            self.cx.execute('CREATE TABLE IF NOT EXISTS operation (OpId TEXT PRIMARY KEY, Kind TEXT, TargetKind TEXT, TargetId INTEGER, '
                            'ParamsJson TEXT, Actor TEXT, ContextRevision TEXT, Version INTEGER, Status TEXT, OutcomeJson TEXT, Error TEXT, '
                            'Evidence TEXT, Verdict TEXT, VerdictRouteId INTEGER, CreatedAt TEXT, UpdatedAt TEXT, ExecutedAt TEXT)')
            self.cx.execute('CREATE TABLE IF NOT EXISTS correction (Id INTEGER PRIMARY KEY, OpId TEXT UNIQUE, MessageId INTEGER, TaskId INTEGER, '
                            'Sender TEXT, Topic TEXT, Verdict TEXT, VerdictRouteId INTEGER, Change TEXT, ContextJson TEXT, CreatedAt TEXT)')
            self.cx.execute('CREATE TABLE IF NOT EXISTS discussion (Id INTEGER PRIMARY KEY, MessageId INTEGER, TaskId INTEGER, Actor TEXT, '
                            'Body TEXT, OpId TEXT, CreatedAt TEXT)')
            # THE OUTCOME LEDGER (spec 2026-10-12, build step 2): what the app did, what the owner did next, what came of
            # it - resolved later by outcomes.resolve from facts already here. Evidence for reflection, never a rule.
            self.cx.execute('CREATE TABLE IF NOT EXISTS outcome (Id INTEGER PRIMARY KEY, Kind TEXT, TargetKind TEXT, TargetId INTEGER, '
                            'Actor TEXT, At TEXT, FactsJson TEXT, NextMove TEXT, NextAt TEXT, Outcome TEXT, ResolvedAt TEXT, Verdict TEXT)')
            self.cx.execute('CREATE INDEX IF NOT EXISTS outcome_target ON outcome(TargetKind, TargetId)')
            # THE ADVISOR LIGHTS NO BUTTON (the owner, 2026-11-15: "remove the entire advisor from buttons thing"): its judgements (advice) and
            # the press log that measured them (advice_press) are dropped from every home; advice_decision keeps a duplicate pair's survivor alone
            self.cx.execute('DROP TABLE IF EXISTS advice'); self.cx.execute('DROP TABLE IF EXISTS advice_press')
            self.cx.execute('CREATE TABLE IF NOT EXISTS advice_decision (Key TEXT PRIMARY KEY, Stamp TEXT, Json TEXT, At TEXT)')
            self.cx.execute("DELETE FROM advice_decision WHERE Key NOT LIKE 'pair:%'")
            # ...and each learned line's SECTION (Reader holds its slug now), whom it is about (Subject: the address in a people line)
            # and when it stopped being true (ValidTo, status closed) - a fact that ended is closed, never deleted (2026-10-25)
            llcols = {r[1] for r in self.cx.execute('PRAGMA table_info(learned_line)')}
            for col in ('Subject', 'ValidTo'):
                if col not in llcols: self.cx.execute(f'ALTER TABLE learned_line ADD COLUMN {col} TEXT')
            # WHICH WORKSTREAM each item is under (the design 2026-11-01, workstreams.py): a day job, a side product, personal - '' unplaced
            # ...and which one an ACCOUNT is tagged to - a connection, a mailbox (workstreams.of_account); '' serves every profile
            for t in ('task', 'message', 'idea', 'learned_line', 'connector', 'source'):
                if 'Workstream' not in {r[1] for r in self.cx.execute(f'PRAGMA table_info({t})')}:
                    self.cx.execute(f'ALTER TABLE {t} ADD COLUMN Workstream TEXT')
            # a verified 'this mailbox wrote to them' hit, remembered so the mail server is asked once per address (PW-080)
            self.cx.execute('CREATE TABLE IF NOT EXISTS sender_trust (Mailbox TEXT, Address TEXT, Reason TEXT, CheckedAt TEXT, '
                            'PRIMARY KEY (Mailbox, Address))')
            # explicit worker events (workerstate.py, PW-222/227): what a run said about itself, by task, run and request
            self.cx.execute('CREATE TABLE IF NOT EXISTS worker_event (Id INTEGER PRIMARY KEY, TaskId INTEGER, Sid TEXT, Kind TEXT, RequestId TEXT, '
                            'Text TEXT, ChoicesJson TEXT, Source TEXT, EventId TEXT UNIQUE, CreatedAt TEXT)')
            # ...read by task on every session row, hand-raise tick and task list: without this each read scanned every event ever written
            self.cx.execute('CREATE INDEX IF NOT EXISTS idx_worker_event_task ON worker_event(TaskId, Id)')
            # the assistant's private read on the message (counsel.py) - JSON, shown on the panel
            if 'Brief' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN Brief TEXT')
            # WHAT TRIAGE CALLED IT, in its own words (triage.TASK_FIELDS answers a title on every
            # verdict). A task keeps its title on the task, but an fyi or a triaged report has no
            # task to hold one - so the rail fell back to the mail header and a row read
            # "rrdbreports@northwind.example - Northwind - PCC ..." (the owner, 2026-09-16). This is where the
            # verdict's line lives for a message that never became work.
            if 'TriageTitle' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN TriageTitle TEXT')
            # WHO SENT IT - person / automated / bulk (categories.sender_class): the mail's own list and auto-submission
            # headers at ingest, then the triage verdict's word over them (add_route). Null on every row stored before
            # 2026-10-11, which reads as a person: the address-and-footer regexes that guessed it are gone.
            if 'SenderClass' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN SenderClass TEXT')
            # ...and what the HEADERS said, which the verdict never overwrites (header_words: "a system (Auto-Submitted: ...)"): triage
            # is told it, and the eval splits machine-sent mail by it after SenderClass has taken the verdict's word (2026-11-12)
            if 'HeaderClass' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN HeaderClass TEXT')
            # what the message's text tries to make an AI do, in the reading model's words (the triage verdict's `danger`,
            # or ranking's for a batched arrival): a warning on a stranger's card, never a gate
            if 'Danger' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN Danger TEXT')
            # ...and WHO IT IS AIMED AT - 'owner' (a scam on them) or 'agent' (text written to steer the AI): the warning's words follow it
            # (the owner, 2026-10-30: a phish on the owner read "an attempt to steer the agent"). Null on older rows, which read as 'agent'
            if 'DangerAim' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN DangerAim TEXT')
            # the message asks the owner to find a time to meet (the triage verdict's `meet`, JSON {minutes, from, to}): its row
            # offers Find a time (calwrite.slots_for)
            if 'MeetJson' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN MeetJson TEXT')
            # WHAT ORDER TO JUDGE IT IN (bulk processing, rank.py). Triage is the expensive call, so a
            # connector in rank mode ranks its arrivals BEFORE judging any: 300 pull requests cost one
            # listwise ranking call and four triage calls, not 300 triage calls. The value lives on the
            # message because at this point there is no task - making one is what triage does.
            if 'RankValue' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN RankValue REAL')
            if 'RankWhy' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN RankWhy TEXT')
            # WHERE an approved outbound draft goes. A reply knows its recipient from the
            # message it answers; an outbound report has no such message, so the review has to
            # carry the address itself or approving it would have nowhere to send.
            rcols = {r[1] for r in self.cx.execute('PRAGMA table_info(review)')}
            if 'Deliver' not in rcols:
                self.cx.execute('ALTER TABLE review ADD COLUMN Deliver TEXT')
            icols = {r[1] for r in self.cx.execute('PRAGMA table_info(invoice_item)')}
            if 'TemplateInvoiceId' not in icols:
                self.cx.execute('ALTER TABLE invoice_item ADD COLUMN TemplateInvoiceId TEXT')
            # the wall composts: a day's notes are summarised into one and marked with the day
            # they were rolled up, so the live wall stays short without anything being deleted
            ncols = {r[1] for r in self.cx.execute('PRAGMA table_info(boardnote)')}
            if 'Rolled' not in ncols: self.cx.execute('ALTER TABLE boardnote ADD COLUMN Rolled TEXT')
            if 'Sid' not in ncols: self.cx.execute('ALTER TABLE boardnote ADD COLUMN Sid TEXT')   # the run that wrote it (PW-178)
            tcols = {r[1] for r in self.cx.execute('PRAGMA table_info(transcript)')}
            if 'ExtId' not in tcols: self.cx.execute('ALTER TABLE transcript ADD COLUMN ExtId TEXT')   # the CLI's own conversation, reopenable
            qcols = {r[1] for r in self.cx.execute('PRAGMA table_info(dispatchq)')}
            for col, typ in (('Value', 'REAL'), ('Floor', 'REAL'), ('Why', 'TEXT'),    # rank.py: value-ordered queue
                             ('Attempts', 'INTEGER DEFAULT 0'), ('LastError', 'TEXT'), ('NextAt', 'TEXT'), ('State', 'TEXT'),   # PW-085: the retry budget
                             ('Brief', 'TEXT'),         # what a general start was to be asked (ingest._auto_general), kept for the drain
                             ('Turn', 'TEXT')):         # a stopped agent's next turn waiting for a slot, not a fresh start (ingest.queue_turn)
                if col not in qcols: self.cx.execute(f'ALTER TABLE dispatchq ADD COLUMN {col} {typ}')
            have = {r[1] for r in self.cx.execute('PRAGMA table_info(connector)')}
            if 'Roles' not in have: self.cx.execute('ALTER TABLE connector ADD COLUMN Roles TEXT')
            # left NULL on purpose: scopes.scope_of falls back to the type's default, so an
            # existing db keeps exactly the authority it had before the column existed
            if 'Scope' not in have: self.cx.execute('ALTER TABLE connector ADD COLUMN Scope TEXT')
            # Connector Type used to be UNIQUE, which made the catalog row the only possible
            # instance of a connector. SQLite cannot drop an inline unique constraint, so widen
            # the table in place while keeping every ConnectorId. Source ownership is by that id,
            # so mailboxes/repos/cloud objects remain attached to exactly the same connection.
            unique_type = False
            for ix in self.cx.execute('PRAGMA index_list(connector)').fetchall():
                if not ix[2]: continue
                cols = [r[2] for r in self.cx.execute(f'PRAGMA index_info("{ix[1]}")').fetchall()]
                if cols == ['Type']: unique_type = True; break
            if unique_type:
                self.cx.execute('SAVEPOINT widen_connector_type')
                try:
                    self.cx.execute('ALTER TABLE connector RENAME TO connector_one_per_type')
                    # every column the old table has rides across, in its own type: a rebuild that named its columns
                    # dropped one added above (an account's Workstream), and the first read after it failed
                    info = self.cx.execute('PRAGMA table_info(connector_one_per_type)').fetchall()
                    names = ', '.join(f'"{r[1]}"' for r in info)
                    defs = ', '.join(f'"{r[1]}" {r[2]}' + (' PRIMARY KEY' if r[5] else '') + (f' DEFAULT {r[4]}' if r[4] is not None else '') for r in info)
                    self.cx.execute(f'CREATE TABLE connector ({defs})')
                    self.cx.execute(f'INSERT INTO connector ({names}) SELECT {names} FROM connector_one_per_type')
                    self.cx.execute('DROP TABLE connector_one_per_type')
                    self.cx.execute('RELEASE widen_connector_type')
                except Exception:
                    self.cx.execute('ROLLBACK TO widen_connector_type')
                    self.cx.execute('RELEASE widen_connector_type')
                    raise
            # a workflow's steps, each with its status, output and time (flow.py), and the run task they belong to
            rrcols = {r[1] for r in self.cx.execute('PRAGMA table_info(report_run)')}
            if 'StepsJson' not in rrcols: self.cx.execute('ALTER TABLE report_run ADD COLUMN StepsJson TEXT')
            if 'TaskId' not in rrcols: self.cx.execute('ALTER TABLE report_run ADD COLUMN TaskId INTEGER')
            if 'RepairsJson' not in rrcols: self.cx.execute('ALTER TABLE report_run ADD COLUMN RepairsJson TEXT')   # flow.py self-repairs
            # what each AI call used (aiusage.py, 2026-11-06)
            brcols = {r[1] for r in self.cx.execute('PRAGMA table_info(brainroute)')}
            # ...and which function asked (aiusage.asking, 2026-11-11): a row from before it has none, and reads as a call nobody named
            for c, t in (('Ran', 'TEXT'), ('TokensIn', 'INTEGER'), ('Cached', 'INTEGER'), ('TokensOut', 'INTEGER'), ('Calls', 'INTEGER'), ('Sid', 'TEXT'),
                         ('Caller', 'TEXT'), ('FellFrom', 'TEXT'),       # ...and the model asked for, where another answered (llm.fell_back)
                         ('Cost', 'REAL')):      # ...and what the provider said the call cost, in dollars, where it says (aiusage.cost, 2026-11-24)
                if c not in brcols: self.cx.execute(f'ALTER TABLE brainroute ADD COLUMN {c} {t}')
            # after the widen above, which rebuilds the table without it
            if 'LastErrorAt' not in {r[1] for r in self.cx.execute('PRAGMA table_info(connector)')}:
                self.cx.execute('ALTER TABLE connector ADD COLUMN LastErrorAt TEXT')
            for ix in INDEXES:
                self.cx.execute(ix)
            for table in PROCESSING_DIRTY_TABLES:
                for action in ('INSERT', 'UPDATE', 'DELETE'):
                    self.cx.execute(f'''CREATE TRIGGER IF NOT EXISTS processing_dirty_{table}_{action.lower()}
                        AFTER {action} ON {table} BEGIN
                          UPDATE processing_reconcile_state
                          SET DirtyGeneration=DirtyGeneration+1 WHERE Singleton=1;
                        END''')
            # WHO IS TRUSTED moves with these writes, from any process (origin.hold keeps each task's judged hold under this generation)
            self.cx.execute("INSERT OR IGNORE INTO change_gen (Tbl, Gen) VALUES ('trust', 0)")
            self.cx.execute('CREATE TABLE IF NOT EXISTS origin_hold (TaskId INTEGER PRIMARY KEY, Sig TEXT, HoldJson TEXT)')
            # ...a setting only where its value moved, and none a pile never reads (a stamp the store rewrites as it opens left every hold stale)
            blind = lambda r: ' AND '.join(f"{r}.Name NOT LIKE '{k}%'" for k in PILE_BLIND_SETTINGS)
            for table, cols in TRUST_INPUTS:
                for action in ('INSERT', 'UPDATE', 'DELETE'):
                    of = f' OF {cols}' if action == 'UPDATE' and cols not in ('', 'blind') else ''
                    row = 'OLD' if action == 'DELETE' else 'NEW'
                    cond = '' if cols != 'blind' else f' WHEN {blind(row)}' + (' AND OLD.Value IS NOT NEW.Value' if action == 'UPDATE' else '')
                    self.cx.execute(f'''CREATE TRIGGER IF NOT EXISTS trust_gen_{table}_{action.lower()} AFTER {action}{of} ON {table}{cond}
                        BEGIN UPDATE change_gen SET Gen=Gen+1 WHERE Tbl='trust'; END''')
            setting_names = ','.join("'" + name + "'" for name in PROCESSING_DIRTY_SETTINGS)
            self.cx.execute(f'''CREATE TRIGGER IF NOT EXISTS processing_dirty_setting_insert
                AFTER INSERT ON setting WHEN NEW.Name IN ({setting_names}) BEGIN
                  UPDATE processing_reconcile_state SET DirtyGeneration=DirtyGeneration+1 WHERE Singleton=1;
                END''')
            self.cx.execute(f'''CREATE TRIGGER IF NOT EXISTS processing_dirty_setting_update
                AFTER UPDATE ON setting WHEN OLD.Name IN ({setting_names}) OR NEW.Name IN ({setting_names}) BEGIN
                  UPDATE processing_reconcile_state SET DirtyGeneration=DirtyGeneration+1 WHERE Singleton=1;
                END''')
            self.cx.execute(f'''CREATE TRIGGER IF NOT EXISTS processing_dirty_setting_delete
                AFTER DELETE ON setting WHEN OLD.Name IN ({setting_names}) BEGIN
                  UPDATE processing_reconcile_state SET DirtyGeneration=DirtyGeneration+1 WHERE Singleton=1;
                END''')
            from . import processing_rail, processing_membership
            processing_rail.install(self.cx, PROCESSING_DIRTY_SETTINGS)
            # what the census reads, apart from what readers need to see (processing_membership.CENSUS_INPUTS);
            # -1 never equals a generation, so a database new to these columns runs its next census in full
            rscols = {r[1] for r in self.cx.execute('PRAGMA table_info(processing_reconcile_state)')}
            if 'MembershipGeneration' not in rscols:
                self.cx.execute('ALTER TABLE processing_reconcile_state ADD COLUMN MembershipGeneration INTEGER NOT NULL DEFAULT 0')
            if 'CensusGeneration' not in rscols:
                self.cx.execute('ALTER TABLE processing_reconcile_state ADD COLUMN CensusGeneration INTEGER NOT NULL DEFAULT -1')
            processing_membership.install_census_triggers(self.cx)
            try: self.cx.execute(KB_FTS); self.kb_fts = True
            except sqlite3.OperationalError as e:
                self.kb_fts = False; logger.warning(f'no FTS5 in this sqlite build - knowledge search falls back to LIKE: {e}')
            self.msg_fts = self.kb_fts and self._open_msg_fts()
            # renamed keys keep the owner's value: moved BEFORE the seed below, or the new name is seeded first and the old
            # value is stranded. OR IGNORE leaves a new name that already exists alone; the old row goes either way.
            for old, new in SETTING_RENAMES:
                self.cx.execute('UPDATE OR IGNORE setting SET Name=? WHERE Name=?', (new, old))
                self.cx.execute('DELETE FROM setting WHERE Name=?', (old,))
            for k, v in DEFAULT_SETTINGS.items():
                self.cx.execute('INSERT OR IGNORE INTO setting (Name, Value) VALUES (?,?)', (k, v))
            # AUTO ROUTING ON (the owner, 2026-11-06: "it should be on auto routing by default"). The old seed was 'fixed' with no
            # writer; a Fixed the owner chose carries who saved it (brainroute.set_panel, the Settings row), so only the seed moves
            self.cx.execute("UPDATE setting SET Value='auto', UpdatedBy='migration' WHERE Name='ai_route_mode' AND Value='fixed' "
                            "AND COALESCE(UpdatedBy, '')=''")
            # ...and the poll's old seed of 10 moves under the cache window the same way (the owner, 2026-11-11: "if you have to
            # move triage to 5 minutes to keep cache it's worth it"): a 10 somebody typed carries its writer and stays
            self.cx.execute("UPDATE setting SET Value=?, UpdatedBy='migration' WHERE Name='poll_minutes' AND Value='10' "
                            "AND COALESCE(UpdatedBy, '')=''", (DEFAULT_SETTINGS['poll_minutes'],))
            from . import apireads, connectorcatalog
            for t, n in (('outlook', 'Outlook mail'), ('teams', 'Microsoft Teams'),
                         ('slack', 'Slack'), ('github', 'GitHub'),
                         ('anthropic', 'Anthropic API'), ('openai', 'OpenAI API'),
                         ('groq', 'Groq'),
                         ('mistral', 'Mistral AI'),
                         ('together', 'Together AI'),
                         ('cerebras', 'Cerebras'),
                         ('xai', 'xAI Grok'),
                         ('gemini', 'Google Gemini'),
                         ('cohere', 'Cohere'),
                         ('deepseek', 'DeepSeek'),
                         ('perplexity', 'Perplexity'),
                         ('fireworks_ai', 'Fireworks AI'), ('nvidia_nim', 'NVIDIA NIM'), ('sambanova', 'SambaNova'), ('deepinfra', 'DeepInfra'), ('novita', 'Novita AI'), ('hyperbolic', 'Hyperbolic'), ('bedrock', 'AWS Bedrock'),
                         ('hipaa_ai', 'HIPAA AI'),
                         ('azure_openai', 'Azure OpenAI'), ('vertex_ai', 'Google Vertex AI'), ('openrouter', 'OpenRouter'),
                         ('ollama', 'Local models (Ollama)'), ('meta', 'Meta Model API (Muse Spark)'),
                         ('chatgpt', 'ChatGPT (your plan)'),
                         # answers typed questions and emits no text at all, so it is a card you can
                         # paste a key on but never a brain - see the comment on llm.AI_TYPES
                         ('typesafe', 'TypeSafe Jev (decisions only)'),
                         ('mssql', 'Microsoft SQL Server'),
                         ('telegram', 'Telegram'), ('whatsapp', 'WhatsApp'),
                         ('linkedin', 'LinkedIn'),
                         ('treg', 'treg (agent tools)'),
                         ('reason_network', 'Reason Network'),
                         ('agent_desktop', 'Agent Desktop'),
                         # video tools for the agents (videotools.py): remote MCP servers, a skill, and a key card - each seeded off
                         ('descript', 'Descript'), ('invideo', 'InVideo'), ('vidova', 'Vidova'), ('opusclip', 'OpusClip'),
                         ('video_use', 'video-use (Browser Use)'), ('kling', 'Kling AI'),          # seeded off, like every card: the owner's desktop is opt-in (agentdesktop.py)
                         ('postgresql', 'PostgreSQL'),
                         ('mysql', 'MySQL / MariaDB'),
                         ('clickhouse', 'ClickHouse'),
                         ('cockroachdb', 'CockroachDB'), ('oracle', 'Oracle Database'), ('duckdb', 'DuckDB'), ('dynamodb', 'Amazon DynamoDB'),
                         ('mongodb', 'MongoDB'), ('redis', 'Redis'), ('neo4j', 'Neo4j'), ('obsidian', 'Obsidian'),
                         # a vendor's REST API read with a key (apireads.json)
                         *((t, r['title']) for t, r in apireads.table().items()),
                         ('snowflake', 'Snowflake'),
                         ('bigquery', 'Google BigQuery'),
                         ('imessage', 'Apple Messages'),
                         ('gmail', 'Gmail / Google Workspace'), ('imap', 'Any mailbox (IMAP)'),
                         ('winrm', 'Remote Windows (WinRM)'),
                         ('database', 'Any database (connection string)'),
                         ('robinhood', 'Robinhood (agentic trading)'),
                         ('aws', 'Amazon Web Services'), ('azure', 'Microsoft Azure'),
                         ('sharepoint', 'SharePoint'), ('google_sheets', 'Google Sheets'),
                         ('smb_file', 'Network file share'), ('sftp', 'SFTP'),
                         ('knowledge', 'Knowledge base'), ('handbook', 'Company Hub'),
                         ('jira', 'Jira'), ('asana', 'Asana'), ('monday', 'Monday.com'),
                         ('clickup', 'ClickUp'), ('todoist', 'Todoist'),
                         ('gitlab', 'GitLab'), ('azdo', 'Azure DevOps'), ('linear', 'Linear'),
                         ('trello', 'Trello'), ('notion', 'Notion'), ('discord', 'Discord'),
                         ('mattermost', 'Mattermost'), ('rocketchat', 'Rocket.Chat'),
                         ('matrix', 'Matrix'), ('google_chat', 'Google Chat'),
                         ('sentry', 'Sentry'), ('pagerduty', 'PagerDuty'), *INBOX_NAMES.items(),
                         ('prometheus', 'Prometheus'), ('datadog', 'Datadog'),
                         ('intacct', 'Sage Intacct'), ('quickbooks', 'QuickBooks Online'), ('amazon_sp', 'Amazon (Seller Central & Business)'), ('stripe', 'Stripe'), ('teller', 'Bank & card feed (Teller)'),
                         ('simplefin', 'Bank & card feed (SimpleFIN)'),
                         ('coingecko', 'Crypto prices (CoinGecko)'), ('alchemy', 'Alchemy'), ('frankfurter', 'FX rates'),
                         ('yahoo', 'Yahoo Finance (best-effort)'), ('sec_edgar', 'SEC filings (EDGAR)'),
                         ('twelvedata', 'Twelve Data'), ('alphavantage', 'Alpha Vantage'), ('fred', 'FRED (keyless)'),
                         ('finnhub', 'Finnhub'), ('polygon', 'Polygon.io'), ('tiingo', 'Tiingo'),
                         ('marketstack', 'Marketstack'), ('eodhd', 'EOD Historical Data'),
                         ('fmp', 'Financial Modeling Prep'), ('alpaca', 'Alpaca (market data)'),
                         ('screen', 'Strategy screen'),
                         ('zoho_invoice', 'Zoho Invoice'),
                         ('exa', 'Exa search'), ('tavily', 'Tavily search'),
                         ('firecrawl', 'Firecrawl'), ('reader', 'Jina Reader'),
                         ('bluesky', 'Bluesky'), ('mastodon', 'Mastodon'),
                         ('brave_search', 'Brave Search'), ('serpapi', 'SerpApi'),
                         ('serper', 'Serper'), ('scrapingbee', 'ScrapingBee'), ('apify', 'Apify'),
                         ('gemini_stt', 'Google Gemini transcription'), ('groq_stt', 'Groq (Whisper)'), ('openai_stt', 'OpenAI transcription'), ('deepgram', 'Deepgram'),
                         ('elevenlabs_stt', 'ElevenLabs Scribe'), ('stt_server', 'Any Whisper server'), ('local_whisper', 'Local Whisper'),
                         ('assemblyai', 'AssemblyAI'), ('speechmatics', 'Speechmatics'), ('gladia', 'Gladia'), ('azure_speech', 'Azure AI Speech'), ('amazon_transcribe', 'Amazon Transcribe'),
                         # image models (images.py). Seeded like every other card: DEFAULT_ROLES
                         # says what a type IS, but the Connections page renders from ROWS, and a
                         # type with no row is a group with nothing in it (2026-09-15).
                         ('openai_image', 'OpenAI images'), ('azure_openai_image', 'Azure OpenAI images'),
                         ('gemini_image', 'Google Gemini images'), ('stability_image', 'Stability AI'),
                         ('openrouter_image', 'OpenRouter images'), ('replicate_image', 'Replicate'), ('runway_image', 'Runway'),
                         ('xai_image', 'xAI Grok images'), ('image_server', 'Any image server'),
                         # every vendor's own MCP server for the agents (remotemcp.py): a catalogue row with an `mcp` url is a card
                         *((c['type'], c['title']) for c in connectorcatalog.cards() if c.get('mcp'))):
                # Type is intentionally not unique anymore. Seed only when a type has no card;
                # INSERT OR IGNORE would now insert another blank copy on every startup.
                self.cx.execute('''INSERT INTO connector (Type, Name, Roles)
                                   SELECT ?, ?, ? WHERE NOT EXISTS
                                   (SELECT 1 FROM connector WHERE Type=?)''',
                                (t, n, DEFAULT_ROLES.get(t, ''), t))
            for t, r in DEFAULT_ROLES.items():        # dbs from before roles existed
                self.cx.execute('UPDATE connector SET Roles=? WHERE Type=? AND Roles IS NULL', (r, t))
            # Reddit's card became an agent tool when it learned to post: one from before, an inbox alone, gains the role once
            if self.cx.execute("SELECT 1 FROM setting WHERE Name='reddit_tool_role'").fetchone() is None:
                self.cx.execute("UPDATE connector SET Roles='trigger,tool' WHERE Type='reddit' AND Roles='trigger'")
                self.cx.execute("INSERT OR REPLACE INTO setting (Name, Value) VALUES ('reddit_tool_role','1')")
            # Product rename without touching a name the owner customised.
            self.cx.execute("UPDATE connector SET Name='Company Hub' WHERE Type='handbook' AND Name='Company handbook'")
            # SECRETS ARE SEALED (vault.py): a database from before kept them as text - seal those in place, once each
            for cid, sec in self.cx.execute("SELECT ConnectorId, Secret FROM connector WHERE Secret IS NOT NULL AND Secret != '' "
                                            "AND Secret NOT LIKE 'vault:%'").fetchall():
                if vault.sealed(new := vault.seal(sec)): self.cx.execute('UPDATE connector SET Secret=? WHERE ConnectorId=?', (new, cid))
            # ...and the config fields that are secret (connectorcatalog.map_secrets) saved before they were sealed there too
            n = 0
            for cid, t, cj in self.cx.execute("SELECT ConnectorId, Type, ConfigJson FROM connector WHERE ConfigJson IS NOT NULL AND ConfigJson != ''").fetchall():
                try: c = json.loads(cj)
                except (TypeError, ValueError): continue
                if not isinstance(c, dict): continue
                got = map_secrets(c, lambda v: v if vault.sealed(v) else vault.seal(v), secret_keys(t))
                if got != c: n += 1; self.cx.execute('UPDATE connector SET ConfigJson=? WHERE ConnectorId=?', (json.dumps(got), cid))
            if n: logger.info(f'sealed the secret config fields of {n} card(s) that were kept as text')
            # The handbook ships ON - handbook.enabled has said so since it was written - but its
            # card is seeded like every other, at Active 0, and enabled() reads the card when one
            # exists. So the feature was off on every install that ever ran: wrapup.wrap skipped
            # learn_from_session, `--learned` was refused, and the Hub tab could only ever hold
            # what a person typed. Flip it once and remember that we did, so an owner who turns it
            # off later does not find it back on after a restart.
            if self.cx.execute("SELECT 1 FROM setting WHERE Name='handbook_on_by_default'").fetchone() is None:
                self.cx.execute("UPDATE connector SET Active=1 WHERE Type='handbook'")
                self.cx.execute("INSERT OR REPLACE INTO setting (Name, Value) VALUES ('handbook_on_by_default','1')")
            # operator documents start from shipped templates (John Smith placeholder) -
            # first run only; the owner's edits are never overwritten
            from pathlib import Path
            # data heal: the owner-name pass (server._heal_owner_docs) used to save every doc it
            # retokenized as 'startup', which the rule below reads as "somebody edited this" -
            # so one launch after a real owner was known, NO doc tracked the template any more.
            # TRIAGE.md on a live install sat at the 2026-08-25 wording while the code went on
            # sending it fields (others_replied) the doc never described. Only that pass writes a
            # non-SOUL doc as 'startup' (docsync writes SOUL.md), so those are untouched by anyone.
            self.cx.execute("UPDATE doc SET UpdatedBy='template' WHERE UpdatedBy='startup' AND Name<>'soul'")
            if self.cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory'").fetchone():   # an older install, not yet drained
                self._heal_notes()
            for name in OWNER_DOCS:
                f = Path(__file__).parent / 'templates' / f'{name}.md'
                if f.exists():
                    txt = f.read_text(encoding='utf-8')
                    self.cx.execute('INSERT OR IGNORE INTO doc (Name, Content, UpdatedBy, UpdatedAt) VALUES (?,?,?,?)',
                                    (name, txt, 'template', _now()))
                    # SOUL is the safety constitution every prompt is stacked on. An old UI/test
                    # path could save it as an empty edited document, which disabled the shipped
                    # boundaries forever because edited docs correctly stop following templates.
                    # Empty carries no owner intent to preserve: restore the complete default, and
                    # let the interview replace it only after the owner actually answers.
                    # ...and not only SOUL: a document went blank on a live install (2026-09-01) and its
                    # reader ran with nothing until somebody looked. Empty is empty.
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedBy='template', UpdatedAt=? "
                                    "WHERE Name=? AND TRIM(IFNULL(Content,''))=''",
                                    (txt, _now(), name))
                    # a doc NOBODY ever touched keeps tracking the shipped template, so template
                    # improvements reach existing installs - the first edit (owner or machine)
                    # changes UpdatedBy and makes the document theirs, never overwritten again
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedAt=? WHERE Name=? AND UpdatedBy='template' AND Content<>?",
                                    (txt, _now(), name, txt))
            # A DOC THE OWNER HAS TOUCHED STOPS TRACKING THE TEMPLATE, which is right - and it means a
            # WRONG shipped rule stays wrong forever on exactly the installs that use the product most.
            # TRIAGE.md told the model "a stranger's pull request or issue is fyi - never task", so every
            # PR on the owner's own repository was filed, and ingest carried a regex gate to override it;
            # the gate named no `kind`, so all twelve went to the assistant instead of the coding agent. The gate
            # is gone and the template says what a PR is - but a doc whose UpdatedBy is anything but
            # 'template' would never see it. One surgical replacement of the sentence that was wrong,
            # whoever owns the document: everything else in it stays exactly as the owner left it.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='triage_pr_rule_fixed'").fetchone():
                row = self.cx.execute("SELECT Content FROM doc WHERE Name='triage'").fetchone()
                body = (row['Content'] or '') if row else ''
                if _PR_RULE_WAS in body:
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedAt=? WHERE Name='triage'",
                                    (body.replace(_PR_RULE_WAS, _PR_RULE_NOW), _now()))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) "
                                "VALUES ('triage_pr_rule_fixed', '1', 'migration')")
            # ...and the same surgery for the CONTRACT LINE, for the same reason: a document the
            # owner or a generator has touched stops tracking the template, and this install's
            # named intent/kind/why, so a model that answered exactly that was obeying it. One
            # sentence replaced, in place; everything else in the document stays as they left it.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='triage_answer_shape_fixed'").fetchone():
                row = self.cx.execute("SELECT Content FROM doc WHERE Name='triage'").fetchone()
                body = (row['Content'] or '') if row else ''
                if _SHAPE_WAS in body:
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedAt=? WHERE Name='triage'",
                                    (body.replace(_SHAPE_WAS, _SHAPE_NOW), _now()))
                    logger.info('triage: the contract line now names title, summary and checklist')
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) "
                                "VALUES ('triage_answer_shape_fixed', '1', 'migration')")
            # ...and the summary inside that line now asks who wants what - same surgery, once
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='triage_summary_who_wants_what'").fetchone():
                row = self.cx.execute("SELECT Content FROM doc WHERE Name='triage'").fetchone()
                body = (row['Content'] or '') if row else ''
                if _SUMMARY_WAS in body:
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedAt=? WHERE Name='triage'",
                                    (body.replace(_SUMMARY_WAS, _SUMMARY_NOW), _now()))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) "
                                "VALUES ('triage_summary_who_wants_what', '1', 'migration')")
            # ...and CODING IS NOT THE DEFAULT any more (the owner, 2026-09-23: "i don't like coding by
            # default"): an Advisor idea about chasing a bank's contact went to the coding agent in a
            # repository that only matched its topic (TQ-0694). The paragraphs that said otherwise are
            # swapped where they still read as shipped - an owner's own rewording of one is theirs.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='triage_coding_not_default'").fetchone():
                row = self.cx.execute("SELECT Content FROM doc WHERE Name='triage'").fetchone()
                body = (row['Content'] or '') if row else ''
                fixed = body
                for was, now in _KIND_RULES: fixed = fixed.replace(was, now)
                if fixed != body:
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedAt=? WHERE Name='triage'", (fixed, _now()))
                    logger.info('triage: coding is no longer the default kind; unsure is a task')
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) "
                                "VALUES ('triage_coding_not_default', '1', 'migration')")
            # ...and READING IS NOT CODING (the owner, 2026-10-05: "data is coding" - a CHANGE): the coding sentence still
            # said "a query against one of their databases, a file or report produced from them", so a request for open AP
            # by vendor went to the coding agent (2026-10-06). Swapped where it still reads as shipped, once.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='triage_reading_not_coding'").fetchone():
                row = self.cx.execute("SELECT Content FROM doc WHERE Name='triage'").fetchone()
                body = (row['Content'] or '') if row else ''
                if _CODING_WAS in body:
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedAt=? WHERE Name='triage'", (body.replace(_CODING_WAS, _CODING_NOW), _now()))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('triage_reading_not_coding', '1', 'migration')")
            # ...and NO REPOSITORY IS ASKED FOR (_REPO_CHOICE_WAS): out of a TRIAGE.md the owner edited where it still reads as shipped,
            # once. One nobody edited follows the guide below, which no longer has it - cut here, it would stop following it
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='triage_no_repo_choice'").fetchone():
                row = self.cx.execute("SELECT Content, UpdatedBy FROM doc WHERE Name='triage'").fetchone()
                body = (row['Content'] or '') if row and row['UpdatedBy'] == 'owner' else ''
                nl = '\r\n' if '\r\n' in body else '\n'
                for was in (_REPO_CHOICE_WAS + nl + nl, _REPO_CHOICE_WAS):
                    if body.count(was) == 1:
                        self.cx.execute("UPDATE doc SET Content=?, UpdatedAt=? WHERE Name='triage'", (body.replace(was, ''), _now())); break
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('triage_no_repo_choice', '1', 'migration')")
            # ...and THE ROUTE ROWS OF BRAINS BUILT AND NEVER CALLED go, once (brainroute.Lazy, 2026-11-06): the chat poll wrote one a second,
            # each 'ok' with no time and no tokens - a call made through the meter always has its time, so these were never calls
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='brainroute_uncalled_swept'").fetchone():
                n = self.cx.execute(f"DELETE FROM brainroute WHERE {UNCALLED_ROUTES}", (_now(),)).rowcount
                if n: logger.info(f'removed {n} AI route rows of brains that were built and never called')
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('brainroute_uncalled_swept', ?, 'migration')", (str(n),))
            # ...and THE GUIDE REPLACES THE PATCHWORK (the owner, 2026-10-09: "make it clear how to triage things, what to
            # look for, signs that would suggest things"). The sentence swaps above each fixed one rule; the template is now
            # one guide written as questions and signs, and the judgement code used to append lives in it. A document only
            # a template, a migration or the history generator ever wrote takes the guide whole, keeping its generated
            # "Learned from your mail history" block; one the owner wrote is theirs and is left as it is.
            # ...and it KEEPS tracking the guide: a generated history block makes the document differ from the template, so
            # the plain "untouched template" rule would freeze it at the first guide. The guide part is updated while it is
            # still exactly the guide last put there (triage_guide_sha); an edit to it, by anyone, ends that.
            row = self.cx.execute("SELECT Content, UpdatedBy FROM doc WHERE Name='triage'").fetchone()
            if row and row['UpdatedBy'] != 'owner':
                from .histgen import HIST_END, HIST_START, TITLES, _splice
                guide = (Path(__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')
                body = row['Content'] or ''
                hist = body.split(HIST_START, 1)[1].split(HIST_END, 1)[0] if HIST_START in body and HIST_END in body else ''
                head = body.split(f'## {TITLES["triage"]}\n{HIST_START}', 1)[0].strip()
                sha = lambda t: hashlib.sha256(t.strip().encode()).hexdigest()
                last = self.cx.execute("SELECT Value FROM setting WHERE Name='triage_guide_sha'").fetchone()
                first = not self.cx.execute("SELECT 1 FROM setting WHERE Name='triage_guide_2026_10_09'").fetchone()
                # ...and a guide the 10-09 migration wrote before the fingerprint was kept: no sha names it, so it froze for
                # good (2026-10-15). Its last writer being the migration itself says nobody edited it since; histgen's name
                # can sit over an owner's edit (it rewrites only the history block), so that one stays as it is.
                tracks = first or (sha(head) == last['Value'] if last else row['UpdatedBy'] in ('migration', 'template'))
                if tracks and sha(head) != sha(guide):
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedBy=?, UpdatedAt=? WHERE Name='triage'",
                                    (_splice(guide, hist, TITLES['triage']) if hist.strip() else guide,
                                     'migration' if hist.strip() else 'template', _now()))
                    logger.info('triage: TRIAGE.md follows the triage guide' + (' (your mail-history section kept)' if hist.strip() else ''))
                    head = guide
                if tracks or sha(head) == sha(guide):
                    self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('triage_guide_sha', ?, 'migration') "
                                    "ON CONFLICT(Name) DO UPDATE SET Value=excluded.Value", (sha(guide),))
            self.cx.execute("INSERT OR IGNORE INTO setting (Name, Value, UpdatedBy) VALUES ('triage_guide_2026_10_09', '1', 'migration')")
            # THE WHATSAPP CATCH-ALL IS GONE, so the row for it goes too. '*' admitted every direct
            # chat on an account that is the owner's own phone; nothing honours it now (messengers
            # .poll_whatsapp skips it, the door refuses a new one), and a dead row with a live-looking
            # switch beside it is worse than the setting was - the owner asked why it was still
            # there, which is the whole problem with leaving it (2026-09-17). Telegram's '*' is a
            # different thing and is left alone: a bot only hears the chats it was added to.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='whatsapp_star_dropped'").fetchone():
                gone = self.cx.execute("DELETE FROM source WHERE Channel='whatsapp' AND Address='*'").rowcount
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) "
                                "VALUES ('whatsapp_star_dropped', '1', 'migration')")
                if gone: logger.info(f'whatsapp: dropped the {gone} catch-all source row - named chats only now')
            # An INVOICE, a REPORT or a proposed SETTING with no task has nowhere left to be
            # answered once the task page is gone; rows filed before add_review asked for one are
            # still sitting in live stores. Each gets the task it should have had, titled with the
            # words it already carries. Scoped to those two kinds on purpose: a task-less `draft` is
            # the answer to filed chatter and is MEANT to stay task-less - it is decided in the
            # assistant, by rid. The id allocation is create_task's own rule - one past the highest
            # ever ISSUED, audit included - so a backfilled TQ-ref can never name existing work.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='review_task_backfilled'").fetchone():
                stranded = self.cx.execute("SELECT ReviewId, Reason FROM review WHERE TaskId IS NULL "
                                           "AND Kind IN ('outbound','action') AND Status IN ('pending','held') ORDER BY ReviewId").fetchall()
                if stranded:
                    mark = self.cx.execute("SELECT Value FROM setting WHERE Name='task_id_mark'").fetchone()
                    nxt = max(self.cx.execute('SELECT MAX(TaskId) m FROM task WHERE TaskId<?', (INTERNAL_TASK_BASE,)).fetchone()['m'] or 0,
                              self.cx.execute("SELECT MAX(EntityId) m FROM audit WHERE EntityType='task' AND EntityId<?",
                                              (INTERNAL_TASK_BASE,)).fetchone()['m'] or 0,
                              int((mark['Value'] if mark else 0) or 0))
                    for rv in stranded:
                        nxt += 1
                        self.cx.execute('INSERT INTO task (TaskId, Title, Kind, Status, Source, CreatedBy, CreatedAt) VALUES (?,?,?,?,?,?,?)',
                                        (nxt, str(rv['Reason'] or 'Waiting on you')[:140], 'task', 'open', 'review', 'migration', _now()))
                        self.cx.execute('UPDATE review SET TaskId=? WHERE ReviewId=?', (nxt, rv['ReviewId']))
                    self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('task_id_mark', ?, 'migration') "
                                    "ON CONFLICT(Name) DO UPDATE SET Value=excluded.Value", (str(nxt),))
                    logger.info(f'review: {len(stranded)} decision(s) with no task now have one')
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) "
                                "VALUES ('review_task_backfilled', '1', 'migration')")
            self._heal_seeded_report_owner()
            # AUTOMATION IDEAS IS GONE, from older installs too (the owner, 2026-09-29: "delete it for everyone"). Keeping
            # it made two voices raise the same month of toil - the Advisor and this. Once, after the heal above has put
            # Owner='template' back on the seeded row: only that row goes, edited or not; one the owner made stays theirs.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='automate_report_removed'").fetchone():
                gone = [r['SourceId'] for r in self.cx.execute(
                    "SELECT SourceId, ConfigJson FROM source WHERE Channel='report' AND Owner='template'").fetchall()
                    if _cfg_type(r['ConfigJson']) == 'automate']
                for sid in gone: self.cx.execute('DELETE FROM source WHERE SourceId=?', (sid,))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('automate_report_removed', '1', 'migration')")
                if gone: logger.info(f'sources: removed the retired Automation ideas report - SourceId {gone}')
            # THE ADVISOR, by its new name. The seeded review-and-ideas report was called 'Assistant',
            # which is also the tab that walks you through the day (2026-09-23). Renamed once, and only
            # while it still wears the seeded name - a title the owner chose is theirs. Found the way
            # assistant.seeded_source finds it (Owner='template', type 'assistant'); every internal key
            # (the `assistant` thread, its notes, its idea keys) stays exactly as it is.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='assistant_report_renamed_advisor'").fetchone():
                for r in self.cx.execute("SELECT SourceId, Address, ConfigJson FROM source WHERE Channel='report' AND Owner='template'").fetchall():
                    try: c = json.loads(r['ConfigJson'] or '{}')
                    except ValueError: continue
                    if c.get('type') != 'assistant' or r['Address'] != 'Assistant' or c.get('title', 'Assistant') != 'Assistant': continue
                    c['title'] = 'Advisor'
                    self.cx.execute("UPDATE source SET Address='Advisor', ConfigJson=? WHERE SourceId=?", (json.dumps(c), r['SourceId']))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('assistant_report_renamed_advisor', '1', 'migration')")
            # The Morning digest and Automation ideas are no longer seeded (RETIRED_SEEDS): the walk opens the day
            # with who wants what, and the Advisor reads the month of counts once a week. An install that has a Morning
            # digest keeps it until its owner deletes it; its Automation ideas is removed (just above). Both report types
            # still exist to make one by hand.
            # ...and the Assistant (assistant.py): its post on the Timeline is scheduled and worded HERE
            # too - twice a day, at the start and the end of the working day (assistant.TWICE_A_DAY; a look missed while the app was
            # shut runs once when it opens, reports.is_due), the instruction editable, deleting the row is the off switch. These two are
            # the working demo of both kinds of report: the digest is an AI pass over the hub's own data, the assistant a voice.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='assistant_report_seeded'").fetchone():
                from .assistant import PROMPT as ASSISTANT_PROMPT, TWICE_A_DAY
                self.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                                ('report', 'Advisor', 'template', 1,
                                 json.dumps({'type': 'assistant', 'title': 'Advisor', 'cron': TWICE_A_DAY, 'ai_prompt': ASSISTANT_PROMPT})))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('assistant_report_seeded', '1', 'template')")
            # The close of the day deserves a different lens from the Morning digest: eight
            # rolling hours of whatever is connected and the owner's own work (evening.py),
            # accomplishments first and tomorrow's top three second. It waits for its 6 pm local
            # slot instead of greeting a morning startup.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='evening_inbox_report_seeded'").fetchone():
                from .evening import PROMPT as EVENING_PROMPT
                self.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                                ('report', 'End of day checkup', 'template', 1,
                                 json.dumps({'type': 'evening_inbox', 'title': 'End of day checkup', 'hours': 8,
                                             'daily_at': '18:00', 'once_per_day': True,
                                             'first_run_at_schedule': True, 'ai_prompt': EVENING_PROMPT})))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('evening_inbox_report_seeded', '1', 'template')")
            # ...and its dashboard twin (the owner, 2026-10-23: "like we have end of day report as template let's do the same for
            # dashboard"): Taskuary at a glance, drawn from the app's own tables, so it needs nothing connected. A daily_at with no
            # run yet is due at once (reports.is_due), so the first sync fills it; deleting the row is the off switch, as above.
            # ...and an install that already made one from New dashboard's template keeps that one: it becomes the default, not a twin
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='glance_dashboard_seeded'").fetchone():
                from .dashboards import GLANCE
                had = self.cx.execute("SELECT 1 FROM source WHERE Channel='report' AND Address=? AND ConfigJson LIKE '%\"dashboard\"%'",
                                      (GLANCE['title'],)).fetchone()
                if not had: self.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                                            ('report', GLANCE['title'], 'template', 1, json.dumps(GLANCE)))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('glance_dashboard_seeded', '1', 'template')")
            # prompt heal: a Morning digest still running a SHIPPED instruction tracks the
            # current one (same deal the template docs get) - an owner-edited prompt is never touched
            from .digest import OLD_PROMPTS, PROMPT as DIGEST_PROMPT
            from .assistant import OLD_PROMPT_HEADS, OLD_PROMPT_SHA, PROMPT as ASSISTANT_PROMPT
            from .toil import OLD_PROMPTS as AUTOMATE_OLD, PROMPT as AUTOMATE_PROMPT
            from .evening import OLD_PROMPTS as EVENING_OLD, PROMPT as EVENING_NOW
            for sid_, cj in self.cx.execute("SELECT SourceId, ConfigJson FROM source WHERE Channel='report'").fetchall():
                try: c = json.loads(cj or '{}')
                except ValueError: continue
                # the stock Advisor on a shipped prompt, unedited, takes the current one (an owner-edited prompt is kept); its clock is
                # the move below's, once - healing it here on every launch put back a cadence the owner had changed
                if c.get('type') == 'assistant' and (str(c.get('ai_prompt') or '').startswith(OLD_PROMPT_HEADS)
                                                     or hashlib.sha256(str(c.get('ai_prompt') or '').encode()).hexdigest() in OLD_PROMPT_SHA):
                    c['ai_prompt'] = ASSISTANT_PROMPT
                    self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), sid_))
                # the stock Automation ideas on a shipped prompt that still advised an auto-answer takes today's (2026-10-25)
                if c.get('type') == 'automate' and c.get('ai_prompt') in AUTOMATE_OLD:
                    c['ai_prompt'] = AUTOMATE_PROMPT
                    self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), sid_))
                # the stock Automation ideas was seeded on Mondays only; unedited, it also greets
                # a launch - at most once a week (an owner-set cadence is kept as it is)
                if c.get('type') == 'automate' and c.get('ai_prompt') == AUTOMATE_PROMPT and c.get('cron') == '0 8 * * 1':
                    if not c.get('on_startup'):
                        c['on_startup'], c['once_per_week'] = True, True
                        self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), sid_))
                # only a digest still on an OLD stock prompt: one already healed is the owner's to reschedule,
                # and healing it on every launch put back an 08:00 they had taken off (2026-09-27)
                # the stock evening checkup, unedited, takes the current instruction (an owner-edited one is kept)
                if c.get('type') == 'evening_inbox' and c.get('ai_prompt') in EVENING_OLD:
                    c['ai_prompt'] = EVENING_NOW
                    self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), sid_))
                if c.get('type') == 'digest' and c.get('ai_prompt') in OLD_PROMPTS:
                    c['ai_prompt'] = DIGEST_PROMPT
                    # a stock digest on the old default clock (none, or the three-hourly one) becomes the
                    # 8 am brief that also runs on startup; an owner-set cadence is kept
                    stock_clock = not any(c.get(k) for k in ('cron', 'every_minutes', 'daily_at')) or (c.get('every_minutes') == 180 and not c.get('cron') and not c.get('daily_at'))
                    if stock_clock: c.pop('every_minutes', None); c['daily_at'] = '08:00'; c['on_startup'] = True
                    # ...and a brief is once a day: on_startup alone re-filed it on every launch
                    if c.get('on_startup'): c['once_per_day'] = True
                    self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), sid_))
            # THE ADVISOR TWICE A DAY, once (the owner, 2026-11-12: "run the advisor twice a day in AM and PM"): the seeded row still on the
            # clock it shipped with - every 30 (once 20, once 60) minutes, with or without app start - moves to assistant.TWICE_A_DAY. Any
            # other clock is one the owner set, and is kept and named in the log.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='advisor_twice_a_day'").fetchone():
                from .assistant import OLD_EVERY, TWICE_A_DAY
                for r in self.cx.execute("SELECT SourceId, Owner, ConfigJson FROM source WHERE Channel='report'").fetchall():
                    try: c = json.loads(r['ConfigJson'] or '{}')
                    except ValueError: continue
                    if c.get('type') != 'assistant': continue
                    if r['Owner'] == 'template' and not (c.get('cron') or c.get('daily_at')) and str(c.get('every_minutes')) in map(str, OLD_EVERY):
                        for k in ('every_minutes', 'on_startup', 'once_per_day'): c.pop(k, None)
                        self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c | {'cron': TWICE_A_DAY}), r['SourceId']))
                        logger.info(f"reports: the Advisor (SourceId {r['SourceId']}) runs twice a day now - {TWICE_A_DAY}")
                    elif c.get('cron') != TWICE_A_DAY: logger.info(f"reports: {c.get('title') or 'an Advisor report'} (SourceId {r['SourceId']}) keeps the clock it was given - "
                                      f"{ {k: c[k] for k in ('cron', 'daily_at', 'every_minutes', 'on_startup') if c.get(k)} or 'none'}")
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('advisor_twice_a_day', '1', 'migration')")
            # THE TRIAGE LINE, once (the owner, 2026-10-16: "most reports should not go through triage"): every report triaged
            # every run before it existed, so each is given the line its own behaviour already says - a monitor keeps its condition,
            # a digest never (reports.triage_from). BEFORE the card pass below, which would write the default `never` into all of them
            from .reports import from_old_rules, triage_from
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='report_triage_line_set'").fetchone():
                for sid_, cj in self.cx.execute("SELECT SourceId, ConfigJson FROM source WHERE Channel='report'").fetchall():
                    try: c = json.loads(cj or '{}')
                    except ValueError: continue
                    card = c if c.get('route') else from_old_rules(c)
                    if 'triage' in (card.get('route') or {}): continue
                    card = {**card, 'route': {**card['route'], 'triage': triage_from(card)}}
                    self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(card), sid_))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('report_triage_line_set', '1', 'migration')")
            # ONE RULE SET for where a run goes (the owner, 2026-09-27): a report saved before the route
            # card is written down as the card, meaning exactly what it did - reports.from_old_rules
            for sid_, cj in self.cx.execute("SELECT SourceId, ConfigJson FROM source WHERE Channel='report'").fetchall():
                try: c = json.loads(cj or '{}')
                except ValueError: continue
                if (n := from_old_rules(c)) != c: self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(n), sid_))
            # data heal: 'triage' was a fourth Kind the pickers never offered, so those tasks
            # showed a kind the dropdown could not represent - and every one of them had a
            # coding agent dispatched at it, because the gate was "not a reply" and not the
            # kind itself. They are plain tasks on the owner's list: 'general'.
            self.cx.execute("UPDATE task SET Kind='general' WHERE Kind='triage'")
            # data heal: timestamps stored as raw ISO/UTC ('...T18:44:00Z') sorted above later
            # local rows and lied about the hour - normalize the survivors once
            for mid, sent in self.cx.execute("SELECT MessageId, SentAt FROM message WHERE SentAt LIKE '%T%'").fetchall():
                self.cx.execute('UPDATE message SET SentAt=? WHERE MessageId=?', (norm_stamp(sent), mid))
            # data heal: sources written before ownership existed have no ConnectorId, so a
            # NEW connector on the same channel (the Gmail card) claimed the Outlook mailboxes.
            # Adopt each orphan to the channel's legacy owner - Graph was the only email/teams/
            # slack road back then, so the attribution is certain. Reports keep their own rules.
            for ch, typ in (('email', 'outlook'), ('teams', 'teams'), ('slack', 'slack'), ('github', 'github')):
                self.cx.execute('''UPDATE source SET ConnectorId =
                                     (SELECT ConnectorId FROM connector WHERE Type = ?)
                                   WHERE Channel = ? AND ConnectorId IS NULL''', (typ, ch))
            # data heal: dbs written before review dedupe can hold stacked pending reviews
            # of the same kind on one task - keep the newest, supersede the rest. NOT a task's emails (slots.py): several
            # pending at once is what they are, and every start retired all but the newest (TQ-0957, 2026-10-05). Nor a reply to
            # ANOTHER PERSON on the same task: an agent's reply to one requester and one to a second are two letters (2026-11-02). Nor
            # a task's PROPOSALS: one turn's two held pushes are two steps of one act, and every open of the store retired all but the last
            # (2026-11-09, the one-card walk: the merge vanished, its push stood alone)
            self.cx.execute("""UPDATE review SET Status='superseded'
                               WHERE Status='pending' AND Kind NOT IN ('slot','action') AND ReviewId NOT IN (
                                   SELECT MAX(rv.ReviewId) FROM review rv LEFT JOIN message m ON m.MessageId=rv.MessageId
                                   WHERE rv.Status='pending'
                                   GROUP BY rv.TaskId, rv.Kind, lower(IFNULL(m.FromEmail, IFNULL(m.FromName, ''))))""")
            # ...and the email drafts it wrongly retired come back: superseded with nobody deciding, on a task still open,
            # whose email is still owed (its slot names this draft and is not done)
            for r in self.cx.execute("""SELECT rv.ReviewId, t.Checklist FROM review rv JOIN task t ON t.TaskId=rv.TaskId
                                         WHERE rv.Kind='slot' AND rv.Status='superseded' AND rv.DecidedBy IS NULL
                                         AND t.Status NOT IN ('done','dropped')""").fetchall():
                try: owed = any(isinstance(i, dict) and i.get('rid') == r[0] and not i.get('done') for i in json.loads(r[1] or '[]'))
                except (TypeError, ValueError): owed = False
                if owed: self.cx.execute("UPDATE review SET Status='pending' WHERE ReviewId=?", (r[0],))
            # escalation reviews are gone: they only ever came from the headless report contract
            # ('needs_you'), and a live session asks you IN the terminal. Old pending ones would
            # render as a reply draft with nothing to send, so they resolve on first open - the
            # task keeps its 'waiting' status, so nothing quietly stops needing you.
            self.cx.execute("UPDATE review SET Status='superseded' WHERE Status='pending' AND Kind='escalation'")
            self.cx.commit()

        self.recover_review_deliveries()

    def _heal_seeded_report_owner(self):
        """OWNERSHIP HEAL. `POST /api/sources` used to stamp Owner on every save, and Owner is in
        SOURCE_COLS, so one press of Save - or of the on/off Switch, which posts
        {SourceId, Active} - rewrote a seeded row's 'template' to the actor. The route sets
        Owner on CREATE only now, but installs carry the damage: on the owner's own box three
        of the four seeded reports had already lost it, the Assistant among them. Owner is how
        assistant.seeded_source tells the app's own Assistant from one the owner made, so
        unhealed, both would read as the app's and would share the `assistant` Timeline thread
        and its idea namespace.

        IDEA KEYS ARE LEFT ALONE, deliberately and for ever: a report that has been posting as
        its own has `report:<id>:...` keys with state on them (declined, snoozed, said), and
        rewriting them would strand every one. Do not "finish" this by renaming them.

        Its own method (not inline in __init__) so a test can run it again against a live
        store - reopening a :memory: store would just hand back an empty one."""
        if self.cx.execute("SELECT 1 FROM setting WHERE Name='seeded_report_owner_healed'").fetchone(): return
        healed = []
        for sentinel, address, kind in SEEDED_REPORTS + RETIRED_SEEDS:
            if not self.cx.execute('SELECT 1 FROM setting WHERE Name=?', (sentinel,)).fetchone(): continue
            # The name the seeder gave it, and the type it seeded, LOWEST id first. Address
            # follows the title (ReportsView posts Address: c.title), so a renamed row is
            # indistinguishable from one the owner made - and a migration that cannot be
            # sure does nothing. The seeded row is the oldest of its type either way: it is
            # written at first run, before the owner can create anything.
            rows = [r for r in self.cx.execute(
                'SELECT SourceId, Owner, ConfigJson FROM source WHERE Channel=? AND Address=? ORDER BY SourceId', ('report', address)).fetchall()
                if (json.loads(r['ConfigJson'] or '{}') or {}).get('type') == kind]
            if not rows: continue                           # deleted (the off switch) or renamed: nothing to heal
            row = rows[0]
            if row['Owner'] == 'template': continue         # intact - never rewritten, never touched
            self.cx.execute("UPDATE source SET Owner='template' WHERE SourceId=?", (row['SourceId'],))
            healed.append(row['SourceId'])
        self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('seeded_report_owner_healed', '1', 'migration')")
        if healed: logger.info(f'sources: restored Owner=template on the seeded report row(s) an old save had taken over - SourceId {healed} '
                               '(idea keys deliberately untouched)')

    @contextlib.contextmanager
    def reads_off_writer(self):
        "This thread's plain SELECTs go to a reader connection until the block ends (see _OFF_WRITER). Re-entrant."
        was = getattr(_OFF_WRITER, 'on', False); _OFF_WRITER.on = True
        try: yield
        finally: _OFF_WRITER.on = was
    @contextlib.contextmanager
    def _writer_reads(self):
        "This thread's _processing_read() stays on the writer connection until the block ends. Re-entrant."
        was = getattr(_ON_WRITER, 'on', False); _ON_WRITER.on = True
        try: yield
        finally: _ON_WRITER.on = was
    def _off_writer(self) -> bool:
        """May this thread read on a reader connection? Not on a memory database (there is no second one), not from inside
        the writer's lock (its own open transaction must be read back), and not while a transaction sits open on the writer
        with nobody holding the lock - a failed write left it (see _undone) and the writer is where it can be seen."""
        return self._rail_cx is not None and not self.lock._is_owned() and not (self.cx.in_transaction and not self.lock._depth)
    @contextlib.contextmanager
    def pinned_read(self):
        """ONE VIEW, READ OFF THE WRITER (the load run, 2026-11-24: a 2,000-line chat polled once a second held the writer's lock 243 s in
        13 min, every triage write and press queued behind it): this thread's plain reads till the block ends share one reader snapshot -
        begun under the writer's lock, so it is never the middle of a write made in steps under it (take_kept: his line heard, then taken
        off the box), and read after the lock is let go. A memory database, or a thread inside the lock, reads under the lock as before."""
        if (getattr(_PINNED, 'at', None) or (None,))[0] is self: yield; return
        if not self._off_writer():
            with self.lock: yield
            return
        with self._snapshot_read() as cur:
            with self.lock: cur.execute('SELECT COUNT(*) FROM chatlog_task').fetchone()      # ...the snapshot is taken by its first read
            was, _PINNED.at = getattr(_PINNED, 'at', None), (self, cur)
            try: yield
            finally: _PINNED.at = was
    def _rows(self, q, p=()):
        if (pin := getattr(_PINNED, 'at', None)) and pin[0] is self and q.lstrip()[:6].upper() == 'SELECT' and not self.lock._is_owned():
            return [dict(r) for r in pin[1].execute(q, p).fetchall()]
        if q.lstrip()[:6].upper() == 'SELECT' and self._off_writer():
            with self._snapshot_read() as cur: return [dict(r) for r in cur.execute(q, p).fetchall()]
        with self.lock: return [dict(r) for r in self.cx.execute(q, p).fetchall()]
    def _one(self, q, p=()):
        r = self._rows(q, p); return r[0] if r else None
    def _exec(self, q, p=()):
        with self.lock, self._undone():
            cur = self.cx.execute(q, p); self.cx.commit(); self._writes += 1
        # EVERY WRITER OF A HELD SETTING OR DOCUMENT, ONE ROAD (robustness review, 2026-11-18): this thread's hold (held_settings) lets go
        # once the write is in - a writer that dropped its own key first and then read the old value back (save_doc's line diff) held it
        # stale, and one that wrote the table directly dropped nothing
        if (held := getattr(_HELD, 'settings', None)) is not None and held[0] is self and _HELD_TABLES.match(q): held[1].clear()
        return cur.lastrowid
    # A WRITE THAT FAILS LEAVES NOTHING OPEN (2026-10-26): another process held the database 5s, one INSERT met "database is
    # locked", and the transaction sqlite3 had opened for it stayed open on the writer - every BEGIN IMMEDIATE after it failed
    # with "cannot start a transaction within a transaction" until a restart, the rail's reads with them, and Next said "still
    # refreshing" over and over. A failed bare write rolls back; a BEGIN first drops one a failed write left behind.
    @contextlib.contextmanager
    def _undone(self):
        try: yield
        except BaseException:
            if self.cx.in_transaction: self.cx.rollback()
            raise
    def _clear_stale(self):
        if self.cx.in_transaction:
            logger.warning('store: a failed write had left a transaction open - rolled back before BEGIN'); self.cx.rollback()
    def _patch_poll_state(self, table, row_id, *, config_set=None, config_remove=(),
                          expect_fields=None, expect_config=None, last_polled_at=_POLL_UNSET):
        """Merge poll metadata into the latest config under a SQLite write transaction.

        Expectations compare only supplied keys; expected config None accepts either a
        missing key or JSON null. An omitted last_polled_at leaves it alone, while explicit
        None clears it. Missing rows and stale expectations return False without writes.
        Invalid/non-object JSON raises, preserving the owner's original configuration.
        """
        key = {'source': 'SourceId', 'connector': 'ConnectorId'}[table]
        updates = copy.deepcopy({} if config_set is None else config_set)
        removed = tuple(config_remove)
        fields = copy.deepcopy({} if expect_fields is None else expect_fields)
        expected = copy.deepcopy({} if expect_config is None else expect_config)
        if not isinstance(updates, dict) or not isinstance(fields, dict) or not isinstance(expected, dict):
            raise TypeError('poll checkpoint patches and expectations must be dictionaries')
        if any(not isinstance(k, str) for k in (*updates, *removed, *fields, *expected)):
            raise TypeError('poll checkpoint keys must be strings')
        if set(updates).intersection(removed):
            raise ValueError('a poll checkpoint cannot set and remove the same config key')
        with self.lock:
            self._clear_stale(); self.cx.execute('BEGIN IMMEDIATE')
            try:
                found = self.cx.execute(f'SELECT * FROM {table} WHERE {key}=?', (row_id,)).fetchone()
                if found is None:
                    self.cx.rollback()
                    return False
                row = dict(found)
                if any(k not in row for k in fields):
                    raise ValueError('unknown poll checkpoint row expectation')
                current = json.loads(row['ConfigJson']) if row.get('ConfigJson') else {}
                if not isinstance(current, dict):
                    raise ValueError('poll checkpoint requires an object ConfigJson')
                # a caller holds the secret OPENED (get_connector with_secret); the column holds it sealed (vault.py)
                if (any((vault.unseal(row[k]) if k == 'Secret' else row[k]) != value for k, value in fields.items()) or
                        any(current.get(k) != value for k, value in expected.items())):
                    self.cx.rollback()
                    return False
                current.update(updates)
                for name in removed: current.pop(name, None)
                values, assignments = [json.dumps(current)], ['ConfigJson=?']
                if last_polled_at is not _POLL_UNSET:
                    if table != 'source': raise ValueError('only sources have LastPolledAt')
                    values.append(last_polled_at)
                    assignments.append('LastPolledAt=?')
                self.cx.execute(f"UPDATE {table} SET {','.join(assignments)} WHERE {key}=?",
                                [*values, row_id])
                self.cx.commit()
                self._writes += 1
                # Watermarks and poll checkpoints do not participate in a processing item.
                # A successful no-op sync can update many of them; counting those writes as
                # Timeline content changes makes the next read rebuild the entire projection.
                self._processing_ignored_writes += 1
                return True
            except BaseException:
                self.cx.rollback()
                raise
    def _insert(self, table, fields, allowed, extra=None):
        d = {k: fields[k] for k in allowed if k in fields and fields[k] is not None} | (extra or {})
        cols = list(d)
        return self._exec(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
                          [d[c] for c in cols])
    @contextlib.contextmanager
    def one_poke(self):
        """Hold the UI wake-ups of a batch and send them ONCE at the end.

        A settle pokes `feed-changed`, which empties the pile cache and wakes every open tab - and
        a handful of fyi settled together did that four times over, so four forced rebuilds of a
        60-item pile raced each other while the owner waited on the Next behind them (2026-09-14:
        "all read, next on fyi takes 2/3 seconds"). The writes still land one at a time; only the
        shouting is coalesced. Re-entrant, and it fires even if the body raises - a caller that
        failed half way through has still changed what the tabs are looking at.
        """
        if getattr(self, '_poke_held', None) is not None:      # already inside one: the outer owns it
            yield
            return
        self._poke_held, held = {}, None
        try:
            yield
        finally:
            held, self._poke_held = self._poke_held, None
            for kinds, payload in held.values(): self._poke(*kinds, **payload)

    def _poke(self, *kinds, **payload):
        """Wake the UI. A write that does not change what a tab is looking at stays quiet."""
        held = getattr(self, '_poke_held', None)
        # STAMPED WHERE THE WRITE IS POKED (live.stamp), a held batch's too: its rail, read later in the same batch, has seen it. A write
        # still inside a transaction is not stamped - a read begun now would not see it - and an unstamped wake-up is always read again.
        # `by`: the tab whose request this is (live.TAB) - a burst only that page's presses made waits for their answers (AssistantView)
        if 'seq' not in payload and any(k in ('feed-changed', 'task-changed') for k in kinds):
            from . import live
            payload['seq'] = None if self.cx.in_transaction else live.stamp()
            tab = live.TAB.get()
            if tab: payload['by'] = tab
        if held is not None:
            key = (kinds, json.dumps({k: v for k, v in payload.items() if k != 'seq'}, sort_keys=True, default=str))
            if key in held and 'seq' in payload:
                was = held[key][1].get('seq')
                payload['seq'] = None if was is None or payload['seq'] is None else max(was, payload['seq'])
            # Keyed by content so a batch shouts once per distinct wake-up - as a canonical
            # string, because a payload can nest: the ingest-status poke carries a dict, and
            # tuple(sorted(items)) made that dict a dict KEY. `_poke_held` is one attribute on
            # the shared store, so the poke that hit it came from ANOTHER thread's batch - the
            # chat lane, mid-poll, inside a settle's one_poke() - and died with
            # "unhashable type: 'dict'" before reading WhatsApp or Telegram (2026-09-16/17).
            held[key] = (kinds, payload)
            return
        try:
            # The Assistant pile is expensive to assemble, so its normal reads use a long cache.
            # Any durable feed/task change invalidates that cache before the websocket wakes the
            # views: new provider messages stay immediate without every open tab rebuilding it.
            if any(k in ('feed-changed', 'task-changed') for k in kinds):
                from . import funnel
                funnel.invalidate()
            from . import live
            for k in kinds: live.emit(k, **payload)
            # an ask the owner made is checked when its task moves (asks.py) - a no-op until the watcher runs
            if 'task-changed' in kinds and payload.get('task_id'):
                from . import asks
                asks.notice(self, payload['task_id'])
        except Exception:
            pass

    # tasks
    def create_task(self, fields, actor, numbered=True):
        # TaskId is a rowid, and SQLite hands a DELETED one straight back to the next insert.
        # TQ-0034 was three different tasks in one morning: a refund thread at 08:19 (with a
        # live agent on it), deleted at 10:11, the id reused twice more by lunchtime - and the
        # orphaned session, still holding task_id 34, showed up as the agent working a report
        # it had never been given. A TQ-ref is an identity: it goes in prompts, in transcripts,
        # in pull requests. It must never name two different pieces of work.
        # ...and it must be issued ONCE: the allocation is three reads and a write, each taking the
        # statement lock on its own, so a poll and a click creating tasks together computed the same
        # id and one of them hit the primary key (audit 2026-09-02)
        # one of the three priorities, whatever word the caller used (processing_order.level, 2026-10-25) - regular when it gave none
        from .processing_order import level
        fields = {**_shown_title(fields), 'Priority': level(fields.get('Priority')), **({'Files': files_json(fields['Files'])} if 'Files' in fields else {})}
        with self.idlock:
            tid = self._insert('task', {**fields, 'TaskId': self._next_task_id() if numbered else self._next_internal_id()},
                                TASK_COLS + ('TaskId',), {'CreatedBy': actor, 'CreatedAt': _now()})
        # ...his ask on the record (ledger.his_line): the files New attached to it, the addresses he gave in it
        if fields.get('Files') or (fields.get('OriginBase') == 'owner' and '@' in str(fields.get('Summary') or '')):
            from . import ledger
            ledger.his_line(self, tid, fields.get('Summary') if fields.get('OriginBase') == 'owner' else '', files_of(fields))
        self._bump_snapshots()
        self._poke('task-changed', task_id=tid)
        return tid

    def migrate_priorities(self) -> dict:
        """THE OLD FOUR AS THE NEW THREE, once (the owner, 2026-10-25): normal is regular and high is important - renames, one word for
        one word - and low is regular too. Low is the one word that merges with another, so each task it changes keeps an audit row
        with the word it had ('priority_renamed'): nothing is lost. A DueRaised the due day saved is read the same way. Returns what
        changed; {} when there was nothing left to do."""
        from .processing_order import LEGACY
        out = {}
        for old, new in LEGACY.items():
            rows = self._rows('SELECT TaskId FROM task WHERE lower(IFNULL(Priority,\'\'))=?', (old,))
            if not rows: continue
            if old == 'low':
                for r in rows: self.audit('task', r['TaskId'], 'priority_renamed', 'migrate', 'system', {'from': old, 'to': new})
            self._exec('UPDATE task SET Priority=? WHERE lower(IFNULL(Priority,\'\'))=?', (new, old))
            out[old] = len(rows)
        for old, new in LEGACY.items(): self._exec('UPDATE task SET DueRaised=? WHERE lower(IFNULL(DueRaised,\'\'))=?', (new, old))
        self._exec("UPDATE task SET Priority='regular' WHERE IFNULL(Priority,'')=''")
        if out: self._bump_snapshots()
        return out

    def scrub_titles(self) -> int:
        "A title kept from before titles were scrubbed (_shown_title), without its password: how many changed."
        from .redact import shown
        rows = [(t, r['TaskId']) for r in self._rows('SELECT TaskId, Title FROM task') if (t := shown(r['Title'])) != (r['Title'] or '')]
        for t, tid in rows: self._exec('UPDATE task SET Title=? WHERE TaskId=?', (t, tid))
        if rows: self._bump_snapshots()
        return len(rows)

    def _next_internal_id(self) -> int:
        """The same never-reused rule, in the range no TQ number reaches (INTERNAL_TASK_BASE)."""
        live = self._one('SELECT MAX(TaskId) m FROM task WHERE TaskId>=?', (INTERNAL_TASK_BASE,))['m'] or 0
        ever = self._one("SELECT MAX(EntityId) m FROM audit WHERE EntityType='task' AND EntityId>=?", (INTERNAL_TASK_BASE,))['m'] or 0
        return max(live, ever, INTERNAL_TASK_BASE) + 1

    def _next_task_id(self) -> int:
        """One past the highest id ever ISSUED - not the highest still present. The audit log
        is the record of what was issued (its rows outlive the task, by design), so the two
        together survive a deleted tail that the table alone forgets."""
        live = self._one('SELECT MAX(TaskId) m FROM task WHERE TaskId<?', (INTERNAL_TASK_BASE,))['m'] or 0
        ever = self._one("SELECT MAX(EntityId) m FROM audit WHERE EntityType='task' AND EntityId<?", (INTERNAL_TASK_BASE,))['m'] or 0
        mark = int(self.get_setting('task_id_mark') or 0)
        nxt = max(live, ever, mark) + 1
        self._exec('INSERT INTO setting (Name, Value, UpdatedBy) VALUES (?,?,?) '
                   'ON CONFLICT(Name) DO UPDATE SET Value=excluded.Value', ('task_id_mark', str(nxt), 'store'))
        return nxt
    def update_task(self, task_id, fields, actor):
        fields = _shown_title(fields)
        if 'Priority' in fields:
            from .processing_order import level
            fields = {**fields, 'Priority': level(fields['Priority'])}
        if 'Files' in fields and not isinstance(fields['Files'], (str, type(None))): fields = {**fields, 'Files': files_json(fields['Files'])}
        cols = [c for c in TASK_COLS if c in fields]
        if not cols: return
        was_row = (self._one('SELECT Status, Assignee, DueAt, Tags FROM task WHERE TaskId=?', (task_id,)) or {}) if 'Status' in fields else {}
        was = was_row.get('Status')
        # ClosedAt describes the CURRENT lifecycle, not merely that the task was closed once.
        # An explicit reopen used to change Status while retaining the old close timestamp, so
        # the API simultaneously said "waiting" and "closed" and different views chose a
        # different truth. A write that does not touch Status leaves the timestamp alone.
        closed = (", ClosedAt='" + _now() + "'" if fields.get('Status') in ('done', 'dropped')
                  else ', ClosedAt=NULL' if 'Status' in fields else '')
        # a priority anybody sets is theirs: the due day's raise is no longer the assistant's to put back (remind.set_due, B18)
        raised = ', DueRaised=NULL' if 'Priority' in fields else ''
        self._exec(f"UPDATE task SET {','.join(f'{c}=?' for c in cols)}, UpdatedBy=?, UpdatedAt=?{closed}{raised} WHERE TaskId=?",
                   [fields[c] for c in cols] + [actor, _now(), task_id])
        # closing a task IS the decision: its pending reviews (escalations, drafts) resolve
        # with it instead of haunting the review queue for a task that's already handled
        if fields.get('Status') in ('done', 'dropped'):
            # a closed task waits on nobody: their later line is judged as any line on a closed thread (ingest._reopen)
            # ...and a closed task is watched by nobody (watch.py): Mark done ends a watch like any task
            # ...and checked back on by nobody: a check-back is the agent's, and a closed task has none at work (checkback.py)
            self._exec('UPDATE task SET WaitingOn=NULL, WatchedAt=NULL, WatchBack=NULL WHERE TaskId=?', (task_id,))
            # ...BUT A CHECK-BACK OUTLIVES MARK DONE (the owner, 2026-11-20): "Checks back Sat 8 AM" was cancelled by the close it promised to
            # come back after - at its time the agent checks, and the task comes back with what it found (checkback.due). Let it go ends it
            if fields.get('Status') == 'dropped': self._exec('UPDATE task SET CheckBackAt=NULL, CheckBackWhat=NULL WHERE TaskId=?', (task_id,))
            live = [r['ReviewId'] for r in self._rows("SELECT ReviewId FROM review WHERE TaskId=? AND Status='pending'", (task_id,))]
            self._exec("UPDATE review SET Status='superseded', DecidedBy=?, DecidedAt=? "
                       "WHERE TaskId=? AND Status='pending'", (actor, _now(), task_id))
            for rid in live: self._review_changed(rid)          # ...each card's state, said where every card's is (events.card)
            # ...and so does the Advisor idea the task was MADE from: left open, 96 ideas outlived their closed tasks
            # (2026-10-10). Only SourceRef - an idea that merely cites a task may name a separate follow-up.
            self._exec("UPDATE idea SET Status='done', DecidedBy='task', DecidedAt=? WHERE Status IN ('open','snoozed') AND "
                       "IdeaId IN (SELECT CAST(substr(SourceRef,16) AS INTEGER) FROM task WHERE TaskId=? AND SourceRef LIKE 'assistant:idea:%')",
                       (_now(), task_id))
        # ...and Done is the whole job. An agent finished TQ-0646 with `--done` and the card kept three
        # open boxes, as if the work were still owed (the owner, 2026-09-18: "part of --done should be
        # that, no? same if it's saved manually"). Dropped leaves them: nothing was done.
        if fields.get('Status') == 'done':
            # ...a batch's items with it: Done on the batch is the owner settling every line still open
            self._exec("UPDATE batch_item SET State='done', UpdatedAt=? WHERE TaskId=? AND State NOT IN ('done','ended')", (_now(), task_id))
            items = self.task_checklist(task_id)
            if any(not i.get('done') for i in items):
                self._exec('UPDATE task SET Checklist=? WHERE TaskId=?', (json.dumps([{**i, 'done': True} for i in items]), task_id))
            self._tick_parent_step(task_id, actor)
        # THE LEDGER'S ONE CLOSE DOOR (outcomes.py): every road that closes a live task - Done, a batch, the chat, a self-close, a
        # pull request's end - passes here, so the "did it stay closed?" row is written once, from the same place. A write that
        # leaves the task waiting (a self-close that drafted a reply) is not a close and gets no row; a delivered promise is
        # already its own row (promise.made) and the actor says so.
        # ...and every road that opens a closed one again says so (Close out starts a new round there) - 'reopened', not new mail's own
        # 'reopen' (ingest._reopen), which is the rail's arrival clock (processing_unread.came_back): a Reopen press is not an arrival
        if 'Status' in fields and was in ('done', 'dropped') and fields['Status'] not in ('done', 'dropped'):
            self.audit('task', task_id, 'reopened', actor, 'human' if actor in ('owner', 'web') else 'agent', {'from': was})
        if fields.get('Status') in ('done', 'dropped') and was not in (None, 'done', 'dropped') and actor != 'promise':
            from . import outcomes
            facts = {'from': was, 'to': fields['Status']}
            if str(was_row.get('Assignee') or '').startswith('person:'):     # a step somebody owed: whom, and how late (build step 4)
                facts['who'] = was_row['Assignee'][7:].lower(); facts['due'] = was_row.get('DueAt')
                try: facts['late_days'] = max(0, (datetime.now().date() - datetime.strptime(str(was_row.get('DueAt') or '')[:10], '%Y-%m-%d').date()).days)
                except ValueError: pass
            # ...the skill it was worked from, and whether the last mail on it asked something - what the ledger counts about a
            # KIND of work (skill_facts.py, build step 5): "closed with a question open" is the model's intent, never a word match
            from . import skills as _pb
            if _pb.of_task(was_row):
                # ...and still open only when the owner's own word did not come after it (the review, 2026-10-12: the opening mail alone
                # counted every task as closed on an open question)
                li = self.last_inbound_on_task(task_id); v = self.message_verdict(li['MessageId']) if li else None
                own = self.own_reply_on_thread(li.get('ConversationId'), task_id) if li else None
                facts.update(skill=_pb.of_task(was_row), asked=bool(v and v.get('intent') in ('task', 'reply_only')
                                                                    and not (own and str(own.get('SentAt') or '') >= str(li.get('SentAt') or ''))))
            outcomes.record(self, 'task.closed', 'task', task_id, actor, facts=facts)
        self._bump_snapshots()
        # Timeline rows carry task/review state too, so a task transition changes both views.
        self._poke('feed-changed', 'task-changed', task_id=task_id)
    def get_task(self, task_id):
        """One task's row. While a build holds its settings (held_settings) the row is read once until this store writes - a task's page
        read asked it ~30 times (tests/test_big_task_opens_fast) - and each caller gets its own copy to change."""
        held, w = getattr(_HELD, 'settings', None), getattr(self, '_writes', None)
        if held is None or held[0] is not self or w is None: return self._one('SELECT * FROM task WHERE TaskId=?', (task_id,))
        k = ('task', task_id, w)
        if k not in held[1]: held[1][k] = self._one('SELECT * FROM task WHERE TaskId=?', (task_id,))
        return dict(held[1][k]) if held[1][k] else held[1][k]
    # ── the checklist: what the message actually asked for, as boxes (PW-074..077) ───────────
    # Items carry a stable id derived from their words, so a re-triage or an owner edit that
    # keeps an item's text keeps its box; progress is never task completion.
    CHECKLIST_MAX = 12
    @staticmethod
    def checklist_id(text: str) -> str:
        # Case, punctuation, comparison operators and internal spacing can change the work.
        # Hash the stored words exactly (apart from their harmless outer whitespace) so
        # "x <= 3" never aliases "x >= 3" and an owner-authored distinction stays distinct.
        return hashlib.sha1(str(text or '').strip().encode()).hexdigest()[:8]
    @classmethod
    def clean_checklist(cls, items, *, cap=True) -> list:
        """Strings only, outer whitespace trimmed, exact repeats removed.

        Triage verdicts stay bounded by CHECKLIST_MAX. The owner can edit an accumulated
        checklist beyond that per-verdict limit without silently dropping existing boxes.
        """
        if not isinstance(items, (list, tuple)): return []
        out, seen = [], set()
        for x in items:
            if not isinstance(x, str): continue
            text = x.strip() if len(x.strip()) <= ON_YOU_MAX else by_sentence(x, ON_YOU_MAX)
            if not text: continue
            # Case can be substantive in paths, identifiers, and commands. Only the exact
            # stored text is safe to treat as a duplicate.
            if text in seen: continue
            seen.add(text); out.append(text)
            if cap and len(out) >= cls.CHECKLIST_MAX: break
        return out
    def task_checklist(self, task_id) -> list:
        t = self.get_task(task_id)
        try: items = json.loads((t or {}).get('Checklist') or '[]')
        except (TypeError, ValueError): items = []
        return [i for i in items if isinstance(i, dict) and i.get('text')] if isinstance(items, list) else []
    def _write_checklist(self, task_id, items: list, actor: str):
        self._exec('UPDATE task SET Checklist=?, UpdatedBy=?, UpdatedAt=? WHERE TaskId=?', (json.dumps(items), actor, _now(), task_id))
        self._bump_snapshots(); self._poke('task-changed', task_id=task_id)
    def set_task_checklist(self, task_id, texts, actor: str) -> list:
        """Replace the list with these words; a box whose words are unchanged keeps its state."""
        old = {i['text']: i for i in self.task_checklist(task_id)}
        clean = self.clean_checklist(texts, cap=actor != 'owner')
        # Reserve every retained box before allocating IDs to new boxes. A new earlier row's
        # digest prefix must not steal a later unchanged box's legacy ID and its UI target.
        retained_id_owner = {}
        for text in clean:
            item_id = (old.get(text) or {}).get('id')
            if item_id and item_id not in retained_id_owner:
                retained_id_owner[item_id] = text
        items, used_ids = [], set(retained_id_owner)
        for text in clean:
            prior = old.get(text) or {}
            item_id = prior.get('id')
            digest = hashlib.sha1(text.encode()).hexdigest()
            if not item_id or retained_id_owner.get(item_id) != text:
                item_id = next((digest[:n] for n in range(8, len(digest) + 1)
                                if digest[:n] not in used_ids), digest)
            used_ids.add(item_id)
            items.append({'id': item_id, 'text': text, 'done': bool(prior.get('done')),
                          **{k: prior[k] for k in ('out', 'rid', 'tid', 'note', 'src', 'on_you') if k in prior}})     # a slot keeps what it sends and its draft; a step its child; a box its note and its message
        self._write_checklist(task_id, items, actor)
        return items
    def merge_task_checklist(self, task_id, texts, actor: str) -> list:
        """Add items to the list; nothing existing moves or unticks. Returns the new ones."""
        items = self.task_checklist(task_id)
        have, used_ids, new = {i['text'] for i in items}, {i.get('id') for i in items}, []
        for text in self.clean_checklist(texts):
            if text in have: continue
            digest = hashlib.sha1(text.encode()).hexdigest()
            item_id = next((digest[:n] for n in range(8, len(digest) + 1)
                            if digest[:n] not in used_ids), digest)
            new.append({'id': item_id, 'text': text, 'done': False})
            have.add(text); used_ids.add(item_id)
        if new: self._write_checklist(task_id, items + new, actor)
        return new
    def add_checklist_items(self, task_id, ready: list, actor: str) -> list:
        """Append ready-made items ({text, out}) - output slots (slots.add); ids as merge_task_checklist gives them."""
        items = self.task_checklist(task_id)
        have, used_ids, new = {i['text'] for i in items}, {i.get('id') for i in items}, []
        for r in ready:
            text = str(r.get('text') or '').strip()[:300]
            if not text or text in have: continue
            digest = hashlib.sha1(text.encode()).hexdigest()
            item_id = next((digest[:n] for n in range(8, len(digest) + 1) if digest[:n] not in used_ids), digest)
            new.append({'id': item_id, 'text': text, 'done': False, **({'out': r['out']} if r.get('out') else {})})
            have.add(text); used_ids.add(item_id)
        if new: self._write_checklist(task_id, items + new, actor)
        return new
    def note_checklist_item(self, task_id, item_id: str, note: str, actor: str) -> bool:
        """A note on one to-do, kept with the box ('' removes it) - the owner's "Gail has it" under "send the W-9" (2026-10-20)."""
        items = self.task_checklist(task_id)
        hit = [i for i in items if i['id'] == item_id]
        if not hit: return False
        note = ' '.join(str(note or '').split())[:500]
        if note: hit[0]['note'] = note
        else: hit[0].pop('note', None)
        self._write_checklist(task_id, items, actor)
        return True
    def set_on_you(self, task_id, texts, actor: str) -> list:
        """The steps left on the owner (`on_you` items) as these words - from an agent's turn summary or, where no agent works, triage's
        reading (Task 3.5). Every other box stays, and so does an On you step the owner ticked; the unticked ones are replaced - a step
        said again keeps its place, id, note and source, a new one goes at the end. Returns the list as written.
        Read and written under the writer's lock, as tick_checklist_item is: an owner's tick landing between the two was lost."""
        clean = self.clean_checklist(texts)
        with self.lock:
            items, want = self.task_checklist(task_id), set(clean)
            out = [i for i in items if not (i.get('on_you') and not i.get('done') and i['text'] not in want)]
            have, used_ids = {i['text'] for i in out}, {i.get('id') for i in out}
            for text in clean:
                if text in have: continue
                digest = hashlib.sha1(text.encode()).hexdigest()
                item_id = next((digest[:n] for n in range(8, len(digest) + 1) if digest[:n] not in used_ids), digest)
                out.append({'id': item_id, 'text': text, 'done': False, 'on_you': True}); have.add(text); used_ids.add(item_id)
            if out != items: self._write_checklist(task_id, out, actor)
        return out
    def tick_checklist_item(self, task_id, item_id: str, done: bool, actor: str) -> bool:
        with self.lock:          # one read-and-write: a set_on_you between them lost the tick, or the tick its steps
            items = self.task_checklist(task_id)
            hit = [i for i in items if i['id'] == item_id]
            if not hit: return False
            hit[0]['done'] = bool(done)
            self._write_checklist(task_id, items, actor)
        return True
    def checklist_markdown(self, task_id, ids: bool = False, shell: bool = True) -> str:
        """`ids`: the agent's copy - each box an agent may tick carries its id, for `taskuary --tick <id>` (the owner, 2026-10-22:
        agents tick the to-dos they finish). An email box ticks when its email goes and a goal's step when its task closes.
        `shell`: a slot's line says the command that fills it - a session whose hands are its shell (the coding seed). A chat's copy names
        the slot by its id instead, and its brief says the one way it fills it (general.by_tool): told the command, the tool and the marked
        block at once, an agent wrote "an email to Ray Colton" a second time beside the line that asked for it (the agent walk, 2026-11-10)."""
        # a slot says where it goes and how to fill it: the seed line is byte-capped, so the command rides here (slots.py)
        def line(i):
            o = i.get('out') if isinstance(i.get('out'), dict) else None
            maybe = f" (could be {' or '.join(o['candidates'][:3])} - {'fill with --to' if shell else 'say which in `to`'})" if o and o.get('candidates') else ''
            how = 'drafted' if i.get('rid') else f"fill with `taskuary --slot {i['id']} --draft \"<text>\"`"
            if not shell: how = f"slot {i['id']} - {'drafted' if i.get('rid') else 'to draft'}"
            tail = f" -> email to {o.get('to')}{maybe}, {how}" if o else ''
            tag = f" [{i['id']}]" if ids and agent_tickable(i) else ''
            return f"- [{'x' if i.get('done') else ' '}] {i['text']}{tag}{tail}" + (f" (note: {i['note']})" if i.get('note') else '')
        return '\n'.join(line(i) for i in self.task_checklist(task_id))
    # ── goals: a task whose boxes are tasks (spec 2026-10-12) ─────────────────────────────────
    def children(self, task_id) -> list:
        return self._rows('SELECT * FROM task WHERE ParentId=? ORDER BY TaskId', (task_id,))
    def goal_steps(self, task_id) -> list:
        """Every box of the goal with the child task behind it, in the goal's own order."""
        kids = {t['TaskId']: t for t in self.children(task_id)}
        return [{'id': i['id'], 'text': i['text'], 'done': bool(i.get('done')), 'tid': i.get('tid'), 'child': kids.get(i.get('tid'))}
                for i in self.task_checklist(task_id)]
    def link_step(self, task_id, item_id: str, child_tid: int, actor: str) -> bool:
        items = self.task_checklist(task_id)
        hit = [i for i in items if i['id'] == item_id]
        if not hit: return False
        hit[0]['tid'] = int(child_tid)
        self._write_checklist(task_id, items, actor)
        self._exec('UPDATE task SET ParentId=? WHERE TaskId=?', (task_id, int(child_tid)))
        return True
    def step_arrivals(self, goal_tid) -> dict:
        """Mail that served a goal's steps, by step id - the route rows triage wrote with `serves` (spec 2026-10-12)."""
        rows = self._rows("SELECT r.MessageId mid, json_extract(r.VerdictJson, '$.serves.step') step, m.FromName who, m.FromEmail em, m.SentAt at, "
                          "m.Subject subject FROM route r JOIN message m ON m.MessageId=r.MessageId "
                          "WHERE json_extract(r.VerdictJson, '$.serves.task')=? ORDER BY m.SentAt, r.RouteId", (int(goal_tid),))
        out = {}
        for r in rows: out.setdefault(r['step'], []).append({'mid': r['mid'], 'who': r['who'] or r['em'] or '', 'at': r['at'], 'subject': r['subject'] or ''})
        return out
    def _tick_parent_step(self, child_tid, actor: str):
        """A child closed `done` ticks the parent's box that points at it; the parent itself is never closed for it."""
        row = self._one('SELECT ParentId FROM task WHERE TaskId=?', (child_tid,))
        if not row or not row.get('ParentId'): return
        items = self.task_checklist(row['ParentId'])
        hit = [i for i in items if i.get('tid') == child_tid and not i.get('done')]
        if not hit: return
        hit[0]['done'] = True
        self._write_checklist(row['ParentId'], items, actor)

    def tag_task(self, task_id, tag, on=True, actor='router'):
        """Add or remove ONE tag, leaving the others alone. Tags is a csv the UI and the router
        both write (repo:x, needs:browser, hold:new-sender), so read-modify-write on the whole
        field is how two writers lose each other's tag."""
        cur = [t for t in re.split(r'[\s,]+', str((self.get_task(task_id) or {}).get('Tags') or '')) if t]
        want = [t for t in cur if t != tag] + ([tag] if on else [])
        if want == cur: return False
        self.update_task(task_id, {'Tags': ','.join(want) or None}, actor)
        return True

    def task_has_tag(self, task_id, tag) -> bool:
        return tag in re.split(r'[\s,]+', str((self.get_task(task_id) or {}).get('Tags') or ''))
    @staticmethod
    def _like_pat(term):
        """A LIKE pattern for one search word. % and _ typed in the box are literals, not wildcards."""
        t = _fold(term).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        return f'%{t}%'

    def _search_where(self, q, shown=False):
        """AND of the typed words; each word may match the task OR any of its messages.

        Taken from PR #49, which had the field list right - the same eighteen the Tasks tab used to
        filter on in the browser, so a search means the same thing now that it runs here. The one
        change is tq_fold on both sides: #49 lowered the pattern in Python (Unicode) and the column
        in SQL (ASCII), so a task titled "MULLER invoice" with an umlaut was findable by no
        spelling of the word at all.

        `shown`: only what a hit can show it matched on (search.py) - Status and Priority are the
        Tasks tab's columns, and in the one search box "open" listed every open task, ahead of the
        one that said it (the 2026-10-19 UI walk). That box asks for a status as `status:open`.
        """
        # ONE FOLD PER ROW, NOT ONE PER FIELD (the load run, 2026-11-24): eighteen tq_fold calls a task and a message, each a hop into Python,
        # made triage's found_tasks ~100 ms a mail on 150 open tasks. The fields are joined by char(31) - a word never holds it (split() cuts
        # on it), so a word is found in the join exactly where it is found in one of the fields
        cols = ['t.Title', 't.Summary', 't.Kind', *(() if shown else ('t.Status', 't.Priority')), 't.Assignee', 't.Source', 't.SourceRef', 't.Tags',
                "printf('TQ-%04d', t.TaskId)", 'CAST(t.TaskId AS TEXT)']
        mcols = ['m.Channel', 'm.SourceName', 'm.Subject', 'm.FromName', 'm.FromEmail', 'm.ExternalId', 'm.SourceLink']
        join = lambda cs: "tq_fold(" + "||char(31)||".join(f"IFNULL({c},'')" for c in cs) + ")"
        where, p = [], []
        for term in str(q or '').split():
            pat = self._like_pat(term)
            where.append(f"""({join(cols)} LIKE ? ESCAPE '\\' OR ('tq-' || t.TaskId) LIKE ? ESCAPE '\\'
                OR EXISTS (SELECT 1 FROM message m WHERE m.TaskId=t.TaskId AND {join(mcols)} LIKE ? ESCAPE '\\'))""")
            # "TQ-796" finds TQ-0796: the ref is matched with its padding zeros read as none
            ref = re.sub(r'^tq-?0*(?=\d)', 'tq-', _fold(term))
            p.extend([pat, self._like_pat(ref), pat])
        return where, p

    def worked_today_task_ids(self) -> set:
        """Tasks the owner handled on the work rail today - put on the table, passed or settled there. Read from the
        walk's own marks, not the read receipts: a receipt is kept once per version of an item, so when Taskuary had
        already read its own words the owner's look wrote nothing and the task seemed untouched."""
        return {int(r['LocalId']) for r in self._rows(
            "SELECT DISTINCT m.LocalId FROM funnel_state f JOIN processing_member m ON f.Key='processing:'||m.ItemId "
            "WHERE m.EntityKind='task' AND m.RetiredAt IS NULL AND f.By IN ('owner','you') "
            "AND f.At >= date('now','localtime')") if str(r['LocalId']).isdigit()}
    def list_tasks(self, status=None, active_only=False, q=None, also=(), shown=False):
        """Task rows, each carrying its latest review, run and handover note.

        `q` searches HERE rather than in the browser. It used to be six more GROUP_CONCAT(DISTINCT)
        columns over the WHOLE message table - seven temp B-trees, 34ms of a 35ms query and 69KB of
        a 319KB payload on a store of 270 tasks - shipped to every caller so that the Tasks tab
        could filter them locally. Nothing reads them now, so nothing builds or sends them, and the
        saving grows with the message table rather than with the task table. SearchSources stays:
        Board and Tasks both draw "Report - <source>" from it.
        """
        where, p = [], []
        # The hovering guide persists its conversation in a task-shaped record so it can reuse
        # the assistant session machinery, but it is application chrome, not work. Keep it out
        # of every task consumer (Board, digests, cold-task checks, setup statistics).
        where.append("IFNULL(t.SourceRef,'') <> 'assistant:dock'")
        if status:
            where.append('t.Status=?'); p.append(status)
        if active_only:
            # the Board's Done column is today only; older finished work lives on Tasks
            where.append("(t.Status IN ('open','in_progress','waiting') "
                         "OR (t.Status='done' AND IFNULL(t.ClosedAt, t.UpdatedAt) >= date('now','localtime'))"
                         + ''.join(f" OR t.TaskId={int(i)}" for i in also) + ")")
        qw, qp = self._search_where(q, shown)
        where += qw; p += qp
        # ...THE TASKS FIRST, then what each one carries - for those tasks only (the owner's restart, 2026-11-16): the latest review, run,
        # handover and sources were each built over the whole table and then joined to the thirty open tasks, ~90 ms a call on his store,
        # and one page read asks for the open tasks several times
        query = f'''WITH t AS (SELECT t.* FROM task t WHERE {' AND '.join(where)}), ids AS (SELECT TaskId FROM t)
                SELECT t.*, rv.Status ReviewStatus, rv.Kind ReviewKind,
                       rn.Status RunStatus, rn.AgentName RunAgent,
                       ho.Body HandoverNote,
                       ms.SearchSources
                FROM t
               LEFT JOIN (
                   SELECT TaskId, Status, Kind FROM review
                   WHERE ReviewId IN (SELECT MAX(ReviewId) FROM review WHERE TaskId IN ids GROUP BY TaskId)
               ) rv ON rv.TaskId=t.TaskId
               LEFT JOIN (
                   SELECT TaskId, Status, AgentName FROM run
                   WHERE RunId IN (SELECT MAX(RunId) FROM run WHERE TaskId IN ids GROUP BY TaskId)
               ) rn ON rn.TaskId=t.TaskId
               LEFT JOIN (
                   SELECT TaskId, Body FROM comment
                   WHERE CommentId IN (
                       SELECT MAX(CommentId) FROM comment WHERE TaskId IN ids AND Body LIKE 'HANDOVER NOTE%' GROUP BY TaskId
                   )
                ) ho ON ho.TaskId=t.TaskId
               LEFT JOIN (
                   SELECT TaskId, GROUP_CONCAT(DISTINCT SourceName) SearchSources
                   FROM message WHERE TaskId IN ids GROUP BY TaskId
               ) ms ON ms.TaskId=t.TaskId'''
        # ...A SEARCH READS ON A READER CONNECTION, NEVER UNDER THE WRITER'S LOCK (his live app, 2026-11-23: triage's found_tasks ran a search per
        # word and held the lock 3-4 s each, every other request - a press, the list - queued behind it for up to 10 s). Read only, so any snapshot serves
        # ...and so does the plain list, whose WITH _rows never took for a read: triage's open_goals held the writer 80-200 ms a mail (load run, 11-24)
        if q or self._off_writer():
            with self._snapshot_read() as cur: return [dict(r) for r in cur.execute(query + ' ORDER BY t.TaskId DESC', p).fetchall()]
        return self._rows(query + ' ORDER BY t.TaskId DESC', p)
    def delete_task(self, task_id):
        # the Advisor idea this task was made from goes with it: left open, it came back on the rail alone as "asked you",
        # pointing at a task that no longer existed (2026-09-29)
        self._exec("UPDATE idea SET Status='dismissed', DecidedBy='owner', DecidedAt=? WHERE Status IN ('open','snoozed') AND "
                   "(json_extract(ActionJson,'$.tid')=? OR IdeaId IN (SELECT CAST(substr(SourceRef,16) AS INTEGER) FROM task "
                   "WHERE TaskId=? AND SourceRef LIKE 'assistant:idea:%'))", (_now(), task_id, task_id))
        for q in ("UPDATE message SET TaskId=NULL, Status='filed' WHERE TaskId=?", 'UPDATE route SET TaskId=NULL WHERE TaskId=?',
                  'DELETE FROM review WHERE TaskId=?', 'DELETE FROM comment WHERE TaskId=?', 'DELETE FROM draft_snapshot WHERE TaskId=?',
                  'DELETE FROM run WHERE TaskId=?', 'DELETE FROM task_artifact WHERE TaskId=?',
                  'DELETE FROM session_resume WHERE TaskId=?',
                  # ...and its worker's events: a question it asked stayed open, and a deleted task still raised its toast (email walk 2026-10-29)
                  'DELETE FROM worker_event WHERE TaskId=?',
                  'DELETE FROM task WHERE TaskId=?'):
            self._exec(q, (task_id,))
        self._bump_snapshots()
        self._poke('feed-changed', 'task-changed', task_id=task_id)
    @contextlib.contextmanager
    def freeze_snapshots(self):
        """Reuse one snapshots() result until a task/message write invalidates it.

        drain() holds this so a 40-mail catch-up is not 40 rebuilds: a filed FYI does
        not change the open-task picture, so the next message reuses it. Opening a
        task (or attaching mail to one) drops the cache, so a thread's second message
        still finds the task the first one just created."""
        self._snap_hold += 1
        try:
            yield
        finally:
            self._snap_hold -= 1
            if self._snap_hold <= 0:
                self._snap_hold, self._snap_cache = 0, None

    def _bump_snapshots(self):
        self._snap_gen += 1; self._snap_cache = None

    def snapshots(self):
        if self._snap_hold and (c := self._snap_cache) is not None: return c
        # ...kept only when no write landed while it was read: drain's lanes write beside each other, and a picture read before
        # another lane opened a task, cached after, hid that task from the thread's next line
        gen = self._snap_gen
        snaps = self._load_snapshots()
        if self._snap_hold and gen == self._snap_gen: self._snap_cache = snaps
        return snaps

    def _load_snapshots(self):
        """Open tasks as the router sees them - one query, not one per task.

        A catch-up used to do SELECT * FROM task then SELECT * FROM message for each,
        so routing 40 mails against 80 open tasks was 3,200 extra round trips on the
        lock. LEFT JOIN keeps a hand-typed task (no messages yet) in the picture."""
        rows = self._rows("""
            SELECT t.TaskId, t.Title, m.Subject, m.FromEmail, m.ConversationId,
                   substr(m.BodyText, 1, 2000) BodyText
            FROM task t
            LEFT JOIN message m ON m.TaskId = t.TaskId
            WHERE t.Status IN ('open','in_progress','waiting')
            ORDER BY t.TaskId, m.MessageId
        """)
        out = {}
        for r in rows:
            snap = out.get(r['TaskId'])
            if snap is None:
                snap = out[r['TaskId']] = {
                    'task_id': r['TaskId'], 'title': r['Title'],
                    'subjects': [], 'senders': [], 'conversation_ids': [],
                    'text': r['Title'] or '',
                }
            if r['Subject']: snap['subjects'].append(r['Subject'])
            if r['FromEmail']: snap['senders'].append(r['FromEmail'])
            if r['ConversationId']: snap['conversation_ids'].append(r['ConversationId'])
            if r['BodyText'] is not None:
                snap['text'] += ' ' + r['BodyText']
        return list(out.values())

    # messages / routes / comments
    def withdraw_message(self, external_id: str, actor: str = 'sync') -> bool:
        """The sender deleted it where it came from. Mark the row - do NOT remove it.

        A Timeline row can have a task, an agent session, a drafted reply and an audit trail
        hanging off it, and a message vanishing from a mailbox must not silently destroy that
        work. Withdrawn is a state, not a deletion: the row stays readable and its history
        intact, it stops counting as waiting on the owner, and the screen says the sender took
        it back."""
        row = self._one('SELECT MessageId, TaskId, Status FROM message WHERE ExternalId=?', (external_id,))
        if not row or row['Status'] == 'withdrawn': return False
        self._exec("UPDATE message SET Status='withdrawn' WHERE MessageId=?", (row['MessageId'],))
        if row['TaskId']:
            self.add_comment(row['TaskId'], actor, 'agent',
                             'The sender deleted this message where it came from. The task is left '
                             'as it is - only the message is marked withdrawn.')
        self.audit('message', row['MessageId'], 'withdrawn', actor, 'agent', {'external_id': external_id})
        return True

    def set_chain_coverage(self, conversation_id: str, channel: str, mailbox: str, cov: dict):
        self._exec('INSERT INTO chain (Mailbox, ConversationId, Channel, CheckedAt, Complete, Listed, Added, Error) VALUES (?,?,?,?,?,?,?,?) '
                   'ON CONFLICT(Mailbox, ConversationId) DO UPDATE SET Channel=excluded.Channel, CheckedAt=excluded.CheckedAt, '
                   'Complete=excluded.Complete, Listed=excluded.Listed, Added=excluded.Added, Error=excluded.Error',
                   (str(mailbox or '').lower(), conversation_id, channel, _now(), 1 if cov.get('complete') else 0, int(cov.get('listed') or 0), int(cov.get('added') or 0), cov.get('error')))
    def chain_coverage(self, conversation_id: str, mailbox: str = None):
        """One mailbox's coverage of the conversation; a caller with no mailbox reads the latest row (PW-011)."""
        r = (self._one('SELECT * FROM chain WHERE Mailbox=? AND ConversationId=?', (str(mailbox).lower(), conversation_id)) if mailbox is not None
             else self._one('SELECT * FROM chain WHERE ConversationId=? ORDER BY CheckedAt DESC, rowid DESC LIMIT 1', (conversation_id,)))
        if not r: return None
        return {'complete': bool(r['Complete']), 'listed': r['Listed'], 'added': r['Added'], 'error': r['Error'], 'checked_at': r['CheckedAt']}
    # operations, correction evidence and discussion (operations.py)
    OP_COLS = ('OpId', 'Kind', 'TargetKind', 'TargetId', 'ParamsJson', 'Actor', 'ContextRevision', 'Version', 'Status', 'OutcomeJson',
               'Error', 'Evidence', 'Verdict', 'VerdictRouteId', 'ExecutedAt')
    def add_operation(self, fields: dict) -> str:
        self._insert('operation', fields, self.OP_COLS, {'CreatedAt': _now(), 'UpdatedAt': _now()}); return fields['OpId']
    def get_operation(self, op_id: str): return self._one('SELECT * FROM operation WHERE OpId=?', (op_id,))
    def claim_operation(self, op_id: str, version: int) -> bool:
        """The compare-and-set two simultaneous confirms race on (PW-129): exactly one turns the row `running`."""
        with self.lock:
            cur = self.cx.execute("UPDATE operation SET Status='running', UpdatedAt=? WHERE OpId=? AND Version=? AND Status IN ('proposed','error')",
                                  (_now(), op_id, int(version)))
            self.cx.commit(); self._writes += 1
            return cur.rowcount == 1
    def update_operation(self, op_id: str, fields: dict):
        d = {k: v for k, v in fields.items() if k in self.OP_COLS and k != 'OpId'} | {'UpdatedAt': _now()}
        self._exec(f"UPDATE operation SET {', '.join(k + '=?' for k in d)} WHERE OpId=?", [*d.values(), op_id])
    def operations_for(self, task_id: int = None, message_ids: list = ()) -> list:
        conds, args = [], []
        if task_id: conds.append("(TargetKind='task' AND TargetId=?)"); args.append(task_id)
        if message_ids: conds.append(f"(TargetKind='message' AND TargetId IN ({','.join('?' * len(message_ids))}))"); args += list(message_ids)
        if not conds: return []
        return self._rows(f"SELECT * FROM operation WHERE {' OR '.join(conds)} ORDER BY CreatedAt, rowid", args)
    def operations_pending_evidence(self) -> list: return self._rows("SELECT * FROM operation WHERE Status='done' AND Evidence='pending' ORDER BY rowid")
    def add_correction(self, fields: dict) -> int:
        return self._insert('correction', fields, ('OpId', 'MessageId', 'TaskId', 'Sender', 'Topic', 'Verdict', 'VerdictRouteId', 'Change', 'ContextJson'),
                            {'CreatedAt': _now()})
    def corrections(self, message_id: int = None, task_id: int = None, sender: str = None, topic: str = None, limit: int = 200) -> list:
        conds, args = [], []
        if message_id: conds.append('MessageId=?'); args.append(message_id)
        if task_id: conds.append('TaskId=?'); args.append(task_id)
        if sender: conds.append('lower(Sender)=?'); args.append(str(sender).lower())
        if topic: conds.append('Topic=?'); args.append(topic)
        where = ('WHERE ' + ' OR '.join(conds)) if conds else ''
        return self._rows(f'SELECT * FROM correction {where} ORDER BY Id DESC LIMIT ?', [*args, limit])[::-1]
    def add_discussion(self, fields: dict) -> int:
        return self._insert('discussion', fields, ('MessageId', 'TaskId', 'Actor', 'Body', 'OpId'), {'CreatedAt': _now()})
    def discussion(self, task_id: int = None, message_id: int = None) -> list:
        conds, args = [], []
        if task_id: conds.append('TaskId=?'); args.append(task_id)
        if message_id: conds.append('MessageId=?'); args.append(message_id)
        if not conds: return []
        return self._rows(f"SELECT * FROM discussion WHERE {' OR '.join(conds)} ORDER BY Id", args)
    def link_discussion(self, task_id: int, message_ids: list) -> int:
        if not message_ids: return 0
        with self.lock:
            cur = self.cx.execute(f"UPDATE discussion SET TaskId=? WHERE TaskId IS NULL AND MessageId IN ({','.join('?' * len(message_ids))})", [task_id, *message_ids])
            self.cx.commit(); return cur.rowcount
    def message_exists(self, external_id):
        return self._one('SELECT 1 x FROM message WHERE ExternalId=?', (external_id,)) is not None
    def add_message(self, fields):
        # normalized on the way IN, not only by a heal on the way past: one clock for the
        # timeline, and no row that can sort above its own future
        if fields.get('SentAt'): fields = {**fields, 'SentAt': norm_stamp(fields['SentAt'])}
        mid = self._insert('message', fields, MSG_COLS, {'CreatedAt': _now()})
        if fields.get('TaskId'):
            self._bump_snapshots()
            from . import events                 # ...filed on a task as it is stored: one event there (events.arrived)
            events.arrived(self, mid, fields['TaskId'])
            self._poke('feed-changed', 'task-changed', message_id=mid, task_id=fields['TaskId'])
        else:
            if (fields.get('Direction') == 'out' or fields.get('Status') == 'context') and fields.get('ConversationId'):
                from . import events             # ...his own reply filed on no task: an event on the tasks of its thread
                events.arrived(self, mid)
            self._poke('feed-changed', message_id=mid)
        return mid
    def get_message(self, mid): return self._one('SELECT * FROM message WHERE MessageId=?', (mid,))
    def message_by_external(self, external_id):
        return self._one('SELECT * FROM message WHERE ExternalId=? ORDER BY MessageId DESC LIMIT 1', (external_id,))
    def last_version(self, base):
        "The newest stored version of tracker item `base` (gh:o/r#42, jira:OPS-12): its bare id or a rev_id of it - never a comment on it."
        return self._one("SELECT * FROM message WHERE ExternalId=? OR ExternalId LIKE ? ORDER BY MessageId DESC LIMIT 1", (base, base + '@%'))
    # ── what the hub knows about a sender / a topic (counsel.dossier, responder) ─────────────
    def messages_from(self, email, since, limit=8):
        return self._rows("SELECT * FROM message WHERE lower(FromEmail)=? AND Status NOT IN ('context','history','skipped') AND SentAt>=? "
                          'ORDER BY SentAt DESC LIMIT ?', (email.lower(), since, limit))
    def senders_like(self, text, limit=6) -> list:
        """Everyone who ever wrote in whose name or address holds `text`, the most frequent first."""
        return self._rows("SELECT lower(FromEmail) Email, MAX(FromName) Name, COUNT(*) N, MIN(SentAt) First, MAX(SentAt) Last FROM message "
                          "WHERE IFNULL(Direction,'in')<>'out' AND Status<>'context' AND IFNULL(FromEmail,'')<>'' "
                          "AND lower(IFNULL(FromName,'') || ' ' || FromEmail) LIKE ? GROUP BY lower(FromEmail) ORDER BY N DESC LIMIT ?",
                          (f'%{str(text).strip().lower()}%', limit))
    def open_tasks_from(self, email) -> list:
        return self._rows("SELECT DISTINCT t.TaskId, t.Title, t.Status, t.Kind FROM task t JOIN message m ON m.TaskId=t.TaskId "
                          "WHERE lower(m.FromEmail)=? AND t.Status IN ('open','in_progress','waiting') ORDER BY t.TaskId DESC", (email.lower(),))
    def own_replies_to(self, email, since, limit=5):
        """The owner's own words on this sender's threads - 'context' rows ride inside the chains."""
        return self._rows("SELECT * FROM message WHERE Status='context' AND SentAt>=? AND ConversationId IN "
                          '(SELECT ConversationId FROM message WHERE lower(FromEmail)=? AND ConversationId IS NOT NULL) '
                          'ORDER BY SentAt DESC LIMIT ?', (since, email.lower(), limit))
    def recent_messages(self, since, limit=300):
        return self._rows("SELECT MessageId, ConversationId, Channel, Direction, Subject, FromName, FromEmail, SentAt, Status, TaskId, SenderClass, substr(BodyText, 1, 400) BodyText "
                          "FROM message WHERE Status NOT IN ('context','history','skipped') AND SentAt>=? ORDER BY SentAt DESC LIMIT ?", (since, limit))
    def set_brief(self, mid, brief): self._exec('UPDATE message SET Brief=? WHERE MessageId=?', (brief, mid))
    def set_conversation(self, mid, cid): self._exec('UPDATE message SET ConversationId=? WHERE MessageId=?', (cid, mid))
    # ── what the assistant's post reads (assistant.py) ────────────────────────────────────────
    def owner_last_words(self, since, before, limit=40):
        """Threads whose LAST message is the owner's own ('context' rides inside a chain, 'out' was
        sent from here), written between `since` and `before` - the silence a chase is about."""
        return self._rows("SELECT * FROM message m WHERE (m.Status='context' OR m.Direction='out') AND m.ConversationId IS NOT NULL "
                          'AND m.SentAt>=? AND m.SentAt<=? AND NOT EXISTS (SELECT 1 FROM message x WHERE x.ConversationId=m.ConversationId '
                          "AND x.MessageId<>m.MessageId AND x.Status<>'skipped' AND x.SentAt>m.SentAt) ORDER BY m.SentAt DESC LIMIT ?",
                          (since, before, limit))
    # ── the owner's sent words, judged (sentjudge.py) ───────────────────────────────────────────
    _OWN_SENT = ("(m.Status='context' OR IFNULL(m.Direction,'')='out') AND m.ConversationId IS NOT NULL "
                 "AND IFNULL(m.Channel,'') NOT IN ('report','assistant','own')")
    def sent_unjudged(self, since, limit=40):
        """The owner's own sent messages in the window the model has not read yet, newest first."""
        return self._rows(f"SELECT m.* FROM message m WHERE {self._OWN_SENT} AND m.SentAt>=? "
                          'AND NOT EXISTS (SELECT 1 FROM sent_verdict v WHERE v.MessageId=m.MessageId) ORDER BY m.SentAt DESC LIMIT ?',
                          (since, limit))
    def own_sent_on_thread(self, conversation_id, after=None, before=None, limit=4):
        """The owner's own sent words on one thread, oldest first, between two stamps."""
        return self._rows(f"SELECT m.* FROM message m WHERE {self._OWN_SENT} AND m.ConversationId=? AND m.SentAt>? AND m.SentAt<? "
                          'ORDER BY m.SentAt LIMIT ?', (conversation_id, after or '', before or '9999', limit))
    def sent_verdict(self, mid): return self._one('SELECT * FROM sent_verdict WHERE MessageId=?', (mid,))
    def put_sent_verdict(self, mid, cid, asks, promise, what, due, by, delivered_by=None):
        self._exec('INSERT OR REPLACE INTO sent_verdict (MessageId,ConversationId,AsksThem,Promise,What,Due,DeliveredBy,JudgedAt,JudgedBy) '
                   'VALUES (?,?,?,?,?,?,?,?,?)', (mid, cid, int(bool(asks)), int(bool(promise)), what, due, delivered_by, _now(), by))
    def deliver_promise(self, mid, by):
        self._exec('UPDATE sent_verdict SET DeliveredBy=? WHERE MessageId=? AND Promise=1 AND DeliveredBy IS NULL', (by, mid))
        t = self.promise_task(mid)
        if t and t.get('Status') not in ('done', 'dropped'):
            # ...AN AUTOMATIC CLOSE, so it asks what every automatic close asks (workerstate.live_work, the owner 2026-11-01: "If anything
            # still working never close the task automatically") and what still waits on the owner there (proposals.owed): an agent put on
            # the promise kept working a closed task, and a reply drafted on it waited where no page shows one. Kept open, and said
            from . import buttons, proposals, workerstate as ws
            live = ws.live_work(self, t['TaskId'])
            if not live and not proposals.owed(self, t['TaskId']):
                from .concierge import close_task
                close_task(self, t['TaskId'], 'promise', save=False)
            else: self.add_comment(t['TaskId'], 'promise', 'agent', 'Your sent mail delivered this promise. It stays open - '
                                   + (live[0] if live else 'something on it still waits on you') + f" - {buttons.label('close')} when it is finished.")
        if t:                                           # delivered: the ledger row resolves now, not at the sweep
            try:
                from . import outcomes
                for r in outcomes.rows_for(self, 'task', t['TaskId']):
                    if r['Kind'] == 'promise.made' and not r['ResolvedAt']: outcomes._resolve_one(self, r, datetime.now())
            except Exception as e: logger.warning(f'promise {mid}: its outcome row was not resolved - {e}')
    def promise_task(self, mid): return self._one('SELECT * FROM task WHERE SourceRef=?', (f'promise:{mid}',))
    # A PROMISE TASK KNOWS WHOM IT OWES (the owner, 2026-10-26, on a promise task: "it does not show who to send it back to?? meaning
    # if the promise was to x it should save who to send to and draft response to them"). Its sent mail stays on the thread's own task
    # (made_from), so every "who is waiting on a reply" road - the agent's --reply, Close out's To, Reply, the Advisor - found nobody.
    # The mail is the reply's anchor instead: an answer to the owner's own mail goes to whom it went (outbound.reply_envelope: its To,
    # its Cc as they had them), and a chat's to its room. SourceRef already names it, so every promise task ever made has one.
    def promised_in(self, t) -> dict | None:
        """The owner's own message a promise task was made from ('promise:<mid>' in SourceRef), else None."""
        ref = str((t or {}).get('SourceRef') or '')
        return self.get_message(int(ref[8:])) if ref.startswith('promise:') and ref[8:].isdigit() else None
    def promisee(self, m: dict) -> str:
        """Whom the owner promised it to, by name: a mail's To line, else the room's other side (as task_for_promise says it)."""
        if not m: return ''
        if str(m.get('Channel') or '').lower() == 'email':
            from .ingest import names_on_thread
            try: to = (json.loads(m.get('RecipientsJson') or '{}') or {}).get('to') or []
            except (TypeError, ValueError): to = []
            if to: return ', '.join(names_on_thread(self, {'conversation_id': m.get('ConversationId'), 'subject': m.get('Subject')}, to)[:3])
        o = self.last_inbound_in(m['ConversationId']) if m.get('ConversationId') else None
        return str((o or {}).get('FromName') or (o or {}).get('FromEmail') or '')
    def made_from(self, t: dict, before=12, after=8) -> list:
        """The message a task was made from that is not ON it, with its thread around it, oldest first. A promise's sent mail
        is nearly always on the thread's own task already (task_for_promise links it only when it is free), and an Advisor
        idea on a closed task's mail opens a fresh task - a message points at one task, so the task carries its message in
        SourceRef ('promise:<mid>', 'assistant:idea:<n>' -> idea.MessageId) and Came from reads it from there, never moving it."""
        ref, mids = str(t.get('SourceRef') or ''), []
        if ref.startswith('promise:') and ref[8:].isdigit(): mids = [int(ref[8:])]
        elif ref.startswith('assistant:idea:') and ref[15:].isdigit(): mids = self.idea_sources(self.get_idea(int(ref[15:])))
        ms = [m for m in map(self.get_message, mids) if m and m.get('Channel') != 'assistant']   # the Advisor's own line is no source
        if not ms: return []
        m, out = ms[0], []
        if m.get('ConversationId'):
            q = ("SELECT * FROM message WHERE ConversationId=? AND Status<>'skipped' AND IFNULL(Channel,'')<>'assistant' AND MessageId<>? "
                 'AND SentAt{} ? ORDER BY SentAt {} LIMIT ?')
            a = (m['ConversationId'], m['MessageId'], m.get('SentAt') or '')
            # ...a window, not the whole thread: a family chat a promise was made in runs to thousands of lines
            out = list(reversed(self._rows(q.format('<=', 'DESC'), a + (before,)))) + [m] + self._rows(q.format('>', 'ASC'), a + (after,))
        else: out = [m]
        # ...and the other mails the idea's evidence cites (the follow-up on another thread), oldest first among them
        seen = {x['MessageId'] for x in out}
        return out + sorted((x for x in ms[1:] if x['MessageId'] not in seen), key=lambda x: x.get('SentAt') or '')
    def idea_sources(self, i) -> list:
        """The messages an Advisor idea is ABOUT, its own pick first: the mail it names (`mid`), then the ones its evidence cites ("Erin
        mid 41 vs Gail mid 42"), then the line it was read off. idea.MessageId is the Advisor post that SAID it - a task made from the
        idea used to show that post as what came in, and never the mail the idea was talking about (2026-10-28)."""
        if not i: return []
        try: a = json.loads(i.get('ActionJson') or '{}') or {}
        except (ValueError, TypeError): a = {}
        cited = cited_mids(a.get('why'))
        out = []
        for x in [a.get('mid'), *cited[:4], i.get('MessageId')]:
            try: x = int(x)
            except (TypeError, ValueError): continue
            if x not in out: out.append(x)
        return out
    def task_for_promise(self, mid: int, what: str, due) -> int:
        """The owner's own promise as a task on them (spec 2026-10-12): made once per sent message, dated when it was,
        saying whom it was made to and carrying the thread it was made in (the review, 2026-10-12: a title alone)."""
        t = self.promise_task(mid)
        if t: return t['TaskId']
        what = ' '.join(str(what or '').split())[:120] or 'what you promised'
        m = self.get_message(mid) or {}
        other = self.last_inbound_in(m['ConversationId']) if m.get('ConversationId') else None
        who = (other or {}).get('FromName') or (other or {}).get('FromEmail') or 'them'
        # a chat message has no subject: no `re ""` (the owner, 2026-10-14: "what is this text that looks weird??")
        subj = ' '.join(str(m.get('Subject') or '').split())
        summary = f"You told {who} on {str(m.get('SentAt') or '')[:10]}" + (f" re \"{subj}\"" if subj else '') + f" you would {what}."
        tid = self.create_task({'Title': what[:1].upper() + what[1:], 'Summary': summary, 'Kind': 'task', 'Status': 'open', 'Assignee': 'owner',
                                'Source': m.get('Channel') or 'email', 'SourceRef': f'promise:{mid}', 'DueAt': due or None}, 'promise')
        self.arrive(mid, tid, free=True)
        from . import outcomes
        outcomes.record(self, 'promise.made', 'task', tid, 'promise', facts={'mid': mid, 'due': due})   # the ledger: kept, kept late, late?
        from . import ledger
        ledger.promise(self, tid, mid, what, due)                                                     # ...and the record of what exists
        return tid
    def sent_onto_task(self, mid: int, tid: int, why: str) -> bool:
        """The owner's own sent message, on no task yet, put on the open task the model read it as part of - so the thread is that
        task's and the other side's reply follows it there (store.task_for_conversation). False when it found a task meanwhile."""
        if not self.arrive(mid, tid, free=True): return False       # ...nor while triage still reads it: it decides first
        self.add_route(mid, tid, 'attach', None, why, [], 'sentjudge')
        return True
    def open_promises(self, since, before='9999', conversation_id=None):
        """Promises the model read in the owner's sent words that nothing later of theirs delivered, newest first, with
        the message they were made in. The other side replying does not close one - "Great, thanks!" is not the budget."""
        return self._rows('SELECT m.*, v.What PromiseWhat, v.Due PromiseDue FROM sent_verdict v JOIN message m ON m.MessageId=v.MessageId '
                          'WHERE v.Promise=1 AND v.DeliveredBy IS NULL AND m.SentAt>=? AND m.SentAt<=? '
                          + ('AND m.ConversationId=? ' if conversation_id else '') + 'ORDER BY m.SentAt DESC',
                          (since, before) + ((conversation_id,) if conversation_id else ()))
    def task_verdicts(self, task_id) -> dict:
        "message_verdict for every message on a task in one read: {MessageId: verdict} - the newest route that kept one."
        out = {}
        for r in self._rows('SELECT r.MessageId, r.VerdictJson FROM route r JOIN message m ON m.MessageId=r.MessageId '
                            'WHERE m.TaskId=? AND r.VerdictJson IS NOT NULL ORDER BY r.RouteId', (task_id,)):
            try: out[r['MessageId']] = json.loads(r['VerdictJson'])
            except (TypeError, ValueError): out[r['MessageId']] = None
        return out
    def message_verdict(self, mid):
        """Triage's stored verdict on one message (route.VerdictJson), newest - None when triage never judged it."""
        row = self._one('SELECT VerdictJson FROM route WHERE MessageId=? AND VerdictJson IS NOT NULL ORDER BY RouteId DESC LIMIT 1', (mid,))
        try: return json.loads(row['VerdictJson']) if row else None
        except (TypeError, ValueError): return None
    def own_reply_on_thread(self, conversation_id=None, task_id=None):
        """The owner's own last word on a thread (or on a task's chain), however it was typed: a
        'context' row is their reply read back out of Sent, 'out' is one Taskuary sent. The
        assistant needs this to know the ball is in the other court - a reply typed in Outlook
        counts exactly as much as one approved here."""
        own = "(m.Status='context' OR IFNULL(m.Direction,'')='out')"
        if conversation_id:
            r = self._one(f"SELECT * FROM message m WHERE {own} AND m.ConversationId=? ORDER BY m.SentAt DESC LIMIT 1", (conversation_id,))
            if r: return r
        if not task_id: return None
        return self._one(f"SELECT * FROM message m WHERE {own} AND m.TaskId=? ORDER BY m.SentAt DESC LIMIT 1", (task_id,))
    def last_inbound_on_task(self, task_id):
        """The newest message on this task that somebody SENT us - never our own reply, never a
        report row. It is who a reply from this task goes to, which an item with no message of its
        own (an agent that finished, a wrap-up) had no way to name."""
        return self._one("SELECT * FROM message WHERE TaskId=? AND Status NOT IN ('context','history','skipped') "
                         "AND IFNULL(Direction,'in')<>'out' AND IFNULL(Channel,'')<>'report' "
                         'ORDER BY SentAt DESC, MessageId DESC LIMIT 1', (task_id,))
    def last_material_inbound_on_task(self, task_id, skip=()):
        """last_inbound_on_task minus the FYIs triage filed with nothing to do (PW-240): the line that can make a
        drafted reply stale is one somebody sent that changed the ask. `skip`: message ids passed over (triage's asides)."""
        skip = tuple(skip)
        return self._one("SELECT * FROM message WHERE TaskId=? AND Status NOT IN ('context','history','skipped','filed') "
                         "AND IFNULL(Direction,'in')<>'out' AND IFNULL(Channel,'')<>'report' "
                         + (f"AND MessageId NOT IN ({','.join('?' * len(skip))}) " if skip else '')
                         + 'ORDER BY SentAt DESC, MessageId DESC LIMIT 1', (task_id, *skip))
    def last_inbound_in(self, conversation_id):
        return self._one("SELECT * FROM message WHERE ConversationId=? AND Status NOT IN ('context','history','skipped') AND IFNULL(Direction,'in')<>'out' "
                         'ORDER BY SentAt DESC LIMIT 1', (conversation_id,))
    def inbound_before(self, conversation_id, at):
        "The newest line the other side wrote on the thread up to `at` - what the owner's line there answers (sentjudge._item)."
        if not conversation_id: return None
        return self._one("SELECT * FROM message WHERE ConversationId=? AND IFNULL(Direction,'in')<>'out' AND Status NOT IN ('context','skipped') "
                         'AND SentAt<=? ORDER BY SentAt DESC, MessageId DESC LIMIT 1', (conversation_id, str(at or '9999')))
    def shown_message_of(self, mid):
        """The newest message the feed SHOWS on the thread of one it hides (the owner's own sent mail, a back-filled `history` start):
        its task's, else its conversation's - None when nothing of that thread is shown. A hidden row is no row of its own, but its
        thread is, and "I can't find that one" over a thread active that week is the wrong answer (TQ-1293)."""
        m = self.get_message(mid)
        for col in ('TaskId', 'ConversationId'):
            if not m or m.get(col) is None: continue
            r = self._one(f"SELECT MessageId FROM message WHERE {col}=? AND Status NOT IN ('context','history','skipped') "
                          'ORDER BY SentAt DESC, MessageId DESC LIMIT 1', (m[col],))
            if r: return r['MessageId']
        return None
    def task_for_conversation(self, conversation_id, subject=None, parent=None):
        """The task this thread already belongs to - OPEN OR CLOSED. The router matches a reply
        against open tasks only (snapshots), which is right for inbound work and wrong for the
        owner's own reply: answer a thread the day after its task closed and the reply had
        nowhere to land, so the chain lost the last thing said on it. `parent` is the Message-ID
        the mail answers: on a thread with two tasks, the task of that mail is this one's."""
        if tid := self.task_of_parent(conversation_id, parent): return tid
        if conversation_id:
            r = self._one('SELECT TaskId FROM message WHERE ConversationId=? AND TaskId IS NOT NULL '
                          'ORDER BY MessageId DESC LIMIT 1', (conversation_id,))
            if r: return r['TaskId']
        # channels without a conversation id (and mail whose References header was rewritten)
        return next((m['TaskId'] for m in reversed(self.thread_messages(None, subject)) if m['TaskId']), None) if subject else None
    def task_of_parent(self, conversation_id, parent):
        "The task of the stored mail on this thread whose Message-ID is `parent` (what a mail answers - ingest.answers), else None."
        r = conversation_id and parent and self._one(f"SELECT TaskId FROM message WHERE ConversationId=? AND {meta_expr('mid')}=? "
                                                      'AND TaskId IS NOT NULL ORDER BY MessageId DESC LIMIT 1', (conversation_id, parent))
        return r['TaskId'] if r else None
    def conversation_of_mail(self, ids=(), gm_thread=None, mailbox=None):
        """The conversation a mail already stored here files under, found through the mail's own ids (TQ-1214,
        2026-10-26): Gmail's thread id when the server gave one, else the first of `ids` - root first - that is a
        conversation key or the Message-ID of a stored mail. None when nothing here belongs to it.

        The key each IMAP mail derived from its own headers was not enough: a reply whose In-Reply-To named the
        owner's answer rather than the first mail keyed a thread of its own, and the owner's next answer sat on
        the other half. Gmail's id is per account, so it is matched within the mailbox that read it."""
        if gm_thread:
            r = self._one(f"SELECT ConversationId FROM message WHERE {meta_expr('gm_thread')}=? AND SourceName=? "
                          'AND ConversationId IS NOT NULL ORDER BY MessageId LIMIT 1', (str(gm_thread), mailbox))
            if r: return r['ConversationId']
        ids = [i for i in dict.fromkeys(ids) if i][:100]
        if not ids: return None
        qs = ','.join('?' * len(ids))
        keys = {r['ConversationId'] for r in self._rows(f'SELECT DISTINCT ConversationId FROM message WHERE ConversationId IN ({qs})', ids)}
        # oldest row last, so where one id ever landed on two keys the first one kept wins
        by_mid = {r['m']: r['ConversationId'] for r in self._rows(
            f"SELECT {meta_expr('mid')} m, ConversationId FROM message WHERE {meta_expr('mid')} IN ({qs}) "
            'AND ConversationId IS NOT NULL ORDER BY MessageId DESC', ids)}
        return next((i if i in keys else by_mid[i] for i in ids if i in keys or i in by_mid), None)
    def open_task_with_same_ask(self, title, from_email, channel=None):
        """The OPEN task this exact ask is already sitting on, when the thread cannot say so.

        A machine that mails the same alert daily gets a new conversation id every time, so the
        thread check rightly finds nothing to join and the owner collects one task per day: TQ-0510
        and TQ-0511, identical titles, one day apart (2026-09-14). Identity here is triage's own
        title plus the sender's address, both matched EXACTLY - resemblance still decides nothing
        (ingest.identity_route), and a closed task is never reopened by a repeat.
        """
        if not (title or '').strip(): return None
        # ...and Taskuary's OWN arrivals, which have no sender address at all: an Advisor idea and the report run
        # about the same event opened two tasks seconds apart (the owner, 2026-09-25: "no duplicate ideas"). For
        # those the "sender" is Taskuary itself - the same triaged title from its own channels, still open.
        if not (from_email or '').strip():
            if channel not in OWN_CHANNELS: return None
            r = self._one("SELECT t.TaskId FROM task t WHERE t.Status NOT IN ('done','dropped') "
                          "AND LOWER(TRIM(t.Title))=? AND EXISTS (SELECT 1 FROM message m WHERE m.TaskId=t.TaskId "
                          f"AND m.Channel IN ({','.join('?' * len(OWN_CHANNELS))})) ORDER BY t.TaskId DESC LIMIT 1",
                          (title.strip().lower(), *OWN_CHANNELS))
            return r['TaskId'] if r else None
        # Driven from the TASKS, of which a handful are ever open, not from the messages, of which
        # there are tens of thousands: joining message-first scanned the whole table on every triaged
        # mail (14ms on a 6.7k-row store, growing with it). LOWER(TRIM()) rules out idx_message_from
        # either way, so the answer is to reach the address through few rows, not many.
        r = self._one("SELECT t.TaskId FROM task t WHERE t.Status NOT IN ('done','dropped') "
                      "AND LOWER(TRIM(t.Title))=? AND EXISTS (SELECT 1 FROM message m WHERE m.TaskId=t.TaskId "
                      "AND IFNULL(m.Direction,'in')='in' AND LOWER(TRIM(IFNULL(m.FromEmail,'')))=?) "
                      "ORDER BY t.TaskId DESC LIMIT 1", (title.strip().lower(), from_email.strip().lower()))
        return r['TaskId'] if r else None
    def task_last_activity(self, task_id):
        r = self._one('SELECT MAX(x) last FROM (SELECT MAX(CreatedAt) x FROM comment WHERE TaskId=? UNION ALL '
                      'SELECT MAX(SentAt) FROM message WHERE TaskId=? UNION ALL SELECT MAX(IFNULL(UpdatedAt, StartedAt)) FROM run WHERE TaskId=?)',
                      (task_id, task_id, task_id))
        return (r or {}).get('last')
    def done_tasks_from(self, senders, limit=50):
        """Closed tasks that carried mail from any of these addresses (context.past_work)."""
        s = [x for x in senders if x]
        if not s: return []
        return self._rows(f"SELECT DISTINCT t.TaskId FROM task t JOIN message m ON m.TaskId=t.TaskId WHERE t.Status='done' "
                          f"AND lower(m.FromEmail) IN ({','.join('?' * len(s))}) ORDER BY t.TaskId DESC LIMIT ?", [*s, limit])
    def tasks_from_sender(self, sender, since, limit=3):
        """This sender's newest asks since `since`, dropped ones aside - how their work has been handled (context.sender_history)."""
        if not sender: return []
        return self._rows("SELECT t.TaskId, t.Title, t.Kind, t.Status, t.Tags, t.CreatedAt FROM task t WHERE t.CreatedAt >= ? "
                          "AND t.Status <> 'dropped' AND EXISTS (SELECT 1 FROM message m WHERE m.TaskId=t.TaskId AND lower(m.FromEmail)=?) "
                          "ORDER BY t.CreatedAt DESC, t.TaskId DESC LIMIT ?", (since, sender.lower(), limit))
    def tasks_open_linked(self, limit=80):
        """The OPEN tasks, newest activity first, each with the senders and conversations it carried - the
        open half of what triage is shown (context.recent_open) beside what closed lately."""
        return self._rows(
            "SELECT t.TaskId, t.Title, t.Status, t.Kind, t.Summary, t.Source, t.OriginBase, IFNULL(t.UpdatedAt, t.CreatedAt) Touched, "
            "       GROUP_CONCAT(DISTINCT lower(m.FromEmail)) Senders, GROUP_CONCAT(DISTINCT m.ConversationId) Convs "
            "  FROM task t LEFT JOIN message m ON m.TaskId=t.TaskId "
            f" WHERE t.Status NOT IN ('done','dropped') AND {WORK} "
            " GROUP BY t.TaskId ORDER BY IFNULL(t.UpdatedAt, t.CreatedAt) DESC LIMIT ?", (limit,))
    def tasks_open_brief(self, limit=40):
        """The OPEN tasks and Watching items, newest activity first, each with what triage read it to ask (ThreadJson), the channel and the
        name it first came from - one line each of the list every arrival is shown (context.open_items). Senders is who wrote on it, as
        tasks_open_linked has it, so a task someone sent is never read as the owner's own (context._own); Items are a batch's own titles,
        best first, since its title and summary are only a count."""
        first = "(SELECT m.{} FROM message m WHERE m.TaskId=t.TaskId AND IFNULL(m.Direction,'')<>'out' ORDER BY m.MessageId LIMIT 1)"
        return self._rows(
            "SELECT t.TaskId, t.Title, t.Summary, t.ThreadJson, t.WatchedAt, t.Source, t.OriginBase, t.CreatedAt, "
            f"       IFNULL(t.UpdatedAt, t.CreatedAt) Touched, {first.format('Channel')} Channel, {first.format('FromName')} FromName, "
            "       (SELECT GROUP_CONCAT(DISTINCT lower(IFNULL(m.FromEmail, m.FromName))) FROM message m WHERE m.TaskId=t.TaskId) Senders, "
            "       (SELECT GROUP_CONCAT(Title, ' ; ') FROM (SELECT b.Title FROM batch_item b WHERE b.TaskId=t.TaskId ORDER BY b.Place, b.ItemId)) Items "
            f"  FROM task t WHERE t.Status NOT IN ('done','dropped') AND {WORK} ORDER BY IFNULL(t.UpdatedAt, t.CreatedAt) DESC, t.TaskId DESC LIMIT ?", (limit,))
    def task_people(self, tids) -> dict:
        """{TaskId: [{name, email, channel}]} - who wrote on each task, by display name, never the owner's own lines: what a name on
        another channel is compared against (context.same_name)."""
        tids = [int(t) for t in tids if t][:200]
        if not tids: return {}
        out = {}
        for r in self._rows(f"SELECT DISTINCT TaskId, FromName, FromEmail, Channel FROM message WHERE TaskId IN ({','.join('?' * len(tids))}) "
                            "AND IFNULL(FromName,'')<>'' AND IFNULL(Status,'')<>'context' AND IFNULL(Direction,'')<>'out'", tuple(tids)):
            out.setdefault(r['TaskId'], []).append({'name': r['FromName'], 'email': r['FromEmail'] or '', 'channel': r['Channel'] or ''})
        return out
    def task_recipients(self, tids) -> dict:
        """{TaskId: {address}} - who each task's mail was written TO (its To and Cc lines), lower-cased: with task_people's senders,
        what says an arrival is written between the same people (context.recent_open)."""
        tids = [int(t) for t in tids if t][:200]
        if not tids: return {}
        out, rj = {}, "CASE WHEN json_valid(m.RecipientsJson) THEN m.RecipientsJson ELSE '{}' END"
        for r in self._rows(f"SELECT DISTINCT m.TaskId, lower(trim(j.value)) a FROM message m, json_each({rj}, '$.to') j WHERE m.TaskId IN ({','.join('?' * len(tids))}) "
                            f"UNION SELECT m.TaskId, lower(trim(j.value)) FROM message m, json_each({rj}, '$.cc') j WHERE m.TaskId IN ({','.join('?' * len(tids))})",
                            tuple(tids) * 2):
            if r['a']: out.setdefault(r['TaskId'], set()).add(r['a'])
        return out
    def tasks_owner_worked(self, since: str, before: str, limit=3):
        """The OPEN tasks the owner acted on (an audit row of theirs) between two stamps, last touched first, with when.
        What they had in hand when they sent a mail of their own (context.worked_before)."""
        return self._rows(
            "SELECT t.TaskId, t.Title, t.Summary, MAX(a.CreatedAt) Touched FROM audit a JOIN task t ON t.TaskId=CAST(a.EntityId AS INTEGER) "
            f" WHERE a.EntityType='task' AND a.Actor='owner' AND a.CreatedAt>=? AND a.CreatedAt<=? AND t.Status NOT IN ('done','dropped') AND {WORK} "
            " GROUP BY t.TaskId ORDER BY Touched DESC LIMIT ?", (since, before, limit))
    def owner_started(self, conversation_id):
        """The owner's own sent message that STARTED this thread, when no task holds the thread yet - else None."""
        if not conversation_id or self.task_for_conversation(conversation_id): return None
        rows = self._rows("SELECT * FROM message WHERE ConversationId=? AND IFNULL(Channel,'') NOT IN ('report','assistant','own') "
                          'ORDER BY SentAt, MessageId', (conversation_id,))
        mine = lambda r: r.get('Status') == 'context' or r.get('Direction') == 'out'
        m = rows[0] if rows and mine(rows[0]) else None
        if not m: return None
        # ...and never the owner's REPLY to somebody's mail: a sent copy stamped to the minute sorted seconds ahead of the mail it
        # answered, so triage was told "you started this thread" while working another task, and a second person's separate ask
        # joined that task (2026-11-02). Theirs from the same minute or earlier, or quoted in the owner's words, came first
        said, at = ' '.join(str(m.get('BodyText') or '').split()), str(m.get('SentAt') or '')[:16]
        quoted = lambda r: (q := ' '.join(str(r.get('BodyText') or '').split())[:200]) and q in said
        return None if any(str(r.get('SentAt') or '')[:16] <= at or quoted(r) for r in rows[1:] if not mine(r)) else m
    def tasks_closed_since(self, since: str, limit=60):
        """Tasks closed (done or dropped) on or after `since`, newest first, each with the senders and
        conversations it carried - enough for a caller to decide whether it touches the message in hand
        without a query per task (context.recent_closures, which runs inside the triage funnel)."""
        return self._rows(
            "SELECT t.TaskId, t.Title, t.Status, t.Summary, IFNULL(t.ClosedAt, t.UpdatedAt) Closed, "
            "       GROUP_CONCAT(DISTINCT lower(m.FromEmail)) Senders, GROUP_CONCAT(DISTINCT m.ConversationId) Convs "
            "  FROM task t LEFT JOIN message m ON m.TaskId=t.TaskId "
            " WHERE t.Status IN ('done','dropped') AND IFNULL(t.ClosedAt, t.UpdatedAt) >= ? "
            " GROUP BY t.TaskId ORDER BY Closed DESC LIMIT ?", (since, limit))
    # ── ideas: what the assistant said, and what the owner did about it ──────────────────────
    def list_ideas(self, status=None, mid=None):
        q, p = 'SELECT * FROM idea', []
        w = ([('Status=?', status)] if status else []) + ([('MessageId=?', mid)] if mid else [])
        if w: q += ' WHERE ' + ' AND '.join(k for k, _ in w); p = [v for _, v in w]
        return self._rows(q + ' ORDER BY IdeaId DESC', p)
    def get_idea(self, idea_id): return self._one('SELECT * FROM idea WHERE IdeaId=?', (idea_id,))
    def upsert_idea(self, s: dict, stamp: str) -> dict:
        """Said: a new key is born. Said AGAIN: the model's own idea (idea:<slug>) reopens AS IT WAS - the Advisor
        raises new ideas, it never edits one (the owner, 2026-09-25); its Sig is only its wording. A candidate the
        hub found (a follow-up, a quiet thread) reopens with the new facts and text, which is what its Sig tracks."""
        old = self._one('SELECT * FROM idea WHERE Key=?', (s['key'],))
        if old and is_model_idea(s['key']):
            self._exec("UPDATE idea SET Status='open', SnoozeUntil=NULL, LastSaid=?, SaidCount=SaidCount+1 WHERE Key=?", (stamp, s['key']))
            return self._one('SELECT * FROM idea WHERE Key=?', (s['key'],))
        action = dict(s.get('action') or {})
        if old:
            try: prior = json.loads(old.get('ActionJson') or '{}')
            except ValueError: prior = {}
            # Talking back is part of this suggestion's history. New facts may reopen and
            # rewrite the action, but must not erase the owner's correction or our answer.
            if prior.get('chat'): action['chat'] = prior['chat']
            # the shared verdict is history too: it stays until the facts (Sig) change, when triage_ideas re-judges
            if prior.get('triage') and 'triage' not in action: action['triage'] = prior['triage']
        act = json.dumps(action)
        if old:
            self._exec("UPDATE idea SET Kind=?, Text=?, ActionJson=?, Sig=?, Status='open', SnoozeUntil=NULL, LastSaid=?, SaidCount=SaidCount+1 WHERE Key=?",
                       (s.get('kind'), s['text'], act, s.get('sig'), stamp, s['key']))
        else:
            self._exec('INSERT INTO idea (Key, Kind, Text, ActionJson, Sig, Status, FirstSeen, LastSaid, SaidCount) VALUES (?,?,?,?,?,?,?,?,1)',
                       (s['key'], s.get('kind'), s['text'], act, s.get('sig'), 'open', stamp, stamp))
        # ...under the workstream of what it is about: its task's, else its message's (workstreams.py, 2026-11-01) - the idea's label
        try:
            from . import workstreams
            ws = (workstreams.of_task(self, int(action['tid'])) if action.get('tid') else '') or \
                 (workstreams.of_message(self, self.get_message(int(action['mid'])) or {}) if action.get('mid') else '')
            if ws: self._exec('UPDATE idea SET Workstream=? WHERE Key=?', (ws, s['key']))
        except Exception as e: logger.debug(f"idea {s['key']}: workstream not placed - {e}")
        return self._one('SELECT * FROM idea WHERE Key=?', (s['key'],))
    def set_idea_status(self, idea_id, status, by, until=None):
        self._exec('UPDATE idea SET Status=?, SnoozeUntil=?, DecidedBy=?, DecidedAt=? WHERE IdeaId=?', (status, until, by, _now(), idea_id))
    def set_idea_action(self, idea_id, action):
        self._exec('UPDATE idea SET ActionJson=? WHERE IdeaId=?', (json.dumps(action), idea_id))
    def set_ideas_message(self, ids, mid):
        if ids: self._exec(f"UPDATE idea SET MessageId=? WHERE IdeaId IN ({','.join('?' * len(ids))})", [mid, *ids])
    # ── the pipe (funnel.py): surfaced / done / later, per item key ─────────────────────────
    def funnel_states(self) -> dict:
        """Every funnel_state row by key. One pile build asks three times (the cards, the order, the alerts): ~4k rows each,
        read again only once something was written - every funnel_state write, in any process, moves DirtyGeneration and
        leaves a dirty row (its triggers), so the pair read in the same snapshot as the rows says whether they still hold."""
        if not self._off_writer(): return {r['Key']: r for r in self._rows('SELECT * FROM funnel_state')}
        with self._snapshot_read() as cur:
            mark = tuple(cur.execute('SELECT (SELECT DirtyGeneration FROM processing_reconcile_state WHERE Singleton=1), '
                                     '(SELECT COALESCE(MAX(Id),0) FROM processing_dirty_row)').fetchone())
            got = self._states_cache
            if got is None or got[0] != mark: got = self._states_cache = (mark, {r['Key']: dict(r) for r in cur.execute('SELECT * FROM funnel_state')})
        return {k: dict(v) for k, v in got[1].items()}
    def _units_shown(self, key, iid, picture, shown):
        """What the card pressed on SHOWED (processing_reads.drawn): the revision the press carried, else the card last
        drawn - never what landed after it was drawn. A card never drawn here is the item as it stands."""
        from . import processing_reads
        rev = shown.get(key) or shown.get('processing:' + iid) if isinstance(shown, dict) else shown
        got, now = processing_reads.shown_units(self, iid, rev), _units_of(picture)
        return now if got is None else [u for u in now if (u['entity_kind'], u['local_id']) in got]
    # A PICTURE IS READ BEFORE THE WRITER'S LOCK, NOT UNDER IT (the load run, 2026-11-24): a read receipt projects its whole item first,
    # and a 2,000-line chat's projection - 0.4 s idle, up to 8 s on a busy home - was read under the lock on every open of the row and
    # every line the Assistant mirrored onto it (101 s and 76 s of lock in one run): every press and every triage write queued behind it.
    # It is read on a reader snapshot first, and the write takes it while nothing it reads was written since - the rail's own test.
    def _ahead(self, find):
        """(dirty mark, item id, picture) for the item `find(cur)` names, read on a reader snapshot - None where there is no reader
        (a memory database, a thread already inside the lock) or no item: the write reads it under the lock as it always did."""
        if not self._off_writer(): return None
        from .processing_projection import processing_projection
        with self._snapshot_read() as cur:
            mark, iid = cur.execute('SELECT COALESCE(MAX(Id),0) FROM processing_dirty_row').fetchone()[0], find(cur)
            if not iid: return None
            picture = processing_projection(cur, iid); _units_of(picture)
            return mark, iid, picture
    def _picture(self, cur, iid, ahead=None):
        """The item's picture inside the writer's transaction: the one read ahead while no row it reads has been written since
        (processing_rail.touched names no change to it), else read now."""
        from . import processing_rail
        from .processing_projection import processing_projection
        if ahead and ahead[1] == iid:
            rows = processing_rail.dirty_since(cur, ahead[0])[1]
            if rows == (): return ahead[2]
            roots = None if rows is None else processing_rail.touched(cur, rows, lambda i: self._processing_follow(cur, i))[0]
            if roots is not None and iid not in roots: return ahead[2]
        return processing_projection(cur, iid)
    def set_funnel_state(self, key, status, by='owner', until=None, note=None, *, expected_context=None, read=False, shown=None):
        from . import processing_reads
        stamp = _now()
        # ...read ahead only for a write that reads the picture: Done, and a Surfaced that is a read or carries a note
        ahead = (self._ahead(lambda cur: processing_reads.active_version(cur) and (self._processing_read_target(cur, key) or (None,))[0])
                 if (status == 'done' or status == 'surfaced' and (read or note)) and not str(key).startswith('meeting:') else None)
        with self.lock:
            self._clear_stale(); cur = self.cx.cursor()
            cur.execute('BEGIN IMMEDIATE')
            try:
                version = processing_reads.active_version(cur)
                clean = bool(version) and not self._processing_reconcile_status_cursor(cur)['pending']
                if version and status in ('done', 'later', 'skip'):
                    calendar = str(key).startswith('meeting:')
                    target = ('', 'calendar', key) if calendar else self._processing_read_target(cur, key)
                    if target is None and str(key).split(':', 1)[0] in (
                            'processing', 'msg', 'report', 'review', 'idea', 'agent', 'wrap', 'task'):
                        raise ValueError('processing target is unavailable')
                    # ...AND THE PRESS IS NOT BEHIND THE CENSUS (the load run, 2026-11-24: Mark done waited up to 4.75 s on a whole-home
                    # census run inside it while mail kept landing). It puts down what its card showed (_units_shown) on the item as filed
                    # now; whatever the census moves is the membership worker's, behind it - mail filed onto the item since is unread news
                    if target is not None:
                        iid, kind, local_id = target
                        verified_picture = None
                        if not calendar and expected_context is not None:
                            verified_picture = self._picture(cur, iid, ahead)
                            if (not isinstance(expected_context, dict)
                                    or expected_context.get(iid) != verified_picture['context_revision']):
                                raise ValueError('processing context changed since confirmation was proposed')
                        if status == 'done':
                            if calendar:
                                current_units = [dict(entity_kind='calendar', local_id=key, fingerprint='identity-v1')]
                                deferred_keys = [key]
                            else:
                                picture = verified_picture or self._picture(cur, iid, ahead)
                                current_units = self._units_shown(key, iid, picture, shown)
                                deferred_keys = [d['key'] for d in picture['view']['processing_read']['deferrals']]
                            processing_reads.record(cur, current_units,
                                version=version, at=stamp, by=by, origin='explicit_done')
                            for deferred_key in deferred_keys:
                                cur.execute('DELETE FROM processing_read_defer WHERE Key=?', (deferred_key,))
                        else:
                            self._processing_write_defer(cur, key, target, status, until, stamp, by)
                # ...one picture for the read and the note, taken before the receipts: they change no context, which is all the note keeps
                target = self._processing_read_target(cur, key) if version and status == 'surfaced' and (read or note) else None
                picture = self._picture(cur, target[0], ahead) if target else None
                if target and read:
                    # shown in the chat IS read (the owner, 2026-09-06): the receipt is the same one an
                    # explicit done writes, minus lifting a deferral - later/skip still hold it back
                    processing_reads.record(cur, self._units_shown(key, target[0], picture, shown),
                                            version=version, at=stamp, by=by, origin='surfaced')
                if target and note:
                    cur.execute('''INSERT INTO processing_display_summary (Key,ContextRevision,Summary)
                        VALUES (?,?,?) ON CONFLICT(Key) DO UPDATE SET
                        ContextRevision=excluded.ContextRevision,Summary=excluded.Summary''',
                        (key, picture['context_revision'], str(note)))
                cur.execute('INSERT INTO funnel_state (Key,Status,Until,Note,By,At) VALUES (?,?,?,?,?,?) '
                    'ON CONFLICT(Key) DO UPDATE SET Status=excluded.Status, Until=excluded.Until, Note=excluded.Note, By=excluded.By, At=excluded.At',
                    (key, status, until, note, by, stamp))
                self._processing_finish_funnel_write(cur, clean)
                self.cx.commit()
                self._writes += 1
            except BaseException:
                self.cx.rollback()
                raise
            finally:
                cur.close()
        self._poke('feed-changed')                 # Unread is a feed filter; remove/read it immediately
    @contextlib.contextmanager
    def processing_own_words(self, tid, by='owner'):
        """Wrap a comment that mirrors the chat onto a task. Words said ABOUT an item are not news
        about it: a task Next had just marked read came straight back as unread because the assistant's
        own introduction changed its fingerprint one second later (the owner, 2026-09-06)."""
        from . import processing_reads
        from .processing_projection import processing_projection
        def item(cur):
            row = cur.execute('''SELECT ItemId FROM processing_member WHERE EntityKind='task' AND LocalId=?
                AND RetiredAt IS NULL''', (str(tid),)).fetchone()
            return self._processing_follow(cur, row['ItemId']) if row else None
        with self._processing_read() as cur:
            version = processing_reads.active_version(cur)
            before = processing_projection(cur, iid) if version and (iid := item(cur)) else None
            units_before = before['view']['processing_read']['units'] if before else []
            was_read = bool(units_before) and all(u['read'] for u in units_before)
        yield
        if not was_read: return
        ahead = self._ahead(item)                  # ...the words' picture read off the writer (_ahead), taken under it unless moved since
        with self.lock:
            self._clear_stale(); cur = self.cx.cursor(); cur.execute('BEGIN IMMEDIATE')
            try:
                after = self._picture(cur, iid, ahead) if (iid := item(cur)) else None
                if after: processing_reads.record(cur, _units_of(after), version=version, at=_now(), by=by, origin='own_words')
                self.cx.commit(); self._writes += 1
            except BaseException: self.cx.rollback(); raise
            finally: cur.close()
    def clear_funnel_state(self, key):
        """Forget one row's state entirely - it is new again. A new chat does this to an agent
        that is still waiting on you: shown once yesterday is not an answer."""
        # ...and forgetting a state nobody had is not news. The pile's own read clears an agent's notice on every transition it
        # announces (funnel.announce) - a stop or a finish had none - and the poke made every open tab rebuild the pile a second
        # time 1.5 s after the read that caused it (the intake walk, 2026-10-26: one mail arriving, two full rail reloads)
        if self._clear_funnel_compat('Key=?', (key,)): self._poke('feed-changed')
    def clear_funnel_states(self, statuses=('surfaced',)):
        """A new chat walks the pile afresh: what was merely SHOWN comes back; what the owner
        decided (done, later) stands."""
        if statuses:
            if self._clear_funnel_compat(f"Status IN ({','.join('?' * len(statuses))})", list(statuses)): self._poke('feed-changed')

    @staticmethod
    def _processing_finish_funnel_write(cur, clean):
        # Only this transaction's funnel_state trigger changed the census. No
        # entity/FK can move under BEGIN IMMEDIATE. Never clear earlier raw dirt.
        if clean:
            cur.execute('''UPDATE processing_reconcile_state
                SET AttemptedGeneration=DirtyGeneration, ReconciledGeneration=DirtyGeneration
                WHERE Singleton=1''')

    def _clear_funnel_compat(self, where, params):
        from .processing_reads import active_version
        with self.lock:
            self._clear_stale(); cur = self.cx.cursor()
            cur.execute('BEGIN IMMEDIATE')
            try:
                clean = bool(active_version(cur)) and not self._processing_reconcile_status_cursor(cur)['pending']
                cur.execute('DELETE FROM funnel_state WHERE ' + where, params)
                gone = cur.rowcount
                self._processing_finish_funnel_write(cur, clean)
                self.cx.commit()
                self._writes += 1
                return gone
            except BaseException:
                self.cx.rollback()
                raise
            finally:
                cur.close()
    # ── canonical processing inventory (Phase 1 additive foundation) ────────────
    def processing_reads_active(self):
        from .processing_reads import active_version
        with self._processing_read() as cur:
            return bool(active_version(cur))

    def processing_calendar_states(self):
        """The explicit legacy-calendar exception; no canonical calendar allocation."""
        with self._processing_read() as cur:
            result = {row['LocalId']: {'read': True} for row in cur.execute('''
                SELECT LocalId FROM processing_read_receipt
                WHERE EntityKind='calendar' AND Fingerprint='identity-v1' ''').fetchall()}
            for row in cur.execute('''SELECT * FROM processing_read_defer
                WHERE TargetEntityKind='calendar' ''').fetchall():
                result.setdefault(row['TargetLocalId'], {'read': False}).update(
                    status=row['Status'], until=row['Until'], at=row['At'], by=row['By'])
            return result

    def activate_processing_reads(self, *, fixed_now, live_state=None):
        """Explicit, fresh legacy capture and activation in one writer transaction.

        The caller owns the consistent backup and startup admission barrier. A
        dirty census fails closed; constructors and getters never activate reads.
        """
        return self.backfill_processing('canonical-reads-' + uuid.uuid4().hex,
            fixed_now=fixed_now, live_state=live_state, _activate_reads=True)

    def processing_item_ideas(self, key):
        """The Advisor ideas a rail row IS - none when a task is the row, since the task decides then."""
        with self._processing_read() as cur:
            t = self._processing_read_target(cur, key)
            if not t: return []
            rows = cur.execute('SELECT EntityKind,LocalId FROM processing_member WHERE ItemId=? AND RetiredAt IS NULL', (t[0],)).fetchall()
        if any(r['EntityKind'] == 'task' for r in rows): return []
        return [int(r['LocalId']) for r in rows if r['EntityKind'] == 'idea']

    def _processing_read_target(self, cur, key):
        if str(key).startswith('processing:'):
            iid = self._processing_follow(cur, str(key).split(':', 1)[1])
            return (iid, None, None) if iid else None
        row = cur.execute('''SELECT a.EntityKind,a.LocalId,m.ItemId FROM processing_alias a
            JOIN processing_member m ON m.EntityKind=a.EntityKind AND m.LocalId=a.LocalId
            WHERE a.Namespace='legacy_funnel' AND a.Scope='local' AND a.Value=?
              AND a.RetiredAt IS NULL AND m.RetiredAt IS NULL''', (key,)).fetchone()
        return ((self._processing_follow(cur, row['ItemId']), row['EntityKind'], row['LocalId'])
                if row else None)

    @staticmethod
    def _processing_write_defer(cur, key, target, status, until, at, by):
        iid, kind, local_id = target
        cur.execute('''INSERT INTO processing_read_defer
            (Key,TargetItemId,TargetEntityKind,TargetLocalId,Status,Until,At,By)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(Key) DO UPDATE SET
            TargetItemId=excluded.TargetItemId,TargetEntityKind=excluded.TargetEntityKind,
            TargetLocalId=excluded.TargetLocalId,Status=excluded.Status,Until=excluded.Until,
            At=excluded.At,By=excluded.By''', (key, iid, kind, local_id, status, until, at, by))

    @staticmethod
    def _processing_reconcile_status_cursor(cur):
        row = cur.execute('''SELECT * FROM processing_reconcile_state
            WHERE Singleton=1''').fetchone()
        if row is None:
            raise RuntimeError('processing reconciliation state is missing')
        dirty = int(row['DirtyGeneration'])
        attempted = int(row['AttemptedGeneration'])
        reconciled = int(row['ReconciledGeneration'])
        conflicts = json.loads(row['ConflictsJson'] or '[]')
        diagnostics = json.loads(row['DiagnosticsJson'] or '[]')
        if dirty == reconciled:
            status = 'complete'
        elif attempted == dirty and conflicts:
            status = 'conflicted'
        else:
            status = 'pending'
        return {
            'dirty_generation': dirty,
            'attempted_generation': attempted,
            'reconciled_generation': reconciled,
            'pending': dirty != reconciled,
            'status': status,
            'conflicts': conflicts,
            'diagnostics': diagnostics,
            'last_attempt_at': row['LastAttemptAt'],
        }

    def processing_reconcile_status(self):
        """Return generation/diagnostic state without allocating canonical identity."""
        with self._processing_read() as cur:
            return self._processing_reconcile_status_cursor(cur)

    def processing_census_due(self):
        """The MembershipGeneration a census would read, when the next reconcile would run one (something it reads was
        written since the last clean census) - else None, and the next reconcile only advances the generations."""
        with self._processing_read() as cur:
            r = cur.execute('SELECT * FROM processing_reconcile_state WHERE Singleton=1').fetchone()
            due = r['DirtyGeneration'] != r['AttemptedGeneration'] and r['MembershipGeneration'] != r['CensusGeneration']
            return r['MembershipGeneration'] if due else None

    def _census_plan(self, cur, stamp):
        """What a census would do, read on `cur`: the reconcile state, the MembershipGeneration it was read at, whether the census
        can be skipped (nothing it reads moved since a clean one), and its writes and result - worked out in Python, with no lock."""
        from .processing_membership import census_current, census_inputs, plan_membership
        before = self._processing_reconcile_status_cursor(cur)
        gen = cur.execute('SELECT MembershipGeneration FROM processing_reconcile_state WHERE Singleton=1').fetchone()[0]
        if before['dirty_generation'] == before['reconciled_generation']: return {'before': before, 'current': True}
        if census_current(cur):         # only writes the census never reads: its answer cannot have moved
            return {'before': before, 'current': False, 'gen': gen, 'skip': True, 'ops': [],
                    'result': {**dict.fromkeys(_CENSUS_COUNTS, 0), 'conflicts': before['conflicts'], 'diagnostics': before['diagnostics']}}
        ops, result = plan_membership(census_inputs(cur), stamp=stamp, new_item_id=self._processing_item_id)
        return {'before': before, 'current': False, 'gen': gen, 'skip': False, 'ops': ops, 'result': result}

    def _census_apply(self, cur, plan, ops, last, stamp):
        """One turn of a planned census on the writer: False when something it read was written since the last turn (plan['gen'],
        None for a plan made in this very transaction) - else its writes, and on the last turn the bookkeeping."""
        gen = lambda: cur.execute('SELECT MembershipGeneration FROM processing_reconcile_state WHERE Singleton=1').fetchone()[0]
        if plan['gen'] is not None and gen() != plan['gen']: return False
        for q, p in ops: cur.execute(q, p)
        plan['gen'] = gen()
        return self._census_finish(cur, plan, stamp) if last else True

    def _census_finish(self, cur, plan, stamp):
        "The census's bookkeeping, in the transaction that applied its last write."
        from .processing_membership import mark_census
        from . import processing_rail
        st, result = self._processing_reconcile_status_cursor(cur), plan['result']
        complete = not result['conflicts']
        if not plan['skip']: mark_census(cur, complete)
        # a write the census does not read may have landed since it was planned: it settles with it, as under one transaction
        cur.execute('''UPDATE processing_reconcile_state SET AttemptedGeneration=?, ReconciledGeneration=?, LastAttemptAt=?,
            ConflictsJson=?, DiagnosticsJson=? WHERE Singleton=1''',
            (st['dirty_generation'], st['dirty_generation'] if complete else st['reconciled_generation'], stamp,
             json.dumps(result['conflicts'], sort_keys=True), json.dumps(result['diagnostics'], sort_keys=True)))
        after = self._processing_reconcile_status_cursor(cur)
        processing_rail.trim(self.cx)        # the rail needs only the recent dirty rows
        return {**after, **result, 'status': 'complete' if complete else 'conflicted'}

    def _census_turn(self, run):
        "One short BEGIN IMMEDIATE on the writer: run(cur) inside it; commit what it wrote unless it answers False."
        with self.lock:
            self._clear_stale(); cur = self.cx.cursor(); cur.execute('BEGIN IMMEDIATE')
            try:
                out = run(cur)
                if out is False: self.cx.rollback()
                else: self.cx.commit(); self._writes += 1
                return out
            except BaseException:
                self.cx.rollback()
                raise
            finally:
                cur.close()

    def reconcile_processing_membership(self, *, fixed_now=None):
        """Reconcile exact raw entity relationships, uncapped.

        This is an explicit startup/background operation. Inventory and API getters
        never call it, and it does not infer read, defer, action, or provider identity.

        THE CENSUS NEVER HOLDS THE WRITER FOR ITS WHOLE PASS (2026-11-23): one BEGIN IMMEDIATE held store.lock ~4 s on a real
        mailbox, every press and the list waiting up to 10 s behind it. It is read on a reader snapshot and worked out with no
        lock; its writes go in turns of CENSUS_CHUNK, the lock let go between. Each turn first finds MembershipGeneration where
        the last one left it - else something the census read was written in between, and it is planned again from what is
        there now (which carries on from the turns already applied). After CENSUS_TRIES such races, one pass under one lock.
        """
        stamp = fixed_now or _now()
        if not isinstance(stamp, str) or not stamp:
            raise ValueError('fixed_now must be a non-empty string')
        def already(plan): return {**plan['before'], **dict.fromkeys(_CENSUS_COUNTS, 0), 'status': 'already_current'}
        for _ in range(CENSUS_TRIES):
            with self._processing_read() as cur: plan = self._census_plan(cur, stamp)
            if plan['current']: return already(plan)
            chunks = [plan['ops'][i:i + CENSUS_CHUNK] for i in range(0, len(plan['ops']), CENSUS_CHUNK)] or [[]]
            for i, chunk in enumerate(chunks):
                out = self._census_turn(lambda cur: self._census_apply(cur, plan, chunk, i == len(chunks) - 1, stamp))
                if out is False: break
                if i < len(chunks) - 1: time.sleep(0.001)     # the lock is not fair: let whoever waits for it in before the next turn
            else: return out
        def under_lock(cur):
            plan = self._census_plan(cur, stamp)
            return already(plan) if plan['current'] else self._census_apply(cur, {**plan, 'gen': None}, plan['ops'], True, stamp)
        return self._census_turn(under_lock)

    @staticmethod
    def _processing_item_id():
        """Opaque identity: source ids and changing funnel keys never become the primary key."""
        return 'pi_' + uuid.uuid4().hex

    @staticmethod
    def _processing_follow(cur, item_id):
        seen, current = set(), item_id
        while current and current not in seen:
            seen.add(current)
            row = cur.execute('SELECT RedirectItemId FROM processing_item WHERE ItemId=?', (current,)).fetchone()
            if not row: return None
            if not row[0]: return current
            current = row[0]
        raise ValueError(f'processing item redirect cycle at {item_id}')

    @classmethod
    def _processing_lineage(cls, cur, resolved):
        return [r['ItemId'] for r in cur.execute('SELECT ItemId FROM processing_item').fetchall()
                if cls._processing_follow(cur, r['ItemId']) == resolved]

    def reconcile_processing_entities(self, *, kind, members, aliases=(), item_id=None,
                                      context_revision=None, view_revision=None, fixed_now=None):
        """Attach newly persisted exact entities without activating the new read model.

        Existing membership wins, so an FYI can later become a task without changing its item id.
        Entities already owned by different items require ``merge_processing_items``; conversation
        ids, external ids and display names never merge items implicitly.
        """
        stamp = fixed_now or _now()
        clean = []
        for member in members or ():
            entity_kind, local_id = str(member.get('entity_kind') or ''), str(member.get('local_id') or '')
            if not entity_kind or not local_id: raise ValueError('processing members require entity_kind and local_id')
            clean.append({'entity_kind': entity_kind, 'local_id': local_id,
                          'role': str(member.get('role') or 'member')})
        if not clean: raise ValueError('a processing item requires at least one member')
        exact = {(m['entity_kind'], m['local_id']) for m in clean}
        clean_aliases = []
        for alias in aliases or ():
            a = {k: str(alias.get(k) or '') for k in
                 ('namespace', 'scope', 'value', 'entity_kind', 'local_id', 'provenance')}
            if not all(a.values()): raise ValueError('processing aliases require namespace, scope, value, exact entity and provenance')
            if (a['entity_kind'], a['local_id']) not in exact:
                raise ValueError('processing alias target must be one of the reconciled exact entities')
            clean_aliases.append(a)
        with self.lock:
            self._clear_stale(); cur = self.cx.cursor(); cur.execute('BEGIN IMMEDIATE')
            try:
                existing = set()
                for member in clean:
                    row = cur.execute('''SELECT ItemId FROM processing_member
                                         WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL''',
                                      (member['entity_kind'], member['local_id'])).fetchone()
                    if row: existing.add(self._processing_follow(cur, row[0]))
                if item_id:
                    chosen = self._processing_follow(cur, str(item_id))
                    if not chosen: raise KeyError(f'unknown processing item {item_id}')
                    if existing and existing != {chosen}: raise ValueError('entities belong to another item; merge explicitly')
                elif len(existing) > 1: raise ValueError('entities belong to multiple items; merge explicitly')
                elif existing: chosen = next(iter(existing))
                else:
                    chosen = self._processing_item_id()
                    cur.execute('''INSERT INTO processing_item
                        (ItemId,Kind,ContextRevision,ViewRevision,CreatedAt,UpdatedAt) VALUES (?,?,?,?,?,?)''',
                        (chosen, str(kind), context_revision, view_revision, stamp, stamp))
                primary = cur.execute("SELECT 1 FROM processing_member WHERE ItemId=? AND Role='primary' AND RetiredAt IS NULL", (chosen,)).fetchone()
                for i, member in enumerate(clean):
                    old = cur.execute('''SELECT ItemId FROM processing_member
                                         WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL''',
                                      (member['entity_kind'], member['local_id'])).fetchone()
                    if old:
                        if self._processing_follow(cur, old['ItemId']) != chosen:
                            raise ValueError('entity belongs to another item; merge explicitly')
                        continue
                    role = member['role']
                    if role == 'primary' and primary: role = 'member'
                    if not primary and (role == 'primary' or i == 0): role, primary = 'primary', True
                    cur.execute('''INSERT INTO processing_member
                        (ItemId,EntityKind,LocalId,Role,JoinedAt) VALUES (?,?,?,?,?)''',
                        (chosen, member['entity_kind'], member['local_id'], role, stamp))
                for alias in clean_aliases:
                    old = cur.execute('''SELECT EntityKind,LocalId FROM processing_alias
                        WHERE Namespace=? AND Scope=? AND Value=? AND RetiredAt IS NULL''',
                        (alias['namespace'], alias['scope'], alias['value'])).fetchone()
                    if old and (old['EntityKind'], old['LocalId']) != (alias['entity_kind'], alias['local_id']):
                        raise ValueError('processing alias already identifies another exact entity')
                    if not old:
                        cur.execute('''INSERT INTO processing_alias
                            (Namespace,Scope,Value,EntityKind,LocalId,Provenance,CreatedAt)
                            VALUES (?,?,?,?,?,?,?)''',
                            (alias['namespace'], alias['scope'], alias['value'], alias['entity_kind'],
                             alias['local_id'], alias['provenance'], stamp))
                # Reconciliation changes the item's inputs. A caller may supply freshly computed
                # revisions; otherwise invalidate them rather than retaining a stale fingerprint.
                cur.execute('''UPDATE processing_item SET Kind=?, ContextRevision=?,
                    ViewRevision=?, UpdatedAt=? WHERE ItemId=?''',
                    (str(kind), context_revision, view_revision, stamp, chosen))
                self.cx.commit(); self._writes += 1
                return chosen
            except BaseException:
                self.cx.rollback(); raise

    def merge_processing_items(self, source_item_id, target_item_id, *, fixed_now=None):
        """Explicitly redirect one item while retaining old memberships and alias receipts."""
        stamp = fixed_now or _now()
        with self.lock:
            self._clear_stale(); cur = self.cx.cursor(); cur.execute('BEGIN IMMEDIATE')
            try:
                source = self._processing_follow(cur, str(source_item_id))
                target = self._processing_follow(cur, str(target_item_id))
                if not source or not target: raise KeyError('unknown processing item')
                if source == target: self.cx.commit(); return target
                target_primary = cur.execute("SELECT 1 FROM processing_member WHERE ItemId=? AND Role='primary' AND RetiredAt IS NULL", (target,)).fetchone()
                for row in cur.execute('SELECT * FROM processing_member WHERE ItemId=? AND RetiredAt IS NULL', (source,)).fetchall():
                    cur.execute('UPDATE processing_member SET RetiredAt=? WHERE MemberId=?', (stamp, row['MemberId']))
                    duplicate = cur.execute('''SELECT 1 FROM processing_member WHERE EntityKind=? AND LocalId=?
                                               AND RetiredAt IS NULL''', (row['EntityKind'], row['LocalId'])).fetchone()
                    if duplicate: continue
                    role = row['Role'] if row['Role'] != 'primary' or not target_primary else 'member'
                    cur.execute('''INSERT INTO processing_member
                        (ItemId,EntityKind,LocalId,Role,JoinedAt) VALUES (?,?,?,?,?)''',
                        (target, row['EntityKind'], row['LocalId'], role, stamp))
                    if role == 'primary': target_primary = True
                cur.execute('UPDATE processing_item SET RedirectItemId=?,UpdatedAt=? WHERE ItemId=?', (target, stamp, source))
                cur.execute('UPDATE processing_item SET ContextRevision=NULL,ViewRevision=NULL,UpdatedAt=? WHERE ItemId=?',
                            (stamp, target))
                self.cx.commit(); self._writes += 1; return target
            except BaseException:
                self.cx.rollback(); raise

    @contextlib.contextmanager
    def _processing_read(self):
        """Hold one SQLite snapshot across related reads, including external merges - on a reader connection (_off_writer),
        which is the same snapshot without the writer's lock. Inside _writer_reads(): on the writer, for a read whose answer
        is compared with that connection's own counters (total_changes, data_version), which only its snapshot can answer."""
        if not getattr(_ON_WRITER, 'on', False) and self._off_writer():
            with self._snapshot_read() as cur: yield cur
            return
        with self.lock:
            self._clear_stale(); cur = self.cx.cursor()
            cur.execute('BEGIN')
            try:
                yield cur
            except BaseException:
                self.cx.rollback()
                raise
            else:
                self.cx.commit()
            finally:
                cur.close()

    def resolve_processing_target(self, namespace, value, scope='local'):
        """Resolve an alias to both its durable item and the exact entity it names."""
        if not namespace or not value or not scope: raise ValueError('namespace, scope and value are required')
        with self._processing_read() as cur:
            alias = cur.execute('''SELECT * FROM processing_alias WHERE Namespace=? AND Scope=? AND Value=?
                                   AND RetiredAt IS NULL ORDER BY AliasId DESC LIMIT 1''',
                                (str(namespace), str(scope), str(value))).fetchone()
            if not alias: return None
            member = cur.execute('''SELECT ItemId FROM processing_member WHERE EntityKind=? AND LocalId=?
                                    AND RetiredAt IS NULL ORDER BY MemberId DESC LIMIT 1''',
                                 (alias['EntityKind'], alias['LocalId'])).fetchone()
            if not member: return None
            resolved = self._processing_follow(cur, member['ItemId'])
            return {'item_id': resolved, 'entity_kind': alias['EntityKind'], 'local_id': alias['LocalId'],
                    'namespace': alias['Namespace'], 'scope': alias['Scope'], 'value': alias['Value'],
                    'provenance': alias['Provenance'],
                    'redirected_from': member['ItemId'] if member['ItemId'] != resolved else None}

    def processing_members(self, item_id, *, include_retired=False):
        with self._processing_read() as cur:
            resolved = self._processing_follow(cur, str(item_id))
            if not resolved: return []
            if not include_retired:
                return [dict(r) for r in cur.execute('''SELECT * FROM processing_member WHERE ItemId=?
                                                        AND RetiredAt IS NULL ORDER BY MemberId''', (resolved,)).fetchall()]
            item_ids = self._processing_lineage(cur, resolved)
            return [dict(r) for r in cur.execute(
                f"SELECT * FROM processing_member WHERE ItemId IN ({','.join('?' * len(item_ids))}) ORDER BY MemberId",
                item_ids).fetchall()]

    @staticmethod
    def _processing_evidence_row(row):
        out = dict(row)
        for old, new in (('EvidenceId', 'evidence_id'), ('MigrationVersion', 'migration_version'),
                         ('ItemId', 'item_id'), ('EntityKind', 'entity_kind'), ('LocalId', 'local_id'),
                         ('SelectedLegacyKey', 'selected_key'), ('ContextFingerprint', 'context_fingerprint'),
                         ('CapturedAt', 'captured_at')):
            out[new] = out.pop(old)
        value = out.pop('ObservedUnread'); out['observed_unread'] = None if value is None else bool(value)
        value = out.pop('PermanentRead'); out['permanent_read'] = None if value is None else bool(value)
        out['reasons'] = json.loads(out.pop('ReasonsJson') or '[]')
        raw = out.pop('TemporaryDeferJson'); out['temporary_defer'] = json.loads(raw) if raw else None
        out['original'] = json.loads(out.pop('OriginalJson') or '{}')
        return out

    def processing_legacy_evidence(self, version=None, *, entity_kind=None, local_id=None):
        q, p = 'SELECT * FROM processing_legacy_evidence WHERE 1=1', []
        if version is not None: q += ' AND MigrationVersion=?'; p.append(str(version))
        if entity_kind is not None: q += ' AND EntityKind=?'; p.append(str(entity_kind))
        if local_id is not None: q += ' AND LocalId=?'; p.append(str(local_id))
        return [self._processing_evidence_row(r) for r in self._rows(q + ' ORDER BY EvidenceId', p)]

    def _processing_snapshot_cursor(self, cur, resolved, *, live_state=None, lineage=None, item=None,
                                    include_history=True, display_only=False, pre=None):
        """Build the public item picture inside a caller-owned read transaction."""
        from .processing_projection import processing_projection
        if item is None:
            row = cur.execute('SELECT * FROM processing_item WHERE ItemId=?', (resolved,)).fetchone()
            if not row: return None
            item = dict(row)
        else:
            item = dict(item)
        lineage = list(lineage) if lineage is not None else self._processing_lineage(cur, resolved)
        # All and Unread need the current projection plus the old root ids that remain valid
        # aliases. They do not consume the captured migration evidence/context history. Loading
        # those large JSON records for every root made a five-row Timeline request materialize
        # and hash tens of megabytes before it could draw anything. Keep the complete snapshot as
        # the default contract; display inventory opts into this deliberately smaller envelope.
        if display_only:
            projection = processing_projection(cur, resolved, live_state=live_state, pre=pre)
            return {
                'item': item,
                'item_history': [{'ItemId': item_id} for item_id in lineage],
                'members': [],
                'member_history': [],
                'aliases': list(projection.get('view', {}).get('aliases', [])),
                'relations': [],
                'legacy_evidence': [],
                'context_history': [],
                **projection,
            }
        item_history = [dict(r) for r in cur.execute(
            f"SELECT * FROM processing_item WHERE ItemId IN ({','.join('?' * len(lineage))}) ORDER BY CreatedAt,ItemId",
            lineage).fetchall()]
        members = [dict(r) for r in cur.execute('''SELECT * FROM processing_member
                                                   WHERE ItemId=? AND RetiredAt IS NULL ORDER BY MemberId''', (resolved,))]
        member_history = [dict(r) for r in cur.execute(
            f"SELECT * FROM processing_member WHERE ItemId IN ({','.join('?' * len(lineage))}) ORDER BY MemberId",
            lineage).fetchall()]
        aliases_by_id = {}
        for member in member_history:
            for row in cur.execute('''SELECT * FROM processing_alias
                WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL ORDER BY AliasId''',
                (member['EntityKind'], member['LocalId'])).fetchall():
                aliases_by_id[row['AliasId']] = dict(row)
        aliases = [aliases_by_id[key] for key in sorted(aliases_by_id)]
        if not include_history:
            return {'item': item, 'item_history': item_history, 'members': members,
                    'aliases': aliases, **processing_projection(cur, resolved, live_state=live_state)}
        evidence_by_id = {r['EvidenceId']: r for r in cur.execute(
            f"SELECT * FROM processing_legacy_evidence WHERE ItemId IN ({','.join('?' * len(lineage))}) ORDER BY EvidenceId",
            lineage).fetchall()}
        # A split moves one exact entity without redirecting the old root, because
        # that root still owns another current component. Carry the entity's frozen
        # read evidence into its new snapshot while retaining the original ItemId.
        for member in members:
            for row in cur.execute('''SELECT * FROM processing_legacy_evidence
                WHERE EntityKind=? AND LocalId=? ORDER BY EvidenceId''',
                (member['EntityKind'], member['LocalId'])).fetchall():
                evidence_by_id[row['EvidenceId']] = row
        evidence = [self._processing_evidence_row(evidence_by_id[key])
                    for key in sorted(evidence_by_id)]
        context_history = [dict(r) for r in cur.execute(
            f"SELECT * FROM processing_context_snapshot WHERE ItemId IN ({','.join('?' * len(lineage))}) ORDER BY MigrationVersion,ItemId",
            lineage).fetchall()]
        exact = {(m['EntityKind'], m['LocalId']) for m in member_history}
        related = [dict(r) for r in cur.execute(
            'SELECT * FROM processing_relation WHERE RetiredAt IS NULL ORDER BY RelationId').fetchall()
                   if (r['FromEntityKind'], r['FromLocalId']) in exact
                   or (r['ToEntityKind'], r['ToLocalId']) in exact]
        return {'item': item, 'item_history': item_history, 'members': members,
                'member_history': member_history, 'aliases': aliases,
                'relations': related, 'legacy_evidence': evidence, 'context_history': context_history,
                **processing_projection(cur, resolved, live_state=live_state)}

    def processing_snapshot(self, item_id, *, live_state=None):
        """Read current fingerprints and preserved history without creating read receipts.

        Top-level revisions are computed from current persisted inputs; nullable
        revisions in ``item`` are historical capture/cache metadata, not freshness
        certification. Native worker attention is an explicit caller snapshot.
        """
        live_state = None if live_state is None else copy.deepcopy(tuple(live_state))
        with self._processing_read() as cur:
            resolved = self._processing_follow(cur, str(item_id))
            if not resolved: return None
            return self._processing_snapshot_cursor(cur, resolved, live_state=live_state)

    def processing_inventory_snapshot(self, *, fixed_now, live_state=None, display_only=False,
                                      history_days=None, include_history=True):
        """Read the complete, non-activating canonical inventory from one SQLite snapshot.

        This reports gaps in explicit membership but never allocates identity, infers read or
        action state, calls a worker, or changes which runtime views consume legacy storage.
        """
        if not isinstance(fixed_now, str) or not fixed_now:
            raise ValueError('fixed_now must be a non-empty string')
        if history_days is not None and (isinstance(history_days, bool) or not isinstance(history_days, int)
                                         or not 0 <= history_days <= 36500):
            raise ValueError('history_days must be between 0 and 36500')
        as_of = fixed_now
        frozen_live = None if live_state is None else copy.deepcopy(tuple(live_state))
        from .processing_projection import _worker_attention
        worker_rows = [] if frozen_live is None else sorted(
            (_worker_attention(row) for row in frozen_live),
            key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':'), allow_nan=False))
        worker_payload = {'available': frozen_live is not None, 'rows': worker_rows}
        worker_revision = hashlib.sha256(json.dumps(
            worker_payload, ensure_ascii=False, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if display_only and frozen_live is not None:
            frozen_live = tuple(copy.deepcopy(worker_rows))

        def apply_workers(snapshot):
            """Overlay volatile worker facts without re-reading every canonical DB root."""
            if not display_only:
                return snapshot
            from .processing import processing_view_revision
            available = frozen_live is not None
            for item in snapshot['items']:
                view = item['view']
                tids = {str(task['TaskId']) for task in view.get('tasks', [])}
                attention = sorted((copy.deepcopy(row) for row in worker_rows
                                    if str(row.get('taskId', row.get('task_id'))) in tids),
                                   key=lambda row: json.dumps(row, sort_keys=True))
                if (view.get('worker_attention_available') != available
                        or view.get('worker_attention', []) != attention):
                    view['worker_attention_available'] = available
                    view['worker_attention'] = attention
                    item['view_revision'] = processing_view_revision(item['context_revision'], view)
            snapshot['worker_attention_available'] = available
            snapshot['worker_input_revision'] = worker_revision
            return snapshot

        # Current projections are pure functions of database content, the history window and the
        # supplied native-worker observation. Reuse that work across Unread and All until a local
        # write changes the database. Do not consult PRAGMA data_version on the shared writer
        # connection here: that made a cache HIT wait behind a running sync's SQLite lock. The
        # membership reconciler turns supported external inserts into a local generation change;
        # rebuilding merely because a timer ticked would recreate the periodic loading bug.
        # Include the date because the history cutoff moves at midnight even if nothing was written.
        from . import processing_rail
        if display_only:
            # the rail: re-project what a write touched, reuse the rest (processing_rail)
            snapshot, hashes = self._rail_read(as_of=as_of, history_days=history_days, frozen_live=frozen_live,
                                               worker_revision=worker_revision)
            snapshot = apply_workers(snapshot)
            snapshot['snapshot_revision'] = processing_rail.revision(snapshot, hashes)
            return snapshot

        # The expensive relational projection is database-only. Worker telemetry is overlaid
        # afterwards, so a changing terminal tail re-hashes its one owned item instead of issuing
        # the queries for every item in the Timeline again.
        projection_live = ([] if frozen_live is not None else None) if display_only else frozen_live
        with self._writer_reads(), self._processing_read() as cur:
            cache_key = None
            if not display_only and not include_history:
                cache_key = (self.cx.total_changes,
                             cur.execute('PRAGMA data_version').fetchone()[0], worker_revision)
                cached = getattr(self, '_processing_runtime_inventory_cache', None)
                if cached is not None and cached[0] == cache_key:
                    snapshot = _snapcopy(cached[1])
                    snapshot['as_of'] = as_of
                    snapshot.pop('snapshot_revision', None)
                    snapshot['snapshot_revision'] = hashlib.sha256(json.dumps(
                        snapshot, ensure_ascii=False, sort_keys=True,
                        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
                    return snapshot
            item_rows = [dict(r) for r in cur.execute(
                'SELECT * FROM processing_item ORDER BY ItemId').fetchall()]
            roots = {row['ItemId']: row for row in item_rows if row['RedirectItemId'] is None}
            lineage_by_root = {item_id: [] for item_id in roots}
            for row in item_rows:
                resolved = self._processing_follow(cur, row['ItemId'])
                if resolved in lineage_by_root: lineage_by_root[resolved].append(row['ItemId'])
            selected_roots = set(roots)
            items = [self._processing_snapshot_cursor(
                cur, item_id, live_state=projection_live,
                lineage=lineage_by_root[item_id], item=roots[item_id],
                include_history=include_history, display_only=display_only)
                for item_id in sorted(selected_roots)]

            member_count = cur.execute('''SELECT COUNT(*) FROM processing_member pm
                JOIN processing_item pi ON pi.ItemId=pm.ItemId
                WHERE pm.RetiredAt IS NULL AND pi.RedirectItemId IS NULL''').fetchone()[0]
            # Mail the census deliberately never groups is not mail MISSING from it. Counting it
            # here would stop the Timeline dead: compact_inventory refuses while any of these is
            # non-zero, so a flood sender would degrade every read forever. This exclusion and
            # processing_membership.UNGROUPED_MESSAGE_STATUS are one decision - move them together.
            from .processing_membership import ungrouped_message_sql
            ungrouped, ungrouped_params = ungrouped_message_sql('source')
            uncatalogued = {}
            for entity_kind, table, column, extra, extra_params in (
                    ('message', 'message', 'MessageId', f' AND NOT {ungrouped}', ungrouped_params),
                    ('task', 'task', 'TaskId', '', ()),
                    ('review', 'review', 'ReviewId', '', ()),
                    ('idea', 'idea', 'IdeaId', '', ())):
                uncatalogued[entity_kind] = cur.execute(f'''SELECT COUNT(*) FROM {table} source
                    WHERE NOT EXISTS (SELECT 1 FROM processing_member pm
                        JOIN processing_item pi ON pi.ItemId=pm.ItemId
                        WHERE pm.EntityKind=? AND pm.LocalId=CAST(source.{column} AS TEXT)
                          AND pm.RetiredAt IS NULL AND pi.RedirectItemId IS NULL){extra}''',
                    (entity_kind, *extra_params)).fetchone()[0]
            completed = [r[0] for r in cur.execute('''SELECT Version FROM processing_migration
                WHERE Completion='complete' ORDER BY Version''').fetchall()]
            coverage = {
                'canonical_item_count': len(roots),
                'visible_item_count': sum(bool(item['member_ids']) for item in items),
                'tombstone_item_count': sum(not item['member_ids'] for item in items),
                'member_count': member_count,
                'uncatalogued': uncatalogued,
                'completed_baselines': completed,
                # Comments/artifacts are included as task-associated detail, not roots.
                'unsupported': ['attachment_only_items', 'calendar', 'comment_only_items', 'task_artifact_only_items',
                                'waitroom', 'worker_questions'],
                'processing_reconciliation': self._processing_reconcile_status_cursor(cur),
            }

        snapshot = {
            'schema_version': 'taskuary.processing.inventory.v1',
            'as_of': as_of,
            'items': items,
            'coverage': coverage,
            'worker_attention_available': projection_live is not None,
            'worker_input_revision': worker_revision,
        }
        if history_days is not None: snapshot['history_days'] = history_days
        snapshot = apply_workers(snapshot)
        snapshot['snapshot_revision'] = hashlib.sha256(json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if not display_only and not include_history:
            # The payload is independent of the query clock; consumers apply history,
            # deferrals and calendar eligibility using as_of on every read. Any local
            # write, external SQLite commit or substantive worker change invalidates.
            with self.lock:
                self._processing_runtime_inventory_cache = (cache_key, copy.deepcopy(snapshot))
        return snapshot

    # ---- the rail: re-project what a write touched, reuse the rest (processing_rail) ----------------
    def close(self):
        """Both connections: the writer and the rail's reader. A test that closes only `cx` leaves the
        file open on Windows and its temporary directory cannot be removed. Under the store's lock: a background thread
        mid-query (the reply watch's judge, 2026-10-11) had its connection closed beneath it and the process died with an
        access violation - after this, a late reader gets sqlite's "closed database" error instead."""
        self._closing = True                      # ...no new background job starts on it from here
        if not self.lock._is_owned():             # ...and the chat log's own worker lets go of it first, never waited for under the lock (_Writer.close)
            try:
                from . import chatlog; chatlog.let_go(self)
            except Exception as e: logger.warning(f'store: the chat log worker was not let go before close - {e}')
        with self.lock, self._rail_lock:
            with self._readers_lock: self._closed, readers, self._readers = True, self._readers, []
            for cx in (self._rail_cx, self.cx, *readers):
                try:
                    if cx is not None: cx.close()
                except sqlite3.Error: pass

    @contextlib.contextmanager
    def _snapshot_read(self):
        """One SQLite read snapshot on a pooled reader connection - never the writer's lock, so a long read leaves every
        other request free to run. Read only: what it yields must never write. A memory database has no second
        connection to open, and reads under the writer's lock as before (_processing_read)."""
        if self._rail_cx is None:
            with self._writer_reads(), self._processing_read() as cur: yield cur
            return
        with self._readers_lock:
            if self._closed: raise sqlite3.ProgrammingError('Cannot operate on a closed database.')
            cx = self._readers.pop() if self._readers else None
        if cx is None:
            cx = sqlite3.connect(self._path, check_same_thread=False, timeout=5.0)
            cx.row_factory = sqlite3.Row
            cx.create_function('tq_fold', 1, _fold, deterministic=True)
            cx.execute('PRAGMA busy_timeout=5000')
        cur = cx.cursor()
        try:
            cur.execute('BEGIN')
            yield cur
        finally:
            try: cur.close(); cx.rollback(); keep = True
            except sqlite3.Error: keep = False
            with self._readers_lock:
                if keep and not self._closed and len(self._readers) < READERS_KEPT: self._readers.append(cx); cx = None
            if cx is not None: cx.close()

    def rail_top(self):
        """The newest dirty-row id: "has anything been written, by any process?" in one cheap read. The
        pile cache (funnel.pile) compares it to the one it was built at, so a write from the sync
        process invalidates it as surely as this process's own do. None when the table is not there."""
        sql = 'SELECT COALESCE(MAX(Id),0) FROM processing_dirty_row'
        try:
            if self._rail_cx is not None:
                with self._rail_lock: return self._rail_cx.execute(sql).fetchone()[0]
            with self.lock: return self.cx.execute(sql).fetchone()[0]
        except sqlite3.OperationalError: return None

    def rail_written(self, low, high):
        """The (kind, id) pairs written in (low, high] - None when that cannot be known (rows trimmed, or the table not there)."""
        sql = ('SELECT MIN(Id) FROM processing_dirty_row WHERE Id>?', 'SELECT DISTINCT Kind, LocalId FROM processing_dirty_row WHERE Id>? AND Id<=?')
        try:
            cx, lock = (self._rail_cx, self._rail_lock) if self._rail_cx is not None else (self.cx, self.lock)
            with lock:
                first = cx.execute(sql[0], (low,)).fetchone()[0]
                if first is None or first > low + 1: return None
                return {(str(k), str(i)) for k, i in cx.execute(sql[1], (low, high))}
        except sqlite3.OperationalError: return None

    def rail_touched_tasks(self, low, high):
        """The tasks a write in (low, high] can have moved, by the rail's own reading of its dirty rows (processing_rail.touched): its own
        rows and every item it sits in - None when that cannot be told (rows trimmed, a setting or a connector every card reads)."""
        from . import processing_rail
        rows = self.rail_written(low, high)
        if rows is None or any(k in ('setting', 'connector') for k, _ in rows): return None
        with self._processing_read() as cur:
            roots = processing_rail.touched(cur, rows, lambda i: self._processing_follow(cur, i))[0]
            if roots is None: return None
            tids = {int(i) for k, i in rows if k == 'task' and i.isdigit()}
            mids = [int(i) for k, i in rows if k == 'message' and i.isdigit()]
            for part in (sorted(roots)[o:o + 400] for o in range(0, len(roots), 400)):
                tids |= {int(r[0]) for r in cur.execute("SELECT LocalId FROM processing_member WHERE EntityKind='task' AND RetiredAt IS NULL "
                                                        f"AND ItemId IN ({','.join('?' * len(part))})", part)}
            for part in (mids[o:o + 400] for o in range(0, len(mids), 400)):
                tids |= {r[0] for r in cur.execute(f"SELECT TaskId FROM message WHERE TaskId IS NOT NULL AND MessageId IN ({','.join('?' * len(part))})", part)}
        return tids

    def rail_cold_building(self) -> bool:
        """A first rail build is running - a restart's - and there is no rail yet: a read of it would wait for that build."""
        return self._rail_build_lock.locked() and not self._processing_display_cache

    def _rail_read(self, *, as_of, history_days, frozen_live, worker_revision):
        """The display snapshot from the rail cache, keyed by window and by whether workers were observed.
        Returns (snapshot, per-root hashes); items are reader copies (item dict + view dict), the
        projections under them are shared by reference and never written to."""
        from . import processing_rail
        key = (history_days, frozen_live is not None)
        projection_live = [] if frozen_live is not None else None
        rail = self._processing_display_cache.get(key)
        if rail is not None and rail['day'] != as_of[:10]: rail = None          # the window moves at midnight
        if rail is not None and self._rail_cx is not None:
            # nothing new since the rail was read: serve it without the writer lock (see __init__)
            status = None
            with self._rail_lock:
                cur = self._rail_cx.cursor()
                try:
                    if processing_rail.dirty_since(cur, rail['mark'])[1] == (): status = self._processing_reconcile_status_cursor(cur)
                finally:
                    cur.close()
            if status is not None: return self._rail_snapshot(rail, as_of, history_days, projection_live, worker_revision, status)
        # ...and a build or an update on a reader connection of its own, one at a time: the writer's lock stays free for
        # every other request (_snapshot_read). Waiting here for another thread's build, take what it built. A memory database
        # reads under the writer's lock, which serialises it already - and a second lock there could cross with it.
        with self._rail_build_lock if self._rail_cx is not None else contextlib.nullcontext(), self._snapshot_read() as cur:
            if self._processing_display_cache.get(key) is not rail:
                rail = self._processing_display_cache.get(key)
                if rail is not None and rail['day'] != as_of[:10]: rail = None
            top, rows = (0, None) if rail is None else processing_rail.dirty_since(cur, rail['mark'])
            if rail is None or rows is None:
                rail = self._rail_build(cur, as_of, history_days, projection_live)
                top = cur.execute('SELECT COALESCE(MAX(Id),0) FROM processing_dirty_row').fetchone()[0]
            elif rows:
                roots, structural = processing_rail.touched(cur, rows, lambda i: processing_rail.follow(rail['redirect'], i))
                if roots is None: rail = self._rail_build(cur, as_of, history_days, projection_live)
                else: self._rail_update(cur, rail, roots, structural, any(k in processing_rail.ENTITY_KINDS for k, _ in rows),
                                        as_of, history_days, projection_live)
            rail['mark'] = top
            self._processing_display_cache[key] = rail
            status = self._processing_reconcile_status_cursor(cur)
        return self._rail_snapshot(rail, as_of, history_days, projection_live, worker_revision, status)

    @staticmethod
    def _rail_snapshot(rail, as_of, history_days, projection_live, worker_revision, status):
        # one atomic read of the rail's view: an update in another thread swaps the tuple, never edits it
        order, proj, hashes, coverage = rail['view']
        items = [{**proj[r], 'view': dict(proj[r]['view'])} for r in order]
        snapshot = {'schema_version': 'taskuary.processing.inventory.v1', 'as_of': as_of, 'items': items,
                    'coverage': {**coverage, 'processing_reconciliation': status},
                    'worker_attention_available': projection_live is not None, 'worker_input_revision': worker_revision}
        if history_days is not None: snapshot['history_days'] = history_days
        return snapshot, hashes

    def _rail_roots(self, cur, rail):
        """Every item, its redirect, the roots and each root's lineage - one query, followed in Python
        (this used to be one SELECT per item, ~8,000 on the owner's store, on every build)."""
        from . import processing_rail
        item_rows = [dict(r) for r in cur.execute('SELECT * FROM processing_item ORDER BY ItemId')]
        rail['redirect'] = {r['ItemId']: r['RedirectItemId'] for r in item_rows}
        rail['roots'] = {r['ItemId']: r for r in item_rows if r['RedirectItemId'] is None}
        lineage = {i: [] for i in rail['roots']}
        for r in item_rows:
            root = processing_rail.follow(rail['redirect'], r['ItemId'])
            if root in lineage: lineage[root].append(r['ItemId'])
        rail['lineage'] = lineage

    def _rail_build(self, cur, as_of, history_days, projection_live):
        rail = {'day': as_of[:10], 'mark': 0, 'proj': {}, 'hash': {}, 'selected': set(), 'order': [], 'coverage': {}}
        self._rail_roots(cur, rail)
        rail['selected'] = self._rail_selected(cur, rail, as_of, history_days)
        pre = self._rail_prefetch(cur, rail, rail['selected'])
        for root in rail['selected']: self._rail_project(cur, rail, root, projection_live, pre)
        self._rail_publish(cur, rail)
        return rail

    @staticmethod
    def _rail_prefetch(cur, rail, roots, least=0):
        """One bulk read for many roots (processing_projection.Prefetch) - None for a handful, which a query each serves."""
        if len(roots) < max(least, 1): return None
        from .processing_projection import Prefetch
        return Prefetch(cur, {r: rail['lineage'][r] for r in roots})

    def _rail_publish(self, cur, rail):
        """The view readers take, swapped in whole: order, projections, hashes, coverage."""
        rail['order'] = sorted(rail['selected'])
        rail['coverage'] = self._rail_coverage(cur, rail)
        rail['view'] = (rail['order'], rail['proj'], rail['hash'], rail['coverage'])

    def _rail_project(self, cur, rail, root, projection_live, pre=None):
        from . import processing_rail
        proj = self._processing_snapshot_cursor(cur, root, live_state=projection_live, lineage=rail['lineage'][root],
                                                item=rail['roots'][root], include_history=False, display_only=True, pre=pre)
        rail['proj'][root] = proj
        rail['hash'][root] = processing_rail.root_hash(proj)

    def _rail_update(self, cur, rail, roots, structural, reselect, as_of, history_days, projection_live):
        """Re-project the touched roots; on a structural change (an item or member moved) re-derive roots and
        lineage and re-project whatever lineage changed; on an entity change re-derive the window."""
        rail['proj'], rail['hash'] = dict(rail['proj']), dict(rail['hash'])     # copy-on-write: readers hold the old view
        if structural:
            old = rail['lineage']
            self._rail_roots(cur, rail)
            roots = set(roots) | {r for r in rail['proj'] if rail['lineage'].get(r) != old.get(r)}
        if structural or reselect:
            rail['selected'] = self._rail_selected(cur, rail, as_of, history_days)
        todo = {r for r in roots if r in rail['selected']} | {r for r in rail['selected'] if r not in rail['proj']}
        pre = self._rail_prefetch(cur, rail, todo, least=64)
        for root in todo: self._rail_project(cur, rail, root, projection_live, pre)
        for root in list(rail['proj']):
            if root not in rail['selected']: rail['proj'].pop(root); rail['hash'].pop(root)
        self._rail_publish(cur, rail)

    def _rail_selected(self, cur, rail, as_of, history_days):
        """The roots in the history window. The HTTP history window must constrain the expensive projection,
        not merely slice its result: a 14-day, 100-row All page once projected every one of 4,590 roots before
        pagination. A root with any message can only be represented by an in-window, non-history message;
        message-less roots use the same task/idea/review timestamps as compact_inventory."""
        from . import processing_rail
        roots = rail['roots']
        if history_days is None: return set(roots)
        try:
            cutoff = datetime.fromisoformat(as_of.replace('Z', '+00:00')) - timedelta(days=history_days)
            if cutoff.tzinfo is not None: cutoff = cutoff.astimezone().replace(tzinfo=None)
        except ValueError:
            raise ValueError('fixed_now must be an ISO timestamp') from None

        def in_window(value):
            if not value: return True       # compact_inventory deliberately retains unknown dates
            try:
                stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                if stamp.tzinfo is not None: stamp = stamp.astimezone().replace(tzinfo=None)
                return stamp >= cutoff
            except ValueError:
                return True

        follow = lambda i: processing_rail.follow(rail['redirect'], i)
        message_roots = {follow(row[0]) for row in cur.execute(
            '''SELECT DISTINCT ItemId FROM processing_member WHERE RetiredAt IS NULL AND EntityKind='message' ''')}
        selected = set()
        sources = (
            ('message', 'message', 'MessageId', 'source.CreatedAt',
             "AND (source.Status IS NULL OR source.Status NOT IN ('context','history','skipped'))"),
            ('task', 'task', 'TaskId', 'source.CreatedAt', ''),
            ('review', 'review', 'ReviewId', 'source.CreatedAt', ''),
            ('idea', 'idea', 'IdeaId', 'COALESCE(source.LastSaid,source.FirstSeen)', ''),
        )
        for kind, table, column, stamp_expr, extra in sources:
            for row in cur.execute(f'''SELECT DISTINCT pm.ItemId,{stamp_expr} ActivityAt
                FROM processing_member pm JOIN {table} source
                  ON pm.EntityKind=? AND pm.LocalId=CAST(source.{column} AS TEXT)
                WHERE pm.RetiredAt IS NULL {extra}''', (kind,)).fetchall():
                root = follow(row['ItemId'])
                if root not in roots or (kind != 'message' and root in message_roots): continue
                if in_window(row['ActivityAt']): selected.add(root)
        # ...and AN OPEN TASK IS ON THE RAIL HOWEVER OLD (processing_unread.card_for): the window is the mail's. A task whose one
        # message aged past it fell off the rail with work still going on it - found through search, worked, and gone on Next (2026-10-29)
        for row in cur.execute(f'''SELECT DISTINCT pm.ItemId FROM processing_member pm JOIN task t
                ON pm.EntityKind='task' AND pm.LocalId=CAST(t.TaskId AS TEXT)
                WHERE pm.RetiredAt IS NULL AND t.Status NOT IN ('done','dropped') AND COALESCE(t.SourceRef,'')!='assistant:dock' '''):
            if (root := follow(row['ItemId'])) in roots: selected.add(root)
        return selected

    def _rail_coverage(self, cur, rail):
        member_count = cur.execute('''SELECT COUNT(*) FROM processing_member pm
            JOIN processing_item pi ON pi.ItemId=pm.ItemId
            WHERE pm.RetiredAt IS NULL AND pi.RedirectItemId IS NULL''').fetchone()[0]
        # Mail the census deliberately never groups is not mail MISSING from it. Counting it here would stop
        # the Timeline dead: compact_inventory refuses while any of these is non-zero, so a flood sender would
        # degrade every read forever. This exclusion and processing_membership.UNGROUPED_MESSAGE_STATUS are one
        # decision - move them together.
        from .processing_membership import ungrouped_message_sql
        ungrouped, ungrouped_params = ungrouped_message_sql('source')
        uncatalogued = {}
        for entity_kind, table, column, extra, extra_params in (
                ('message', 'message', 'MessageId', f' AND NOT {ungrouped}', ungrouped_params),
                ('task', 'task', 'TaskId', '', ()),
                ('review', 'review', 'ReviewId', '', ()),
                ('idea', 'idea', 'IdeaId', '', ())):
            uncatalogued[entity_kind] = cur.execute(f'''SELECT COUNT(*) FROM {table} source
                WHERE NOT EXISTS (SELECT 1 FROM processing_member pm
                    JOIN processing_item pi ON pi.ItemId=pm.ItemId
                    WHERE pm.EntityKind=? AND pm.LocalId=CAST(source.{column} AS TEXT)
                      AND pm.RetiredAt IS NULL AND pi.RedirectItemId IS NULL){extra}''',
                (entity_kind, *extra_params)).fetchone()[0]
        completed = [r[0] for r in cur.execute('''SELECT Version FROM processing_migration
            WHERE Completion='complete' ORDER BY Version''').fetchall()]
        items = [rail['proj'][r] for r in rail['selected']]
        return {
            'canonical_item_count': len(rail['roots']),
            'visible_item_count': sum(bool(item['member_ids']) for item in items),
            'tombstone_item_count': sum(not item['member_ids'] for item in items),
            'member_count': member_count,
            'uncatalogued': uncatalogued,
            'completed_baselines': completed,
            # Comments/artifacts are included as task-associated detail, not roots.
            'unsupported': ['attachment_only_items', 'calendar', 'comment_only_items', 'task_artifact_only_items',
                            'waitroom', 'worker_questions'],
        }

    @staticmethod
    def _processing_backfill_summary(cur, version, status):
        migration = cur.execute('SELECT * FROM processing_migration WHERE Version=?', (version,)).fetchone()
        if not migration: return None
        counts = {}
        for name, table in (('items', 'processing_item'), ('members', 'processing_member'),
                            ('aliases', 'processing_alias'), ('relations', 'processing_relation')):
            counts[name] = cur.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        counts['evidence'] = cur.execute('SELECT COUNT(*) FROM processing_legacy_evidence WHERE MigrationVersion=?',
                                         (version,)).fetchone()[0]
        unresolved = [r[0] for r in cur.execute('''SELECT LocalId FROM processing_legacy_evidence
            WHERE MigrationVersion=? AND EntityKind='legacy_key' ORDER BY LocalId''', (version,)).fetchall()]
        return {'version': version, 'status': status, 'input_watermark': json.loads(migration['InputWatermark']),
                **counts, 'unresolved_keys': unresolved}

    def backfill_processing(self, version, *, fixed_now, live_state=None, evaluator=None,
                            _activate_reads=False):
        """Capture an idempotent legacy baseline; this does not switch reads to the new tables.

        The transaction reads every legacy row without feed windows/caps, writes canonical identity
        and verbatim evidence, and commits the journal marker last. ``live_state`` is an explicit
        caller snapshot; None means "not supplied", while an empty collection explicitly
        records that the caller observed no native workers.
        """
        if not version or not fixed_now: raise ValueError('version and fixed_now are required')
        if evaluator is None:
            from .processing import legacy_read_evidence as evaluator
        live_state = None if live_state is None else copy.deepcopy(tuple(live_state))
        live_by_task = {}
        for raw in live_state or ():
            tid = raw.get('taskId', raw.get('task_id'))
            if tid is None: continue
            live_by_task[int(tid)] = {'working': raw.get('Working') or shown_agent(raw),   # the name the chip says: Taskuary, never the profile
                                      'waiting': bool(raw.get('AgentWaiting', raw.get('waiting', False)))}
        with self.lock:
            cur = self.cx.cursor()
            prior = cur.execute("SELECT Completion FROM processing_migration WHERE Version=?", (str(version),)).fetchone()
            if prior and prior[0] == 'complete':
                return self._processing_backfill_summary(cur, str(version), 'already_complete')
            self._clear_stale(); cur.execute('BEGIN IMMEDIATE')
            try:
                if _activate_reads:
                    from . import processing_reads
                    active = processing_reads.active_version(cur)
                    if active:
                        self.cx.commit()
                        return self._processing_backfill_summary(cur, active, 'already_active')
                    if self._processing_reconcile_status_cursor(cur)['pending']:
                        raise ValueError('processing membership must be reconciled before activation')
                prior = cur.execute("SELECT Completion FROM processing_migration WHERE Version=?", (str(version),)).fetchone()
                if prior and prior[0] == 'complete':
                    self.cx.commit()
                    return self._processing_backfill_summary(cur, str(version), 'already_complete')
                settings = {r['Name']: r['Value'] for r in cur.execute('SELECT Name,Value FROM setting').fetchall()}
                tables = {'message': 'MessageId', 'task': 'TaskId', 'review': 'ReviewId',
                          'idea': 'IdeaId', 'run': 'RunId', 'attachment': 'AttachmentId'}
                watermark = {}
                for table, key in tables.items():
                    count, maximum = cur.execute(f'SELECT COUNT(*),MAX({key}) FROM {table}').fetchone()
                    watermark[table] = {'count': count, 'max_id': maximum}
                watermark['funnel_state'] = {'count': cur.execute('SELECT COUNT(*) FROM funnel_state').fetchone()[0]}
                watermark['live_state'] = ('not_supplied' if live_state is None else
                                           'caller_supplied' if live_by_task else 'caller_supplied_empty')
                cur.execute('''INSERT OR REPLACE INTO processing_migration
                    (Version,CapturedAt,InputWatermark,SettingsJson,Completion) VALUES (?,?,?,?,?)''',
                    (str(version), str(fixed_now), json.dumps(watermark, sort_keys=True),
                     json.dumps(settings, sort_keys=True), 'capturing'))

                def existing_item(entity_kind, local_id):
                    row = cur.execute('''SELECT ItemId FROM processing_member WHERE EntityKind=? AND LocalId=?
                                         AND RetiredAt IS NULL''', (entity_kind, str(local_id))).fetchone()
                    return self._processing_follow(cur, row[0]) if row else None

                def new_item(kind):
                    iid = self._processing_item_id()
                    cur.execute('''INSERT INTO processing_item (ItemId,Kind,CreatedAt,UpdatedAt)
                                   VALUES (?,?,?,?)''', (iid, kind, str(fixed_now), str(fixed_now)))
                    return iid

                def member(iid, entity_kind, local_id, role='member'):
                    local_id = str(local_id)
                    old = existing_item(entity_kind, local_id)
                    if old:
                        if old != iid: raise ValueError(f'{entity_kind}:{local_id} belongs to another processing item')
                        return
                    if role == 'primary' and cur.execute("SELECT 1 FROM processing_member WHERE ItemId=? AND Role='primary' AND RetiredAt IS NULL", (iid,)).fetchone():
                        role = 'member'
                    cur.execute('''INSERT INTO processing_member
                        (ItemId,EntityKind,LocalId,Role,JoinedAt) VALUES (?,?,?,?,?)''',
                        (iid, entity_kind, local_id, role, str(fixed_now)))

                legacy_values = set()
                def alias(namespace, scope, value, entity_kind, local_id, provenance='legacy-backfill'):
                    if not namespace or not scope or not value: raise ValueError('aliases require explicit namespace, scope and value')
                    old = cur.execute('''SELECT EntityKind,LocalId FROM processing_alias
                        WHERE Namespace=? AND Scope=? AND Value=? AND RetiredAt IS NULL''',
                        (namespace, scope, str(value))).fetchone()
                    if old and (old['EntityKind'], old['LocalId']) != (entity_kind, str(local_id)):
                        raise ValueError(f'alias collision for {namespace}/{scope}/{value}')
                    if not old:
                        cur.execute('''INSERT INTO processing_alias
                            (Namespace,Scope,Value,EntityKind,LocalId,Provenance,CreatedAt)
                            VALUES (?,?,?,?,?,?,?)''',
                            (namespace, scope, str(value), entity_kind, str(local_id), provenance, str(fixed_now)))
                    if namespace == 'legacy_funnel': legacy_values.add(str(value))

                tasks = [dict(r) for r in cur.execute('SELECT * FROM task ORDER BY TaskId').fetchall()]
                # the SAME rows the census groups. This builder and reconcile_membership both write
                # processing_member; a message in one set and not the other is a collision waiting to
                # happen, and it happened (see processing_membership.ungrouped_message_sql). Columns
                # stay SELECT *: what the two must agree about is which ROWS exist.
                from .processing_membership import ungrouped_message_sql
                ungrouped, ungrouped_params = ungrouped_message_sql()
                messages = [dict(r) for r in cur.execute(
                    f'SELECT * FROM message WHERE NOT {ungrouped} ORDER BY MessageId', ungrouped_params).fetchall()]
                messages_by_id = {r['MessageId']: r for r in messages}
                reviews = [dict(r) for r in cur.execute('SELECT * FROM review ORDER BY ReviewId').fetchall()]
                ideas = [dict(r) for r in cur.execute('SELECT * FROM idea ORDER BY IdeaId').fetchall()]
                attachments = [dict(r) for r in cur.execute('SELECT * FROM attachment ORDER BY AttachmentId').fetchall()]
                runs = [dict(r) for r in cur.execute('SELECT * FROM run ORDER BY RunId').fetchall()]
                item_by_task, item_by_message = {}, {}
                for task in tasks:
                    tid = task['TaskId']
                    task_item = existing_item('task', tid)
                    message_items = {existing_item('message', m['MessageId']) for m in messages
                                     if m.get('TaskId') == tid and existing_item('message', m['MessageId'])}
                    anchors = ({task_item} if task_item else set()) | message_items
                    if len(anchors) > 1:
                        raise ValueError(f'task:{tid} joins multiple established items; merge explicitly')
                    iid = next(iter(anchors), None) or new_item('task')
                    member(iid, 'task', tid, 'primary'); item_by_task[tid] = iid
                    for key in (f'task:{tid}', f'agent:{tid}', f'wrap:{tid}'):
                        alias('legacy_funnel', 'local', key, 'task', tid); legacy_values.add(key)
                for message_row in messages:
                    mid, tid = message_row['MessageId'], message_row.get('TaskId')
                    iid = item_by_task.get(tid) or existing_item('message', mid) or new_item('message')
                    member(iid, 'message', mid, 'member' if tid else 'primary'); item_by_message[mid] = iid
                    alias('legacy_funnel', 'local', f'msg:{mid}', 'message', mid)
                    if message_row.get('Channel') == 'report':
                        alias('legacy_funnel', 'local', f'report:{mid}', 'message', mid)
                for review in reviews:
                    rid = review['ReviewId']
                    iid = item_by_message.get(review.get('MessageId')) or item_by_task.get(review.get('TaskId')) or existing_item('review', rid) or new_item('review')
                    member(iid, 'review', rid, 'member' if (review.get('MessageId') or review.get('TaskId')) else 'primary')
                    alias('legacy_funnel', 'local', f'review:{rid}', 'review', rid)
                for idea in ideas:
                    iid = existing_item('idea', idea['IdeaId']) or new_item('idea')
                    member(iid, 'idea', idea['IdeaId'], 'primary')
                    alias('legacy_funnel', 'local', f"idea:{idea['IdeaId']}", 'idea', idea['IdeaId'])
                    if idea.get('MessageId'):
                        cur.execute('''INSERT OR IGNORE INTO processing_relation
                            (FromEntityKind,FromLocalId,ToEntityKind,ToLocalId,Kind,Provenance,CreatedAt)
                            VALUES ('message',?,'idea',?,'mentions','legacy-assistant-wrapper',?)''',
                            (str(idea['MessageId']), str(idea['IdeaId']), str(fixed_now)))
                known_ideas = {i['IdeaId'] for i in ideas}
                for message_row in messages:
                    try: brief_ideas = (json.loads(message_row.get('Brief') or '{}').get('ideas') or [])
                    except (TypeError, ValueError, json.JSONDecodeError): brief_ideas = []
                    for entry in brief_ideas:
                        idea_id = entry.get('id') if isinstance(entry, dict) else None
                        if idea_id not in known_ideas: continue
                        cur.execute('''INSERT OR IGNORE INTO processing_relation
                            (FromEntityKind,FromLocalId,ToEntityKind,ToLocalId,Kind,Provenance,CreatedAt)
                            VALUES ('message',?,'idea',?,'mentions','legacy-assistant-brief',?)''',
                            (str(message_row['MessageId']), str(idea_id), str(fixed_now)))
                for attachment in attachments:
                    iid = item_by_message.get(attachment.get('MessageId'))
                    if iid: member(iid, 'attachment', attachment['AttachmentId'], 'attachment')
                for run in runs:
                    iid = item_by_task.get(run.get('TaskId'))
                    if iid: member(iid, 'run', run['RunId'], 'work')

                states = {r['Key']: dict(r) for r in cur.execute('SELECT * FROM funnel_state').fetchall()}
                latest_running = {}
                for run in reversed(runs):
                    if run.get('Status') == 'running' and run.get('TaskId'):
                        latest_running[run['TaskId']] = run.get('AgentName') or 'agent'
                linked = {}
                for idea in ideas:
                    if idea.get('MessageId'): linked.setdefault(idea['MessageId'], []).append(idea)
                for idea_rows in linked.values(): idea_rows.sort(key=lambda x: x['IdeaId'], reverse=True)
                q = f'''SELECT m.MessageId,m.Channel,m.SourceName,m.Subject,m.FromName,m.FromEmail,
                    m.SentAt,m.CreatedAt IngestedAt,m.ConversationId,substr(m.BodyText,1,4000) Preview,
                    m.Status MsgStatus,m.SourceLink,m.TaskId,m.Direction,m.Brief,m.TriageTitle,m.SenderClass,
                    t.Title,t.Status TaskStatus,t.Priority,t.Kind TaskKind,t.Tags TaskTags,
                    IFNULL(ch.n,0) ChainSize,rt.Decision,rt.Reason RouteReason,
                    rv.ReviewId,rv.Status ReviewStatus,rv.Kind ReviewKind,
                    CASE WHEN IFNULL(rv.DraftText,'')<>'' THEN 1 ELSE 0 END HasDraft,
                    IFNULL(att.n,0) Attachments,{self.ANSWERED_AT} AnsweredAt,{self.THEIR_TURN} TheirTurn
                    FROM message m LEFT JOIN task t ON t.TaskId=m.TaskId
                    LEFT JOIN (SELECT MessageId,Decision,Reason FROM route WHERE RouteId IN
                      (SELECT MAX(RouteId) FROM route GROUP BY MessageId)) rt ON rt.MessageId=m.MessageId
                    LEFT JOIN (SELECT * FROM review WHERE ReviewId IN
                      (SELECT MAX(ReviewId) FROM review GROUP BY MessageId)) rv ON rv.MessageId=m.MessageId
                    LEFT JOIN (SELECT MessageId,COUNT(*) n FROM attachment GROUP BY MessageId) att ON att.MessageId=m.MessageId
                    LEFT JOIN (SELECT TaskId,COUNT(*) n FROM message WHERE Status NOT IN ('context','history') GROUP BY TaskId) ch ON ch.TaskId=m.TaskId
                    WHERE m.Status NOT IN ('context','history','skipped') ORDER BY m.MessageId'''
                feed_rows = [dict(r) for r in cur.execute(q).fetchall()]
                from .categories import category_of, team_domains_of
                team = team_domains_of(settings)
                try: funnel_hours = max(1, int(settings.get('funnel_hours') or 12))
                except (TypeError, ValueError): funnel_hours = 12
                evaluated_mids, selected_state_keys = set(), set()
                for row in feed_rows:
                    tid = row.get('TaskId'); live = live_by_task.get(tid)
                    active_task = tid is not None and row.get('TaskStatus') not in ('done', 'dropped')
                    working = ((live or {}).get('working') or latest_running.get(tid)) if active_task else None
                    waiting = bool((live or {}).get('waiting', False)) if active_task else False
                    needs = bool(row.get('ReviewStatus') == 'pending' or
                                 (active_task and not latest_running.get(tid)
                                  and (row.get('TaskKind') != 'note' or str(row.get('SentAt') or '') <= str(fixed_now))
                                  and row.get('MsgStatus') != 'withdrawn' and not row.get('AnsweredAt')
                                  and not row.get('TheirTurn')))
                    if working and active_task and row.get('ReviewStatus') != 'pending': needs = waiting
                    row.update(Category=category_of(row, team), Working=working,
                               AgentWaiting=waiting, NeedsYou=1 if needs else 0,
                               LinkedIdeas=[dict(i) for i in linked.get(row['MessageId'], [])])
                    result = evaluator(row, states, now=str(fixed_now), funnel_hours=funnel_hours)
                    required = {'selected_key', 'observed_unread', 'permanent_read', 'reasons', 'deferral', 'raw_evidence'}
                    missing = required - set(result)
                    if missing: raise ValueError(f'legacy evaluator omitted {sorted(missing)}')
                    evaluated_mids.add(row['MessageId'])
                    if result['selected_key'] in states: selected_state_keys.add(result['selected_key'])
                    payload = {'row': row, 'source_message': messages_by_id[row['MessageId']],
                               'raw_evidence': result['raw_evidence']}
                    fingerprint = hashlib.sha256(json.dumps(row, sort_keys=True, default=str,
                                                            separators=(',', ':')).encode()).hexdigest()
                    cur.execute('''INSERT INTO processing_legacy_evidence
                        (MigrationVersion,ItemId,EntityKind,LocalId,SelectedLegacyKey,ObservedUnread,
                         PermanentRead,ReasonsJson,TemporaryDeferJson,ContextFingerprint,OriginalJson,CapturedAt)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (str(version), item_by_message[row['MessageId']], 'message', str(row['MessageId']),
                         result['selected_key'], int(bool(result['observed_unread'])), int(bool(result['permanent_read'])),
                         json.dumps(result['reasons'], sort_keys=True, default=str),
                         json.dumps(result['deferral'], sort_keys=True, default=str) if result['deferral'] else None,
                         fingerprint, json.dumps(payload, sort_keys=True, default=str), str(fixed_now)))
                # Context/skipped rows were outside the legacy feed, but remain part of the uncapped
                # source inventory. Record that exclusion without inventing an unread result.
                for row in messages:
                    if row['MessageId'] in evaluated_mids: continue
                    original = {'row': row, 'legacy_exclusion': 'message_status_outside_feed'}
                    fingerprint = hashlib.sha256(json.dumps(original, sort_keys=True, default=str).encode()).hexdigest()
                    cur.execute('''INSERT INTO processing_legacy_evidence
                        (MigrationVersion,ItemId,EntityKind,LocalId,SelectedLegacyKey,ObservedUnread,
                         PermanentRead,ReasonsJson,TemporaryDeferJson,ContextFingerprint,OriginalJson,CapturedAt)
                        VALUES (?,?,?,?,?,NULL,NULL,?,NULL,?,?,?)''',
                        (str(version), item_by_message[row['MessageId']], 'message', str(row['MessageId']),
                         f"msg:{row['MessageId']}", json.dumps(['excluded_from_legacy_feed']), fingerprint,
                         json.dumps(original, sort_keys=True, default=str), str(fixed_now)))
                # Every raw funnel receipt is versioned. A receipt not selected by a message may
                # still belong to a task, idea, wrap-up, or an old key no current entity resolves.
                for key in sorted(set(states) - selected_state_keys):
                    target = cur.execute('''SELECT EntityKind,LocalId FROM processing_alias
                        WHERE Namespace='legacy_funnel' AND Scope='local' AND Value=? AND RetiredAt IS NULL''',
                        (key,)).fetchone()
                    item_id = existing_item(target['EntityKind'], target['LocalId']) if target else None
                    entity_kind = 'legacy_state' if target else 'legacy_key'
                    original = {'legacy_key': key, 'state': states[key],
                                'target': dict(target) if target else None}
                    fingerprint = hashlib.sha256(json.dumps(original, sort_keys=True, default=str).encode()).hexdigest()
                    cur.execute('''INSERT INTO processing_legacy_evidence
                        (MigrationVersion,ItemId,EntityKind,LocalId,SelectedLegacyKey,ObservedUnread,
                         PermanentRead,ReasonsJson,TemporaryDeferJson,ContextFingerprint,OriginalJson,CapturedAt)
                        VALUES (?,?,?,?,?,NULL,NULL,?,NULL,?,?,?)''',
                        (str(version), item_id, entity_kind, key, key,
                         json.dumps(['legacy_state_receipt' if target else 'unresolved_legacy_key']), fingerprint,
                         json.dumps(original, sort_keys=True, default=str), str(fixed_now)))
                # Store each full context once per item/version, rather than duplicating
                # a large chain in every message receipt. The completion marker covers
                # identity, receipts and these exact context/view inputs atomically.
                from .processing_projection import processing_projection
                item_ids = [r[0] for r in cur.execute(
                    'SELECT ItemId FROM processing_item WHERE RedirectItemId IS NULL ORDER BY ItemId').fetchall()]
                verdicts = processing_reads.legacy_verdicts(cur, str(version)) if _activate_reads else None
                for item_id in item_ids:
                    picture = processing_projection(cur, item_id, live_state=live_state)
                    if _activate_reads:
                        processing_reads.capture_legacy(cur, str(version), picture, at=str(fixed_now), verdicts=verdicts)
                    cur.execute('''INSERT INTO processing_context_snapshot
                        (MigrationVersion,ItemId,ContextRevision,ViewRevision,ContextJson,ViewJson)
                        VALUES (?,?,?,?,?,?)''',
                        (str(version), item_id, picture['context_revision'], picture['view_revision'],
                         json.dumps(picture['context'], sort_keys=True, ensure_ascii=False),
                         json.dumps(picture['view'], sort_keys=True, ensure_ascii=False)))
                    cur.execute('UPDATE processing_item SET ContextRevision=?,ViewRevision=? WHERE ItemId=?',
                                (picture['context_revision'], picture['view_revision'], item_id))
                    cur.execute('''UPDATE processing_legacy_evidence SET ContextFingerprint=?
                                   WHERE MigrationVersion=? AND ItemId=?''',
                                (picture['context_revision'], str(version), item_id))
                if _activate_reads:
                    for key, legacy_state in states.items():
                        calendar = key.startswith('meeting:')
                        if calendar and legacy_state.get('Status') in ('surfaced', 'done'):
                            processing_reads.record(cur, [dict(entity_kind='calendar', local_id=key,
                                fingerprint='identity-v1')], version=str(version), at=str(fixed_now),
                                by='legacy', origin='legacy_preserved')
                        if legacy_state.get('Status') not in ('later', 'skip'):
                            continue
                        target = ('', 'calendar', key) if calendar else self._processing_read_target(cur, key)
                        if target:
                            self._processing_write_defer(cur, key, target, legacy_state['Status'],
                                legacy_state.get('Until'), legacy_state.get('At') or str(fixed_now),
                                legacy_state.get('By'))
                    cur.execute('''INSERT INTO processing_read_activation
                        (Singleton,Version,ActivatedAt) VALUES (1,?,?)''', (str(version), str(fixed_now)))
                cur.execute("UPDATE processing_migration SET Completion='complete' WHERE Version=?", (str(version),))
                self.cx.commit(); self._writes += 1
                return self._processing_backfill_summary(cur, str(version), 'complete')
            except BaseException:
                self.cx.rollback(); raise

    def dock_tasks(self, tag, limit=60, before=None):
        """Every conversation the guide has had, newest first - the chats list, a page at a time (`before` is
        the last task id of the previous page)."""
        if before: return self._rows('SELECT * FROM task WHERE SourceRef=? AND TaskId<? ORDER BY TaskId DESC LIMIT ?', (tag, int(before), int(limit)))
        return self._rows('SELECT * FROM task WHERE SourceRef=? ORDER BY TaskId DESC LIMIT ?', (tag, int(limit)))
    # ── which brain each AI call ran on (brainroute.log) ────────
    # A route row is on no screen's road but the log's own, so it does not move this connection's write counter: the display
    # caches are keyed on it (feed_tag, PROCESSING_DIRTY_TABLES), and every AI call writes one - the rail would rebuild for nothing.
    BRAIN_ROUTE_COLS = ('At', 'Job', 'TaskId', 'MessageId', 'Pick', 'Model', 'Tier', 'Rule', 'Why', 'Difficulty', 'DataClass',
                        'EscalatedFrom', 'Outcome', 'Ms', 'Ran', 'TokensIn', 'Cached', 'TokensOut', 'Calls', 'Sid', 'Caller', 'Cost')
    def add_brain_route(self, rec: dict) -> int:
        cols = [c for c in self.BRAIN_ROUTE_COLS if rec.get(c) is not None]
        return self._exec_unseen(f"INSERT INTO brainroute ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [rec[c] for c in cols])
    def _exec_unseen(self, q, p=()):
        with self.lock, self._undone():
            cur = self.cx.execute(q, p); self.cx.commit(); return cur.lastrowid
    def set_brain_route(self, rid: int, **fields) -> None:
        cols = [c for c in fields if c in self.BRAIN_ROUTE_COLS]
        if not cols: return
        self._exec_unseen(f"UPDATE brainroute SET {','.join(f'{c}=?' for c in cols)} WHERE Id=?", [fields[c] for c in cols] + [int(rid)])
    def brain_routes(self, task_id: int = None, limit: int = 20) -> list:
        if task_id is not None: return self._rows('SELECT * FROM brainroute WHERE TaskId=? ORDER BY Id DESC LIMIT ?', (int(task_id), int(limit)))
        return self._rows('SELECT * FROM brainroute ORDER BY Id DESC LIMIT ?', (int(limit),))
    def count_brain_routes(self, since: str, tier: str = None) -> int:
        q, p = 'SELECT COUNT(*) AS n FROM brainroute WHERE At>=?', [since]
        if tier: q, p = q + ' AND Tier=?', p + [tier]
        return (self._one(q, p) or {}).get('n') or 0
    def trim_brain_routes(self, before: str, why_before: str = None) -> int:
        "Rows older than `before` go; older than `why_before`, only their reason does - what they used stays for the dashboard."
        if why_before: self._exec_unseen('UPDATE brainroute SET Why=NULL WHERE At<? AND Why IS NOT NULL', (why_before,))
        n = (self._one('SELECT COUNT(*) AS n FROM brainroute WHERE At<?', (before,)) or {}).get('n') or 0
        if n: self._exec_unseen('DELETE FROM brainroute WHERE At<?', (before,))
        return n
    def add_brain_usage(self, rid: int, ms: int = None, use: dict = None) -> None:
        "One more call on route `rid`: its time and tokens ADDED to the row's (a kept conversation is one brain, many calls)."
        u = use or {}
        tok = lambda k: None if u.get(k) is None else int(u[k])
        self._exec_unseen('''UPDATE brainroute SET Calls=COALESCE(Calls,0)+1, Ms=CASE WHEN ? IS NULL THEN Ms ELSE COALESCE(Ms,0)+? END,
            TokensIn=CASE WHEN ? IS NULL THEN TokensIn ELSE COALESCE(TokensIn,0)+? END, Cached=CASE WHEN ? IS NULL THEN Cached ELSE COALESCE(Cached,0)+? END,
            TokensOut=CASE WHEN ? IS NULL THEN TokensOut ELSE COALESCE(TokensOut,0)+? END, Cost=CASE WHEN ? IS NULL THEN Cost ELSE COALESCE(Cost,0)+? END,
            Ran=COALESCE(?, Ran), FellFrom=COALESCE(?, FellFrom) WHERE Id=?''',
            (ms, ms, tok('in'), tok('in'), tok('cached'), tok('cached'), tok('out'), tok('out'), u.get('cost'), u.get('cost'), u.get('model') or None,
             u.get('fell_from') or None, int(rid)))
    def brain_routes_since(self, since: str, task_id: int = None, limit: int = 20000) -> list:
        q, p = 'SELECT * FROM brainroute WHERE At>=?', [since]
        if task_id is not None: q, p = q + ' AND TaskId=?', p + [int(task_id)]
        return self._rows(q + ' ORDER BY Id DESC LIMIT ?', p + [int(limit)])
    def brain_route_of_session(self, sid: str):
        return self._one('SELECT * FROM brainroute WHERE Sid=? ORDER BY Id DESC LIMIT 1', (str(sid),))
    # ── how hard a task's work is, and what data it carries (triage's judgements; brainroute reads them) ────────
    def task_judged(self, task_id) -> dict:
        return self._one('SELECT * FROM task_judged WHERE TaskId=?', (int(task_id),)) or {}
    def judge_task(self, task_id, v: dict, by: str) -> dict:
        """Triage's newest word on how hard and how sure, unless the owner corrected it - theirs stands. The data class only ever
        goes UP from a reading: one sensitive message makes the task sensitive (the worst wins, as origin does), and only the owner
        brings it back down. A judgement the verdict did not give is left as it was.
        HOW HARD AND HOW SURE ARE THE OWNER'S ALONE (2026-11-23): triage judges no difficulty, so a verdict that still carries one - an older
        stored verdict reused, an owner's own TRIAGE.md that asks for it - moves nothing; only his correction on the task does."""
        was = self.task_judged(task_id); owner = by == 'owner'
        held = not owner
        d, sure, dc = v.get('difficulty'), v.get('sure'), v.get('data_class')
        new = {'Difficulty': was.get('Difficulty') if held or d not in ('quick', 'standard', 'hard') else d,
               'Sure': was.get('Sure') if held or not isinstance(sure, bool) else int(sure),
               'DataClass': dc if dc in ('ordinary', 'sensitive') and (owner or dc == 'sensitive' or not was.get('DataClass')) else was.get('DataClass')}
        if was and all(new[k] == was.get(k) for k in new) and not owner: return was
        self._exec_unseen('INSERT OR REPLACE INTO task_judged (TaskId,Difficulty,Sure,DataClass,By,At) VALUES (?,?,?,?,?,?)',
                          (int(task_id), new['Difficulty'], new['Sure'], new['DataClass'], 'owner' if owner else was.get('By') or by, _now()))
        return self.task_judged(task_id)
    # ── a report's run history (reports.run_report_source; the Reports tab's History) ────────
    REPORT_RUNS_KEPT = 60          # per report - a month of half-hourly assistant checks is 1400, and nobody reads past the last few dozen
    def add_report_run(self, sid: int, rec: dict) -> int:
        """One run of one report, whole: what it read (Inputs), what it reviewed, what it said and why
        (Lines), what came out. The last-run setting keeps the newest for the row; this keeps the rest."""
        rid = self._exec('INSERT INTO report_run (SourceId, At, Type, Title, Ms, Subject, MessageId, Failed, Error, Said, LinesJson, ReviewedJson, Inputs, Summary, '
                         'StepsJson, TaskId) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (sid, rec.get('at'), rec.get('type'), rec.get('title'), rec.get('ms'), rec.get('subject'), rec.get('message_id'), int(bool(rec.get('failed'))),
                          rec.get('error'), rec.get('said'), json.dumps(rec.get('lines') or [], default=str), json.dumps(rec.get('reviewed'), default=str) if rec.get('reviewed') else None,
                          rec.get('inputs'), rec.get('summary'), json.dumps(rec['steps'], default=str) if rec.get('steps') is not None else None, rec.get('task_id')))
        self._exec('DELETE FROM report_run WHERE SourceId=? AND RunId NOT IN (SELECT RunId FROM report_run WHERE SourceId=? ORDER BY RunId DESC LIMIT ?)',
                   (sid, sid, self.REPORT_RUNS_KEPT))
        return rid
    def set_report_run_steps(self, rid: int, steps: list, failed: bool = False, error: str = None, ms: int = None, summary: str = None) -> None:
        """A workflow run's steps as they land (flow.execute), so the run is readable while it works."""
        self._exec('UPDATE report_run SET StepsJson=?, Failed=?, Error=?, Ms=COALESCE(?, Ms), Summary=COALESCE(?, Summary) WHERE RunId=?',
                   (json.dumps(steps or [], default=str), int(bool(failed)), error, ms, summary, int(rid)))
    def set_report_run_inputs(self, rid: int, inputs: str) -> None:
        """What a stopped workflow run read in full (flow._walk), for the run that goes on after a yes (flow.resume)."""
        self._exec('UPDATE report_run SET Inputs=? WHERE RunId=?', (inputs, int(rid)))
    def set_report_run_repairs(self, rid: int, repairs: list) -> None:
        """The repairs a run made to its own steps (flow.execute), each with the steps it replaced - what Undo puts back."""
        self._exec('UPDATE report_run SET RepairsJson=? WHERE RunId=?', (json.dumps(repairs or [], default=str), int(rid)))
    def report_run_of_task(self, tid: int):
        """The newest workflow run that belongs to this run task - its steps, for the task card."""
        r = self._one('SELECT *, length(Inputs) InputChars FROM report_run WHERE TaskId=? ORDER BY RunId DESC LIMIT 1', (int(tid),))
        return self._run_row(r) if r else None
    def report_run_failed(self, mid) -> bool | None:
        """Did the run that PRODUCED this report message fail? None when no run is linked to it - the
        caller falls back to the subject's convention. Keyed on the row, never on the report's newest
        run, so an old failure stays a failure and a new one does not re-mark the rows before it."""
        if not mid: return None
        r = self._one('SELECT Failed FROM report_run WHERE MessageId=? ORDER BY RunId DESC LIMIT 1', (int(mid),))
        return bool(r['Failed']) if r else None
    def report_runs(self, sid: int, limit: int = 60) -> list:
        """The history, newest first, WITHOUT the inputs (14KB each) - get_report_run fetches one whole."""
        return [self._run_row(r) for r in self._rows('SELECT RunId, SourceId, At, Type, Title, Ms, Subject, MessageId, Failed, Error, Said, LinesJson, ReviewedJson, '
                                                      'StepsJson, TaskId, RepairsJson, length(Inputs) InputChars FROM report_run WHERE SourceId=? ORDER BY RunId DESC LIMIT ?', (sid, limit))]
    def get_report_run(self, rid: int):
        r = self._one('SELECT *, length(Inputs) InputChars FROM report_run WHERE RunId=?', (rid,))
        return self._run_row(r) if r else None
    @staticmethod
    def _run_row(r: dict) -> dict:
        def j(s):
            try: return json.loads(s) if s else None
            except ValueError: return None
        return {'runId': r['RunId'], 'sourceId': r['SourceId'], 'at': r['At'], 'type': r['Type'], 'title': r['Title'], 'ms': r['Ms'], 'subject': r['Subject'],
                'messageId': r['MessageId'], 'failed': bool(r['Failed']), 'error': r['Error'], 'said': r['Said'], 'lines': j(r.get('LinesJson')) or [],
                'reviewed': j(r.get('ReviewedJson')), 'inputChars': r.get('InputChars') or 0, 'steps': j(r.get('StepsJson')), 'taskId': r.get('TaskId'), 'repairs': j(r.get('RepairsJson')) or [], **({'inputs': r['Inputs']} if 'Inputs' in r else {}),
                **({'summary': r['Summary']} if 'Summary' in r else {})}

    def thread_messages(self, conversation_id=None, subject=None, limit=40):
        """Every message already on this thread, oldest last - by ConversationId where the channel
        gives us one, else by normalised subject for the channels that do not.

        Triage needs this to answer the one question a message cannot answer about itself: has
        somebody ELSE already picked this up? That fact is never in the message; it is in the
        messages around it."""
        if conversation_id:
            rows = self._rows('SELECT * FROM message WHERE ConversationId=? ORDER BY SentAt DESC LIMIT ?',
                              (conversation_id, limit))
            if rows: return list(reversed(rows))
        if not subject: return []
        from .routing import norm_subject
        key = norm_subject(subject)
        if not key: return []
        # no index on a normalised subject, so bound the scan rather than the table
        rows = self._rows('SELECT * FROM message WHERE Subject IS NOT NULL ORDER BY SentAt DESC LIMIT 400')
        return list(reversed([r for r in rows if norm_subject(r['Subject']) == key][:limit]))

    def owner_verdict_on_thread(self, conversation_id, sent_at=None, sender: str = None, channel: str = None) -> str:
        """The owner's own "this is not work" on an EARLIER message of this same conversation, if
        any - the route reason they left ('not ours - ...', 'not a task - ...', 'nothing to do - ...').
        The thread is the one key that needs no scope: whatever else the verdict was filed under
        (a sender, a topic, nothing), it was given about THIS conversation - and the verdict the
        owner gives most is the one that deliberately teaches nothing about anybody, so without
        this rule the same thread opened a task on every burst (six times for one Teams chat).

        A real conversation id only. The same-subject fallback thread_messages offers is good
        enough to ADVISE (others_on_thread) but not to decide: two mails that merely share a
        subject line are not proof the owner ruled on the second.

        A CHAT IS NOT A TOPIC. teams:<chat> and whatsapp:<jid> are a room - a relationship - and
        "nothing to do here" said about one line in it means THAT line is handled, not that the
        person is muted. It used to carry: the same sender's next lines were filed unread for
        24 hours, so "I just remembered..." an hour later never reached the funnel at all (the
        owner, 2026-08-31: "it should not judge the same sender sending something else"). It
        carries nothing now. The verdict still reaches the classifier as EVIDENCE, with the
        sender and subject it was given on (relevant_notes), which is where a judgement about a
        person belongs - a reader can tell a new ask from a settled one; a clock cannot.

        An email THREAD is a topic, and a reply on it is the same topic, so that one still
        decides - bounded by the thread itself, whoever writes."""
        if not conversation_id: return ''
        # the CHANNEL is the fact; the id's prefix is only a convention, and an anonymised or
        # imported conversation id carries none
        if str(channel or '').lower() in CHAT_CHANNELS or conversation_id.startswith(CHAT_PREFIXES): return ''
        mids = [m['MessageId'] for m in self.thread_messages(conversation_id)]
        if not mids: return ''
        if str((self.get_message(mids[0]) or {}).get('Channel') or '').lower() in CHAT_CHANNELS: return ''
        row = self._one("SELECT r.Reason FROM route r WHERE r.MessageId IN "
                        f"({','.join('?' * len(mids))}) AND r.Decision='ignore' AND r.RoutedBy='owner' "
                        'ORDER BY r.RouteId DESC LIMIT 1', tuple(mids))
        return (row or {}).get('Reason') or ''
    def list_messages(self, task_id): return self._rows('SELECT * FROM message WHERE TaskId=? ORDER BY SentAt', (task_id,))
    def skill_examples(self, query='', before=0):
        """Page through imported incoming email, including old and already filed requests."""
        where, args = ["Channel='email'", "Direction='in'"], []
        if before:
            where.append('MessageId<?'); args.append(before)
        if query.strip():
            # Literal substring search: a sender's '%' or '_' is not a SQL wildcard.
            where.append("instr(lower(COALESCE(Subject,'') || char(10) || COALESCE(FromName,'') "
                         "|| char(10) || COALESCE(FromEmail,'') || char(10) || COALESCE(BodyText,'')), lower(?))>0")
            args.append(query.strip())
        rows = self._rows('SELECT MessageId, Subject, FromName, FromEmail, SentAt, '
                          'substr(BodyText,1,4000) BodyText FROM message WHERE ' + ' AND '.join(where)
                          + ' ORDER BY MessageId DESC LIMIT 21', tuple(args))
        return {'data': rows[:20], 'next': rows[19]['MessageId'] if len(rows) > 20 else None}

    def saved_session(self, task_id):
        return self._one('SELECT * FROM session_resume WHERE TaskId=?', (task_id,))

    def save_session(self, task_id, pick, model, native_id, context_key):
        self._exec('INSERT INTO session_resume (TaskId,Pick,Model,NativeId,ContextKey,UpdatedAt) VALUES (?,?,?,?,?,?) '
                   'ON CONFLICT(TaskId) DO UPDATE SET Pick=excluded.Pick, Model=excluded.Model, '
                   'NativeId=excluded.NativeId, ContextKey=excluded.ContextKey, UpdatedAt=excluded.UpdatedAt',
                   (task_id, pick, model, native_id or '', context_key, _now()))

    def save_frozen(self, task_id, frozen: str):
        "What the task's kept conversation was told - its instructions and the late lines it has heard (general.freeze)."
        self._exec('UPDATE session_resume SET Frozen=? WHERE TaskId=?', (frozen, task_id))

    def previous_work(self):
        """Existing work records for the welcome card; no summaries or new AI jobs."""
        return self._rows('''SELECT t.TaskId, t.Title, t.Status, t.Kind, t.SourceRef,
                   c.Body Recap, tr.Agent, tr.Cwd,
                   MAX(COALESCE(c.CreatedAt,''), COALESCE(tr.CreatedAt,'')) LastWorkedAt
            FROM task t
            LEFT JOIN comment c ON c.CommentId=(SELECT MAX(c2.CommentId) FROM comment c2
                WHERE c2.TaskId=t.TaskId AND (c2.ActorType='assistant_agent'
                    OR c2.Body LIKE 'HANDOVER NOTE%' OR c2.Body LIKE 'AGENT REPORT%' OR c2.Body LIKE 'CODER REPORT%'))
            LEFT JOIN transcript tr ON tr.TranscriptId=(SELECT MAX(tr2.TranscriptId) FROM transcript tr2 WHERE tr2.TaskId=t.TaskId)
            WHERE COALESCE(t.SourceRef,'') NOT IN ('assistant:dock','assistant:concierge')
                AND (t.Status IN ('open','waiting','in_progress') OR (t.Status='done'
                    AND EXISTS (SELECT 1 FROM review r WHERE r.TaskId=t.TaskId AND r.Status='pending')))
                AND (c.CommentId IS NOT NULL OR tr.TranscriptId IS NOT NULL)
            ORDER BY LastWorkedAt DESC, t.TaskId DESC LIMIT 100''')

    def scan_messages(self, limit=20000, since=None, statuses=None, from_email=None, from_domains=None,
                      include_body=True):
        """Just enough message history, with the common filters pushed into SQLite.

        Every filter here is a PRE-filter: policy.matches() still judges each row it returns, so a
        clause may over-fetch but must never be narrower than the Python predicate it stands in for -
        a row SQLite drops is a row the owner silently never sees again.
        """
        # ConversationId rides along so a history reader can pair inbound mail with what the owner
        # SENT back (histgen: "answered" is the ground truth TRIAGE.md is distilled from, and on an
        # IMAP install this store is the only place the inbound half lives). Most callers only want a
        # date/status/envelope slice; do that before Python ever sees the back catalogue.
        where, args = [], []
        if since is not None:
            where.append('SentAt>=?'); args.append(since)
        if statuses:
            where.append('Status IN (' + ','.join('?' * len(statuses)) + ')'); args += list(statuses)
        if from_email:
            vals = [x.lower() for x in from_email]
            where.append('lower(FromEmail) IN (' + ','.join('?' * len(vals)) + ')'); args += vals
        if from_domains:
            # '%@'||domain, not substr-after-the-first-'@': matches() splits on the LAST '@', and a
            # quoted local part ('"a@b"@vendor.com') puts an earlier one in the way
            where.append('(' + ' OR '.join(["lower(FromEmail) LIKE '%@'||?"] * len(from_domains)) + ')')
            args += [x.lower() for x in from_domains]
        body = 'substr(BodyText, 1, 2000) BodyText' if include_body else "'' BodyText"
        sql = ('SELECT MessageId, TaskId, ConversationId, FromEmail, Subject, Status, SentAt, SourceName, ' + body + ' FROM message'
               + ((' WHERE ' + ' AND '.join(where)) if where else '') + ' ORDER BY MessageId DESC LIMIT ?')
        return self._rows(sql, (*args, limit))
    def set_message_status(self, mid, status):
        self._exec('UPDATE message SET Status=? WHERE MessageId=?', (status, mid))
        self._poke('feed-changed', message_id=mid)
    def update_message_body(self, mid, body): self._exec('UPDATE message SET BodyText=? WHERE MessageId=?', (body, mid))   # a voice note, transcribed later
    def get_message(self, mid): return self._one('SELECT * FROM message WHERE MessageId=?', (mid,))
    def arrive(self, mid, task_id, status=None, title=None, *, free: bool = False, decided: bool = False) -> bool:
        """WHERE A MESSAGE IS - THE ONE WRITER OF message.TaskId (spec B, one arrival road). Triage decides first: while a row is still
        'triaging' only a placement that `decided` it lands - triage's own verdict (ingest._land, its retry and error paths) or the owner's
        own hand (promote, split, move). Any other road - the sent-mail judge's join, an idea's sources, a promise - is refused, so a
        message is never on a task and on the rail as "triage is deciding" at once (two mails in one poll, a join while triage read).
        `status` None keeps the row's; `title` is the verdict's own line; `free` places only a row no task holds yet. -> placed?"""
        sets, args = ['TaskId=?'], [task_id]
        if status is not None: sets.append('Status=?'); args.append(status)
        if title: sets.append('TriageTitle=?'); args.append(title)
        where = 'MessageId=?' + (' AND TaskId IS NULL' if free else '') + ('' if decided else " AND Status!='triaging'")
        with self.lock:
            cur = self.cx.execute(f"UPDATE message SET {', '.join(sets)} WHERE {where}", (*args, mid)); self.cx.commit(); self._writes += 1
        if cur.rowcount != 1: return False
        if task_id is not None:
            self._bump_snapshots()
            from . import events                 # ...one event on the task: what its agent hears of it (events.py)
            events.arrived(self, mid, task_id)
            self._poke('feed-changed', 'task-changed', message_id=mid, task_id=task_id)
        else:
            self._poke('feed-changed', message_id=mid)
        return True
    # the two old names, kept for the tests that set rows up by hand: each is arrive, decided - no road of the app calls them
    def place_message(self, mid, task_id, status, title=None): self.arrive(mid, task_id, status, title, decided=True)
    def attach_message(self, mid, task_id): self.arrive(mid, task_id, 'routed', decided=True)
    def claim_retriage(self, mid: int) -> bool:
        """Atomically move one failed row back into triage: a message in the `error` state (linked
        to a task or not), or a legacy failure still stored as a taskless `filed` row.

        The endpoint checks the prior verdict for a useful error message; this compare-and-set is
        the concurrency guard. Two clicks (or browser retries) must never create two tasks.
        """
        with self.lock:
            # a legacy filed row qualifies only when its LAST route is a failure diagnostic - a
            # genuine fyi is not retriable (same rule as upgrade_triage_failures, in SQL)
            cur = self.cx.execute("""UPDATE message SET Status='triaging'
                                   WHERE MessageId=? AND (Status='error' OR (Status='filed' AND TaskId IS NULL AND EXISTS (
                                       SELECT 1 FROM route r WHERE r.RouteId=(SELECT MAX(RouteId) FROM route WHERE MessageId=message.MessageId)
                                       AND (r.Reason LIKE 'AI triage failed (%' OR r.Reason LIKE 'AI triage returned an answer it could not read%'
                                            OR r.Reason LIKE 'triage failed (%' OR r.Reason LIKE 'triage retry failed (%'))))""", (mid,))
            self.cx.commit(); self._writes += 1
            ok = cur.rowcount == 1
        if ok:
            self._poke('feed-changed', message_id=mid)
        return ok
    # The route reasons triage writes when it FAILED - distinct from a verdict it reached. A
    # no-AI install's "awaiting AI triage" is deliberately not here: flipping years of that
    # history at once would be the bulk conversion PW-040 forbids; new arrivals wear the state.
    TRIAGE_FAILURE = r"^(AI triage failed \(|AI triage returned an answer it could not read|triage failed \(|triage retry failed \()"
    # ...and the row that never reached the AI at all, because there was no connector to ask. It is
    # the same thing to the owner - unjudged, waiting - so the sweep that retries failures retries it
    # too, the moment a brain exists. Kept separate from TRIAGE_FAILURE, which also decides which
    # legacy `filed` rows are upgraded: an install that never had an AI must not have its history
    # rewritten by one being connected today.
    TRIAGE_UNJUDGED = TRIAGE_FAILURE[:-1] + r"|awaiting AI triage)"
    def upgrade_auto_start(self) -> bool:
        """An install that had switched the coding agent's auto-start OFF said 'no unattended sessions'
        before the assistant had a switch of its own: the new switch starts off for it too (PW-070).
        Runs once; an owner's explicit choice for the new switch is never overwritten."""
        cfg = self.get_settings()
        if cfg.get('auto_start_upgraded') == '1': return False
        row = self._one("SELECT * FROM setting WHERE Name='general_auto_enabled'")
        seeded = row is None or not row.get('UpdatedBy')
        changed = False
        if seeded and cfg.get('coding_auto_enabled') == '0':
            self.set_setting('general_auto_enabled', '0', 'upgrade'); changed = True
        elif row is None: self.set_setting('general_auto_enabled', '1', 'upgrade')
        self.set_setting('auto_start_upgraded', '1', 'upgrade')
        return changed
    def upgrade_triage_failures(self) -> int:
        """Historical triage failures stored as `filed` become `error` once (PW-040) - identified
        by their LAST route being a failure diagnostic, so a row the owner later ruled on, a genuine
        fyi and a no-AI install's history all stay as they are. Read state is untouched: the funnel
        keeps its own rows, and an error row is quiet there like a filed one."""
        rows = self._rows("""SELECT m.MessageId, r.Reason FROM message m
                             JOIN route r ON r.RouteId = (SELECT MAX(RouteId) FROM route WHERE MessageId=m.MessageId)
                             WHERE m.Status='filed' AND m.TaskId IS NULL""")
        ids = [r['MessageId'] for r in rows if re.match(self.TRIAGE_FAILURE, r['Reason'] or '')]
        for mid in ids: self._exec("UPDATE message SET Status='error' WHERE MessageId=? AND Status='filed'", (mid,))
        if ids: self._poke('feed-changed')
        return len(ids)
    def last_judged_route_id(self) -> int:
        """The newest route triage actually judged (no failure on it) - the brain's last answer."""
        r = self._rows("SELECT MAX(RouteId) m FROM route WHERE RoutedBy='triage' AND ParseError IS NULL")
        return int((r[0]['m'] if r else 0) or 0)
    def last_route_id(self) -> int:
        r = self._rows('SELECT MAX(RouteId) m FROM route')
        return int((r[0]['m'] if r else 0) or 0)
    def stranded_triage_failures(self, limit=25, since=None, tries_after=0, tries=0, failed_only=False) -> list:
        """Rows the AI never judged, oldest first, with how many times it has already been tried.

        A triage failure was only ever retried by hand, one row at a time, from the opened row - so
        an outage left every message it touched stranded for good, wearing no verdict, while the
        brain that came back minutes later judged only what arrived AFTER it (the owner, 2026-09-15:
        "we should also retry the ones that triage failed if it becomes available on next sync no?").

        `Tries` counts the failure diagnostics already written for the row, so a message that fails
        for its own reasons - a body no model can answer about - stops being retried instead of
        costing a call every cycle forever. Same identification as upgrade_triage_failures.

        `since` bounds it to what is still NEWS. Triage decides what needs the owner now, and a
        message that has sat unjudged for a fortnight is history: the first sweep resurrected two
        WhatsApp lines and an email from two weeks earlier, made live tasks of them and drafted
        replies to a conversation that had moved on five days later (the owner, 2026-09-15: "what
        is this? don't see them in the task list?"). Anything older stays in `error` with the
        Retry button it always had - reopening it is then somebody's decision, not a side effect.
        Same clock both sides: SentAt is local 'YYYY-MM-DD HH:MM:SS' (norm_stamp), and so is _now().
        `tries_after`: count only failures on routes after this one - the brain's last recovery (ingest.retry_failed_triage).

        `tries` > 0 is the AUTOMATIC sweep, and what it will not try is left out INSIDE the query: a row whose tries are
        spent, and a row it already gave up on and put on the owner's list (HELD). Skipped after the LIMIT instead, 25 spent
        rows at the head filled every page, and nothing newer was ever retried again. 0 is the owner's own Retry all, which
        reaches both. `failed_only` leaves out the no-AI install's `awaiting AI triage`: nothing failed there.
        """
        like = self.FAILURE_LIKE + (() if failed_only else ('awaiting AI triage%',))
        auto = " AND IFNULL(Decision,'') <> ? AND Tries < ?" if tries else ''
        rows = self._rows(f"""SELECT * FROM (SELECT m.MessageId, m.SentAt, r.Reason, r.Decision,
                               (SELECT COUNT(*) FROM route x WHERE x.MessageId=m.MessageId
                                AND x.ParseError IS NOT NULL AND x.RouteId > ?) Tries
                             FROM message m JOIN route r
                               ON r.RouteId=(SELECT MAX(RouteId) FROM route WHERE MessageId=m.MessageId)
                             WHERE m.Status='error'{' AND m.SentAt >= ?' if since else ''}
                               AND (r.Decision=? OR {' OR '.join(['r.Reason LIKE ?'] * len(like))}))
                             WHERE 1=1{auto} ORDER BY MessageId LIMIT ?""",
                          (int(tries_after or 0),) + ((since,) if since else ()) + (self.HELD,) + like
                          + ((self.HELD, int(tries)) if tries else ()) + (limit,))
        unjudged = self.TRIAGE_FAILURE if failed_only else self.TRIAGE_UNJUDGED
        return [dict(r) for r in rows if r['Decision'] == self.HELD or re.match(unjudged, r['Reason'] or '')]
    # THE SWEEP GAVE UP ON IT: the route a row gets when the automatic retry stops for good (ingest.give_up). It stays in
    # `error` - its Retry button is the owner's - and the bands read it as the owner's (processing_order.feed_band).
    HELD = 'held'
    # TRIAGE_FAILURE's prefixes, as SQL can match them - so a filter lives in the query, before its LIMIT
    FAILURE_LIKE = ('AI triage failed (%', 'AI triage returned an answer it could not read%', 'triage failed (%', 'triage retry failed (%')
    def spent_triage_failures(self, since=None, tries_after=0, tries=4, aged_from=None) -> list:
        """What the automatic sweep has stopped on and not yet handed over: failed rows inside the window whose tries are
        spent, and - with `aged_from` - rows that slid out of the window since then, still unjudged."""
        aged = ' OR (SentAt >= ? AND SentAt < ?)' if aged_from and since else ''
        rows = self._rows(f"""SELECT * FROM (SELECT m.MessageId, m.TaskId, m.SentAt, r.Reason,
                               (SELECT COUNT(*) FROM route x WHERE x.MessageId=m.MessageId
                                AND x.ParseError IS NOT NULL AND x.RouteId > ?) Tries
                             FROM message m JOIN route r
                               ON r.RouteId=(SELECT MAX(RouteId) FROM route WHERE MessageId=m.MessageId)
                             WHERE m.Status='error' AND IFNULL(r.Decision,'') <> ?
                               AND ({' OR '.join(['r.Reason LIKE ?'] * len(self.FAILURE_LIKE))}))
                             WHERE (Tries >= ?{' AND SentAt >= ?' if since else ''}){aged} ORDER BY MessageId""",
                          (int(tries_after or 0), self.HELD) + self.FAILURE_LIKE + (int(tries),) + ((since,) if since else ())
                          + ((aged_from, since) if aged else ()))
        return [dict(r) for r in rows if re.match(self.TRIAGE_FAILURE, r['Reason'] or '')]
    def live_tasks_from_sender(self, email: str) -> list:
        """Open tasks carrying a message from this address - what a skip rule leaves behind.

        Hiding the mail does not hide the WORK it already made: the rule marked the Power BI mail
        skipped and its task sat in the pipe being offered again, which is worse than the Next the
        owner could have pressed instead (the owner, 2026-09-15: "it should not be worse then
        clicking next which marks it as read no?").
        """
        return self._rows("""SELECT DISTINCT t.TaskId, t.Title FROM task t JOIN message m ON m.TaskId=t.TaskId
                             WHERE t.Status NOT IN ('done','dropped') AND lower(IFNULL(m.FromEmail,''))=?
                             ORDER BY t.TaskId""", ((email or '').lower().strip(),))
    def pending_triage(self, limit=500, ranked=False):
        """What is waiting to be judged. Arrival order is the rule; `ranked` answers by the value
        rank.py gave it, and a row nobody ranked sorts AFTER what was ranked - never above it, which
        would let an unranked arrival jump the queue it was never measured against."""
        order = 'RankValue IS NULL, RankValue DESC, MessageId' if ranked else 'MessageId'
        return self._rows(f"SELECT * FROM message WHERE Status='triaging' ORDER BY {order} LIMIT ?", (limit,))
    def ranked_held(self, channel) -> int: return len(self.ranked_head(channel))
    # ── batches (batch.py) ──────────────────────────────────────────────────────────────────
    BATCH_ITEM_COLS = ('State', 'Result', 'Overlap', 'EndedWhy', 'Title', 'Link', 'MessageId', 'Place', 'Sha', 'Propose', 'Fix', 'FixAt', 'FixLink', 'Trusted', 'Screen', 'Warn')
    def batch_items_fixing(self) -> list:
        return self._rows("SELECT * FROM batch_item WHERE Fix='running' ORDER BY ItemId")
    def add_batch_item(self, tid, conv, mid, place, title, link):
        self._exec('INSERT OR IGNORE INTO batch_item (TaskId, ConversationId, MessageId, Place, Title, Link, State, CreatedAt, UpdatedAt) '
                   "VALUES (?,?,?,?,?,?,'waiting',?,?)", (tid, conv, mid, place, title, link, _now(), _now()))
    def move_batch_item(self, item_id, tid, place) -> None:
        """One item into another batch, with its review, head and screen - batch.combine."""
        self._exec('UPDATE batch_item SET TaskId=?, Place=?, UpdatedAt=? WHERE ItemId=?', (tid, place, _now(), item_id))
        self._bump_snapshots(); self._poke('task-changed', task_id=tid)
    def batch_items(self, tid) -> list:
        return self._rows('SELECT * FROM batch_item WHERE TaskId=? ORDER BY Place, ItemId', (tid,))
    def batch_items_for(self, tids) -> list:
        tids = [int(t) for t in tids or [] if str(t).isdigit()]
        if not tids: return []
        return self._rows(f"SELECT TaskId, Place, State FROM batch_item WHERE TaskId IN ({','.join('?' * len(tids))}) ORDER BY TaskId, Place", tids)
    def batch_item(self, tid, conv):
        return self._one('SELECT * FROM batch_item WHERE TaskId=? AND ConversationId=?', (tid, conv))
    def update_batch_item(self, tid, conv, fields: dict) -> bool:
        d = {k: v for k, v in fields.items() if k in self.BATCH_ITEM_COLS}
        if not d or not self.batch_item(tid, conv): return False
        self._exec(f"UPDATE batch_item SET {', '.join(f'{k}=?' for k in d)}, UpdatedAt=? WHERE TaskId=? AND ConversationId=?",
                   (*d.values(), _now(), tid, conv))
        self._bump_snapshots(); self._poke('task-changed', task_id=tid)
        return True
    def open_batch(self, source_ref):
        """The newest open batch of this input - the one an arrival may join (batch.admit). An older one can still be open
        on items that wait for the owner."""
        r = self._one("SELECT TaskId FROM task WHERE SourceRef=? AND Status NOT IN ('done','dropped') ORDER BY TaskId DESC LIMIT 1",
                      (source_ref,))
        return r['TaskId'] if r else None
    def ranked_head(self, channel) -> list:
        """How many of this input's RANKED arrivals were judged into a task that still waits on the owner - not
        read (Next, Done), not put away (Later, Remind me), not closed. They hold the head: a drain judges only
        head_size minus these, so a sync cannot empty the queue behind them in waves (the owner, 2026-09-28: all
        eight pull requests were triaged, four at a time, where four were meant to wait)."""
        # ONE PLACE PER TASK: a pull request GitHub notified about twice had two ranked messages on one task - it held two
        # places in the head (one fewer arrival judged) and the rail's circled number read ② with no ① anywhere (the owner,
        # 2026-09-29: "i also only see number 2 why?"). The task's first ranked message stands for it.
        seen = set()
        return [r for r in self._ranked_rows(channel) if not (r['TaskId'] in seen or seen.add(r['TaskId']))]
    def _ranked_rows(self, channel) -> list:
        return self._rows("""SELECT m.MessageId, m.TaskId, m.RankValue FROM message m JOIN task t ON t.TaskId=m.TaskId
            WHERE m.Channel=? AND m.RankValue IS NOT NULL AND m.Status!='triaging'
              AND t.Status IN ('open','waiting','in_progress')
              -- ...a read or a put-away SINCE this task: a receipt from the message's earlier life (it was Next'd on an
              -- older task) freed a place it never held, and a fifth pull request was judged (2026-09-28)
              AND NOT EXISTS (SELECT 1 FROM processing_read_receipt r WHERE r.ReadAt >= t.CreatedAt
                                AND ((r.EntityKind='message' AND r.LocalId=CAST(m.MessageId AS TEXT))
                                     OR (r.EntityKind='task' AND r.LocalId=CAST(t.TaskId AS TEXT))))
              AND NOT EXISTS (SELECT 1 FROM processing_read_defer d WHERE d.At >= t.CreatedAt
                                AND d.TargetLocalId IN (CAST(m.MessageId AS TEXT), CAST(t.TaskId AS TEXT)))
            -- IN THE ORDER THEY WERE LET IN: each ranking call scales its own pool from 1.0, so a later arrival's value
            -- is not comparable with the head's - the order of admission is the batch's real order
            ORDER BY t.CreatedAt, t.TaskId""", (channel,))
    def set_message_danger(self, mid, text, aim=None):
        """What this message's text tries to make an AI or the owner do (one sentence), or nothing: the newest reading's word stands -
        and `aim`, whom: 'owner' for a scam on them, 'agent' (the default) for text written to steer the AI."""
        t = ' '.join(str(text or '').split())[:320]
        self._exec('UPDATE message SET Danger=?, DangerAim=? WHERE MessageId=?', (t or None, (aim if aim in ('owner', 'agent') else 'agent') if t else None, mid))
    def set_message_rank(self, mid, value: float, why: str, actor: str):
        """Where in the judging queue this arrival sits, and the words it got there by."""
        self._exec('UPDATE message SET RankValue=?, RankWhy=? WHERE MessageId=?', (float(value), str(why or ''), mid))
    # What was ON the mail: the screenshot of the spreadsheet, the invoice PDF. The bytes live on
    # disk (`Path`) - a database that grows by 8MB a mail is a database nobody backs up.
    def add_attachment(self, fields): return self._insert('attachment', fields, ATT_COLS, {'CreatedAt': _now()})
    def list_attachments(self, mid): return self._rows('SELECT * FROM attachment WHERE MessageId=? ORDER BY AttachmentId', (mid,))
    def get_attachment(self, aid): return self._one('SELECT * FROM attachment WHERE AttachmentId=?', (aid,))
    def attachment_exists(self, external_id):
        return self._one('SELECT 1 x FROM attachment WHERE ExternalId=?', (external_id,)) is not None
    # A session artifact is the long-form record the compact Agent work result points to. It is
    # task-owned rather than message-owned: hand-created research and coding sessions may have no
    # inbound message at all.
    def add_task_artifact(self, fields):
        return self._insert('task_artifact', fields, ARTIFACT_COLS, {'CreatedAt': _now()})
    def list_task_artifacts(self, task_id):
        return self._rows('SELECT * FROM task_artifact WHERE TaskId=? ORDER BY ArtifactId DESC', (task_id,))
    def get_task_artifact(self, aid):
        return self._one('SELECT * FROM task_artifact WHERE ArtifactId=?', (aid,))
    def task_artifact_by_ext(self, task_id, kind, ext_id):
        return self._one('SELECT * FROM task_artifact WHERE TaskId=? AND Kind=? AND ExtId=?', (task_id, kind, ext_id))
    def update_task_artifact(self, aid, fields):
        d = {k: fields[k] for k in ARTIFACT_COLS if k in fields and k not in ('TaskId', 'Kind', 'ExtId')}
        if d: self._exec(f"UPDATE task_artifact SET {','.join(f'{k}=?' for k in d)} WHERE ArtifactId=?", [*d.values(), aid])
    # A pty is not storage: the session's readable transcript is written here when it ends, so
    # "Done - wrap it up" still works an hour later, on a task whose CLI has long since exited.
    def add_transcript(self, task_id, sid, text, agent=None, cwd=None, ext_id=None, brain=None):
        # `brain` is WHICH CLI ran it, beside `agent` - the role. The task is never stamped with a
        # brain (it would go stale the moment the default changed), so the session is the record.
        if not (text or '').strip(): return None
        prev = self._one('SELECT ExtId FROM transcript WHERE Sid=?', (sid,)) or {}
        self._exec('DELETE FROM transcript WHERE Sid=?', (sid,))      # one row per session, always the latest
        return self._exec('INSERT INTO transcript (TaskId,Sid,Agent,Cwd,Text,ExtId,Brain,CreatedAt) VALUES (?,?,?,?,?,?,?,?)',
                          (task_id, sid, agent, cwd, text, ext_id or prev.get('ExtId') or '', brain, _now()))
    def note_session_id(self, task_id, sid, ext_id, agent=None, cwd=None, brain=None):
        """The CLI's OWN conversation id, filed the moment a hook or a rollout names it - NOT when
        the pane closes. keep() runs only on a clean exit, so a killed Taskuary (or a rebooted box)
        would otherwise take yesterday's resumable session with it."""
        if not (sid and ext_id): return None
        if self._one('SELECT TranscriptId FROM transcript WHERE Sid=?', (sid,)):
            return self._exec('UPDATE transcript SET ExtId=?, Brain=COALESCE(?, Brain) WHERE Sid=?', (ext_id, brain, sid))
        # the id is only meaningful to the CLI that made it, so it is filed with that CLI's name
        return self._exec('INSERT INTO transcript (TaskId,Sid,Agent,Cwd,Text,ExtId,CreatedAt,Brain) VALUES (?,?,?,?,?,?,?,?)',
                          (task_id, sid, agent, cwd, '', ext_id, _now(), brain))
    def resumable_session(self, task_id):
        """The newest session on this task whose CLI conversation can be reopened by its own id."""
        row = self._one("SELECT * FROM transcript WHERE TaskId=? AND COALESCE(ExtId,'')<>'' "
                        'ORDER BY TranscriptId DESC LIMIT 1', (task_id,))
        # ...on the CLI that MADE that conversation: the first row carrying its id. A resume that failed on the wrong CLI filed
        # the same id again under its own name, and the next continue read that and failed the same way (TQ-0887, three times)
        first = row and self._one("SELECT Brain FROM transcript WHERE TaskId=? AND ExtId=? AND COALESCE(Brain,'')<>'' "
                                  'ORDER BY TranscriptId LIMIT 1', (task_id, row['ExtId']))
        return {**row, 'Brain': first['Brain']} if first else row
    def agented_task_ids(self) -> set:
        """Every task an agent has ever touched - a live-session transcript, a headless run, or a run that reported on itself (a
        general agent leaves only its worker events: one that finished or failed was off the Board its column named, G7). The
        Board is the agents' board: a reply the owner answered by hand is finished work, not board work."""
        return {r['TaskId'] for r in self._rows('SELECT DISTINCT TaskId FROM transcript UNION SELECT DISTINCT TaskId FROM run '
                                                'UNION SELECT DISTINCT TaskId FROM worker_event') if r['TaskId']}
    def report_runs_before(self, conversation_id, mid):
        """Earlier runs of the SAME report, newest first. One report is one conversation
        (reports.py writes `report:<SourceId>` on every run), so this is what "the previous one"
        means without matching on titles that the owner is free to change."""
        return self._rows("SELECT MessageId, TaskId, Status, ExternalId FROM message "
                          "WHERE ConversationId=? AND MessageId<>? AND Direction<>'out' "
                          "ORDER BY MessageId DESC", (conversation_id, mid))
    def last_transcript(self, task_id):
        return self._one('SELECT * FROM transcript WHERE TaskId=? ORDER BY TranscriptId DESC LIMIT 1', (task_id,))

    def add_route(self, mid, tid, decision, score, reason, candidates, routed_by='router',
                  raw_output=None, parse_error=None, verdict=None):
        # the verdict's sender_class outranks the headers' guess on the message itself, so every reader of a row
        # (the chip, the Advisor, the evening brief, the coding agent's hold) sees the model's word without a join
        sc = (verdict or {}).get('sender_class') if isinstance(verdict, dict) else None
        if sc in ('person', 'automated', 'bulk') and mid: self._exec('UPDATE message SET SenderClass=? WHERE MessageId=?', (sc, mid))
        if isinstance(verdict, dict) and 'danger' in verdict and mid: self.set_message_danger(mid, verdict.get('danger'), verdict.get('danger_aim'))
        if isinstance(verdict, dict) and isinstance(verdict.get('meet'), dict) and mid:
            self._exec('UPDATE message SET MeetJson=? WHERE MessageId=?', (json.dumps(verdict['meet']), mid))
        if isinstance(verdict, dict) and isinstance(verdict.get('thread'), dict) and mid:
            verdict = {**verdict, 'thread': thread_pinned(verdict['thread'], mid)}
            if tid: self._exec('UPDATE task SET ThreadJson=? WHERE TaskId=?', (json.dumps(verdict['thread'], default=str), tid))
        if isinstance(verdict, dict) and tid: self.judge_task(tid, verdict, 'triage')     # how hard, how sure, what data (the router)
        return self._exec('''INSERT INTO route
            (MessageId,TaskId,Decision,Score,Reason,CandidatesJson,RoutedBy,CreatedAt,RawOutput,ParseError,VerdictJson)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                          (mid, tid, decision, score, reason, json.dumps(candidates), routed_by, _now(),
                           raw_output, parse_error,
                           json.dumps(verdict, default=str)[:8000] if verdict else None))
    def task_verdict(self, task_id):
        """The triage verdict a correction is measured against: the newest route row on this task
        that created the task and kept one. Follow-up messages now keep their own structured
        verdict for the Timeline, but must not replace the task's original routing decision.
        Absent for tasks routed before the column existed, and for the mechanical router."""
        row = self._one('SELECT VerdictJson FROM route WHERE TaskId=? AND VerdictJson IS NOT NULL '
                        "AND Decision<>'attach' ORDER BY RouteId DESC LIMIT 1", (task_id,))
        try: return json.loads(row['VerdictJson']) if row else None
        except Exception: return None
    def message_thread(self, mid):
        """Triage's newest reading of a message no task holds (a filed FYI, a report): off its own routes, the newest that has one -
        a later verdict without it (a CLI brain, an older TRIAGE.md) leaves the last reading standing. None when there never was one."""
        for r in self._rows('SELECT VerdictJson FROM route WHERE MessageId=? AND VerdictJson IS NOT NULL ORDER BY RouteId DESC', (mid,)):
            try: t = json.loads(r['VerdictJson']).get('thread')
            except Exception: continue
            if isinstance(t, dict): return t
        return None
    def task_thread(self, task_id):
        row = self._one('SELECT ThreadJson FROM task WHERE TaskId=?', (task_id,))
        try: t = json.loads(row['ThreadJson']) if row and row['ThreadJson'] else None
        except Exception: return None
        return t if isinstance(t, dict) else None
    def aside_mids(self, task_id):
        # every mail triage ever called aside on this task, across its verdicts
        out = set()
        for r in self._rows('SELECT VerdictJson FROM route WHERE TaskId=? AND VerdictJson IS NOT NULL', (task_id,)):
            try: out |= {o['mid'] for o in json.loads(r['VerdictJson'])['thread']['aside'] if isinstance(o['mid'], int) and o['mid']}
            except Exception: continue
        return out
    def list_routes(self, task_id): return self._rows('SELECT * FROM route WHERE TaskId=? ORDER BY RouteId', (task_id,))
    def _files_out(self):
        "Rows written before the Files field: the block at the end of a line's words, a task's ask or a kept note moved into its Files, once."
        for tbl, key, col in (('comment', 'CommentId', 'Body'), ('task', 'TaskId', 'Summary'), ('waitroom', 'WId', 'Note')):
            for k, v in self.cx.execute(f"SELECT {key}, {col} FROM {tbl} WHERE Files IS NULL AND {col} LIKE '%ATTACHED %(read these files)%'").fetchall():
                words, files = _legacy_split(v)
                if files: self.cx.execute(f'UPDATE {tbl} SET {col}=?, Files=? WHERE {key}=?', (words, files_json(files), k))
        # ...and a line kept for a turn kept its files in its own JSON (general.wait_line)
        for k, v in self.cx.execute("SELECT CommentId, Body FROM comment WHERE Files IS NULL AND ActorType='assistant_waiting' AND Body LIKE '%\"files\": [\"%'").fetchall():
            try: got = json.loads(v or '{}')
            except ValueError: continue
            if isinstance(got, dict) and got.get('files'):
                self.cx.execute('UPDATE comment SET Body=?, Files=? WHERE CommentId=?',
                                (json.dumps({n: x for n, x in got.items() if n != 'files'}), files_json(got['files']), k))
    def add_comment(self, task_id, actor, actor_type, body, line_id=None, files=None):
        """`files`: what he attached to this line of his - kept beside its words (files_json), never written into them. The comment and its
        row in the chat's log are ONE STEP under the store's lock (Windows CI, 2026-11-24: an answer filed, its turn's row written a beat later -
        a read at rest in that beat held an answer in no turn): a chat read (pinned_read) begins under the same lock, so it sees both or neither."""
        with self.lock: return self._add_comment(task_id, actor, actor_type, body, line_id, files)
    def _add_comment(self, task_id, actor, actor_type, body, line_id, files):
        cid = self._exec('INSERT INTO comment (TaskId,Actor,ActorType,Body,CreatedAt,LineId,Files) VALUES (?,?,?,?,?,?,?)',
                         (task_id, actor, actor_type, body, at := _now(), line_id, fj := files_json(files)))
        # ...a line of his is on the record (ledger.owner_line): the addresses he gave in it and the files he attached, known on every task
        if task_id and str(actor_type).startswith(('assistant_', 'concierge_')) and (files or '@' in str(body or '')):
            from . import ledger
            ledger.owner_line(self, task_id, actor, actor_type, body, files, at)
        # ...an answer filed ends its turn in the chat's log, in place (chatlog.answered: the one door every answer road goes through)
        if actor_type == 'assistant_agent' and task_id:
            from . import chatlog
            chatlog.answered(self, task_id, cid, actor, body, at)
        elif actor_type == 'assistant_summary' and task_id:
            from . import chatlog                    # ...and its summary goes with the turn whose answer it sums up, in place
            chatlog.summarized(self, task_id, body)
        elif line_id and task_id:
            from . import chatlog
            chatlog.filed(self, task_id, line_id, {'Body': body, 'ActorType': actor_type, 'CreatedAt': at, 'Files': fj})
        elif actor_type == 'assistant_user' and actor in ('owner', 'you') and task_id:
            from . import chatlog                    # ...a line of his filed with no name to hear it by: his line where it is filed
            chatlog.put(self, task_id, 'line', f'c:{cid}', {'at': at, **chatlog.his({'Body': body, 'Files': fj})}, src=f'comment:{cid}')
        return cid
    def add_comment_once(self, task_id, actor, actor_type, body, files=None):
        """Append a turn unless it is already the last turn on this task.

        Concierge auto-advance can be requested by more than one open browser or by a card and a
        simultaneous live event. Check-and-insert under the store lock so identical assistant
        turns cannot both become durable while those requests race.
        """
        with self.lock:
            last = self.cx.execute(
                'SELECT CommentId,Actor,ActorType,Body FROM comment WHERE TaskId=? ORDER BY CommentId DESC LIMIT 1',
                (task_id,)).fetchone()
            if last and last['Actor'] == actor and last['ActorType'] == actor_type and last['Body'] == body:
                return last['CommentId']
            # ...through add_comment's own door, so an answer filed this way is in the chat's log as one filed there (the demo's line after Send)
            return self.add_comment(task_id, actor, actor_type, body, files=files)
    def list_comments(self, task_id, internal: bool = False):
        """The task's comments, oldest first. PROMPT MACHINERY IS NOT A COMMENT (the owner, 2026-11-08): a brief Taskuary handed an agent ("THIS
        TASK IS A REPLY OWED..."), a turn's summary JSON, a line kept for a turn - each its own ActorType already (is_internal) - stays out of
        every reader (exports, search, the phone, an agent's my_task, the Assistant) unless it asks with `internal`: the agent's own
        machinery (general, sessionrecord, the task's state) does."""
        rows = self._rows('SELECT * FROM comment WHERE TaskId=? ORDER BY CommentId', (task_id,))
        return rows if internal else [c for c in rows if not is_internal(c)]
    def drop_comment(self, comment_id): self._exec('DELETE FROM comment WHERE CommentId=?', (comment_id,))
    def take_lines(self, task_id, kind, as_kind, words=lambda r: {'text': r['Body'], 'files': files_of(r)}, ids=None) -> list:
        """THE OWNER'S LINES KEPT FOR A TURN, taken by it (general.send_prompt): each `kind` row moved to the END of the conversation as an
        `as_kind` row - its words read out of the kept body by `words`, the time it was typed kept - so the conversation reads in the order the
        agent read it. In one step under the lock: two turns never take one line. [the rows as they waited], oldest first."""
        with self.lock:
            got = [dict(r) for r in self.cx.execute('SELECT * FROM comment WHERE TaskId=? AND ActorType=? ORDER BY CommentId', (task_id, kind))
                   if ids is None or r['CommentId'] in ids]       # `ids`: only the lines a session was handed - one kept since waits for its turn
            for r in got:
                self.cx.execute('DELETE FROM comment WHERE CommentId=?', (r['CommentId'],))
                w = words(r)              # ...{'text', 'files'} of the kept row: his words as the Body, his files beside them
                self.cx.execute('INSERT INTO comment (TaskId,Actor,ActorType,Body,CreatedAt,LineId,Files) VALUES (?,?,?,?,?,?,?)',
                                (task_id, r['Actor'], as_kind, w['text'], r['CreatedAt'], r.get('LineId'), files_json(w['files'])))
            if got: self.cx.commit(); self._writes += 1
        if got: self._poke('task-changed', task_id=task_id)
        return got
    def snap_draft(self, review_id, comment_id) -> bool:
        """Keep review `review_id` as it stands, under the turn `comment_id` that left it - only when its words changed since the last turn
        kept it: a turn that left the draft untouched did not write it, so it is not drawn there again. True when one was kept."""
        rv = self._one('SELECT rv.TaskId, rv.DraftText, m.FromName, m.FromEmail, m.Subject FROM review rv LEFT JOIN message m '
                       'ON m.MessageId=COALESCE(rv.AnswersMid, rv.MessageId) WHERE rv.ReviewId=?', (review_id,))
        if not rv or not str(rv.get('DraftText') or '').strip(): return False
        last = self._one('SELECT Text FROM draft_snapshot WHERE ReviewId=? ORDER BY Id DESC LIMIT 1', (review_id,))
        if last and last['Text'] == rv['DraftText']: return False
        self._exec('INSERT INTO draft_snapshot (TaskId, ReviewId, CommentId, Text, ToName, Subject, CreatedAt) VALUES (?,?,?,?,?,?,?)',
                   (rv['TaskId'], review_id, comment_id, rv['DraftText'], rv.get('FromName') or rv.get('FromEmail') or '', rv.get('Subject') or '', _now()))
        return True
    def draft_snapshots(self, task_id) -> dict:
        "Each turn's kept drafts, by the turn's CommentId: [{review, text, to, subject, at}], oldest first."
        out = {}
        for r in self._rows('SELECT * FROM draft_snapshot WHERE TaskId=? ORDER BY Id', (task_id,)):
            out.setdefault(r['CommentId'], []).append({'review': r['ReviewId'], 'text': r['Text'], 'to': r['ToName'] or '', 'subject': r['Subject'] or '', 'at': r['CreatedAt']})
        return out
    def set_comment_body(self, comment_id, body):
        """Rewrite one turn where it stands: the day's opener is drawn at once and filled when the mail is in (welcome.arrive)."""
        self._exec('UPDATE comment SET Body=? WHERE CommentId=?', (body, comment_id))

    # audit chain
    def audit(self, et, eid, action, actor, actor_type='human', detail=None, run_id=None):
        """One row, linked to the one before it - and the read of "the one before it" and the write
        have to be the SAME critical section. They were two: _one took the lock, released it, then
        _exec took it again. So the poll thread and a click could both read the same last row and
        both insert, each pointing at the same parent - a FORK, which verification then reported as
        a broken chain. A tamper-evident log that breaks itself is worse than none: it makes a real
        tamper indistinguishable from its own noise. (Seen at ids 151/152 of a live database, both
        stamped the same second, both carrying the same PrevHash.)"""
        from .guard import masked_detail
        d = masked_detail(detail if isinstance(detail, str) or detail is None else json.dumps(detail, default=str))
        with self.lock:
            row = self.cx.execute('SELECT RowHash FROM audit ORDER BY Id DESC LIMIT 1').fetchone()
            prev = (row['RowHash'] if row and row['RowHash'] else None) or GENESIS
            rh = chain_hash(prev, _audit_payload(et, eid, action, actor, actor_type, run_id, d))
            aid = self.cx.execute('INSERT INTO audit (EntityType,EntityId,Action,Actor,ActorType,RunId,Detail,PrevHash,RowHash,CreatedAt) VALUES (?,?,?,?,?,?,?,?,?,?)',
                                  (et, eid, action, actor, actor_type, run_id, d, prev, rh, _now())).lastrowid
            self.cx.commit()
        from . import events                     # ...a press of his on a task is a fact its agent hears (events.audited)
        events.audited(self, et, eid, action, actor, d)
        # ...HIS PRESS ON A TASK is a line of its chat from the moment he makes it (chatlog.pressed: the one hook for every press road)
        if et == 'task' and eid and actor in ('owner', 'you'):
            from . import chatlog
            chatlog.pressed(self, int(eid), aid, action)
    # ── what went wrong, and what happened (lookups.py: errors.list, activity.list) ──
    def audit_since(self, since, limit=400) -> list:
        return self._rows('SELECT EntityType, EntityId, Action, Actor, ActorType, Detail, CreatedAt FROM audit WHERE CreatedAt>=? '
                          'ORDER BY Id DESC LIMIT ?', (since, limit))
    def running_runs(self) -> list:
        return self._rows("SELECT RunId, TaskId, AgentName, StartedAt FROM run WHERE Status='running' ORDER BY RunId DESC")
    def failures_since(self, since) -> dict:
        """Every place a failure is written down, from `since`: agent runs, report runs, drafts, triage, operations."""
        q = lambda sql: self._rows(sql, (since,))
        return {'agent runs': q("SELECT TaskId, AgentName Who, LastError Error, IFNULL(FinishedAt, UpdatedAt) At FROM run "
                                "WHERE Status='error' AND IFNULL(FinishedAt, IFNULL(UpdatedAt, StartedAt))>=? ORDER BY RunId DESC LIMIT 20"),
                'report runs': q("SELECT NULL TaskId, Title Who, Error, At FROM report_run WHERE Failed=1 AND At>=? ORDER BY RunId DESC LIMIT 20"),
                'drafts': q("SELECT TaskId, Kind Who, DraftError Error, CreatedAt At FROM review WHERE IFNULL(DraftError,'')<>'' AND CreatedAt>=? "
                            'ORDER BY ReviewId DESC LIMIT 20'),
                'triage': q("SELECT TaskId, 'm' || MessageId Who, ParseError Error, CreatedAt At FROM route WHERE IFNULL(ParseError,'')<>'' "
                            'AND CreatedAt>=? ORDER BY RouteId DESC LIMIT 20'),
                'actions': q("SELECT NULL TaskId, Kind Who, Error, IFNULL(ExecutedAt, UpdatedAt) At FROM operation WHERE IFNULL(Error,'')<>'' "
                             'AND IFNULL(ExecutedAt, UpdatedAt)>=? ORDER BY UpdatedAt DESC LIMIT 20')}
    def reopened_at(self, task_id):
        """When new mail or chat last reopened this task (ingest._reopen's audit row), or None."""
        r = self._one("SELECT MAX(CreatedAt) m FROM audit WHERE EntityType='task' AND EntityId IN (?,?) AND Action='reopen'", (task_id, str(task_id)))
        return (r or {}).get('m')
    def closeouts(self, task_id) -> list:
        """Every time this task was closed and opened again, oldest first: {what: 'closed'|'reopened', at, to, note}. Close out is drawn
        in ROUNDS from it (the owner, 2026-11-01: "now that a new message can reopen close out can happen multiple times") - each close
        ends one, its note with it ("Closed out: ..." is written just before the close it is the note of), and a reopen starts the next.
        Closes are the ledger's task.closed rows (outcomes.py, the one close door); a done task whose close predates the ledger keeps
        its ClosedAt. Reopens are the audit's - new mail's (ingest._reopen) and a Reopen press's (update_task), one per moment."""
        tid, cs, rs = int(task_id), [], []
        notes = [(str(c['CreatedAt'] or ''), str(c['Body'])[len('Closed out: '):]) for c in self.list_comments(tid) if str(c.get('Body') or '').startswith('Closed out: ')]
        for r in self._rows("SELECT At, FactsJson FROM outcome WHERE Kind='task.closed' AND TargetKind='task' AND TargetId=? ORDER BY Id", (tid,)):
            try: to = (json.loads(r['FactsJson'] or '{}') or {}).get('to') or 'done'
            except ValueError: to = 'done'
            cs.append({'what': 'closed', 'at': str(r['At'] or ''), 'to': to, 'note': ''})
        t = self.get_task(tid) or {}
        if t.get('Status') in ('done', 'dropped') and t.get('ClosedAt') and not any(e['at'][:16] >= str(t['ClosedAt'])[:16] for e in cs):
            cs.append({'what': 'closed', 'at': str(t['ClosedAt']), 'to': t['Status'], 'note': ''})
        # ...new mail's reopen is said twice, by the write ('reopened') and then by its door ('reopen', ingest._reopen): one reopen
        said = self._rows("SELECT Action, CreatedAt FROM audit WHERE EntityType='task' AND EntityId IN (?,?) AND Action IN ('reopen','reopened') "
                          "ORDER BY Id", (tid, str(tid)))
        # ...whichever of the two was written first (general.reopen writes its door's row before the store's own)
        rs = [{'what': 'reopened', 'at': str(r['CreatedAt'] or '')} for i, r in enumerate(said)
              if not (r['Action'] == 'reopen' and ((i and said[i - 1]['Action'] == 'reopened') or (i + 1 < len(said) and said[i + 1]['Action'] == 'reopened')))]
        # ...in turn: a task is closed, then opened, then closed - the clock is to the second, and a Reopen and the next close can share one
        ev, want = [], 'closed'
        while cs or rs:
            c, r = (cs[0]['at'][:19] if cs else None), (rs[0]['at'][:19] if rs else None)
            take = cs if r is None or (c is not None and (c < r or (c == r and want == 'closed'))) else rs
            ev.append(take.pop(0)); want = 'reopened' if ev[-1]['what'] == 'closed' else 'closed'
        for e in ev:                                  # ...each note the close it was written for: the first one at or after it
            if e['what'] != 'closed': continue
            mine = [b for at, b in notes if at <= e['at'][:19]]
            if mine: e['note'], notes = mine[-1], notes[len(mine):]
        return ev
    def list_audit(self, et=None, eid=None, limit=200):
        "Audit rows, newest first - a row written before secrets were kept out of it (guard.masked_detail) read without them too."
        from .guard import masked_detail
        rows = self._rows('SELECT * FROM audit WHERE EntityType=? AND EntityId=? ORDER BY Id DESC LIMIT ?', (et, eid, limit)) if et else \
            self._rows('SELECT * FROM audit ORDER BY Id DESC LIMIT ?', (limit,))
        return [{**r, 'Detail': masked_detail(r.get('Detail'))} for r in rows]
    def verify_audit_chain(self):
        """Two different failures, and calling both "broken" was the problem.

        ALTERED: the row's own hash does not match its own contents. Somebody edited the row -
        this is what the log exists to catch, and it is never innocent.

        FORKED: the row hashes its own contents correctly against the PrevHash it recorded, but
        that PrevHash is not the row before it. Nothing was edited; two writers raced (see
        audit()). Reporting that as tampering cried wolf about a bug in this file."""
        prev, altered, forked = GENESIS, [], []
        for r in self._rows('SELECT * FROM audit ORDER BY Id'):
            payload = _audit_payload(r['EntityType'], r['EntityId'], r['Action'], r['Actor'],
                                     r['ActorType'], r['RunId'], r['Detail'])
            if r['RowHash'] != chain_hash(r['PrevHash'] or GENESIS, payload): altered.append(r['Id'])
            elif r['PrevHash'] != prev: forked.append(r['Id'])
            prev = r['RowHash'] or chain_hash(prev, payload)
        return {'rows': len(self._rows('SELECT Id FROM audit')), 'ok': not (altered or forked),
                'altered_ids': altered, 'forked_ids': forked,
                # kept so anything reading the old shape still sees every id that failed
                'broken_ids': sorted(altered + forked)}

    # agents & runs
    def list_agents(self, active_only=True):
        return self._rows('SELECT * FROM agent' + (' WHERE Active=1' if active_only else ''))
    def get_agent(self, name): return self._one('SELECT * FROM agent WHERE Name=?', (name,))
    def upsert_agent(self, name, kind, runner, config):
        if self.get_agent(name): self._exec('UPDATE agent SET Kind=?, Runner=?, Config=? WHERE Name=?', (kind, runner, config, name))
        else: self._exec('INSERT INTO agent (Name,Kind,Runner,Config) VALUES (?,?,?,?)', (name, kind, runner, config))
    def start_run(self, task_id, agent_name, instruction, by):
        rid = self._exec('INSERT INTO run (TaskId,AgentName,Instruction,DispatchedBy,StartedAt) VALUES (?,?,?,?,?)',
                         (task_id, agent_name, instruction, by, _now()))
        # Older/background executors still record a `run` instead of opening a terminal. They
        # obey the same ownership contract: the configured profile name, not its underlying CLI,
        # stays on the task before anyone sees the run as live.
        if agent_name and (self.get_task(task_id) or {}).get('Assignee') != f'agent:{agent_name}':
            self.update_task(task_id, {'Assignee': f'agent:{agent_name}'}, by)
        self._poke('run-tail', 'task-changed', task_id=task_id, run_id=rid)
        return rid
    def update_run(self, run_id, fields, finished=False):
        cols = [c for c in RUN_COLS if c in fields]
        fin = f", FinishedAt='{_now()}'" if finished else ''
        self._exec(f"UPDATE run SET {','.join(f'{c}=?' for c in cols)}, UpdatedAt=?{fin} WHERE RunId=?",
                   [fields[c] for c in cols] + [_now(), run_id])
        row = self.get_run(run_id)
        if row: self._poke('run-tail', 'task-changed', task_id=row.get('TaskId'), run_id=run_id)
    def get_run(self, run_id): return self._one('SELECT * FROM run WHERE RunId=?', (run_id,))
    def running_runs(self):
        return self._rows("SELECT * FROM run WHERE Status='running' ORDER BY RunId DESC")
    def list_runs(self, task_id): return self._rows('SELECT * FROM run WHERE TaskId=? ORDER BY RunId DESC', (task_id,))

    # the dispatch queue: tasks held back from auto-start because a running agent's work would
    # likely collide (BehindTaskId) or every session slot is busy (NULL) - see blackboard.drain
    def enqueue_dispatch(self, task_id, behind, agent, reason, value=None, why=None, brief=None, turn=None):
        if self._one('SELECT 1 x FROM dispatchq WHERE TaskId=?', (task_id,)):
            if brief: self._exec('UPDATE dispatchq SET Brief=? WHERE TaskId=?', (brief, task_id))     # the newer ask is the one to start on
            if turn: self._exec('UPDATE dispatchq SET Turn=? WHERE TaskId=?', (turn, task_id))
            return None
        qid = self._exec('INSERT INTO dispatchq (TaskId,BehindTaskId,Agent,Reason,CreatedAt,Value,Floor,Why,Brief,Turn) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (task_id, behind, agent, reason, _now(), value, value, why, brief, turn))
        # Queued is already assigned work: waiting for a free desk must not look unowned. The
        # profile name survives the queue and the eventual session, regardless of whether triage
        # or the owner created the task.
        if agent and (self.get_task(task_id) or {}).get('Assignee') != f'agent:{agent}':
            self.update_task(task_id, {'Assignee': f'agent:{agent}'}, 'router')
        return qid
    def queued_dispatches(self):
        # by value where one is set, arrival order among equals; an unranked (clear-mode) row
        # counts as the base value, so ranked and unranked queues interleave sensibly
        return self._rows('SELECT * FROM dispatchq ORDER BY COALESCE(Value, 0.5) DESC, QId')
    def set_dispatch_value(self, task_id, value, why=None, floor_=None):
        self._exec('UPDATE dispatchq SET Value=?, Why=COALESCE(?, Why), Floor=COALESCE(?, Floor) WHERE TaskId=?', (value, why, floor_, task_id))
    def clear_dispatch(self, task_id): self._exec('DELETE FROM dispatchq WHERE TaskId=?', (task_id,))
    def get_dispatch(self, task_id): return self._one('SELECT * FROM dispatchq WHERE TaskId=?', (task_id,))
    def dispatch_failed(self, task_id, error: str, permanent: bool = False, backoff=(30, 120), max_attempts: int = 3) -> dict:
        """One failed start attempt on the queue row (PW-085/086): the count, the error and the next try are
        persisted, so a restart cannot reset the budget. A permanent failure, or the last allowed attempt,
        leaves the row 'failed' with no next try - the owner's Retry starts a new cycle."""
        row = self.get_dispatch(task_id)
        if not row: return None
        n = int(row.get('Attempts') or 0) + 1
        done = permanent or n >= max_attempts
        wait = None if done else backoff[min(n - 1, len(backoff) - 1)]
        nxt = None if done else (datetime.now() + timedelta(seconds=wait)).isoformat(sep=' ', timespec='seconds')
        self._exec('UPDATE dispatchq SET Attempts=?, LastError=?, NextAt=?, State=? WHERE TaskId=?',
                   (n, str(error)[:500], nxt, 'failed' if done else 'retrying', task_id))
        self._poke('task-changed', task_id=task_id)
        return {**self.get_dispatch(task_id), 'wait': wait}
    def dispatch_retry(self, task_id) -> bool:
        """The owner's Retry: a fresh bounded cycle on the same row (PW-087)."""
        if not self.get_dispatch(task_id): return False
        self._exec("UPDATE dispatchq SET Attempts=0, NextAt=NULL, State='waiting' WHERE TaskId=?", (task_id,))
        self._poke('task-changed', task_id=task_id)
        return True

    # the waiting room (waitroom.py): owner notes queued on a task while its agent works
    def add_waiting(self, task_id, note, actor, files=None):
        if files:                                    # ...the files of a note he kept for a coding agent, on the record (ledger.his_line)
            from . import ledger
            ledger.his_line(self, task_id, '', files)
        return self._exec('INSERT INTO waitroom (TaskId, Note, CreatedBy, CreatedAt, Files) VALUES (?,?,?,?,?)', (task_id, note, actor, _now(), files_json(files)))
    def waiting_notes(self, task_id): return self._rows('SELECT * FROM waitroom WHERE TaskId=? AND DeliveredAt IS NULL ORDER BY WId', (task_id,))
    def waitroom(self, task_id, limit=40):
        return self._rows('SELECT * FROM waitroom WHERE TaskId=? ORDER BY WId DESC LIMIT ?', (task_id, limit))[::-1]
    def tasks_with_waiting(self): return [r['TaskId'] for r in self._rows('SELECT DISTINCT TaskId FROM waitroom WHERE DeliveredAt IS NULL ORDER BY TaskId')]
    def waiting_counts(self):
        return {r['TaskId']: r['n'] for r in self._rows('SELECT TaskId, COUNT(*) n FROM waitroom WHERE DeliveredAt IS NULL GROUP BY TaskId')}
    def deliver_waiting(self, wids, how):
        if wids: self._exec(f"UPDATE waitroom SET DeliveredAt=?, How=? WHERE WId IN ({','.join('?' * len(wids))})", (_now(), how, *wids))
    def drop_waiting(self, wid, task_id=None):
        # only an undelivered note can be withdrawn - a delivered one is already in the agent's hands
        self._exec('DELETE FROM waitroom WHERE WId=? AND DeliveredAt IS NULL' + (' AND TaskId=?' if task_id else ''),
                   (wid, task_id) if task_id else (wid,))

    # reviews (orphans - reviews whose task is gone - never surface)
    def _poke_review(self, review):
        """A review changes both places that render it: its message and its task - and its card in the task's chat log is written HERE, at
        the source, as it changes (chatlog.advance: every road that raises, presses or settles a review comes through here)."""
        if not review: return
        if review.get('TaskId'):                # ...raised, pressed, sent, withdrawn, set aside or failed: its card says so where it stood
            from . import chatlog                # ...put by the log's own worker, never under what this write's caller holds (advance_soon)
            chatlog.advance_soon(self, review['TaskId'], review.get('ReviewId'))
            from . import events                 # ...and its state, once, for the agent (events.card)
            events.card(self, review)
        kinds = []
        if review.get('MessageId'): kinds.append('feed-changed')
        if review.get('TaskId'): kinds.append('task-changed')
        if kinds:
            self._poke(*kinds, review_id=review.get('ReviewId'),
                       message_id=review.get('MessageId'), task_id=review.get('TaskId'))
    def _review_changed(self, rid): self._poke_review(self.get_review(rid))
    def add_review(self, fields):
        # A review that NEEDS a task says so, by naming it. Three callers file one that nothing
        # else owns - a setting proposed in chat, a Zoho invoice, an outbound report - and once
        # the task page is gone those have no page to be answered on, so they ask for a task here.
        #
        # This is opt-in, deliberately, and a blanket "every review gets a task" was tried first
        # and is wrong: answering filed chatter is a REPLY, not a project (server.py, the /reply
        # endpoint), and minting a task to hold that review puts a TQ badge on "it was just his
        # demo". A task-less review is not stranded either way - the funnel gives it the `approve`
        # lane and the assistant decides it by rid, with no tid needed (2026-09-22).
        fields = dict(fields)
        title, kind = fields.pop('_task_title', None), fields.pop('_task_kind', None)
        if title and not fields.get('TaskId'):
            fields['TaskId'] = self.create_task(
                {'Title': str(title)[:140], 'Kind': kind or 'task', 'Status': 'open', 'Source': 'review'}, 'system')
        rid = self._insert('review', fields, REVIEW_COLS, {'CreatedAt': _now()})
        self._poke_review({**fields, 'ReviewId': rid})
        # Sync and triage run independently. If the owner answered in WhatsApp/Teams/mail while
        # triage was still drafting, the context row can beat this insert. Reconcile in both
        # directions so thread timing -- rather than worker timing -- decides whether a draft lives.
        # This reverse-order repair is intentionally limited to triage-created reply work. A
        # person can deliberately ask for a follow-up draft after their last sent message; that
        # new instruction must stay pending. Once any draft is already pending, the normal sync
        # path in channels.py still retires it when a newer owner reply arrives.
        triage_reply = fields.get('Origin') == 'triage'
        if fields.get('Status') == 'pending' and triage_reply and fields.get('MessageId'):
            target = self.get_message(fields['MessageId']) or {}
            conv, after = target.get('ConversationId'), target.get('SentAt')
            sent = self._one("SELECT * FROM message WHERE Status='context' AND ConversationId=? AND SentAt>=? "
                             'ORDER BY SentAt DESC, MessageId DESC LIMIT 1', (conv, after)) if conv and after else None
            if sent:
                from .channels import retire_draft_answered_elsewhere
                retire_draft_answered_elsewhere(self, fields.get('TaskId'), sent, later=True)   # a model read, never inside this write
        return rid
    def get_review(self, rid): return self._one('SELECT * FROM review WHERE ReviewId=?', (rid,))
    def reviews_for_message(self, mid):
        """Every review on a taskless message as well as reviews attached to a task.

        Timeline detail for an FYI has no task_detail() to carry these. Without this query the
        feed chip could truthfully say reply ready while reopening the item produced an empty
        Reply tab.
        """
        return self._rows('SELECT * FROM review WHERE MessageId=? ORDER BY ReviewId DESC', (mid,))
    def list_reviews(self, status=None):
        # the inbound text rides along: the queue shows what they wrote above what we would say back
        q = f'''SELECT rv.*, t.Title, m.Subject, m.FromName, m.FromEmail, m.SentAt,
                       m.Channel, m.SourceName, m.ConversationId, substr(m.BodyText, 1, 1500) Preview {_REVIEW_FROM}
                WHERE {_NOT_ORPHAN} AND {_VISIBLE_PENDING}'''
        return self._rows(q + (' AND rv.Status=?' if status else '') + ' ORDER BY rv.ReviewId DESC', (status,) if status else ())
    def waiting_reviews(self):
        """WHAT WAITS ON THE OWNER'S PRESS, for every list that SAYS so - the page's queue, the Assistant's view, the digest, the phone: the
        pending reviews less any reply draft the thread has moved past (proposals.written_past - the one rule the chat greys it by and the
        task's state reads). A road that DECIDES about a pending row (what his own line may have answered, an item that ended upstream)
        reads list_reviews: the row is still pending there until its agent hears the newer message."""
        return self._stands(self.list_reviews('pending'))
    def _stands(self, rows) -> list:
        """THE ONE RULE FOR WHAT WAITS ON HIS PRESS, over pending review rows: less any reply draft the thread has moved past
        (proposals.written_past - the one rule the chat greys it by), any card that waits behind another on its task (cardqueue: one
        stands at a time, on every surface) and an obsolete read request. waiting_reviews (every task) and waiting_on_owner (one) read it."""
        from . import cardqueue
        off = {}
        gone = lambda t: off[t] if t in off else off.setdefault(t, self.off_table(t))
        return [r for r in rows if not (r.get('TaskId') and r['ReviewId'] in gone(r['TaskId'])) and not cardqueue.obsolete_read(self, r.get('TaskId'), r)]
    def off_table(self, tid) -> set:
        "The pending review ids on task `tid` that do not stand for his press: a draft the thread moved past, a card waiting behind another."
        from . import cardqueue, proposals
        return proposals.written_past(self, tid) | cardqueue.held(self, tid)
    @contextlib.contextmanager
    def review_delivery_edit(self, rid):
        """Exclude send claims while attachment bytes/envelopes change, even in another process."""
        with _DELIVERY_LOCK, self.lock:
            self._clear_stale(); self.cx.execute('BEGIN IMMEDIATE')
            try:
                row = self.get_review(rid) or {}
                if row.get('DeliveryClaim') or row.get('DeliveryState') in ('sending', 'unknown', 'sent'):
                    raise ValueError('the attempted attachments must be kept while delivery is in progress or unknown')
                yield
                self.cx.commit()
            except BaseException:
                self.cx.rollback(); raise
    def set_review_deliver(self, rid, deliver: str):
        """The delivery envelope - who it goes to, and now WHAT RIDES WITH IT (verdicts.attach)."""
        with _DELIVERY_LOCK, self.lock:
            cur = self.cx.execute("UPDATE review SET Deliver=? WHERE ReviewId=? AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'') NOT IN ('sending','unknown','sent')", (deliver, rid))
            self.cx.commit(); self._writes += 1
        if cur.rowcount: self._review_changed(rid)
        return bool(cur.rowcount)
    def recover_review_deliveries(self, rid=None):
        """An interrupted attempt is unknown, never a sent receipt or a fresh draft.

        Check ownership before clearing a claim: another SQLite connection or server
        process may still be waiting on the provider. A claim has no expiry that could
        allow a slow send and its retry to overlap.
        """
        changed = []
        with _DELIVERY_LOCK, self.lock:
            query = 'SELECT * FROM review WHERE (DeliveryClaim IS NOT NULL OR (DeliveryState IS NULL AND Deliver IS NOT NULL))'
            rows = self.cx.execute(query + (' AND ReviewId=?' if rid is not None else ''), (rid,) if rid is not None else ()).fetchall()
            for raw in rows:
                row = dict(raw)
                try: env = json.loads(row.get('Deliver') or '{}') or {}
                except (TypeError, ValueError): env = {}
                if not isinstance(env, dict): env = {}
                state = row.get('DeliveryState') or env.get('delivery')
                claim = row.get('DeliveryClaim')
                if claim and _delivery_claim_alive(claim): continue
                if claim:
                    state = 'unknown'; env['delivery'] = state
                    reason = 'Delivery unknown after an interrupted attempt; check with the provider before any retry.'
                    # ...with who pressed it, as an attempt that ends unknown in its own process keeps them (finish_review_delivery): without them
                    # its agent heard nothing of a send that may have gone (events.card), and could set it up again
                    try: by = json.loads(row.get('DeliveryEnvelope') or '{}').get('actor') or 'owner'
                    except (TypeError, ValueError, AttributeError): by = 'owner'
                    self.cx.execute("UPDATE review SET DeliveryState=?, DeliveryClaim=NULL, Deliver=?, Reason=?, DecidedBy=?, DecidedAt=? WHERE ReviewId=? AND DeliveryClaim=?",
                                    (state, json.dumps(env), reason, by, _now(), row['ReviewId'], claim))
                elif state in ('sent', 'failed', 'unknown'):
                    self.cx.execute('UPDATE review SET DeliveryState=? WHERE ReviewId=? AND DeliveryState IS NULL', (state, row['ReviewId']))
                else: continue
                changed.append(row['ReviewId'])
            if changed:
                self.cx.commit(); self._writes += 1
        for review_id in changed: self._review_changed(review_id)
        return len(changed)
    def claim_review_delivery(self, rid, snapshot, expected):
        """Atomically claim one pending review across threads and SQLite connections.

        The payload is durable before sending. Unknown attempts keep their original
        payload for reconciliation, even if the owner has since edited the draft.
        """
        self.recover_review_deliveries(rid)
        token = _DELIVERY_PROCESS + uuid.uuid4().hex
        claimed = None
        with _DELIVERY_LOCK, self.lock:
            self._clear_stale(); self.cx.execute('BEGIN IMMEDIATE')
            try:
                raw = self.cx.execute('SELECT * FROM review WHERE ReviewId=?', (rid,)).fetchone()
                row = dict(raw) if raw else {}
                fields = ('Status', 'DraftText', 'Deliver', 'ContextRevision', 'Stale', 'TaskId', 'MessageId', 'Kind')
                if (not row or row.get('Status') != 'pending' or row.get('DeliveryClaim')
                        or row.get('DeliveryState') == 'sent'
                        or any(row.get(k) != expected.get(k) for k in fields)):
                    self.cx.rollback(); return None
                previous = row.get('DeliveryState') or ''
                uncertain = previous in ('unknown', 'sending')
                state = 'unknown' if uncertain else 'sending'
                saved = row.get('DeliveryEnvelope') if uncertain else json.dumps(snapshot)
                # Older unknown envelopes predate the durable payload. Their approved
                # FinalText is the best record available; never reconcile a new edit.
                if uncertain and not saved:
                    saved_snapshot = copy.deepcopy(snapshot)
                    saved_snapshot['body'] = row.get('FinalText') or row.get('DraftText') or snapshot['body']
                    saved_snapshot['attempted_at'] = row.get('DeliveryAttemptedAt') or snapshot['envelope'].get('attempted_at')
                    saved = json.dumps(saved_snapshot)
                attempted = (row.get('DeliveryAttemptedAt') or snapshot['envelope'].get('attempted_at')) if uncertain else snapshot['attempted_at']
                env = copy.deepcopy(snapshot['envelope'])
                if uncertain:
                    try: env = json.loads(saved)['envelope']
                    except (TypeError, ValueError, KeyError): pass
                env['delivery'] = state
                if attempted: env['attempted_at'] = attempted
                # ...and WHY THE LAST ATTEMPT DID NOT GO is that attempt's, not this one's: every attempt that does not send writes its own
                # reason (finish_review_delivery), so one that does send must not leave "Not sent: ..." on a sent mail (the agent walk,
                # 2026-11-09: refused once, sent on the retry, and its agent was told "not sent" and offered to send it again)
                self.cx.execute('UPDATE review SET DeliveryState=?, DeliveryClaim=?, DeliveryEnvelope=?, DeliveryAttemptedAt=?, Deliver=?, '
                                'Reason=CASE WHEN ? THEN NULL ELSE Reason END WHERE ReviewId=? AND Status=\'pending\' AND DeliveryClaim IS NULL',
                                (state, token, saved, attempted, json.dumps(env), bool(previous), rid))
                self.cx.commit(); self._writes += 1
                _DELIVERY_CLAIMS.add(token)
                claimed = {'token': token, 'previous': previous, 'snapshot': json.loads(saved)}
            except BaseException:
                self.cx.rollback(); raise
        self._review_changed(rid)
        return claimed
    def start_review_delivery(self, rid, token, snapshot):
        """Record a fresh attempt after the previous one was confirmed absent."""
        env = copy.deepcopy(snapshot['envelope'])
        env.update(delivery='sending', attempted_at=snapshot['attempted_at'])
        with _DELIVERY_LOCK, self.lock:
            cur = self.cx.execute("UPDATE review SET DeliveryState='sending', DeliveryEnvelope=?, DeliveryAttemptedAt=?, Deliver=? WHERE ReviewId=? AND DeliveryClaim=?",
                                  (json.dumps(snapshot), snapshot['attempted_at'], json.dumps(env), rid, token))
            self.cx.commit(); self._writes += 1
        if cur.rowcount: self._review_changed(rid)
        return bool(cur.rowcount)
    def finish_review_delivery(self, rid, token, state, receipt=None, reason=None, fix=None):
        """Commit a provider outcome before any task lifecycle bookkeeping. `fix` ({label, href}, outbound.Fixable) rides in
        the envelope, so the draft's row offers the place that fixes a failed send after a reload too."""
        changed = False
        with _DELIVERY_LOCK, self.lock:
            raw = self.cx.execute('SELECT * FROM review WHERE ReviewId=? AND DeliveryClaim=?', (rid, token)).fetchone()
            if raw:
                row = dict(raw); snapshot = json.loads(row['DeliveryEnvelope'])
                env = copy.deepcopy(snapshot['envelope'])
                env.update(delivery=state, attempted_at=row.get('DeliveryAttemptedAt'))
                if fix: env['fix'] = fix
                else: env.pop('fix', None)
                status = snapshot['status'] if state == 'sent' else 'pending'
                cur = self.cx.execute('UPDATE review SET Status=CASE WHEN Status=\'pending\' THEN ? ELSE Status END, FinalText=?, DraftText=CASE WHEN ?=\'sent\' THEN DraftText ELSE ? END, '
                                      'DecidedBy=?, DecidedAt=?, DecideNote=?, DeliveryState=?, DeliveryClaim=NULL, DeliveryReceipt=?, Deliver=?, Reason=COALESCE(?,Reason) '
                                      'WHERE ReviewId=? AND DeliveryClaim=?',
                                      (status, snapshot['body'], state, snapshot['body'], snapshot['actor'], _now(), snapshot.get('note'), state,
                                       json.dumps(receipt) if receipt is not None else None, json.dumps(env), reason, rid, token))
                self.cx.commit(); self._writes += 1; changed = bool(cur.rowcount)
            _DELIVERY_CLAIMS.discard(token)
        if changed and state == 'sent':
            from . import ledger
            try: ledger.sent(self, rid)               # ...on the record: a send the provider confirmed is what every task reads went (ledger.py)
            except Exception as e: logger.warning(f'review {rid}: sent, and not written to the ledger - {e}')
        if changed: self._review_changed(rid)
        return changed
    def decide_review(self, rid, status, final, by, note=None, was=('pending', 'held')):
        "`was`: the states it may be decided from - a draft the chat set aside ('superseded') is still the agent's to retire (verdicts.not_needed)."
        with self.lock:
            cur = self.cx.execute(f"UPDATE review SET Status=?, FinalText=?, DecidedBy=?, DecidedAt=?, DecideNote=? WHERE ReviewId=? "
                                  f"AND Status IN ({','.join('?' * len(was))}) AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'')<>'sent'",
                                  (status, final, by, _now(), note, rid, *was))
            self.cx.commit(); self._writes += 1
        if cur.rowcount: self._review_changed(rid)
        return bool(cur.rowcount)
    def pending_review(self, task_id, kind=None, live_only=True):
        """The task's newest pending review ROW, for a road that DECIDES about it - re-draft into it, answer it, retire it, dismiss it on a
        close. It is NOT what waits on his press: a draft held behind another card or one the thread moved past is still found here.
        Whatever is SHOWN or LIT for him asks waiting_on_owner (the one rule, _stands). live_only=False reaches a row the queue hides."""
        q = f"SELECT rv.* {_REVIEW_FROM} WHERE rv.TaskId=? AND rv.Status='pending'"
        if kind:      q += ' AND rv.Kind=?'
        else:         q += " AND rv.Kind<>'slot'"             # a task's emails (slots.py) are never its reply
        if live_only: q += f' AND {_NOT_ORPHAN} AND {_VISIBLE_PENDING}'
        return self._one(q + ' ORDER BY rv.ReviewId DESC LIMIT 1', (task_id, kind) if kind else (task_id,))
    def waiting_on_owner(self, task_id, kinds=()):
        """WHAT WAITS ON HIS PRESS ON THIS TASK - the newest card that stands (_stands: never one held behind another, never one the thread
        moved past): a reply draft, one of its emails (slots.py), a proposal. `kinds` narrows it (('draft', 'draft_reply'): the reply).
        Every surface that shows or lights a card asks this - the pill, the rail, the desk's lit Send, the phone, the Assistant - so none of
        them names a card another one holds back (the audit, 2026-11-19: the desk lit Send on a reply the queue held)."""
        rows = self._rows(f"SELECT rv.* {_REVIEW_FROM} WHERE rv.TaskId=? AND rv.Status='pending' AND {_NOT_ORPHAN} AND {_VISIBLE_PENDING} "
                          "ORDER BY rv.ReviewId DESC", (task_id,))
        return next(iter(self._stands([r for r in rows if not kinds or r['Kind'] in kinds])), None)
    def sent_reply(self, message_id=None, task_id=None):
        """The newest reply that actually passed the send gate for this message/task.

        A successful review is the durable receipt for replies sent by Taskuary. Those replies
        are not necessarily ingested back from the external channel before the Assistant's next
        check, so message history alone can briefly (and falsely) look unanswered.
        """
        return next(iter(self.sent_replies(message_id=message_id, task_id=task_id, limit=1)), None)
    def sent_replies(self, message_id=None, task_id=None, conversation_id=None, limit=50) -> list:
        "sent_reply's receipts, newest first - for a message, a task, or every task on a conversation (by the mail each answers)."
        where, values = ["(rv.DeliveryState='sent' OR (rv.DeliveryState IS NULL AND rv.Status IN ('approved','edited','sent')))", "rv.Kind<>'action'", "rv.Kind<>'slot'",
                         "COALESCE(NULLIF(rv.FinalText,''), rv.DraftText, '')<>''"], []
        if message_id is not None: where.append('rv.MessageId=?'); values.append(message_id)
        elif task_id is not None: where.append('rv.TaskId=?'); values.append(task_id)
        elif conversation_id: where.append('m.ConversationId=?'); values.append(conversation_id)
        else: return []
        return self._rows('SELECT rv.* FROM review rv LEFT JOIN message m ON m.MessageId=COALESCE(rv.AnswersMid, rv.MessageId) WHERE ' + ' AND '.join(where)
                          + ' ORDER BY IFNULL(rv.DecidedAt, rv.CreatedAt) DESC, rv.ReviewId DESC LIMIT ?', (*values, limit))
    def hold_reviews(self, task_id, reason=None):
        """Park this task's pending reply drafts while an agent works it. A draft written from the
        mail alone promises what the session has not found yet - and it sat on the task as if it
        were ready to send. Held leaves the queue; the wrap-up brings it back, rewritten."""
        with self.lock:
            cur = self.cx.execute("UPDATE review SET Status='held', Reason=COALESCE(?, Reason) "
                                  "WHERE TaskId=? AND Status='pending' AND Kind IN ('draft','draft_reply') "
                                  "AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'') NOT IN ('sending','unknown','sent')",
                                  (reason, task_id))
            self.cx.commit()
            self._writes += 1
            changed = cur.rowcount                 # lastrowid is meaningless on an UPDATE
        if changed: self._poke('feed-changed', 'task-changed', task_id=task_id)
        return changed
    def held_review(self, task_id, mid=None):
        q = "SELECT * FROM review WHERE TaskId=? AND Status='held'" + (' AND MessageId=?' if mid else '') + ' ORDER BY ReviewId DESC LIMIT 1'
        return self._one(q, (task_id, mid) if mid else (task_id,))
    def unhold_review(self, rid, reason=None):
        self._exec("UPDATE review SET Status='pending', Reason=COALESCE(?, Reason) WHERE ReviewId=? AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'') NOT IN ('sending','sent')", (reason, rid))
        self._review_changed(rid)
    def update_review_reason(self, rid, reason, run_id=None):
        self._exec('UPDATE review SET Reason=?, RunId=COALESCE(?, RunId) WHERE ReviewId=?', (reason, run_id, rid))
        self._review_changed(rid)
    def update_review_draft(self, rid, draft, run_id, by=None, files=...):
        """`files`: the names the writer said ride with this draft ([] = a file promised, unnamed; None = it promised none). Left out,
        the same text keeps what its writer said and new text from anyone else drops it - a word about other words is no word on these.
        AN EMPTY DRAFT IS NO DRAFT: nothing (or only blanks) never replaces the text there - the review keeps it and says the draft came back
        empty (DraftError), so the card says so instead of a blank box under Send (2026-11-04). False when refused."""
        if not str(draft or '').strip():
            self.set_review_draft_error(rid, EMPTY_DRAFT)
            return False
        if his_words(self.get_review(rid)): return False     # HIS WORDS ARE IN ITS BOX: no draft is written over them
        fp = None if files in (None, ...) else json.dumps({'named': [str(f) for f in files]})
        self._exec("UPDATE review SET FilesPromised=CASE WHEN ? THEN ? WHEN DraftText IS ? THEN FilesPromised END, DraftText=?, RunId=?, DraftError=NULL, DraftNeeds=NULL, NotNeeded=NULL, Versions=NULL, "
                   f"DraftBy=?, {_DRAFT_AT} WHERE ReviewId=? AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'') NOT IN ('sending','unknown','sent')",
                   (files is not ..., fp, draft, draft, run_id, by, draft, _now(), rid))
        self._review_changed(rid)
        return True
    def add_review_instruction(self, rid, text: str):
        """Keep the owner's instruction for this draft beside the ones before it - never replaced, never cleared by a redraft."""
        said = ' '.join(str(text or '').split())[:1000]
        if not said: return
        with self.lock:
            r = self.cx.execute('SELECT Instructions FROM review WHERE ReviewId=?', (rid,)).fetchone()
            if not r: return
            try: have = json.loads(r[0] or '[]') or []
            except ValueError: have = []
            # ...once: a reply opened with words (open_reply's later) hands the same words to the draft it owes (/draft)
            if have and have[-1].get('text') == said: return
            have.append({'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'text': said})
            self.cx.execute('UPDATE review SET Instructions=? WHERE ReviewId=?', (json.dumps(have), rid)); self.cx.commit(); self._writes += 1
    def set_review_draft_error(self, rid, error: str):
        """The draft could not be written: keep the review pending and say why (PW-046)."""
        self._exec('UPDATE review SET DraftError=?, DraftNeeds=NULL WHERE ReviewId=?', (by_sentence(error) or None, rid))
        # ...and WHEN, as an act on its task: the error had no time, so the Advisor read it as the newest failure whatever failed after
        # it - Send to agent failed with its error on the card, and the line still said the reply could not be drafted (the matrix,
        # 2026-10-20). rulebook.failure reads the draft's error only while nothing newer failed.
        rv = self.get_review(rid) or {}
        if error and rv.get('TaskId'):
            self.add_operation({'OpId': uuid.uuid4().hex[:12], 'Kind': 'message.reply', 'TargetKind': 'task', 'TargetId': int(rv['TaskId']), 'ParamsJson': '{}',
                                'Version': 1, 'Status': 'error', 'Error': by_sentence(error),
                                'OutcomeJson': json.dumps({'what': 'the reply could not be drafted', 'source': 'draft'})})
        self._review_changed(rid)
    def set_review_draft_needs(self, rid, why: str):
        """The writer would not draft it - it said what it NEEDS (responder.NotDrafted). No draft, and no failure either: the work goes
        to an agent (Send to agent / Continue), and the reason is the owner's to read whole. It was kept as a DraftError, so the card
        showed a red app failure cut mid-word and the Advisor lit "New task to fix this" (walk 2026-10-29)."""
        self._exec('UPDATE review SET DraftNeeds=?, DraftError=NULL WHERE ReviewId=?', (by_sentence(why, 2000) or None, rid))
        self._review_changed(rid)
    def review_envelope(self, rid) -> dict:
        try: d = json.loads((self.get_review(rid) or {}).get('Deliver') or '{}') or {}
        except (TypeError, ValueError): d = {}
        return d if d.get('kind') == 'reply' else {}
    def set_review_envelope(self, rid, env: dict):
        """The recipients this draft will go to, kept with it so approval sends exactly what was reviewed (PW-064).
        An outbound review's own delivery envelope is never overwritten."""
        cur = (self.get_review(rid) or {}).get('Deliver')
        try: existing = json.loads(cur or '{}') or {}
        except (TypeError, ValueError): existing = {}
        if existing and existing.get('kind') != 'reply': return False
        return self.set_review_deliver(rid, json.dumps(env))
    def pin_review_context(self, rid, mid, revision: str):
        """The exact inbound message and message-set revision this draft answered - captured BEFORE the
        model ran, so a line landing during generation is not called seen (PW-048)."""
        self._exec("UPDATE review SET MessageId=?, ContextRevision=?, Stale=0 WHERE ReviewId=? AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'') NOT IN ('sending','unknown','sent')", (mid, revision, rid))
        self._review_changed(rid)
    def mark_review_stale(self, rid, on: bool = True):
        self._exec('UPDATE review SET Stale=? WHERE ReviewId=?', (1 if on else 0, rid))
        self._review_changed(rid)
    def update_review_message(self, rid, mid):
        """Pin a reply draft to the newest inbound message it was written against.

        MessageId is more than the eventual delivery target for chat.  It is also the durable
        freshness marker: if another line lands on the task after this one, approval can see that
        the draft predates the conversation and refuse to send it unchanged.
        """
        self._exec("UPDATE review SET MessageId=? WHERE ReviewId=? AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'') NOT IN ('sending','unknown','sent')", (mid, rid))
        self._review_changed(rid)
    def set_review_answers(self, rid, mid):
        """The mail this draft answers; MessageId stays the freshness marker (update_review_message)."""
        self._exec("UPDATE review SET AnswersMid=? WHERE ReviewId=? AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'') NOT IN ('sending','unknown','sent')", (mid, rid))
        self._review_changed(rid)
    def set_review_why(self, rid, why):
        self._exec("UPDATE review SET DraftWhy=? WHERE ReviewId=? AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'') NOT IN ('sending','unknown','sent')", (by_sentence(why, 400) or None, rid))
        self._review_changed(rid)
    def set_review_not_needed(self, rid, why):
        self._exec("UPDATE review SET NotNeeded=? WHERE ReviewId=? AND Status='pending'", (by_sentence(why, 300) or None, rid))
        self._review_changed(rid)
    def set_review_versions(self, rid, versions: list):
        "The versions of review `rid`'s words its agent gave for him to pick from (agenttools._many) - the first stands in its box; None for none."
        if versions and his_words(self.get_review(rid)): return     # ...nor are versions set over his own words
        self._exec('UPDATE review SET DraftText=?, Versions=? WHERE ReviewId=?', (versions[0], json.dumps(versions), rid)) if versions else \
            self._exec('UPDATE review SET Versions=NULL WHERE ReviewId=?', (rid,))
        self._review_changed(rid)
    def set_review_next_step(self, rid, then):
        "The agent's own step after his press on review `rid` (card.raising), None for none."
        self._exec('UPDATE review SET NextStep=? WHERE ReviewId=?', (then or None, rid))
    def review_act_failed(self, rid, error, by, retry: bool = False):
        """An act's press that failed: kept on the review, which still waits - with who pressed and when, as a failed send keeps them
        (finish_review_delivery). `retry`: its card offers Try again (ActRetry 1) - once: tried again it is 2, and the try that fails too is over."""
        self._exec("UPDATE review SET ActError=?, DecidedBy=?, DecidedAt=?, ActRetry=CASE WHEN ? THEN 1 ELSE ActRetry END WHERE ReviewId=? AND Status IN ('pending','held','superseded')",
                   (str(error or '')[:300] or None, by, _now(), bool(retry), rid))
        self._review_changed(rid)
    def review_try_again(self, rid) -> bool:
        "His Try again on an act whose press failed (proposals.retryable): it waits again as it stood, its one second try spent."
        with self.lock:
            cur = self.cx.execute("UPDATE review SET Status='pending', ActRetry=2, FinalText=NULL, DecideNote=NULL WHERE ReviewId=? AND Status='superseded' AND ActRetry=1", (rid,))
            self.cx.commit(); self._writes += 1
        if cur.rowcount: self._review_changed(rid)
        return bool(cur.rowcount)
    def hold_review_edit(self, rid, edit) -> bool:
        """WHAT HE TYPED INTO A WAITING CARD IS HIS, FROM THE KEYSTROKE (the owner, 2026-11-26: no edit of his is ever written over):
        `edit` is the card as he has left it and not pressed yet - {text, cc, bcc, subject, vals, words, answers}, only what he changed; None or
        nothing in it takes it back. Kept on the review while it waits: no draft is written over it (update_review_draft), and a press that
        carries no words of its own sends these (verdicts._decide). False when the card no longer waits."""
        e = {k: v for k, v in (edit or {}).items() if k in EDIT_PARTS and v is not None}
        with self.lock:
            cur = self.cx.execute("UPDATE review SET OwnerEdit=? WHERE ReviewId=? AND Status IN ('pending','held')", (json.dumps(e) if e else None, rid))
            self.cx.commit(); self._writes += 1
        if cur.rowcount: self._review_changed(rid)
        return bool(cur.rowcount)
    def his_words_back(self, rid):
        "His own ask for other words (Redraft, a rewrite he asked for) takes the ones he typed back: the draft written for it stands in the box."
        if his_words(rv := self.get_review(rid)): self.hold_review_edit(rid, {**his_edit(rv), 'text': None})
    def review_result(self, rid, final) -> bool:
        "What came of an act already pressed (cardqueue.done): its FinalText, its status as it was."
        with self.lock:
            cur = self.cx.execute("UPDATE review SET FinalText=? WHERE ReviewId=? AND Kind='action' AND Status IN ('approved','edited')", (final, rid))
            self.cx.commit(); self._writes += 1
        if cur.rowcount: self._review_changed(rid)
        return bool(cur.rowcount)
    def review_unhanded(self, rid, status, error, note) -> bool:
        "An act his press handed to its agent that ends undone (cardqueue.keep, verdicts.withdraw): `status` with why - his press and its time kept."
        with self.lock:
            cur = self.cx.execute("UPDATE review SET Status=?, ActError=?, DecideNote=? WHERE ReviewId=? AND Kind='action' AND Status IN ('approved','edited')",
                                  (status, error, note, rid))
            self.cx.commit(); self._writes += 1
        if cur.rowcount: self._review_changed(rid)
        return bool(cur.rowcount)
    def review_overcome(self, rid, final, note) -> bool:
        "An act's press that failed, done since by a later step (browsergate.overcome): settled as done, with what came of it - its error gone."
        with self.lock:
            cur = self.cx.execute("UPDATE review SET Status='approved', FinalText=?, ActError=NULL, DecideNote=? WHERE ReviewId=? AND Kind='action' "
                                  "AND Status IN ('pending','held','superseded')", (final, note, rid))
            self.cx.commit(); self._writes += 1
        if cur.rowcount: self._review_changed(rid)
        return bool(cur.rowcount)
    def set_review_sid(self, rid, sid):
        self._exec('UPDATE review SET DraftSid=? WHERE ReviewId=?', (sid, rid)); self._review_changed(rid)
    def save_review_draft(self, rid, draft):
        """Persist the owner's editor without erasing which agent run originally produced it."""
        self._exec(f"UPDATE review SET DraftText=?, {_DRAFT_AT} WHERE ReviewId=? AND DeliveryClaim IS NULL AND IFNULL(DeliveryState,'') NOT IN ('sending','unknown','sent')", (draft, draft, _now(), rid))
        self._review_changed(rid)

    # policies / sources / settings / memory / docs
    def delete_policy(self, pid): self._exec('DELETE FROM policy WHERE PolicyId=?', (pid,))
    def list_policies(self, active_only=True):
        return self._rows('SELECT * FROM policy' + (' WHERE Active=1' if active_only else '') + ' ORDER BY SortOrder')
    def save_policy(self, fields, actor):
        pid = fields.get('PolicyId')
        cols = [c for c in POLICY_COLS if c in fields and fields[c] is not None]
        if pid:
            self._exec(f"UPDATE policy SET {','.join(f'{c}=?' for c in cols)} WHERE PolicyId=?", [fields[c] for c in cols] + [pid])
            return pid
        return self._insert('policy', fields, POLICY_COLS, {'CreatedBy': actor})
    # ── the agent wall (blackboard.py) ──────────────────────────────────────────────────
    def add_note(self, fields) -> int:
        return self._insert('boardnote', {**fields, 'CreatedAt': _now()},
                            ('TaskId', 'Agent', 'Cwd', 'Kind', 'Body', 'Files', 'CreatedAt', 'ReadBy', 'Sid'))
    def roll_notes(self, ids: list, day: str) -> int:
        """Mark these as composted into a summary. Nothing is deleted - the Board can still show
        the whole wall, and an agent that wants the detail can still read it."""
        if not ids: return 0
        marks = ','.join('?' * len(ids))
        self._exec(f'UPDATE boardnote SET Rolled=? WHERE NoteId IN ({marks})', [day] + list(ids))
        return len(ids)

    def notes(self, cwd: str = None, limit: int = 60, house: bool = True, rolled: bool = False) -> list:
        """Newest first.

        Given a checkout: that checkout's wall, plus the HOUSE lane - notes written with no
        checkout at all, by the assistant chat and by the owner. A peer in another repo is none
        of this agent's business; "do not touch the Intacct credentials today" is everybody's.
        Given none: everything, which is what the Board shows."""
        live = '' if rolled else ' AND Rolled IS NULL'
        if not cwd:
            return self._rows(f'SELECT * FROM boardnote WHERE 1=1{live} ORDER BY NoteId DESC LIMIT ?', (int(limit),))
        if not house:
            return self._rows(f'SELECT * FROM boardnote WHERE Cwd=?{live} ORDER BY NoteId DESC LIMIT ?', (cwd, int(limit)))
        return self._rows(f"SELECT * FROM boardnote WHERE (Cwd=? OR IFNULL(Cwd,'')=''){live} "
                          'ORDER BY NoteId DESC LIMIT ?', (cwd, int(limit)))
    def mark_note_read(self, note_id: int, who: str):
        """Who has actually read it - the Board shows an unread note differently, and an agent
        that says it read the wall can be taken at its word."""
        row = self.get_note(note_id)
        if not row: return
        seen = [w for w in str(row.get('ReadBy') or '').split(',') if w]
        if who in seen: return
        self._exec('UPDATE boardnote SET ReadBy=? WHERE NoteId=?', (','.join(seen + [who]), note_id))
    def get_note(self, note_id: int): return self._one('SELECT * FROM boardnote WHERE NoteId=?', (note_id,))
    # ── notes between agents (peers.py) ──
    def add_peer_note(self, frm, to, scope: str, repo: str, body: str) -> int:
        return self._insert('peernote', {'FromTask': frm, 'ToTask': to, 'Scope': scope, 'Repo': repo or '', 'Body': body, 'CreatedAt': _now()},
                            ('FromTask', 'ToTask', 'Scope', 'Repo', 'Body', 'CreatedAt'))
    def peer_notes(self, to: int, unread: bool = True) -> list:
        return self._rows('SELECT * FROM peernote WHERE ToTask=?' + (' AND ReadAt IS NULL' if unread else '') + ' ORDER BY PeerNoteId', (int(to),))
    def peer_notes_read(self, ids: list) -> int:
        if not ids: return 0
        self._exec(f"UPDATE peernote SET ReadAt=? WHERE PeerNoteId IN ({','.join('?' * len(ids))})", [_now(), *ids])
        return len(ids)
    def tasks_with_peer_notes(self) -> list:
        return [r['ToTask'] for r in self._rows('SELECT DISTINCT ToTask FROM peernote WHERE ReadAt IS NULL')]
    # ── agent channels (agentchannels.py) and the owner's standing permission answers (permissions.py) ──
    def agent_channels(self) -> list: return self._rows('SELECT * FROM agentchannel ORDER BY ChannelId')
    def agent_channel(self, cid: int): return self._one('SELECT * FROM agentchannel WHERE ChannelId=?', (int(cid),))
    def add_agent_channel(self, f: dict) -> int:
        return self._insert('agentchannel', {**f, 'CreatedAt': _now()}, ('Kind', 'Chat', 'ConnectorId', 'TaskId', 'Repo', 'MembersJson', 'StateJson', 'CreatedAt'))
    def set_agent_channel(self, cid: int, **f):
        ok = [k for k in f if k in ('MembersJson', 'StateJson', 'Repo', 'TaskId')]
        if ok: self._exec(f"UPDATE agentchannel SET {', '.join(k + '=?' for k in ok)} WHERE ChannelId=?", [f[k] for k in ok] + [int(cid)])
    def delete_agent_channel(self, cid: int):
        self._exec('DELETE FROM agentchannel WHERE ChannelId=?', (int(cid),))
    def agent_channel_log(self, cid: int, ext: str, dir_: str, who: str = '', role: str = '', tid=None, text: str = '') -> bool:
        "One line in or out; False when that provider id was already kept (a re-read, or our own post read back)."
        with self.lock, self._undone():
            cur = self.cx.execute('INSERT OR IGNORE INTO agentchannel_msg (ChannelId, ExtId, Dir, Who, Role, TaskId, Text, At) VALUES (?,?,?,?,?,?,?,?)',
                                  (int(cid), str(ext), dir_, who, role, tid, text, _now()))
            self.cx.commit(); self._writes += 1
            return cur.rowcount > 0
    def agent_channel_msgs(self, cid: int, n: int = 50) -> list:
        return self._rows('SELECT * FROM agentchannel_msg WHERE ChannelId=? ORDER BY Id DESC LIMIT ?', (int(cid), int(n)))[::-1]
    def perm_rule(self, tid: int, pattern: str):
        r = self._one('SELECT Answer FROM permrule WHERE TaskId=? AND Pattern=?', (int(tid), str(pattern)))
        return r['Answer'] if r else None
    def set_perm_rule(self, tid: int, pattern: str, answer: str):
        self._exec('INSERT OR REPLACE INTO permrule (TaskId, Pattern, Answer, CreatedAt) VALUES (?,?,?,?)', (int(tid), str(pattern), answer, _now()))
    def perm_rules(self, tid: int) -> list: return self._rows('SELECT * FROM permrule WHERE TaskId=? ORDER BY RuleId', (int(tid),))

    def list_sources(self, active_only=True):
        return self._rows('SELECT * FROM source' + (' WHERE Active=1' if active_only else ''))
    def save_source(self, fields, actor):
        sid = fields.get('SourceId')
        # a report is saved as its route card, whoever writes it (the page, the Assistant, a test) -
        # the old reach/triage words never land again (reports.from_old_rules)
        if fields.get('ConfigJson') and (fields.get('Channel') or (self.get_source(sid) or {}).get('Channel') if sid else fields.get('Channel')) == 'report':
            from .reports import as_card
            try: fields = {**fields, 'ConfigJson': json.dumps(as_card(json.loads(fields['ConfigJson'])))}
            except ValueError: pass
        cols = [c for c in SOURCE_COLS if c in fields and fields[c] is not None]
        if sid:
            self._exec(f"UPDATE source SET {','.join(f'{c}=?' for c in cols)} WHERE SourceId=?", [fields[c] for c in cols] + [sid])
            return sid
        return self._insert('source', fields, SOURCE_COLS)
    def touch_source(self, sid):
        self._touch('UPDATE source SET LastPolledAt=? WHERE SourceId=?', (_now(), sid))
        self._processing_ignored_writes += 1
    # A HEARTBEAT NEVER WAITS ON THE DATABASE (2026-11-09). A poll's "polled at" stamp waited out SQLite's whole 5 s busy timeout while another
    # process wrote - holding store.lock all the while: the WhatsApp poll held it 6 s at a time, every press and read in the app behind it.
    # The stamp is written when the database is free within TOUCH_WAIT_MS, else skipped: the next poll stamps it (and reads a little again).
    TOUCH_WAIT_MS = 200
    def _touch(self, q, p=()):
        with self.lock:
            self.cx.execute(f'PRAGMA busy_timeout={self.TOUCH_WAIT_MS}')
            try: return self._exec(q, p)
            except sqlite3.OperationalError as e:
                if 'locked' not in str(e) and 'busy' not in str(e): raise
                logger.debug(f'store: a heartbeat stamp skipped - the database is busy ({e})'); return None
            finally: self.cx.execute('PRAGMA busy_timeout=5000')
    def patch_source_poll_state(self, source_id, *, config_set=None, config_remove=(),
                                last_polled_at=_POLL_UNSET, expect_fields=None, expect_config=None):
        """Atomically checkpoint source progress; False means the captured source changed."""
        return self._patch_poll_state('source', source_id, config_set=config_set,
                                     config_remove=config_remove, last_polled_at=last_polled_at,
                                     expect_fields=expect_fields, expect_config=expect_config)
    def rewind_source(self, sid):
        """Forget this source's watermark, so the next poll reaches back over history instead
        of only forward. What a source that was OFF needs the moment it is switched on: the
        watermark kept marching while nothing was being read, and without this the items
        that existed before the switch are invisible forever."""
        self._exec('UPDATE source SET LastPolledAt=NULL WHERE SourceId=?', (sid,))
    def get_source(self, sid): return self._one('SELECT * FROM source WHERE SourceId=?', (sid,))
    def delete_source(self, sid): self._exec('DELETE FROM source WHERE SourceId=?', (sid,))
    def save_dashboard_result(self, sid, data_json):
        self._exec('INSERT OR REPLACE INTO dashboard_result (SourceId, At, DataJson) VALUES (?,?,?)', (sid, _now(), data_json))
    def get_dashboard_result(self, sid): return self._one('SELECT * FROM dashboard_result WHERE SourceId=?', (sid,))
    def delete_agent(self, name): self._exec('DELETE FROM agent WHERE Name=?', (name,))
    # RECENTLY DELETED (recentlydeleted.py): what a Remove took, kept whole so Restore and Undo put it back as it was
    def keep_deleted(self, kind, title, data, at, until) -> int:
        return self._exec('INSERT INTO deleted (Kind, Title, DataJson, DeletedAt, KeepUntil) VALUES (?,?,?,?,?)',
                          (kind, title, json.dumps(data, default=str), at, until))
    def deleted_rows(self): return self._rows('SELECT * FROM deleted ORDER BY DeletedAt DESC, DeletedId DESC')
    def get_deleted(self, did): return self._one('SELECT * FROM deleted WHERE DeletedId=?', (did,))
    def drop_deleted(self, did): self._exec('DELETE FROM deleted WHERE DeletedId=?', (did,))
    def put_back(self, table, row, key):
        """A row Recently deleted kept, inserted again as it was - under its old id while nothing has taken it."""
        cols = {r['name'] for r in self._rows(f'PRAGMA table_info({table})')}
        d = {k: v for k, v in (row or {}).items() if k in cols}
        if d.get(key) is not None and self._one(f'SELECT 1 FROM {table} WHERE {key}=?', (d[key],)): d.pop(key)
        rid = self._exec(f"INSERT INTO {table} ({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
        return d.get(key) or rid

    # Monthly invoice workflow. These methods deliberately expose dicts like the rest of the
    # store; Zoho-specific decisions stay in invoice_workflow.py.
    def invoice_batch(self, batch_id):
        return self._one('SELECT * FROM invoice_batch WHERE BatchId=?', (batch_id,))
    def invoice_batch_for(self, source_id, period):
        return self._one('SELECT * FROM invoice_batch WHERE SourceId=? AND Period=?', (source_id, period))
    def list_invoice_batches(self, source_id, limit=24):
        return self._rows('SELECT * FROM invoice_batch WHERE SourceId=? ORDER BY Period DESC, BatchId DESC LIMIT ?',
                          (source_id, int(limit)))
    def create_invoice_batch(self, source_id, period):
        found = self.invoice_batch_for(source_id, period)
        if found: return found['BatchId']
        try:
            return self._insert('invoice_batch', {'SourceId': source_id, 'Period': period,
                                'Status': 'needs_amounts', 'CreatedAt': _now(), 'UpdatedAt': _now()},
                                ('SourceId', 'Period', 'Status', 'CreatedAt', 'UpdatedAt'))
        except sqlite3.IntegrityError:   # another scheduler thread won the same unique key
            return self.invoice_batch_for(source_id, period)['BatchId']
    def invoice_items(self, batch_id):
        return self._rows('SELECT * FROM invoice_item WHERE BatchId=? ORDER BY CustomerName, ItemId', (batch_id,))
    def invoice_item(self, item_id): return self._one('SELECT * FROM invoice_item WHERE ItemId=?', (item_id,))
    def add_invoice_item(self, fields):
        cols = ('BatchId','ConnectorId','CustomerId','CustomerName','Recipient','Currency','PreviousAmount',
                'Amount','Description','Status','Reference','TemplateInvoiceId','InvoiceId','InvoiceNumber','ReviewId','Subject',
                'Body','Error','CreatedAt','UpdatedAt')
        body = {**fields, 'CreatedAt': fields.get('CreatedAt') or _now(), 'UpdatedAt': _now()}
        try: return self._insert('invoice_item', body, cols)
        except sqlite3.IntegrityError:
            row = self._one('SELECT ItemId FROM invoice_item WHERE BatchId=? AND CustomerId=?',
                            (fields['BatchId'], fields['CustomerId']))
            return row['ItemId']
    def update_invoice_item(self, item_id, fields):
        allowed = {'Recipient','Currency','PreviousAmount','Amount','Description','Status','Reference',
                   'TemplateInvoiceId','InvoiceId','InvoiceNumber','ReviewId','Subject','Body','Error'}
        cols = [k for k in fields if k in allowed]
        if cols:
            self._exec(f"UPDATE invoice_item SET {','.join(f'{k}=?' for k in cols)}, UpdatedAt=? WHERE ItemId=?",
                       [fields[k] for k in cols] + [_now(), item_id])
        return self.invoice_item(item_id)
    def update_invoice_batch(self, batch_id, fields):
        cols = [k for k in fields if k in {'Status','MessageId'}]
        if cols:
            self._exec(f"UPDATE invoice_batch SET {','.join(f'{k}=?' for k in cols)}, UpdatedAt=? WHERE BatchId=?",
                       [fields[k] for k in cols] + [_now(), batch_id])
        return self.invoice_batch(batch_id)
    def invoice_item_by_review(self, review_id):
        return self._one('SELECT * FROM invoice_item WHERE ReviewId=?', (review_id,))
    def last_sent_invoice_item(self, source_id, customer_id, before_period):
        return self._one('''SELECT i.*, b.Period FROM invoice_item i JOIN invoice_batch b ON b.BatchId=i.BatchId
                            WHERE b.SourceId=? AND i.CustomerId=? AND b.Period<? AND i.Status='sent'
                            ORDER BY b.Period DESC, i.ItemId DESC LIMIT 1''',
                         (source_id, customer_id, before_period))

    # channel connectors (secrets are write-only: list/get never return them)
    _CONN_SAFE = "ConnectorId, Type, Name, ConfigJson, Active, Roles, Scope, Workstream, LastSyncAt, LastError, LastErrorAt, (Secret IS NOT NULL AND Secret != '') HasSecret"
    def list_connectors(self):
        """Every card, secrets left out. ASKED A DOZEN TIMES A PAGE READ (the owner's restart, 2026-11-16: /api/setup, the first run, the
        agents and the rail each asked it again, ~340 cards each time): kept until a connector is written - change_gen's trigger counts every
        write, from any process - and read with that count in one snapshot. A copy each time: callers edit what they get."""
        if not self._off_writer(): return [self._shown(r) for r in self._rows(f'SELECT {self._CONN_SAFE} FROM connector ORDER BY ConnectorId')]   # ...its own writes, unread
        with self._snapshot_read() as cur:
            gen = cur.execute("SELECT Gen FROM change_gen WHERE Tbl='connector'").fetchone()
            got = self._conn_cache
            if gen is None: return [self._shown(dict(r)) for r in cur.execute(f'SELECT {self._CONN_SAFE} FROM connector ORDER BY ConnectorId')]
            if got is None or got[0] != gen[0]:
                got = self._conn_cache = (gen[0], [self._shown(dict(r)) for r in cur.execute(f'SELECT {self._CONN_SAFE} FROM connector ORDER BY ConnectorId')])
        return [dict(r) for r in got[1]]
    # A SECRET KEPT IN ConfigJson IS SEALED LIKE THE Secret COLUMN: the fields a card declares secret (connectorcatalog.secret_config -
    # an app's client secret, a refresh token, an authenticator key, a sender password) - a copy of taskuary.db must not carry them in the clear
    @staticmethod
    def _opened(r, keep=None):
        """A with_secret row carries the secret itself: the column holds it sealed (vault.py) - and so do its config's sealed fields, at any
        depth. Every sealed value opens, declared or not: the marker is the app's own, and a field once sealed must stay readable. `keep`:
        top-level keys left sealed - a read without with_secret keeps its card's declared ones shut, and opens what is sealed by shape alone."""
        if r and r.get('Secret') and keep is None: r['Secret'] = vault.unseal(r['Secret'])
        if r and vault.PREFIX in (r.get('ConfigJson') or ''):
            try: cfg = json.loads(r['ConfigJson'])
            except (TypeError, ValueError): return r
            if isinstance(cfg, dict):
                r['ConfigJson'] = json.dumps({k: v if k in (keep or ()) else map_secrets(v, _open_sealed, within=True) for k, v in cfg.items()})
        return r
    def _shown(self, r):
        "A row read without with_secret: what is sealed by its shape alone opens (it was text before), what its card declares stays shut."
        return self._opened(r, secret_keys(r.get('Type'))) if r else r
    def _cfg_sealed(self, cid, cj, typ=None):
        """ConfigJson as stored: its secret fields sealed. A value that opens to what is stored keeps its seal - a card saved
        from a with_secret read would otherwise mint a new keychain entry on every save - and one replaced is forgotten."""
        try: cfg = json.loads(cj) if cj else None
        except (TypeError, ValueError): return cj
        if not isinstance(cfg, dict): return cj
        row = (self._one('SELECT Type, ConfigJson FROM connector WHERE ConnectorId=?', (cid,)) or {}) if cid else {}
        try: old = json.loads(row.get('ConfigJson') or '{}')
        except (TypeError, ValueError): old = {}
        return self._seal_cfg(cfg, old if isinstance(old, dict) else {}, row.get('Type') or typ, cj)
    def _seal_cfg(self, cfg: dict, old: dict, typ, cj=None):
        """`cfg` as stored over `old`, the stored config of a card of type `typ`: each secret in it (connectorcatalog.map_secrets - what the
        card declares and what is one by its shape) sealed, a value already sealed in `old` keeping that seal."""
        was = _sealed_in(old)
        prev = {_open_sealed(v): v for v in was}
        out = map_secrets(cfg, lambda v: v if vault.sealed(v) else prev.get(v) or vault.seal(v), secret_keys(typ))
        for v in was - _sealed_in(out): vault.forget(v)
        return (json.dumps(cfg) if cj is None else cj) if out == cfg else json.dumps(out)
    def get_connector(self, cid, with_secret=False):
        r = self._one(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector WHERE ConnectorId=?", (cid,))
        return self._opened(r) if with_secret else self._shown(r)
    def connectors_by_type(self, ctype, with_secret=False):
        rows = self._rows(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector "
                          'WHERE Type=? ORDER BY Active DESC, ConnectorId', (ctype,))
        return [self._opened(r) if with_secret else self._shown(r) for r in rows]
    def get_connector_by_type(self, ctype, with_secret=False):
        """Compatibility/default lookup for code that needs one connection: prefer an active
        instance, then the original catalog row. Instance-aware paths use ConnectorId."""
        rows = self.connectors_by_type(ctype, with_secret)
        return rows[0] if rows else None
    def save_connector(self, fields, actor):
        if fields.get('Secret'):
            old = (self._one('SELECT Secret FROM connector WHERE ConnectorId=?', (fields['ConnectorId'],)) or {}).get('Secret')                 if fields.get('ConnectorId') else None
            fields = {**fields, 'Secret': vault.seal(fields['Secret'])}
            if old and old != fields['Secret']: vault.forget(old)
        cid = fields.get('ConnectorId')
        if fields.get('ConfigJson'): fields = {**fields, 'ConfigJson': self._cfg_sealed(cid, fields['ConfigJson'], fields.get('Type'))}
        cols = [c for c in ('Type', 'Name', 'ConfigJson', 'Secret', 'Active', 'Roles', 'Scope') if c in fields and fields[c] is not None]
        if cid:
            # nothing to change is not "UPDATE connector SET  WHERE" - a syntax error that failed the chat's Create (2026-10-06)
            if cols: self._exec(f"UPDATE connector SET {','.join(f'{c}=?' for c in cols)} WHERE ConnectorId=?", [fields[c] for c in cols] + [cid])
            return cid
        # A NEW CARD NEVER TAKES A REMOVED ONE'S ID: SQLite gives the highest id again once its row is deleted, and a card added after a
        # Remove got the removed card's id - its sources still named it, and Undo wrote the removed card's sign-in over the new one. The id
        # is past every one a source or a removed card's Undo still names, in the one statement that inserts it.
        d = {k: fields[k] for k in cols}
        return self._exec(f"INSERT INTO connector (ConnectorId, {','.join(d)}) VALUES (1 + MAX("
                          "COALESCE((SELECT MAX(ConnectorId) FROM connector), 0), COALESCE((SELECT MAX(ConnectorId) FROM source), 0), "
                          "COALESCE((SELECT MAX(CAST(json_extract(DataJson, '$.cid') AS INTEGER)) FROM deleted WHERE Kind='connection'), 0)), "
                          f"{','.join('?' * len(d))})", list(d.values()))
    def reset_connector(self, cid):
        """'Remove connection': wipe creds/config/test state, deactivate it and its sources."""
        vault.forget((self._one('SELECT Secret FROM connector WHERE ConnectorId=?', (cid,)) or {}).get('Secret'))
        self._cfg_sealed(cid, '{}')                     # ...and the keychain entries of its sealed config keys
        self._exec('UPDATE connector SET Secret=NULL, ConfigJson=NULL, Active=0, LastSyncAt=NULL, LastError=NULL, Scope=NULL WHERE ConnectorId=?', (cid,))
        self._exec('UPDATE source SET Active=0 WHERE ConnectorId=?', (cid,))
    def set_connector_config(self, cid, cfg: dict):
        """Just the config JSON - how the pollers keep their watermark (Telegram's update
        offset, the WhatsApp bridge's sequence) without touching secrets or roles."""
        self._exec('UPDATE connector SET ConfigJson=? WHERE ConnectorId=?', (self._cfg_sealed(cid, json.dumps(cfg)), cid))
        self._processing_ignored_writes += 1
    # A FIELD SAVES ITSELF, AND ONLY ITSELF (the owner, 2026-11-05: "what saves with one click while other hit the save buttons"; #242).
    # Each control on a card posts the key it changed, and the key is merged into the config as it is NOW - read and written in one
    # transaction - so a poller's watermark written a moment ago (Telegram's offset, the WhatsApp sequence) is never rolled back by an
    # edit made from an older read. A value None removes its key; a key in `keep` sent blank keeps what is stored (a write-only
    # secret the browser never had: guard.keep_write_only). Returns the merged config, or None when the row is gone.
    def merge_config(self, table, row_id, patch: dict, keep=()):
        key = {'source': 'SourceId', 'connector': 'ConnectorId'}[table]
        if not isinstance(patch, dict) or any(not isinstance(k, str) for k in patch): raise TypeError('a config patch is a dict of keys')
        with self.lock:
            self._clear_stale(); self.cx.execute('BEGIN IMMEDIATE')
            try:
                found = self.cx.execute(f"SELECT ConfigJson, {'Type' if table == 'connector' else 'NULL'} FROM {table} WHERE {key}=?", (row_id,)).fetchone()
                if found is None: self.cx.rollback(); return None
                try: cur = json.loads(found[0]) if found[0] else {}
                except (TypeError, ValueError): cur = None
                if not isinstance(cur, dict): raise ValueError('the stored config is not an object - not merged over')
                new = dict(cur)
                for k, v in patch.items():
                    if v is None: new.pop(k, None)
                    elif k in keep and v == '': continue
                    else: new[k] = v
                cj = self._seal_cfg(new, cur, found[1]) if table == 'connector' else json.dumps(new)
                self.cx.execute(f'UPDATE {table} SET ConfigJson=? WHERE {key}=?', (cj, row_id))
                self.cx.commit(); self._writes += 1
                return new
            except BaseException:
                self.cx.rollback(); raise
    def merge_connector_config(self, cid, patch: dict) -> bool:
        """THE KEYS A POLL OR A JOB CHANGED, merged over the config as it is now (merge_config) - never the whole config from its own
        earlier read, which put back whatever the owner's field saved in between (the owner, 2026-11-05: every field saves itself).
        None removes a key. False when the card is gone."""
        merged = self.merge_config('connector', cid, patch) is not None
        self._processing_ignored_writes += 1
        return merged
    def patch_connector_poll_state(self, connector_id, *, config_set=None, config_remove=(),
                                   expect_fields=None, expect_config=None):
        """Atomically merge only poll-owned config keys while checking mailbox identity."""
        return self._patch_poll_state('connector', connector_id, config_set=config_set,
                                     config_remove=config_remove, expect_fields=expect_fields,
                                     expect_config=expect_config)
    TOUCH_EVERY = 30      # seconds: a check-in that changes nothing rewrites the stamp at most this often
    def touch_connector(self, cid, error=None):
        # LastErrorAt is WHEN it failed: LastSyncAt is the last time it worked, and the bell was showing that as the failure's time
        # A check-in that says what the row already says, inside TOUCH_EVERY, changes no row: WhatsApp checks in ~2/s, and
        # every one rewrote it (2026-10-12). The stamps are read as "ok 3m ago", never to the second; a stamp
        # from the future (the clock went back) does not hold the next one off.
        now, since = _now(), (datetime.now() - timedelta(seconds=self.TOUCH_EVERY)).isoformat(sep=' ', timespec='seconds')
        if error: self._exec('''UPDATE connector SET LastError=?, LastErrorAt=? WHERE ConnectorId=?
                                AND NOT (LastError IS ? AND COALESCE(LastErrorAt, '') BETWEEN ? AND ?)''',
                             (error[:500], now, cid, error[:500], since, now))
        else: self._touch('''UPDATE connector SET LastSyncAt=?, LastError=NULL, LastErrorAt=NULL WHERE ConnectorId=?
                            AND NOT (LastError IS NULL AND LastErrorAt IS NULL AND COALESCE(LastSyncAt, '') BETWEEN ? AND ?)''',
                         (now, cid, since, now))
        self._processing_ignored_writes += 1
    @contextlib.contextmanager
    def held_settings(self):
        """ONE READ OF A SETTING FOR A WHOLE BUILD (the owner's restart, 2026-11-16: the rail's ~1,300 cards each asked the owner's address
        and its neighbours again - ~1,000 queries a build, rebuilt after every write of the start's sync): while held, this thread's
        get_setting answers each name from its first read. A build reads one moment; a write it makes itself is read fresh after."""
        was = getattr(_HELD, 'settings', None)
        if was is not None and was[0] is self: yield; return
        _HELD.settings = (self, {})
        try: yield
        finally: _HELD.settings = was
    def get_settings(self):
        return {r['Name']: (BLANK_DEFAULTS[r['Name']] if r['Name'] in BLANK_DEFAULTS and not str(r['Value'] or '').strip() else r['Value'])
                for r in self._rows('SELECT * FROM setting')}
    def get_setting(self, name, default=None):
        """ONE setting, as `get_setting(name, default)` answers it (a stored NULL or '' is returned as stored - except a number
        knob's, which reads back its shipped default: BLANK_DEFAULTS). Reading the whole table to pick one key was ~35% of the
        app's busy time (2026-09-25 profile): the table carries 400 rows, one of them a 35k-character run record."""
        held = getattr(_HELD, 'settings', None)
        if held is not None and held[0] is self:
            if name not in held[1]: held[1][name] = self._one('SELECT Value FROM setting WHERE Name=?', (name,))
            r = held[1][name]
        else: r = self._one('SELECT Value FROM setting WHERE Name=?', (name,))
        if r is None: return default
        return BLANK_DEFAULTS[name] if name in BLANK_DEFAULTS and not str(r['Value'] or '').strip() else r['Value']
    def list_settings(self): return self._rows('SELECT * FROM setting ORDER BY Name')
    def setting_writer(self, name):
        """Who last wrote one setting ('owner', 'migration', ...) - the line between a choice and a default."""
        r = self._one('SELECT UpdatedBy FROM setting WHERE Name=?', (name,))
        return str((r or {}).get('UpdatedBy') or '')
    def set_setting(self, name, value, actor):
        # A write that says what the row already says - the same value from the same writer - changes nothing, so it moves no stamp and
        # empties no cache: a setting rewritten on a loop (a pane's size, a router note) used to throw the whole pile away each time
        # (2026-11-09). str() as SQLite keeps it: a number written as 3 reads back '3' only through the TEXT column's affinity.
        was = self._one('SELECT Value, UpdatedBy FROM setting WHERE Name=?', (name,))
        if was is not None and was['UpdatedBy'] == actor and (was['Value'] == value or (value is not None and was['Value'] == str(value))): return
        self._exec('INSERT INTO setting (Name, Value, UpdatedBy) VALUES (?,?,?) ON CONFLICT(Name) DO UPDATE SET Value=?, UpdatedBy=?',
                   (name, value, actor, value, actor))
        if name == 'ingest_status':
            # This setting is an ephemeral progress clock. It is intentionally absent from every
            # processing projection, so do not make it invalidate otherwise reusable DB work.
            self._processing_ignored_writes += 1
        elif name.startswith(PILE_BLIND_SETTINGS):
            # ...nor are these: the assistant's own bookkeeping, written on every Next press. Emptying the pile for them
            # made the press that wrote one rebuild it cold (2026-10-12).
            self._processing_ignored_writes += 1
        else:
            # Only a setting the projection READS colds the rail (PROCESSING_DIRTY_SETTINGS - and its
            # trigger leaves the dirty row that says so). Every other setting is bookkeeping to the
            # rail: the assistant writes the item on the table (concierge.set_current) and its session
            # id on EVERY press, and dropping the whole rail for those made each press rebuild it cold
            # - 1.4 s of a 1.5 s press, measured on the owner's DB copy (2026-09-17, design B/D).
            if name in PROCESSING_DIRTY_SETTINGS: self._processing_display_cache = {}
            else: self._processing_ignored_writes += 1
            # ...and the Assistant's pile is built from settings too - the mutes, feed_days, the
            # owner's own address. Leaving its cache alone showed a change the owner had just made up
            # to PILE_EVERY seconds later, or not until New chat (2026-09-10 audit).
            try:
                from . import funnel
                funnel.invalidate()
            except Exception: pass
        if name == 'ingest_status':
            try: extra = json.loads(value) if isinstance(value, str) else {}
            except (TypeError, ValueError): extra = {}
            # Progress is a clock/status change, not a new Timeline item. Treating every
            # "reading Outlook" / "triaging" update as feed-changed made each open Assistant
            # rebuild the complete canonical inventory over and over for one sync. Message and
            # task writes already emit their own feed-changed events.
            self._poke('ingest-status', ingest=extra if isinstance(extra, dict) else {})
    def last_report(self, title):
        """The previous filed run of a report, by title - its shape anchors the next run (reports.run_agent).
        Failed runs and outbound copies do not count: a table of refusals is not a structure to keep."""
        return self._one("SELECT * FROM message WHERE Channel='report' AND (SourceName=? OR Subject LIKE ?) "
                         "AND Subject NOT LIKE '%FAILED' AND COALESCE(Direction, '') <> 'out' ORDER BY SentAt DESC LIMIT 1",
                         (title, f'{title} —%'))
    def known_sender(self, email, exclude_mid=None):
        """Has the OWNER dealt with this address? A row from them is not enough - a stranger's own
        first mail, held for the owner, made their second one 'known' and started the agent the hold
        existed to stop (audit 2026-09-02). Known is: the owner's words on one of their threads (a
        'context' row or an outbound one), or a reply to them the owner approved or sent."""
        if not email: return False
        return self._one("""SELECT 1 x FROM message m WHERE LOWER(m.FromEmail)=LOWER(?) AND m.MessageId<>? AND (
                               EXISTS (SELECT 1 FROM message o WHERE o.ConversationId=m.ConversationId AND o.ConversationId IS NOT NULL
                                       AND o.MessageId<>m.MessageId AND (o.Status='context' OR o.Direction='out'))
                            OR EXISTS (SELECT 1 FROM review r WHERE r.MessageId=m.MessageId AND r.Status IN ('approved','edited','sent')))
                            LIMIT 1""", (email, exclude_mid or 0)) is not None
    def add_worker_event(self, fields: dict) -> int:
        return self._insert('worker_event', fields, ('TaskId', 'Sid', 'Kind', 'RequestId', 'Text', 'ChoicesJson', 'Source', 'EventId'), {'CreatedAt': _now()})
    def worker_events(self, task_id: int) -> list: return self._rows('SELECT * FROM worker_event WHERE TaskId=? ORDER BY Id', (task_id,))
    def last_worker_event(self, task_id: int, kinds=None, skip=()):
        """The task's newest worker event - of `kinds` only, none of `skip` - or None. Read newest-first down the task's index, so it
        stops at the first match however long the run's history is (workerstate.ended)."""
        q, args = 'SELECT * FROM worker_event WHERE TaskId=?', [task_id]
        if kinds: q += f" AND Kind IN ({','.join('?' * len(kinds))})"; args += list(kinds)
        if skip: q += f" AND Kind NOT IN ({','.join('?' * len(skip))})"; args += list(skip)
        return self._one(q + ' ORDER BY Id DESC LIMIT 1', tuple(args))
    def worker_event_exists(self, event_id: str) -> bool: return self._one('SELECT 1 x FROM worker_event WHERE EventId=?', (event_id,)) is not None
    def wrote_to_locally(self, mailbox: str, email: str, exclude_mid=None, memo=None) -> bool:
        """Verified SENT evidence this store already holds, scoped to the receiving mailbox: the mailbox's own mail TO them (its To
        or Cc, a 'context' row or an outbound one) - what a card sent is written as it goes (channels.record_sent), so the person he
        just wrote to is no stranger before the Sent folder syncs (walk 14) - or a reply to them the owner approved or sent.
        Incoming rows alone never count (PW-079), and neither does the thread a mail names: a stranger's In-Reply-To citing a thread
        he wrote on put them "on a thread with him" and their next mail started a full agent (the red team, 2026-11-24, T1a).
        `memo`: see _witnessed."""
        if not (email and mailbox): return False
        rj = "CASE WHEN json_valid(o.RecipientsJson) THEN o.RecipientsJson ELSE '{}' END"
        to = lambda ex, n: [r['x'] for r in self._rows(f"""SELECT o.MessageId x FROM message o WHERE o.Channel='email' AND LOWER(o.SourceName)=LOWER(?)
                             AND (o.Status='context' OR o.Direction='out') AND o.MessageId<>? AND EXISTS (SELECT 1 FROM json_each({rj}, '$.to') j
                             WHERE lower(trim(j.value))=LOWER(?) UNION SELECT 1 FROM json_each({rj}, '$.cc') j WHERE lower(trim(j.value))=LOWER(?)) LIMIT ?""",
                                                       (mailbox, ex, email, email, n))]
        return self._witnessed(memo, ('wrote', mailbox.lower(), email.lower()), exclude_mid, lambda ex, n: to(ex, n) or [r['x'] for r in self._rows("""SELECT m.MessageId x FROM message m
                             WHERE m.Channel='email' AND LOWER(m.SourceName)=LOWER(?)
                               AND LOWER(m.FromEmail)=LOWER(?) AND m.MessageId<>?
                               AND EXISTS (SELECT 1 FROM review r WHERE r.MessageId=m.MessageId AND r.Status IN ('approved','edited','sent'))
                             LIMIT ?""", (mailbox, email, ex, n))])
    @staticmethod
    def _witnessed(memo, key, exclude_mid, find):
        """Is there a witness row other than exclude_mid? `find(exclude, n)` lists up to n witnesses. With a `memo` (one dict across a
        task's messages, origin.of_task) a person is asked ONCE: up to two witnesses, excluding none - one of them is not this row
        exactly when the question asked for this row alone would find one. Judging a 1,500-line group chat asked it once a line, and a
        big task's page waited on that before it drew (the owner, 2026-11-01: "this still happens")."""
        if memo is None: return bool(find(exclude_mid or 0, 1))
        if key not in memo: memo[key] = find(0, 2)
        return any(w != exclude_mid for w in memo[key])
    def talked_with(self, channel: str, who: str, exclude_mid=None, aliases=(), conversation=None, memo=None):
        """How the owner has talked with `who` in this chat channel, or None. 'dm': a conversation the PLATFORM called
        one-to-one (the poller's {'dm': true} on their line - who has spoken proves nothing, a group's one talker looks
        alone), with the owner's own line AFTER one of theirs (other than exclude_mid), and nobody else's. 'answered':
        in any conversation, a group too, the owner's own line came next after one of theirs with nobody else between -
        the owner answering THEM, not a room the owner happens to be in (2026-10-20: weeks of replies in a group chat
        still read "someone you haven't worked with"). `who` is senders.chat_key's key - their address or platform id,
        else their name; `aliases` the same person's other ids (WhatsApp's phone and LID forms), matched against a
        row's key and its MailMetaJson alias alike. `conversation` keeps the search to that one conversation (senders._chat_known's
        name-keyed Teams history). `memo`: see _witnessed."""
        keys = sorted({str(x).strip().lower() for x in (who, *aliases) if str(x or '').strip()})
        if not (channel and keys): return None
        k = "LOWER(TRIM(COALESCE(NULLIF(TRIM({0}.FromEmail),''), NULLIF(TRIM({0}.FromName),''), '')))"
        qs = ','.join('?' * len(keys))
        them = (f"({k} IN ({qs}) OR LOWER(COALESCE(CASE WHEN json_valid({{0}}.MailMetaJson) "
                f"THEN json_extract({{0}}.MailMetaJson, '$.alias') END, '')) IN ({qs}))")
        # code sets these; a sender who calls themselves 'You' is not the owner (ingest.is_ours reads names, this must not)
        mine = "(COALESCE({0}.Status,'')='context' OR COALESCE({0}.Direction,'')='out')"
        head = f"""SELECT m.MessageId x FROM message m WHERE m.Channel=? AND m.ConversationId IS NOT NULL AND m.MessageId<>?
                   AND NOT {mine.format('m')} AND {them.format('m')}""" + (' AND m.ConversationId=?' if conversation else '')
        args = lambda ex, n: (channel, ex, *keys, *keys, *((conversation,) if conversation else ()), *keys, *keys, n)
        ask = lambda sql: lambda ex, n: [r['x'] for r in self._rows(sql, args(ex, n))]
        key = (channel, tuple(keys), conversation)
        if self._witnessed(memo, ('dm', *key), exclude_mid, ask(f"""{head} AND (CASE WHEN json_valid(m.MailMetaJson) THEN json_extract(m.MailMetaJson, '$.dm') END)=1
                         AND EXISTS (SELECT 1 FROM message o WHERE o.Channel=m.Channel AND o.ConversationId=m.ConversationId
                                     AND o.MessageId>m.MessageId AND {mine.format('o')})
                         AND NOT EXISTS (SELECT 1 FROM message x WHERE x.Channel=m.Channel AND x.ConversationId=m.ConversationId
                                         AND NOT {mine.format('x')} AND NOT {them.format('x')})
                       LIMIT ?""")): return 'dm'
        # ...the owner's FIRST line after theirs is the only one to look at: anyone between it and theirs is between every later one
        # and theirs too. Every pair of lines was tried, each against the lines between: one person in a 1,500-line group took minutes
        first = f"""(SELECT MIN(f.MessageId) FROM message f WHERE f.Channel=m.Channel AND f.ConversationId=m.ConversationId
                     AND f.MessageId>m.MessageId AND {mine.format('f')})"""
        if self._witnessed(memo, ('answered', *key), exclude_mid, ask(f"""{head} AND {first} IS NOT NULL
                         AND NOT EXISTS (SELECT 1 FROM message x WHERE x.Channel=m.Channel AND x.ConversationId=m.ConversationId
                                         AND x.MessageId>m.MessageId AND x.MessageId<{first}
                                         AND NOT {mine.format('x')} AND NOT {them.format('x')})
                       LIMIT ?""")): return 'answered'
        return None
    def trusted_sender(self, mailbox: str, email: str):
        r = self._one('SELECT * FROM sender_trust WHERE LOWER(Mailbox)=LOWER(?) AND LOWER(Address)=LOWER(?)', (mailbox or '', email or ''))
        return r['Reason'] if r else None
    def remember_trust(self, mailbox: str, email: str, reason: str):
        self._exec('INSERT OR REPLACE INTO sender_trust (Mailbox, Address, Reason, CheckedAt) VALUES (?,?,?,?)',
                   ((mailbox or '').lower(), (email or '').lower(), reason, _now()))
    def trusts(self, reasons) -> list:
        return self._rows(f"SELECT * FROM sender_trust WHERE Reason IN ({','.join('?' * len(reasons))}) ORDER BY CheckedAt DESC", tuple(reasons))
    def forget_trust(self, mailbox: str, email: str) -> bool:
        q, p = 'FROM sender_trust WHERE LOWER(Mailbox)=LOWER(?) AND LOWER(Address)=LOWER(?)', (mailbox or '', email or '')
        if not self._one('SELECT 1 x ' + q, p): return False
        self._exec('DELETE ' + q, p); return True
    def _heal_notes(self):
        """An older install's notes table, healed in place before memory.migrate reads its rows into the memory and drops it."""
        self.cx.execute("UPDATE memory SET Note=REPLACE(Note, ' from an unknown sender', '') WHERE Source='verdict' AND Note LIKE '%from an unknown sender%'")
        # data heal: verdict notes used to be written as RULES ("Messages from X like 'S' are not
        # tasks - do not open tasks or draft replies"); they are EVIDENCE now (2026-08-27), so the
        # old shape becomes the dated line the new ones get - same facts, no instruction in it
        _RULE = re.compile(r"^Messages from (?P<who>\S+) like '(?P<subj>.*)' are not tasks - do not open tasks or draft replies\.$"
                           r"|^Mail about \"(?P<topic>.*)\" is not a task - do not open tasks or draft replies\.$"
                           r"|^Mail (?:about \"(?P<t2>.*)\"|like \"(?P<s2>.*)\"(?: from (?P<w2>\S+)| from anyone at (?P<d2>\S+)|, whoever sends it,)?) is other people's work - file it, do not open a task or draft a reply\.$")
        for r in self.cx.execute("SELECT MemoryId, Note, Scope, ScopeKey, CreatedAt FROM memory WHERE Source='verdict'").fetchall():
            m = _RULE.match(r['Note'] or '')
            if not m: continue
            g = m.groupdict(); when = str(r['CreatedAt'] or '')[:10]
            subj = g.get('subj') or g.get('s2') or ''
            who = g.get('who') or g.get('w2') or (r['ScopeKey'] if r['Scope'] == 'sender' else '')
            topic = g.get('topic') or g.get('t2')
            verdict = 'NOT A TASK: the owner filed it, no task, no reply' if 'are not tasks' in r['Note'] or 'is not a task' in r['Note']                           else "NOT OURS: other people's work, no task, no reply"
            about = (f' - the topic "{topic}"' if topic else f" - anyone at {g['d2']}" if g.get('d2')
                     else ' - whoever sends it' if 'whoever sends it' in r['Note'] else '')
            line = f'{when}: "{subj or topic or ""}"' + (f' from {who}' if who else '') + f'{about} - {verdict}'
            self.cx.execute('UPDATE memory SET Note=? WHERE MemoryId=?', (line, r['MemoryId']))

    # projects and their identities ---------------------------------------------------------
    def ensure_project(self, name: str, description: str = None, actor: str = 'system') -> int:
        """Return the durable project id for a display name, creating it if needed."""
        name = str(name or '').strip()
        if not name: raise ValueError('a project needs a name')
        row = self._one('SELECT ProjectId FROM project WHERE Name=? COLLATE NOCASE', (name,))
        if row:
            if description:
                self._exec('UPDATE project SET Description=COALESCE(NULLIF(Description,\'\'),?), UpdatedBy=?, UpdatedAt=? '
                           'WHERE ProjectId=?', (description, actor, _now(), row['ProjectId']))
            return row['ProjectId']
        try:
            return self._insert('project', {'Name': name, 'Description': description, 'Active': 1,
                                            'CreatedBy': actor, 'UpdatedBy': actor}, PROJECT_COLS,
                                {'CreatedAt': _now(), 'UpdatedAt': _now()})
        except sqlite3.IntegrityError:       # another ingest thread created the same name
            return self._one('SELECT ProjectId FROM project WHERE Name=? COLLATE NOCASE', (name,))['ProjectId']

    def upsert_project_link(self, project_id: int, kind: str, value: str, label: str = None,
                            confidence: float = 0, confirmed: bool = False,
                            source: str = 'system') -> int:
        """Add one edge without weakening evidence already on it."""
        kind, value = str(kind or '').strip().lower(), str(value or '').strip()
        if not kind or not value: raise ValueError('a project link needs a kind and value')
        row = self._one('SELECT * FROM project_link WHERE ProjectId=? AND Kind=? AND Value=? COLLATE NOCASE',
                        (project_id, kind, value))
        if row:
            self._exec('UPDATE project_link SET Label=COALESCE(NULLIF(?,\'\'),Label), Confidence=MAX(Confidence,?), '
                       'Confirmed=MAX(Confirmed,?), Source=COALESCE(NULLIF(?,\'\'),Source), UpdatedAt=? WHERE LinkId=?',
                       (label, float(confidence or 0), 1 if confirmed else 0, source, _now(), row['LinkId']))
            return row['LinkId']
        return self._insert('project_link', {'ProjectId': project_id, 'Kind': kind, 'Value': value,
                                             'Label': label, 'Confidence': float(confidence or 0),
                                             'EvidenceCount': 0, 'Confirmed': 1 if confirmed else 0,
                                             'Source': source}, PROJECT_LINK_COLS,
                            {'CreatedAt': _now(), 'UpdatedAt': _now()})

    def upsert_routing_fact(self, field: str, signal: str, key: str, value: str,
                            confidence: float = 0, confirmed: bool = False, source: str = 'system') -> int:
        """One lesson about a verdict field, added without weakening evidence already on it."""
        field, signal = str(field or '').strip().lower(), str(signal or '').strip().lower()
        key, value = str(key or '').strip(), str(value or '').strip()
        if not (field and signal and key and value): raise ValueError('a routing fact needs a field, a signal and a value')
        row = self._one('SELECT * FROM routing_fact WHERE Field=? AND Signal=? AND SignalKey=? COLLATE NOCASE AND Value=?',
                        (field, signal, key, value))
        if row:
            self._exec('UPDATE routing_fact SET Confidence=MAX(Confidence,?), Confirmed=MAX(Confirmed,?), '
                       "Source=COALESCE(NULLIF(?,''),Source), UpdatedAt=? WHERE FactId=?",
                       (float(confidence or 0), 1 if confirmed else 0, source, _now(), row['FactId']))
            return row['FactId']
        return self._insert('routing_fact', {'Field': field, 'Signal': signal, 'SignalKey': key, 'Value': value,
                                             'Confidence': float(confidence or 0), 'EvidenceCount': 0,
                                             'Confirmed': 1 if confirmed else 0, 'Source': source},
                            ROUTING_FACT_COLS, {'CreatedAt': _now(), 'UpdatedAt': _now()})

    def add_routing_evidence(self, fact_id: int, task_id: int, reason: str = 'owner corrected the verdict') -> bool:
        """Count a task once against a lesson. Same curve the project graph uses, for the same
        reason: one correction is a visible hypothesis (.72), two independent ones may route (.86)."""
        if self._one('SELECT 1 x FROM routing_evidence WHERE FactId=? AND TaskId=?', (fact_id, task_id)):
            return False
        try:
            self._exec('INSERT INTO routing_evidence (FactId,TaskId,Reason,CreatedAt) VALUES (?,?,?,?)',
                       (fact_id, task_id, reason, _now()))
        except sqlite3.IntegrityError:
            return False
        n = self._one('SELECT COUNT(*) n FROM routing_evidence WHERE FactId=?', (fact_id,))['n']
        self._exec('UPDATE routing_fact SET EvidenceCount=?, Confidence=MAX(Confidence,?), UpdatedAt=? WHERE FactId=?',
                   (n, min(.96, .58 + .14 * int(n)), _now(), fact_id))
        return True

    def routing_facts(self, field: str = None, signals: list = None) -> list:
        """Lessons on file, strongest first. `signals` is [(signal, key), ...] from this message."""
        sql, args = 'SELECT * FROM routing_fact WHERE 1=1', []
        if field: sql, args = sql + ' AND Field=?', args + [str(field).lower()]
        if signals is not None:
            if not signals: return []
            sql += ' AND (' + ' OR '.join(['(Signal=? AND SignalKey=? COLLATE NOCASE)'] * len(signals)) + ')'
            for s, k in signals: args += [str(s).lower(), str(k)]
        return self._rows(sql + ' ORDER BY Confirmed DESC, Confidence DESC, EvidenceCount DESC', tuple(args))

    def add_project_evidence(self, link_id: int, task_id: int, reason: str = 'owner chose repository') -> bool:
        """Count a task once on an identity edge; return False when startup already replayed it."""
        if self._one('SELECT 1 x FROM project_evidence WHERE LinkId=? AND TaskId=?', (link_id, task_id)):
            return False
        try:
            self._exec('INSERT INTO project_evidence (LinkId,TaskId,Reason,CreatedAt) VALUES (?,?,?,?)',
                       (link_id, task_id, reason, _now()))
        except sqlite3.IntegrityError:
            return False
        n = self._one('SELECT COUNT(*) n FROM project_evidence WHERE LinkId=?', (link_id,))['n']
        # One choice is a visible hypothesis; two independent owner choices are enough to route.
        confidence = min(.96, .58 + .14 * int(n))
        self._exec('UPDATE project_link SET EvidenceCount=?, Confidence=MAX(Confidence,?), UpdatedAt=? WHERE LinkId=?',
                   (n, confidence, _now(), link_id))
        return True

    def clear_project_evidence(self, task_id: int):
        """Forget what one former repo choice taught before recording its replacement."""
        links = [r['LinkId'] for r in self._rows('SELECT DISTINCT LinkId FROM project_evidence WHERE TaskId=?',
                                                 (task_id,))]
        if not links: return
        self._exec('DELETE FROM project_evidence WHERE TaskId=?', (task_id,))
        for lid in links:
            row = self._one('SELECT Confirmed FROM project_link WHERE LinkId=?', (lid,))
            if not row: continue
            n = self._one('SELECT COUNT(*) n FROM project_evidence WHERE LinkId=?', (lid,))['n']
            if not n and not row['Confirmed']:
                self._exec('DELETE FROM project_link WHERE LinkId=?', (lid,))
            else:
                confidence = 1.0 if row['Confirmed'] else min(.96, .58 + .14 * int(n))
                self._exec('UPDATE project_link SET EvidenceCount=?, Confidence=?, UpdatedAt=? WHERE LinkId=?',
                           (n, confidence, _now(), lid))

    def list_projects(self, active_only=True):
        return self._rows('SELECT * FROM project' + (' WHERE Active=1' if active_only else '') + ' ORDER BY Name')

    def project_links(self, project_id: int = None, kind: str = None):
        q = ('SELECT l.*, p.Name ProjectName, p.Description ProjectDescription FROM project_link l '
             'JOIN project p ON p.ProjectId=l.ProjectId WHERE p.Active=1')
        vals = []
        if project_id is not None: q += ' AND l.ProjectId=?'; vals.append(project_id)
        if kind is not None: q += ' AND l.Kind=?'; vals.append(kind)
        return self._rows(q + ' ORDER BY l.Confirmed DESC, l.Confidence DESC, l.LinkId', vals)
    def get_doc(self, name):
        """The document AS WRITTEN - placeholders and all. This is what the editor loads and saves;
        every consumer that feeds a doc to an AI wants `doc()` instead."""
        # ...held with the settings (held_settings) while a read holds them: the owner's name is read from SOUL.md by every reader of a task's page
        held = getattr(_HELD, 'settings', None)
        if held is not None and held[0] is self:
            if ('doc', name) not in held[1]: held[1][('doc', name)] = self._one('SELECT Content FROM doc WHERE Name=?', (name,))
            r = held[1][('doc', name)]
        else: r = self._one('SELECT Content FROM doc WHERE Name=?', (name,))
        return r['Content'] if r else None
    def doc_owner(self, name):
        """Who last wrote it - 'template' means nobody has, and the shipped text still flows in."""
        r = self._one('SELECT UpdatedBy FROM doc WHERE Name=?', (name,)); return r['UpdatedBy'] if r else None
    def save_doc(self, name, content, actor):
        self._exec('INSERT INTO doc (Name, Content, UpdatedBy, UpdatedAt) VALUES (?,?,?,?) ON CONFLICT(Name) DO UPDATE SET Content=?, UpdatedBy=?, UpdatedAt=?',
                   (name, content, actor, _now(), content, actor, _now()))
    def delete_doc(self, name): self._exec('DELETE FROM doc WHERE Name=?', (name,))
    def doc(self, name):
        """The document as the AI should read it: {{owner}} and friends filled in. The name used to
        be typed into six places across SOUL.md and three more in CODING.md, so changing it changed
        one of them - a doc that half calls you by name and half calls you John Smith.
        ...and with NOBODY named yet, the shipped example is a hole, not a person: triage read "You work for John Smith", found mail
        greeting Alex, and filed Alex's own asks as someone else's (agent-flow audit, 2026-11-07). The owner is then "the owner",
        known only by the mailbox the mail came to - SOUL.md says so."""
        who, text = self.owner(), self.get_doc(name) or ''
        if who['owner'] != 'the owner': return render_doc(text, who)
        text = re.sub(r'\s*\(\s*\{\{\s*owner_email\s*\}\}\s*\)', '', retoken_doc(text, *TEMPLATE_OWNER))
        if name == 'soul' and text.strip(): text = f'{text.rstrip()}\n\n{NO_NAME_YET}'     # an empty SOUL.md stays empty: nothing to misread
        return render_doc(text, who)
    def get_doc_row(self, name): return self._one('SELECT Name, Content, UpdatedBy, UpdatedAt FROM doc WHERE Name=?', (name,))
    def doc_names(self) -> list: return [r['Name'] for r in self._rows('SELECT Name FROM doc ORDER BY Name') if r['Name'] not in UNREAD_DOCS]
    def github_permissions(self) -> tuple:
        """(use_github_as_tracker, agents_may_push) - read from the GitHub CONNECTOR, where the
        GitHub decisions belong, falling back to the legacy settings so nothing regresses.
        use_as_tracker means exactly that: the team runs on GitHub issues, so agents may open
        and update them for the work; off means Taskuary is the tracker and issues are noise."""
        cfg = {}
        try:
            c = self.get_connector_by_type('github')
            cfg = json.loads((c or {}).get('ConfigJson') or '{}')
        except Exception:
            pass
        st = self.get_settings()
        tracker = cfg['use_as_tracker'] if 'use_as_tracker' in cfg else st.get('agent_issues_enabled') == '1'
        push = cfg['agents_push'] if 'agents_push' in cfg else st.get('agent_push_enabled') == '1'
        return bool(tracker), bool(push)

    def github_for(self, repo=None, with_secret=False):
        """The GitHub card that reaches `repo` - the one its source row belongs to - else the default card. Two
        accounts (a personal one and an org's) are two cards, and the first card's token cannot see the second's repos."""
        src = next((s for s in self.list_sources(active_only=False) if s.get('Channel') == 'github' and s.get('ConnectorId')
                    and str(s.get('Address') or '').lower() == str(repo or '').lower()), None) if repo else None
        c = self.get_connector(src['ConnectorId'], with_secret) if src else None
        return c if c and c.get('Type') == 'github' else self.get_connector_by_type('github', with_secret)

    def owner(self) -> dict:
        """Who this hub belongs to, from one setting. Falls back to whatever SOUL.md says so an
        existing document keeps working before the owner has ever touched the field."""
        st = {k: self.get_setting(k) for k in ('owner_name', 'owner_email')}      # ...two rows, never the whole table: read per mail judged
        soul_name = owner_from_soul(self.get_doc('soul') or '')
        if soul_name == 'John Smith': soul_name = None            # the shipped example, not a person
        name = (st.get('owner_name') or '').strip() or soul_name or 'the owner'
        email = (st.get('owner_email') or '').strip() or email_from_soul(self.get_doc('soul') or '')
        if email == 'john.smith@example.com': email = ''
        # nobody named yet: "the owner" whole - its first word rendered {{owner_first}} as "the" ("the presses Next")
        first = name if name == 'the owner' else name.split()[0] if name.split() else name
        return {'owner': name, 'owner_first': first, 'owner_email': email}

    # feed
    # One definition of "this is on me", used by the chip, the counter and the filter alike:
    # a decision is pending, OR the task is not finished and no agent is working it right
    # now. A task nobody is running is nobody's but yours.
    # The aliases (rv, t, rn) are the JOINs in feed() - one pass, not a correlated
    # subquery per row. The chip and the pending_only filter MUST keep using this
    # same expression or they will disagree.
    # A note you left yourself is work on your list, but it is not work waiting on you UNTIL
    # ITS TIME: "chase this Tuesday" nagging from Monday is the thing that makes a reminder
    # useless. A note's row is stamped with when it is FOR (ownwork.note), so the clock decides.
    # ...and it is NOT on you once you have already answered it yourself, somewhere else.
    # channels.ingest_own_message stores the owner's own lines as `context` rows on the same
    # conversation - its docstring has said "so the panel shows it was answered" since it was
    # written, and nothing ever read them. So a Teams message answered in Teams thirty seconds
    # later still counted as waiting on the owner, forever. A pending draft still wins: that is
    # a decision nobody has taken.
    ANSWERED_AT = """(SELECT MAX(o.SentAt) FROM message o
                       WHERE o.ConversationId = m.ConversationId AND IFNULL(m.ConversationId,'') <> ''
                         AND o.Status = 'context' AND o.SentAt > m.SentAt)"""
    # ...and it is not on you while the ball is in THEIR court. The last word on the thread is
    # yours (wherever you typed it), or Taskuary sent the reply and nothing has come back since:
    # you are waiting on them. The row used to read "on your list - nobody is on this" for the
    # whole of that wait, so "needs me" counted every thread the owner had just answered.
    LAST_WORD_YOURS = """(SELECT CASE WHEN o.Status='context' OR IFNULL(o.Direction,'')='out' THEN 1 ELSE 0 END
                          FROM message o
                          WHERE o.ConversationId = m.ConversationId AND IFNULL(m.ConversationId,'') <> ''
                            AND o.Status <> 'skipped'
                          ORDER BY o.SentAt DESC, o.MessageId DESC LIMIT 1)"""
    SENT_UNANSWERED = """(rv.Status IN ('approved','edited','sent') AND rv.Kind <> 'action'
                         AND NOT EXISTS (SELECT 1 FROM message x
                                         WHERE x.ConversationId = m.ConversationId AND IFNULL(m.ConversationId,'') <> ''
                                           AND x.Status NOT IN ('context','history','skipped') AND IFNULL(x.Direction,'in') <> 'out'
                                           AND x.SentAt > IFNULL(rv.DecidedAt, rv.CreatedAt)))"""
    THEIR_TURN = ("(CASE WHEN m.TaskId IS NOT NULL AND IFNULL(t.Status,'') NOT IN ('done', 'dropped') "
                  f"AND (IFNULL({LAST_WORD_YOURS}, 0) = 1 OR {SENT_UNANSWERED}) THEN 1 ELSE 0 END)")
    NEEDS_YOU_T = """(CASE WHEN rv.Status='pending'
                          OR (m.TaskId IS NOT NULL AND IFNULL(t.Status,'') NOT IN ('done', 'dropped')
                              AND rn.TaskId IS NULL
                              AND (IFNULL(t.Kind,'') <> 'note' OR m.SentAt <= datetime('now', 'localtime'))
                              AND m.Status <> 'withdrawn'
                              AND {answered} IS NULL
                              AND {theirs} = 0)
                    THEN 1 ELSE 0 END)"""
    NEEDS_YOU = NEEDS_YOU_T.replace('{answered}', ANSWERED_AT).replace('{theirs}', THEIR_TURN)

    def feed(self, limit=100, days=14, pending_only=False, channel=None, offset=0, source=None,
             live_state=_LIVE_UNSET, ids=None, task_id=None, sent=False, every=False):
        # The newest route/review, the attachment count and the chain size are looked up per output row on their
        # indexes. They were derived tables over the WHOLE route/review/attachment/message tables (GROUP BY, then
        # `RouteId IN (12k MAXes)`), which every output row walked: ~1-2 ms a row, 1.5 s for 500, 14 s for the
        # full history, all under store.lock. tests/test_feed_plan.py pins both the plan and the rows.
        q = f'''SELECT m.MessageId, m.Channel, m.SourceName, m.Subject, m.FromName, m.FromEmail, m.SentAt, m.CreatedAt IngestedAt,
                       m.ConversationId,
                       substr(m.BodyText, 1, 4000) Preview, m.Status MsgStatus, m.SourceLink, m.TaskId, m.Direction, m.Brief, m.TriageTitle, m.SenderClass,
                       CASE WHEN json_valid(m.MailMetaJson) AND json_extract(m.MailMetaJson, '$.unsub.done') IS NULL
                            THEN json_extract(m.MailMetaJson, '$.unsub.via') END Unsub,
                       t.Title, t.Status TaskStatus, t.Priority, t.Kind TaskKind, t.Tags TaskTags, {self.NEEDS_YOU} NeedsYou,
                       rt.Decision, rt.Reason RouteReason,
                       rv.ReviewId, rv.Status ReviewStatus, rv.Kind ReviewKind,
                       CASE WHEN rv.ReviewId IS NULL THEN NULL WHEN IFNULL(rv.DraftText,'')<>'' THEN 1 ELSE 0 END HasDraft, rv.DraftError, rv.DraftNeeds,
                       (SELECT COUNT(*) FROM attachment a WHERE a.MessageId=m.MessageId) Attachments,
                       {self.ANSWERED_AT} AnsweredAt,
                       {self.THEIR_TURN} TheirTurn
                FROM message m
                LEFT JOIN task t ON t.TaskId=m.TaskId
                LEFT JOIN route rt ON rt.RouteId=(SELECT MAX(RouteId) FROM route WHERE MessageId=m.MessageId)
                LEFT JOIN review rv ON rv.ReviewId=(SELECT MAX(ReviewId) FROM review WHERE MessageId=m.MessageId)
                LEFT JOIN (
                    SELECT DISTINCT TaskId FROM run WHERE Status='running'
                ) rn ON rn.TaskId=m.TaskId
                WHERE m.CreatedAt >= datetime('now', 'localtime', ?) AND (m.Status NOT IN ('context', 'history', 'skipped')'''
        # `sent`: the owner's own mail too - read in from Sent as thread context ('context', Direction out), so no list shows it,
        # but a SEARCH must find it: "did I answer the invite" had no row to land on (2026-10-26)
        # `every`: whatever its status - a message asked for by its own id (a Search pick) is that message, skipped at the first sync or not
        q += " OR (m.Direction='out' AND m.Status='context')) " if sent else ' OR 1) ' if every else ') '
        p = [f'-{int(days)} days']
        if pending_only: q += f' AND {self.NEEDS_YOU}=1'
        # channel accepts a csv so the UI can filter by a CATEGORY (messages = email,
        # teams, slack) without needing one request per channel
        if channel:
            chans = [c.strip() for c in str(channel).split(',') if c.strip()]
            q += f" AND m.Channel IN ({','.join('?' * len(chans))})"
            p += chans
        if source: q += ' AND m.SourceName=?'; p.append(source)   # e.g. one mailbox of several
        if ids is not None: q += f" AND m.MessageId IN ({','.join(str(int(i)) for i in ids) or 'NULL'})"
        if task_id is not None: q += ' AND m.TaskId=?'; p.append(int(task_id))   # one task's rows (funnel.item_for_key)
        q += f' ORDER BY m.SentAt DESC, m.MessageId DESC LIMIT {int(limit)} OFFSET {int(offset)}'
        rows = self._rows(q, p)
        # ...and each row's chain size, once per task: counted per output row it walked the whole task for every line of it, and a
        # 1,500-line chat on one task held each rail build - and so every rail press - for 0.4 s of the 0.45 (the owner, 2026-11-01)
        tids = sorted({int(r['TaskId']) for r in rows if r.get('TaskId') is not None})
        chain = {c['TaskId']: c['n'] for c in self._rows(f"SELECT TaskId, COUNT(*) n FROM message WHERE TaskId IN ({','.join(map(str, tids))}) "
                                                          "AND Status NOT IN ('context','history') GROUP BY TaskId")} if tids else {}
        for r in rows: r['ChainSize'] = chain.get(r.get('TaskId'), 0)
        # the one-word tag every row wears (categories.py) - decided here, once, so the feed,
        # the digest and the task page never disagree about what a message is
        from .categories import category_of, team_domains_of
        team = team_domains_of(self.get_settings())
        for r in rows: r['Category'] = category_of(r, team)
        # NEEDS_YOU (SQL) only sees `run` rows; an agent in a LIVE pty session is working the task
        # just as much, and the row said "needs you - no agent is working it" over a running
        # console. Working carries the agent's name so the chip can say who.
        live, parked = {r['TaskId']: SHOWN for r in self.running_runs()}, {}       # Taskuary, never the profile (kinds.shown)
        try:
            # the light road: a feed row reads who works a task, never the session's files - one feed read ran `git status` in
            # every live session's checkout, and a task's own read makes one (funnel.item_for_key)
            from . import funnel
            observed_live = funnel.observe(0) if live_state is _LIVE_UNSET else live_state
            for t in observed_live:
                if not t.get('taskId'): continue
                live[t['taskId']] = shown_agent(t)
                # "an agent has it" and "an agent stopped and is waiting on you" are opposite
                # facts and the row wore the same chip for both, so a session sitting on an
                # unanswered question read as work in progress for as long as nobody looked.
                if t.get('waiting'): parked[t['taskId']] = str(t.get('line') or '')   # ...and its ONE sentence (workerstate.says)
        except Exception:
            pass                                   # no pty support here: runs alone decide
        for r in rows:
            if r.get('TaskId') in live and r.get('TaskStatus') not in ('done', 'dropped'):
                r['Working'] = live[r['TaskId']]
                r['AgentWaiting'] = r['TaskId'] in parked
                r['AgentLine'] = parked.get(r['TaskId']) or ''
                if r.get('ReviewStatus') != 'pending': r['NeedsYou'] = 1 if r['TaskId'] in parked else 0
        # Unread and All are two views of this SAME feed.  Triage's verdict is not a read receipt:
        # a filed FYI, automated notice, promotional message, ignored-by-policy row, report, or
        # Assistant post all arrived and therefore start unread.  The old Assistant rail used
        # funnel.build() as its unread source; that separate source applied category, age, mute,
        # conversation and size filters, so rows plainly visible in All (notably ordinary product
        # mail) could never appear in Unread.  Put the durable handled state on every feed row and
        # let the client filter the one shared result instead.
        funnel_states = self.funnel_states()
        ideas_by_mid = {}
        for idea in self.list_ideas():
            if idea.get('MessageId'):
                ideas_by_mid.setdefault(idea['MessageId'], []).append(idea)
        now_dt = datetime.now()
        now = now_dt.strftime('%Y-%m-%d %H:%M:%S')
        try: unread_hours = max(1, int(self.get_setting('funnel_hours') or 12))
        except (TypeError, ValueError): unread_hours = 12
        unread_cutoff = (now_dt - timedelta(hours=unread_hours)).strftime('%Y-%m-%d %H:%M:%S')
        for r in rows:
            linked_ideas = ideas_by_mid.get(r['MessageId'], []) if r.get('Channel') == 'assistant' else []
            brief_idea_ids = []
            if r.get('Channel') == 'assistant' and r.get('Brief'):
                try: brief_idea_ids = [i.get('id') for i in (json.loads(r['Brief']).get('ideas') or []) if i.get('id')]
                except (TypeError, ValueError, json.JSONDecodeError): pass
            open_ideas = [i for i in linked_ideas if i.get('Status') == 'open']
            unread_ideas = [i for i in open_ideas
                            if (funnel_states.get(f"idea:{i['IdeaId']}") or {}).get('Status') not in ('surfaced', 'done', 'later', 'skip')]
            if unread_ideas:
                key = f"idea:{unread_ideas[0]['IdeaId']}"
            elif r.get('ReviewStatus') == 'pending' and r.get('ReviewId'):
                key = f"review:{r['ReviewId']}"
            elif r.get('Working') and r.get('TaskId'):
                key = f"agent:{r['TaskId']}"
            elif r.get('Channel') == 'report':
                key = f"report:{r['MessageId']}"
            else:
                key = f"msg:{r['MessageId']}"
            state = funnel_states.get(key) or {}
            verdict = state.get('Status')
            deferred = verdict in ('later', 'skip') and (not state.get('Until') or state['Until'] > now)
            # The pipe is a live unread window, not a migration that resurrects every historical
            # Timeline row which predates funnel_state. CreatedAt is used (not the provider's sent
            # date), so mail first synced after an offline weekend is still a new arrival. Explicit
            # work remains visible past the window; an owner policy's `ignored` is already handled.
            active_work = bool(r.get('AgentWaiting') or r.get('Working')
                               or r.get('ReviewStatus') == 'pending' or r.get('NeedsYou'))
            aged = bool(r.get('IngestedAt') and r['IngestedAt'] < unread_cutoff and not active_work)
            # Assistant reports can repeat the same durable idea. set_ideas_message moves that
            # idea to the newest post, so an older post whose Brief names ideas but owns none is a
            # superseded copy, not fresh unread work. The newest row follows idea:<id>, exactly the
            # same key the chat settles.
            assistant_handled = bool(brief_idea_ids and not unread_ideas)
            handled = (assistant_handled or verdict in ('surfaced', 'done') or deferred
                       or r.get('TaskStatus') in ('done', 'dropped')
                       or (r.get('ReviewId') and r.get('ReviewStatus') not in (None, 'pending'))
                       or bool(r.get('AnsweredAt'))
                       or r.get('MsgStatus') in ('withdrawn', 'ignored')
                       or aged)
            # Work currently inside an agent remains on the unread rail as an inactive status row.
            # It cannot become Next (funnel.next_item skips lane=working), and when the agent waves
            # the same stable agent:<task> key is promoted. A prior read of the source message must
            # not make the live work disappear.
            if r.get('Working') and not r.get('AgentWaiting') and r.get('TaskStatus') not in ('done', 'dropped'):
                handled = False
            r['FunnelKey'] = key
            r['Unread'] = 0 if handled else 1
            # Sorting Unread is not a second triage. These are only the durable fields written by
            # the one route decision, plus live agent state. All remains chronological; Unread uses
            # this band to promote what blocks work or needs the owner.
            from .processing_order import feed_band
            if r.get('Channel') == 'report':
                from .funnel import report_failed
                r['ReportFailed'] = report_failed(self, r.get('Subject') or '', r.get('MessageId'))
            r['UnreadRank'] = feed_band(r)
        # the SQL filter matched before live sessions were known; a row a working agent just took off
        # you must not sit in "needs me" wearing a chip that says otherwise
        if pending_only: rows = [r for r in rows if r.get('NeedsYou')]
        return rows

    def feed_tag(self, days=14, pending_only=False, channel=None, source=None):
        """Cheap fingerprint of what /api/feed would return, so a 30s refresh can 304.

        Counts and MAX(id) miss in-place chip changes (reject a review, release a
        held draft, ignore a message) - the row is the same row. This connection's
        write counter covers our own UPDATEs; PRAGMA data_version covers a second
        connection's commits. Filter args stay in the tag so two URLs cannot share
        a 304. A false miss just reruns the JOIN; a false hit freezes the Timeline."""
        with self.lock:
            row = self.cx.execute('PRAGMA data_version').fetchone()
            ver = int(row[0] if row else 0)
            n = self._writes
        bits = [n, ver, int(bool(pending_only)), channel or '', source or '', int(days)]
        return '-'.join(str(b) for b in bits)

    def inbound_threads(self, days=30):
        """One row per inbound CONVERSATION of the last `days` - the sender and the subject, nothing
        else. What the Advisor's connect evidence (assistant.connect_evidence) reads to say "N threads this month were about X", and the reason it
        does not read the Timeline for it: `feed` carries a dozen joins, so it was capped at 600 rows
        and saw under a third of a month on a busy mailbox, with whatever flooded the last week
        crowding the rest out (TQ-0651). The app's own posts are left out here - a row the assistant
        wrote is not a thread about anything."""
        q = """SELECT MIN(MessageId) MessageId, MAX(FromEmail) FromEmail, MAX(Subject) Subject
               FROM message
               WHERE CreatedAt >= datetime('now', 'localtime', ?) AND Status NOT IN ('context', 'history', 'skipped')
                 AND IFNULL(Direction, 'in') <> 'out' AND IFNULL(Channel, '') <> 'assistant'
               GROUP BY IFNULL(ConversationId, 'm' || MessageId)"""
        return self._rows(q, (f'-{int(days)} days',))

    def people(self, limit=60):
        """Everyone who has written to you lately - the hand-off picker's address book."""
        q = """SELECT FromEmail Email, MAX(FromName) Name, COUNT(*) N, MAX(SentAt) Last
               FROM message WHERE FromEmail LIKE '%@%' AND Status<>'context'
               GROUP BY LOWER(FromEmail) ORDER BY Last DESC"""
        return self._rows(q if limit is None else q + ' LIMIT ?', () if limit is None else (int(limit),))

    def chats(self, limit=200):
        """Every chat Taskuary has seen, newest first: the id a message can be SENT to, and a
        name to recognise it by. The id is whatever the channel itself uses - a Graph chat id,
        a WhatsApp JID - which is exactly why nobody can type it from memory."""
        q = """SELECT Channel, ConversationId Cid,
                      MAX(CASE WHEN IFNULL(Direction,'in')<>'out' THEN FromName END) Name,
                      COUNT(*) N, MAX(SentAt) Last
               FROM message WHERE ConversationId IS NOT NULL AND IFNULL(Channel,'')<>'email'
               GROUP BY Channel, ConversationId ORDER BY Last DESC"""
        return self._rows(q if limit is None else q + ' LIMIT ?', () if limit is None else (int(limit),))

    def message_routes(self, mid: int) -> list:
        """Every judgement ever made ABOUT THIS MESSAGE, oldest first.

        list_routes is keyed on the TASK, and "not ours" deletes the task - so the one verdict the
        owner most wants to see recorded took its own record away with it. Routes are keyed on the
        message and outlive it."""
        return self._rows('SELECT * FROM route WHERE MessageId=? ORDER BY RouteId', (mid,))

    def _links(self, task_id, msgs=None) -> list:
        from . import linkdocs
        try: return linkdocs.of_task(self, task_id, msgs)
        except Exception as e: logger.debug(f'task {task_id}: linked documents not listed - {e}'); return []

    def task_detail(self, task_id):
        t = self.get_task(task_id)
        if not t: return None
        msgs, atts = self.list_messages(task_id), {}
        # ...the files in one read, in the messages' order: a read per message was 1,500 on a long chat (the owner, 2026-11-01)
        for a in self._rows('SELECT a.* FROM attachment a JOIN message m ON m.MessageId=a.MessageId WHERE m.TaskId=? ORDER BY a.AttachmentId',
                            (task_id,)): atts.setdefault(a['MessageId'], []).append(a)
        reviews = self._rows('SELECT rv.*, m.FromName, m.FromEmail, m.Channel, m.SourceName, m.ConversationId, m.Subject FROM review rv '
                             'LEFT JOIN message m ON m.MessageId=rv.MessageId WHERE rv.TaskId=? ORDER BY rv.ReviewId DESC', (task_id,))
        # ...and a reply to a promise's own mail answers whom it was made to, not its author: "sends this to Alex Doyle" was the owner
        if (p := self.promised_in(t)) and any(r.get('MessageId') == p['MessageId'] for r in reviews):
            who = self.promisee(p) or 'them'
            for r in reviews:
                if r.get('MessageId') == p['MessageId']: r.update(FromName=who, FromEmail='')
        return {'task': {**t, 'ChecklistMd': self.checklist_markdown(task_id)}, 'ref': task_ref(task_id), 'messages': msgs,
                'checklist': self.task_checklist(task_id),
                'attachments': [a for m in msgs for a in atts.get(m['MessageId'], ())],
                # ...and the documents its messages LINK to (linkdocs), once each - counted beside the files ("6 attachments · 2 links")
                'links': [{k: d[k] for k in ('id', 'label', 'url')} for d in self._links(task_id, msgs)],
                'artifacts': self.list_task_artifacts(task_id),
                'routes': self.list_routes(task_id), 'comments': self.list_comments(task_id),
                'runs': self.list_runs(task_id), 'audit': self.list_audit('task', task_id),
                # ...with who it answers, as list_reviews has: without it a draft's To line read "this conversation"
                'reviews': reviews,
                # ...and each close and reopen, so Close out stacks its rounds (closeoutRounds.js) - the replies are the reviews above
                'closeouts': self.closeouts(task_id)}

    # ── knowledge base (knowledge.py): documents as passages behind an FTS5 index ──
    def kb_doc(self, cid, source, path):
        return self._one('SELECT * FROM kb_doc WHERE ConnectorId=? AND Source=? AND Path=?', (cid, source, path))
    def kb_put(self, doc: dict, chunks: list, vecs: list = None, model: str = '') -> int:
        """Replace one document's passages in a single transaction - _exec commits per statement,
        and a library of a thousand files is not a thousand fsyncs per file. `vecs` (kbembed.pack blobs,
        one per passage) ride in the same transaction, so a passage and its vector are never out of step."""
        with self.lock:
            cur = self.cx.cursor()
            old = cur.execute('SELECT DocId FROM kb_doc WHERE ConnectorId=? AND Source=? AND Path=?',
                              (doc['ConnectorId'], doc['Source'], doc['Path'])).fetchone()
            if old: self._kb_drop(cur, old[0])
            cur.execute('INSERT INTO kb_doc (ConnectorId,Source,Path,Name,Modified,Size,Chars,IndexedAt) VALUES (?,?,?,?,?,?,?,?)',
                        (doc['ConnectorId'], doc['Source'], doc['Path'], doc.get('Name'), doc.get('Modified'), doc.get('Size'),
                         doc.get('Chars'), _now()))
            did = cur.lastrowid
            for i, t in enumerate(chunks):
                cur.execute('INSERT INTO kb_chunk (DocId, Seq, Text) VALUES (?,?,?)', (did, i, t))
                cid = cur.lastrowid
                if self.kb_fts: cur.execute('INSERT INTO kb_fts (Text, ChunkId) VALUES (?,?)', (t, cid))
                if vecs and i < len(vecs) and vecs[i]:
                    cur.execute('INSERT OR REPLACE INTO kb_vec (ChunkId, Model, Dim, Vec) VALUES (?,?,?,?)', (cid, model, len(vecs[i]) // 4, vecs[i]))
            self.cx.commit(); self._writes += 1
            return did
    def _kb_drop(self, cur, did):
        if self.kb_fts: cur.execute('DELETE FROM kb_fts WHERE ChunkId IN (SELECT ChunkId FROM kb_chunk WHERE DocId=?)', (did,))
        cur.execute('DELETE FROM kb_vec WHERE ChunkId IN (SELECT ChunkId FROM kb_chunk WHERE DocId=?)', (did,))
        cur.execute('DELETE FROM kb_chunk WHERE DocId=?', (did,)); cur.execute('DELETE FROM kb_doc WHERE DocId=?', (did,))
    def kb_unembedded(self, model: str, cid=None, limit: int = 64) -> list:
        """Passages with no vector from `model` yet: what a first run after switching semantic search on, a changed
        model, or a reindex whose embedder was down still owes. [{'ChunkId', 'Text'}]"""
        w, p = (' AND d.ConnectorId=?', (cid,)) if cid else ('', ())
        return self._rows('SELECT c.ChunkId, c.Text FROM kb_chunk c JOIN kb_doc d ON d.DocId=c.DocId '
                          f'LEFT JOIN kb_vec v ON v.ChunkId=c.ChunkId AND v.Model=? WHERE v.ChunkId IS NULL{w} ORDER BY c.ChunkId LIMIT ?',
                          (model, *p, limit))
    def kb_vec_put(self, model: str, items: list):
        """items: [(ChunkId, blob)]. One transaction; a passage that already has a vector (another model's) is replaced."""
        with self.lock:
            self.cx.executemany('INSERT OR REPLACE INTO kb_vec (ChunkId, Model, Dim, Vec) VALUES (?,?,?,?)',
                                [(i, model, len(b) // 4, b) for i, b in items])
            self.cx.commit(); self._writes += 1
    def text_vecs(self, model: str, keys: list) -> dict:
        """{Key: (Hash, blob)} for the keys embedded with `model` (textsim.vectors)."""
        out = {}
        for i in range(0, len(keys), 500):
            part = list(keys[i:i + 500])
            with self.lock:
                out.update({k: (h, v) for k, h, v in self.cx.execute(
                    f"SELECT Key, Hash, Vec FROM text_vec WHERE Model=? AND Key IN ({','.join('?' * len(part))})", (model, *part)).fetchall()})
        return out
    def text_vec_put(self, model: str, items: list):
        """items: [(Key, Hash, blob)], one transaction."""
        with self.lock:
            self.cx.executemany('INSERT OR REPLACE INTO text_vec (Key, Model, Hash, Dim, Vec) VALUES (?,?,?,?,?)',
                                [(k, model, h, len(b) // 4, b) for k, h, b in items])
            self.cx.commit(); self._writes += 1
    def kb_vectors(self, model: str, cid=None) -> list:
        """[(ChunkId, Dim, blob)] for every passage embedded with `model` - the whole set, because the search is a brute-force scan."""
        w, p = (' JOIN kb_chunk c ON c.ChunkId=v.ChunkId JOIN kb_doc d ON d.DocId=c.DocId WHERE v.Model=? AND d.ConnectorId=?', (model, cid)) \
            if cid else (' WHERE v.Model=?', (model,))
        with self.lock: return [tuple(r) for r in self.cx.execute(f'SELECT v.ChunkId, v.Dim, v.Vec FROM kb_vec v{w}', p).fetchall()]
    def kb_chunk_hits(self, chunk_ids: list) -> list:
        """The kb_search hit shape for these passages, in the order given (no snippet: nothing matched a WORD)."""
        if not chunk_ids: return []
        rows = {r['ChunkId']: r for r in self._rows(
            'SELECT c.ChunkId, d.DocId, d.Name, d.Path, d.Source, d.Modified, c.Seq, c.Text FROM kb_chunk c JOIN kb_doc d ON d.DocId=c.DocId '
            f'WHERE c.ChunkId IN ({",".join("?" * len(chunk_ids))})', tuple(chunk_ids))}
        return [{'doc_id': r['DocId'], 'name': r['Name'], 'path': r['Path'], 'source': r['Source'], 'modified': r['Modified'] or '',
                 'seq': r['Seq'], 'score': 0.0, 'snippet': '', 'text': r['Text'] or ''} for i in chunk_ids if (r := rows.get(i))]
    def kb_prune(self, cid, source, keep: set) -> int:
        """Drop the documents of one source that a fresh walk did not see - deleted files leave the index."""
        gone = [r for r in self._rows('SELECT DocId, Path FROM kb_doc WHERE ConnectorId=? AND Source=?', (cid, source)) if r['Path'] not in keep]
        with self.lock:
            cur = self.cx.cursor()
            for r in gone: self._kb_drop(cur, r['DocId'])
            if gone: self.cx.commit(); self._writes += 1
        return len(gone)
    def kb_clear(self, cid=None):
        with self.lock:
            cur = self.cx.cursor()
            for r in cur.execute('SELECT DocId FROM kb_doc' + (' WHERE ConnectorId=?' if cid else ''), (cid,) if cid else ()).fetchall():
                self._kb_drop(cur, r[0])
            self.cx.commit(); self._writes += 1
    def kb_count(self, cid=None) -> dict:
        w, p = (' WHERE ConnectorId=?', (cid,)) if cid else ('', ())
        return {'docs': self._one(f'SELECT COUNT(*) n FROM kb_doc{w}', p)['n'],
                'chunks': self._one(f'SELECT COUNT(*) n FROM kb_chunk c' + (' JOIN kb_doc d ON d.DocId=c.DocId' + w if cid else ''), p)['n']}
    def kb_docs(self, cid=None) -> list:
        w, p = (' WHERE ConnectorId=?', (cid,)) if cid else ('', ())
        return self._rows(f'SELECT * FROM kb_doc{w} ORDER BY Source, Path', p)
    def _open_msg_fts(self) -> bool:
        """The message index, and on the first open its backfill (a one-off: ~10k mails is a second or two)."""
        try:
            fresh = not self.cx.execute("SELECT 1 FROM sqlite_master WHERE name='message_fts'").fetchone()
            self.cx.execute(MSG_FTS)
            for sql in MSG_FTS_TRIGGERS: self.cx.execute(sql)
            if fresh: self.cx.execute("INSERT INTO message_fts(message_fts) VALUES('rebuild')")
            return True
        except sqlite3.OperationalError as e:
            logger.warning(f'message search index unavailable - the timeline search scans instead: {e}'); return False
    def message_search(self, words, sender='', days=3650, limit=400, loose=False, prefix=False) -> list:
        """MessageIds, best match first: every word somewhere in the subject, the sender or the body,
        over the whole history. None when there is no index - the caller scans the feed instead.
        `loose`: ANY of the words, each as a prefix (the caller scores how many each row has).
        `prefix`: every word, each as a prefix - the search box, which matches while a word is still being typed."""
        if not getattr(self, 'msg_fts', False): return None
        terms = (' OR ' if loose else ' ').join('"' + w.replace('"', '') + '"' + ('*' if loose or prefix else '') for w in words if w.replace('"', ''))
        where, p = ["m.CreatedAt >= datetime('now', 'localtime', ?)"], [f'-{int(days)} days']
        if sender:
            where.append("lower(IFNULL(m.FromName,'') || ' ' || IFNULL(m.FromEmail,'')) LIKE ?"); p.append(f'%{sender.lower()}%')
        if terms:
            q = (f"SELECT m.MessageId FROM message_fts JOIN message m ON m.MessageId=message_fts.rowid "
                 f"WHERE message_fts MATCH ? AND {' AND '.join(where)} ORDER BY bm25(message_fts) LIMIT ?")
            return [r['MessageId'] for r in self._rows(q, (terms, *p, limit))]
        return [r['MessageId'] for r in self._rows(f"SELECT m.MessageId FROM message m WHERE {' AND '.join(where)} "
                                                   'ORDER BY m.SentAt DESC LIMIT ?', (*p, limit))]
    def kb_search(self, fts_query: str, limit: int = 8, cid=None) -> list:
        """Passages ranked by bm25 (FTS5) with a snippet around the matches; one hit per document,
        the best passage of each. `fts_query` is FTS5 syntax - knowledge._query builds it safely."""
        if not fts_query: return []
        w, p = (' AND d.ConnectorId=?', (cid,)) if cid else ('', ())
        if self.kb_fts:
            q = ('SELECT d.DocId, d.Name, d.Path, d.Source, d.Modified, c.Seq, bm25(kb_fts) score, '
                 "snippet(kb_fts, 0, '[', ']', ' … ', 48) snip, c.Text text FROM kb_fts JOIN kb_chunk c ON c.ChunkId=kb_fts.ChunkId "
                 f'JOIN kb_doc d ON d.DocId=c.DocId WHERE kb_fts MATCH ?{w} ORDER BY score LIMIT ?')
            rows = self._rows(q, (fts_query, *p, limit * 4))
        else:
            words = [t.strip('"') for t in fts_query.split(' OR ') if t.strip('"')]
            like = ' OR '.join('c.Text LIKE ?' for _ in words)
            rows = self._rows('SELECT d.DocId, d.Name, d.Path, d.Source, d.Modified, c.Seq, 0 score, substr(c.Text, 1, 400) snip, c.Text text '
                              f'FROM kb_chunk c JOIN kb_doc d ON d.DocId=c.DocId WHERE ({like}){w} LIMIT ?',
                              (*[f'%{x}%' for x in words], *p, limit * 4))
        out, seen = [], set()
        for r in rows:
            if r['DocId'] in seen: continue
            seen.add(r['DocId'])
            out.append({'doc_id': r['DocId'], 'name': r['Name'], 'path': r['Path'], 'source': r['Source'], 'modified': r['Modified'] or '',
                        'seq': r['Seq'], 'score': round(-float(r['score']), 3), 'snippet': ' '.join(str(r['snip'] or '').split()),
                        'text': r['text'] or ''})
            if len(out) >= limit: break
        return out

    # ── the handbook (handbook.py): what the agents worked out about this company, by topic ──
    # LIKE, not FTS5. The knowledge base indexes thousands of documents and needs bm25; the
    # handbook is hundreds of short posts an agent WROTE, and a second virtual table for that is
    # infrastructure nobody asked for. Ranking is what the caller asks for: recency, or score.
    def lore_put(self, p: dict, actor: str = 'agent') -> int:
        """Write a post, or UPDATE the one that already says this. `Sig` is what makes a fact
        durable rather than repeated: the same agent working the same ground twice writes the
        same signature, and the second run refreshes the post instead of adding a duplicate."""
        sig = (p.get('Sig') or '').strip()
        have = self._one('SELECT LoreId FROM lore WHERE Sig=? AND Sig<>""', (sig,)) if sig else None
        if have:
            self._exec('UPDATE lore SET Topic=?, Title=?, Body=?, Author=?, Kind=?, TaskId=?, Cwd=?, UpdatedAt=? WHERE LoreId=?',
                       (p.get('Topic'), p.get('Title'), p.get('Body'), p.get('Author') or actor, p.get('Kind') or 'howto',
                        p.get('TaskId'), p.get('Cwd'), _now(), have['LoreId']))
            return have['LoreId']
        return self._insert('lore', {**p, 'Author': p.get('Author') or actor, 'Sig': sig},
                            ('Topic', 'Title', 'Body', 'Author', 'Kind', 'TaskId', 'Cwd', 'Score', 'Status', 'Sig'),
                            {'CreatedAt': _now(), 'UpdatedAt': _now()})
    def lore_get(self, lid): return self._one('SELECT * FROM lore WHERE LoreId=?', (lid,))
    def lore_topics(self) -> list:
        return self._rows("SELECT Topic, COUNT(*) n, MAX(UpdatedAt) last FROM lore WHERE Status='live' "
                          'AND IFNULL(Topic,"")<>"" GROUP BY Topic ORDER BY n DESC, Topic')
    LORE_POOL = 500         # the posts a query is ranked among: the best-scored and newest

    def lore_posts(self, topic=None, q=None, limit=50, sort='new', status='live', kind=None) -> list:
        """The posts, filtered by status, topic and kind. With `q`, the ones that MEAN what it is about, best first - ranked by
        embeddings (textsim), `Hits` their similarity. A stopword list and a count of shared words ranked them once (the owner,
        2026-10-28: no hard-coded words). With no embedder a query is FOUND, literally: posts that carry it whole."""
        w = ((["l.Status='live'"] if status == 'live' else ["l.Status<>'live'"])
             + (['l.Topic=?'] if topic else []) + (['l.Kind=?'] if kind else []))
        p = ([topic] if topic else []) + ([kind] if kind else [])
        # Agreement is the strongest value signal; discussion breaks ties. The same ordering
        # feeds the Hub tab and handbook.block(), so validated entries reach later agents first.
        order = 'l.Score DESC, Comments DESC, l.UpdatedAt DESC' if sort == 'top' or q else 'l.UpdatedAt DESC'
        rows = self._rows(f'SELECT l.*, 0 Hits, (SELECT COUNT(*) FROM lore_comment WHERE LoreId=l.LoreId) Comments '
                          f'FROM lore l WHERE {" AND ".join(w)} ORDER BY {order} LIMIT ?', (*p, self.LORE_POOL if q else int(limit)))
        q = ' '.join(str(q or '').split())
        if not q: return rows
        from . import textsim
        text = lambda r: f"{r.get('Title') or ''}\n{r.get('Topic') or ''}\n{str(r.get('Body') or '')[:1500]}"
        got = textsim.rank(self, q, [(f"lore:{r['LoreId']}", text(r)) for r in rows], int(limit))
        if got is None: return [r for r in rows if q.lower() in ' '.join(text(r).split()).lower()][:int(limit)]
        by = {f"lore:{r['LoreId']}": r for r in rows}
        return [{**by[k], 'Hits': round(sim, 4)} for k, sim in got]
    def lore_vote(self, lid, delta: int, actor: str = 'owner') -> int:
        """One vote per voter, forum-style: voting again REPLACES your vote rather than stacking it,
        so an agent that meets the same entry in ten sessions moves it one step, not ten. The Score
        column is the sum, kept denormalised because lore_posts ranks on it. Returns the new score."""
        with self.lock:
            self.cx.execute('INSERT OR REPLACE INTO lore_vote (LoreId, Actor, Delta, At) VALUES (?,?,?,?)',
                            (lid, str(actor or 'owner'), int(delta), _now()))
            self.cx.execute('UPDATE lore SET Score=(SELECT IFNULL(SUM(Delta),0) FROM lore_vote WHERE LoreId=?) WHERE LoreId=?', (lid, lid))
            self.cx.commit(); self._writes += 1
        return int((self.lore_get(lid) or {}).get('Score') or 0)
    def lore_votes(self, lid) -> list:
        return self._rows('SELECT Actor, Delta, At FROM lore_vote WHERE LoreId=? ORDER BY At', (lid,))
    def lore_retire(self, lid, actor='owner', status='retired'):
        """Wrong, or no longer true. Retired rather than deleted: the post is how somebody once
        understood this, and a handbook that silently loses entries cannot be trusted either.
        `status` says why: 'retired' by hand, 'downvoted' by the vote falling below zero."""
        self._exec("UPDATE lore SET Status=?, UpdatedAt=? WHERE LoreId=?", (status, _now(), lid))
    def lore_restore(self, lid):
        self._exec("UPDATE lore SET Status='live', UpdatedAt=? WHERE LoreId=?", (_now(), lid))
    def lore_comments(self, lid) -> list:
        return self._rows('SELECT * FROM lore_comment WHERE LoreId=? ORDER BY CommentId', (lid,))
    def lore_comment(self, lid, body, author='owner') -> int:
        cid = self._insert('lore_comment', {'LoreId': lid, 'Body': body, 'Author': author},
                           ('LoreId', 'Body', 'Author'), {'CreatedAt': _now()})
        self._exec('UPDATE lore SET UpdatedAt=? WHERE LoreId=?', (_now(), lid))
        return cid
    def lore_count(self) -> dict:
        return {'posts': self._one("SELECT COUNT(*) n FROM lore WHERE Status='live'")['n'],
                'topics': self._one("SELECT COUNT(DISTINCT Topic) n FROM lore WHERE Status='live'")['n'],
                'comments': self._one('SELECT COUNT(*) n FROM lore_comment')['n']}

    # ── the semantic layer (semantic.py): what a business number MEANS in this company's books ──
    # A metric is a definition plus the known-good numbers it was proved against. It is only
    # 'verified' while every fixture still reconciles, so a chart-of-accounts change demotes it
    # rather than quietly returning a wrong number.
    METRIC_COLS = ('Name', 'Label', 'Grain', 'Definition', 'SpecJson', 'Notes', 'Status', 'ConnectorId', 'Skill')
    def list_metrics(self, status=None) -> list:
        w, p = (' WHERE Status=?', (status,)) if status else ('', ())
        return self._rows(f'SELECT * FROM metric{w} ORDER BY Name', p)
    def get_metric(self, mid: int): return self._one('SELECT * FROM metric WHERE MetricId=?', (mid,))
    def metric_by_name(self, name: str): return self._one('SELECT * FROM metric WHERE Name=?', (str(name or '').strip().lower(),))
    def save_metric(self, fields: dict, actor: str) -> int:
        name = str(fields.get('Name') or '').strip().lower()
        if not name: raise ValueError('a metric needs a name')
        old = self.metric_by_name(name)
        if old:
            self.update_metric(old['MetricId'], {k: v for k, v in fields.items() if k != 'Name'}, actor)
            return old['MetricId']
        mid = self._insert('metric', {**fields, 'Name': name}, self.METRIC_COLS,
                           {'CreatedBy': actor, 'CreatedAt': _now(), 'UpdatedBy': actor, 'UpdatedAt': _now()})
        self._bump_snapshots()
        return mid
    def update_metric(self, mid: int, fields: dict, actor: str):
        d = {k: v for k, v in fields.items() if k in self.METRIC_COLS + ('LastCheckAt', 'LastCheckPass', 'LastCheckNote') and v is not None}
        if not d: return
        d |= {'UpdatedBy': actor, 'UpdatedAt': _now()}
        self._exec(f"UPDATE metric SET {','.join(f'{k}=?' for k in d)} WHERE MetricId=?", [*d.values(), mid])
        self._bump_snapshots()
    def delete_metric(self, mid: int):
        self._exec('DELETE FROM metric_fixture WHERE MetricId=?', (mid,))
        self._exec('DELETE FROM metric WHERE MetricId=?', (mid,))
        self._bump_snapshots()

    def list_fixtures(self, mid: int) -> list:
        return self._rows('SELECT * FROM metric_fixture WHERE MetricId=? ORDER BY Scope, Period', (mid,))
    def add_fixture(self, mid: int, fields: dict, actor: str) -> int:
        fid = self._insert('metric_fixture', {**fields, 'MetricId': mid},
                           ('MetricId', 'Scope', 'Period', 'Expected', 'Tolerance', 'Source'),
                           {'CreatedBy': actor, 'CreatedAt': _now()})
        self._bump_snapshots()
        return fid
    def record_fixture(self, fid: int, got, passed: bool, error: str = None):
        self._exec('UPDATE metric_fixture SET LastGot=?, LastAt=?, LastPass=?, LastError=? WHERE FixtureId=?',
                   (got, _now(), 1 if passed else 0, error, fid))
    def delete_fixture(self, fid: int):
        self._exec('DELETE FROM metric_fixture WHERE FixtureId=?', (fid,)); self._bump_snapshots()


class MemoryStore(SQLiteStore):
    """Tests/demo: the same store on an in-memory database."""
    def __init__(self): super().__init__(':memory:')
