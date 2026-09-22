"""treg as a Taskuary connection: one card, ~3,600 third-party endpoints behind it.

WHAT IT IS. treg (treg.to, Apache-2.0 + additional terms) is "OpenRouter, but for agent tools
instead of models": a proxy that holds vendor accounts for ~90 providers and bills per call with
no markup and no subscription. It speaks MCP over hosted HTTP, which is the transport mcp.py
already grew for Robinhood - so this file is small on purpose.

WHY IT IS ONE CARD AND NOT NINETY. Tool definitions live in the model's context; 3,600 of them
would cost tens of thousands of tokens before an agent read a single email. treg's own MCP server
solves this the same way its CLI does and exposes ~10 FIXED tools - search the catalogue, then
call the endpoint you found. Their source is explicit that this is deliberate: "treg never
changes its tool surface at runtime... catalog changes are tool DATA, not a tools/list change."
So the catalogue is searched, never enumerated, and this card stays one row.

THE SAFETY MODEL, which is the whole reason this is not four lines:

- SEARCHING IS FREE AND READ-ONLY. treg_search and treg_tools are `read`: they touch the
  catalogue, spend nothing, and change nothing upstream.

- CALLING IS A `write`, ALWAYS - even for an endpoint that only reads. Two independent reasons,
  either sufficient. It SPENDS MONEY (real vendor calls, up to $26 a call in that catalogue), and
  the same door reaches endpoints that publish, post and order. A read-scoped door onto "call
  anything in a 3,600-endpoint catalogue" would make the ladder decorative. The card ships at
  `read` (scopes.DEFAULT_SCOPE), so every call is a proposal the owner approves on the task,
  with the endpoint and the estimated cost in front of them.

- A COST CEILING IS NOT OPTIONAL. treg's contract says plainly that there is NO default cap on a
  direct call - `X-Treg-Route-Max-Cost` is the only one. An agent in a retry loop against a
  $0.50 endpoint is a real hazard, so `max_cost` is sent on every call and defaults to something
  small rather than to nothing.

- `url` and `token` are connection keys (reports.CONNECTION_KEYS), so a tool call cannot redirect
  the card's token at a host of the agent's choosing - the lesson of the 2026-09-02 audit.

WHAT SELF-HOSTING WOULD NOT GIVE YOU, since the licence invites it: the ~73 TREG_PLATFORM_KEY_*
settings that feed the "treg's own key" rung of its credential ladder ship EMPTY. A self-hosted
instance is a credential vault and a faithful proxy for keys you already own; the catalogue on
treg's account is the commercial product and exists only at treg.to. Calling hosted treg.to from
inside your own product is explicitly permitted by their additional terms.
"""
import json

from . import mcp

URL = 'https://treg.to/mcp/'
# Their catalogue's median endpoint is $0.002 and 92% are under $0.05, so this is generous for
# ordinary work and still refuses the video-generation tail without the owner saying so.
DEFAULT_MAX_COST = '0.25'


def _cfg(cfg) -> dict:
    if not cfg.get('token'):
        raise RuntimeError('no treg token saved - create one at treg.to and paste it on the card')
    return {'url': (cfg.get('url') or URL).rstrip('/') + '/', 'token': cfg['token'],
            'timeout': int(cfg.get('timeout') or 60)}


def tools(cfg) -> list:
    """treg's fixed tool surface - about ten, whatever the catalogue does."""
    return mcp.list_tools(_cfg(cfg))


def _text(res) -> str:
    if res.get('isError'): raise RuntimeError(str(res.get('content'))[:500])
    texts = [b.get('text', '') for b in res.get('content', []) if b.get('type') == 'text']
    return '\n'.join(t for t in texts if t) or json.dumps(res, default=str)


def _one(cfg, tool: str, args: dict) -> str:
    s = mcp._session(_cfg(cfg))
    try:
        return _text(s.call_tool(tool, args))
    finally:
        s.close()


def run_treg_tools(cfg):
    """{} - treg's own tool surface. Ten-ish meta-tools; the catalogue is DATA behind them."""
    got = tools(cfg)
    body = '\n'.join(f"{t['name']}\n    {t['description']}" for t in got) or 'the server listed no tools'
    return f'{len(got)} treg tools', body[:4000]


def run_treg_search(cfg):
    """{"q": "backlinks for a domain"} - find an endpoint by the JOB, not the vendor. Free: this
    reads the catalogue and spends nothing. The answer carries each endpoint's id, its price and
    its measured reliability, which is what you need to choose one."""
    q = str(cfg.get('q') or cfg.get('query') or '').strip()
    if not q:
        raise ValueError('say what the tool should DO - treg searches by capability, not by vendor')
    args = {'query': q}
    if cfg.get('limit'): args['limit'] = int(cfg['limit'])
    return f'treg: {q}', _one(cfg, 'catalog_search', args)[:6000]


def run_treg_call(cfg):
    """{"endpoint": "hunter.x.domain-finder", "args": {...}} - run one endpoint.

    A `write` whatever the endpoint does, because this door spends money and reaches endpoints
    that publish and order. The owner approves it on the task with the endpoint in front of them.
    """
    endpoint = str(cfg.get('endpoint') or cfg.get('id') or '').strip()
    if not endpoint:
        raise ValueError('name the treg endpoint to call - run treg_search to find its id')
    args = cfg.get('args') or {}
    if isinstance(args, str): args = json.loads(args or '{}')
    # THE CAP. treg applies none of its own on a direct call; this is the only thing standing
    # between a retry loop and a bill.
    payload = {'endpoint_id': endpoint, 'params': args,
               'max_cost': str(cfg.get('max_cost') or DEFAULT_MAX_COST)}
    return f'treg: {endpoint}', _one(cfg, 'call', payload)[:6000]
