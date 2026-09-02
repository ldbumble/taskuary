"""What an agent may not do, decided in code and nowhere else.

Everything an agent reads is untrusted. The mail it is working IS the prompt; so is the web page
it opened, the issue somebody filed, the document it indexed. Any of them can contain a sentence
telling it to go and send something, and the whole design of this app rests on the promise that
nothing leaves without the owner pressing a button.

That promise was made in PROSE. SOUL.md says what the agents may do, CODER.md says not to push,
the seed prompt says ask before assuming - and every one of those is a paragraph the same
untrusted text sits next to and can argue with. An instruction is not a control. A model that
has been talked into believing the owner wants an immediate reply will find the local API,
which until now answered any process on the machine, and approve its own draft.

So the rule moves out of the documents:

- Sessions run with an AGENT TOKEN in their environment (terminal.session_env). Every request
  carrying it is agent scope.
- Agent scope is REFUSED on the routes below, by path, in the middleware, before a handler
  exists. There is no setting for it, no document that relaxes it, and no argument that reaches
  it - the deny list is this file, and this file is code.
- Approving a reply, sending a message, changing where mail goes and reading or writing
  credentials are all on that list. So is granting scope, because the obvious next move for a
  cornered model is to widen its own permissions.

WHAT THIS DOES NOT DO, said plainly because a security control nobody understands the edges of
is worse than none: an agent runs as the same operating-system user as Taskuary, so it can read
~/.taskuary/taskuary.db and everything in it, including the connector credentials, and it can
run `curl` without the token and be treated as the owner unless a token is configured. Two
things follow. First, set [server].token - `ensure_tokens` writes one on first run and the
browser is handed it, so this costs the owner nothing and closes the anonymous door. Second,
real credential isolation needs the secrets out of the database and behind the OS keychain
(DPAPI on Windows, Keychain on macOS) with only a separate sender able to decrypt them; that is
not built, and until it is, an agent that goes looking for the file can find the keys. What IS
built is that no prompt, no API response and no tool result ever hands them over, and that the
one road from "an agent wants this sent" to "it is sent" runs through a person.
"""
import re
import secrets as _secrets
from loguru import logger

AGENT_ENV = 'TASKUARY_TOKEN'          # what a session carries; the CLI reads it for --note/--done
OWNER, AGENT, ANON = 'owner', 'agent', 'anon'

# ── THE DENY LIST ───────────────────────────────────────────────────────────────────────
# (method regex, path regex, why). Matched against the request before routing. Add to it when
# a new route can make something leave the machine or can widen what an agent may reach; never
# make it conditional on a setting, and never let a document turn an entry off.
DENIED = (
    # anything that puts a message in front of a human somewhere else
    (r'POST', r'^/api/reviews/\d+/decide$', 'approving a reply sends it - that is the owner\'s'),
    (r'POST', r'^/api/tasks/\d+/handoff$', 'handing work to a person sends them a message'),
    (r'POST', r'^/api/outbox$', 'starting an outbound message is the owner\'s door, not an agent\'s'),
    (r'POST', r'^/api/messages/\d+/reply$', 'opening a reply is the first half of sending one'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(connectors|sources)', 'credentials and where mail goes'),
    (r'GET', r'^/api/send-targets$', 'the address book of everywhere this install can send'),
    # ...and anything that would let it widen its own reach
    (r'POST|PUT|PATCH', r'^/api/settings', 'the settings decide what agents may do'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(policies|agents)', 'the rules and the agent profiles'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(docs?|playbooks)(/|$)', 'SOUL.md, the playbooks and the rest are the owner\'s word, not an agent\'s - propose, do not write'),
)
_DENIED = tuple((re.compile(f'^({m})$', re.I), re.compile(p), why) for m, p, why in DENIED)


def denied(method: str, path: str) -> str:
    """'' when an agent may call this, else why not. Pure, so the whole table is testable."""
    for m, p, why in _DENIED:
        if m.match(method or '') and p.match(path or ''): return why
    return ''


def scope_of(cfg: dict, headers) -> str:
    """Who is calling. The agent token is the only thing that says 'agent'; everything else is
    treated as the owner, which is the honest description of a localhost app - see the module
    docstring on what that does and does not buy."""
    tok = str(headers.get('X-Taskuary-Token') or '')
    if tok and tok == str(cfg.get('agent_token') or ''): return AGENT
    owner = str(cfg.get('token') or '')
    if not owner: return OWNER                     # no token configured: the old, open behaviour
    return OWNER if tok == owner else ANON


# ── the tokens ──────────────────────────────────────────────────────────────────────────
def ensure_tokens(read, write, server: dict) -> dict:
    """Give this install an agent token if it has none, and persist it. The OWNER token stays the
    owner's choice - turning it on is a decision about the network, and forcing one would lock a
    running browser out mid-session. The agent token is not a choice: without it there is no way
    to tell a session's request from a person's, and the deny list has nothing to act on.

    `read`/`write` are config's own reader and writer, passed in rather than imported - config
    calls this from inside load(), and importing it back would be a cycle."""
    if server.get('agent_token'): return server
    server['agent_token'] = _secrets.token_urlsafe(24)
    try:
        cur = read()
        cur.setdefault('server', {})['agent_token'] = server['agent_token']
        write(cur)
        logger.info('wrote an agent token to config.toml - sessions run with less authority than you do')
    except Exception as e:
        # in memory only: still enforced for this run, just regenerated on the next start
        logger.warning(f'could not persist the agent token ({e}) - it holds for this run only')
    return server
