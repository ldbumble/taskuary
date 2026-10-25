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
import re

SCOPES = ('read', 'write', 'admin')
_RANK = {s: i for i, s in enumerate(SCOPES)}
UNKNOWN_NEEDS = 'write'          # an unclassified verb is never merely a read

# What each action costs. Keys are the vocabulary the call sites already speak: report/tool
# executor types (reports.REGISTRY) plus the plain verbs the connectors use.
ACTIONS = {
    # ── read: the connection is a window, nothing upstream moves ──────────────────────
    'poll': 'read', 'fetch': 'read', 'search': 'read', 'list': 'read', 'discover': 'read',
    'image_generate': 'read',      # draws a picture: it spends, but nothing upstream moves
    'sqlite': 'read', 'mssql': 'read', 'database': 'read',
    'taskuary_data': 'read', 'dashboard': 'read',     # a dashboard's own rows and the dashboard: reads (each source is gated on its own card)
    'intacct': 'read', 'intacct_fields': 'read',      # readByQuery and lookup; nothing posts
    # QuickBooks: the reads are reads. The two writes post to the books, which is exactly what the
    # ladder is for - the card ships at 'read', so an agent can only PROPOSE a bill (proposals.py,
    # run_tool) and the owner approves it on the task. Raising the card to 'write' is the owner's call.
    'quickbooks': 'read', 'quickbooks_vendors': 'read', 'quickbooks_accounts': 'read',
    'quickbooks_bill': 'write', 'quickbooks_expense': 'write',
    'zoho_monthly_invoices': 'read', 'zoho_customers': 'read', 'zoho_invoices': 'read',
    'zoho_invoice_draft': 'write', 'zoho_invoice_send': 'write',
    # Intacct writes the same way it reads - generically, by object - so ONE pair covers posting a
    # bill, adding a vendor and correcting a memo. The card ships at 'read' like QuickBooks', which
    # is what makes a bill an agent's PROPOSAL rather than an agent's decision.
    'intacct_create': 'write', 'intacct_update': 'write',
    'teller_accounts': 'read', 'teller_transactions': 'read', 'teller_balances': 'read', 'teller_spend': 'read',    # a feed cannot move money
    # SimpleFIN cannot be anything but read: its protocol has no write verbs to expose
    'simplefin_accounts': 'read', 'simplefin_transactions': 'read', 'simplefin_balances': 'read', 'simplefin_spend': 'read',
    # market data: every one of these is a window on a public market. Nothing upstream moves.
    'coingecko_prices': 'read', 'fx_rates': 'read', 'yahoo_quotes': 'read', 'yahoo_history': 'read',
    'alchemy_prices': 'read', 'alchemy_wallet': 'read',
    'edgar_filings': 'read', 'edgar_facts': 'read', 'fred_series': 'read',
    'td_quotes': 'read', 'td_indicator': 'read', 'av_quotes': 'read',
    # five more providers (2026-09-08), field mapping written from documentation, not a live
    # response - still a read: nothing upstream moves for any of them, including alpaca, which
    # ships market DATA only, no order/trading executor at all
    'finnhub_quotes': 'read', 'finnhub_news': 'read', 'finnhub_earnings': 'read', 'finnhub_insiders': 'read',
    'polygon_bars': 'read', 'polygon_snapshot': 'read',
    'tiingo_history': 'read', 'tiingo_news': 'read',
    'fmp_fundamentals': 'read', 'fmp_ratios': 'read',
    'alpaca_quotes': 'read', 'alpaca_bars': 'read',
    # Robinhood is the first connection here that can MOVE MONEY. Listing the manifest and
    # reading the portfolio are windows; placing an order is not, and the card ships at 'read'
    # (DEFAULT_SCOPE) so an agent can only ever propose one. robinhood_read additionally
    # refuses any tool the server has not marked readOnlyHint - see robinhood._call.
    # A named database card runs SELECTs. The engine's own user is the real ceiling, so point
    # these at a read-only account and the ladder holds even if everything above it fails.
    'postgresql': 'read', 'mysql': 'read', 'clickhouse': 'read', 'snowflake': 'read', 'bigquery': 'read',
    # treg: the catalogue is free to read; CALLING spends money and can reach a publish or an
    # order, so it is a write: at a card's read scope every call is a proposal. Cards start at FULL below, so that
    # holds only where the owner narrowed the card.
    'treg_tools': 'read', 'treg_search': 'read', 'treg_call': 'write',
    # LinkedIn: reading who you are is a read; putting words on your feed under your name
    # is a write - a proposal you approve only on a card narrowed to read (cards start at FULL below).
    'linkedin_me': 'read', 'linkedin_post': 'write',
    'bluesky_me': 'read', 'bluesky_timeline': 'read', 'bluesky_post': 'write',
    'mastodon_me': 'read', 'mastodon_timeline': 'read', 'mastodon_post': 'write',
    'robinhood_tools': 'read', 'robinhood_read': 'read', 'robinhood_order': 'write',
    'markets_screen': 'read',    # the screen only reads through whichever provider it borrows
    # the semantic layer (semantic.py) reaches the ERP only through those same reads. The check
    # DOES write - a metric it cannot reconcile is demoted, a verified one is frozen to a skill -
    # but every one of those writes lands in Taskuary's own store, never upstream, which is what
    # this ladder measures. Left unclassified they would have needed 'write' on the Intacct card,
    # and the card ships at 'read': the assistant is told to fetch certified numbers through
    # /api/tools/run, and every one of those calls would have been refused.
    'metric': 'read', 'metric_check': 'read',
    'local_file': 'read',    # a path on this machine, opened read-only - like the sqlite above it
    # files (files.py): the network share and the SFTP server. sftp_get WRITES a file and is still a
    # read, for the reason this whole table measures - it reaches nothing upstream, and the only
    # place it can land is ~/.taskuary/sftp. The four that change something on the far side are writes.
    'smb_read': 'read', 'sftp_list': 'read', 'sftp_get': 'read',
    'smb_write': 'write', 'smb_move': 'write', 'sftp_put': 'write', 'sftp_move': 'write',
    'sharepoint_save': 'write', 'onedrive_save': 'write',     # a file saved, not a message: no press, and the agent says where (2026-10-25)
    'kb_search': 'read',     # the knowledge base is Taskuary's own index; searching it moves nothing (kb_reindex writes it: default)
    # the handbook is Taskuary's own store and the whole point is that agents fill it, so reading
    # it is free. WRITING it is a write - not because it can reach anything (it cannot leave the
    # machine) but because an entry is a claim the next agent is handed as fact, and "who may put
    # a fact in front of every future agent" is exactly the question this ladder exists to ask.
    'handbook_search': 'read', 'handbook_write': 'write', 'handbook_vote': 'write',
    'hub_search': 'read', 'hub_write': 'write', 'hub_vote': 'write', 'hub_comment': 'write',
    'aws': 'read', 's3_object': 'read', 'cloudwatch_logs': 'read',
    'azure': 'read', 'azure_blob': 'read', 'azure_logs': 'read',
    'entra_users': 'read', 'entra_groups': 'read', 'entra_signins': 'read', 'entra_licenses': 'read',
    'prometheus': 'read', 'datadog': 'read',
    # search and page-reading: they fetch, nothing upstream moves
    'exa': 'read', 'tavily': 'read', 'firecrawl': 'read', 'reader': 'read',
    'brave_search': 'read', 'serpapi': 'read', 'serper': 'read', 'scrapingbee': 'read',
    # apify RUNS an actor, which is somebody else's code - but on Apify's machine, under their
    # account, and what comes back is rows. Nothing in YOUR world moves, so it reads.
    'apify': 'read',
    'rest': 'read',          # run_rest is GET-only by construction
    'rss': 'read', 'digest': 'read', 'evening_inbox': 'read', 'automate': 'read',  # Taskuary's own traffic
    # ── write: the everyday work an agent is here to do ───────────────────────────────
    'create': 'write', 'update': 'write', 'comment': 'write', 'reply': 'write',
    'send': 'write', 'notify': 'write', 'assign': 'write', 'complete': 'write',
    'upload': 'write', 'push': 'write',
    # the trackers' write-back (trackers.py): the everyday work on an item - and every one of them reaches people (REACHES below)
    **{f'{t}_{v}': 'write' for t in ('jira', 'monday', 'linear') for v in ('comment', 'move', 'assign', 'close')},
    # GraphQL posts the query to the endpoint - and the same POST carries a mutation, so it is
    # not a read by construction the way run_rest's GET-only request is.
    'graphql': 'write',
    'mcp': 'write',          # an MCP server exposes arbitrary tools - never assume read
    # ── admin: destructive, structural, or arbitrary code ─────────────────────────────
    'delete': 'admin', 'close': 'admin', 'archive': 'admin', 'manage': 'admin',
    'winrm': 'admin',        # Invoke-Command on a remote box is the sharpest edge we ship
}

# Where each connection starts: FULL, the way a CLI agent with full permissions can already do anything its credentials
# reach (the owner, 2026-10-05: "default should be permission of agents are the same as cli tools full permissions. you can
# limit if you want"). The owner narrows a connection on its card or under Settings -> Agent permissions; the read-first
# per-type table this replaced was a guess at caution nobody had asked for. Mail from an unknown sender never starts an
# agent by itself (ingest.auto_start_ok) - but that gate reads the From header and trusts chat channels, so it is not a
# perimeter: these permissions also reach a spoofed sender's work (audit 2026-10-14).
FULL = 'admin'
DEFAULT_SCOPE = {}                     # no per-type exceptions; kept as the /api/scopes shape

_TRACKERS = {'jira': 'Jira', 'monday': 'Monday', 'linear': 'Linear'}
# WHAT REACHES A PERSON (the owner, 2026-10-25: "never send without approval, for now"). Each executor here puts words in front of
# somebody, publishes under the owner's name or moves money. An AGENT's call to one never runs at any Authority - full included - it
# waits as a run_tool proposal on the agent's own task, and the owner's press runs it (server.tool_run). The owner's own calls are
# unchanged. It is a property of the executor, like ACTIONS above, never a reading of what the call says. Cards start at FULL, so
# the older comments above about "the card ships at read, so an agent can only propose" stopped holding; this is what holds now.
REACHES = {
    'linkedin_post': 'posts on LinkedIn under your name', 'bluesky_post': 'posts on Bluesky under your name',
    'mastodon_post': 'posts on Mastodon under your name', 'zoho_invoice_send': 'sends an invoice to a customer',
    'robinhood_order': 'places an order with your money', 'treg_call': 'calls a paid endpoint that can publish or order',
    # these two reach whatever the far side does with them, so the call itself decides (reaches below)
    'mcp': "runs a tool its server does not mark read-only - it may send, post or comment",
    'graphql': 'runs a GraphQL mutation - it may post a comment or change a record somebody reads',
    # A TRACKER ITEM IS A CONVERSATION (2026-10-25): a comment is read by everyone on it, and a move, an assignment or a close is what
    # Jira, Monday and Linear each tell the people following it - so none is a quiet write, and an agent's always waits for the press
    **{f'{t}_comment': f'posts a comment on a {n} item - everyone on it reads it' for t, n in _TRACKERS.items()},
    **{f'{t}_move': f'moves a {n} item to another status - {n} tells the people following it' for t, n in _TRACKERS.items()},
    **{f'{t}_assign': f'assigns a {n} item to somebody - {n} tells them' for t, n in _TRACKERS.items()},
    **{f'{t}_close': f'moves a {n} item to done - {n} tells the people following it' for t, n in _TRACKERS.items()},
}
# ...and the writes that reach nobody, named, so every executor is a decision (test_scopes walks reports.REGISTRY): a file saved, a
# bill posted to the books, the Hub. Each keeps the card's Authority, per the owner's 2026-10-05 ruling. A file is not a message
# (2026-10-25), so a save to SharePoint or OneDrive runs at write, and the agent says where it put it.
QUIET_WRITES = frozenset({
    'quickbooks_bill', 'quickbooks_expense', 'intacct_create', 'intacct_update', 'zoho_invoice_draft',
    'smb_write', 'smb_move', 'sftp_put', 'sftp_move', 'sharepoint_save', 'onedrive_save',
    'handbook_write', 'handbook_vote', 'hub_write', 'hub_vote', 'hub_comment', 'kb_reindex',
    'winrm',                                       # runs on a box the owner named; its reach is that box, and admin gates it
    # each answers the owner or Taskuary's own store: an agent run's words are drafts, and the Assistant posts to the owner
    'agent', 'assistant', 'taskuary', 'calendar', 'google_sheets', 'sharepoint_list', 'sharepoint_file',
    # named in the catalogue, not built (reports.PLANNED): they run nothing yet
    'netsuite', 'sap', 'workday', 'adp', 'epic', 'cerner', 'pointclickcare', 'stooq'})


def _gql_op(query) -> str:
    "A GraphQL document's operation type: the grammar's first word ('{' alone is the query shorthand). Comments are skipped."
    q = '\n'.join(l.split('#', 1)[0] for l in str(query or '').splitlines()).strip()
    return 'query' if not q or q.startswith('{') else re.split(r'[\s({]', q, 1)[0].lower()


def reaches(action, cfg: dict = None, tool: dict = None) -> str:
    """'' when an agent's call to this executor reaches nobody, else what it would do, in words for the owner's card. An MCP tool
    reaches unless its own server marks it read-only (mcp.read_only, fail closed); a GraphQL document unless it is a query."""
    a = (action or '').strip().lower()
    if a == 'mcp':
        from .mcp import read_only
        return '' if read_only(tool or {}) else REACHES['mcp']
    if a == 'graphql': return '' if _gql_op((cfg or {}).get('query')) in ('query', 'subscription') else REACHES['graphql']
    return REACHES.get(a, '')


def rank(scope) -> int: return _RANK.get((scope or '').strip().lower(), 0)

def needs(action) -> str: return ACTIONS.get((action or '').strip().lower(), UNKNOWN_NEEDS)

def default_scope(ctype) -> str: return DEFAULT_SCOPE.get((ctype or '').strip().lower(), FULL)

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
    from . import words
    want, have, t = needs(action), scope_of(c), c.get('Type') or 'this connection'
    raise PermissionError(
        f"'{action}' needs {want} authority on {t}, which is set to {have} - "
        f"raise it under {words.card(t)} → Authority, or leave it and the agents stay hands-off")
