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
    # ...and the matrix's world, seeded once the app is up: seeded before, the start's recovery read every agent as a dead run
    def seed_world():
        from . import server
        return world(server.store)
    app.add_api_route('/api/test/world', seed_world, methods=['POST'])
    return True


# ── THE ADVISOR MATRIX'S WORLD (website/advisor_matrix.mjs, 2026-10-19) ──────────────────────────────────────────────────────────
# The owner: "did you test every single advisor interaction matches what's on the screen?" The demo world holds the states a morning
# happens to leave; this adds every state the Advisor can see - a reply owed with no draft, sent with nothing back, sent then written
# again, a send that failed; agents of both kinds working, asking, finished, failed and stopped with a saved conversation; a goal with
# no news, a meeting soon and one later, a task put off, one with every todo ticked, one reopened by mail. Invented Northwind people
# only. Called by the matrix's launcher after demo.seed, with the demo's scripted Advisor wired in (scripted) - never by the app.
ERIN, GAIL, PAULA, RAY = (('Erin Blake', 'erin@northwind.example'), ('Gail Moreno', 'gail@northwind.example'),
                          ('Paula Vance', 'paula@northwind.example'), ('Ray Colton', 'ray@northwind.example'))


def scripted() -> bool:
    """The Advisor answers from the demo's script while drafting and the chat still have no AI: the faults world had no Advisor at
    all, so no failure was ever walked with a line over it (the Advisor group's verify, 2026-10-19)."""
    if not active(): return False
    from . import advisor, demo
    advisor.build_llm = lambda *a, **kw: demo.brain()
    return True


def world(store) -> dict:
    """Seed the states the demo lacks; returns {state: task id} so each record is named by the state it walks."""
    import time, uuid
    from datetime import datetime, timedelta
    from . import assistant, demo, terminal, workerstate
    from .testing import Factory
    if not active(): return {}
    from . import advisor
    store.set_setting(advisor.CAP_KEY, '100000', 'walk')      # every moment judged: the hour's cap read "no suggestion" over most of them
    f, out = Factory(store), {}
    f.actor = 'triage'
    at = lambda h=0: (datetime.now() - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')
    def asked(title, who, body, h, kind='reply'):
        tid = f.task(title=title, status='open', kind=kind)
        mid = f.message(task_id=tid, subject=title, body=body, from_name=who[0], from_email=who[1], sent_at=at(h), conversation_id=f'email:{title}')
        f.route(mid, tid, 'create', 'a question addressed to you'); return tid, mid
    # a review's delivery and decision are written by the send, never by add_review
    def sent(rid, when): store._exec("UPDATE review SET DeliveryState='sent', DecidedAt=? WHERE ReviewId=?", (when, rid))
    out['reply-no-draft'] = asked('Badge access for the new AP clerk?', GAIL, 'Can you approve badge access for the new clerk by Friday?', 5)[0]
    for name, title, who, body, new in (('sent-quiet', 'Q3 accruals file', PAULA, 'Could you send the Q3 accruals file when you have it?', None),
                                        ('sent-then-new', 'Vendor master clean-up', RAY, 'Can you confirm which vendors we are retiring?',
                                         'Thanks - and the two in Fairhaven, are they going too?')):
        tid, mid = asked(title, who, body, 8)
        sent(f.review(tid, mid, status='approved', draft='Done - it is on the shared drive.', final='Done - it is on the shared drive.'), at(3))
        if new: f.message(task_id=tid, subject=f'RE: {title}', body=new, from_name=who[0], from_email=who[1], sent_at=at(1), conversation_id=f'email:{title}')
        out[name] = tid
    tid, mid = asked('Lease renewal for the Elm Street office', ERIN, 'Is the lease renewal signed? The landlord is asking.', 6)
    rid = f.review(tid, mid, draft='Signed this morning - the copy is with legal.', reason='Not sent: the mail server refused erin@northwind.example (5.1.1 no such user).')
    store._exec("UPDATE review SET DeliveryState='failed' WHERE ReviewId=?", (rid,))
    out['send-failed'] = tid
    # agents of both kinds in every state workerstate reads: a live one working or asking at its terminal, the rest with none
    from .kinds import AGENT
    for kind in AGENT:
        for st, said in (('working', ''), ('input_needed', 'Should the export keep inter-company rows, or drop them as before?'),
                         ('finished', 'Done - the export keeps inter-company rows now, and the tests pass.'),
                         ('failed', 'The run stopped: the test database was not reachable.'), ('stopped', '')):
            word = {'input_needed': 'asking', 'stopped': 'stopped-saved'}.get(st, st)
            t = f.task(title=f'{"Fix" if kind == "coding" else "Reconcile"} the export - agent {word} ({kind})', status='in_progress', kind=kind)
            sid = uuid.uuid4().hex[:12]
            if st in ('working', 'input_needed'):
                r = demo.Replay(store, t, label=kind, lines=[('$ agent', .1), ('Reading the export job.', .2), *([('', 36000)] if st == 'working' else [])])
                terminal.SESSIONS.pop(r.sid, None); r.sid, r.agent = sid, kind; terminal.SESSIONS[sid] = r
            workerstate.record(store, t, sid, 'working')
            if st != 'working': workerstate.record(store, t, sid, st, text=said)
            if st == 'stopped': store.add_transcript(t, sid, 'Reading the export job.', agent=kind, ext_id=f'conv-{sid}', brain='claude')
            out[f'{kind}-{word}'] = t
    g = f.task(title='Move payroll to Payworth', status='open', kind='task', DoneWhen='payroll runs on Payworth for every site',
               DueAt=(datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d'))
    store.set_task_checklist(g, ['Export the pay rules', 'Parallel run for one cycle'], 'owner'); out['goal-quiet'] = g
    out['for-later'] = f.task(title='Renew the PhishGuard licence', status='open', kind='task', RemindAt=(datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d 09:00:00'))
    t = f.task(title='Close the August books', status='open', kind='task')
    todo = ['Bank reconciliation', 'Accruals posted', 'Sign-off from Erin']
    store.set_task_checklist(t, todo, 'owner')
    for x in todo: store.tick_checklist_item(t, store.checklist_id(x), True, 'owner')
    out['todos-ticked'] = t
    tid, mid = asked('Trainly seats for the finance team', GAIL, 'Can we get five Trainly seats for finance?', 30)
    sent(f.review(tid, mid, status='approved', draft='Yes - five seats are booked.', final='Yes - five seats are booked.'), at(28))
    store.update_task(tid, {'Status': 'done'}, 'owner')
    f.message(task_id=tid, subject='RE: Trainly seats for the finance team', body='Could we make it seven? Two more joined.', from_name=GAIL[0],
              from_email=GAIL[1], sent_at=at(1), conversation_id='email:Trainly seats for the finance team')
    store.update_task(tid, {'Status': 'open'}, 'owner'); out['reopened'] = tid
    store.upsert_idea({'key': 'idea:spendly-limits', 'kind': 'idea', 'text': 'Spendly card limits were raised twice this month - worth a standing rule?',
                       'action': {'triage': {'intent': 'task', 'priority': 'normal'}}}, at(2))
    # a meeting in twenty minutes and one this evening: the calendar the pile reads, held fresh for the walk
    ev = lambda s, subj, who: {'start': s.strftime('%Y-%m-%dT%H:%M:00'), 'end': (s + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:00'),
                               'subject': subj, 'who': who, 'where': 'Teams'}
    now = datetime.now()
    assistant._AGENDA.update(days=7, at=time.time() + 10 ** 9, events=[ev(now + timedelta(minutes=20), 'Month-end check-in', ['Erin Blake']),
                                                                        ev(now + timedelta(hours=5), 'Vendor review with Payworth', ['Paula Vance'])])
    return out
