"""Roles: one click from "I do accounts payable" to a Taskuary set up for it.

Everything a role needs already existed as a separate thing to find and fill in: PLAYBOOKS (how each
kind of job is done, playbooks.py), a WORKFLOW (a scheduled job, workflows.py) and the ledger it checks.
Someone who is not technical never assembled them, so a role is all of them written down together, and
apply() lays them out - no mail is moved, a task's general work runs on the assistant (the owner, 2026-11-04):

- each shipped playbook is copied into ~/.taskuary/playbooks, never over one already there;
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
        'playbooks': ('vendor-payment-inquiry', 'portal-bill-approvals'),
        'ledger': 'intacct',
        # the portal posts what is approved to the ledger by itself (the owner, 2026-10-08: "stampli syncs to Intacct. we
        # just need to approve them if they look good") - so the job is the approval, the ledger only checks it
        'workflow': {'type': 'agent', 'title': 'Bills waiting for approval in the portal',
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
    """The roles on offer, each saying whether this install already has it: every playbook it ships, and its workflow."""
    from . import playbooks
    return [{'name': k, 'title': r['title'], 'blurb': r['blurb'], 'portal_needed': bool(r.get('workflow')),
             'applied': all(playbooks.read(s) is not None for s in r['playbooks']) and (not r.get('workflow') or _found(store, r) is not None)}
            for k, r in ROLES.items()]


def _found(store, r):
    "The role's workflow already made - found by its title."
    return next((s['SourceId'] for s in store.list_sources(active_only=False)
                 if s.get('Channel') == 'report' and s.get('Address') == r['workflow']['title']), None)


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
    if (sid := _found(store, r)) is not None: return sid
    c = {**wf, 'prompt': wf['prompt'].format(portal=portal or 'the address the owner gives you (ask once, in the session)')}
    return store.save_source({'Channel': 'report', 'Address': wf['title'], 'Owner': 'role', 'Active': 0,
                              'ConfigJson': json.dumps(c)}, 'role')


def apply(store, name: str, portal: str = '') -> dict:
    """Lay the role out. Returns what changed, so the page and the chat can say it in plain words. The owner's mail is never
    moved (the owner, 2026-11-04)."""
    r = ROLES.get(name)
    if not r: raise ValueError(f'unknown role {name!r} - one of {", ".join(ROLES)}')
    books = _playbooks(r)
    narrowed = _ledger(store, r)
    wid = _workflow(store, r, portal.strip())
    out = {'role': name, 'playbooks_added': books,
           'ledger_narrowed': narrowed, 'workflow_id': wid, 'workflow_title': (r.get('workflow') or {}).get('title', '')}
    store.audit('role', 0, 'apply', 'owner', detail=out)
    logger.info(f'role {name}: {out}')
    return out
