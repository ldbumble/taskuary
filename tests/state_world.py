"""THE STATE WORLD (moved from the Advisor's eval, 2026-11-15): the demo, the state matrix's faults world and the states they lack - a person
past their day, a chat line pulled into the chat, a slipped follow-up, a learned usual - each named by the title its card carries. Read by
tests/test_rulebook.py's state x surface matrix. Invented Northwind people only."""
import os
from datetime import datetime, timedelta
from unittest import mock

TITLES = [
    'Month-end close is short',
    'New starter on Monday',
    'did the overnight import finish',
    'Invoice 88213',
    'AP cutover - Thursday?',
    'Lease renewal for the Elm Street office',
    'Badge access for the new AP clerk',
    'Can you resend the Q3 numbers',
    'Year-end audit',
    'Spendly card limits',
    'Vendor master clean-up',
    'Trainly seats',
    'importers#214',
    'Q3 accruals file',
    'Helpdesk tickets by day',
    'Vendor portal maintenance',
    'importers#215',
    'Reconcile the August GL export',
    'agent asking (general)',
    'agent asking (coding)',
    'agent finished (general)',
    'agent finished (coding)',
    'agent failed (general)',
    'agent failed (coding)',
    'agent stopped-saved (general)',
    'agent stopped-saved (coding)',
    'agent working (coding)',
    'agent working (general)',
    'Close the August books',
    'Renew the PhishGuard licence',
    'Move payroll to Payworth',
    'Migrate the census export',
    'Ray: schema sign-off',
    'Vendor W-9 for the new supplier',
    'Budget figures for Q4',
    'can you cover the Thursday call',
    'Q4 forecast numbers',
    'Night shift overtime rate',
    'Payworth seat count renewal',
]

RAIL = {'Vendor W-9 for the new supplier', 'Move payroll to Payworth', 'Migrate the census export'}     # judged as the processing rail draws them


def world():
    """(store, {case title: item}) - the demo, the matrix's world, and the extra states. Needs a scratch TASKUARY_HOME."""
    from taskuary import demo, faults, funnel, rulebook
    from taskuary.store import MemoryStore
    from taskuary.funnel import _item as mk
    from taskuary.testing import Factory
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    s.starts_itself = True      # tests/conftest.py leaves the start to this world, below
    demo.seed(s)
    with mock.patch.dict(os.environ, {faults.ENV: '1'}):
        assert faults.active(), 'the world needs a scratch home'
        states = faults.world(s)
    f, at = Factory(s), (lambda d=0, h=0: (datetime.now() - timedelta(days=d, hours=h)).strftime('%Y-%m-%d %H:%M:%S'))
    # a person past their day on a step of yours: the slipped lane's Chase is the row's own move
    gail = ('Gail Moreno', 'gail@northwind.example')
    step = s.create_task({'Title': 'Vendor W-9 for the new supplier', 'Status': 'waiting', 'Assignee': f'person:{gail[1]}',
                          'DueAt': (datetime.now() - timedelta(days=9)).strftime('%Y-%m-%d')}, 'owner')
    # a thread the owner asked on that went quiet past the person's day: an idea in the slipped lane
    t = s.create_task({'Title': 'Budget figures for Q4', 'Status': 'open'}, 'owner')
    mid = s.add_message({'ConversationId': 'email:budget-q4', 'Channel': 'email', 'Subject': 'Budget figures for Q4', 'FromEmail': 'ray@northwind.example',
                         'FromName': 'Ray Colton', 'SentAt': at(d=12), 'BodyText': 'Can you send the Q4 budget figures?', 'Status': 'filed', 'TaskId': t})
    s.upsert_idea({'key': 'followup:budget-q4', 'kind': 'followup', 'text': 'No answer from Ray in 10 days on "Budget figures for Q4" - follow up?', 'sig': 'x',
                   'action': {'type': 'followup', 'mid': mid, 'tid': t, 'who_email': 'ray@northwind.example', 'asked_at': at(d=10)}}, at(h=1))
    # a chat line the owner pulls into the chat by hand: a WhatsApp question, on a task of its own
    wt = f.task(title='can you cover the Thursday call', status='open', kind='reply', source='whatsapp')
    wm = f.message(task_id=wt, channel='whatsapp', subject='can you cover the Thursday call', body='can you cover the Thursday call with the auditors? I am out',
                   from_name='Omar Keller', from_email='@omarkeller', source_name='Omar (whatsapp)', conversation_id='whatsapp:4410', sent_at=at(h=2))
    f.route(wm, wt, 'create', 'a question a sentence settles')
    # Marcus Reed, answered within the hour three times - and a fourth ask, three hours old
    marcus = ('Marcus Reed', 'marcus@northwind.example')
    for i, lag in enumerate((20, 35, 15)):
        mt, sent = f.task(title=f'Accruals check {i + 1}', status='done', kind='task'), datetime.now() - timedelta(days=10 + i * 7)
        f.message(task_id=mt, subject=f'Accruals check {i + 1}', body='Can you check the accruals?', from_name=marcus[0], from_email=marcus[1],
                  conversation_id=f'email:accruals-{i}', sent_at=sent.strftime('%Y-%m-%d %H:%M:%S'))
        s.add_message({'ConversationId': f'email:accruals-{i}', 'Channel': 'email', 'Subject': f'Re: Accruals check {i + 1}', 'FromName': 'You',
                       'FromEmail': 'alex@northwind.example', 'SentAt': (sent + timedelta(minutes=lag)).strftime('%Y-%m-%d %H:%M:%S'),
                       'BodyText': 'Checked.', 'Status': 'sent', 'TaskId': mt, 'Direction': 'out'})
    qt = f.task(title='Q4 forecast numbers', status='open', kind='task')
    f.message(task_id=qt, subject='Q4 forecast numbers', body='Can you send me the Q4 forecast numbers for the sync?', from_name=marcus[0],
              from_email=marcus[1], conversation_id='email:q4-forecast', sent_at=at(h=3))
    # the east site's manager, whose payroll asks the owner handed to Ray twice - and a third ask (the owner, 2026-10-25: "Hand it to a
    # person" pre-fills the usual recipient; the model reads whom, the topic is its to read)
    east = ('Site Manager East', 'east.manager@northwind.example')
    for i in range(2):
        ht = f.task(title=f'Payroll rate fix {i + 1}', status='waiting', kind='task')
        f.message(task_id=ht, subject=f'Payroll rate fix {i + 1}', body='A rate was wrong last cycle - can it be fixed?', from_name=east[0],
                  from_email=east[1], conversation_id=f'email:east-payroll-{i}', sent_at=at(d=20 - i * 7))
        s.audit('task', ht, 'handoff', 'owner', 'human', {'to': 'ray@northwind.example', 'channel': 'email', 'closed': False})
    nt = f.task(title='Night shift overtime rate', status='open', kind='task')
    f.message(task_id=nt, subject='Night shift overtime rate', body='The night shift overtime came through at the day rate - can this be fixed?',
              from_name=east[0], from_email=east[1], conversation_id='email:east-overtime', sent_at=at(h=2))
    # Payworth's notices, put off to Friday three times over three weeks: the reflection writes the How you work line Remind me reads
    from tests.memory_cases import put_off, reflected
    for d in (30, 23, 16): put_off(s, 'payworth', d)
    reflected(s)
    pt = f.task(title='Payworth seat count renewal', status='open', kind='task')
    f.message(task_id=pt, subject='Payworth seat count renewal', body='Your seats renew next month. Reply to change the count.', from_name='Payworth Renewals',
              from_email='renewals@payworth.example', conversation_id='email:payworth-seats', sent_at=at(h=2))
    # the home starts, as the app starts one before anything reads its rail (server lifespan), its membership then kept current inline
    # where the app runs a worker
    from types import SimpleNamespace
    from taskuary import processing_startup
    processing_startup.initialize(s, live_state=[]); s.membership_worker = SimpleNamespace(kick=s.reconcile_processing_membership)
    funnel.invalidate()
    pile = funnel.pile(s, quiet=True).get('items') or []
    seen, items = set(), []
    for i in pile + (funnel.full_items(s) or []):
        if i.get('key') not in seen: seen.add(i.get('key')); items.append(i)
    # the agents in every state, as the rail draws them (the matrix keeps no live sessions for them here)
    syn = {}
    for nm, tid in states.items():
        k, _, w = nm.partition('-')
        if k not in ('coding', 'general') or w == 'working': continue
        title = (s.get_task(tid) or {}).get('Title'); kw = dict(tid=tid, agent=k, channel='')
        it = (mk(f'agent:{tid}', 'agent', 'blocked', title, asking=True, request_kind='input_needed', **kw) if w == 'asking'
              else mk(f'agent:{tid}', 'agent', 'saved', title, **kw) if w == 'stopped-saved'
              else mk(f'agent:{tid}', 'agent', 'stopped', title, **kw) if w == 'failed'
              else mk(f'agent:{tid}', 'agentdone', 'done', title, summary='Done - the export keeps inter-company rows now, and the tests pass.', **kw))
        syn[it['key']] = it; items = [i for i in items if i.get('tid') != tid] + [it]
    # ...and the rail's own cards, read ones kept: a person past their day and a goal's facts are its reading
    from taskuary import processing_unread
    try: rail = processing_unread.build(s, live_state=[], include_read=True)['items']
    except Exception: rail = []
    by = {}
    for title in TITLES:
        hit = next((i for i in rail if title in RAIL and title.lower() in str(i.get('title') or '').lower()), None)
        hit = hit or next((i for i in items if title.lower() in str(i.get('title') or '').lower()), None)
        # ...a drafted reply's card is titled by its task; the case names the mail it answers
        hit = hit or next((i for i in items if i.get('mid') and title.lower() in str((s.get_message(i['mid']) or {}).get('Subject') or '').lower()), None)
        # ...and a row already read when the home started is still a card of the rail (the demo's GL-export notice, 2026-10-20)
        hit = hit or next((i for i in rail if title.lower() in str(i.get('title') or '').lower()), None)
        if not hit:
            t = next((x for x in s.list_tasks() if title.lower() in str(x.get('Title') or '').lower()), None)
            hit = rulebook._item(s, 'task', t['TaskId']) if t else None
        if hit and title == 'can you cover the Thursday call': hit = funnel.item_for_key(s, f'task:{wt}') or hit   # pulled in by hand
        by[title] = hit
    return s, by, syn
