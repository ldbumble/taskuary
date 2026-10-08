"""Roles: one click from "I do accounts payable" to a Taskuary set up for it.

Everything a role needs already existed as a separate thing to find and fill in: a PROFILE (the
worker and its rules document, agents.py), PLAYBOOKS (how each kind of job is done, playbooks.py),
a WORKFLOW (a scheduled job, workflows.py), and the routing that sends mail to the worker. Someone
who is not technical never assembled the four, so a role is the four written down together, and
apply() lays them out:

- the profile is an ordinary agent row plus its document (templates/<profile>.md), on the roster;
- each shipped playbook is copied into ~/.taskuary/playbooks, never over one already there;
- `default_profile` is set, so general work that triage names no worker for lands on this one
  (agents.routed_role);
- the role's workflow is created SWITCHED OFF. A scheduled browser job needs a sign-in that only
  the owner can type, so it starts when they have signed in once and turned it on;
- a ledger the role writes to is narrowed to read when nobody has chosen its Authority: every bill
  becomes a proposal the owner approves. The playbooks say so too, but a prompt is not a control.

Applying twice changes nothing the first apply or the owner already set.
"""
import json
from pathlib import Path
from loguru import logger

TEMPLATES = Path(__file__).parent / 'templates'

ROLES = {
    'ap': {
        'title': 'Accounts payable',
        'blurb': 'Vendor mail answered from the ledger; bills waiting in the approval portal checked against it, approved on your yes.',
        'profile': 'ap', 'kind': 'accounts-payable',
        'purpose': 'ACCOUNTS PAYABLE - a vendor asking about an invoice, a bill, a statement or a payment; bills to '
                   'enter or reconcile. Looks them up in the accounting system and drafts the answer',
        'playbooks': ('vendor-payment-inquiry', 'portal-bill-approvals'),
        'ledger': 'intacct',
        # the portal posts what is approved to the ledger by itself (the owner, 2026-10-08: "stampli syncs to Intacct. we
        # just need to approve them if they look good") - so the job is the approval, the ledger only checks it
        'workflow': {'type': 'agent', 'title': 'Bills waiting for approval in the portal', 'agent': 'ap',
                     'browser': True, 'access': 'write', 'daily_at': '08:00', 'uses': ['intacct'],
                     'prompt': 'Follow the playbook "Review the bills waiting for approval in the bill-approval portal": '
                               'open the portal at {portal}, list every bill waiting for approval, check each against the '
                               'ledger, give each a verdict, and ask the owner which to approve.',
                     'ask_first': 'EVERY approval: approve only the bills the owner names in this conversation after seeing '
                                  'your table; never reject, re-code or edit a bill; never touch vendor or bank details; never '
                                  'write to the ledger',
                     'done_when': 'the table of waiting bills with a verdict for each is on the task, and every bill the owner '
                                  'named is approved in the portal and listed - or the owner said approve none'},
    },
}


def playbook_text(slug: str) -> str: return (TEMPLATES / 'playbooks' / f'{slug}.md').read_text(encoding='utf-8')


def catalog(store) -> list:
    """The roles on offer, each saying whether this install already has it."""
    from . import agents
    return [{'name': k, 'title': r['title'], 'blurb': r['blurb'], 'profile': r['profile'],
             'applied': bool(store.get_agent(r['profile'])),
             'is_default': (store.get_setting('default_profile') or '') == r['profile'],
             'portal_needed': bool(r.get('workflow'))} for k, r in ROLES.items()]


def _profile(store, cfg, r, routed: bool = True) -> bool:
    """The worker, inheriting the coding agent's CLI the way the shipped roles do (agents.seed_profiles) - on the
    triage roster only when the owner's mail is to reach it. An existing one is the owner's and is left as it is."""
    from . import agents, cli_connections
    name = r['profile']
    if name in (cfg.get('agents') or {}) or store.get_agent(name): return False
    prof = {**agents.cli_inheritance(cfg), 'kind': r['kind'], 'purpose': r['purpose'], 'triage_enabled': bool(routed)}
    cfg.setdefault('agents', {})[name] = prof
    store.upsert_agent(name, r['kind'], 'cli', json.dumps(prof))
    try: cli_connections.sync(cfg, store, name)
    except ValueError: pass                          # no CLI yet: the row stands, the Agents page asks for one
    agents.ensure_profile_document(store, name)
    return True


def _playbooks(r) -> list:
    from . import playbooks
    return [playbooks.write(s, playbook_text(s)) for s in r['playbooks'] if playbooks.read(s) is None]


def _ledger(store, r) -> str:
    """Narrow the ledger to read - only when its Authority was never chosen. An owner who set it
    has decided, and this must not undo that."""
    c = store.get_connector_by_type(r['ledger']) if r.get('ledger') else None
    if not c or (c.get('Scope') or '').strip(): return ''
    store.save_connector({'ConnectorId': c['ConnectorId'], 'Scope': 'read'}, 'role')
    return c.get('Name') or r['ledger']


def _workflow(store, r, portal: str):
    """The role's daily job, created OFF. Found again by title, so applying twice makes one."""
    wf = r.get('workflow')
    if not wf: return None
    for s in store.list_sources(active_only=False):
        if s.get('Channel') == 'report' and s.get('Address') == wf['title']: return s['SourceId']
    c = {**wf, 'prompt': wf['prompt'].format(portal=portal or 'the address the owner gives you (ask once, in the session)')}
    return store.save_source({'Channel': 'report', 'Address': wf['title'], 'Owner': 'role', 'Active': 0,
                              'ConfigJson': json.dumps(c)}, 'role')


def apply(store, cfg, name: str, portal: str = '', route_mail: bool = True) -> dict:
    """Lay the role out. Returns what changed, so the page and the chat can say it in plain words.

    `route_mail` False sets up the worker and its job WITHOUT moving the owner's mail: no default route, and the
    worker stays off triage's roster - trying a role out (the owner, 2026-10-08) is not handing over the inbox."""
    from . import config
    r = ROLES.get(name)
    if not r: raise ValueError(f'unknown role {name!r} - one of {", ".join(ROLES)}')
    made = _profile(store, cfg, r, route_mail)
    if made: config.save(cfg)
    books = _playbooks(r)
    was = store.get_setting('default_profile') or ''
    if route_mail and was != r['profile']: store.set_setting('default_profile', r['profile'], 'role')
    narrowed = _ledger(store, r)
    wid = _workflow(store, r, portal.strip())
    out = {'role': name, 'profile': r['profile'], 'profile_added': made, 'playbooks_added': books,
           'default_profile': r['profile'] if route_mail else was, 'default_was': was, 'mail_routed': bool(route_mail),
           # a worker that was already here keeps its own roster setting - so triage may still hand it mail
           'on_roster': bool(json.loads((store.get_agent(r['profile']) or {}).get('Config') or '{}').get('triage_enabled', True)),
           'ledger_narrowed': narrowed, 'workflow_id': wid, 'workflow_title': (r.get('workflow') or {}).get('title', '')}
    store.audit('role', 0, 'apply', 'owner', detail=out)
    logger.info(f'role {name}: {out}')
    return out
