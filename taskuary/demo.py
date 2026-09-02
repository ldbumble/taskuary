"""The demo: the whole app, none of the world.

A product whose point is connectors cannot be shown by screenshots, and cannot be shown by a
real instance either - a public Taskuary with a mailbox behind it is somebody's mailbox on the
internet. So the demo is the real application, running on a seeded database of invented work,
with every door to the outside world nailed shut at the API layer.

NAILED SHUT, not hidden. Buttons that do nothing are a design; a deny list is a control. In
demo mode nothing sends, no connector can be created, edited or given a secret, no tool runs
against anything, no shell or CLI starts, and no channel is ever polled - and that is enforced
by one middleware over the METHOD and PATH, before any handler sees the request, so a
capability added next month is refused by default rather than discovered later.

What is left is everything worth showing: a timeline of work arriving, triage verdicts with
their reasons, drafts waiting in Review, a board with agents on it, reports, the assistant's
posts, the wall. All of it invented, all of it already in the database, and the coding
sessions REPLAY a recorded transcript so the board is alive without a CLI existing.
"""
import json
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta

from loguru import logger

FLAG = 'TASKUARY_DEMO'


def enabled() -> bool:
    return str(os.environ.get(FLAG) or '').strip().lower() in ('1', 'true', 'yes', 'on')


# ── the deny list ────────────────────────────────────────────────────────────────────────
# Written as what the demo MAY do, not as what it may not: a new endpoint is refused until
# somebody decides it is safe, which is the only way a list like this survives a year.
READ_ONLY_METHODS = {'GET', 'HEAD', 'OPTIONS'}

# The methods an allowance can be given for at all: a DELETE is never the demo, and PUT is how
# agents and connectors are configured. Both fall through to the refusal.
ALLOWED_METHODS = {'POST', 'PATCH'}

# POSTs that change nothing outside the demo's own database, and are the demo itself
ALLOWED_WRITES = (
    r'^/api/tasks$',                                   # make a task
    r'^/api/tasks/\d+$',                               # ...and change it
    r'^/api/tasks/\d+/(comments|waitroom|not-a-task|assistant/(session|messages|stream|cancel))$',
    r'^/api/messages/\d+/(file|promote|read)$',        # the triage verdicts: the whole funnel
    r'^/api/reviews?/\d+/(hold|drop|edit)$',           # ...but never /send
    r'^/api/board/notes',                              # the wall
    r'^/api/handbook',                                 # durable handbook entries and comments
    r'^/api/settings$',                                # display preferences
    r'^/api/setup/dismiss$',
    r'^/api/terminals/\d+/resize$',
)

# What is refused, and the sentence the visitor sees. Order matters: the first match wins.
REFUSALS = (
    (r'^/api/connectors', 'Connections are read-only in the demo - this is invented data, and '
                          'there is nothing real behind these cards.'),
    (r'^/api/(tools/run|agents/[^/]+/test)', 'Tools do not run in the demo: they would reach real '
                                             'systems, and there are none here.'),
    (r'^/api/(reviews?/\d+/send|tasks/\d+/handoff|board/send)', 'Nothing sends from the demo. In '
                                                                'your own Taskuary this is where you approve it and it goes.'),
    (r'^/api/(terminals|agents)(/|$)', 'Coding sessions are replays here - a real one would start a '
                                       'CLI on the machine this is running on.'),
    (r'^/api/(sync|ingest|poll|msauth|hooks)', 'Nothing is fetched or received in the demo; the '
                                               'timeline you see was seeded.'),
    (r'^/api/(doc|soul|semantic|reports?/[^/]*/(run|preview))', 'Editing the operator documents and '
                                                                'running reports is disabled here.'),
)


def refuse(method: str, path: str) -> str:
    """'' when the request may proceed, otherwise the sentence to answer with."""
    if not enabled(): return ''
    if method.upper() in READ_ONLY_METHODS: return ''
    for pattern, why in REFUSALS:
        if re.match(pattern, path): return why
    if method.upper() in ALLOWED_METHODS:
        for pattern in ALLOWED_WRITES:
            if re.match(pattern, path): return ''
    return ('That is switched off in the demo - it would reach something real. Everything you can '
            'see here is invented.')


# ── the canned brain ─────────────────────────────────────────────────────────────────────
CANNED = [
    "Here is what I would do: read the thread, pull the numbers it refers to, and come back with "
    "the two lines that decide it. In the demo I answer from a script - in your own Taskuary this "
    "is your CLI or your API key doing the work.",
    "I looked at what is on the timeline. Three things are waiting on you and one of them has been "
    "waiting since Tuesday; the rest is filed. Ask me to draft the chase and it lands in Review.",
    "That is a report, not a question - give me the schedule and I will write it every morning "
    "before you are up.",
]


def brain(seed: int = 0):
    """A model that never leaves the process. Deterministic per conversation, so the demo reads
    the same for everyone who clicks the same thing."""
    pick = random.Random(seed)
    def llm(system, user, max_tokens=None, images=None, **kw):
        text = str(user or '')
        if 'JSON' in str(system or '') or 'intent' in str(system or '').lower():
            return json.dumps({'intent': 'fyi', 'why': 'the demo files everything it is not sure about'})
        # what the person actually typed, out of a prompt that also carries the task, the
        # documents and the conversation - quoting the whole thing back reads as a bug
        asked = [l[6:].strip() for l in text.splitlines() if l.startswith('USER: ')]
        said = pick.choice(CANNED)
        if not asked: return said
        return said + f'\n\n(You asked: "{asked[-1][:160]}" - and this is a scripted answer.)'
    return llm


# ── the world, invented ──────────────────────────────────────────────────────────────────
# Northwind Facilities: a plausible mid-size operation with a plausible morning. Everything
# below is written; nobody's mail was borrowed for it.
OWNER = 'Dana Whitfield'
PEOPLE = [('Marcus Reed', 'mreed@northwind.example'), ('Priya Shah', 'pshah@northwind.example'),
          ('Tom Alvarez', 'talvarez@vendor.example'), ('Ruth Bennett', 'rbennett@northwind.example')]

SEEDS = [
    # (channel, who, subject, body, what triage did, why)
    ('email', 0, 'Month-end close is short by 4,180',
     'The GL export and the bank feed disagree for August. Can you look before Thursday?', 'task',
     'a concrete ask, addressed to you, with a date on it'),
    ('email', 1, 'New starter on Monday - laptop + accounts',
     'Sasha starts Monday in Accounts Payable. Usual kit and the AP group, please.', 'task',
     'onboarding: an ask that has to happen, and a coding agent can do most of it'),
    ('teams', 3, '', 'did the overnight import finish? the dashboard still says yesterday', 'reply',
     'a question a sentence settles - answering IS the work'),
    ('email', 2, 'Invoice 88213 - past due', 'This invoice is 46 days past due. Please advise.',
     'reply', 'a vendor chasing payment: an answer, not a project'),
    ('email', 0, 'FW: Quarterly newsletter', 'Sharing for visibility. No action needed.', 'fyi',
     'cc-for-visibility, nothing asked'),
    ('teams', 1, '', 'thanks!! that fixed it', 'fyi', 'a thank-you closes a thread, it does not open one'),
]

TRANSCRIPT = [
    ('$ claude', .4), ('', .2),
    ("I'll take the month-end difference. Reading the export first.", 1.1),
    ('→ Bash: python -m tools.gl_export --month 2026-08 --dry-run', .9),
    ('  1,284 rows, 4 with no bank reference', 1.0),
    ('→ Read: tools/gl_export.py', .7),
    ('The four are inter-company transfers - the export drops them because they have no counterparty', 1.3),
    ('reference, and the bank feed keeps them. That is the 4,180 exactly.', .9),
    ('→ Edit: tools/gl_export.py  (keep inter-company rows, flagged)', 1.2),
    ('→ Bash: pytest tests/test_gl_export.py -q', 1.0),
    ('  14 passed', .8),
    ('Fixed and tested. The August export now reconciles to the penny; I have left the four rows', 1.2),
    ('flagged rather than silently included, so the close can see them.', .9),
    ('Not pushing - that is yours to approve.', 1.6),
]


# Reports are half of what Taskuary does and the demo showed one row of JSON. These are the
# three shapes a real desk schedules - a count by place, money by counterparty, a volume over
# time - so the visitor sees the spreadsheet AND the chart the run hands back, including the
# line chart that only a dated series draws.
REPORTS = [
    ('Headcount by site, nightly', 'Headcount by site',
     [{'site': 'Lakeview', 'headcount': 112}, {'site': 'Riverside', 'headcount': 98},
      {'site': 'Fairhaven', 'headcount': 143}, {'site': 'Oak Ridge', 'headcount': 76},
      {'site': 'Millbrook', 'headcount': 121}]),
    ('AP ageing over 30 days, weekly', 'Past due by vendor',
     [{'vendor': 'Alvarez Supply', 'past_due': 18420.55}, {'vendor': 'Northline Linen', 'past_due': 9310.0},
      {'vendor': 'Kesler Medical', 'past_due': 7715.4}, {'vendor': 'BrightPath IT', 'past_due': 4180.0},
      {'vendor': 'Cardinal Food Svc', 'past_due': 2260.75}]),
    ('Helpdesk tickets by day, last 14', 'Ticket volume by day',
     [{'day': f'2026-08-{d:02d}', 'tickets': n}
      for d, n in zip(range(18, 32), (38, 41, 35, 52, 49, 22, 17, 44, 58, 61, 55, 47, 63, 71))]),
]

# What the assistant is FOR, in the assistant's own words: it has read the thread, it knows what
# is on the timeline, and it says the one thing that decides the next move. The demo used to open
# this pane empty, which showed a chat box and nothing worth chatting about.
ASSIST = [
    ('user', 'what is actually waiting on me this morning?'),
    ('assistant', """Six things came in, four are handled. What is actually yours:

- **TQ-0001 - month-end short by 4,180.** The coder has a fix and is waiting on your approval; it found the four inter-company transfers the export drops.
- **TQ-0003 - AP cutover Thursday.** Ruth needs a yes or a date. A reply is drafted in Review.
- **TQ-0005 - Sam wants the Q3 numbers.** Also drafted.

The newsletter, the thank-you and the maintenance notice are filed. Nothing there needs you."""),
    ('user', 'is Thursday safe for the AP cutover?'),
    ('assistant', """Thursday is safe if the export lands first. The reconciliation fix is written and its tests pass, so the August close can be signed Wednesday night - that was the only thing the cutover was waiting on.

One caveat worth telling Ruth: the AP importer needs pyodbc on the box before its tests mean anything (codex left that on the wall yesterday). If that is not installed by Wednesday, Thursday slips a day.

Want me to say that in the draft?"""),
]


# The days BEFORE this one. A demo that opens on a single day ends halfway down the screen and
# reads as an app with six things in it; a week of finished work is what a funnel actually looks
# like, and it is the only way to see the day rail, the scroll and the "already handled" rows -
# which are most of what Taskuary does. Everything here is closed: the open work is today's.
# (days ago, hours into that day, channel, who, subject, body, verdict, why)
HISTORY = [
    (1, 21, 'email', 0, 'Bank feed reconnected - August is complete',
     'The feed dropped on Thursday and has caught up. Nothing is missing.', 'fyi',
     'a notice that something is fixed: nothing is asked'),
    (1, 19, 'teams', 3, '', 'can you approve the Fairhaven PO before you go?', 'reply',
     'a yes-or-no a sentence settles'),
    (1, 16, 'email', 1, 'Agency invoices for October - approve by Friday',
     'Six invoices are queued for approval. The list is attached.', 'task',
     'a batch with a deadline: real work, and it is yours'),
    (1, 13, 'github', 3, '#211 census sync retries forever on a 502',
     'It backs off but never gives up, so a bad night fills the log with the same line.', 'task',
     'an issue with a reproduction: a coding agent can start on this'),
    (1, 9, 'email', 2, 'Statement of account - August',
     'Attached is your statement. No action required.', 'fyi', 'an automated statement, nothing asked'),
    (2, 20, 'email', 0, 'Payroll export mismatched two employee ids',
     'Two rows came through with the old ids after the site merge. Can the export map them?', 'task',
     'a concrete defect in a system you own'),
    (2, 17, 'whatsapp', 3, '', 'badge printer is back, ignore my last', 'fyi',
     'a retraction closes its own thread'),
    (2, 15, 'email', 1, 'RE: New starter on Monday - laptop + accounts',
     'Adding that she needs the AP group and PO approval up to 5k.', 'reply',
     'more detail on a thread already being worked'),
    (2, 11, 'email', 2, 'Price increase effective 1 October',
     'A 4% increase across the contract lines from October.', 'task',
     'a change to a contract you pay: someone has to look before October'),
    (3, 18, 'email', 0, 'Quarter close checklist - anything outstanding?',
     'Sending the checklist round. Reply with anything still open on your side.', 'reply',
     'a round-robin that wants one line back'),
    (3, 14, 'teams', 1, '', 'the Lakeview dashboard is showing yesterday again', 'task',
     'the same symptom as the overnight import: worth a look, not a chat'),
    (3, 10, 'email', 3, 'Vendor portal password reset',
     'Your password was reset as requested.', 'fyi', 'a transactional notice'),
    (4, 21, 'email', 1, 'Fairhaven wifi is down in the east wing',
     'Staff cannot chart from the east wing. The switch cupboard light is amber.', 'task',
     'an outage with people waiting on it'),
    (4, 18, 'teams', 0, '', 'thanks for turning the payroll thing round so fast', 'fyi',
     'a thank-you closes a thread'),
    (4, 15, 'email', 3, 'RE: Month-end close - the bank feed',
     'Confirming the feed is back and the balances agree as of this morning.', 'reply',
     'a confirmation on a thread you are already on'),
    (4, 12, 'github', 0, '#209 nightly import writes the same warning 4,000 times',
     'One row with a null manager, logged once per retry. The log is unreadable by morning.', 'task',
     'noise with a cause: small, and a coding agent can take it'),
    (4, 8, 'email', 2, 'Contract renewal - Cardinal Food Services',
     'Your agreement renews on 1 November. No action is needed to continue.', 'fyi',
     'an auto-renewal notice, nothing asked'),
    (5, 20, 'email', 0, 'Can we get the AP ageing weekly instead of monthly?',
     'Monthly is too late to chase anything. Weekly on Mondays would work.', 'task',
     'a change to something you run: a report, and it is yours'),
    (5, 17, 'whatsapp', 1, '', 'are you around for ten minutes about the cutover?', 'reply',
     'a request for your time: an answer, not a task'),
    (5, 14, 'email', 3, 'Access review - please confirm your team list',
     'Confirm who should keep access to the finance systems by Friday.', 'task',
     'a compliance ask with a name and a date on it'),
    (5, 11, 'teams', 2, '', 'the Riverside export ran clean last night', 'fyi',
     'a green run is not work'),
    (5, 9, 'email', 1, 'FW: Regional operations newsletter',
     'Sharing for visibility.', 'fyi', 'cc-for-visibility, nothing asked'),
]


def seed(store) -> int:
    """Build the demo's world. Idempotent: a home that already has work in it is left alone."""
    from . import artifacts, general
    from .testing import Factory
    if store.list_tasks(): return 0
    f = Factory(store)
    f.actor = 'triage'                     # not the test factory's 't': it is printed on every task
    made = 0
    for i, (channel, who, subject, body, verdict, why) in enumerate(SEEDS):
        name, email = PEOPLE[who]
        hours = 2 + i * 3
        conv = f'{channel}:{email or name}'
        # a chat line has no subject of its own, and a timeline row is titled by its subject -
        # so the row would read as the sender's name and nothing else
        subject = subject or (body[:60] + ('…' if len(body) > 60 else ''))
        source = None if channel == 'email' else ('Ops chat' if channel == 'teams' else channel)
        if verdict == 'task':
            tid = f.task(title=subject or body[:60], status='open',
                         kind='coding' if 'starter' in (subject or '') else 'general')
            mid = f.message(task_id=tid, channel=channel, subject=subject or None, body=body,
                            from_name=name, from_email=email if channel == 'email' else None,
                            sent_at=f.ago(hours=hours), status='routed', conversation_id=conv,
                            source_name=source)
            f.route(mid, tid, 'create', why)
        else:
            mid = f.message(channel=channel, subject=subject or None, body=body, from_name=name,
                            from_email=email if channel == 'email' else None, conversation_id=conv,
                            sent_at=f.ago(hours=hours), status='filed' if verdict == 'fyi' else 'routed')
            f.route(mid, None, 'file' if verdict == 'fyi' else 'reply', why)
        made += 1

    # ...and the rest of a working morning, out of the same named pictures the regression desk
    # uses (testing.Factory), so the demo shows every surface with something in it: a draft
    # waiting in Review, an agent mid-run, a scheduled report that filed, a chat, a thread.
    # every picture is given its own words: the desk's defaults ("please look", "Sam Delgado")
    # are placeholders for a test to assert on, and a demo is read by people
    f.pending_draft(title='Can you confirm the AP cutover date?', subject='AP cutover - Thursday?',
                    from_name='Ruth Bennett', from_email='rbennett@northwind.example',
                    body='Are we still moving AP over on Thursday? I need to tell the team.',
                    draft='Thursday still works - the export will be reconciled by Wednesday night.')
    f.running(title='Reconcile the August GL export', agent='coder')
    for title, chart_title, rows in REPORTS:
        pic = f.report_row(title=title)
        body = '\n'.join(json.dumps(r) for r in rows)
        store._exec('UPDATE message SET BodyText=?, Subject=? WHERE MessageId=?',
                    (body, f'{title} - {len(rows)} rows', pic.mid))
        artifacts.attach_report_output(store, pic.mid, chart_title, body)
    f.messenger(channel='whatsapp', title='the badge printer is offline again')
    f.thread(title='Onboard the new AP clerk - laptop, AP group, PO approval', n=3)
    f.filed_fyi(subject='Vendor portal maintenance window, Sunday 02:00-04:00')
    # the code lane: GitHub is a source like any other - an issue is an ask, a PR is a notice
    gh = f.task(title='northwind/importers#214 - census sync fails when a site has no manager',
                status='open', kind='coding')
    gid = f.message(task_id=gh, channel='github', subject='#214 census sync fails when a site has no manager',
                    body='Traceback on Lakeview: manager_id is null and the sync aborts the whole run '
                         'rather than skipping the row. Third night in a row.',
                    from_name='Marcus Reed', source_name='northwind/importers',
                    sent_at=f.ago(hours=5), status='routed', conversation_id='github:214')
    f.route(gid, gh, 'create', 'an issue with a traceback in it: a coding agent can start on this now')
    f.feed_only(title='northwind/importers#215 - keep inter-company rows in the GL export (open)')
    made += 9
    # the desk's pictures carry placeholder words for a test to assert on ("please look"); a
    # demo is read by people, so the few that show get real ones
    for mid, subject in zip([m['MessageId'] for m in store.scan_messages(40)
                             if (m.get('Subject') or '') == 'please look'],
                            ('Reconcile the August GL export', 'Can you resend the Q3 numbers?',
                             'Onboard the new AP clerk - laptop, AP group, PO approval')):
        store._exec('UPDATE message SET Subject=? WHERE MessageId=?', (subject, mid))
    for mid, (who, mail) in zip([m['MessageId'] for m in store.scan_messages(40) if not (m.get('FromEmail') or '')
                                 and not store.get_message(m['MessageId']).get('FromName')],
                                PEOPLE * 4):
        store._exec('UPDATE message SET FromName=?, FromEmail=? WHERE MessageId=?', (who, mail, mid))

    # ...and spread across the day: the pictures all stamp themselves 'now', so a demo opened
    # at 8pm showed a morning's work arriving in the same minute
    for i, m in enumerate(store.scan_messages(60)):
        if str(m.get('SentAt') or '')[:10] != datetime.now().strftime('%Y-%m-%d'): continue
        store._exec('UPDATE message SET SentAt=? WHERE MessageId=?',
                    ((datetime.now() - timedelta(minutes=37 * i + 11)).strftime('%Y-%m-%d %H:%M:%S'), m['MessageId']))

    # the week behind today: finished, so it reads as history rather than a backlog
    for days, hour, channel, who, subject, body, verdict, why in HISTORY:
        name, email = PEOPLE[who]
        when = f.ago(hours=days * 24 + (22 - hour))
        subject = subject or (body[:60] + ('…' if len(body) > 60 else ''))
        source = ('Ops chat' if channel == 'teams' else 'northwind/importers' if channel == 'github'
                  else f'{name.split()[0]} (whatsapp)' if channel == 'whatsapp' else None)
        tid = f.task(title=subject, status='done', kind='coding' if channel == 'github' else 'general',
                     ) if verdict == 'task' else None
        mid = f.message(task_id=tid, channel=channel, subject=subject, body=body, from_name=name,
                        from_email=email if channel == 'email' else None, sent_at=when,
                        status='filed' if verdict == 'fyi' else 'routed',
                        conversation_id=f'{channel}:{email or name}:{days}', source_name=source)
        f.route(mid, tid, 'create' if verdict == 'task' else 'file' if verdict == 'fyi' else 'reply', why)
        made += 1

    store.save_doc('soul', SOUL, 'demo')
    store.add_comment(next(t['TaskId'] for t in store.list_tasks()), 'assistant', 'assistant_agent',
                      'The month-end difference is the four inter-company transfers the export drops. '
                      'I can fix the export, or file it for the close to handle - say which.')
    chat = f.task(title='This morning, and whether Thursday holds', status='open', kind='general')
    for role, body in ASSIST:
        store.add_comment(chat, 'Dana' if role == 'user' else 'assistant',
                          general.USER_TYPE if role == 'user' else general.ASSISTANT_TYPE, body)
    for kind, agent, body in (
        ('working', 'coder', 'on the month-end export - tools/gl_export.py is mine for the next hour'),
        ('note', 'codex', 'the bank feed keeps inter-company transfers; the export drops them. That is the 4,180'),
        ('ready', 'coder', 'export fixed, 14 tests green - safe to build on'),
        ('summary', 'the wall', '2026-08-30 - the AP importer needs pyodbc installed before its tests mean anything; '
                                'the census sync is behind a VPN and will not run from a laptop'),
    ):
        store.add_note({'TaskId': None, 'Agent': agent, 'Cwd': '', 'Kind': kind, 'Body': body, 'Files': ''})
    # ...and Social: what those sessions worked out that is still true next month, voted on by the
    # agents that came after - a shelf with something on it, so the tab shows how the votes work
    from . import handbook
    for topic, kind, title, body, votes in (
        ('importers', 'gotcha', 'The AP importer needs pyodbc on the box before its tests mean anything',
         'Without the driver every test passes vacuously - the SQL Server fixtures skip. pip install pyodbc, then run the suite.',
         (('coder', 1), ('codex', 1), ('gemini', 1))),
        ('gl-export', 'gotcha', 'The bank feed keeps inter-company transfers; the GL export drops them',
         'That is the recurring month-end gap. Reconcile against the feed with the transfers flagged, never silently included.',
         (('codex', 1), ('coder', 1))),
        ('census', 'system', 'The census sync runs behind the office VPN and will not run from a laptop',
         'It reads the old view (census_v1), not the new dashboard tables. Run it from the ops box or over the VPN.',
         (('coder', 1),)),
        ('payroll', 'decision', 'Finance closes on the first Wednesday, not the first business day',
         'Decided with the CFO in July so the bank feed has settled. Anything asking for numbers before then gets the previous month.',
         ()),
    ):
        lid = handbook.post(store, title, body, topic, kind, 'coder')['LoreId']
        for who, d in votes: handbook.vote(store, lid, d, who)
    logger.info(f'demo: seeded {made} items of invented work')
    return made


SOUL = """# SOUL.md - the operator's document

You work for **Dana Whitfield**, who runs IT and finance systems for Northwind Facilities.
You are the funnel between everything inbound and Dana's attention.
**Nothing sends or ships without Dana's approval.**

## What counts as a task
- A concrete request to DO something: fix, change, build, investigate, produce.
- A question a sentence settles is a reply, not a task.
- Cc'd-for-visibility threads, newsletters and thank-yous are fyi.

## How we respond
- Plain, brief, warm-professional. Sign as Dana. No filler.

## Escalate (a human decides) when
- Money, vendors, contracts, credentials or an external commitment is involved.

## Systems and repositories
- The GL export, the census database, the AP importers.

## People
- The CFO outranks everyone; the helpdesk reports to Dana; vendors get a polite no by default.

<!-- this is a demo: Dana, Northwind and everyone in it are invented -->
"""


class Replay:
    """A coding session that never was: a recorded transcript, typed out at reading speed.

    It wears the same live-session surface as terminal.Term - the Board, the Wall and the task
    page ask a session for its scrollback, whether it is alive and what it is doing, and this
    answers all three - so the demo shows an agent working without a CLI, a repository or a
    machine to run either on.
    """
    mode, argv, cwd, agent, cli = 'demo', [], '', 'coder', 'demo'

    def __init__(self, store, task_id: int, label: str = 'coder', lines=None):
        import uuid
        self.sid = uuid.uuid4().hex[:12]
        self.store, self.task_id, self.label = store, task_id, label
        self.lines = list(lines or TRANSCRIPT)
        self.started = datetime.now().isoformat(sep=' ', timespec='seconds')
        self.buf, self.subs, self.taps = [], [], []
        self.alive, self.busy, self.ended = True, True, None
        self.rows, self.cols = 32, 110
        self.last = time.time()
        threading.Thread(target=self._play, daemon=True).start()

    def _play(self):
        for text, pause in self.lines:
            if not self.alive: return
            time.sleep(pause)
            self._emit(f'{text}\r\n')
        self.busy = False
        # the Board and the task card show a TAIL of this as text, not as a terminal - the dim
        # escape rode along with it and printed as a literal [2m on every card
        self._emit('\r\nthe agent is waiting for you - this is a demo, so it waits forever\r\n')

    def _emit(self, text):
        self.buf.append(text)
        self.last = time.time()
        for loop, q in list(self.subs):
            try: loop.call_soon_threadsafe(q.put_nowait, text)
            except RuntimeError: pass
        for fn in list(self.taps):
            try: fn(text)
            except Exception: pass

    def scrollback(self): return ''.join(self.buf)
    def subscribe(self, loop, q): self.subs.append((loop, q))
    def unsubscribe(self, q): self.subs = [(l, i) for l, i in self.subs if i is not q]
    def tap(self, fn): self.taps.append(fn)
    def untap(self, fn): self.taps = [f for f in self.taps if f is not fn]
    def write(self, data): pass                      # a replay does not take dictation
    def resize(self, rows, cols): self.rows, self.cols = rows, cols
    def idle(self): return time.time() - self.last
    def phase(self): return 'working' if self.busy else 'parked'
    def waiting(self): return not self.busy
    def files(self): return ['tools/gl_export.py'] if not self.busy else []
    def tail(self, n=3): return [l.strip() for l in ''.join(self.buf).splitlines() if l.strip()][-n:]
    def close(self):
        self.alive, self.busy, self.ended = False, False, time.time()
    def info(self, tail=0):
        return {'sid': self.sid, 'label': self.label, 'cwd': '~/northwind/importers', 'taskId': self.task_id,
                'agent': self.agent, 'cli': self.cli, 'mode': self.mode, 'alive': self.alive,
                'started': self.started, 'idle': self.idle(), 'phase': self.phase(),
                'waiting': self.waiting(), 'cmd': 'claude (demo replay)', 'files': self.files(),
                'browser': {'open': False, 'url': '', 'port': 0}, 'work': None,
                **({'tail': self.tail(tail)} if tail else {})}


def start_sessions(store) -> int:
    """Put a replaying agent on the demo's coding tasks, so the Board is alive on arrival."""
    from . import terminal
    n = 0
    for t in store.list_tasks():
        if t.get('Kind') != 'coding' or t.get('Status') in ('done', 'dropped'): continue
        if any(getattr(x, 'task_id', None) == t['TaskId'] for x in terminal.SESSIONS.values()): continue
        r = Replay(store, t['TaskId'])
        terminal.SESSIONS[r.sid] = r
        n += 1
    return n
