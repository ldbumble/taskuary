"""Get AI to set it up: a connector card's own guide, handed to an agent as its brief.

A CONNECTOR CARD'S walk is the GENERAL agent now (start_walk, below - the owner, 2026-10-21); what follows first is the
terminal road the CLI-install setup (clisetup.py) still takes, and what this file was before.

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
import json, re
from . import config, words


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


# Nothing to hand the setup to (B10, 2026-10-11): a new install without any AI CLI answered the card's
# biggest button with "command not found: claude" - true, and nothing the owner could do with it.
NO_AI = ("No AI app is set up on this computer yet, so there is nothing to hand this setup to. Set one up under "
         f"{words.name('ai_apps')} and press this again - or follow the Guide tab and fill the card yourself.")


def runner(store, agent: str = None) -> str:
    """The agent that will run this setup, once its CLI is FOUND - or ValueError in words the owner can
    act on. The same profile + brain open_session will start; asked before any task exists, because a
    task made first and a spawn that failed after left one more empty "Set up X" per press (B10)."""
    from . import agents as hub, terminal as term
    agent = (agent or hub.default_agent(store)).strip()
    row = store.get_agent(agent)
    if not row: raise ValueError(f'no CLI agent named {agent!r} - add one under {words.name("ai_apps")} first')
    profile = term.with_brain(json.loads(row.get('Config') or '{}'), hub.brain_command(store, agent))
    try: hub._resolve_cmd(profile.get('cmd') or 'claude')
    except FileNotFoundError: raise ValueError(NO_AI) from None
    return agent


def open_task(store, tags: str, title: str):
    """The still-open setup task this press belongs to, or None. A pane that died took its task with
    it only in spirit: the row stayed in progress, went "interrupted" and landed on the owner, so a
    CLI that crashed on launch left one more "Set up codex" per press (TQ-0726). Reuse it instead."""
    for t in store.list_tasks(active_only=True):
        if t.get('Kind') == KIND and t.get('Status') != 'done' and str(t.get('Tags') or '') == tags and t.get('Title') == title:
            return t['TaskId']
    return None


def start(store, server: dict, cid: int, guide: list, fields: list = None, secret_label: str = '',
          agent: str = None, model: str = None, actor: str = 'owner', agent_steps: list = None) -> dict:
    from . import terminal as term
    c = store.get_connector(cid)
    if not c: raise ValueError('connector not found')
    live = live_for(store, cid)
    if live: return {**live, 'existing': True}
    agent, title = runner(store, agent), f"Set up {c.get('Name') or c.get('Type')}"     # resolve first: no task if no AI
    reused = open_task(store, tag(cid), title)
    tid = reused or store.create_task({'Title': title, 'Kind': KIND, 'Status': 'in_progress', 'Tags': tag(cid),
                                       'Summary': f"{agent} walks the owner through the {c.get('Type')} guide in a live session on the card and saves what they give it."}, actor)
    # no repo: the session sits in Taskuary's own data folder, where there is no checkout to attribute dirt to
    try: t = term.open_session(store, agent, tid, None, str(config.home()), 0, 0, actor, model,
                               seed_fn=lambda cwd: prompt(c, server, guide, fields or [], secret_label or '', agent_steps))
    except Exception as e:
        # found is not always runnable (a shim whose target went): the task this press made goes with it
        if not reused: store.delete_task(tid)
        if isinstance(e, OSError): raise ValueError(f"{agent} is set up here but would not start ({e}). Open {words.name('ai_apps')} "
                                                    "and press Test or Update on it, then press this again.") from None
        raise
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
# ── A CONNECTOR'S WALK, AS A GENERAL AGENT (the owner, 2026-10-21: "it should look like general agent working, not code one,
# for AI setup") ──
# Setting up a connector edits no code. It was a coding CLI in a terminal in Taskuary's folder: the owner pressed it on the LinkedIn
# card, got a session on the Board, and read "LinkedIn is not working". Now it is the general agent - the brain the owner's AI
# settings name, API or CLI, never a vendor picked here - on a general task, with the card's Guide as its brief and the card's
# own tools as its hands: put a value it knows onto the card, run the card's Test, ask the person for one step. Its words and its
# steps show on the card (walk); the task is on the Board behind it. The CLI-install setup (clisetup.py) is still a terminal.
WALK_REF = 'connector:setup'
_TOOL = re.compile(r'^[ \t]*\[\[TASKUARY-CARD-(ASK|SAVE|TEST|DONE)(?::([^\]]*))?\]\][ \t]*(.*)$', re.M)
WALKS = {}                       # task id -> {'ask': {'field', 'text'}, 'test': bool, 'done': bool, 'ctx': the card's guide and form}
SETUP_ACTOR = 'setup'            # the card's own notes on the walk ("Saved on the card", "Test passed") - shown as its steps

CARD_TOOLS = (
    "THE CARD'S TOOLS - the only way you act here. Each is a line of its own at the end of your reply; Taskuary carries it out "
    "and takes it out of what the person reads.\n"
    "[[TASKUARY-CARD-ASK: <field key>]] <the one step only the person can do> - an account, a portal, a browser, a phone. The card "
    "shows this step and lights that field. Say exactly where to go, what to click and what to paste into which field. "
    "Use - as the key for a step with no field. One step per reply; then stop and wait.\n"
    "[[TASKUARY-CARD-SAVE: <field key> = <value>]] - put a value YOU know onto the card (an address or a version the guide gives). "
    "Never a secret: client secrets, keys, tokens and passwords are pasted by the person into the card's own masked field, never "
    "into this chat. If they paste one here, tell them to paste it into the field instead, and never repeat it.\n"
    "[[TASKUARY-CARD-TEST]] - run the card's Test. Its answer comes back to you as the next message.\n"
    "[[TASKUARY-CARD-DONE]] - only after a Test passed: the card is connected. Say in one line what now works.\n"
    "You edit no code, open no repository and run nothing on this machine for this walk unless a step in MACHINE NOTES needs it. "
    "When the person presses Save on the card you are told which fields they saved.")


def _secretish(key: str) -> bool:
    from .guard import WRITE_ONLY_CONFIG, _CONFIG_SECRETS
    k = str(key or '').lower()
    return (k == 'secret' or k in _CONFIG_SECRETS or k.endswith(('_secret', '_password', '_token', '_key'))
            or any(k in keys for keys in WRITE_ONLY_CONFIG.values()))


def card_state(store, cid: int, ctx: dict) -> str:
    """What the card holds NOW, as keys - never a value. Read fresh for every turn: the person saves between turns."""
    c = store.get_connector(cid, with_secret=True) or {}
    try: cfg = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    keys = [str(f[1]) for f in ctx.get('fields') or [] if len(f) > 1]
    have = [k for k in keys if cfg.get(k) not in (None, '', [], {})]
    secret = ctx.get('secret_label') or ''
    last = c.get('LastError') and f"failing - {c['LastError']}" or ('passed' if c.get('LastSyncAt') else 'not run yet')
    return (f"THE CARD NOW: set: {', '.join(have) or 'nothing'}; empty: {', '.join(k for k in keys if k not in have) or 'nothing'}"
            + (f"; {secret} (key Secret): {'saved' if c.get('Secret') else 'not saved'}" if secret else '')
            + f"; last Test: {last}.")


def walk_brief(store, cid: int, ctx: dict) -> str:
    c = store.get_connector(cid) or {}
    fields = [f for f in ctx.get('fields') or [] if len(f) > 1]
    notes = [str(s).replace('{base}', 'Taskuary').replace('{cid}', str(cid)).replace('{hdr}', '') for s in ctx.get('agent_steps') or [] if str(s).strip()]
    return '\n'.join(p for p in [
        f"CONNECTING A CARD: you are walking the person through connecting {c.get('Name') or c.get('Type')} (a {c.get('Type')} "
        "connection in Taskuary) on its own card, where they are looking. Guide them one step at a time, put onto the card what you "
        "know, and run its Test until it passes. Start with two lines on what this needs from them, then the first step.",
        'GUIDE (Taskuary\'s own, written for a person): ' + ' '.join(f'{i + 1}. {s}' for i, s in enumerate(ctx.get('guide') or [])),
        'FIELDS on the card: ' + ('; '.join(f'{f[0]} (key {f[1]})' for f in fields) or 'none')
        + (f"; {ctx['secret_label']} (key Secret, write-only)" if ctx.get('secret_label') else '') + '.',
        ('MACHINE NOTES (the card\'s Agent tab - for reference): ' + ' '.join(notes)) if notes else '',
        card_state(store, cid, ctx), CARD_TOOLS] if p)


def walk_task(store, cid: int):
    """The open walk on this card, or None."""
    for t in store.list_tasks(active_only=True):
        if t.get('SourceRef') == WALK_REF and str(t.get('Tags') or '') == tag(cid) and t.get('Status') not in ('done', 'dropped'):
            return t
    return None


def _cid_of(task: dict):
    tags = str((task or {}).get('Tags') or '')
    return int(tags.split(':', 1)[1]) if tags.startswith('connector:') and tags.split(':', 1)[1].isdigit() else None


def note(store, tid: int, text: str): store.add_comment(tid, SETUP_ACTOR, 'agent', text)


def collect(store, tid: int, reply: str) -> str:
    """The card's tools out of a walk's reply (general.send_prompt hands every reply here): a SAVE is made, an ASK is the step the
    card shows and lights, a TEST runs once the turn is over (walk_turn), DONE ends the walk. Any other task's reply is untouched."""
    task = store.get_task(tid) or {}
    if task.get('SourceRef') != WALK_REF or '[[TASKUARY-CARD-' not in str(reply or ''): return reply
    cid, st = _cid_of(task), WALKS.setdefault(tid, {})
    labels = {str(f[1]): str(f[0]) for f in (st.get('ctx') or {}).get('fields') or [] if len(f) > 1}
    for verb, arg, rest in _TOOL.findall(reply):
        verb, arg = verb.upper(), (arg or '').strip()
        if verb == 'ASK':
            field = '' if arg in ('', '-') else arg
            st['ask'] = {'field': field, 'label': labels.get(field) or ('' if field != 'Secret' else (st.get('ctx') or {}).get('secret_label') or ''),
                         'text': rest.strip()}
        elif verb == 'SAVE':
            key, _, value = arg.partition('=')
            key, value = key.strip(), value.strip()
            if not key or cid is None: continue
            if _secretish(key):
                note(store, tid, f'✗ Not saved by the agent: {labels.get(key) or key} is yours to paste into its field on the card.')
                continue
            row = store.get_connector(cid) or {}
            try: cfg = json.loads(row.get('ConfigJson') or '{}')
            except ValueError: cfg = {}
            store.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({**cfg, key: value})}, SETUP_ACTOR)
            note(store, tid, f'✓ Saved on the card: {labels.get(key) or key}')
        elif verb == 'TEST': st['test'] = True
        elif verb == 'DONE': st['done'] = True
    kept = _TOOL.sub(lambda m: m.group(3) if m.group(1).upper() == 'ASK' else '', reply)
    return '\n'.join(line for line in kept.splitlines()).strip() or (st.get('ask') or {}).get('text') or 'Working on the card.'


def _spawn(fn, store, cid, tid, *args):
    """A turn on its own thread - the card's press returns at once and the card follows the walk. `turning` says so from the
    press on, before the brain has started: a card polled in that gap read idle with nothing asked."""
    import threading
    WALKS.setdefault(tid, {})['turning'] = True
    def run():
        try: fn(store, cid, tid, *args)
        finally: WALKS.setdefault(tid, {})['turning'] = False
    threading.Thread(target=run, daemon=True).start()


def walk_turn(store, cid: int, tid: int, text: str, as_owner: bool = False, depth: int = 0):
    """One turn of the walk, and the Test it asked for: its answer goes back to the agent as the next turn (three at most - a card
    that keeps failing is said, not retried for ever)."""
    from . import channels, general
    st = WALKS.setdefault(tid, {})
    st.pop('ask', None); st['test'] = False
    try:
        sess = general.session_for(tid) or general.start_session(store, tid, actor='owner')
        sess.send_prompt(text, as_owner=as_owner, echo=as_owner, delivery_instructions=walk_brief(store, cid, st.get('ctx') or {}))
    except Exception as e:
        note(store, tid, f"✗ The agent could not answer: {str(e)[:300]}")
        return
    if st.pop('test', False):
        out = channels.test_connector(store, cid)
        note(store, tid, ('✓ Test passed: ' if out.get('ok') else '✗ Test failed: ') + str(out.get('detail') or '')[:400])
        if depth < 3:
            walk_turn(store, cid, tid, f"The card's Test {'passed' if out.get('ok') else 'failed'}: {out.get('detail')}. Continue the walk.",
                      False, depth + 1)


def walk_view(store, cid: int) -> dict:
    """What the card draws: the walk's steps (what the agent said, what was saved and tested, what you said), what it is doing
    now, the one step it needs from the person - with the field to light - and whether it is done."""
    from . import general
    t = walk_task(store, cid)
    if not t: return {'session': None, 'steps': [], 'busy': False, 'now': '', 'ask': None, 'done': False}
    tid, st = t['TaskId'], WALKS.get(t['TaskId'], {})
    sess = general.session_for(tid)
    steps = []
    for c in store.list_comments(tid):
        body = str(c.get('Body') or '').strip()
        if not body: continue
        if c.get('ActorType') == general.ASSISTANT_TYPE: steps.append({'kind': 'agent', 'text': body})
        elif c.get('ActorType') == general.USER_TYPE: steps.append({'kind': 'you', 'text': body})
        elif c.get('Actor') == SETUP_ACTOR: steps.append({'kind': 'failed' if body.startswith('✗') else 'done', 'text': body.lstrip('✓✗ ').strip()})
    busy = bool((sess and sess.busy) or st.get('turning'))
    now = ''
    if busy:
        last = next((e for e in reversed(sess.trace if sess else []) if e.get('type') in ('progress', 'live', 'tool_call')), None)
        now = (str(last.get('detail') if isinstance(last.get('detail'), str) else last.get('name') or '') if last else '')[:200] or 'Thinking about the next step…'
    from .store import task_ref
    return {'session': {'taskId': tid, 'ref': task_ref(tid), 'sid': sess.sid if sess else None},
            'steps': steps[-14:], 'busy': busy, 'now': now, 'ask': None if busy else st.get('ask'), 'done': bool(st.get('done'))}


def ready_why(store) -> str:
    """'' when a brain can take a walk - any CLI or API the owner connected, the general agent's own choice among them."""
    from . import general
    return '' if general.provider_options(store) else NO_AI


def start_walk(store, cid: int, ctx: dict, actor: str = 'owner') -> dict:
    from . import general
    c = store.get_connector(cid)
    if not c: raise ValueError('connector not found')
    t = walk_task(store, cid)
    if t:
        WALKS.setdefault(t['TaskId'], {})['ctx'] = ctx
        if not general.session_for(t['TaskId']): general.start_session(store, t['TaskId'], actor=actor)
        return {**walk_view(store, cid), 'existing': True}
    why = ready_why(store)
    if why: raise ValueError(why)
    name = c.get('Name') or c.get('Type')
    tid = store.create_task({'Title': f'Set up {name}', 'Kind': 'general', 'Status': 'in_progress', 'Tags': tag(cid),
                             'Source': 'connector', 'SourceRef': WALK_REF,
                             'Summary': f"The general agent walks the owner through connecting {name} on its card: a step at a time, "
                                        "what it knows put onto the card, and the card's Test until it passes."}, actor)
    WALKS[tid] = {'ctx': ctx}
    try: general.start_session(store, tid, actor=actor)
    except Exception:
        store.delete_task(tid); WALKS.pop(tid, None); raise
    store.audit('connector', cid, 'ai_setup', actor, detail={'task': tid, 'agent': 'general'})
    _spawn(walk_turn, store, cid, tid, 'Begin the walk: say what this needs from the person, then the first step.')
    return {**walk_view(store, cid), 'existing': False}


def walk_said(store, cid: int, ctx: dict, text: str = '', saved: list = None) -> dict:
    """The person answered - in words on the card, or by saving fields on it. Either goes to the agent as its next turn."""
    t = walk_task(store, cid)
    if not t: raise ValueError('no walk is open on this card - press Get AI to set it up')
    tid = t['TaskId']
    WALKS.setdefault(tid, {})['ctx'] = ctx or WALKS[tid].get('ctx') or {}
    text = str(text or '').strip()
    if text: _spawn(walk_turn, store, cid, tid, text, True)
    elif saved:
        names = ', '.join(str(s) for s in saved)
        note(store, tid, f'✓ You saved on the card: {names}')
        _spawn(walk_turn, store, cid, tid, f'The person saved these on the card: {names}. Continue the walk.')
    return walk_view(store, cid)


def finish_walk(store, tid: int, actor: str = 'owner') -> dict:
    """Done: the agent goes and the task closes - the card's Test said the rest."""
    from . import general
    sess = general.session_for(tid)
    if sess: sess.close(learn=False)
    WALKS.pop(tid, None)
    note(store, tid, 'Setup closed.')
    if (store.get_task(tid) or {}).get('Status') not in ('done', 'dropped'): store.update_task(tid, {'Status': 'done'}, actor)
    return {'wrap': 'done', 'taskId': tid}
