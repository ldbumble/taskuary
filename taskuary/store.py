"""Storage: one small dict-shaped contract, two bindings - SQLite (stdlib, the local-first
default) and in-memory (tests/demo). Every mutation is meant to be paired with .audit();
the audit log is a Buzz-style tamper-evident hash chain (each row hashes the previous).
"""
import contextlib, hashlib, json, re, sqlite3, threading
from datetime import datetime, timedelta

GENESIS = '0' * 64
TASK_COLS = ('Title', 'Summary', 'Kind', 'Status', 'Priority', 'Assignee', 'Source', 'SourceRef', 'Tags')
MSG_COLS = ('TaskId', 'ExternalId', 'ConversationId', 'Channel', 'SourceName', 'Subject',
            'FromName', 'FromEmail', 'SentAt', 'BodyText', 'SourceLink', 'Status', 'Direction', 'RecipientsJson')
RUN_COLS = ('Status', 'TraceJson', 'Result', 'LastError', 'SessionId', 'DiffText')
REVIEW_COLS = ('TaskId', 'MessageId', 'RunId', 'Kind', 'DraftText', 'FinalText', 'Status', 'Reason', 'Deliver')
POLICY_COLS = ('Name', 'Kind', 'Pattern', 'Action', 'Reason', 'SortOrder', 'Active')
SOURCE_COLS = ('Channel', 'Address', 'Owner', 'ConnectorId', 'Active', 'ConfigJson')
MEMORY_COLS = ('Scope', 'ScopeKey', 'Note', 'Source', 'Active', 'CreatedBy')
ATT_COLS = ('MessageId', 'ExternalId', 'Name', 'ContentType', 'Size', 'ContentId', 'Inline', 'Path')

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
                'LEFT JOIN message m ON m.MessageId=rv.MessageId')
_NOT_ORPHAN = '(rv.TaskId IS NULL OR t.TaskId IS NOT NULL)'
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


def task_ref(task_id): return f'TQ-{int(task_id):04d}'
def _now(): return datetime.now().isoformat(sep=' ', timespec='seconds')

# conversation ids that name a CHAT rather than a topic - one id for every message ever exchanged
# there, so an owner verdict on it covers an episode, not the relationship (owner_verdict_on_thread)
CHAT_PREFIXES = ('teams:', 'slack:', 'telegram:', 'whatsapp:', 'imessage:')
CHAT_VERDICT_HOURS = 24      # a chat ruling covers the SAME SENDER'S burst, not the room for three days

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
  CreatedBy TEXT, CreatedAt TEXT, UpdatedBy TEXT, UpdatedAt TEXT, ClosedAt TEXT);
CREATE TABLE IF NOT EXISTS message (MessageId INTEGER PRIMARY KEY, TaskId INTEGER, ExternalId TEXT,
  ConversationId TEXT, Channel TEXT, SourceName TEXT, Subject TEXT, FromName TEXT, FromEmail TEXT,
  SentAt TEXT, BodyText TEXT, SourceLink TEXT, Status TEXT DEFAULT 'routed', CreatedAt TEXT,
  Direction TEXT DEFAULT 'in', RecipientsJson TEXT);
CREATE TABLE IF NOT EXISTS attachment (AttachmentId INTEGER PRIMARY KEY, MessageId INTEGER, ExternalId TEXT,
  Name TEXT, ContentType TEXT, Size INTEGER, ContentId TEXT, Inline INTEGER DEFAULT 0, Path TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS transcript (TranscriptId INTEGER PRIMARY KEY, TaskId INTEGER, Sid TEXT,
  Agent TEXT, Cwd TEXT, Text TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS route (RouteId INTEGER PRIMARY KEY, MessageId INTEGER, TaskId INTEGER,
  Decision TEXT, Score REAL, Reason TEXT, CandidatesJson TEXT, RoutedBy TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS comment (CommentId INTEGER PRIMARY KEY, TaskId INTEGER, Actor TEXT,
  ActorType TEXT, Body TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS audit (Id INTEGER PRIMARY KEY, EntityType TEXT, EntityId INTEGER,
  Action TEXT, Actor TEXT, ActorType TEXT, RunId INTEGER, Detail TEXT, PrevHash TEXT, RowHash TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS agent (AgentId INTEGER PRIMARY KEY, Name TEXT UNIQUE, Kind TEXT,
  Runner TEXT, Config TEXT, Active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS run (RunId INTEGER PRIMARY KEY, TaskId INTEGER, AgentName TEXT,
  Status TEXT DEFAULT 'running', Instruction TEXT, TraceJson TEXT, Result TEXT, LastError TEXT,
  SessionId TEXT, DiffText TEXT, DispatchedBy TEXT, StartedAt TEXT, UpdatedAt TEXT, FinishedAt TEXT);
CREATE TABLE IF NOT EXISTS review (ReviewId INTEGER PRIMARY KEY, TaskId INTEGER, MessageId INTEGER,
  RunId INTEGER, Kind TEXT, DraftText TEXT, FinalText TEXT, Status TEXT DEFAULT 'pending',
  Reason TEXT, DecidedBy TEXT, DecidedAt TEXT, DecideNote TEXT, CreatedAt TEXT, Deliver TEXT);
CREATE TABLE IF NOT EXISTS policy (PolicyId INTEGER PRIMARY KEY, Name TEXT, Kind TEXT, Pattern TEXT,
  Action TEXT, Reason TEXT, SortOrder INTEGER DEFAULT 100, Active INTEGER DEFAULT 1, CreatedBy TEXT);
CREATE TABLE IF NOT EXISTS source (SourceId INTEGER PRIMARY KEY, Channel TEXT, Address TEXT,
  Owner TEXT, ConnectorId INTEGER, Active INTEGER DEFAULT 1, ConfigJson TEXT, LastPolledAt TEXT);
CREATE TABLE IF NOT EXISTS connector (ConnectorId INTEGER PRIMARY KEY, Type TEXT UNIQUE, Name TEXT,
  ConfigJson TEXT, Secret TEXT, Active INTEGER DEFAULT 0, LastSyncAt TEXT, LastError TEXT, Roles TEXT,
  Scope TEXT);
CREATE TABLE IF NOT EXISTS setting (Name TEXT PRIMARY KEY, Value TEXT, Description TEXT, UpdatedBy TEXT);
CREATE TABLE IF NOT EXISTS memory (MemoryId INTEGER PRIMARY KEY, Scope TEXT, ScopeKey TEXT, Note TEXT,
  Source TEXT, Active INTEGER DEFAULT 1, CreatedBy TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS doc (Name TEXT PRIMARY KEY, Content TEXT, UpdatedBy TEXT, UpdatedAt TEXT);
CREATE TABLE IF NOT EXISTS dispatchq (QId INTEGER PRIMARY KEY, TaskId INTEGER, BehindTaskId INTEGER,
  Agent TEXT, Reason TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS waitroom (WId INTEGER PRIMARY KEY, TaskId INTEGER, Note TEXT, CreatedBy TEXT,
  CreatedAt TEXT, DeliveredAt TEXT, How TEXT);
CREATE TABLE IF NOT EXISTS learned_history (Id INTEGER PRIMARY KEY, Key TEXT, Text TEXT, Status TEXT, Score INTEGER,
  Ev TEXT, Action TEXT, Actor TEXT, At TEXT);
"""

# CREATE TABLE IF NOT EXISTS is a no-op on an existing db; these are not. IF NOT EXISTS
# so a second open (desktop + web, or a restart) does not raise. Named so EXPLAIN QUERY
# PLAN tests can see them, and so a DROP INDEX in a test is not a mystery.
INDEXES = (
    'CREATE INDEX IF NOT EXISTS idx_message_external ON message(ExternalId)',
    'CREATE INDEX IF NOT EXISTS idx_message_conversation ON message(ConversationId, SentAt)',
    'CREATE INDEX IF NOT EXISTS idx_message_task ON message(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_message_status ON message(Status)',
    'CREATE INDEX IF NOT EXISTS idx_message_sent ON message(SentAt, MessageId)',
    'CREATE INDEX IF NOT EXISTS idx_message_created ON message(CreatedAt)',
    'CREATE INDEX IF NOT EXISTS idx_message_from ON message(FromEmail)',
    'CREATE INDEX IF NOT EXISTS idx_route_message ON route(MessageId, RouteId)',
    'CREATE INDEX IF NOT EXISTS idx_route_task ON route(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_review_message ON review(MessageId, ReviewId)',
    'CREATE INDEX IF NOT EXISTS idx_review_task ON review(TaskId, Status)',
    'CREATE INDEX IF NOT EXISTS idx_run_task ON run(TaskId, Status)',
    'CREATE INDEX IF NOT EXISTS idx_attachment_message ON attachment(MessageId)',
    'CREATE INDEX IF NOT EXISTS idx_comment_task ON comment(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit(EntityType, EntityId)',
    'CREATE INDEX IF NOT EXISTS idx_dispatchq_task ON dispatchq(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_waitroom_task ON waitroom(TaskId, DeliveredAt)',
)

# Out of the box Taskuary WORKS the mail: a job goes to the coding agent, a question gets a
# draft. Both stop short of anything leaving the building - a draft waits for you to send it,
# and a session is one you watch - so ON is a safe default and OFF was just a slower start.
DEFAULT_SETTINGS = {'default_action': 'draft', 'auto_draft_enabled': '1', 'attach_threshold': '0.42',
                    'feed_days': '14', 'intent_classify_enabled': '1', 'coder_auto_enabled': '1',
                    'auto_sessions': '4',           # unattended agent sessions at once; the rest queue
                    'triage_ai': '',      # '' = first active AI connector | connector:<type> | cli:<agent>
                    'startup_sync_days': '3',       # backfill window when the app starts: catch what arrived while it was shut
                    # minutes between background polls while the app is OPEN. The Timeline said
                    # "auto-syncs every 10 min" for a long time while the only clock was a
                    # setInterval inside its own tab - see server.poll_forever. 0 = off.
                    'poll_minutes': '10',
                    'vision_enabled': '1',          # send attached images to the AI, when the model can see
                    'report_images_enabled': '1',   # reports hand back a chart, and draw it in the body
                    # the ONE copy of your name. The docs say {{owner}} / {{owner_first}} /
                    # {{owner_email}} and are filled in when an AI reads them - see store.doc().
                    'owner_name': '', 'owner_email': '',
                    # what gets pushed to notify-role channels: off | needs_me | all
                    'notify_level': 'needs_me',
                    # the agent raised its hand (a session parked at its prompt, or asked a question):
                    # a sound in the app and the browser's own desktop notification - each its own switch
                    'hand_sound': 'chime', 'hand_desktop': '1',
                    'calendar_enabled': '1',      # a reply about time reads the owner's calendar first
                    'waitroom_drip': '1',         # queued notes land one per stop (a funnel of prompts), not all at once
                    # which CLI agent works tasks when nothing names one - pickers list it first
                    'default_agent': 'coder',
                    # may agents open GitHub issues/tracker items for the work itself? Off by
                    # default: Taskuary is the tracker, and one issue per task is noise.
                    'agent_issues_enabled': '0',
                    # may agents push/deploy on their own? Off: commit locally, the owner pushes.
                    'agent_push_enabled': '0',
                    # LEARNED.md: distill the owner's verdicts (edited drafts, rejections,
                    # reclassifications) into a general style/responsibility profile - see learn.py
                    'learn_enabled': '1',
                    # when an inbound answer ATTACHES to a task whose agent session is live:
                    # ask = a one-click offer in the panel; auto = typed straight in; off = neither
                    'answer_to_agent': 'ask',
                    # replies in the notify chat decide pinged reviews (approve/reject/your text)
                    'phone_approvals': '0',
                    # which channels Taskuary drafts and sends replies on (csv). github also
                    # needs its card's 'Reply to issue/PR authors'; the read-only trackers
                    # can never carry one - see outbound.can_reply
                    'reply_channels': 'email,teams,slack,telegram,whatsapp,imessage,discord,github',
                    # watch the CI of a task's pull request and hand red builds back to the
                    # agent that wrote the code: off | watch (status only) | feedback
                    'ci_watch': 'off',
                    # how finished work leaves the machine: 'pr' opens a DRAFT pull request,
                    # 'direct' pushes the existing commits straight onto the default branch
                    # (your own repo, no review ceremony). Either way 'Agents may push' gates it.
                    'git_flow': 'pr',
                    # an agent may PROPOSE high-impact actions (open a PR, comment publicly,
                    # close an issue, run a tool); each lands in Review for approval
                    'proposals_enabled': '1',
                    # once the hub has READ something, say so at the source: mark the mail
                    # seen, the chat read. Off by default - the funnel is a reader, and a
                    # mailbox that empties its own bold rows surprises people. See mark_read()
                    'mark_read_enabled': '0',
                    # the zone timestamps are stamped in (blank = this machine's local). Setting
                    # it makes every displayed time wear its label (2:44 PM EDT) and keeps a
                    # browser in another zone reading the stamps correctly.
                    'timezone': ''}

# What a connection IS to the hub, independent of what it can technically do:
#   trigger - polled for inbound items; they land on the Timeline and go through triage,
#             which can open tasks and draft replies
#   feed    - polled and SHOWN on the Timeline, but never becomes work: no triage, no task,
#             no AI call. "I want to see new GitHub issues, not be assigned them."
#   report  - selectable as a scheduled report source (Reports tab)
#   tool    - the agents may read from / write to it (listed for them in SOUL.md)
#   notify  - the OUTBOUND direction: Taskuary pushes timeline events INTO this channel
#             (a Telegram/WhatsApp ping when something needs you) - see outbound.notify
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
                 # research reads the public web - a report source, and a tool an agent may use
                 'exa': 'report,tool', 'tavily': 'report,tool',
                 'firecrawl': 'report,tool', 'reader': 'report,tool',
                 # aws/azure: the per-OBJECT picker carries the intent (report by default,
                 # which polls nothing) - the card itself is just a connection and a tool
                 'aws': 'report,tool', 'azure': 'report,tool',
                 'jira': 'trigger', 'asana': 'trigger', 'monday': 'trigger',
                 'clickup': 'trigger', 'todoist': 'trigger',
                 'gitlab': 'trigger', 'azdo': 'trigger', 'linear': 'trigger', 'trello': 'trigger',
                 # notion edits are information, not assignments; discord is a chat channel
                 'notion': 'feed', 'discord': 'trigger,tool',
                 'sentry': 'trigger', 'pagerduty': 'trigger'}
ROLES = ('trigger', 'feed', 'report', 'tool', 'notify')

def roles_of(c) -> set: return {r for r in (c.get('Roles') or '').split(',') if r}


class SQLiteStore:
    """The local-first binding. One connection, a lock (sqlite + threads), rows as dicts."""

    def __init__(self, path):
        # timeout= is sqlite's lock wait in seconds; WAL below is what actually lets a
        # Timeline read proceed while a poll is writing. :memory: cannot WAL (it has
        # nowhere to put the -wal file), so tests keep the default journal.
        self.cx = sqlite3.connect(path, check_same_thread=False, timeout=5.0)
        self.cx.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        if path != ':memory:':
            self.cx.execute('PRAGMA journal_mode=WAL')
            self.cx.execute('PRAGMA synchronous=NORMAL')
        # milliseconds. connect(timeout=) is the same wait in seconds; both have to be
        # set because a second connection (desktop + web, or a stuck poll) otherwise
        # fails instantly with "database is locked" instead of waiting its turn.
        self.cx.execute('PRAGMA busy_timeout=5000')
        self._snap_hold = 0
        self._snap_cache = None
        self._writes = 0
        with self.lock:
            self.cx.executescript(SCHEMA)
            for ix in INDEXES:
                self.cx.execute(ix)
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
            # WHERE an approved outbound draft goes. A reply knows its recipient from the
            # message it answers; an outbound report has no such message, so the review has to
            # carry the address itself or approving it would have nowhere to send.
            rcols = {r[1] for r in self.cx.execute('PRAGMA table_info(review)')}
            if 'Deliver' not in rcols:
                self.cx.execute('ALTER TABLE review ADD COLUMN Deliver TEXT')
            qcols = {r[1] for r in self.cx.execute('PRAGMA table_info(dispatchq)')}
            for col, typ in (('Value', 'REAL'), ('Floor', 'REAL'), ('Why', 'TEXT')):    # rank.py: value-ordered queue
                if col not in qcols: self.cx.execute(f'ALTER TABLE dispatchq ADD COLUMN {col} {typ}')
            have = {r[1] for r in self.cx.execute('PRAGMA table_info(connector)')}
            if 'Roles' not in have: self.cx.execute('ALTER TABLE connector ADD COLUMN Roles TEXT')
            # left NULL on purpose: scopes.scope_of falls back to the type's default, so an
            # existing db keeps exactly the authority it had before the column existed
            if 'Scope' not in have: self.cx.execute('ALTER TABLE connector ADD COLUMN Scope TEXT')
            for k, v in DEFAULT_SETTINGS.items():
                self.cx.execute('INSERT OR IGNORE INTO setting (Name, Value) VALUES (?,?)', (k, v))
            for t, n in (('outlook', 'Outlook mail'), ('teams', 'Microsoft Teams'),
                         ('slack', 'Slack'), ('github', 'GitHub'),
                         ('anthropic', 'Anthropic API'), ('openai', 'OpenAI API'),
                         ('azure_openai', 'Azure OpenAI'), ('openrouter', 'OpenRouter'),
                         ('ollama', 'Local models (Ollama)'), ('mssql', 'Microsoft SQL Server'),
                         ('telegram', 'Telegram'), ('whatsapp', 'WhatsApp'),
                         ('imessage', 'Apple Messages'),
                         ('gmail', 'Gmail / Google Workspace'), ('imap', 'Any mailbox (IMAP)'),
                         ('winrm', 'Remote Windows (WinRM)'),
                         ('database', 'Any database (connection string)'),
                         ('aws', 'Amazon Web Services'), ('azure', 'Microsoft Azure'),
                         ('jira', 'Jira'), ('asana', 'Asana'), ('monday', 'Monday.com'),
                         ('clickup', 'ClickUp'), ('todoist', 'Todoist'),
                         ('gitlab', 'GitLab'), ('azdo', 'Azure DevOps'), ('linear', 'Linear'),
                         ('trello', 'Trello'), ('notion', 'Notion'), ('discord', 'Discord'),
                         ('sentry', 'Sentry'), ('pagerduty', 'PagerDuty'),
                         ('prometheus', 'Prometheus'), ('datadog', 'Datadog'),
                         ('intacct', 'Sage Intacct'),
                         ('exa', 'Exa search'), ('tavily', 'Tavily search'),
                         ('firecrawl', 'Firecrawl'), ('reader', 'Jina Reader')):
                self.cx.execute('INSERT OR IGNORE INTO connector (Type, Name, Roles) VALUES (?,?,?)',
                                (t, n, DEFAULT_ROLES.get(t, '')))
            for t, r in DEFAULT_ROLES.items():        # dbs from before roles existed
                self.cx.execute('UPDATE connector SET Roles=? WHERE Type=? AND Roles IS NULL', (r, t))
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
            for name in ('soul', 'coder', 'digest', 'learned', 'triage', 'style'):
                f = Path(__file__).parent / 'templates' / f'{name}.md'
                if f.exists():
                    txt = f.read_text(encoding='utf-8')
                    self.cx.execute('INSERT OR IGNORE INTO doc (Name, Content, UpdatedBy, UpdatedAt) VALUES (?,?,?,?)',
                                    (name, txt, 'template', _now()))
                    # a doc NOBODY ever touched keeps tracking the shipped template, so template
                    # improvements reach existing installs - the first edit (owner or machine)
                    # changes UpdatedBy and makes the document theirs, never overwritten again
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedAt=? WHERE Name=? AND UpdatedBy='template' AND Content<>?",
                                    (txt, _now(), name, txt))
            # the Morning digest ships as a real REPORT (reports.run_digest): the brief lands
            # on the Timeline, its prompt is edited on the Reports tab, and deleting the
            # source turns it off - the sentinel keeps a deletion deleted across restarts.
            # It is also the working demo of how reports work, on data every install has.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='digest_report_seeded'").fetchone():
                from .digest import PROMPT
                self.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                                ('report', 'Morning digest', 'template', 1,
                                 json.dumps({'type': 'digest', 'title': 'Morning digest', 'days': 3, 'every_minutes': 180,
                                             'ai_prompt': PROMPT})))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('digest_report_seeded', '1', 'template')")
            # ...and its sibling: the weekly 'what should you automate next' brief (toil.py) -
            # same deal: a real report, prompt on the Reports tab, deleting it turns it off
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='automate_report_seeded'").fetchone():
                from .toil import PROMPT as AUTOMATE_PROMPT
                self.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                                ('report', 'Automation ideas', 'template', 1,
                                 json.dumps({'type': 'automate', 'title': 'Automation ideas', 'days': 30,
                                             'cron': '0 8 * * 1', 'ai_prompt': AUTOMATE_PROMPT})))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('automate_report_seeded', '1', 'template')")
            # prompt heal: a Morning digest still running a SHIPPED instruction tracks the
            # current one (same deal the template docs get) - an owner-edited prompt is never touched
            from .digest import OLD_PROMPTS, PROMPT as DIGEST_PROMPT
            for sid_, cj in self.cx.execute("SELECT SourceId, ConfigJson FROM source WHERE Channel='report'").fetchall():
                try: c = json.loads(cj or '{}')
                except ValueError: continue
                if c.get('type') == 'digest' and c.get('ai_prompt') in OLD_PROMPTS:
                    c['ai_prompt'] = DIGEST_PROMPT
                    # a stock digest that never had a cadence set was daily by default; out of the
                    # box it is now every three hours with a link per task (owner-set cadences kept)
                    if not any(c.get(k) for k in ('cron', 'every_minutes', 'daily_at', 'on_startup')): c['every_minutes'] = 180
                    self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), sid_))
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
            # of the same kind on one task - keep the newest, supersede the rest
            self.cx.execute("""UPDATE review SET Status='superseded'
                               WHERE Status='pending' AND ReviewId NOT IN (
                                   SELECT MAX(ReviewId) FROM review WHERE Status='pending'
                                   GROUP BY TaskId, Kind)""")
            # escalation reviews are gone: they only ever came from the headless report contract
            # ('needs_you'), and a live session asks you IN the terminal. Old pending ones would
            # render as a reply draft with nothing to send, so they resolve on first open - the
            # task keeps its 'waiting' status, so nothing quietly stops needing you.
            self.cx.execute("UPDATE review SET Status='superseded' WHERE Status='pending' AND Kind='escalation'")
            self.cx.commit()

    def _rows(self, q, p=()):
        with self.lock: return [dict(r) for r in self.cx.execute(q, p).fetchall()]
    def _one(self, q, p=()):
        r = self._rows(q, p); return r[0] if r else None
    def _exec(self, q, p=()):
        with self.lock:
            cur = self.cx.execute(q, p); self.cx.commit(); self._writes += 1; return cur.lastrowid
    def _insert(self, table, fields, allowed, extra=None):
        d = {k: fields[k] for k in allowed if k in fields and fields[k] is not None} | (extra or {})
        cols = list(d)
        return self._exec(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
                          [d[c] for c in cols])

    # tasks
    def create_task(self, fields, actor):
        # TaskId is a rowid, and SQLite hands a DELETED one straight back to the next insert.
        # TQ-0034 was three different tasks in one morning: a refund thread at 08:19 (with a
        # live agent on it), deleted at 10:11, the id reused twice more by lunchtime - and the
        # orphaned session, still holding task_id 34, showed up as the agent working a report
        # it had never been given. A TQ-ref is an identity: it goes in prompts, in transcripts,
        # in pull requests. It must never name two different pieces of work.
        tid = self._insert('task', {**fields, 'TaskId': self._next_task_id()},
                            TASK_COLS + ('TaskId',), {'CreatedBy': actor, 'CreatedAt': _now()})
        self._bump_snapshots()
        return tid

    def _next_task_id(self) -> int:
        """One past the highest id ever ISSUED - not the highest still present. The audit log
        is the record of what was issued (its rows outlive the task, by design), so the two
        together survive a deleted tail that the table alone forgets."""
        live = self._one('SELECT MAX(TaskId) m FROM task')['m'] or 0
        ever = self._one("SELECT MAX(EntityId) m FROM audit WHERE EntityType='task'")['m'] or 0
        mark = int(self.get_settings().get('task_id_mark') or 0)
        nxt = max(live, ever, mark) + 1
        self._exec('INSERT INTO setting (Name, Value, UpdatedBy) VALUES (?,?,?) '
                   'ON CONFLICT(Name) DO UPDATE SET Value=excluded.Value', ('task_id_mark', str(nxt), 'store'))
        return nxt
    def update_task(self, task_id, fields, actor):
        cols = [c for c in TASK_COLS if c in fields]
        if not cols: return
        closed = ", ClosedAt='" + _now() + "'" if fields.get('Status') in ('done', 'dropped') else ''
        self._exec(f"UPDATE task SET {','.join(f'{c}=?' for c in cols)}, UpdatedBy=?, UpdatedAt=?{closed} WHERE TaskId=?",
                   [fields[c] for c in cols] + [actor, _now(), task_id])
        # closing a task IS the decision: its pending reviews (escalations, drafts) resolve
        # with it instead of haunting the Review queue for a task that's already handled
        if fields.get('Status') in ('done', 'dropped'):
            self._exec("UPDATE review SET Status='superseded', DecidedBy=?, DecidedAt=? "
                       "WHERE TaskId=? AND Status='pending'", (actor, _now(), task_id))
        self._bump_snapshots()
    def get_task(self, task_id): return self._one('SELECT * FROM task WHERE TaskId=?', (task_id,))
    def list_tasks(self, status=None, active_only=False):
        q = '''SELECT t.*, rv.Status ReviewStatus, rv.Kind ReviewKind,
                      rn.Status RunStatus, rn.AgentName RunAgent,
                      ho.Body HandoverNote
               FROM task t
               LEFT JOIN (
                   SELECT TaskId, Status, Kind FROM review
                   WHERE ReviewId IN (SELECT MAX(ReviewId) FROM review GROUP BY TaskId)
               ) rv ON rv.TaskId=t.TaskId
               LEFT JOIN (
                   SELECT TaskId, Status, AgentName FROM run
                   WHERE RunId IN (SELECT MAX(RunId) FROM run GROUP BY TaskId)
               ) rn ON rn.TaskId=t.TaskId
               LEFT JOIN (
                   SELECT TaskId, Body FROM comment
                   WHERE CommentId IN (
                       SELECT MAX(CommentId) FROM comment WHERE Body LIKE 'HANDOVER NOTE%' GROUP BY TaskId
                   )
               ) ho ON ho.TaskId=t.TaskId'''
        where, p = [], []
        if status:
            where.append('t.Status=?'); p.append(status)
        if active_only:
            # the Board's Done column is today only; older finished work lives on Tasks
            where.append("(t.Status IN ('open','in_progress','waiting') "
                         "OR (t.Status='done' AND IFNULL(t.ClosedAt, t.UpdatedAt) >= date('now','localtime')))")
        if where:
            q += ' WHERE ' + ' AND '.join(where)
        return self._rows(q + ' ORDER BY t.TaskId DESC', p)
    def delete_task(self, task_id):
        for q in ("UPDATE message SET TaskId=NULL, Status='filed' WHERE TaskId=?", 'UPDATE route SET TaskId=NULL WHERE TaskId=?',
                  'DELETE FROM review WHERE TaskId=?', 'DELETE FROM comment WHERE TaskId=?',
                  'DELETE FROM run WHERE TaskId=?', 'DELETE FROM task WHERE TaskId=?'):
            self._exec(q, (task_id,))
        self._bump_snapshots()
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
        self._snap_cache = None

    def snapshots(self):
        if self._snap_hold and self._snap_cache is not None:
            return self._snap_cache
        snaps = self._load_snapshots()
        if self._snap_hold:
            self._snap_cache = snaps
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
    def message_exists(self, external_id):
        return self._one('SELECT 1 x FROM message WHERE ExternalId=?', (external_id,)) is not None
    def add_message(self, fields):
        # normalized on the way IN, not only by a heal on the way past: one clock for the
        # timeline, and no row that can sort above its own future
        if fields.get('SentAt'): fields = {**fields, 'SentAt': norm_stamp(fields['SentAt'])}
        mid = self._insert('message', fields, MSG_COLS, {'CreatedAt': _now()})
        if fields.get('TaskId'):
            self._bump_snapshots()
        return mid
    def get_message(self, mid): return self._one('SELECT * FROM message WHERE MessageId=?', (mid,))
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

    def owner_verdict_on_thread(self, conversation_id, sent_at=None, sender: str = None) -> str:
        """The owner's own "this is not work" on an EARLIER message of this same conversation, if
        any - the route reason they left ('not ours - ...', 'not a task - ...', 'nothing to do - ...').
        The thread is the one key that needs no scope: whatever else the verdict was filed under
        (a sender, a topic, nothing), it was given about THIS conversation - and the verdict the
        owner gives most is the one that deliberately teaches nothing about anybody, so without
        this rule the same thread opened a task on every burst (six times for one Teams chat).

        A real conversation id only. The same-subject fallback thread_messages offers is good
        enough to ADVISE (others_on_thread) but not to decide: two mails that merely share a
        subject line are not proof the owner ruled on the second.

        A chat id is a whole ROOM (teams:<chat>, slack:<channel>), not a topic, so a verdict
        there covers one person's episode: the SAME SENDER'S next lines, for CHAT_VERDICT_HOURS.
        It never covers somebody else's ask - a "nothing to do" on Richard's "Thank you" silenced
        Ivan's request three days later in the same support chat (2026-08-27). An email thread
        is one topic for life, and stays ruled whoever writes."""
        if not conversation_id: return ''
        mids = [m['MessageId'] for m in self.thread_messages(conversation_id)]
        if not mids: return ''
        chat = conversation_id.startswith(CHAT_PREFIXES)
        rows = self._rows(f"SELECT r.Reason, r.CreatedAt, m.FromEmail, m.FromName FROM route r JOIN message m ON m.MessageId=r.MessageId "
                          f"WHERE r.MessageId IN ({','.join('?' * len(mids))}) AND r.Decision='ignore' AND r.RoutedBy='owner' "
                          "ORDER BY r.RouteId DESC" + ('' if chat else ' LIMIT 1'), tuple(mids))
        if not rows: return ''
        if not chat: return rows[0]['Reason'] or ''
        who = (sender or '').strip().lower()
        for r in rows:
            ruled = {(r['FromEmail'] or '').strip().lower(), (r['FromName'] or '').strip().lower()} - {''}
            if who and ruled and who not in ruled: continue          # a different person: their ask is their own
            try:
                given = datetime.fromisoformat(r['CreatedAt'])
                now = datetime.fromisoformat(norm_stamp(sent_at) or _now())
                if now - given > timedelta(hours=CHAT_VERDICT_HOURS): return ''
            except (TypeError, ValueError): pass
            return r['Reason'] or ''
        return ''
    def list_messages(self, task_id): return self._rows('SELECT * FROM message WHERE TaskId=? ORDER BY SentAt', (task_id,))
    def scan_messages(self, limit=20000):
        """Just enough of every message to re-run a policy over the history (bodies capped)."""
        return self._rows('SELECT MessageId, TaskId, FromEmail, Subject, Status, SentAt, substr(BodyText, 1, 2000) BodyText '
                          'FROM message ORDER BY MessageId DESC LIMIT ?', (limit,))
    def set_message_status(self, mid, status): self._exec('UPDATE message SET Status=? WHERE MessageId=?', (status, mid))
    def place_message(self, mid, task_id, status):
        """A row that was shown first and judged later lands where the judgement puts it (ingest.drain)."""
        self._exec('UPDATE message SET TaskId=?, Status=? WHERE MessageId=?', (task_id, status, mid))
        if task_id is not None:
            self._bump_snapshots()
    def pending_triage(self, limit=500):
        return self._rows("SELECT * FROM message WHERE Status='triaging' ORDER BY MessageId LIMIT ?", (limit,))
    def attach_message(self, mid, task_id):
        self._exec("UPDATE message SET TaskId=?, Status='routed' WHERE MessageId=?", (task_id, mid))
        self._bump_snapshots()
    # What was ON the mail: the screenshot of the spreadsheet, the invoice PDF. The bytes live on
    # disk (`Path`) - a database that grows by 8MB a mail is a database nobody backs up.
    def add_attachment(self, fields): return self._insert('attachment', fields, ATT_COLS, {'CreatedAt': _now()})
    def list_attachments(self, mid): return self._rows('SELECT * FROM attachment WHERE MessageId=? ORDER BY AttachmentId', (mid,))
    def get_attachment(self, aid): return self._one('SELECT * FROM attachment WHERE AttachmentId=?', (aid,))
    def attachment_exists(self, external_id):
        return self._one('SELECT 1 x FROM attachment WHERE ExternalId=?', (external_id,)) is not None
    # A pty is not storage: the session's readable transcript is written here when it ends, so
    # "Done - wrap it up" still works an hour later, on a task whose CLI has long since exited.
    def add_transcript(self, task_id, sid, text, agent=None, cwd=None):
        if not (text or '').strip(): return None
        self._exec('DELETE FROM transcript WHERE Sid=?', (sid,))      # one row per session, always the latest
        return self._exec('INSERT INTO transcript (TaskId,Sid,Agent,Cwd,Text,CreatedAt) VALUES (?,?,?,?,?,?)',
                          (task_id, sid, agent, cwd, text, _now()))
    def last_transcript(self, task_id):
        return self._one('SELECT * FROM transcript WHERE TaskId=? ORDER BY TranscriptId DESC LIMIT 1', (task_id,))

    def add_route(self, mid, tid, decision, score, reason, candidates, routed_by='router'):
        return self._exec('INSERT INTO route (MessageId,TaskId,Decision,Score,Reason,CandidatesJson,RoutedBy,CreatedAt) VALUES (?,?,?,?,?,?,?,?)',
                          (mid, tid, decision, score, reason, json.dumps(candidates), routed_by, _now()))
    def list_routes(self, task_id): return self._rows('SELECT * FROM route WHERE TaskId=? ORDER BY RouteId', (task_id,))
    def add_comment(self, task_id, actor, actor_type, body):
        return self._exec('INSERT INTO comment (TaskId,Actor,ActorType,Body,CreatedAt) VALUES (?,?,?,?,?)',
                          (task_id, actor, actor_type, body, _now()))
    def list_comments(self, task_id): return self._rows('SELECT * FROM comment WHERE TaskId=? ORDER BY CommentId', (task_id,))

    # audit chain
    def audit(self, et, eid, action, actor, actor_type='human', detail=None, run_id=None):
        """One row, linked to the one before it - and the read of "the one before it" and the write
        have to be the SAME critical section. They were two: _one took the lock, released it, then
        _exec took it again. So the poll thread and a click could both read the same last row and
        both insert, each pointing at the same parent - a FORK, which verification then reported as
        a broken chain. A tamper-evident log that breaks itself is worse than none: it makes a real
        tamper indistinguishable from its own noise. (Seen at ids 151/152 of a live database, both
        stamped the same second, both carrying the same PrevHash.)"""
        d = detail if isinstance(detail, str) or detail is None else json.dumps(detail, default=str)
        with self.lock:
            row = self.cx.execute('SELECT RowHash FROM audit ORDER BY Id DESC LIMIT 1').fetchone()
            prev = (row['RowHash'] if row and row['RowHash'] else None) or GENESIS
            rh = chain_hash(prev, _audit_payload(et, eid, action, actor, actor_type, run_id, d))
            self.cx.execute('INSERT INTO audit (EntityType,EntityId,Action,Actor,ActorType,RunId,Detail,PrevHash,RowHash,CreatedAt) VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (et, eid, action, actor, actor_type, run_id, d, prev, rh, _now()))
            self.cx.commit()
    def list_audit(self, et=None, eid=None, limit=200):
        if et: return self._rows('SELECT * FROM audit WHERE EntityType=? AND EntityId=? ORDER BY Id DESC LIMIT ?', (et, eid, limit))
        return self._rows('SELECT * FROM audit ORDER BY Id DESC LIMIT ?', (limit,))
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
        return self._exec('INSERT INTO run (TaskId,AgentName,Instruction,DispatchedBy,StartedAt) VALUES (?,?,?,?,?)',
                          (task_id, agent_name, instruction, by, _now()))
    def update_run(self, run_id, fields, finished=False):
        cols = [c for c in RUN_COLS if c in fields]
        fin = f", FinishedAt='{_now()}'" if finished else ''
        self._exec(f"UPDATE run SET {','.join(f'{c}=?' for c in cols)}, UpdatedAt=?{fin} WHERE RunId=?",
                   [fields[c] for c in cols] + [_now(), run_id])
    def get_run(self, run_id): return self._one('SELECT * FROM run WHERE RunId=?', (run_id,))
    def running_runs(self):
        return self._rows("SELECT * FROM run WHERE Status='running' ORDER BY RunId DESC")
    def list_runs(self, task_id): return self._rows('SELECT * FROM run WHERE TaskId=? ORDER BY RunId DESC', (task_id,))

    # the dispatch queue: tasks held back from auto-start because a running agent's work would
    # likely collide (BehindTaskId) or every session slot is busy (NULL) - see blackboard.drain
    def enqueue_dispatch(self, task_id, behind, agent, reason, value=None, why=None):
        if self._one('SELECT 1 x FROM dispatchq WHERE TaskId=?', (task_id,)): return None
        return self._exec('INSERT INTO dispatchq (TaskId,BehindTaskId,Agent,Reason,CreatedAt,Value,Floor,Why) VALUES (?,?,?,?,?,?,?,?)',
                          (task_id, behind, agent, reason, _now(), value, value, why))
    def queued_dispatches(self):
        # by value where one is set, arrival order among equals; an unranked (clear-mode) row
        # counts as the base value, so ranked and unranked queues interleave sensibly
        return self._rows('SELECT * FROM dispatchq ORDER BY COALESCE(Value, 0.5) DESC, QId')
    def set_dispatch_value(self, task_id, value, why=None, floor_=None):
        self._exec('UPDATE dispatchq SET Value=?, Why=COALESCE(?, Why), Floor=COALESCE(?, Floor) WHERE TaskId=?', (value, why, floor_, task_id))
    def clear_dispatch(self, task_id): self._exec('DELETE FROM dispatchq WHERE TaskId=?', (task_id,))

    # LEARNED.md's history (learnedgraph.py): every point a line gained or lost, and every line that died
    def add_learned_event(self, key, text, status, score, ev, action, actor):
        return self._exec('INSERT INTO learned_history (Key,Text,Status,Score,Ev,Action,Actor,At) VALUES (?,?,?,?,?,?,?,?)',
                          (key, text, status, score, ev, action, actor, _now()))
    def learned_history(self, key=None):
        return self._rows('SELECT * FROM learned_history' + (' WHERE Key=?' if key else '') + ' ORDER BY Id', (key,) if key else ())

    # the waiting room (waitroom.py): owner notes queued on a task while its agent works
    def add_waiting(self, task_id, note, actor):
        return self._exec('INSERT INTO waitroom (TaskId, Note, CreatedBy, CreatedAt) VALUES (?,?,?,?)', (task_id, note, actor, _now()))
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
    def add_review(self, fields): return self._insert('review', fields, REVIEW_COLS, {'CreatedAt': _now()})
    def get_review(self, rid): return self._one('SELECT * FROM review WHERE ReviewId=?', (rid,))
    def list_reviews(self, status=None):
        q = f'''SELECT rv.*, t.Title, m.Subject, m.FromEmail, m.Channel {_REVIEW_FROM}
                WHERE {_NOT_ORPHAN} AND {_VISIBLE_PENDING}'''
        return self._rows(q + (' AND rv.Status=?' if status else '') + ' ORDER BY rv.ReviewId DESC', (status,) if status else ())
    def decide_review(self, rid, status, final, by, note=None):
        self._exec('UPDATE review SET Status=?, FinalText=?, DecidedBy=?, DecidedAt=?, DecideNote=? WHERE ReviewId=?',
                   (status, final, by, _now(), note, rid))
    def pending_review(self, task_id, kind=None, live_only=True):
        """The task's live pending review, by the SAME visibility rule the queue uses: a draft the
        owner can no longer see is not one to re-draft into or treat as already-answered. Pass
        live_only=False only to reach a row deliberately - housekeeping, not the funnel."""
        q = f"SELECT rv.* {_REVIEW_FROM} WHERE rv.TaskId=? AND rv.Status='pending'"
        if kind:      q += ' AND rv.Kind=?'
        if live_only: q += f' AND {_NOT_ORPHAN} AND {_VISIBLE_PENDING}'
        return self._one(q + ' ORDER BY rv.ReviewId DESC LIMIT 1', (task_id, kind) if kind else (task_id,))
    def hold_reviews(self, task_id, reason=None):
        """Park this task's pending reply drafts while an agent works it. A draft written from the
        mail alone promises what the session has not found yet - and it sat in Review as if it
        were ready to send. Held leaves the queue; the wrap-up brings it back, rewritten."""
        with self.lock:
            cur = self.cx.execute("UPDATE review SET Status='held', Reason=COALESCE(?, Reason) "
                                  "WHERE TaskId=? AND Status='pending' AND Kind IN ('draft','draft_reply')",
                                  (reason, task_id))
            self.cx.commit()
            self._writes += 1
            return cur.rowcount                    # lastrowid is meaningless on an UPDATE
    def held_review(self, task_id, mid=None):
        q = "SELECT * FROM review WHERE TaskId=? AND Status='held'" + (' AND MessageId=?' if mid else '') + ' ORDER BY ReviewId DESC LIMIT 1'
        return self._one(q, (task_id, mid) if mid else (task_id,))
    def unhold_review(self, rid, reason=None):
        self._exec("UPDATE review SET Status='pending', Reason=COALESCE(?, Reason) WHERE ReviewId=?", (reason, rid))
    def update_review_reason(self, rid, reason, run_id=None):
        self._exec('UPDATE review SET Reason=?, RunId=COALESCE(?, RunId) WHERE ReviewId=?', (reason, run_id, rid))
    def update_review_draft(self, rid, draft, run_id):
        self._exec('UPDATE review SET DraftText=?, RunId=? WHERE ReviewId=?', (draft, run_id, rid))

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
    def list_sources(self, active_only=True):
        return self._rows('SELECT * FROM source' + (' WHERE Active=1' if active_only else ''))
    def save_source(self, fields, actor):
        sid = fields.get('SourceId')
        cols = [c for c in SOURCE_COLS if c in fields and fields[c] is not None]
        if sid:
            self._exec(f"UPDATE source SET {','.join(f'{c}=?' for c in cols)} WHERE SourceId=?", [fields[c] for c in cols] + [sid])
            return sid
        return self._insert('source', fields, SOURCE_COLS)
    def touch_source(self, sid): self._exec('UPDATE source SET LastPolledAt=? WHERE SourceId=?', (_now(), sid))
    def rewind_source(self, sid):
        """Forget this source's watermark, so the next poll reaches back over history instead
        of only forward. What a source that was OFF needs the moment it is switched on: the
        watermark kept marching while nothing was being read, and without this the items
        that existed before the switch are invisible forever."""
        self._exec('UPDATE source SET LastPolledAt=NULL WHERE SourceId=?', (sid,))
    def get_source(self, sid): return self._one('SELECT * FROM source WHERE SourceId=?', (sid,))
    def delete_source(self, sid): self._exec('DELETE FROM source WHERE SourceId=?', (sid,))
    def delete_agent(self, name): self._exec('DELETE FROM agent WHERE Name=?', (name,))

    # channel connectors (secrets are write-only: list/get never return them)
    _CONN_SAFE = "ConnectorId, Type, Name, ConfigJson, Active, Roles, Scope, LastSyncAt, LastError, (Secret IS NOT NULL AND Secret != '') HasSecret"
    def list_connectors(self): return self._rows(f'SELECT {self._CONN_SAFE} FROM connector ORDER BY ConnectorId')
    def get_connector(self, cid, with_secret=False):
        return self._one(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector WHERE ConnectorId=?", (cid,))
    def get_connector_by_type(self, ctype, with_secret=False):
        return self._one(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector WHERE Type=?", (ctype,))
    def save_connector(self, fields, actor):
        cid = fields.get('ConnectorId')
        cols = [c for c in ('Type', 'Name', 'ConfigJson', 'Secret', 'Active', 'Roles', 'Scope') if c in fields and fields[c] is not None]
        if cid:
            self._exec(f"UPDATE connector SET {','.join(f'{c}=?' for c in cols)} WHERE ConnectorId=?", [fields[c] for c in cols] + [cid])
            return cid
        return self._insert('connector', fields, ('Type', 'Name', 'ConfigJson', 'Secret', 'Active', 'Roles', 'Scope'))
    def reset_connector(self, cid):
        """'Remove connection': wipe creds/config/test state, deactivate it and its sources."""
        self._exec('UPDATE connector SET Secret=NULL, ConfigJson=NULL, Active=0, LastSyncAt=NULL, LastError=NULL, Scope=NULL WHERE ConnectorId=?', (cid,))
        self._exec('UPDATE source SET Active=0 WHERE ConnectorId=?', (cid,))
    def set_connector_config(self, cid, cfg: dict):
        """Just the config JSON - how the pollers keep their watermark (Telegram's update
        offset, the WhatsApp bridge's sequence) without touching secrets or roles."""
        self._exec('UPDATE connector SET ConfigJson=? WHERE ConnectorId=?', (json.dumps(cfg), cid))
    def touch_connector(self, cid, error=None):
        if error: self._exec('UPDATE connector SET LastError=? WHERE ConnectorId=?', (error[:500], cid))
        else: self._exec('UPDATE connector SET LastSyncAt=?, LastError=NULL WHERE ConnectorId=?', (_now(), cid))
    def get_settings(self): return {r['Name']: r['Value'] for r in self._rows('SELECT * FROM setting')}
    def list_settings(self): return self._rows('SELECT * FROM setting ORDER BY Name')
    def set_setting(self, name, value, actor):
        self._exec('INSERT INTO setting (Name, Value, UpdatedBy) VALUES (?,?,?) ON CONFLICT(Name) DO UPDATE SET Value=?, UpdatedBy=?',
                   (name, value, actor, value, actor))
    def known_sender(self, email, exclude_mid=None):
        """Has this address written before? exclude_mid: the message being judged, once it is
        already landed - otherwise every sender is 'known' by their own first mail."""
        if not email: return False
        return self._one('SELECT 1 x FROM message WHERE LOWER(FromEmail)=LOWER(?) AND MessageId<>? LIMIT 1',
                         (email, exclude_mid or 0)) is not None
    def add_memory(self, fields): return self._insert('memory', fields, MEMORY_COLS, {'CreatedAt': _now()})
    def list_memories(self, active_only=True):
        return self._rows('SELECT * FROM memory' + (' WHERE Active=1' if active_only else '') + ' ORDER BY MemoryId DESC')
    def set_memory_active(self, mid, active): self._exec('UPDATE memory SET Active=? WHERE MemoryId=?', (1 if active else 0, mid))
    def get_doc(self, name):
        """The document AS WRITTEN - placeholders and all. This is what the editor loads and saves;
        every consumer that feeds a doc to an AI wants `doc()` instead."""
        r = self._one('SELECT Content FROM doc WHERE Name=?', (name,)); return r['Content'] if r else None
    def doc_owner(self, name):
        """Who last wrote it - 'template' means nobody has, and the shipped text still flows in."""
        r = self._one('SELECT UpdatedBy FROM doc WHERE Name=?', (name,)); return r['UpdatedBy'] if r else None
    def save_doc(self, name, content, actor):
        self._exec('INSERT INTO doc (Name, Content, UpdatedBy, UpdatedAt) VALUES (?,?,?,?) ON CONFLICT(Name) DO UPDATE SET Content=?, UpdatedBy=?, UpdatedAt=?',
                   (name, content, actor, _now(), content, actor, _now()))
    def doc(self, name):
        """The document as the AI should read it: {{owner}} and friends filled in. The name used to
        be typed into six places across SOUL.md and three more in CODER.md, so changing it changed
        one of them - a doc that half calls you by name and half calls you John Smith."""
        return render_doc(self.get_doc(name) or '', self.owner())
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

    def github_replies_ok(self) -> bool:
        """May Taskuary answer issue/PR authors - which means posting a PUBLIC comment on the
        thread? Off by default: an open repository's drive-by authors should not each get a
        drafted reply, and before this flag the drafts were dead ends anyway (github had no
        send road at all). The switch lives on the GitHub connector card, with its siblings."""
        c = self.get_connector_by_type('github')
        try: return bool(json.loads((c or {}).get('ConfigJson') or '{}').get('reply_comments'))
        except ValueError: return False

    def owner(self) -> dict:
        """Who this hub belongs to, from one setting. Falls back to whatever SOUL.md says so an
        existing document keeps working before the owner has ever touched the field."""
        st = self.get_settings()
        soul_name = owner_from_soul(self.get_doc('soul') or '')
        if soul_name == 'John Smith': soul_name = None            # the shipped example, not a person
        name = (st.get('owner_name') or '').strip() or soul_name or 'the owner'
        email = (st.get('owner_email') or '').strip() or email_from_soul(self.get_doc('soul') or '')
        if email == 'john.smith@example.com': email = ''
        return {'owner': name, 'owner_first': name.split()[0] if name.split() else name, 'owner_email': email}

    # feed
    # One definition of "this is on me", used by the chip, the counter and the filter alike:
    # a decision is pending, OR the task is not finished and no agent is working it right
    # now. A task nobody is running is nobody's but yours.
    # The aliases (rv, t, rn) are the JOINs in feed() - one pass, not a correlated
    # subquery per row. The chip and the pending_only filter MUST keep using this
    # same expression or they will disagree.
    NEEDS_YOU = """(CASE WHEN rv.Status='pending'
                          OR (m.TaskId IS NOT NULL AND IFNULL(t.Status,'') NOT IN ('done', 'dropped')
                              AND rn.TaskId IS NULL)
                    THEN 1 ELSE 0 END)"""

    def feed(self, limit=100, days=14, pending_only=False, channel=None, offset=0, source=None):
        q = f'''SELECT m.MessageId, m.Channel, m.SourceName, m.Subject, m.FromName, m.FromEmail, m.SentAt,
                       substr(m.BodyText, 1, 4000) Preview, m.Status MsgStatus, m.SourceLink, m.TaskId, m.Direction,
                       t.Title, t.Status TaskStatus, t.Priority, t.Kind TaskKind, {self.NEEDS_YOU} NeedsYou,
                       IFNULL(ch.n, 0) ChainSize,
                       rt.Decision, rt.Reason RouteReason,
                       rv.ReviewId, rv.Status ReviewStatus, rv.Kind ReviewKind,
                       IFNULL(att.n, 0) Attachments
                FROM message m
                LEFT JOIN task t ON t.TaskId=m.TaskId
                LEFT JOIN (
                    SELECT MessageId, Decision, Reason FROM route
                    WHERE RouteId IN (SELECT MAX(RouteId) FROM route GROUP BY MessageId)
                ) rt ON rt.MessageId=m.MessageId
                LEFT JOIN (
                    SELECT MessageId, ReviewId, Status, Kind FROM review
                    WHERE ReviewId IN (SELECT MAX(ReviewId) FROM review GROUP BY MessageId)
                ) rv ON rv.MessageId=m.MessageId
                LEFT JOIN (
                    SELECT MessageId, COUNT(*) n FROM attachment GROUP BY MessageId
                ) att ON att.MessageId=m.MessageId
                LEFT JOIN (
                    SELECT TaskId, COUNT(*) n FROM message WHERE Status<>'context' GROUP BY TaskId
                ) ch ON ch.TaskId=m.TaskId
                LEFT JOIN (
                    SELECT DISTINCT TaskId FROM run WHERE Status='running'
                ) rn ON rn.TaskId=m.TaskId
                WHERE m.CreatedAt >= datetime('now', 'localtime', ?) AND m.Status NOT IN ('context', 'skipped') '''
        p = [f'-{int(days)} days']
        if pending_only: q += f' AND {self.NEEDS_YOU}=1'
        # channel accepts a csv so the UI can filter by a CATEGORY (messages = email,
        # teams, slack) without needing one request per channel
        if channel:
            chans = [c.strip() for c in str(channel).split(',') if c.strip()]
            q += f" AND m.Channel IN ({','.join('?' * len(chans))})"
            p += chans
        if source: q += ' AND m.SourceName=?'; p.append(source)   # e.g. one mailbox of several
        q += f' ORDER BY m.SentAt DESC, m.MessageId DESC LIMIT {int(limit)} OFFSET {int(offset)}'
        rows = self._rows(q, p)
        # the one-word tag every row wears (categories.py) - decided here, once, so the feed,
        # the digest and the task page never disagree about what a message is
        from .categories import category_of, team_domains_of
        team = team_domains_of(self.get_settings())
        for r in rows: r['Category'] = category_of(r, team)
        # NEEDS_YOU (SQL) only sees `run` rows; a coder in a LIVE pty session is working the task
        # just as much, and the row said "needs you - no agent is working it" over a running
        # console. Working carries the agent's name so the chip can say who.
        live = {r['TaskId']: r.get('AgentName') or 'agent' for r in self.running_runs()}
        try:
            from . import terminal as hub_term
            live.update({t['taskId']: t.get('agent') or t.get('label') or 'coder' for t in hub_term.live_sessions(tail=0) if t.get('taskId')})
        except Exception:
            pass                                   # no pty support here: runs alone decide
        for r in rows:
            if r.get('TaskId') in live and r.get('TaskStatus') not in ('done', 'dropped'):
                r['Working'] = live[r['TaskId']]
                if r.get('ReviewStatus') != 'pending': r['NeedsYou'] = 0
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

    def people(self, limit=60):
        """Everyone who has written to you lately - the hand-off picker's address book."""
        return self._rows("""SELECT FromEmail Email, MAX(FromName) Name, COUNT(*) N, MAX(SentAt) Last
                             FROM message WHERE FromEmail LIKE '%@%' AND Status<>'context'
                             GROUP BY LOWER(FromEmail) ORDER BY Last DESC LIMIT ?""", (int(limit),))

    def task_detail(self, task_id):
        t = self.get_task(task_id)
        if not t: return None
        msgs = self.list_messages(task_id)
        return {'task': t, 'ref': task_ref(task_id), 'messages': msgs,
                'attachments': [a for m in msgs for a in self.list_attachments(m['MessageId'])],
                'routes': self.list_routes(task_id), 'comments': self.list_comments(task_id),
                'runs': self.list_runs(task_id), 'audit': self.list_audit('task', task_id),
                'reviews': self._rows('SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId DESC', (task_id,))}


class MemoryStore(SQLiteStore):
    """Tests/demo: the same store on an in-memory database."""
    def __init__(self): super().__init__(':memory:')
