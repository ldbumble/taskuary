"""Storage: one small dict-shaped contract, two bindings - SQLite (stdlib, the local-first
default) and in-memory (tests/demo). Every mutation is meant to be paired with .audit();
the audit log is a Buzz-style tamper-evident hash chain (each row hashes the previous).
"""
import hashlib, json, re, sqlite3, threading
from datetime import datetime

GENESIS = '0' * 64
TASK_COLS = ('Title', 'Summary', 'Kind', 'Status', 'Priority', 'Assignee', 'Source', 'SourceRef', 'Tags')
MSG_COLS = ('TaskId', 'ExternalId', 'ConversationId', 'Channel', 'SourceName', 'Subject',
            'FromName', 'FromEmail', 'SentAt', 'BodyText', 'SourceLink', 'Status')
RUN_COLS = ('Status', 'TraceJson', 'Result', 'LastError', 'SessionId', 'DiffText')
REVIEW_COLS = ('TaskId', 'MessageId', 'RunId', 'Kind', 'DraftText', 'FinalText', 'Status', 'Reason')
POLICY_COLS = ('Name', 'Kind', 'Pattern', 'Action', 'Reason', 'SortOrder', 'Active')
SOURCE_COLS = ('Channel', 'Address', 'Owner', 'ConnectorId', 'Active', 'ConfigJson')
MEMORY_COLS = ('Scope', 'ScopeKey', 'Note', 'Source', 'Active', 'CreatedBy')
ATT_COLS = ('MessageId', 'ExternalId', 'Name', 'ContentType', 'Size', 'ContentId', 'Inline', 'Path')

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

def norm_stamp(s) -> str:
    """One clock for the timeline: every channel's timestamp lands as LOCAL 'YYYY-MM-DD
    HH:MM:SS'. A single path storing raw UTC ISO ('...T18:44:00Z') string-sorted ABOVE later
    local rows ('T' > ' ' at position 10) while displaying as the local afternoon - a
    timeline visibly out of order. Anything unparseable passes through untouched."""
    if not s: return _now()
    try: d = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
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
  SentAt TEXT, BodyText TEXT, SourceLink TEXT, Status TEXT DEFAULT 'routed', CreatedAt TEXT);
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
  Reason TEXT, DecidedBy TEXT, DecidedAt TEXT, DecideNote TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS policy (PolicyId INTEGER PRIMARY KEY, Name TEXT, Kind TEXT, Pattern TEXT,
  Action TEXT, Reason TEXT, SortOrder INTEGER DEFAULT 100, Active INTEGER DEFAULT 1, CreatedBy TEXT);
CREATE TABLE IF NOT EXISTS source (SourceId INTEGER PRIMARY KEY, Channel TEXT, Address TEXT,
  Owner TEXT, ConnectorId INTEGER, Active INTEGER DEFAULT 1, ConfigJson TEXT, LastPolledAt TEXT);
CREATE TABLE IF NOT EXISTS connector (ConnectorId INTEGER PRIMARY KEY, Type TEXT UNIQUE, Name TEXT,
  ConfigJson TEXT, Secret TEXT, Active INTEGER DEFAULT 0, LastSyncAt TEXT, LastError TEXT, Roles TEXT);
CREATE TABLE IF NOT EXISTS setting (Name TEXT PRIMARY KEY, Value TEXT, Description TEXT, UpdatedBy TEXT);
CREATE TABLE IF NOT EXISTS memory (MemoryId INTEGER PRIMARY KEY, Scope TEXT, ScopeKey TEXT, Note TEXT,
  Source TEXT, Active INTEGER DEFAULT 1, CreatedBy TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS doc (Name TEXT PRIMARY KEY, Content TEXT, UpdatedBy TEXT, UpdatedAt TEXT);
CREATE TABLE IF NOT EXISTS dispatchq (QId INTEGER PRIMARY KEY, TaskId INTEGER, BehindTaskId INTEGER,
  Agent TEXT, Reason TEXT, CreatedAt TEXT);
"""

# Out of the box Taskuary WORKS the mail: a job goes to the coding agent, a question gets a
# draft. Both stop short of anything leaving the building - a draft waits for you to send it,
# and a session is one you watch - so ON is a safe default and OFF was just a slower start.
DEFAULT_SETTINGS = {'default_action': 'draft', 'auto_draft_enabled': '1', 'attach_threshold': '0.42',
                    'feed_days': '14', 'intent_classify_enabled': '1', 'coder_auto_enabled': '1',
                    'triage_ai': '',      # '' = first active AI connector | connector:<type> | cli:<agent>
                    'startup_sync_days': '3',       # backfill window when the app starts: catch what arrived while it was shut
                    'vision_enabled': '1',          # send attached images to the AI, when the model can see
                    'report_images_enabled': '1',   # reports hand back a chart, and draw it in the body
                    # the ONE copy of your name. The docs say {{owner}} / {{owner_first}} /
                    # {{owner_email}} and are filled in when an AI reads them - see store.doc().
                    'owner_name': '', 'owner_email': '',
                    # what gets pushed to notify-role channels: off | needs_me | all
                    'notify_level': 'needs_me',
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
                 'telegram': 'trigger,tool', 'whatsapp': 'trigger,tool',
                 'gmail': 'trigger,tool', 'imap': 'trigger,tool',
                 'github': 'tool', 'mssql': 'report,tool', 'winrm': 'report,tool',
                 'database': 'report,tool',
                 'prometheus': 'report,tool', 'datadog': 'report,tool',
                 # aws/azure: the per-OBJECT picker carries the intent (report by default,
                 # which polls nothing) - the card itself is just a connection and a tool
                 'aws': 'report,tool', 'azure': 'report,tool',
                 'jira': 'trigger', 'asana': 'trigger', 'monday': 'trigger',
                 'gitlab': 'trigger', 'azdo': 'trigger', 'linear': 'trigger', 'trello': 'trigger',
                 # notion edits are information, not assignments; discord is a chat channel
                 'notion': 'feed', 'discord': 'trigger,tool',
                 'sentry': 'trigger', 'pagerduty': 'trigger'}
ROLES = ('trigger', 'feed', 'report', 'tool', 'notify')

def roles_of(c) -> set: return {r for r in (c.get('Roles') or '').split(',') if r}


class SQLiteStore:
    """The local-first binding. One connection, a lock (sqlite + threads), rows as dicts."""

    def __init__(self, path):
        self.cx = sqlite3.connect(path, check_same_thread=False)
        self.cx.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.cx.executescript(SCHEMA)
            # columns added after a release: CREATE TABLE IF NOT EXISTS never reaches an
            # existing db, so widen it here (cheap, idempotent)
            have = {r[1] for r in self.cx.execute('PRAGMA table_info(connector)')}
            if 'Roles' not in have: self.cx.execute('ALTER TABLE connector ADD COLUMN Roles TEXT')
            for k, v in DEFAULT_SETTINGS.items():
                self.cx.execute('INSERT OR IGNORE INTO setting (Name, Value) VALUES (?,?)', (k, v))
            for t, n in (('outlook', 'Outlook mail'), ('teams', 'Microsoft Teams'),
                         ('slack', 'Slack'), ('github', 'GitHub'),
                         ('anthropic', 'Anthropic API'), ('openai', 'OpenAI API'),
                         ('azure_openai', 'Azure OpenAI'), ('openrouter', 'OpenRouter'),
                         ('ollama', 'Local models (Ollama)'), ('mssql', 'Microsoft SQL Server'),
                         ('telegram', 'Telegram'), ('whatsapp', 'WhatsApp'),
                         ('gmail', 'Gmail / Google Workspace'), ('imap', 'Any mailbox (IMAP)'),
                         ('winrm', 'Remote Windows (WinRM)'),
                         ('database', 'Any database (connection string)'),
                         ('aws', 'Amazon Web Services'), ('azure', 'Microsoft Azure'),
                         ('jira', 'Jira'), ('asana', 'Asana'), ('monday', 'Monday.com'),
                         ('gitlab', 'GitLab'), ('azdo', 'Azure DevOps'), ('linear', 'Linear'),
                         ('trello', 'Trello'), ('notion', 'Notion'), ('discord', 'Discord'),
                         ('sentry', 'Sentry'), ('pagerduty', 'PagerDuty'),
                         ('prometheus', 'Prometheus'), ('datadog', 'Datadog')):
                self.cx.execute('INSERT OR IGNORE INTO connector (Type, Name, Roles) VALUES (?,?,?)',
                                (t, n, DEFAULT_ROLES.get(t, '')))
            for t, r in DEFAULT_ROLES.items():        # dbs from before roles existed
                self.cx.execute('UPDATE connector SET Roles=? WHERE Type=? AND Roles IS NULL', (r, t))
            # operator documents start from shipped templates (John Smith placeholder) -
            # first run only; the owner's edits are never overwritten
            from pathlib import Path
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
                                 json.dumps({'type': 'digest', 'title': 'Morning digest', 'days': 3,
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
                    self.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(c), sid_))
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
            cur = self.cx.execute(q, p); self.cx.commit(); return cur.lastrowid
    def _insert(self, table, fields, allowed, extra=None):
        d = {k: fields[k] for k in allowed if k in fields and fields[k] is not None} | (extra or {})
        cols = list(d)
        return self._exec(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
                          [d[c] for c in cols])

    # tasks
    def create_task(self, fields, actor):
        return self._insert('task', fields, TASK_COLS, {'CreatedBy': actor, 'CreatedAt': _now()})
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
    def get_task(self, task_id): return self._one('SELECT * FROM task WHERE TaskId=?', (task_id,))
    def list_tasks(self, status=None):
        q = '''SELECT t.*, (SELECT Status FROM review r WHERE r.TaskId=t.TaskId ORDER BY ReviewId DESC LIMIT 1) ReviewStatus,
                      (SELECT Kind FROM review r WHERE r.TaskId=t.TaskId ORDER BY ReviewId DESC LIMIT 1) ReviewKind,
                      (SELECT Status FROM run r2 WHERE r2.TaskId=t.TaskId ORDER BY RunId DESC LIMIT 1) RunStatus,
                      (SELECT AgentName FROM run r2 WHERE r2.TaskId=t.TaskId ORDER BY RunId DESC LIMIT 1) RunAgent FROM task t'''
        return self._rows(q + (' WHERE Status=?' if status else '') + ' ORDER BY TaskId DESC', (status,) if status else ())
    def delete_task(self, task_id):
        for q in ("UPDATE message SET TaskId=NULL, Status='filed' WHERE TaskId=?", 'UPDATE route SET TaskId=NULL WHERE TaskId=?',
                  'DELETE FROM review WHERE TaskId=?', 'DELETE FROM comment WHERE TaskId=?',
                  'DELETE FROM run WHERE TaskId=?', 'DELETE FROM task WHERE TaskId=?'):
            self._exec(q, (task_id,))
    def snapshots(self):
        snaps = []
        for t in self._rows("SELECT * FROM task WHERE Status IN ('open','in_progress','waiting')"):
            ms = self._rows('SELECT * FROM message WHERE TaskId=?', (t['TaskId'],))
            snaps.append({'task_id': t['TaskId'], 'title': t['Title'],
                          'subjects': [m['Subject'] for m in ms if m['Subject']],
                          'senders': [m['FromEmail'] for m in ms if m['FromEmail']],
                          'conversation_ids': [m['ConversationId'] for m in ms if m['ConversationId']],
                          'text': ' '.join([t['Title'] or ''] + [str(m['BodyText'] or '')[:2000] for m in ms])})
        return snaps

    # messages / routes / comments
    def message_exists(self, external_id):
        return self._one('SELECT 1 x FROM message WHERE ExternalId=?', (external_id,)) is not None
    def add_message(self, fields): return self._insert('message', fields, MSG_COLS, {'CreatedAt': _now()})
    def get_message(self, mid): return self._one('SELECT * FROM message WHERE MessageId=?', (mid,))
    def list_messages(self, task_id): return self._rows('SELECT * FROM message WHERE TaskId=? ORDER BY SentAt', (task_id,))
    def scan_messages(self, limit=20000):
        """Just enough of every message to re-run a policy over the history (bodies capped)."""
        return self._rows('SELECT MessageId, TaskId, FromEmail, Subject, Status, SentAt, substr(BodyText, 1, 2000) BodyText '
                          'FROM message ORDER BY MessageId DESC LIMIT ?', (limit,))
    def set_message_status(self, mid, status): self._exec('UPDATE message SET Status=? WHERE MessageId=?', (status, mid))
    def attach_message(self, mid, task_id):
        self._exec("UPDATE message SET TaskId=?, Status='routed' WHERE MessageId=?", (task_id, mid))
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
        d = detail if isinstance(detail, str) or detail is None else json.dumps(detail, default=str)
        last = self._one('SELECT RowHash FROM audit ORDER BY Id DESC LIMIT 1')
        prev = last['RowHash'] if last and last['RowHash'] else GENESIS
        rh = chain_hash(prev, _audit_payload(et, eid, action, actor, actor_type, run_id, d))
        self._exec('INSERT INTO audit (EntityType,EntityId,Action,Actor,ActorType,RunId,Detail,PrevHash,RowHash,CreatedAt) VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (et, eid, action, actor, actor_type, run_id, d, prev, rh, _now()))
    def list_audit(self, et=None, eid=None, limit=200):
        if et: return self._rows('SELECT * FROM audit WHERE EntityType=? AND EntityId=? ORDER BY Id DESC LIMIT ?', (et, eid, limit))
        return self._rows('SELECT * FROM audit ORDER BY Id DESC LIMIT ?', (limit,))
    def verify_audit_chain(self):
        prev, bad = GENESIS, []
        for r in self._rows('SELECT * FROM audit ORDER BY Id'):
            exp = chain_hash(prev, _audit_payload(r['EntityType'], r['EntityId'], r['Action'], r['Actor'], r['ActorType'], r['RunId'], r['Detail']))
            if r['RowHash'] != exp or r['PrevHash'] != prev: bad.append(r['Id'])
            prev = r['RowHash'] or exp
        return {'rows': len(self._rows('SELECT Id FROM audit')), 'ok': not bad, 'broken_ids': bad}

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
    def enqueue_dispatch(self, task_id, behind, agent, reason):
        if self._one('SELECT 1 x FROM dispatchq WHERE TaskId=?', (task_id,)): return None
        return self._exec('INSERT INTO dispatchq (TaskId,BehindTaskId,Agent,Reason,CreatedAt) VALUES (?,?,?,?,?)',
                          (task_id, behind, agent, reason, _now()))
    def queued_dispatches(self): return self._rows('SELECT * FROM dispatchq ORDER BY QId')
    def clear_dispatch(self, task_id): self._exec('DELETE FROM dispatchq WHERE TaskId=?', (task_id,))

    # reviews (orphans - reviews whose task is gone - never surface)
    def add_review(self, fields): return self._insert('review', fields, REVIEW_COLS, {'CreatedAt': _now()})
    def get_review(self, rid): return self._one('SELECT * FROM review WHERE ReviewId=?', (rid,))
    def list_reviews(self, status=None):
        # LEFT JOIN: a reply opened on a FILED message carries no task at all - the inner join
        # made those reviews invisible everywhere, including the pending queue.
        # A PENDING review must also point at work you can still SEE: a task folded away
        # (dropped/merged/done) or a message a skip policy hid would otherwise keep the
        # badge at 1 with nothing on the timeline to answer - the queue self-heals instead.
        # Decided reviews keep their history whatever happened to the task since.
        q = '''SELECT rv.*, t.Title, m.Subject, m.FromEmail, m.Channel FROM review rv
               LEFT JOIN task t ON t.TaskId=rv.TaskId LEFT JOIN message m ON m.MessageId=rv.MessageId
               WHERE (rv.TaskId IS NULL OR t.TaskId IS NOT NULL)
                 AND NOT (rv.Status='pending' AND (IFNULL(t.Status,'') IN ('dropped','done')
                                                   OR IFNULL(m.Status,'') IN ('context','skipped','ignored')))'''
        return self._rows(q + (' AND rv.Status=?' if status else '') + ' ORDER BY rv.ReviewId DESC', (status,) if status else ())
    def decide_review(self, rid, status, final, by, note=None):
        self._exec('UPDATE review SET Status=?, FinalText=?, DecidedBy=?, DecidedAt=?, DecideNote=? WHERE ReviewId=?',
                   (status, final, by, _now(), note, rid))
    def pending_review(self, task_id, kind=None):
        q = "SELECT * FROM review WHERE TaskId=? AND Status='pending'" + (" AND Kind=?" if kind else "") + " ORDER BY ReviewId DESC LIMIT 1"
        return self._one(q, (task_id, kind) if kind else (task_id,))
    def hold_reviews(self, task_id, reason=None):
        """Park this task's pending reply drafts while an agent works it. A draft written from the
        mail alone promises what the session has not found yet - and it sat in Review as if it
        were ready to send. Held leaves the queue; the wrap-up brings it back, rewritten."""
        with self.lock:
            cur = self.cx.execute("UPDATE review SET Status='held', Reason=COALESCE(?, Reason) "
                                  "WHERE TaskId=? AND Status='pending' AND Kind IN ('draft','draft_reply')",
                                  (reason, task_id))
            self.cx.commit()
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
    def get_source(self, sid): return self._one('SELECT * FROM source WHERE SourceId=?', (sid,))
    def delete_source(self, sid): self._exec('DELETE FROM source WHERE SourceId=?', (sid,))
    def delete_agent(self, name): self._exec('DELETE FROM agent WHERE Name=?', (name,))

    # channel connectors (secrets are write-only: list/get never return them)
    _CONN_SAFE = "ConnectorId, Type, Name, ConfigJson, Active, Roles, LastSyncAt, LastError, (Secret IS NOT NULL AND Secret != '') HasSecret"
    def list_connectors(self): return self._rows(f'SELECT {self._CONN_SAFE} FROM connector ORDER BY ConnectorId')
    def get_connector(self, cid, with_secret=False):
        return self._one(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector WHERE ConnectorId=?", (cid,))
    def get_connector_by_type(self, ctype, with_secret=False):
        return self._one(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector WHERE Type=?", (ctype,))
    def save_connector(self, fields, actor):
        cid = fields.get('ConnectorId')
        cols = [c for c in ('Type', 'Name', 'ConfigJson', 'Secret', 'Active', 'Roles') if c in fields and fields[c] is not None]
        if cid:
            self._exec(f"UPDATE connector SET {','.join(f'{c}=?' for c in cols)} WHERE ConnectorId=?", [fields[c] for c in cols] + [cid])
            return cid
        return self._insert('connector', fields, ('Type', 'Name', 'ConfigJson', 'Secret', 'Active', 'Roles'))
    def reset_connector(self, cid):
        """'Remove connection': wipe creds/config/test state, deactivate it and its sources."""
        self._exec('UPDATE connector SET Secret=NULL, ConfigJson=NULL, Active=0, LastSyncAt=NULL, LastError=NULL WHERE ConnectorId=?', (cid,))
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
    def known_sender(self, email):
        return bool(email) and self._one('SELECT 1 x FROM message WHERE FromEmail=? LIMIT 1', (email,)) is not None
    def add_memory(self, fields): return self._insert('memory', fields, MEMORY_COLS, {'CreatedAt': _now()})
    def list_memories(self, active_only=True):
        return self._rows('SELECT * FROM memory' + (' WHERE Active=1' if active_only else '') + ' ORDER BY MemoryId DESC')
    def set_memory_active(self, mid, active): self._exec('UPDATE memory SET Active=? WHERE MemoryId=?', (1 if active else 0, mid))
    def get_doc(self, name):
        """The document AS WRITTEN - placeholders and all. This is what the editor loads and saves;
        every consumer that feeds a doc to an AI wants `doc()` instead."""
        r = self._one('SELECT Content FROM doc WHERE Name=?', (name,)); return r['Content'] if r else None
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
    NEEDS_YOU = """(CASE WHEN (SELECT Status FROM review WHERE MessageId=m.MessageId ORDER BY ReviewId DESC LIMIT 1)='pending'
                          OR (m.TaskId IS NOT NULL AND t.Status NOT IN ('done', 'dropped')
                              AND NOT EXISTS (SELECT 1 FROM run WHERE TaskId=m.TaskId AND Status='running'))
                    THEN 1 ELSE 0 END)"""

    def feed(self, limit=100, days=14, pending_only=False, channel=None, offset=0, source=None):
        q = f'''SELECT m.MessageId, m.Channel, m.SourceName, m.Subject, m.FromName, m.FromEmail, m.SentAt,
                       substr(m.BodyText, 1, 4000) Preview, m.Status MsgStatus, m.SourceLink, m.TaskId,
                       t.Title, t.Status TaskStatus, t.Priority, {self.NEEDS_YOU} NeedsYou,
                       (SELECT COUNT(*) FROM message x WHERE x.TaskId=m.TaskId AND x.Status<>'context') ChainSize,
                       (SELECT Decision FROM route WHERE MessageId=m.MessageId ORDER BY RouteId DESC LIMIT 1) Decision,
                       (SELECT Reason FROM route WHERE MessageId=m.MessageId ORDER BY RouteId DESC LIMIT 1) RouteReason,
                       (SELECT ReviewId FROM review WHERE MessageId=m.MessageId ORDER BY ReviewId DESC LIMIT 1) ReviewId,
                       (SELECT Status FROM review WHERE MessageId=m.MessageId ORDER BY ReviewId DESC LIMIT 1) ReviewStatus,
                       (SELECT Kind FROM review WHERE MessageId=m.MessageId ORDER BY ReviewId DESC LIMIT 1) ReviewKind,
                       (SELECT COUNT(*) FROM attachment a WHERE a.MessageId=m.MessageId) Attachments
                FROM message m LEFT JOIN task t ON t.TaskId=m.TaskId
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
        return self._rows(q, p)

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
