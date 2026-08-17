"""Storage: one small dict-shaped contract, two bindings - SQLite (stdlib, the local-first
default) and in-memory (tests/demo). Every mutation is meant to be paired with .audit();
the audit log is a Buzz-style tamper-evident hash chain (each row hashes the previous).
"""
import hashlib, json, sqlite3, threading
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

def task_ref(task_id): return f'TQ-{int(task_id):04d}'
def _now(): return datetime.now().isoformat(sep=' ', timespec='seconds')

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
  ConfigJson TEXT, Secret TEXT, Active INTEGER DEFAULT 0, LastSyncAt TEXT, LastError TEXT);
CREATE TABLE IF NOT EXISTS setting (Name TEXT PRIMARY KEY, Value TEXT, Description TEXT, UpdatedBy TEXT);
CREATE TABLE IF NOT EXISTS memory (MemoryId INTEGER PRIMARY KEY, Scope TEXT, ScopeKey TEXT, Note TEXT,
  Source TEXT, Active INTEGER DEFAULT 1, CreatedBy TEXT, CreatedAt TEXT);
CREATE TABLE IF NOT EXISTS doc (Name TEXT PRIMARY KEY, Content TEXT, UpdatedBy TEXT, UpdatedAt TEXT);
"""

DEFAULT_SETTINGS = {'default_action': 'draft', 'auto_draft_enabled': '0', 'attach_threshold': '0.42',
                    'feed_days': '14', 'intent_classify_enabled': '1', 'coder_auto_enabled': '0'}


class SQLiteStore:
    """The local-first binding. One connection, a lock (sqlite + threads), rows as dicts."""

    def __init__(self, path):
        self.cx = sqlite3.connect(path, check_same_thread=False)
        self.cx.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.cx.executescript(SCHEMA)
            for k, v in DEFAULT_SETTINGS.items():
                self.cx.execute('INSERT OR IGNORE INTO setting (Name, Value) VALUES (?,?)', (k, v))
            for t, n in (('outlook', 'Outlook mail'), ('teams', 'Microsoft Teams'),
                         ('slack', 'Slack'), ('github', 'GitHub'),
                         ('anthropic', 'Anthropic API'), ('openai', 'OpenAI API'),
                         ('azure_openai', 'Azure OpenAI'), ('mssql', 'Microsoft SQL Server'),
                         ('winrm', 'Remote Windows (WinRM)')):
                self.cx.execute('INSERT OR IGNORE INTO connector (Type, Name) VALUES (?,?)', (t, n))
            # operator documents start from shipped templates (John Smith placeholder) -
            # first run only; the owner's edits are never overwritten
            from pathlib import Path
            for name in ('soul', 'coder', 'digest'):
                f = Path(__file__).parent / 'templates' / f'{name}.md'
                if f.exists():
                    self.cx.execute('INSERT OR IGNORE INTO doc (Name, Content, UpdatedBy, UpdatedAt) VALUES (?,?,?,?)',
                                    (name, f.read_text(encoding='utf-8'), 'template', _now()))
            # data heal: dbs written before review dedupe can hold stacked pending reviews
            # of the same kind on one task - keep the newest, supersede the rest
            self.cx.execute("""UPDATE review SET Status='superseded'
                               WHERE Status='pending' AND ReviewId NOT IN (
                                   SELECT MAX(ReviewId) FROM review WHERE Status='pending'
                                   GROUP BY TaskId, Kind)""")
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
    def list_runs(self, task_id): return self._rows('SELECT * FROM run WHERE TaskId=? ORDER BY RunId DESC', (task_id,))

    # reviews (orphans - reviews whose task is gone - never surface)
    def add_review(self, fields): return self._insert('review', fields, REVIEW_COLS, {'CreatedAt': _now()})
    def get_review(self, rid): return self._one('SELECT * FROM review WHERE ReviewId=?', (rid,))
    def list_reviews(self, status=None):
        q = '''SELECT rv.*, t.Title, m.Subject, m.FromEmail, m.Channel FROM review rv
               JOIN task t ON t.TaskId=rv.TaskId LEFT JOIN message m ON m.MessageId=rv.MessageId'''
        return self._rows(q + (' WHERE rv.Status=?' if status else '') + ' ORDER BY rv.ReviewId DESC', (status,) if status else ())
    def decide_review(self, rid, status, final, by, note=None):
        self._exec('UPDATE review SET Status=?, FinalText=?, DecidedBy=?, DecidedAt=?, DecideNote=? WHERE ReviewId=?',
                   (status, final, by, _now(), note, rid))
    def pending_review(self, task_id, kind=None):
        q = "SELECT * FROM review WHERE TaskId=? AND Status='pending'" + (" AND Kind=?" if kind else "") + " ORDER BY ReviewId DESC LIMIT 1"
        return self._one(q, (task_id, kind) if kind else (task_id,))
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
    _CONN_SAFE = "ConnectorId, Type, Name, ConfigJson, Active, LastSyncAt, LastError, (Secret IS NOT NULL AND Secret != '') HasSecret"
    def list_connectors(self): return self._rows(f'SELECT {self._CONN_SAFE} FROM connector ORDER BY ConnectorId')
    def get_connector(self, cid, with_secret=False):
        return self._one(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector WHERE ConnectorId=?", (cid,))
    def get_connector_by_type(self, ctype, with_secret=False):
        return self._one(f"SELECT {'*' if with_secret else self._CONN_SAFE} FROM connector WHERE Type=?", (ctype,))
    def save_connector(self, fields, actor):
        cid = fields.get('ConnectorId')
        cols = [c for c in ('Type', 'Name', 'ConfigJson', 'Secret', 'Active') if c in fields and fields[c] is not None]
        if cid:
            self._exec(f"UPDATE connector SET {','.join(f'{c}=?' for c in cols)} WHERE ConnectorId=?", [fields[c] for c in cols] + [cid])
            return cid
        return self._insert('connector', fields, ('Type', 'Name', 'ConfigJson', 'Secret', 'Active'))
    def reset_connector(self, cid):
        """'Remove connection': wipe creds/config/test state, deactivate it and its sources."""
        self._exec('UPDATE connector SET Secret=NULL, ConfigJson=NULL, Active=0, LastSyncAt=NULL, LastError=NULL WHERE ConnectorId=?', (cid,))
        self._exec('UPDATE source SET Active=0 WHERE ConnectorId=?', (cid,))
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
        r = self._one('SELECT Content FROM doc WHERE Name=?', (name,)); return r['Content'] if r else None
    def save_doc(self, name, content, actor):
        self._exec('INSERT INTO doc (Name, Content, UpdatedBy, UpdatedAt) VALUES (?,?,?,?) ON CONFLICT(Name) DO UPDATE SET Content=?, UpdatedBy=?, UpdatedAt=?',
                   (name, content, actor, _now(), content, actor, _now()))

    # feed
    def feed(self, limit=100, days=14, pending_only=False, channel=None, offset=0, source=None):
        q = f'''SELECT m.MessageId, m.Channel, m.SourceName, m.Subject, m.FromName, m.FromEmail, m.SentAt,
                       substr(m.BodyText, 1, 4000) Preview, m.Status MsgStatus, m.SourceLink, m.TaskId,
                       t.Title, t.Status TaskStatus, t.Priority,
                       (SELECT Decision FROM route WHERE MessageId=m.MessageId ORDER BY RouteId DESC LIMIT 1) Decision,
                       (SELECT Reason FROM route WHERE MessageId=m.MessageId ORDER BY RouteId DESC LIMIT 1) RouteReason,
                       (SELECT ReviewId FROM review WHERE MessageId=m.MessageId ORDER BY ReviewId DESC LIMIT 1) ReviewId,
                       (SELECT Status FROM review WHERE MessageId=m.MessageId ORDER BY ReviewId DESC LIMIT 1) ReviewStatus,
                       (SELECT Kind FROM review WHERE MessageId=m.MessageId ORDER BY ReviewId DESC LIMIT 1) ReviewKind
                FROM message m LEFT JOIN task t ON t.TaskId=m.TaskId
                WHERE m.CreatedAt >= datetime('now', 'localtime', ?) AND m.Status NOT IN ('context', 'skipped') '''
        p = [f'-{int(days)} days']
        if pending_only:
            q += " AND (SELECT Status FROM review WHERE MessageId=m.MessageId ORDER BY ReviewId DESC LIMIT 1)='pending'"
        if channel: q += ' AND m.Channel=?'; p.append(channel)
        if source: q += ' AND m.SourceName=?'; p.append(source)   # e.g. one mailbox of several
        q += f' ORDER BY m.SentAt DESC, m.MessageId DESC LIMIT {int(limit)} OFFSET {int(offset)}'
        return self._rows(q, p)

    def task_detail(self, task_id):
        t = self.get_task(task_id)
        if not t: return None
        return {'task': t, 'ref': task_ref(task_id), 'messages': self.list_messages(task_id),
                'routes': self.list_routes(task_id), 'comments': self.list_comments(task_id),
                'runs': self.list_runs(task_id), 'audit': self.list_audit('task', task_id),
                'reviews': self._rows('SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId DESC', (task_id,))}


class MemoryStore(SQLiteStore):
    """Tests/demo: the same store on an in-memory database."""
    def __init__(self): super().__init__(':memory:')
