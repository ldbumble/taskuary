"""Per-action authority: how far may an agent reach through a connection?

`Roles` says WHAT a connection is for (trigger/feed/report/tool/notify). Scope says HOW FAR
an agent may go once it is a tool - the difference between "the agents may use Jira" and
"the agents may close Jira tickets". Three levels, ordered, each containing the ones before:

    read   - list, fetch, search, query. Nothing upstream changes.
    write  - plus the everyday work: create, update, comment, send a reply.
    admin  - plus the destructive and the structural: delete, run code on a box, manage access.

The ceiling is one dropdown on the connector card. Every action declares what it needs, and
an action nobody classified needs 'write' - guessing 'read' for an unrecognised verb is how
an agent quietly changes something nobody authorised. Fail closed and be wrong in the
direction that asks permission.

Pure, like policy.py: dicts in, a decision out, no store and no network, so the whole table
is unit-testable offline. `Scope` on the connector row is the owner's setting; the defaults
below are what each connection could already do before scopes existed, so switching a
version on changes nothing until the owner tightens it.
"""

SCOPES = ('read', 'write', 'admin')
_RANK = {s: i for i, s in enumerate(SCOPES)}
UNKNOWN_NEEDS = 'write'          # an unclassified verb is never merely a read

# What each action costs. Keys are the vocabulary the call sites already speak: report/tool
# executor types (reports.REGISTRY) plus the plain verbs the connectors use.
ACTIONS = {
    # ── read: the connection is a window, nothing upstream moves ──────────────────────
    'poll': 'read', 'fetch': 'read', 'search': 'read', 'list': 'read', 'discover': 'read',
    'sqlite': 'read', 'mssql': 'read', 'database': 'read',
    'local_file': 'read',    # a path on this machine, opened read-only - like the sqlite above it
    'aws': 'read', 's3_object': 'read', 'cloudwatch_logs': 'read',
    'azure': 'read', 'azure_blob': 'read', 'azure_logs': 'read',
    'entra_users': 'read', 'entra_groups': 'read', 'entra_signins': 'read', 'entra_licenses': 'read',
    'prometheus': 'read', 'datadog': 'read',
    # search and page-reading: they fetch, nothing upstream moves
    'exa': 'read', 'tavily': 'read', 'firecrawl': 'read', 'reader': 'read',
    'rest': 'read',          # run_rest is GET-only by construction
    'rss': 'read', 'digest': 'read', 'automate': 'read',     # automate reads Taskuary's own traffic
    # ── write: the everyday work an agent is here to do ───────────────────────────────
    'create': 'write', 'update': 'write', 'comment': 'write', 'reply': 'write',
    'send': 'write', 'notify': 'write', 'assign': 'write', 'complete': 'write',
    'upload': 'write', 'push': 'write',
    'mcp': 'write',          # an MCP server exposes arbitrary tools - never assume read
    # ── admin: destructive, structural, or arbitrary code ─────────────────────────────
    'delete': 'admin', 'close': 'admin', 'archive': 'admin', 'manage': 'admin',
    'winrm': 'admin',        # Invoke-Command on a remote box is the sharpest edge we ship
}

# Where each connection starts. These match what it could already do, so nothing regresses
# on upgrade; the read-only trackers start at 'read' because that is all they have ever
# done, and the new connectors start at 'read' because nothing depends on them yet.
DEFAULT_SCOPE = {
    'winrm': 'admin',                                        # its one executor needs admin
    'github': 'write', 'outlook': 'write', 'teams': 'write', 'slack': 'write',
    'telegram': 'write', 'whatsapp': 'write', 'discord': 'write',
    'gmail': 'write', 'imap': 'write',
    'mssql': 'read', 'database': 'read', 'prometheus': 'read', 'datadog': 'read',
    'aws': 'read', 'azure': 'read',
    'jira': 'read', 'asana': 'read', 'monday': 'read', 'gitlab': 'read', 'azdo': 'read',
    'linear': 'read', 'trello': 'read', 'notion': 'read', 'sentry': 'read', 'pagerduty': 'read',
    'clickup': 'read', 'todoist': 'read', 'dropbox': 'read',
}


def rank(scope) -> int: return _RANK.get((scope or '').strip().lower(), 0)

def needs(action) -> str: return ACTIONS.get((action or '').strip().lower(), UNKNOWN_NEEDS)

def default_scope(ctype) -> str: return DEFAULT_SCOPE.get((ctype or '').strip().lower(), 'read')

def scope_of(c) -> str:
    """The ceiling on a connector row - the owner's setting, or the type's default."""
    return (c.get('Scope') or '').strip().lower() or default_scope(c.get('Type'))

def allows(c, action) -> bool: return rank(scope_of(c)) >= rank(needs(action))

def actions_at(scope) -> list:
    """Every action a connection at this scope may take - what the card lists back."""
    return sorted(a for a in ACTIONS if rank(scope) >= rank(ACTIONS[a]))


def require(c, action):
    """Raise unless this connection may take this action. The message names the dropdown to
    move and the level to move it to, because 'forbidden' with no next step is a dead end."""
    if allows(c, action): return
    want, have, t = needs(action), scope_of(c), c.get('Type') or 'this connection'
    raise PermissionError(
        f"'{action}' needs {want} authority on {t}, which is set to {have} - "
        f"raise it under Connectors → {t} → Authority, or leave it and the agents stay hands-off")
