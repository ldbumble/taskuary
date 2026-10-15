"""First run, as three plain questions on the assistant canvas: what AI do you have, what email do you have, any other
connection - then the mail is read and sorted.

The owner, 2026-10-14: "Think about a idiot user who knows nothing about nothing and he should setup this app in 2 steps
... it should never drop the user". Setup was a checklist popup over four tabs; a first run that connected Codex and
Outlook still sorted nothing, because nothing made Codex the brain (setup trace, 2026-10-14). Here every choice is one
click on a card, each card does the WHOLE step - connect, test, switch on, make it the brain, start reading - and every
answer says what happened and what to press next. Nothing here waits without a limit.

The step is read from real state (setup.py's own readers), never stored: a step is done when the thing works. The cards
under each question are the Connections page's own (the owner, 2026-10-15: "Don't create new ui. keep the same as we have in
connections but just show them/tell what to do next") - this file says which step, and the one line on top.
"""
import json
from loguru import logger

# the CLIs most people already pay for, always offered; any OTHER installed CLI joins them
OFFERED = ('claude', 'codex', 'gemini', 'copilot')
PLAIN = {'claude': ('Claude', 'Claude Code - if you pay for Claude'), 'codex': ('ChatGPT', 'Codex - if you pay for ChatGPT'),
         'gemini': ('Gemini', 'Gemini CLI - free with a Google account'), 'copilot': ('Copilot', 'GitHub Copilot CLI - if you pay for Copilot')}
KEYS = (('anthropic', 'Claude API key', 'console.anthropic.com → API Keys'),
        ('openai', 'OpenAI API key', 'platform.openai.com → API keys'))
MAIL = (('outlook', 'Microsoft 365 / Outlook', 'Work email or Outlook.com - one sign-in, no password here'),
        ('gmail', 'Gmail', 'Your Gmail address and a Google App Password'),
        ('imap', 'Other email', 'Any other mailbox: address, server and password'))
TEST_SECONDS = 60          # a CLI that has not answered in a minute is not going to: say so, never spin
# a pick that failed, kept until one works: the NEXT line said "pick your AI" again after it, and a reload lost Sign in (2026-10-15)
FIX = 'first_run_fix'


def unchosen(store) -> bool:
    """No AI picked yet, on an install that sorts nothing: what a blank brain falls to is a guess, not the owner's - and asking it
    turned the bell red over the question asking which AI (a fresh-home run, 2026-10-15)."""
    from . import setup as setup_mod
    return not str(store.get_setting('triage_ai') or '').strip() and not setup_mod._first_items(store)


def _fix(store):
    try: return json.loads(store.get_setting(FIX) or 'null')
    except ValueError: return None


def _close_setup(store, name: str):
    """The Sign in pane's "Set up" task, closed once the AI answers - it stayed under On you after it worked."""
    from . import clisetup
    for t in store.list_tasks(active_only=True):
        if t.get('Kind') == clisetup.KIND and str(t.get('Tags') or '') == clisetup.tag(name) and t.get('Status') not in ('done', 'dropped'):
            clisetup.finish(store, t['TaskId'], 'owner')


def _sorting(store) -> int:
    """Mail read in and not judged yet - what the "reading" step counts down."""
    return int((store._one("SELECT COUNT(*) AS n FROM message WHERE Status IN ('new','triaging') "
                           "AND IFNULL(Direction,'in')<>'out'") or {}).get('n') or 0)


def state(store) -> dict:
    """{step, brain, ais, keys, mail, connected, sorting, sorted, next}. `step` is ai -> email -> reading -> done."""
    from . import clis, setup as setup_mod
    brain, inbound, items = setup_mod._ai(store), setup_mod._inbound(store), setup_mod._first_items(store)
    # the CLIs, not the profiles that run them: detect also lists every worker on claude, and the first run showed eight
    # "Claude Code" cards (a fresh-install screenshot, 2026-10-14)
    found = list({k['name']: k for k in clis.detect(store) if not k.get('profile')}.values())
    ais = [k for k in found if k['name'] in OFFERED or k['installed']]
    ais.sort(key=lambda k: (k['name'] not in OFFERED, not k['installed'], OFFERED.index(k['name']) if k['name'] in OFFERED else 9))
    # the three most people pay for lead; any other CLI on this machine is offered under "more", never in the first glance
    ais = [{'name': k['name'], 'title': PLAIN.get(k['name'], (k['label'], ''))[0], 'sub': PLAIN.get(k['name'], ('', 'Already on this computer'))[1],
            'installed': k['installed'], 'install': k['install'] if k.get('installable') else '', 'setup': k.get('setup') or '',
            'why_not': k.get('why_not') or '', 'more': k['name'] not in OFFERED} for k in ais]
    by = lambda t: (store.get_connector_by_type(t) or {}).get('ConnectorId')
    keys = [{'type': t, 'title': label, 'sub': where, 'cid': by(t)} for t, label, where in KEYS if by(t)]
    mail = [{'type': t, 'title': label, 'sub': sub, 'cid': by(t)} for t, label, sub in MAIL if by(t)]
    # STEP 1 IS A CHOICE, not a CLI that happens to be on the PATH: Claude Code installed and never signed in read "ready" while
    # every mail failed. Done when the owner picked a brain that works - or when mail is already being sorted (an install that
    # set up before this card existed never sees it again)
    chosen = bool(str(store.get_setting('triage_ai') or '').strip()) or bool(items)
    step = ('done' if brain['ready'] and inbound and items else 'ai' if not (brain['ready'] and chosen)
            else 'email' if not inbound else 'reading')
    sorting = _sorting(store)
    # the AI, not the profile that runs it: a fresh install's brain is `coder` on claude, and step 2 said "coder is ready"
    from . import agents
    pick, raw = str(brain.get('pick') or ''), (brain.get('Name') or '').replace(' (CLI)', '')
    via = next((o['cli'] for o in agents.cli_agent_options(store) if f"cli:{o.get('value')}" == pick), '') if pick.startswith('cli:') else ''
    cli = via or next((k['name'] for k in found if k['name'] == raw or k['name'] in pick), '')
    name = PLAIN[cli][0] if cli in PLAIN else raw
    fix = _fix(store) if step == 'ai' else None
    ask = "What AI do you have? Click it below - Taskuary checks it works and uses it to sort your mail."
    nxt = {'ai': f"{fix['why']} Or pick another AI below." if fix else ask,
           'email': f"{name or 'Your AI'} is ready. What email do you have? Click it below - Microsoft 365 is one sign-in.",
           'reading': (f"Sorting {sorting} email{'s' if sorting != 1 else ''} now. Any other connection you'd like to set up while it reads?"
                       if sorting else "Reading your mail now. Any other connection you'd like to set up while it reads?"),
           'done': "You're set up. Any other connection you'd like to set up? Click it below - or press Walk me through my tasks."}[step]
    # what is next, as the rail and the top bar's chip say it - from here, so the three never disagree (2026-10-15)
    todo = {'ai': 'pick your AI', 'email': 'connect your email', 'reading': 'reading your mail', 'done': ''}[step]
    return {'step': step, 'todo': todo, 'brain': {'ready': brain['ready'], 'name': name, 'why': brain.get('why') or ''}, 'fix': fix,
            'ais': ais, 'keys': keys, 'mail': mail, 'connected': inbound, 'sorting': sorting, 'sorted': len(items), 'next': nxt}


# ONE PICK IS THE AI (the owner, 2026-10-14: "this is only triage ai not the other ai's"): the four brains - triage, general
# tasks, the Assistant's voice and coding sessions - each read their own setting, and the first run set only triage's. A key
# cannot run a coding session, so a pasted key leaves that one where it was.
BRAINS = ('triage_ai', 'assistant_ai', 'concierge_ai')


def _everywhere(store, pick: str, cli: str = ''):
    for k in BRAINS: store.set_setting(k, pick, 'owner')
    if cli: store.set_setting('default_brain', cli, 'owner')


def choose_cli(store, cfg: dict, name: str) -> dict:
    """The owner clicked a CLI card: connect it, test it, make it the brain. {ok, why, fix} - `fix` is the ONE thing to press
    when it did not work: 'install' or 'signin'."""
    from . import agents, cli_connections, clis, config
    k = next((k for k in clis.detect(store) if k['name'] == name), None)
    if not k: return {'ok': False, 'why': f'Taskuary does not know a CLI called {name}.', 'fix': ''}
    label = PLAIN.get(name, (k['label'],))[0]
    def failed(out):
        store.set_setting(FIX, json.dumps({'name': name, 'title': label, 'fix': out['fix'], 'setup': k.get('setup') or '', 'why': out['why']}), 'owner')
        return out
    if not k['installed']:
        return failed({'ok': False, 'fix': 'install' if k.get('installable') else '',
                'why': f"{label} isn't on this computer yet." + (' Press Install - it takes about a minute.' if k.get('installable')
                                                                  else f" {k.get('why_not') or 'Install it, then click its card again.'}")})
    conns = cfg.setdefault('cli_connections', {})
    key = next((n for n, c in conns.items() if cli_connections.cli_key(c.get('cmd')) == name), None)
    if not key:
        key = name
        conns[key] = cli_connections.with_defaults({f: k[f] for f in cli_connections.COMMAND_FIELDS if f in k})
        config.save(cfg); cli_connections.sync(cfg, store)
    try: agents.run_cli({**conns[key], 'timeout': TEST_SECONDS}, 'Reply with exactly: ok', lambda *a: None)
    except Exception as e:
        logger.info(f'first run: {name} did not answer - {e}')
        return failed({'ok': False, 'fix': 'signin' if k.get('setup') else '',
                'why': f"{label} is installed but didn't answer - it most likely needs you to sign in once."
                       + (' Press Set it up below, sign in where it asks, then click the card again.' if k.get('setup') else ''),
                'detail': str(e)[:200]})
    worker = next((o['value'] for o in agents.cli_agent_options(store) if o['cli'] == name), '') or key
    _everywhere(store, f'cli:{worker}', cli=key)                       # the owner's own click: theirs, not an auto-pick
    store.audit('setting', 0, 'first_run_brain', 'owner', detail={'cli': name, 'pick': f'cli:{worker}'})
    store.set_setting(FIX, '', 'owner'); _close_setup(store, name)
    return {'ok': True, 'why': f'{label} works - it will sort your mail.'}


def choose_key(store, typ: str, secret: str, cid: int = None, config: dict = None) -> dict:
    """The owner pasted an API key on an AI card: save it (and the card's own fields - Azure's endpoint), switch the card on,
    test it, make it the brain."""
    from .channels import test_connector
    c = store.get_connector(cid) if cid else store.get_connector_by_type(typ)
    secret = str(secret or '').strip()
    if not c: return {'ok': False, 'why': f'There is no {typ} card here.'}
    if len(secret) < 12: return {'ok': False, 'why': "That doesn't look like a whole API key - copy it again and paste the full thing."}
    row = {'ConnectorId': c['ConnectorId'], 'Secret': secret, 'Active': 1}
    if config:
        try: conf = json.loads(c.get('ConfigJson') or '{}')
        except ValueError: conf = {}
        row['ConfigJson'] = json.dumps({**conf, **{k: v for k, v in config.items() if str(v).strip()}})
    store.save_connector(row, 'owner')
    out = test_connector(store, c['ConnectorId'])
    if not out.get('ok'):
        store.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 0}, 'owner')
        return {'ok': False, 'why': f"That key didn't work: {str(out.get('detail') or 'the provider said no')[:200]}. Check you copied all of it."}
    _everywhere(store, f"connector:{c['ConnectorId']}")
    store.set_setting(FIX, '', 'owner')
    return {'ok': True, 'why': f"Your {c.get('Name') or typ.capitalize()} key works - it will sort your mail."}


def connect_mail(store, typ: str, address: str, secret: str, host: str = '') -> dict:
    """Gmail or any IMAP mailbox: address + password, switched on, tested, read. Microsoft 365 signs in instead (ms/signin)."""
    from .channels import test_connector
    if typ not in ('gmail', 'imap'): return {'ok': False, 'why': 'Microsoft 365 signs in with its own button.'}
    c = store.get_connector_by_type(typ)
    address, secret, host = str(address or '').strip(), str(secret or '').strip(), str(host or '').strip()
    if not c: return {'ok': False, 'why': f'There is no {typ} card here.'}
    if '@' not in address: return {'ok': False, 'why': 'Type your full email address, like you@example.com.'}
    if not secret: return {'ok': False, 'why': 'Paste the password' + (' - for Gmail, the 16-letter App Password.' if typ == 'gmail' else '.')}
    try: conf = json.loads(store.get_connector(c['ConnectorId']).get('ConfigJson') or '{}')
    except ValueError: conf = {}
    conf['address'] = address
    if typ == 'imap': conf['imap_host'] = host or f"imap.{address.split('@', 1)[1]}"
    store.save_connector({'ConnectorId': c['ConnectorId'], 'ConfigJson': json.dumps(conf), 'Secret': secret.replace(' ', '') if typ == 'gmail' else secret,
                          'Active': 1}, 'owner')
    out = test_connector(store, c['ConnectorId'])
    if not out.get('ok'):
        store.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 0}, 'owner')
        said = str(out.get('detail') or '').strip()[:160].rstrip('.')
        # a reason that already says what to check is said once - "online.. Check the address" read twice (2026-10-15)
        hint = (' For Gmail you need an App Password, not your normal password: myaccount.google.com/apppasswords'
                if typ == 'gmail' else '' if 'check' in said.lower() else ' Check the address, the password and the server name.')
        return {'ok': False, 'why': f"Couldn't sign in to {address}: {said}.{hint}"}
    for s in store.list_sources(active_only=False):                 # the test claimed the mailbox; make sure it is ON
        if s['Channel'] == 'email' and (s['Address'] or '').lower() == address.lower() and not s.get('Active'):
            store.save_source({**s, 'Active': 1, 'ConnectorId': c['ConnectorId']}, 'owner')
    mine = store.owner() or {}
    if not mine.get('owner') or mine.get('owner') == 'the owner':
        guess = ' '.join(w.capitalize() for w in address.split('@')[0].replace('.', ' ').replace('_', ' ').split()) or address
        store.set_setting('owner_name', guess, 'owner'); store.set_setting('owner_email', address, 'owner')
    return {'ok': True, 'why': f'Connected {address} - reading your mail now.'}
