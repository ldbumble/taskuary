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
    'intacct': 'read', 'intacct_fields': 'read',      # readByQuery and lookup; nothing posts
    # QuickBooks: the reads are reads. The two writes post to the books, which is exactly what the
    # ladder is for - the card ships at 'read', so an agent can only PROPOSE a bill (proposals.py,
    # run_tool) and the owner approves it in Review. Raising the card to 'write' is the owner's call.
    'quickbooks': 'read', 'quickbooks_vendors': 'read', 'quickbooks_accounts': 'read',
    'quickbooks_bill': 'write', 'quickbooks_expense': 'write',
    'zoho_monthly_invoices': 'read', 'zoho_customers': 'read', 'zoho_invoices': 'read',
    'zoho_invoice_draft': 'write', 'zoho_invoice_send': 'write',
    # Intacct writes the same way it reads - generically, by object - so ONE pair covers posting a
    # bill, adding a vendor and correcting a memo. The card ships at 'read' like QuickBooks', which
    # is what makes a bill an agent's PROPOSAL rather than an agent's decision.
    'intacct_create': 'write', 'intacct_update': 'write',
    'teller_accounts': 'read', 'teller_transactions': 'read', 'teller_balances': 'read',    # a feed cannot move money
    # the semantic layer (semantic.py) reaches the ERP only through those same reads. The check
    # DOES write - a metric it cannot reconcile is demoted, a verified one is frozen to a skill -
    # but every one of those writes lands in Taskuary's own store, never upstream, which is what
    # this ladder measures. Left unclassified they would have needed 'write' on the Intacct card,
    # and the card ships at 'read': the assistant is told to fetch certified numbers through
    # /api/tools/run, and every one of those calls would have been refused.
    'metric': 'read', 'metric_check': 'read',
    'local_file': 'read',    # a path on this machine, opened read-only - like the sqlite above it
    'kb_search': 'read',     # the knowledge base is Taskuary's own index; searching it moves nothing (kb_reindex writes it: default)
    # the handbook is Taskuary's own store and the whole point is that agents fill it, so reading
    # it is free. WRITING it is a write - not because it can reach anything (it cannot leave the
    # machine) but because an entry is a claim the next agent is handed as fact, and "who may put
    # a fact in front of every future agent" is exactly the question this ladder exists to ask.
    'handbook_search': 'read', 'handbook_write': 'write', 'handbook_vote': 'write',
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
    'telegram': 'write', 'whatsapp': 'write', 'imessage': 'write', 'discord': 'write',
    'gmail': 'write', 'imap': 'write',
    'mssql': 'read', 'database': 'read', 'prometheus': 'read', 'datadog': 'read',
    'intacct': 'read', 'quickbooks': 'read', 'teller': 'read',
    'zoho_invoice': 'write',
    'aws': 'read', 'azure': 'read',
    'jira': 'read', 'asana': 'read', 'monday': 'read', 'gitlab': 'read', 'azdo': 'read',
    'linear': 'read', 'trello': 'read', 'notion': 'read', 'sentry': 'read', 'pagerduty': 'read',
    'clickup': 'read', 'todoist': 'read', 'dropbox': 'read',
    # Taskuary's OWN stores, and the point of both is that agents fill them: a handbook only
    # agents may read is a handbook nobody writes. It stays on the ladder so an owner who wants
    # the agents hands-off can drop it to read - the default is not the absence of a choice.
    'handbook': 'write', 'knowledge': 'write',
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
        f"raise it under Connections → {t} → Authority, or leave it and the agents stay hands-off")
