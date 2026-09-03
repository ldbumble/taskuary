"""Storage: one small dict-shaped contract, two bindings - SQLite (stdlib, the local-first
default) and in-memory (tests/demo). Every mutation is meant to be paired with .audit();
the audit log is a Buzz-style tamper-evident hash chain (each row hashes the previous).
"""
import contextlib, hashlib, json, re, sqlite3, threading
from datetime import datetime, timedelta
from loguru import logger

GENESIS = '0' * 64
TASK_COLS = ('Title', 'Summary', 'Kind', 'Status', 'Priority', 'Assignee', 'Source', 'SourceRef', 'Tags')
MSG_COLS = ('TaskId', 'ExternalId', 'ConversationId', 'Channel', 'SourceName', 'Subject',
            'FromName', 'FromEmail', 'SentAt', 'BodyText', 'SourceLink', 'Status', 'Direction', 'RecipientsJson',
            'MailMetaJson')
RUN_COLS = ('Status', 'TraceJson', 'Result', 'LastError', 'SessionId', 'DiffText')
REVIEW_COLS = ('TaskId', 'MessageId', 'RunId', 'Kind', 'DraftText', 'FinalText', 'Status', 'Reason', 'Deliver')
POLICY_COLS = ('Name', 'Kind', 'Pattern', 'Action', 'Reason', 'SortOrder', 'Active')
SOURCE_COLS = ('Channel', 'Address', 'Owner', 'ConnectorId', 'Active', 'ConfigJson')
MEMORY_COLS = ('Scope', 'ScopeKey', 'Note', 'Source', 'Active', 'CreatedBy')
ATT_COLS = ('MessageId', 'ExternalId', 'Name', 'ContentType', 'Size', 'ContentId', 'Inline', 'Path')
ARTIFACT_COLS = ('TaskId', 'Name', 'ContentType', 'Size', 'Path', 'Kind', 'CreatedBy')

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
CHAT_CHANNELS = {'teams', 'slack', 'telegram', 'whatsapp', 'discord', 'imessage'}
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
  CreatedBy TEXT, CreatedAt TEXT, UpdatedBy TEXT, UpdatedAt TEXT, ClosedAt TEXT);
CREATE TABLE IF NOT EXISTS message (MessageId INTEGER PRIMARY KEY, TaskId INTEGER, ExternalId TEXT,
  ConversationId TEXT, Channel TEXT, SourceName TEXT, Subject TEXT, FromName TEXT, FromEmail TEXT,
  SentAt TEXT, BodyText TEXT, SourceLink TEXT, Status TEXT DEFAULT 'routed', CreatedAt TEXT,
  Direction TEXT DEFAULT 'in', RecipientsJson TEXT, MailMetaJson TEXT);
CREATE TABLE IF NOT EXISTS attachment (AttachmentId INTEGER PRIMARY KEY, MessageId INTEGER, ExternalId TEXT,
  Name TEXT, ContentType TEXT, Size INTEGER, ContentId TEXT, Inline INTEGER DEFAULT 0, Path TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS transcript (TranscriptId INTEGER PRIMARY KEY, TaskId INTEGER, Sid TEXT,
  Agent TEXT, Cwd TEXT, Text TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS task_artifact (ArtifactId INTEGER PRIMARY KEY, TaskId INTEGER, Name TEXT,
  ContentType TEXT, Size INTEGER, Path TEXT, Kind TEXT, CreatedBy TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS route (RouteId INTEGER PRIMARY KEY, MessageId INTEGER, TaskId INTEGER,
  Decision TEXT, Score REAL, Reason TEXT, CandidatesJson TEXT, RoutedBy TEXT, CreatedAt TEXT,
  RawOutput TEXT, ParseError TEXT);
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
CREATE TABLE IF NOT EXISTS connector (ConnectorId INTEGER PRIMARY KEY, Type TEXT, Name TEXT,
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
-- The agent wall (blackboard.py): what one agent leaves for the next one in the same
-- checkout. Derived facts (who holds which file) are read off git and the run trace and are
-- never stored; this is the part only the agent knows - what it is doing, what it found, what
-- it is about to push, and what the next one must not touch.
CREATE TABLE IF NOT EXISTS boardnote (NoteId INTEGER PRIMARY KEY, TaskId INTEGER, Agent TEXT,
  Cwd TEXT, Kind TEXT, Body TEXT, Files TEXT, CreatedAt TEXT, ReadBy TEXT);
CREATE INDEX IF NOT EXISTS idx_boardnote_cwd ON boardnote(Cwd, NoteId);
CREATE TABLE IF NOT EXISTS learned_history (Id INTEGER PRIMARY KEY, Key TEXT, Text TEXT, Status TEXT, Score INTEGER,
  Ev TEXT, Action TEXT, Actor TEXT, At TEXT);
CREATE TABLE IF NOT EXISTS idea (IdeaId INTEGER PRIMARY KEY, Key TEXT UNIQUE, Kind TEXT, Text TEXT, ActionJson TEXT, Sig TEXT,
  Status TEXT DEFAULT 'open', SnoozeUntil TEXT, MessageId INTEGER, FirstSeen TEXT, LastSaid TEXT, SaidCount INTEGER DEFAULT 0,
  DecidedBy TEXT, DecidedAt TEXT);
CREATE TABLE IF NOT EXISTS report_run (RunId INTEGER PRIMARY KEY, SourceId INTEGER, At TEXT, Type TEXT, Title TEXT, Ms INTEGER, Subject TEXT,
  MessageId INTEGER, Failed INTEGER DEFAULT 0, Error TEXT, Said INTEGER, LinesJson TEXT, ReviewedJson TEXT, Inputs TEXT, Summary TEXT);
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
"""
# the knowledge base's search index (knowledge.py). A VIRTUAL table, kept out of SCHEMA: a Python
# built without FTS5 must still open the store - search then falls back to LIKE over kb_chunk.
KB_FTS = 'CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(Text, ChunkId UNINDEXED, tokenize="porter unicode61")'

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
    'CREATE INDEX IF NOT EXISTS idx_task_artifact_task ON task_artifact(TaskId, ArtifactId)',
    'CREATE INDEX IF NOT EXISTS idx_comment_task ON comment(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit(EntityType, EntityId)',
    'CREATE INDEX IF NOT EXISTS idx_dispatchq_task ON dispatchq(TaskId)',
    'CREATE INDEX IF NOT EXISTS idx_waitroom_task ON waitroom(TaskId, DeliveredAt)',
    'CREATE INDEX IF NOT EXISTS idx_idea_status ON idea(Status, MessageId)',
    'CREATE INDEX IF NOT EXISTS idx_connector_type ON connector(Type, ConnectorId)',
    'CREATE INDEX IF NOT EXISTS idx_invoice_batch_source ON invoice_batch(SourceId, Period)',
    'CREATE INDEX IF NOT EXISTS idx_invoice_item_batch ON invoice_item(BatchId, Status)',
    'CREATE INDEX IF NOT EXISTS idx_invoice_item_review ON invoice_item(ReviewId)',
)

# Out of the box Taskuary WORKS the mail: a job goes to the coding agent, a question gets a
# draft. Both stop short of anything leaving the building - a draft waits for you to send it,
# and a session is one you watch - so ON is a safe default and OFF was just a slower start.
DEFAULT_SETTINGS = {'default_action': 'draft', 'auto_draft_enabled': '1', 'attach_threshold': '0.42',
                    'feed_days': '14', 'intent_classify_enabled': '1', 'coder_auto_enabled': '1',
                    'auto_sessions': '4',           # unattended agent sessions at once; the rest queue
                    'triage_ai': '',      # '' = first active AI connector | connector:<id> | cli:<agent>
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
                    # in chat, an ask that starts an agent gets one line back at once (ingest._ack_chat)
                    'chat_ack_enabled': '1', 'chat_ack_text': "On it - I'll get back to you here.",
                    # the assistant's POST on the Timeline (assistant.py): what it looks for, the silence and
                    # quiet that count as news, how much it says. Its clock and its instruction live on the
                    # Reports tab (the seeded 'Assistant' report).
                    'assistant_followup_hours': '24',
                    'assistant_cold_days': '3', 'assistant_producers': 'followup,promise,prep,cold,idea',
                    'assistant_max_lines': '5',
                    # the conversational assistant has its own saved brain. API connectors are
                    # the fast/native path; a CLI remains available for tool-heavy work.
                    'assistant_ai': '', 'assistant_model': '',
                    # the coder's context file (context.py): history, past work and the brief, written to
                    # ~/.taskuary/context/TQ-xxxx.md and pointed at from the seed - not crammed into it
                    'coder_context_file': '1',
                    'agent_hooks': '1',           # Claude Code tells the Board what it is doing, through its own hooks (hooks.py)
                    'timeline_fade': 'normal',    # older Timeline rows rest quieter - off | gentle | normal | sharp
                    'waitroom_drip': '1',         # queued notes land one per stop (a funnel of prompts), not all at once
                    # which CLI agent works tasks when nothing names one - pickers list it first
                    'default_agent': 'coder',
                    # ordered CSV of alternate CLI profiles; * means every other configured
                    # agent in roster order. A quota/login outage should move the same task to
                    # another CLI instead of leaving a dead terminal as its only outcome.
                    'backup_agents': '*',
                    # ordered alternate brains for triage, drafts, summaries and assistant chat.
                    # Blank is deliberately opt-in: a cloud-to-CLI fallback may change cost and
                    # privacy, so the owner names the alternatives explicitly in Settings.
                    'triage_backup_ai': '',
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
                    # the owner's messages in one private WhatsApp notify chat open the same
                    # durable guide conversation as the floating desktop assistant
                    'phone_assistant': '0',
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
                 # QuickBooks is the first Corporate system that can WRITE (a bill, an expense) -
                 # still report and tool, never trigger; the writes are gated by scope, not by role
                 'quickbooks': 'report,tool',
                 'zoho_invoice': 'report,tool',
                 'teller': 'report,tool',          # the bank feed: transactions as a report (and "can become work"), balances as a tool
                 # research reads the public web - a report source, and a tool an agent may use
                 'exa': 'report,tool', 'tavily': 'report,tool',
                 'firecrawl': 'report,tool', 'reader': 'report,tool',
                 # aws/azure: the per-OBJECT picker carries the intent (report by default,
                 # which polls nothing) - the card itself is just a connection and a tool
                 'aws': 'report,tool', 'azure': 'report,tool',
                 'sharepoint': 'report,tool', 'google_sheets': 'report,tool',
                 'knowledge': 'report,tool',       # indexed documents: a kb_search report, and a tool for agents and the drafter
                 # the handbook the agents write themselves (handbook.py). tool, because the only
                 # things that read and write it are agents; no trigger, because it never arrives.
                 'handbook': 'report,tool',
                 'jira': 'trigger', 'asana': 'trigger', 'monday': 'trigger',
                 'clickup': 'trigger', 'todoist': 'trigger',
                 'gitlab': 'trigger', 'azdo': 'trigger', 'linear': 'trigger', 'trello': 'trigger',
                 # notion edits are information, not assignments; discord is a chat channel
                 'notion': 'feed', 'discord': 'trigger,tool',
                 'sentry': 'trigger', 'pagerduty': 'trigger',
                 # speech to text: no role - the funnel and the prompt box ask the first active one
                 'gemini_stt': '', 'groq_stt': '', 'openai_stt': '', 'deepgram': '', 'elevenlabs_stt': '', 'stt_server': '', 'local_whisper': ''}
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
        self.idlock = threading.Lock()     # create_task: allocate-and-insert as one step (self.lock is per statement)
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
            # Keep the evidence when triage answers but breaks its JSON contract. Without the
            # raw answer another machine could only report "could not read it", not why.
            routecols = {r[1] for r in self.cx.execute('PRAGMA table_info(route)')}
            if 'RawOutput' not in routecols:
                self.cx.execute('ALTER TABLE route ADD COLUMN RawOutput TEXT')
            if 'ParseError' not in routecols:
                self.cx.execute('ALTER TABLE route ADD COLUMN ParseError TEXT')
            # the assistant's private read on the message (counsel.py) - JSON, shown on the panel
            if 'Brief' not in mcols:
                self.cx.execute('ALTER TABLE message ADD COLUMN Brief TEXT')
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
            qcols = {r[1] for r in self.cx.execute('PRAGMA table_info(dispatchq)')}
            for col, typ in (('Value', 'REAL'), ('Floor', 'REAL'), ('Why', 'TEXT')):    # rank.py: value-ordered queue
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
                    self.cx.execute('''CREATE TABLE connector (
                        ConnectorId INTEGER PRIMARY KEY, Type TEXT, Name TEXT, ConfigJson TEXT,
                        Secret TEXT, Active INTEGER DEFAULT 0, LastSyncAt TEXT, LastError TEXT,
                        Roles TEXT, Scope TEXT)''')
                    self.cx.execute('''INSERT INTO connector
                        (ConnectorId, Type, Name, ConfigJson, Secret, Active, LastSyncAt, LastError, Roles, Scope)
                        SELECT ConnectorId, Type, Name, ConfigJson, Secret, Active, LastSyncAt, LastError, Roles, Scope
                        FROM connector_one_per_type''')
                    self.cx.execute('DROP TABLE connector_one_per_type')
                    self.cx.execute('RELEASE widen_connector_type')
                except Exception:
                    self.cx.execute('ROLLBACK TO widen_connector_type')
                    self.cx.execute('RELEASE widen_connector_type')
                    raise
            for ix in INDEXES:
                self.cx.execute(ix)
            try: self.cx.execute(KB_FTS); self.kb_fts = True
            except sqlite3.OperationalError as e:
                self.kb_fts = False; logger.warning(f'no FTS5 in this sqlite build - knowledge search falls back to LIKE: {e}')
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
                         ('sharepoint', 'SharePoint'), ('google_sheets', 'Google Sheets'),
                         ('knowledge', 'Knowledge base'), ('handbook', 'Company handbook'),
                         ('jira', 'Jira'), ('asana', 'Asana'), ('monday', 'Monday.com'),
                         ('clickup', 'ClickUp'), ('todoist', 'Todoist'),
                         ('gitlab', 'GitLab'), ('azdo', 'Azure DevOps'), ('linear', 'Linear'),
                         ('trello', 'Trello'), ('notion', 'Notion'), ('discord', 'Discord'),
                         ('sentry', 'Sentry'), ('pagerduty', 'PagerDuty'),
                         ('prometheus', 'Prometheus'), ('datadog', 'Datadog'),
                         ('intacct', 'Sage Intacct'), ('quickbooks', 'QuickBooks Online'), ('teller', 'Bank & card feed (Teller)'),
                         ('zoho_invoice', 'Zoho Invoice'),
                         ('exa', 'Exa search'), ('tavily', 'Tavily search'),
                         ('firecrawl', 'Firecrawl'), ('reader', 'Jina Reader'),
                         ('gemini_stt', 'Google Gemini transcription'), ('groq_stt', 'Groq (Whisper)'), ('openai_stt', 'OpenAI transcription'), ('deepgram', 'Deepgram'),
                         ('elevenlabs_stt', 'ElevenLabs Scribe'), ('stt_server', 'Any Whisper server'), ('local_whisper', 'Local Whisper')):
                # Type is intentionally not unique anymore. Seed only when a type has no card;
                # INSERT OR IGNORE would now insert another blank copy on every startup.
                self.cx.execute('''INSERT INTO connector (Type, Name, Roles)
                                   SELECT ?, ?, ? WHERE NOT EXISTS
                                   (SELECT 1 FROM connector WHERE Type=?)''',
                                (t, n, DEFAULT_ROLES.get(t, ''), t))
            for t, r in DEFAULT_ROLES.items():        # dbs from before roles existed
                self.cx.execute('UPDATE connector SET Roles=? WHERE Type=? AND Roles IS NULL', (r, t))
            # The handbook ships ON - handbook.enabled has said so since it was written - but its
            # card is seeded like every other, at Active 0, and enabled() reads the card when one
            # exists. So the feature was off on every install that ever ran: coder.wrap skipped
            # learn_from_session, `--learned` was refused, and the Social tab could only ever hold
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
            for name in ('soul', 'coder', 'digest', 'learned', 'triage', 'style', 'counsel'):
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
                    # ...and not only SOUL: CODER.md went blank on a live install (2026-09-01) and
                    # every coder session ran with no rules until somebody looked. Empty is empty.
                    self.cx.execute("UPDATE doc SET Content=?, UpdatedBy='template', UpdatedAt=? "
                                    "WHERE Name=? AND TRIM(IFNULL(Content,''))=''",
                                    (txt, _now(), name))
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
                                 json.dumps({'type': 'digest', 'title': 'Morning digest', 'days': 1, 'daily_at': '08:00',
                                             'on_startup': True, 'once_per_day': True, 'ai_prompt': PROMPT})))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('digest_report_seeded', '1', 'template')")
            # ...and its sibling: the weekly 'what should you automate next' brief (toil.py) -
            # same deal: a real report, prompt on the Reports tab, deleting it turns it off.
            # It also runs on startup, once a WEEK: seeded on cron alone, a fresh install saw
            # nothing from it until the following Monday, so the third shipped report was
            # invisible on the day someone was actually looking at the tab.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='automate_report_seeded'").fetchone():
                from .toil import PROMPT as AUTOMATE_PROMPT
                self.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                                ('report', 'Automation ideas', 'template', 1,
                                 json.dumps({'type': 'automate', 'title': 'Automation ideas', 'days': 30,
                                             'cron': '0 8 * * 1', 'on_startup': True, 'once_per_week': True,
                                             'ai_prompt': AUTOMATE_PROMPT})))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('automate_report_seeded', '1', 'template')")
            # ...and the Assistant (assistant.py): its post on the Timeline is scheduled and worded HERE
            # too - every 30 minutes and on startup by default (a quiet check posts nothing), the
            # instruction editable, deleting the row is the off switch. These two are the working demo of
            # both kinds of report: the digest is an AI pass over the hub's own data, the assistant a voice.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='assistant_report_seeded'").fetchone():
                from .assistant import PROMPT as ASSISTANT_PROMPT
                self.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                                ('report', 'Assistant', 'template', 1,
                                 json.dumps({'type': 'assistant', 'title': 'Assistant', 'every_minutes': 30, 'on_startup': True,
                                             'ai_prompt': ASSISTANT_PROMPT})))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('assistant_report_seeded', '1', 'template')")
            # The close of the day deserves a different lens from the Morning digest: eight
            # rolling hours of Inbox/Sent only, accomplishments first and tomorrow's top three
            # second. It waits for its 6 pm local slot instead of greeting a morning startup.
            if not self.cx.execute("SELECT 1 FROM setting WHERE Name='evening_inbox_report_seeded'").fetchone():
                from .evening import PROMPT as EVENING_PROMPT
                self.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                                ('report', 'End of day checkup', 'template', 1,
                                 json.dumps({'type': 'evening_inbox', 'title': 'End of day checkup', 'hours': 8,
                                             'daily_at': '18:00', 'once_per_day': True,
                                             'first_run_at_schedule': True, 'ai_prompt': EVENING_PROMPT})))
                self.cx.execute("INSERT INTO setting (Name, Value, UpdatedBy) VALUES ('evening_inbox_report_seeded', '1', 'template')")
            # prompt heal: a Morning digest still running a SHIPPED instruction tracks the
            # current one (same deal the template docs get) - an owner-edited prompt is never touched
            from .digest import OLD_PROMPTS, PROMPT as DIGEST_PROMPT
            from .assistant import OLD_PROMPT_HEADS, PROMPT as ASSISTANT_PROMPT
            from .toil import PROMPT as AUTOMATE_PROMPT
            for sid_, cj in self.cx.execute("SELECT SourceId, ConfigJson FROM source WHERE Channel='report'").fetchall():
                try: c = json.loads(cj or '{}')
                except ValueError: continue
                # the stock Assistant was seeded hourly (then 20-minutely) with a stock prompt; unedited, it
                # becomes the 30-minute check with the current prompt (an owner-edited prompt or cadence is kept)
                if c.get('type') == 'assistant' and str(c.get('ai_prompt') or '').startswith(OLD_PROMPT_HEADS):
                    c['ai_prompt'] = ASSISTANT_PROMPT
                    if c.get('every_minutes') in (60, 20): c['every_minutes'] = 30
                    c.setdefault('on_startup', True)
                    self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), sid_))
                # the stock Automation ideas was seeded on Mondays only; unedited, it also greets
                # a launch - at most once a week (an owner-set cadence is kept as it is)
                if c.get('type') == 'automate' and c.get('ai_prompt') == AUTOMATE_PROMPT and c.get('cron') == '0 8 * * 1':
                    if not c.get('on_startup'):
                        c['on_startup'], c['once_per_week'] = True, True
                        self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), sid_))
                if c.get('type') == 'digest' and (c.get('ai_prompt') in OLD_PROMPTS or c.get('ai_prompt') == DIGEST_PROMPT):
                    c['ai_prompt'] = DIGEST_PROMPT
                    # a stock digest on the old default clock (none, or the three-hourly one) becomes the
                    # 8 am brief that also runs on startup; an owner-set cadence is kept
                    stock_clock = not any(c.get(k) for k in ('cron', 'every_minutes', 'daily_at')) or (c.get('every_minutes') == 180 and not c.get('cron') and not c.get('daily_at'))
                    if stock_clock: c.pop('every_minutes', None); c['daily_at'] = '08:00'; c['on_startup'] = True
                    # ...and a brief is once a day: on_startup alone re-filed it on every launch
                    if c.get('on_startup'): c['once_per_day'] = True
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
    def _poke(self, *kinds, **payload):
        """Wake the UI. A write that does not change what a tab is looking at stays quiet."""
        try:
            from . import live
            for k in kinds: live.emit(k, **payload)
        except Exception:
            pass

    # tasks
    def create_task(self, fields, actor):
        # TaskId is a rowid, and SQLite hands a DELETED one straight back to the next insert.
        # TQ-0034 was three different tasks in one morning: a refund thread at 08:19 (with a
        # live agent on it), deleted at 10:11, the id reused twice more by lunchtime - and the
        # orphaned session, still holding task_id 34, showed up as the agent working a report
        # it had never been given. A TQ-ref is an identity: it goes in prompts, in transcripts,
        # in pull requests. It must never name two different pieces of work.
        # ...and it must be issued ONCE: the allocation is three reads and a write, each taking the
        # statement lock on its own, so a poll and a click creating tasks together computed the same
        # id and one of them hit the primary key (audit 2026-09-02)
        with self.idlock:
            tid = self._insert('task', {**fields, 'TaskId': self._next_task_id()},
                                TASK_COLS + ('TaskId',), {'CreatedBy': actor, 'CreatedAt': _now()})
        self._bump_snapshots()
        self._poke('task-changed', task_id=tid)
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
        # Timeline rows carry task/review state too, so a task transition changes both views.
        self._poke('feed-changed', 'task-changed', task_id=task_id)
    def get_task(self, task_id): return self._one('SELECT * FROM task WHERE TaskId=?', (task_id,))

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
    def list_tasks(self, status=None, active_only=False):
        q = '''SELECT t.*, rv.Status ReviewStatus, rv.Kind ReviewKind,
                       rn.Status RunStatus, rn.AgentName RunAgent,
                       ho.Body HandoverNote,
                       ms.SearchChannels, ms.SearchSources, ms.SearchSubjects, ms.SearchPeople,
                       ms.SearchEmails, ms.SearchExternalIds, ms.SearchLinks
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
        q += '''
               LEFT JOIN (
                   SELECT TaskId,
                          GROUP_CONCAT(DISTINCT Channel) SearchChannels,
                          GROUP_CONCAT(DISTINCT SourceName) SearchSources,
                          GROUP_CONCAT(DISTINCT Subject) SearchSubjects,
                          GROUP_CONCAT(DISTINCT FromName) SearchPeople,
                          GROUP_CONCAT(DISTINCT FromEmail) SearchEmails,
                          GROUP_CONCAT(DISTINCT ExternalId) SearchExternalIds,
                          GROUP_CONCAT(DISTINCT SourceLink) SearchLinks
                   FROM message GROUP BY TaskId
               ) ms ON ms.TaskId=t.TaskId'''
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
                         "OR (t.Status='done' AND IFNULL(t.ClosedAt, t.UpdatedAt) >= date('now','localtime')))")
        if where:
            q += ' WHERE ' + ' AND '.join(where)
        return self._rows(q + ' ORDER BY t.TaskId DESC', p)
    def delete_task(self, task_id):
        for q in ("UPDATE message SET TaskId=NULL, Status='filed' WHERE TaskId=?", 'UPDATE route SET TaskId=NULL WHERE TaskId=?',
                  'DELETE FROM review WHERE TaskId=?', 'DELETE FROM comment WHERE TaskId=?',
                  'DELETE FROM run WHERE TaskId=?', 'DELETE FROM task_artifact WHERE TaskId=?',
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

    def message_exists(self, external_id):
        return self._one('SELECT 1 x FROM message WHERE ExternalId=?', (external_id,)) is not None
    def add_message(self, fields):
        # normalized on the way IN, not only by a heal on the way past: one clock for the
        # timeline, and no row that can sort above its own future
        if fields.get('SentAt'): fields = {**fields, 'SentAt': norm_stamp(fields['SentAt'])}
        mid = self._insert('message', fields, MSG_COLS, {'CreatedAt': _now()})
        if fields.get('TaskId'):
            self._bump_snapshots()
            self._poke('feed-changed', 'task-changed', message_id=mid, task_id=fields['TaskId'])
        else:
            self._poke('feed-changed', message_id=mid)
        return mid
    def get_message(self, mid): return self._one('SELECT * FROM message WHERE MessageId=?', (mid,))
    def message_by_external(self, external_id):
        return self._one('SELECT * FROM message WHERE ExternalId=? ORDER BY MessageId DESC LIMIT 1', (external_id,))
    # ── what the hub knows about a sender / a topic (counsel.dossier, responder) ─────────────
    def messages_from(self, email, since, limit=8):
        return self._rows("SELECT * FROM message WHERE lower(FromEmail)=? AND Status NOT IN ('context','skipped') AND SentAt>=? "
                          'ORDER BY SentAt DESC LIMIT ?', (email.lower(), since, limit))
    def own_replies_to(self, email, since, limit=5):
        """The owner's own words on this sender's threads - 'context' rows ride inside the chains."""
        return self._rows("SELECT * FROM message WHERE Status='context' AND SentAt>=? AND ConversationId IN "
                          '(SELECT ConversationId FROM message WHERE lower(FromEmail)=? AND ConversationId IS NOT NULL) '
                          'ORDER BY SentAt DESC LIMIT ?', (since, email.lower(), limit))
    def recent_messages(self, since, limit=300):
        return self._rows("SELECT MessageId, ConversationId, Channel, Direction, Subject, FromName, FromEmail, SentAt, Status, TaskId, substr(BodyText, 1, 400) BodyText "
                          "FROM message WHERE Status NOT IN ('context','skipped') AND SentAt>=? ORDER BY SentAt DESC LIMIT ?", (since, limit))
    def set_brief(self, mid, brief): self._exec('UPDATE message SET Brief=? WHERE MessageId=?', (brief, mid))
    # ── what the assistant's post reads (assistant.py) ────────────────────────────────────────
    def owner_last_words(self, since, before, limit=40):
        """Threads whose LAST message is the owner's own ('context' rides inside a chain, 'out' was
        sent from here), written between `since` and `before` - the silence a chase is about."""
        return self._rows("SELECT * FROM message m WHERE (m.Status='context' OR m.Direction='out') AND m.ConversationId IS NOT NULL "
                          'AND m.SentAt>=? AND m.SentAt<=? AND NOT EXISTS (SELECT 1 FROM message x WHERE x.ConversationId=m.ConversationId '
                          "AND x.MessageId<>m.MessageId AND x.Status<>'skipped' AND x.SentAt>m.SentAt) ORDER BY m.SentAt DESC LIMIT ?",
                          (since, before, limit))
    def last_inbound_in(self, conversation_id):
        return self._one("SELECT * FROM message WHERE ConversationId=? AND Status NOT IN ('context','skipped') AND IFNULL(Direction,'in')<>'out' "
                         'ORDER BY SentAt DESC LIMIT 1', (conversation_id,))
    def task_for_conversation(self, conversation_id, subject=None):
        """The task this thread already belongs to - OPEN OR CLOSED. The router matches a reply
        against open tasks only (snapshots), which is right for inbound work and wrong for the
        owner's own reply: answer a thread the day after its task closed and the reply had
        nowhere to land, so the chain lost the last thing said on it."""
        if conversation_id:
            r = self._one('SELECT TaskId FROM message WHERE ConversationId=? AND TaskId IS NOT NULL '
                          'ORDER BY MessageId DESC LIMIT 1', (conversation_id,))
            if r: return r['TaskId']
        # channels without a conversation id (and mail whose References header was rewritten)
        return next((m['TaskId'] for m in reversed(self.thread_messages(None, subject)) if m['TaskId']), None) if subject else None
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
    # ── ideas: what the assistant said, and what the owner did about it ──────────────────────
    def list_ideas(self, status=None, mid=None):
        q, p = 'SELECT * FROM idea', []
        w = ([('Status=?', status)] if status else []) + ([('MessageId=?', mid)] if mid else [])
        if w: q += ' WHERE ' + ' AND '.join(k for k, _ in w); p = [v for _, v in w]
        return self._rows(q + ' ORDER BY IdeaId DESC', p)
    def get_idea(self, idea_id): return self._one('SELECT * FROM idea WHERE IdeaId=?', (idea_id,))
    def upsert_idea(self, s: dict, stamp: str) -> dict:
        """Said (again): a known key reopens with the new facts and text; a new one is born."""
        old = self._one('SELECT * FROM idea WHERE Key=?', (s['key'],))
        action = dict(s.get('action') or {})
        if old:
            try: prior = json.loads(old.get('ActionJson') or '{}')
            except ValueError: prior = {}
            # Talking back is part of this suggestion's history. New facts may reopen and
            # rewrite the action, but must not erase the owner's correction or our answer.
            if prior.get('chat'): action['chat'] = prior['chat']
        act = json.dumps(action)
        if old:
            self._exec("UPDATE idea SET Kind=?, Text=?, ActionJson=?, Sig=?, Status='open', SnoozeUntil=NULL, LastSaid=?, SaidCount=SaidCount+1 WHERE Key=?",
                       (s.get('kind'), s['text'], act, s.get('sig'), stamp, s['key']))
        else:
            self._exec('INSERT INTO idea (Key, Kind, Text, ActionJson, Sig, Status, FirstSeen, LastSaid, SaidCount) VALUES (?,?,?,?,?,?,?,?,1)',
                       (s['key'], s.get('kind'), s['text'], act, s.get('sig'), 'open', stamp, stamp))
        return self._one('SELECT * FROM idea WHERE Key=?', (s['key'],))
    def set_idea_status(self, idea_id, status, by, until=None):
        self._exec('UPDATE idea SET Status=?, SnoozeUntil=?, DecidedBy=?, DecidedAt=? WHERE IdeaId=?', (status, until, by, _now(), idea_id))
    def set_idea_action(self, idea_id, action):
        self._exec('UPDATE idea SET ActionJson=? WHERE IdeaId=?', (json.dumps(action), idea_id))
    def set_ideas_message(self, ids, mid):
        if ids: self._exec(f"UPDATE idea SET MessageId=? WHERE IdeaId IN ({','.join('?' * len(ids))})", [mid, *ids])
    # ── a report's run history (reports.run_report_source; the Reports tab's History) ────────
    REPORT_RUNS_KEPT = 60          # per report - a month of half-hourly assistant checks is 1400, and nobody reads past the last few dozen
    def add_report_run(self, sid: int, rec: dict) -> int:
        """One run of one report, whole: what it read (Inputs), what it reviewed, what it said and why
        (Lines), what came out. The last-run setting keeps the newest for the row; this keeps the rest."""
        rid = self._exec('INSERT INTO report_run (SourceId, At, Type, Title, Ms, Subject, MessageId, Failed, Error, Said, LinesJson, ReviewedJson, Inputs, Summary) '
                         'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (sid, rec.get('at'), rec.get('type'), rec.get('title'), rec.get('ms'), rec.get('subject'), rec.get('message_id'), int(bool(rec.get('failed'))),
                          rec.get('error'), rec.get('said'), json.dumps(rec.get('lines') or [], default=str), json.dumps(rec.get('reviewed'), default=str) if rec.get('reviewed') else None,
                          rec.get('inputs'), rec.get('summary')))
        self._exec('DELETE FROM report_run WHERE SourceId=? AND RunId NOT IN (SELECT RunId FROM report_run WHERE SourceId=? ORDER BY RunId DESC LIMIT ?)',
                   (sid, sid, self.REPORT_RUNS_KEPT))
        return rid
    def report_runs(self, sid: int, limit: int = 60) -> list:
        """The history, newest first, WITHOUT the inputs (14KB each) - get_report_run fetches one whole."""
        return [self._run_row(r) for r in self._rows('SELECT RunId, SourceId, At, Type, Title, Ms, Subject, MessageId, Failed, Error, Said, LinesJson, ReviewedJson, '
                                                      'length(Inputs) InputChars FROM report_run WHERE SourceId=? ORDER BY RunId DESC LIMIT ?', (sid, limit))]
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
                'reviewed': j(r.get('ReviewedJson')), 'inputChars': r.get('InputChars') or 0, **({'inputs': r['Inputs']} if 'Inputs' in r else {}),
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
    def scan_messages(self, limit=20000):
        """Just enough of every message to re-run a policy over the history (bodies capped)."""
        # ConversationId rides along so a history reader can pair inbound mail with what the owner
        # SENT back (histgen: "answered" is the ground truth TRIAGE.md is distilled from, and on an
        # IMAP install this store is the only place the inbound half lives)
        return self._rows('SELECT MessageId, TaskId, ConversationId, FromEmail, Subject, Status, SentAt, '
                          'substr(BodyText, 1, 2000) BodyText '
                          'FROM message ORDER BY MessageId DESC LIMIT ?', (limit,))
    def set_message_status(self, mid, status):
        self._exec('UPDATE message SET Status=? WHERE MessageId=?', (status, mid))
        self._poke('feed-changed', message_id=mid)
    def update_message_body(self, mid, body): self._exec('UPDATE message SET BodyText=? WHERE MessageId=?', (body, mid))   # a voice note, transcribed later
    def get_message(self, mid): return self._one('SELECT * FROM message WHERE MessageId=?', (mid,))
    def place_message(self, mid, task_id, status):
        """A row that was shown first and judged later lands where the judgement puts it (ingest.drain)."""
        self._exec('UPDATE message SET TaskId=?, Status=? WHERE MessageId=?', (task_id, status, mid))
        if task_id is not None:
            self._bump_snapshots()
            self._poke('feed-changed', 'task-changed', message_id=mid, task_id=task_id)
        else:
            self._poke('feed-changed', message_id=mid)
    def claim_retriage(self, mid: int) -> bool:
        """Atomically move one failed, taskless row back into triage.

        The endpoint checks the prior verdict for a useful error message; this compare-and-set is
        the concurrency guard. Two clicks (or browser retries) must never create two tasks.
        """
        with self.lock:
            cur = self.cx.execute("""UPDATE message SET Status='triaging'
                                   WHERE MessageId=? AND TaskId IS NULL AND Status='filed'""", (mid,))
            self.cx.commit(); self._writes += 1
            ok = cur.rowcount == 1
        if ok:
            self._poke('feed-changed', message_id=mid)
        return ok
    def pending_triage(self, limit=500):
        return self._rows("SELECT * FROM message WHERE Status='triaging' ORDER BY MessageId LIMIT ?", (limit,))
    def attach_message(self, mid, task_id):
        self._exec("UPDATE message SET TaskId=?, Status='routed' WHERE MessageId=?", (task_id, mid))
        self._bump_snapshots()
        self._poke('feed-changed', 'task-changed', message_id=mid, task_id=task_id)
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
    # A pty is not storage: the session's readable transcript is written here when it ends, so
    # "Done - wrap it up" still works an hour later, on a task whose CLI has long since exited.
    def add_transcript(self, task_id, sid, text, agent=None, cwd=None):
        if not (text or '').strip(): return None
        self._exec('DELETE FROM transcript WHERE Sid=?', (sid,))      # one row per session, always the latest
        return self._exec('INSERT INTO transcript (TaskId,Sid,Agent,Cwd,Text,CreatedAt) VALUES (?,?,?,?,?,?)',
                          (task_id, sid, agent, cwd, text, _now()))
    def agented_task_ids(self) -> set:
        """Every task an agent has ever touched - a live-session transcript or a headless run. The
        Board is the agents' board: a reply the owner answered by hand is finished work, not board work."""
        return {r['TaskId'] for r in self._rows('SELECT DISTINCT TaskId FROM transcript UNION SELECT DISTINCT TaskId FROM run') if r['TaskId']}
    def last_transcript(self, task_id):
        return self._one('SELECT * FROM transcript WHERE TaskId=? ORDER BY TranscriptId DESC LIMIT 1', (task_id,))

    def add_route(self, mid, tid, decision, score, reason, candidates, routed_by='router',
                  raw_output=None, parse_error=None):
        return self._exec('''INSERT INTO route
            (MessageId,TaskId,Decision,Score,Reason,CandidatesJson,RoutedBy,CreatedAt,RawOutput,ParseError)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
                          (mid, tid, decision, score, reason, json.dumps(candidates), routed_by, _now(),
                           raw_output, parse_error))
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
        rid = self._exec('INSERT INTO run (TaskId,AgentName,Instruction,DispatchedBy,StartedAt) VALUES (?,?,?,?,?)',
                         (task_id, agent_name, instruction, by, _now()))
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
    def _poke_review(self, review):
        """A review changes both places that render it: its message and its task."""
        if not review: return
        kinds = []
        if review.get('MessageId'): kinds.append('feed-changed')
        if review.get('TaskId'): kinds.append('task-changed')
        if kinds:
            self._poke(*kinds, review_id=review.get('ReviewId'),
                       message_id=review.get('MessageId'), task_id=review.get('TaskId'))
    def _review_changed(self, rid): self._poke_review(self.get_review(rid))
    def add_review(self, fields):
        rid = self._insert('review', fields, REVIEW_COLS, {'CreatedAt': _now()})
        self._poke_review({**fields, 'ReviewId': rid})
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
    def decide_review(self, rid, status, final, by, note=None):
        self._exec('UPDATE review SET Status=?, FinalText=?, DecidedBy=?, DecidedAt=?, DecideNote=? WHERE ReviewId=?',
                   (status, final, by, _now(), note, rid))
        self._review_changed(rid)
    def pending_review(self, task_id, kind=None, live_only=True):
        """The task's live pending review, by the SAME visibility rule the queue uses: a draft the
        owner can no longer see is not one to re-draft into or treat as already-answered. Pass
        live_only=False only to reach a row deliberately - housekeeping, not the funnel."""
        q = f"SELECT rv.* {_REVIEW_FROM} WHERE rv.TaskId=? AND rv.Status='pending'"
        if kind:      q += ' AND rv.Kind=?'
        if live_only: q += f' AND {_NOT_ORPHAN} AND {_VISIBLE_PENDING}'
        return self._one(q + ' ORDER BY rv.ReviewId DESC LIMIT 1', (task_id, kind) if kind else (task_id,))
    def sent_reply(self, message_id=None, task_id=None):
        """The newest reply that actually passed the send gate for this message/task.

        A successful review is the durable receipt for replies sent by Taskuary. Those replies
        are not necessarily ingested back from the external channel before the Assistant's next
        check, so message history alone can briefly (and falsely) look unanswered.
        """
        where, values = ["rv.Status IN ('approved','edited','sent')", "rv.Kind<>'action'",
                         "COALESCE(NULLIF(rv.FinalText,''), rv.DraftText, '')<>''"], []
        if message_id is not None:
            where.append('rv.MessageId=?'); values.append(message_id)
        elif task_id is not None:
            where.append('rv.TaskId=?'); values.append(task_id)
        else:
            return None
        return self._one('SELECT rv.* FROM review rv WHERE ' + ' AND '.join(where)
                         + ' ORDER BY IFNULL(rv.DecidedAt, rv.CreatedAt) DESC, rv.ReviewId DESC LIMIT 1', values)
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
            changed = cur.rowcount                 # lastrowid is meaningless on an UPDATE
        if changed: self._poke('feed-changed', 'task-changed', task_id=task_id)
        return changed
    def held_review(self, task_id, mid=None):
        q = "SELECT * FROM review WHERE TaskId=? AND Status='held'" + (' AND MessageId=?' if mid else '') + ' ORDER BY ReviewId DESC LIMIT 1'
        return self._one(q, (task_id, mid) if mid else (task_id,))
    def unhold_review(self, rid, reason=None):
        self._exec("UPDATE review SET Status='pending', Reason=COALESCE(?, Reason) WHERE ReviewId=?", (reason, rid))
        self._review_changed(rid)
    def update_review_reason(self, rid, reason, run_id=None):
        self._exec('UPDATE review SET Reason=?, RunId=COALESCE(?, RunId) WHERE ReviewId=?', (reason, run_id, rid))
        self._review_changed(rid)
    def update_review_draft(self, rid, draft, run_id):
        self._exec('UPDATE review SET DraftText=?, RunId=? WHERE ReviewId=?', (draft, run_id, rid))
        self._review_changed(rid)
    def save_review_draft(self, rid, draft):
        """Persist the owner's editor without erasing which agent run originally produced it."""
        self._exec('UPDATE review SET DraftText=? WHERE ReviewId=?', (draft, rid))
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
                            ('TaskId', 'Agent', 'Cwd', 'Kind', 'Body', 'Files', 'CreatedAt', 'ReadBy'))
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
    _CONN_SAFE = "ConnectorId, Type, Name, ConfigJson, Active, Roles, Scope, LastSyncAt, LastError, (Secret IS NOT NULL AND Secret != '') HasSecret"
    def list_connectors(self): return self._rows(f'SELECT {self._CONN_SAFE} FROM connector ORDER BY ConnectorId')
    def get_connector(self, cid, with_secret=False):
        return self._one(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector WHERE ConnectorId=?", (cid,))
    def connectors_by_type(self, ctype, with_secret=False):
        return self._rows(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector "
                          'WHERE Type=? ORDER BY Active DESC, ConnectorId', (ctype,))
    def get_connector_by_type(self, ctype, with_secret=False):
        """Compatibility/default lookup for code that needs one connection: prefer an active
        instance, then the original catalog row. Instance-aware paths use ConnectorId."""
        rows = self.connectors_by_type(ctype, with_secret)
        return rows[0] if rows else None
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
        if name == 'ingest_status':
            try: extra = json.loads(value) if isinstance(value, str) else {}
            except (TypeError, ValueError): extra = {}
            self._poke('feed-changed', ingest=extra if isinstance(extra, dict) else {})
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
                                           AND x.Status NOT IN ('context','skipped') AND IFNULL(x.Direction,'in') <> 'out'
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

    def feed(self, limit=100, days=14, pending_only=False, channel=None, offset=0, source=None):
        q = f'''SELECT m.MessageId, m.Channel, m.SourceName, m.Subject, m.FromName, m.FromEmail, m.SentAt,
                       m.ConversationId,
                       substr(m.BodyText, 1, 4000) Preview, m.Status MsgStatus, m.SourceLink, m.TaskId, m.Direction, m.Brief,
                       t.Title, t.Status TaskStatus, t.Priority, t.Kind TaskKind, t.Tags TaskTags, {self.NEEDS_YOU} NeedsYou,
                       IFNULL(ch.n, 0) ChainSize,
                       rt.Decision, rt.Reason RouteReason,
                       rv.ReviewId, rv.Status ReviewStatus, rv.Kind ReviewKind, rv.HasDraft,
                       IFNULL(att.n, 0) Attachments,
                       {self.ANSWERED_AT} AnsweredAt,
                       {self.THEIR_TURN} TheirTurn
                FROM message m
                LEFT JOIN task t ON t.TaskId=m.TaskId
                LEFT JOIN (
                    SELECT MessageId, Decision, Reason FROM route
                    WHERE RouteId IN (SELECT MAX(RouteId) FROM route GROUP BY MessageId)
                ) rt ON rt.MessageId=m.MessageId
                LEFT JOIN (
                    SELECT MessageId, ReviewId, Status, Kind, DecidedAt, CreatedAt,
                           CASE WHEN IFNULL(DraftText,'')<>'' THEN 1 ELSE 0 END HasDraft FROM review
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
        live, parked = {r['TaskId']: r.get('AgentName') or 'agent' for r in self.running_runs()}, set()
        try:
            from . import terminal as hub_term
            for t in hub_term.live_sessions(tail=0):
                if not t.get('taskId'): continue
                live[t['taskId']] = t.get('agent') or t.get('label') or 'coder'
                # "an agent has it" and "an agent stopped and is waiting on you" are opposite
                # facts and the row wore the same chip for both, so a session sitting on an
                # unanswered question read as work in progress for as long as nobody looked.
                if t.get('waiting'): parked.add(t['taskId'])
        except Exception:
            pass                                   # no pty support here: runs alone decide
        for r in rows:
            if r.get('TaskId') in live and r.get('TaskStatus') not in ('done', 'dropped'):
                r['Working'] = live[r['TaskId']]
                r['AgentWaiting'] = r['TaskId'] in parked
                if r.get('ReviewStatus') != 'pending': r['NeedsYou'] = 1 if r['TaskId'] in parked else 0
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

    def people(self, limit=60):
        """Everyone who has written to you lately - the hand-off picker's address book."""
        return self._rows("""SELECT FromEmail Email, MAX(FromName) Name, COUNT(*) N, MAX(SentAt) Last
                             FROM message WHERE FromEmail LIKE '%@%' AND Status<>'context'
                             GROUP BY LOWER(FromEmail) ORDER BY Last DESC LIMIT ?""", (int(limit),))

    def chats(self, limit=200):
        """Every chat Taskuary has seen, newest first: the id a message can be SENT to, and a
        name to recognise it by. The id is whatever the channel itself uses - a Graph chat id,
        a WhatsApp JID - which is exactly why nobody can type it from memory."""
        return self._rows("""SELECT Channel, ConversationId Cid,
                                    MAX(CASE WHEN IFNULL(Direction,'in')<>'out' THEN FromName END) Name,
                                    COUNT(*) N, MAX(SentAt) Last
                             FROM message WHERE ConversationId IS NOT NULL AND IFNULL(Channel,'')<>'email'
                             GROUP BY Channel, ConversationId ORDER BY Last DESC LIMIT ?""", (int(limit),))

    def message_routes(self, mid: int) -> list:
        """Every judgement ever made ABOUT THIS MESSAGE, oldest first.

        list_routes is keyed on the TASK, and "not ours" deletes the task - so the one verdict the
        owner most wants to see recorded took its own record away with it. Routes are keyed on the
        message and outlive it."""
        return self._rows('SELECT * FROM route WHERE MessageId=? ORDER BY RouteId', (mid,))

    def task_detail(self, task_id):
        t = self.get_task(task_id)
        if not t: return None
        msgs = self.list_messages(task_id)
        return {'task': t, 'ref': task_ref(task_id), 'messages': msgs,
                'attachments': [a for m in msgs for a in self.list_attachments(m['MessageId'])],
                'artifacts': self.list_task_artifacts(task_id),
                'routes': self.list_routes(task_id), 'comments': self.list_comments(task_id),
                'runs': self.list_runs(task_id), 'audit': self.list_audit('task', task_id),
                'reviews': self._rows('SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId DESC', (task_id,))}

    # ── knowledge base (knowledge.py): documents as passages behind an FTS5 index ──
    def kb_doc(self, cid, source, path):
        return self._one('SELECT * FROM kb_doc WHERE ConnectorId=? AND Source=? AND Path=?', (cid, source, path))
    def kb_put(self, doc: dict, chunks: list) -> int:
        """Replace one document's passages in a single transaction - _exec commits per statement,
        and a library of a thousand files is not a thousand fsyncs per file."""
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
                if self.kb_fts: cur.execute('INSERT INTO kb_fts (Text, ChunkId) VALUES (?,?)', (t, cur.lastrowid))
            self.cx.commit(); self._writes += 1
            return did
    def _kb_drop(self, cur, did):
        if self.kb_fts: cur.execute('DELETE FROM kb_fts WHERE ChunkId IN (SELECT ChunkId FROM kb_chunk WHERE DocId=?)', (did,))
        cur.execute('DELETE FROM kb_chunk WHERE DocId=?', (did,)); cur.execute('DELETE FROM kb_doc WHERE DocId=?', (did,))
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
    def kb_search(self, fts_query: str, limit: int = 8, cid=None) -> list:
        """Passages ranked by bm25 (FTS5) with a snippet around the matches; one hit per document,
        the best passage of each. `fts_query` is FTS5 syntax - knowledge._query builds it safely."""
        if not fts_query: return []
        w, p = (' AND d.ConnectorId=?', (cid,)) if cid else ('', ())
        if self.kb_fts:
            q = ('SELECT d.DocId, d.Name, d.Path, d.Source, d.Modified, c.Seq, bm25(kb_fts) score, '
                 "snippet(kb_fts, 0, '[', ']', ' … ', 48) snip FROM kb_fts JOIN kb_chunk c ON c.ChunkId=kb_fts.ChunkId "
                 f'JOIN kb_doc d ON d.DocId=c.DocId WHERE kb_fts MATCH ?{w} ORDER BY score LIMIT ?')
            rows = self._rows(q, (fts_query, *p, limit * 4))
        else:
            words = [t.strip('"') for t in fts_query.split(' OR ') if t.strip('"')]
            like = ' OR '.join('c.Text LIKE ?' for _ in words)
            rows = self._rows('SELECT d.DocId, d.Name, d.Path, d.Source, d.Modified, c.Seq, 0 score, substr(c.Text, 1, 400) snip '
                              f'FROM kb_chunk c JOIN kb_doc d ON d.DocId=c.DocId WHERE ({like}){w} LIMIT ?',
                              (*[f'%{x}%' for x in words], *p, limit * 4))
        out, seen = [], set()
        for r in rows:
            if r['DocId'] in seen: continue
            seen.add(r['DocId'])
            out.append({'doc_id': r['DocId'], 'name': r['Name'], 'path': r['Path'], 'source': r['Source'], 'modified': r['Modified'] or '',
                        'seq': r['Seq'], 'score': round(-float(r['score']), 3), 'snippet': ' '.join(str(r['snip'] or '').split())})
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
    LORE_STOP = {'the', 'and', 'for', 'you', 'are', 'not', 'with', 'this', 'that', 'have', 'from',
                 'was', 'will', 'has', 'but', 'all', 'our', 'your', 'their', 'its', 'any', 'out',
                 'can', 'when', 'what', 'how', 'why', 'who', 'does', 'did', 'about', 're'}

    def lore_posts(self, topic=None, q=None, limit=50, sort='new', status='live') -> list:
        """Ranked by HOW MANY of the query's distinctive words a post carries, not by whether it
        carries all of them. Requiring all is right for a person typing three words and wrong for
        handbook.block, which hands a whole task's text in - that found nothing at all, because no
        one entry mentions every word of a mail. A post the query touches twice beats one it
        touches once, and the top of that list is what an agent is handed."""
        # the substring runs off the SINGULAR stem so a query's plural finds a singular entry:
        # 'adjustments' must reach a post about an 'adjustment', which is the case that found nothing
        terms = list(dict.fromkeys(t.rstrip('s') for t in re.findall(r'[a-z][a-z0-9-]{2,}', str(q or '').lower())
                                   if t not in self.LORE_STOP))[:12]
        hay = 'lower(l.Title || " " || IFNULL(l.Body,"") || " " || IFNULL(l.Topic,""))'
        score = ' + '.join(f'(CASE WHEN {hay} LIKE ? THEN 1 ELSE 0 END)' for _ in terms) if terms else '0'
        like = [f'%{t}%' for t in terms]
        # params bind in TEXTUAL order across the whole statement: the score expression in SELECT,
        # then the topic in WHERE, then the score expression again in WHERE. ORDER BY uses the
        # alias, which is why it costs no third copy.
        w = (["l.Status='live'"] if status == 'live' else ["l.Status<>'live'"]) + (['l.Topic=?'] if topic else []) + ([f'({score}) > 0'] if terms else [])
        p = [*like] + ([topic] if topic else []) + [*like]
        order = ('Hits DESC, ' if terms else '') + ('l.Score DESC, l.UpdatedAt DESC' if sort == 'top' or terms else 'l.UpdatedAt DESC')
        return self._rows(f'SELECT l.*, ({score}) Hits, (SELECT COUNT(*) FROM lore_comment WHERE LoreId=l.LoreId) Comments '
                          f'FROM lore l WHERE {" AND ".join(w)} ORDER BY {order} LIMIT ?', (*p, int(limit)))
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
