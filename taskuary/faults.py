"""FAILURES ON PURPOSE, for the dead-end walk only (website/deadend_check.mjs, 2026-10-18). The walk pressed only what the demo
world let it, with its refusals switched off, so no send, agent start or sign-in ever failed in front of it and a failure's way out
was never pressed (the re-audit: "the dead-end check is hollow"). This mocks at the boundary - the mailbox, the coding tool, the
AI - and never touches a refusal: the walk's launcher calls `install(server.app)`, and nothing else imports this module.

Inert unless TASKUARY_FAULTS is set AND the home is a scratch one: a stray import in a real install does nothing. With it, one
fault at a time is chosen by POST /api/test/fault {"fault": name}; '' is the world working (a mailbox that sends)."""
import os, smtplib, tempfile
from pathlib import Path

ENV = 'TASKUARY_FAULTS'
# what each fault raises, and where: a send (the mailbox), an agent start (the coding tool), or the AI itself
SEND = {'auth': lambda: smtplib.SMTPAuthenticationError(535, b'5.7.8 Authentication unsuccessful'),
        'reject': lambda: smtplib.SMTPRecipientsRefused({'erin.blake@northwind.example': (550, b'5.1.1 no such user')}),
        'unknown': lambda: _timeout(),
        'nomailbox': lambda: _no_mailbox()}
START = {'nocli': lambda: FileNotFoundError(2, 'No such file or directory', 'claude'),
         'badrepo': lambda: ValueError('working directory does not exist: C:/nowhere/portal')}
FAULTS = ('', *SEND, *START)
NOW = {'fault': ''}


def _timeout():
    import requests
    return requests.exceptions.ReadTimeout('the mail server did not answer in 30 seconds')


def _no_mailbox():
    from . import outbound
    return outbound.Fixable('no mailbox is connected to send from', *outbound.MAIL)


def scratch_home() -> bool:
    """Only a throwaway home: the system temp folder, never ~/.taskuary."""
    home = Path(os.environ.get('TASKUARY_HOME') or Path.home() / '.taskuary').resolve()
    return Path(tempfile.gettempdir()).resolve() in home.parents


def active() -> bool: return bool(os.environ.get(ENV)) and scratch_home()


def install(app) -> bool:
    """Patch the three boundaries and add the switch. False, and nothing touched, outside a walk."""
    if not active(): return False
    from . import advisor, agents, concierge, general, llm, outbound, terminal

    def send(*a, **kw):
        f = NOW['fault']
        if f in SEND: raise SEND[f]()
        return {'channel': 'email', 'to': kw.get('to') or [], 'cc': kw.get('cc') or [], 'mailbox': 'alex@northwind.example'}
    def start(*a, **kw):
        f = NOW['fault']
        raise START[f]() if f in START else RuntimeError('the walk starts no agents')
    outbound.reply_to_message = send
    outbound.reconcile_sent = lambda *a, **kw: None                 # no receipt in Sent: a lost answer stays unknown
    outbound.send_probe = lambda *a, **kw: ''                       # a mailbox is connected - its sends are the fault's to fail
    terminal.start_on_task = start
    general.start_session = start
    agents.coding_ready = lambda *a, **kw: NOW['fault'] in START     # the coding agent is offered only where its start is the test
    for m in (llm, advisor): m.build_llm = lambda *a, **kw: None     # no AI: the walk never calls a real model
    concierge.brain = lambda *a, **kw: None

    from fastapi import HTTPException
    def switch(body: dict):
        f = str((body or {}).get('fault') or '')
        if f not in FAULTS: raise HTTPException(422, f'no such fault: {f} (one of {", ".join(FAULTS)})')
        NOW['fault'] = f
        return {'fault': f}
    app.add_api_route('/api/test/fault', switch, methods=['POST'])
    return True
