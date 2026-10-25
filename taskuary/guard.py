"""What an agent may not do, decided in code and nowhere else.

Everything an agent reads is untrusted. The mail it is working IS the prompt; so is the web page
it opened, the issue somebody filed, the document it indexed. Any of them can contain a sentence
telling it to go and send something, and the whole design of this app rests on the promise that
nothing leaves without the owner pressing a button.

That promise was made in PROSE. SOUL.md says what the agents may do, CODING.md says not to push,
the seed prompt says ask before assuming - and every one of those is a paragraph the same
untrusted text sits next to and can argue with. An instruction is not a control. A model that
has been talked into believing the owner wants an immediate reply will find the local API,
which until now answered any process on the machine, and approve its own draft.

So the rule moves out of the documents:

- Sessions run with an AGENT TOKEN in their environment (terminal.session_env). Every request
  carrying it is agent scope.
- Agent scope may READ, and may WRITE only through the doors on AGENT_WRITES below - the hooks,
  `taskuary --reply/--done`, the wall, the Hub, the data tools and a report rerun. Every other
  write is the owner's, refused by path in the middleware before a handler exists. There is no
  setting for it, no document that relaxes it, and no argument that reaches it - the lists are
  this file, and this file is code.
- Approving a reply, sending a message, changing where mail goes and reading or writing
  credentials are all on the deny list, with their reasons. So is granting scope, because the obvious next move for a
  cornered model is to widen its own permissions.

WHAT THIS DOES NOT DO, said plainly because a security control nobody understands the edges of
is worse than none: an agent runs as the same operating-system user as Taskuary, so it can read
~/.taskuary/taskuary.db and everything in it, including the connector credentials, and it can
run `curl` without the token and be treated as the owner unless a token is configured. Two
things follow. First, set [server].token - `ensure_tokens` writes one on first run and the
browser is handed it, so this costs the owner nothing and closes the anonymous door. Second,
the connector secrets are SEALED in the database now (vault.py: DPAPI on Windows, the keychain
elsewhere), so the file alone - a copy, a backup - no longer carries the keys. That is not
isolation: DPAPI opens for any program running as this user, an agent included. Real isolation
needs a separate sender that alone can decrypt them; that is not built. What IS built is that no
prompt, no API response and no tool result ever hands them over, and that the one road from "an
agent wants this sent" to "it is sent" runs through a person.
"""
import hashlib
import hmac
import json
import re
import secrets as _secrets
from loguru import logger

AGENT_ENV = 'TASKUARY_TOKEN'          # what a session carries; the CLI reads it for --note/--done
TASK_ENV, TASK_HDR = 'TASKUARY_TASK_TOKEN', 'X-Taskuary-Task-Token'   # ...and the proof of WHICH task it is on
OWNER, AGENT, ANON, STRANGER = 'owner', 'agent', 'anon', 'stranger'

# ── THE DENY LIST ───────────────────────────────────────────────────────────────────────
# (method regex, path regex, why). Matched against the request before routing. Add to it when
# a new route can make something leave the machine or can widen what an agent may reach; never
# make it conditional on a setting, and never let a document turn an entry off.
DENIED = (
    (r'POST', r'^/api/tasks/\d+/(resume|continue-session)$', 'resuming previous work is the owner\'s choice'),
    # an agent never answers its own question - and an answer now lets a held ask go (hooks.ask, 2026-09-28)
    (r'POST', r'^/api/tasks/\d+/worker/(answer|answers|release)$', 'answering an agent\'s question is the owner\'s'),
    # anything that puts a message in front of a human somewhere else
    (r'POST', r'^/api/reviews/\d+/decide$', 'approving a reply sends it - that is the owner\'s'),
    (r'POST', r'^/api/tasks/\d+/handoff$', 'handing work to a person sends them a message'),
    (r'POST', r'^/api/outbox$', 'starting an outbound message is the owner\'s door, not an agent\'s'),
    (r'POST', r'^/api/messages/\d+/reply$', 'opening a reply is the first half of sending one'),
    (r'POST', r'^/api/tasks/\d+/clarify$', 'opening a clarification is the first half of sending one'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(connectors|sources)', 'credentials and where mail goes'),
    (r'GET', r'^/api/send-targets$', 'the address book of everywhere this install can send'),
    (r'POST|DELETE', r'^/api/shares(/\d+)?$', 'sharing a result puts it in front of someone else - a draft, a link, an upload (sharing.py)'),
    # a sign-in is typed by the server and only on the owner's say-so: no session mints a fill page, reads which sites are kept, removes
    # one, or opens a fill page it was never shown (signin.py) - reading the list alone would tell a session where the owner banks
    (r'GET|POST|DELETE', r'^/api/signins(/|$)', "the owner's saved sign-ins (signin.py)"),
    (r'POST', r'^/api/tasks/\d+/signin/link$', "a fill page types a password into the browser - only ever the owner's press"),
    (r'GET|POST', r'^/signin/', "the fill page is the owner's"),
    # ...and anything that would let it widen its own reach
    (r'POST|PUT|PATCH', r'^/api/settings', 'the settings decide what agents may do'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(policies|agents)', 'the rules and the agent profiles'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(docs?|playbooks)(/|$)', 'SOUL.md, the playbooks and the rest are the owner\'s word, not an agent\'s - propose, do not write'),
    # importing a skill does BOTH of the two above - an agent row and a rules document - through a
    # prefix neither one covers. GET /api/skills/found is not here: it lists files on this disk that
    # a session's own shell can already read, and writes nothing.
    (r'POST', r'^/api/skills/import$', 'importing a skill makes a worker and writes its rules - an agent does not get to hire itself'),
    (r'POST', r'^/api/skills/read$', 'turning a file on this machine into a proposed worker is the first half of hiring one'),
    (r'POST', r'^/api/skills/fetch$', 'pulling a document off the internet to propose a worker is the same half, from further away'),
    (r'POST', r'^/api/skills/list$', 'reading what a link or a folder holds is where hiring one starts, and it reaches the internet to do it'),
    (r'POST', r'^/api/update$', 'replacing the program is the owner\'s decision'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(invoice-batches|reports/\d+/invoice-batches)(/|$)',
     'preparing or changing an invoice batch is the owner\'s decision'),
    (r'POST', r'^/api/deps/', 'installing software on this machine is the owner\'s decision'),
    (r'POST', r'^/api/cli/(install|update)', "installing or updating a coding CLI runs a vendor installer on this machine - the owner's decision"),
    (r'POST', r'^/api/cli/setup', "setting a coding CLI up runs it on this machine, and signs in as the owner - their decision"),
    (r'POST', r'^/api/setup/first-run/', "choosing the AI that reads the mail, or the mailbox it reads, is the owner's decision"),
    (r'POST', r'^/api/signature/', "the signature under the owner's email is theirs to read off their mail and check"),
    (r'PUT|DELETE|POST', r'^/api/cli/connections', 'CLI commands and connection tests are configured by the owner'),
    (r'POST', r'^/api/problems/', 'what is failing is the owner\'s to read - an agent does not get to clear the bell'),
    # ...and the doors the 2026-09-02 audit found standing open: releasing the held task of the very
    # sender the hold exists for, landing work, running an executor or a query with a card's
    # credentials, and rewriting the documents that govern the agent
    (r'POST', r'^/api/tasks/\d+/(release|land|ci)$', 'releasing a held task or landing its work is the owner\'s decision'),
    (r'POST', r'^/api/tasks/\d+/dispatch/retry$', 'retrying a queued start is the owner\'s decision'),
    (r'DELETE', r'^/api/tasks/\d+/dispatch$', 'cancelling a queued start is the owner\'s decision'),
    (r'POST', r'^/api/(soul|learn)(/|$)', 'SOUL.md and LEARNED.md are the owner\'s word - propose, do not write'),
    (r'PUT|PATCH', r'^/api/(owner|whoami)$', 'who the owner is'),
    (r'POST', r'^/api/(mcp|mssql)/', 'runs a command, or sends saved credentials to a host of the caller\'s choosing'),
    (r'POST', r'^/api/(reports/(preview|compose|compose-sources)|workflows/compose|dashboards/(compose|preview))$',
     'the report/workflow composer may read a connected system with the card\'s credentials'),
    # testing a step reads a connected system with the card's credentials; a repair rewrites a saved workflow
    (r'POST', r'^/api/workflows/(step-test|\d+/repair)$',
     "a workflow's steps - testing one reads with the card's credentials, a repair changes what runs on its schedule"),
    (r'POST|PUT|PATCH|DELETE', r'^/api/semantic(/|$)', 'a metric spec is SQL run against a database of its choosing'),
    # a live pty is a shell as the owner. Agents already dispatch through terminal.start_on_task;
    # this HTTP door is the one the owner sits in (server.open_terminal). GET listing/screen stay.
    (r'POST', r'^/api/terminals$', 'opening a live session is the owner\'s door'),
    (r'DELETE', r'^/api/terminals/', 'closing a live session is the owner\'s door'),
)

# ── THE ALLOW LIST ──────────────────────────────────────────────────────────────────────
# A deny list only shuts the doors somebody remembered. POST /api/operations + /execute runs
# review.approve, setting.set and task.handoff - the very acts DENIED names - under a path it did
# not, and PUT /api/reviews/<rid>/envelope re-addressed any task's pending reply (audit 2026-10-05).
# So a WRITE from an agent is refused unless it is HERE. Each entry is a door a session is actually
# handed - by hooks.py, cli.py or concierge.tools_block - and nothing more.
AGENT_WRITES = (
    (r'POST', r'^/api/hooks/[a-z]+$', 'a CLI hook reporting its own session (hooks.command)'),
    (r'POST', r'^/api/hooks/claude/ask$', 'the ask hook - it shows the question; the owner answers it'),
    (r'POST', r'^/api/hooks/claude/(floor|permit)$', "a stranger's session asking the floor, or the owner, before a tool call"),
    (r'POST', r'^/api/hooks/claude/reason$', "the Reason Network hook - a message to someone untrusted is refused, an approval goes to the owner"),
    (r'POST', r'^/api/agent/(reply|done|draft|item|tick|waiting)$',
     "`taskuary --reply/--done/--draft/--item/--tick/--waiting-on` on the session's OWN task (owns_task); nothing leaves"),
    (r'POST', r'^/api/agent/propose$', "an act only the owner's press runs (proposals.queue), filed on the session's OWN task; nothing runs"),
    (r'POST', r'^/api/mcp$', "Taskuary's own tools for the session (agenttools): each one is a door on this list or a read, on its OWN task"),
    (r'POST', r'^/api/board/notes$', 'the wall agents leave lines for each other on'),
    (r'POST', r'^/api/(hub|handbook)(/\d+/(comment|vote|retire|restore))?$',
     "the Hub - post, correct, vote, retire what is no longer true; gated again by the card's hub_write scope"),
    (r'POST', r'^/api/tools/run$', 'a data tool, gated per card by scopes.require - and a send waits as a proposal (scopes.reaches)'),
    (r'POST', r'^/api/reports/\d+/rerun$', 'a report run as its schedule would run it (concierge.tools_block) - no configuration changes'),
)

# ── THE READS A SESSION IS HANDED, NAMED ────────────────────────────────────────────────
# Every GET is 'read' to an agent (classify), so these need no allowance - they are listed because a session is TOLD of them
# (general.HISTORY_LINE, cli.py), and a door it is told of is a decision: each reads on the session's OWN task (owns_task),
# and a stranger's session is refused by stranger_denied, which names none of them.
AGENT_READS = (
    (r'GET', r'^/api/agent/messages(/\d+)?$',
     "`taskuary --search/--message`: the owner's mail and messages, read-only (mailsearch.py) - never a stranger's task"),
)

# ── EVERY OTHER WRITE, NAMED ────────────────────────────────────────────────────────────
# Refused to an agent whether or not it is listed - the default in classify() does that. It is
# listed so that test_guard walks app.routes and FAILS on a write route nobody classified: a new
# door is a decision, not something that inherits whatever the table happened to say.
OWNER_ONLY = (
    # the first thing a cornered model would do is mark the send tool it was denied as one that does not send (sendfilter)
    (r'POST', r'^/api/sendfilter/(correct|scan)$', "which of the owner's own MCP tools count as sends is the owner's word"),
    (r'POST', r'^/api/(bug-report/draft|open-url)$', "a bug report is drafted from the owner's own screen, and only the owner's click opens a page on their desktop"),
    (r'POST', r'^/api/messages/\d+/unsubscribe$', "leaving a mailing list is the owner's press - a newsletter's words never reach it (unsubscribe.py)"),
    (r'POST', r'^/api/messages/\d+/calendar$',"answering an invite or drafting one is the owner's - drafted for their Send (calwrite)"),
    (r'POST', r'^/api/concierge/chats/\d+/continue$', "continuing an earlier Assistant chat is the owner's own conversation"),
    (r'PATCH', r'^/api/tasks/\d+/checklist/[^/]+/note$', "a note on one of a task's to-dos is the owner's (the agent writes through its own task tools)"),
    (r'POST', r'^/api/advice/press$', "the owner's own press, recorded against what the Advisor lit (learn.moves)"),
    (r'POST', r'^/api/launch-key$', "a launch key opens a page that carries the owner token (launchkey.py, R29)"),
    (r'POST', r'^/api/tasks/\d+/trust$', "raising a task's origin is the owner's decision (origin.raise_to) - never a session's"),
    (r'POST', r'^/api/reason/(trusted|gate|folder|held/[0-9A-Za-z]+)$', "who may reach the owner's agents over Reason Network is the owner's"),
    (r'POST', r'^/api/tasks/\d+/reason-ask$', "asking a teammate's agent is the owner's - an agent uses its own Reason Network tools"),
    (r'POST', r'^/api/cloudfix/setup$', 'it commits a workflow to the repository - only ever the owner pressing Set up (cloudfix.install)'),
    (r'POST|PATCH|DELETE', r'^/api/operations(/[^/]+(/(execute|preview))?)?$',
     'a proposal runs approvals, settings and hand-offs - confirming one is the owner, whatever its kind'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/reviews/\d+(/(attachment|closeout/[a-z_-]+|draft|envelope|release|reopen))?$',
     "a pending reply - its words, recipients and attachments - is the owner's; an agent drafts through --reply"),
    (r'POST', r'^/api/concierge/[a-z/]+$', "the owner's chat with the assistant"),
    (r'POST', r'^/api/assistant/(dock(/new)?|doorways(/listens)?|ideas/[^/]+/[^/]+)$', "the assistant's dock, doorways and ideas"),
    (r'POST|PATCH', r'^/api/tasks(/purge-dropped|/\d+)?$', 'making, editing and purging tasks'),
    (r'POST|PUT|PATCH', r'^/api/tasks/\d+/(agent/stop|assistant/(browser|cancel|messages|session|stream)|checklist(/\d+)?'
                        r'|batch/\d+|batch-combine|code|comments|continue|continue-work|discussion|dispatch|merge|not-a-task|not-coding|pause|remind|repo'
                        r'|split|wrap|answer|read-ask|steps/\w+/start)$', 'steering a task - and a comment here is written as the owner'),
    (r'POST|DELETE', r'^/api/tasks/\d+/waitroom(/bulk|/image|/\d+)?$', 'the waiting room is what the owner tells the agent'),
    (r'POST', r'^/api/tasks/\d+/emails$', "an email the owner starts from a task - an agent drafts one through --draft"),
    (r'POST', r'^/api/messages/\d+/(attachments/fetch|discussion|dispatch|file|ignore-sender|mine|not-mine|reclassify'
              r'|retriage|split|transcribe)$', "what a message is and where it goes is the owner's call"),
    (r'POST', r'^/api/messages/retriage-failed$', "re-judging every message triage failed on is the owner's call, as one is"),
    (r'POST|DELETE', r'^/api/funnel/(\d+/(later|pin)|mutes/\d+|rerank|settle)$', "the owner's pile"),
    (r'POST', r'^/api/board/notes/\d+/read$', "the owner's read mark"),
    (r'POST|PATCH', r'^/api/memory(/\d+)?$', 'memory notes steer triage - an agent proposes one, it does not write it'),
    (r'POST', r'^/api/notes$', "a note to self is the owner's"),
    (r'POST', r'^/api/ingest/(poll|push)$', 'putting a message in the inbox would let an agent write its own next prompt'),
    (r'POST', r'^/api/(ai/defaults|setup/(adopt-brain|dismiss|seen|walk|walk/reset)|knowledge/reindex|calendar/prep|prompt-image)$',
     "set-up, the brains, the index and the owner's own starts"),
    (r'POST', r'^/api/reports/(\d+/replay|due)$', "replaying a judge or running every due report is the owner's"),
    (r'POST', r'^/api/roles/[a-z0-9_-]+$', "a role decides where the owner's mail goes and narrows a ledger's authority"),
    (r'POST', r'^/api/platform/macos/(open-settings|probe)$', "operating-system permission prompts are the owner's"),
    (r'POST', r'^/api/deleted/\d+/restore$', "Undo and Restore put back what the owner removed - a report, a rule, a profile, a sign-in (recentlydeleted)"),
    (r'POST|PUT', r'^/api/voice/(transcribe|vocabulary)$', "the owner's microphone and vocabulary"),
    (r'POST', r'^/api/terminals/[^/]+/(browser/(open|snapshot|viewport)|image|pause|wrap)$', 'the pane the owner is watching'),
)
_c = lambda t: tuple((re.compile(f'^({m})$', re.I), re.compile(p), why) for m, p, why in t)
_DENIED, _ALLOW, _OWNER = _c(DENIED), _c(AGENT_WRITES), _c(OWNER_ONLY)
READS = ('GET', 'HEAD', 'OPTIONS')
UNLISTED = 'changing things is the owner\'s, and this door is not on the agent allow-list (guard.AGENT_WRITES)'


def _hit(table, method, path) -> str:
    return next((why for m, p, why in table if m.match(method or '') and p.match(path or '')), '')


def classify(method: str, path: str) -> tuple:
    """('deny'|'read'|'agent'|'owner'|'unlisted', why). 'unlisted' is refused like 'owner' - it only
    tells the route-walk test that a write door was never decided."""
    if why := _hit(_DENIED, method, path): return 'deny', why
    if (method or '').upper() in READS: return 'read', ''
    if why := _hit(_ALLOW, method, path): return 'agent', why
    if why := _hit(_OWNER, method, path): return 'owner', why
    return 'unlisted', UNLISTED


def denied(method: str, path: str) -> str:
    """'' when an agent may call this, else why not. Pure, so the whole table is testable."""
    k, why = classify(method, path)
    return '' if k in ('read', 'agent') else why


def task_proof(server: dict, tid) -> str:
    """What a session on task `tid` carries (terminal.session_env) to show the task is its own. The
    agent token is one secret every session shares, so alone it cannot tell a session drafting its
    own reply from one rewriting a neighbour's; a keyed hash of the task id can, and needs no table.
    '' with no agent token - there is then no agent scope to narrow."""
    k = str(server.get('agent_token') or '')
    return hmac.new(k.encode(), f'task:{int(tid)}'.encode(), hashlib.sha256).hexdigest()[:32] if k else ''


def owns_task(server: dict, headers, tid) -> bool:
    """The owner owns every task; an agent only the one its session was started on; a stranger's session only the one
    its token names."""
    sc = scope_of(server, headers)
    if sc == STRANGER: return stranger_tid(server, headers.get('X-Taskuary-Token')) == int(tid)
    if sc != AGENT: return True
    return token_matches(headers.get(TASK_HDR), task_proof(server, tid))


# ── A STRANGER'S SESSION (R28) ──────────────────────────────────────────────────────────────────────────────────────
# The agent token is one secret every session shares, and agent scope READS every route - the feed, every message, the
# connectors. A session driven by a stranger's words must not hold it: its floor checks the command text, not what the
# environment hands a child process. So it carries a token bound to its task instead, and that token reads its own task
# and uses its own task's doors, nothing more. Keyed like task_proof, but under its own label, so neither can be made
# from the other.
_STRANGER_TOK = re.compile(r's1\.(\d{1,12})\.[0-9a-f]{32}')

def stranger_token(server: dict, tid) -> str:
    "What a stranger-origin session carries as TASKUARY_TOKEN. '' with no agent token - then there is no secret to key it."
    k = str(server.get('agent_token') or '')
    return f's1.{int(tid)}.' + hmac.new(k.encode(), f'stranger:{int(tid)}'.encode(), hashlib.sha256).hexdigest()[:32] if k else ''

def stranger_tid(server: dict, presented) -> int | None:
    "The task a presented stranger token is bound to, or None. Constant-time, through token_matches."
    m = _STRANGER_TOK.fullmatch(str(presented or ''))
    if not m: return None
    tid = int(m[1])
    return tid if token_matches(presented, stranger_token(server, tid)) else None

# Writes a stranger's session is handed - its session-file hooks, the user-scope event hook, and `taskuary --reply/--done/
# --draft/--item/--tick`, whose task id owns_task checks in the handler - and `taskuary --note`, whose note the board door pins to
# the token's own task, so it never reaches another session's seed (blackboard.live_notes, wave B). Not the Hub, the data
# tools or a report rerun: each of those reaches past its own task.
_STRANGER_WRITES = (re.compile(r'^/api/hooks/[a-z]+$'), re.compile(r'^/api/agent/(reply|done|draft|item|tick|waiting)$'), re.compile(r'^/api/board/notes$'))
_STRANGER_TASK_HOOK = re.compile(r'^/api/hooks/claude/(floor|permit)$')
_STRANGER_FILE = re.compile(r'^/api/(attachments|task-artifacts)/(\d+)$')
STRANGER_WHY = "a session working a stranger's task reaches its own task and nothing else"
STRANGER_TASK_READS = ('history', 'worker', 'proof', 'work', 'diff', 'record', 'waitroom')   # each answers for this task only

def stranger_denied(method: str, path: str, query, tid: int, owner_of) -> str:
    """'' when a stranger's session on `tid` may call this, else why not. `owner_of(kind, id)` answers which task an
    attachment ('attachment') or a session artifact ('artifact') belongs to - the one store question the table needs."""
    m, path = (method or '').upper(), path or ''
    if why := _hit(_DENIED, m, path): return why
    if m in READS:
        # its own task and the parts of it a session reads - named, so a new route is refused until someone decides it.
        # Not /merge-candidates (other tasks' titles), /repos (checkouts on this machine), /steps (child tasks),
        # /split/suggest (a model call on a GET) or /assistant (the install's brains).
        if re.fullmatch(rf'/api/tasks/{int(tid)}(/({"|".join(STRANGER_TASK_READS)}))?', path): return ''
        # ...and the files its own agent made for it (outputs.py) - the route confines the name to that task's folder
        if re.fullmatch(rf'/api/task-outputs/{int(tid)}(/.+)?', path): return ''
        if f := _STRANGER_FILE.match(path):
            return '' if owner_of('attachment' if f[1] == 'attachments' else 'artifact', int(f[2])) == int(tid) else STRANGER_WHY
        return STRANGER_WHY
    if _STRANGER_TASK_HOOK.match(path): return '' if str((query or {}).get('task') or '') == str(int(tid)) else STRANGER_WHY
    return '' if any(p.match(path) for p in _STRANGER_WRITES) else STRANGER_WHY


def token_matches(got, *want) -> bool:
    """True if `got` is one of the secrets in `want`. Compared as BYTES, which is the only form
    hmac.compare_digest takes for arbitrary input: handed str it refuses anything non-ASCII, and a
    header is decoded latin-1, so one high byte on the wire raised TypeError and the middleware
    turned a wrong token into a 500 instead of a refusal. Bytes also make a length mismatch an
    ordinary miss, so there is no length test to get wrong."""
    g = str(got or '').encode('utf-8', 'surrogateescape')
    for w in want:
        w = str(w or '').encode('utf-8', 'surrogateescape')
        if w and hmac.compare_digest(g, w): return True
    return False


def scope_of(cfg: dict, headers) -> str:
    """Who is calling. The agent token is the only thing that says 'agent'; everything else is
    treated as the owner, which is the honest description of a localhost app - see the module
    docstring on what that does and does not buy."""
    tok = str(headers.get('X-Taskuary-Token') or '')
    if token_matches(tok, cfg.get('agent_token')): return AGENT
    if stranger_tid(cfg, tok) is not None: return STRANGER   # before the open no-token case: a stranger is never the owner
    owner = str(cfg.get('token') or '')
    if not owner: return OWNER                     # no token configured: the old, open behaviour
    return OWNER if token_matches(tok, owner) else ANON


# ── WHO IS ON THE OTHER END OF THE SOCKET ──────────────────────────────────
# A token proves the CALLER knows a secret. These two prove the caller is not a web page the
# owner merely visited - which a token alone cannot, because a browser will happily attach
# whatever it has to a request some other site asked it to make (audit 2026-09-02, F03).
#
#   host_ok    DNS rebinding needs a NAME the attacker controls and can re-point at 127.0.0.1.
#              An IP literal cannot be rebound - a browser only ever sends back the name it
#              looked up - so IP Hosts pass and names must be on the list. Without this a page
#              on evil.example reads the whole mailbox through the loopback address.
#   origin_ok  A cross-site fetch announces itself, in Sec-Fetch-Site or Origin. Neither header
#              present means it is not a browser at all (curl, the CLI, a hook), and the token
#              is what gates those.
#
# Both are cheap and neither is sufficient alone: rebinding produces a same-origin request, and
# an origin check cannot see a Host that was never ours.

def _is_ip4(h: str) -> bool:
    parts = h.split('.')
    return len(parts) == 4 and all(p.isdigit() and len(p) <= 3 for p in parts)


def _authority(v: str) -> str:
    """`http://host:port/path`, `host:port`, `host` -> `host:port`, lowercased."""
    v = str(v or '').strip().lower()
    if '://' in v: v = v.split('://', 1)[1]
    return v.split('/', 1)[0]


def _hostname(v: str) -> str:
    """The authority without its port. IPv6 keeps its colons and loses its brackets."""
    a = _authority(v)
    if a.startswith('['): return a[1:].split(']', 1)[0]
    return a.rsplit(':', 1)[0] if a.count(':') == 1 else a


def allowed_hosts(server: dict) -> set:
    """localhost, whatever the server was told to bind, this machine's own name, and anything the
    owner added as `allowed_hosts` in config.toml - for a self-hoster reaching Taskuary by a real
    hostname, which is the one legitimate case this rule breaks.

    A comma-separated string or a TOML array; both, because config._tval WRITES an array and
    tomllib reads one back, so a list that only ever got str()'d became "['name']" and matched
    nothing - silently, and again after every save()."""
    import socket
    out = {'localhost', str(server.get('host') or '').lower()}
    try: out |= {socket.gethostname().lower(), socket.gethostname().lower() + '.local'}
    except Exception: pass
    extra = server.get('allowed_hosts') or ''
    names = extra.split(',') if isinstance(extra, str) else extra if isinstance(extra, (list, tuple, set)) else [extra]
    out |= {str(h).strip().lower() for h in names}
    return {h for h in out if h}


def host_ok(host: str, server: dict) -> bool:
    h = _hostname(host)
    if not h: return False                        # HTTP/1.1 requires a Host; a request without one is nobody
    if _is_ip4(h) or ':' in h: return True       # an IP literal is not a name and cannot be re-pointed
    return h in allowed_hosts(server)


def origin_ok(headers) -> bool:
    """Same-origin, or not a browser. `Origin: null` (a sandboxed frame, a data: URL) is neither."""
    site = str(headers.get('sec-fetch-site') or '').lower()
    if site and site not in ('same-origin', 'none'): return False
    o = str(headers.get('origin') or '').strip()
    if not o: return True
    if o.lower() == 'null': return False
    return _authority(o) == _authority(headers.get('host'))


# ── the tokens ──────────────────────────────────────────────────────────────────────────
def ensure_tokens(read, write, server: dict) -> dict:
    """Give this install both tokens if it has none, and persist them.

    The agent token tells a session's request from a person's; without it the deny list has
    nothing to act on. The OWNER token used to be the owner's choice, on the reasoning that
    forcing one would lock a running browser out mid-session. That reasoning had it backwards:
    with no owner token every local process IS the owner, so an agent defeats the whole deny
    list by simply not sending its header - and any page the owner visits can drive the API,
    because a browser attaches no proof of who asked (audit 2026-09-02, F03). It is minted now,
    and the page the server itself hands out carries it (server._seed_token), so the only browser
    that loses is one holding a tab from before the upgrade: it reloads and is fine.

    `read`/`write` are config's own reader and writer, passed in rather than imported - config
    calls this from inside load(), and importing it back would be a cycle."""
    fresh = {k: _secrets.token_urlsafe(24) for k in ('agent_token', 'token') if not server.get(k)}
    if not fresh: return server
    server.update(fresh)
    try:
        cur = read()
        cur.setdefault('server', {}).update(fresh)
        write(cur)
        logger.info(f"wrote {' and '.join(sorted(fresh))} to config.toml"
                    + (' - the page this server hands out carries the owner token' if 'token' in fresh else '')
                    + (' - sessions run with less authority than you do' if 'agent_token' in fresh else ''))
    except Exception as e:
        # in memory only: still enforced for this run, just regenerated on the next start
        logger.warning(f'could not persist {sorted(fresh)} ({e}) - they hold for this run only')
    return server


# ConfigJson is returned on list/get (the Secret column is not). OAuth client secrets and
# refresh tokens used to ride along, so an agent allowed to GET /api/connectors could read
# them without opening the database. Strip only the secret-shaped keys; host/client_id stay
# so a tool call can still name the card it is using. Owner GETs are not passed through this.
_CONFIG_SECRETS = frozenset({
    'password', 'token', 'api_key', 'app_key', 'client_secret', 'secret_key', 'secret_access_key',
    'sender_password', 'user_password', 'connection_string', 'private_key', 'google_client_secret',
    'google_refresh_token', 'refresh_token', 'access_key', 'bot_token',
})


def without_config_secrets(row: dict) -> dict:
    """A connector row an agent may see: ConfigJson minus the keys that are credentials."""
    out = dict(row)
    raw = out.get('ConfigJson')
    if not raw: return out
    try: cfg = json.loads(raw)
    except (TypeError, ValueError): return out
    if not isinstance(cfg, dict): return out
    cleaned = {k: v for k, v in cfg.items()
               if str(k).lower() not in _CONFIG_SECRETS
               and not str(k).lower().endswith(('_secret', '_password', '_token'))}
    if cleaned != cfg: out['ConfigJson'] = json.dumps(cleaned)
    return out


# WRITE-ONLY CARD FIELDS (the owner, 2026-10-21: "hide secrets"): an app's client secret is typed into
# the card's form like any field, but once saved it is never sent back to the browser - like the
# Secret column, it can be replaced and not read. The server keeps spending the stored value.
# LinkedIn's refresh token lives in ConfigJson too (linkedin._save), so it is held back the same way.
WRITE_ONLY_CONFIG = {'linkedin': ('client_secret', 'refresh_token'),
                     'quickbooks': ('client_secret',), 'zoho_invoice': ('client_secret',),
                     # the Google cards' OAuth client secret and the Gmail card's calendar refresh token came back readable in plain
                     # boxes on reopen, beside an App Password that was masked (the UI audit, 2026-10-21)
                     'gmail': ('google_client_secret', 'google_refresh_token'),
                     'google_sheets': ('google_client_secret',), 'google_chat': ('google_client_secret',)}


def masked_config(row: dict) -> dict:
    """A connector row for the owner's browser: its write-only keys out of ConfigJson, and which of
    them are saved (ConfigSaved) so the card can say "saved - type to replace"."""
    keys = WRITE_ONLY_CONFIG.get(row.get('Type'))
    if not keys: return row
    try: cfg = json.loads(row.get('ConfigJson') or '{}')
    except (TypeError, ValueError): cfg = {}
    if not isinstance(cfg, dict): cfg = {}
    return {**row, 'ConfigJson': json.dumps({k: v for k, v in cfg.items() if k not in keys}),
            'WriteOnlyKeys': list(keys), 'ConfigSaved': [k for k in keys if cfg.get(k)]}


def keep_write_only(typ: str, incoming: str, current: str) -> str:
    """A save that does not carry a write-only key - the browser never had it - keeps the stored one.
    A value typed replaces it, and a key sent as null clears it (a card switched to reuse another card's app)."""
    keys = WRITE_ONLY_CONFIG.get(typ)
    if not keys or incoming is None: return incoming
    try: new, old = json.loads(incoming), json.loads(current or '{}')
    except (TypeError, ValueError): return incoming
    if not (isinstance(new, dict) and isinstance(old, dict)): return incoming
    out = {**new, **{k: old[k] for k in keys if old.get(k) and (new.get(k) == '' or k not in new)}}
    return json.dumps({k: v for k, v in out.items() if not (k in keys and v is None)})
