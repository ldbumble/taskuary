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
their reasons, drafts waiting on the task, a board with agents on it, reports, the assistant's
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
    r'^/api/prompt-image$',                            # a picture for a prompt: saved in the demo's own home
    r'^/api/messages/\d+/(file|promote|read)$',        # the triage verdicts: the whole funnel
    r'^/api/reviews?/\d+/(hold|drop|edit)$',           # ...but never /send
    r'^/api/board/notes',                              # the wall
    r'^/api/(hub|handbook)',                           # durable Hub posts and compatibility route
    r'^/api/settings$',                                # display preferences
    # the checklist's "leave me alone", and the scripted walk - a tour of the app that touches
    # nothing real, which is what a visitor is here for. Its writes are two settings in the demo's
    # own database, which is what everything else on this list has in common.
    # /api/setup/adopt-brain is DELIBERATELY not here and must not be added: it picks the triage
    # brain, and a visitor changing which AI reads the mail is not a tour of the app. The demo has
    # no CLI to test, so nothing on the visitor's screen can even reach it.
    r'^/api/setup/(dismiss|seen|walk(/reset)?)$',
    r'^/api/terminals/\d+/resize$',
    # the Assistant page: the pipe's own memory, the concierge's turns and the greeting when the visitor sits down
    # (arrive) - the demo's database, the demo's canned brain, nothing real behind either (funnel.py, concierge.py, welcome.py)
    r'^/api/(funnel/settle|concierge/(open|next|say|act|stream|ai|setup|arrive)|assistant/dock(/new)?)$',
    # THE CARD'S OWN BUTTONS (U8, 2026-10-17): Mark done, Remind me and a draft were all refused, with "Report this bug" under
    # them - the demo could not show its own walk. A proposal is a row in the demo's database; running one is gated by its
    # KIND below (LOCAL_OPS), since the path cannot tell Mark done from Send. Remind me and a draft write nothing outside either.
    r'^/api/concierge/propose$',
    # ...and the task view's and cards' own road (taskOps.runOperation) proposes here first: refused, Mark done never reached
    # the kind check below (error sweep, 2026-10-18). Proposing and editing a proposal write only its row.
    r'^/api/operations(/[^/]+)?$',
    r'^/api/operations/[^/]+/execute$',
    r'^/api/tasks/\d+/remind$',
    r'^/api/messages/\d+/reply$',                      # puts a draft on the table - only approving it sends
    r'^/api/reviews/\d+/draft$',
)

# What a confirmed proposal may run here: each writes the demo's own database and nothing else. Start (dispatch.prepare,
# agent.*) would start a program on the host, Send (review.approve, task.clarify, task.chase) would mail someone, and
# reports, settings and connections reach systems - those stay refused, as before.
LOCAL_OPS = {'task.complete', 'task.reopen', 'task.defer', 'item.settle', 'message.file', 'task.not_a_task', 'message.reply',
             'preference.exclude_sender', 'preference.sender_rule', 'task.let_go', 'task.elsewhere', 'idea.act', 'memory.remember',
             'routing.remember', 'task.split', 'task.update', 'task.check', 'task.checklist', 'task.watch', 'task.comment', 'task.merge',
             'review.reject', 'hub.publish', 'pipe.clear', 'script.start'}

# The sentences the visitor sees, plain and said as the demo, not as a fault: the page posts them as an ordinary line.
SENDS = 'This is the demo - nothing is sent. In your own Taskuary this is where you approve it and it goes.'
STARTS = 'This is the demo - the agents here are recordings, so nothing new starts.'
OFF = 'This is the demo - that would reach something real, so it is switched off. Everything here is invented.'

# What is refused, and the sentence the visitor sees. Order matters: the first match wins.
REFUSALS = (
    (r'^/api/connectors', 'This is the demo - these connections are invented, and there is nothing real behind them to change.'),
    (r'^/api/(tools/run|agents/[^/]+/test)', 'This is the demo - nothing runs, because there are no real systems here to run against.'),
    (r'^/api/(reviews?/\d+/(send|decide)|tasks/\d+/(handoff|clarify)|board/send|messages/\d+/send)', SENDS),
    (r'^/api/(terminals|agents)(/|$)|^/api/tasks/\d+/(dispatch|code|continue|continue-session|continue-work|resume)$'
     r'|^/api/messages/\d+/(dispatch|chat)$', STARTS),
    (r'^/api/(sync|ingest|poll|msauth|hooks)', 'This is the demo - no mail is fetched; what you see was written in advance.'),
    (r'^/api/(doc|soul|semantic|reports?/[^/]*/(run|preview))', 'This is the demo - editing your documents and running reports are switched off.'),
)


def _store():
    """The running app's store, without importing the server (an import runs its startup): the demo is always the server."""
    import sys
    return getattr(sys.modules.get(f'{__package__}.server'), 'store', None)


def refuse_op(op) -> str:
    """'' when a confirmed proposal only writes the demo's database, else the sentence. Making a task of a message is local;
    handing it to an agent is a start."""
    if not op: return ''                                    # no such proposal: the handler's own 404 says so
    kind, p = op.get('kind'), op.get('params') or {}
    if kind in LOCAL_OPS or (kind == 'task.create_from_message' and str(p.get('kind') or 'task').lower() == 'task'): return ''
    if kind in ('review.approve', 'task.clarify', 'task.chase', 'task.handoff'): return SENDS
    if kind in ('dispatch.prepare', 'agent.continue', 'agent.answer', 'agent.stop', 'task.create_from_message', 'task.create_from_text'): return STARTS
    return OFF


def refuse(method: str, path: str, store=None) -> str:
    """'' when the request may proceed, otherwise the sentence to answer with."""
    if not enabled(): return ''
    if method.upper() in READ_ONLY_METHODS: return ''
    for pattern, why in REFUSALS:
        if re.match(pattern, path): return why
    if method.upper() in ALLOWED_METHODS:
        for pattern in ALLOWED_WRITES:
            if not re.match(pattern, path): continue
            if m := re.match(r'^/api/operations/([^/]+)/execute$', path):
                from . import operations
                st = store if store is not None else _store()
                return refuse_op(operations.get(st, m.group(1))) if st is not None else OFF   # no store to read the kind: shut
            return ''
    return OFF


# ── the canned brain ─────────────────────────────────────────────────────────────────────
CANNED = [
    "Here is what I would do: read the thread, pull the numbers it refers to, and come back with "
    "the two lines that decide it. In the demo I answer from a script - in your own Taskuary this "
    "is your own AI doing the work.",
    "I looked at your list. {list} Ask me to draft a reply and it lands on the task.",
    "That is a report, not a question - give me the schedule and I will write it every morning "
    "before you are up.",
]

def _n(k: int, one: str, many: str) -> str: return f"{k} {one if k == 1 else many}"

def _list_line(store) -> str:
    """The count the rail shows, read from the rail: a line that said "Three things are waiting" beside a rail of nine
    read as the assistant not looking (B23, 2026-10-17)."""
    from . import funnel
    try: items = funnel.pile(store)['items'] if store is not None else None
    except Exception: items = None
    if items is None: return 'Everything on it is in front of you on the left.'
    if not items: return 'Nothing is waiting on you right now.'
    yours = sum(1 for i in items if funnel.waits_on_you(i))
    return (f"{_n(len(items), 'thing is', 'things are')} on it"
            + (f", and {_n(yours, 'is', 'are')} waiting on your answer or your yes." if yours else '.'))


# THE ADVISOR, SCRIPTED (B17, 2026-10-17): its prompt says JSON, so it got triage's {"intent": "fyi"} and dropped every answer as
# "nothing to say" - the demo, where newcomers first meet it, never showed a suggestion. It names the first offered verb that
# someone waiting makes right, with a plain line - and like the real one says nothing on a newsletter: "Make a task" over an
# fyi is the wrong suggestion that is worse than none.
_VERBS = re.compile(r'^VERBS OFFERED: (.*)$', re.M)
ADVICE = {'answer_agent': 'The agent is waiting on your answer.', 'approve': 'The draft is ready - read it, then send it.',
          'reply': 'Someone is waiting on an answer from you.', 'continue': 'The agent stopped partway - pick it up where it left off.'}

def _advice(text: str) -> str:
    offered = dict(re.findall(r'([a-z_]+) \(([^)]*)\)', _VERBS.search(text).group(1)))
    verb = next((v for v in ADVICE if v in offered), None)
    return json.dumps({'verb': verb, 'line': ADVICE[verb] if verb else '', 'evidence': []})


def brain(seed: int = 0, store=None):
    """A model that never leaves the process. Deterministic per conversation, so the demo reads
    the same for everyone who clicks the same thing."""
    pick = random.Random(seed)
    def llm(system, user, max_tokens=None, images=None, **kw):
        text = str(user or '')
        if _VERBS.search(text): return _advice(text)
        if 'JSON' in str(system or '') or 'intent' in str(system or '').lower():
            return json.dumps({'intent': 'fyi', 'why': 'the demo files everything it is not sure about'})
        # what the person actually typed, out of a prompt that also carries the task, the
        # documents and the conversation - quoting the whole thing back reads as a bug
        asked = [l[6:].strip() for l in text.splitlines() if l.startswith('USER: ')]
        said = pick.choice(CANNED)
        if '{list}' in said: said = said.format(list=_list_line(store if store is not None else _store()))
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
     'onboarding: an ask that has to happen, with a day on it'),
    ('teams', 3, '', 'did the overnight import finish? the dashboard still says yesterday', 'reply',
     'a question a sentence settles - answering IS the work'),
    ('email', 2, 'Invoice 88213 - past due', 'This invoice is 46 days past due. Please advise.',
     'reply', 'a vendor chasing payment: an answer, not a project'),
    ('email', 0, 'FW: Quarterly newsletter', 'Sharing for visibility. No action needed.', 'fyi',
     'cc-for-visibility, nothing asked'),
    ('teams', 1, '', 'thanks!! that fixed it', 'fyi', 'a thank-you closes a thread, it does not open one'),
]

# what the responder drafted for each reply-only ask above - the owner's yes is all they wait for
DRAFTS = {
    'did the overnight import finish? the dashboard still says yesterday':
        'It finished at 04:10 - the dashboard catches up on its 7:00 refresh.',
    'Invoice 88213 - past due': "Thanks Tom - it is approved and goes out in Friday's payment run.",
}

# EACH AGENT ITS OWN WORK (B23, 2026-10-17): every agent task replayed the month-end transcript, so the census issue's
# terminal talked about the GL export. The coding issue replays its own fix; the GL reconciliation is a general agent's
# task and reads as its conversation (GL_CHAT) - an accountant's task opened as a terminal.
TRANSCRIPT = [
    ('$ claude', .4), ('', .2),
    ("I'll take #214. Reading the census sync first.", 1.1),
    ('→ Read: importers/census_sync.py', .8),
    ('One site with no manager stops the whole run - it should skip that row and say so.', 1.3),
    ('→ Bash: pytest tests/test_census_sync.py -q', 1.0),
    ('  1 failed: test_site_without_manager', .8),
    ('→ Edit: importers/census_sync.py  (skip a row with no manager, log it once)', 1.2),
    ('→ Bash: pytest tests/test_census_sync.py -q', 1.0),
    ('  9 passed', .8),
    ('Fixed and tested. Lakeview syncs again; the row with no manager is skipped and named once', 1.2),
    ('in the log, so the morning report still adds up.', .9),
    ('Not pushing - that is yours to approve.', 1.6),
]
TRANSCRIPTS = [TRANSCRIPT]

def _brief_replay(title: str) -> list:
    """A coding task the seed did not write a recording for still replays its own words, never another task's."""
    return [('$ claude', .4), ('', .2), (f'Reading the ask: {title}', 1.1), ('Nothing changed yet - waiting for you to say go.', 1.2)]

# the GL reconciliation, as a general agent works it: in plain words, on the task's own conversation
GL_CHAT = [
    ('user', 'Reconcile the August GL export against the bank feed, and flag anything that does not match - the close is Thursday.'),
    ('assistant', 'Reading the August export and the bank feed side by side. The export has 1,284 rows; 4 of them have no '
                  'matching line in the bank feed.'),
    ('assistant', 'Those four are transfers between our own companies. The export leaves them out because there is no outside '
                  'party on them, and the bank feed keeps them. Together they come to 4,180 - the whole difference.'),
    ('assistant', 'I have listed the four on the task, flagged rather than folded in, so the close can see them. Want me to draft a '
                  'note to Marcus saying the 4,180 is explained?'),
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

- **{gl} - month-end short by 4,180.** An agent is on it; it found the four transfers between our own companies that the export leaves out.
- **{cutover} - AP cutover Thursday.** Ruth needs a yes or a date. A reply is drafted on the task.
- **{q3} - Sam wants the Q3 numbers.** Also drafted.

The newsletter, the thank-you and the maintenance notice are filed. Nothing there needs you."""),
    ('user', 'is Thursday safe for the AP cutover?'),
    ('assistant', """Thursday is safe if the export lands first. The reconciliation is done - the four rows are explained and flagged - so the August close can be signed Wednesday night. That was the only thing the cutover was waiting on.

One caveat worth telling Ruth: the AP importer still has a setup step to do on the server (an agent left that on the wall yesterday). If that is not done by Wednesday, Thursday slips a day.

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
    from .store import task_ref
    from .testing import Factory
    if store.list_tasks(): return 0
    f = Factory(store)
    f.actor = 'triage'                     # not the test factory's 't': it is printed on every task
    made = 0
    refs = {}
    for i, (channel, who, subject, body, verdict, why) in enumerate(SEEDS):
        name, email = PEOPLE[who]
        hours = 2 + i * 3
        conv = f'{channel}:{email or name}'
        # a chat line has no subject of its own, and a timeline row is titled by its subject -
        # so the row would read as the sender's name and nothing else
        subject = subject or (body[:60] + ('…' if len(body) > 60 else ''))
        source = None if channel == 'email' else ('Ops chat' if channel == 'teams' else channel)
        said = dict(channel=channel, subject=subject, body=body, from_name=name,
                    from_email=email if channel == 'email' else None, sent_at=f.ago(hours=hours),
                    conversation_id=conv, source_name=source)
        if verdict == 'task':
            tid = f.task(title=subject, status='open', kind='general', source=channel)
            mid = f.message(task_id=tid, status='routed', **said)
            f.route(mid, tid, 'create', why)
        elif verdict == 'reply':
            # a reply-only ask is a reply waiting for a yes, as triage makes it - filed with no task it
            # read as an fyi: "Invoice 46 days past due. Please advise." with nothing to do about it
            tid = f.task(title=subject, status='open', kind='reply', source=channel)
            mid = f.message(task_id=tid, status='routed', **said)
            f.route(mid, tid, 'create', why)
            f.review(tid, mid, draft=DRAFTS.get(body) or DRAFTS[subject])
        else:
            mid = f.message(status='filed', **said)
            f.route(mid, None, 'file', why)
        refs[subject] = tid if verdict != 'fyi' else None
        made += 1

    # ...and the rest of a working morning: a draft waiting on the task, an agent mid-run, reports that
    # filed, a chat, a thread. Every item is written out with its own sender and words - the regression
    # desk's pictures (testing.Factory) carry placeholder bodies ("x", "and one more thing 1") and an
    # earlier pass renamed their subjects in scan order, which put a task's title over another's mail.
    ruth, marcus, priya = PEOPLE[3], PEOPLE[0], PEOPLE[1]
    refs['cutover'] = f.pending_draft(
        title='Can you confirm the AP cutover date?', subject='AP cutover - Thursday?',
        from_name=ruth[0], from_email=ruth[1], sent_at=f.ago(hours=7),
        body='Are we still moving AP over on Thursday? I need to tell the team.',
        draft='Thursday still works - the export will be reconciled by Wednesday night.').tid
    # the agent mid-run: Marcus's month-end difference, handed to a general agent - accounting work, not code
    gl = f.task(title='Reconcile the August GL export', status='in_progress', kind='general')
    gm = f.message(task_id=gl, subject='Reconcile the August GL export', from_name=marcus[0], from_email=marcus[1],
                   body='Can the export be reconciled against the bank feed? Flag anything that does not match - '
                        'the close is Thursday.', sent_at=f.ago(hours=6), conversation_id='email:gl-export')
    f.route(gm, gl, 'create', 'a reconciliation with a clear check: an agent can work it through')
    for role, body in GL_CHAT:
        store.add_comment(gl, OWNER.split()[0] if role == 'user' else 'assistant',
                          general.USER_TYPE if role == 'user' else general.ASSISTANT_TYPE, body)
    refs['gl'] = gl
    # ONE GOAL (spec 2026-10-12): an outcome with a date, its steps tasks of their own - one done by a coding agent, one waiting
    # on a person past its day, the rest not started. Dana's census migration.
    g = f.task(title='Migrate the census export off the old portal', status='open', kind='task',
               DoneWhen='the nightly census lands in the new ledger for all three sites, and the old portal\'s export is switched off',
               DueAt=(datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d'))
    store.set_task_checklist(g, ['Inventory the fields the old export carries', 'Map them onto the ledger schema',
                                 'Ray: schema sign-off', 'Export job on the new schema', 'Tell the sites the cutover date'], 'owner')
    done = f.task(title='Inventory the fields the old export carries', status='done', kind='general', ParentId=g)
    store.link_step(g, store.checklist_id('Inventory the fields the old export carries'), done, 'owner')
    store.tick_checklist_item(g, store.checklist_id('Inventory the fields the old export carries'), True, 'owner')   # seeded closed: tick it as a close would
    waiting = f.task(title='Ray: schema sign-off', status='waiting', kind='task', ParentId=g, Assignee='person:ray@northwind.example',
                     DueAt=(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'))
    store.link_step(g, store.checklist_id('Ray: schema sign-off'), waiting, 'owner')
    refs['goal'] = g
    for title, chart_title, rows in REPORTS:
        pic = f.report_row(title=title)
        body = '\n'.join(json.dumps(r) for r in rows)
        store._exec('UPDATE message SET BodyText=?, Subject=? WHERE MessageId=?',
                    (body, f'{title} - {len(rows)} rows', pic.mid))
        artifacts.attach_report_output(store, pic.mid, chart_title, body)
    # a chat: Sam on WhatsApp, and the answer drafted
    q3 = f.task(title='Can you resend the Q3 numbers?', kind='reply', source='whatsapp')
    qm = f.message(task_id=q3, channel='whatsapp', subject='Can you resend the Q3 numbers?', from_name='Sam Delgado',
                   from_email='@samdelgado', source_name='Sam (whatsapp)', conversation_id='whatsapp:88214',
                   body='Hey - can you resend the Q3 numbers? I lost the file.', sent_at=f.ago(hours=3))
    f.route(qm, q3, 'create', 'a quick ask a reply settles')
    f.review(q3, qm, draft='Sending the Q3 pack now - it is the same file as the board deck.')
    refs['q3'] = q3
    # a thread: three mails on one ask, grouped on one task
    audit = f.task(title='Year-end audit - the first document requests', kind='general')
    for n, (subject, body, hours) in enumerate((
            ('Year-end audit - the first document requests',
             'The auditors sent their first list: August bank reconciliations and the AP ageing for Q3.', 5),
            ('RE: Year-end audit - the first document requests', 'They have added the fixed asset register.', 4),
            ('RE: Year-end audit - the first document requests', 'And they would like all of it by the 15th.', 2))):
        m = f.message(task_id=audit, subject=subject, body=body, from_name=priya[0], from_email=priya[1],
                      sent_at=f.ago(hours=hours), conversation_id='email:year-end-audit')
        f.route(m, audit, 'create' if n == 0 else 'attach', 'a request with a list and a date' if n == 0 else 'same conversation thread')
    f.filed_fyi(subject='Vendor portal maintenance window, Sunday 02:00-04:00')
    # the code lane: GitHub is a source like any other - an issue is an ask, a PR is a notice
    gh = f.task(title='northwind/importers#214 - census sync fails when a site has no manager',
                status='open', kind='coding', source='github')
    gid = f.message(task_id=gh, channel='github', subject='#214 census sync fails when a site has no manager',
                    body='Traceback on Lakeview: manager_id is null and the sync aborts the whole run '
                         'rather than skipping the row. Third night in a row.',
                    from_name='Marcus Reed', source_name='northwind/importers',
                    sent_at=f.ago(hours=5), status='routed', conversation_id='github:214')
    f.route(gid, gh, 'create', 'an issue with a traceback in it: a coding agent can start on this now')
    f.feed_only(title='northwind/importers#215 - keep inter-company rows in the GL export (open)')
    made += 9

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
        # a reply that asked something was answered on a task of its own, as triage makes it: seeded routed with no task,
        # it landed under the fyi as "Nothing to decide" over "can you approve the Fairhaven PO?" (B23, 2026-10-17)
        tid = (f.task(title=subject, status='done', kind='coding' if channel == 'github' else 'reply' if verdict == 'reply' else 'general')
               if verdict in ('task', 'reply') else None)
        mid = f.message(task_id=tid, channel=channel, subject=subject, body=body, from_name=name,
                        from_email=email if channel == 'email' else None, sent_at=when,
                        status='filed' if verdict == 'fyi' else 'routed',
                        conversation_id=f'{channel}:{email or name}:{days}', source_name=source)
        f.route(mid, tid, 'file' if verdict == 'fyi' else 'create', why)
        made += 1

    store.save_doc('soul', SOUL, 'demo')
    store.save_doc('job', JOB, 'demo')
    store.add_comment(next(t['TaskId'] for t in store.list_tasks()), 'assistant', 'assistant_agent',
                      'The month-end difference is the four inter-company transfers the export drops. '
                      'I can fix the export, or file it for the close to handle - say which.')
    # the owner's own conversation with the task assistant, finished this morning: on the Tasks tab to read
    # back, not an empty card in the walk wearing "triage asked you" (it was created as triage, and open)
    chat = store.create_task({'Title': 'This morning, and whether Thursday holds', 'Status': 'done', 'Kind': 'general',
                              'Source': 'assistant', 'SourceRef': 'assistant:chat'}, 'owner')
    names = {'gl': task_ref(refs['gl']), 'cutover': task_ref(refs['cutover']), 'q3': task_ref(refs['q3'])}
    for role, body in ASSIST:
        store.add_comment(chat, 'Dana' if role == 'user' else 'assistant',
                          general.USER_TYPE if role == 'user' else general.ASSISTANT_TYPE, body.format(**names))
    for kind, agent, body in (
        ('working', 'coding', 'on the census sync (#214) - importers/census_sync.py is mine for the next hour'),
        ('note', 'codex', 'the bank feed keeps inter-company transfers; the export drops them. That is the 4,180'),
        ('ready', 'coding', 'census sync skips a site with no manager, 9 tests green - safe to build on'),
        ('summary', 'the wall', '2026-08-30 - the AP importer needs pyodbc installed before its tests mean anything; '
                                'the census sync is behind a VPN and will not run from a laptop'),
    ):
        store.add_note({'TaskId': None, 'Agent': agent, 'Cwd': '', 'Kind': kind, 'Body': body, 'Files': ''})
    # ...and the Hub: hard-earned discoveries and ideas, voted on by the
    # agents that came after - a shelf with something on it, so the tab shows how the votes work
    from . import hub
    for topic, kind, title, body, votes in (
        ('customer-launch', 'new_idea', 'Give every customer launch a reversible dry-run',
         'A rehearsal exposes ownership and data gaps before a date is promised. Keep the rollback path visible and ask operations to sign off.',
         (('assistant', 1), ('coding', 1))),
        ('importers', 'technical_solve', 'Bound retries by elapsed time, not only attempt count',
         'Backoff intervals vary by provider, so attempt counts created wildly different outages. Use an elapsed-time budget and preserve the final response for diagnosis.',
         (('coding', 1), ('codex', 1))),
        ('importers', 'gotcha', 'The AP importer needs pyodbc on the box before its tests mean anything',
         'Without the driver every test passes vacuously - the SQL Server fixtures skip. pip install pyodbc, then run the suite.',
         (('coding', 1), ('codex', 1), ('gemini', 1))),
        ('gl-export', 'gotcha', 'The bank feed keeps inter-company transfers; the GL export drops them',
         'That is the recurring month-end gap. Reconcile against the feed with the transfers flagged, never silently included.',
         (('codex', 1), ('coding', 1))),
        ('census', 'system', 'The census sync runs behind the office VPN and will not run from a laptop',
         'It reads the old view (census_v1), not the new dashboard tables. Run it from the ops box or over the VPN.',
         (('coding', 1),)),
        ('payroll', 'decision', 'Finance closes on the first Wednesday, not the first business day',
         'Decided with the CFO in July so the bank feed has settled. Anything asking for numbers before then gets the previous month.',
         ()),
    ):
        author = 'assistant' if kind == 'new_idea' else 'coding'
        lid = hub.post(store, title, body, topic, kind, author)['LoreId']
        for who, d in votes: hub.vote(store, lid, d, who)
        if kind == 'new_idea':
            store.lore_comment(lid, 'This would also give sales a concrete readiness signal before confirming a date.', 'coding')
            store.lore_comment(lid, 'Try it on the next two launches and compare escaped issues.', 'owner')
        elif kind == 'technical_solve':
            store.lore_comment(lid, 'The same elapsed-time budget should apply to report polling.', 'assistant')
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

# What the job IS, as "Generate from history" would have read it out of three months of Dana's mail - the
# shape every demo arrival is weighed against. Invented, like everyone in it.
JOB = """# JOB.md - what Dana's job is

## The job
- Keep the finance and census systems of Northwind Facilities running and reconciled: the GL export, the
  AP importers, the census database, and the helpdesk queue that sits in front of them.

## Learned from your mail history
<!-- fromhistory:start -->
_generated 2026-09-30 09:12 — 412 inbound + 188 sent from the last 90 days across 1 mailbox(es), read over Graph_

### What my job is
- I own the systems the month-end close depends on, and I'm the person the business writes to when a
  number does not match.

### What I am responsible for
- Month-end differences between the GL export and the ledger, every month.
- AP importer failures and vendor file formats, weekly.
- Census corrections and access to the census database, weekly - answered within the day.
- Helpdesk escalations about finance tools, when the helpdesk cannot settle them.

### Who I work with
- The CFO's office writes most - questions about totals and the timing of the close.
- The helpdesk hands up what it cannot settle; I answer the same day.
- Vendors write about imports and renewals; renewals go to the CFO, imports I settle.

### Recurring cadences
- Month-end close, the first three working days of the month: the difference thread opens every time.
- Vendor statement imports, weekly, Monday or Tuesday.
- Quarterly access review of the census database.

### Decisions I make, and what I hand up
- I decide fixes, imports, access and priorities in the queue.
- Money, contracts and renewals go to the CFO; credentials and policy to IT security.

### What I protect
- The close finishing on time with a number nobody has to explain twice.
- Census data being right before anyone downstream reads it.
<!-- fromhistory:end -->

<!-- this is a demo: Dana, Northwind and everyone in it are invented -->
"""


class Replay:
    """A coding session that never was: a recorded transcript, typed out at reading speed.

    It wears the same live-session surface as terminal.Term - the Board, the Wall and the task
    page ask a session for its scrollback, whether it is alive and what it is doing, and this
    answers all three - so the demo shows an agent working without a CLI, a repository or a
    machine to run either on.
    """
    mode, argv, cwd, agent, cli = 'demo', [], '', 'coding', 'demo'

    def __init__(self, store, task_id: int, label: str = 'coding', lines=None):
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
    def quiet_for(self, secs):
        # Terminal attachment suppresses resize repaint activity. A recording's resize
        # emits nothing, so there is no synthetic activity to suppress or idle clock to reset.
        pass
    def resize(self, rows, cols): self.rows, self.cols = rows, cols
    def idle(self): return time.time() - self.last
    def phase(self): return 'working' if self.busy else 'parked'
    def waiting(self): return not self.busy
    def files(self):                                 # what ITS recording edited, not the month-end export on every board card
        return [] if self.busy else [m.group(1) for t, _ in self.lines for m in [re.search(r'→ Edit: (\S+)', t)] if m]
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
        r = Replay(store, t['TaskId'], lines=TRANSCRIPTS[n] if n < len(TRANSCRIPTS) else _brief_replay(t.get('Title') or ''))
        terminal.SESSIONS[r.sid] = r
        n += 1
    return n
