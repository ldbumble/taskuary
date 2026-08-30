"""Get AI to set it up: a connector card's own guide, handed to the coding CLI as its prompt.

Every card has a Guide tab - "go to api.slack.com/apps, create an app, copy the token" - and a
form the owner fills by hand after reading it. This is the other way round: the agent reads the
guide, asks the owner for each thing only a human can fetch (a token from a browser, an admin's
yes), saves it onto the card through Taskuary's own API and runs the card's Test until it passes.
It happens in a live terminal ON the card, so the owner answers where they are looking - and it
is a task on the Board too, because an agent working is an agent working wherever it started.

Two things are deliberately different from a coding session. The transcript is NOT filed on the
task: the owner types tokens into this terminal, and a task record is not where secrets live.
And "Done" is a plain close - no report, no proposals, no reply draft; the connector's Test
result is the report.
"""
import json
from . import config


KIND = 'setup'


def tag(cid: int) -> str: return f'connector:{cid}'


def live_for(store, cid: int):
    """The live setup session for this card, if one is open - the button reattaches instead of
    starting a second agent on the same form."""
    from . import terminal as term
    for t in list(term.SESSIONS.values()):
        if not (t.alive and t.task_id): continue
        tk = store.get_task(t.task_id) or {}
        if tk.get('Kind') == KIND and tag(cid) in str(tk.get('Tags') or ''): return {**t.info(), 'taskId': t.task_id}
    return None


def prompt(c: dict, server: dict, guide: list, fields: list, secret_label: str, agent_steps: list = None) -> str:
    """One flattened line (a newline submits in a TUI): who the owner is connecting, the steps, the
    card's fields and which are still empty, how to save and test through the API, and the rules.

    Two kinds of steps. The GUIDE is the card's human guide - "run npm install, scan the QR" -
    and handed over raw it made the agent a narrator: it told the owner to run npm install. So the
    standing rule says machine-side work is the agent's own, and a card can carry AGENT STEPS
    written for the agent (the card's Agent tab), with {base} and {cid} filled in here.
    Config VALUES stay out - only the keys - so nothing on the card is echoed into the CLI's logs."""
    import os
    cfg = json.loads(c.get('ConfigJson') or '{}')
    have, keys = [k for k, v in cfg.items() if v not in (None, '', [], {})], [str(f[1]) for f in (fields or []) if len(f) > 1]
    empty = [k for k in keys if k not in have]
    base = f"http://{server.get('host') or '127.0.0.1'}:{server.get('port') or 7787}"
    tok = server.get('token')
    hdr = f" with header X-Taskuary-Token: {tok}" if tok else ''
    fill = lambda s: str(s).replace('{base}', base).replace('{cid}', str(c['ConnectorId'])).replace('{hdr}', hdr)
    steps = [fill(s) for s in (agent_steps or []) if str(s).strip()]
    parts = [f"You are helping the owner connect {c.get('Name') or c.get('Type')} (a {c.get('Type')} connector, id {c['ConnectorId']}) "
             "in Taskuary, the app this terminal belongs to. The owner is watching this terminal and answers you here. "
             f"Taskuary's package folder on this machine is {os.path.dirname(os.path.abspath(__file__))}.",
             'WHO DOES WHAT: anything that happens on THIS machine - installing packages, starting or restarting processes, running '
             'commands, checking ports, reading or writing config files, calling the API - is YOUR job: do it yourself and report what '
             'happened; never hand the owner a command to run. Only what needs the owner\'s own accounts, phone, browser or admin '
             'console is theirs, and you ask for exactly that.',
             ('STEPS FOR YOU (written for you, the agent - do these yourself, in order): ' + ' '.join(f'{i + 1}. {s}' for i, s in enumerate(steps))
              if steps else ''),
             ("OWNER GUIDE (what a person would do by hand - for reference; the machine-side parts of it are yours): " if steps else
              "GUIDE (Taskuary's own, written for a person - follow it in order, doing the machine-side parts yourself): ")
             + ' '.join(f'{i + 1}. {s}' for i, s in enumerate(guide or [])),
             'FIELDS on the card: ' + ('; '.join(f"{f[0]} (key {f[1]})" for f in (fields or []) if len(f) > 1) or 'none') + '.'
             + (f" The card's secret field is \"{secret_label}\" - it is write-only; save it as Secret, never inside ConfigJson." if secret_label else ''),
             f"CURRENTLY SET: {', '.join(have) or 'nothing'}. EMPTY: {', '.join(empty) or 'nothing'}. Secret: {'set' if c.get('HasSecret') else 'not set'}.",
             f"HOW TO SAVE: GET {base}/api/connectors{hdr} and find id {c['ConnectorId']} to read the current config; then POST {base}/api/connectors{hdr} "
             f"with JSON {{\"ConnectorId\": {c['ConnectorId']}, \"ConfigJson\": \"<the WHOLE config as a JSON string - it replaces, so keep keys you are not changing>\", "
             "\"Secret\": \"<only when you have a new one>\", \"Active\": true}. "
             f"THEN TEST: POST {base}/api/connectors/{c['ConnectorId']}/test{hdr} and read {{ok, detail}}; fix and repeat until ok is true.",
             'RULES: start by saying in two lines what this setup needs from the owner, then ask for the first value. Ask for one thing at a time and wait - '
             'anything that lives in a browser, a portal or an admin console is theirs to fetch and paste here; you do not open browsers or sign in as them. '
             'Never invent or guess credentials, ids or hostnames. Once you hold a secret, never print it back to the screen. '
             'Touch nothing in Taskuary beyond this one connector: no other endpoints, no settings, no files, no other cards. '
             'When the test passes, say SETUP DONE and what now works in one line; if it cannot pass, say exactly what is missing and stop.']
    return ' '.join(' '.join(p for p in parts if p).split())


def start(store, server: dict, cid: int, guide: list, fields: list = None, secret_label: str = '',
          agent: str = None, model: str = None, actor: str = 'owner', agent_steps: list = None) -> dict:
    from . import terminal as term
    c = store.get_connector(cid)
    if not c: raise ValueError('connector not found')
    live = live_for(store, cid)
    if live: return {**live, 'existing': True}
    agent = (agent or store.get_settings().get('default_agent') or 'coder').strip()
    if not store.get_agent(agent): raise ValueError(f'no CLI agent named {agent!r} - add one under Connectors > AI CLI agents first')
    tid = store.create_task({'Title': f"Set up {c.get('Name') or c.get('Type')}", 'Kind': KIND, 'Status': 'in_progress', 'Tags': tag(cid),
                             'Summary': f"{agent} walks the owner through the {c.get('Type')} guide in a live session on the card and saves what they give it."}, actor)
    # no repo: the session sits in Taskuary's own data folder, where there is no checkout to attribute dirt to
    t = term.open_session(store, agent, tid, None, str(config.home()), 32, 110, actor, model,
                          seed_fn=lambda cwd: prompt(c, server, guide, fields or [], secret_label or '', agent_steps))
    t.keep_transcript = False
    store.add_comment(tid, actor, 'human', f"{agent} is helping set up {c.get('Name') or c.get('Type')} in a live session on its card.")
    store.audit('connector', cid, 'ai_setup', actor, detail={'task': tid, 'agent': agent})
    return {**t.info(), 'taskId': tid, 'existing': False}


def finish(store, tid: int, actor: str = 'owner') -> dict:
    """Done means the session goes and the task closes - the connector's own Test said the rest."""
    from . import terminal as term
    live = term.for_task(tid)
    if live: term.close(live['sid'])
    store.add_comment(tid, actor, 'human', 'Setup session closed.')
    if (store.get_task(tid) or {}).get('Status') not in ('done', 'dropped'): store.update_task(tid, {'Status': 'done'}, actor)
    store.audit('terminal', tid, 'wrap', actor, detail={'sid': live and live['sid'], 'setup': True})
    return {'wrap': 'done', 'taskId': tid}
