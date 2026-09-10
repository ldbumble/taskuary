"""Robinhood's agentic-trading MCP server, as a Taskuary connection.

Robinhood shipped the first official brokerage MCP (May 2026) at
https://agent.robinhood.com/mcp/trading. Two facts about it shape this whole file:

1. IT IS REMOTE. Every other MCP we speak to is a program we spawn; this one is hosted and
   authenticated with a bearer token, which is why mcp.py grew an HTTP transport. There is no
   `cmd` to put on the card.

2. ITS TOOL NAMES ARE NOT PUBLISHED. Robinhood documents capabilities ("positions, balances,
   place orders") and no manifest, and the community write-ups admit they never ran a trade.
   So nothing here hardcodes a tool name: `robinhood_tools` reads the real manifest off the
   live server, and the other two executors call the name they are given.

THE SAFETY MODEL, which is why this is not four lines:

- The card ships at scope `read` (scopes.DEFAULT_SCOPE), so `robinhood_order` - a `write` - is
  refused for an agent and becomes a PROPOSAL the owner approves in Review. Same ladder the
  QuickBooks bill and the Intacct post already ride, and deliberate: an agent that reads
  untrusted email is upstream of this connection.

- A read may only reach a tool the SERVER declares read-only (`readOnlyHint`, mcp.read_only),
  checked against the live manifest and FAILING CLOSED. Without it `robinhood_read` would be a
  read-scoped door onto every write tool on the server, making the ladder above decorative.

- `url` and `token` are in reports.CONNECTION_KEYS, so a tool call cannot redirect the card's
  token at a host of the agent's choosing (the lesson of audit 2026-09-02).

- Robinhood's own boundary sits underneath all of that: orders reach only the dedicated Agentic
  account the owner funds separately, and it notifies on every trade. We do not rely on it.
"""
import json

from . import mcp

URL = 'https://agent.robinhood.com/mcp/trading'


def _session(cfg):
    if not cfg.get('token'):
        raise RuntimeError('no Robinhood token saved - connect the account on its card first')
    return mcp._session({'url': (cfg.get('url') or URL).rstrip('/'), 'token': cfg['token'],
                         'timeout': int(cfg.get('timeout') or 60)})


def tools(cfg) -> list:
    """The live manifest. THE DISCOVERY STEP: nobody publishes these names, so we ask."""
    return mcp.list_tools({'url': (cfg.get('url') or URL).rstrip('/'), 'token': cfg.get('token'),
                           'timeout': int(cfg.get('timeout') or 60)})


def _text(res) -> str:
    if res.get('isError'): raise RuntimeError(str(res.get('content'))[:500])
    texts = [b.get('text', '') for b in res.get('content', []) if b.get('type') == 'text']
    return '\n'.join(t for t in texts if t) or json.dumps(res, default=str)


def _call(cfg, must_read: bool):
    tool = str(cfg.get('tool') or '').strip()
    if not tool: raise ValueError('name the Robinhood tool to call - run robinhood_tools to list them')
    args = cfg.get('args') or {}
    if isinstance(args, str): args = json.loads(args or '{}')
    s = _session(cfg)
    try:
        if must_read:
            # resolved against the LIVE manifest rather than a name we think we recognise: the
            # point is to let the server say what is safe, and to refuse when it has not
            found = next((t for t in s.list_tools() if t.get('name') == tool), None)
            if not found: raise ValueError(f'{tool} is not a tool this Robinhood account exposes')
            if not mcp.read_only(found):
                raise PermissionError(
                    f'{tool} is not read-only, so it cannot run as a read. Placing an order is '
                    'robinhood_order, which the card refuses at scope read - it becomes a '
                    'proposal you approve in Review.')
        return tool, _text(s.call_tool(tool, args))
    finally:
        s.close()


def run_robinhood_tools(cfg):
    """{} - the live manifest. How you find the tool names, since Robinhood publishes none."""
    got = tools(cfg)
    body = '\n'.join(f"{t['name']}  {'(read-only)' if t['read_only'] else '(WRITE - proposal only)'}\n    {t['description']}"
                     for t in got) or 'the server listed no tools'
    return f'{len(got)} Robinhood tools', body[:4000]


def run_robinhood_read(cfg):
    """{"tool": "...", "args": {...}} - one READ tool: portfolio, positions, balances, orders,
    transactions, watchlists. Refused unless the server itself declares the tool read-only."""
    tool, out = _call(cfg, must_read=True)
    return f'robinhood {tool}', out[:4000]


def run_robinhood_order(cfg):
    """{"tool": "...", "args": {...}} - place an order. A `write`: at the card's shipped scope
    this never runs for an agent - it is proposed, and the owner approves it in Review."""
    tool, out = _call(cfg, must_read=False)
    return f'robinhood order via {tool}', out[:4000]


def test(store, c) -> str:
    """A real round trip that moves nothing: initialize, then tools/list."""
    from .reports import _card
    got = tools(_card(store, 'robinhood', 'token', c['ConnectorId']))
    reads = sum(1 for t in got if t['read_only'])
    return (f'connected - {len(got)} tools, {reads} of them read-only'
            + (': ' + ', '.join(t['name'] for t in got[:6]) if got else ''))
