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
    (r'POST', r'^/api/tasks/\d+/clarify$', 'opening a clarification is the first half of sending one'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(connectors|sources)', 'credentials and where mail goes'),
    (r'GET', r'^/api/send-targets$', 'the address book of everywhere this install can send'),
    # ...and anything that would let it widen its own reach
    (r'POST|PUT|PATCH', r'^/api/settings', 'the settings decide what agents may do'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(policies|agents)', 'the rules and the agent profiles'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/(docs?|playbooks)(/|$)', 'SOUL.md, the playbooks and the rest are the owner\'s word, not an agent\'s - propose, do not write'),
    (r'POST', r'^/api/update$', 'replacing the program is the owner\'s decision'),
    # ...and the doors the 2026-09-02 audit found standing open: releasing the held task of the very
    # sender the hold exists for, landing work, running an executor or a query with a card's
    # credentials, and rewriting the documents that govern the agent
    (r'POST', r'^/api/tasks/\d+/(release|land|ci)$', 'releasing a held task or landing its work is the owner\'s decision'),
    (r'POST', r'^/api/(soul|learn)(/|$)', 'SOUL.md and LEARNED.md are the owner\'s word - propose, do not write'),
    (r'PUT|PATCH', r'^/api/(owner|whoami)$', 'who the owner is'),
    (r'POST', r'^/api/(mcp|mssql)/', 'runs a command, or sends saved credentials to a host of the caller\'s choosing'),
    (r'POST', r'^/api/reports/(preview|compose|compose-sources)$', 'the report composer runs any executor with a card\'s credentials'),
    (r'POST|PUT|PATCH|DELETE', r'^/api/semantic(/|$)', 'a metric spec is SQL run against a database of its choosing'),
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
    owner added as `allowed_hosts` in config.toml (comma-separated) - for a self-hoster reaching
    Taskuary by a real hostname, which is the one legitimate case this rule breaks."""
    import socket
    out = {'localhost', str(server.get('host') or '').lower()}
    try: out |= {socket.gethostname().lower(), socket.gethostname().lower() + '.local'}
    except Exception: pass
    out |= {h.strip().lower() for h in str(server.get('allowed_hosts') or '').split(',')}
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
