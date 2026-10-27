"""THE ADVISOR'S EVAL (the deep dive, 2026-10-20): every state the demo and the advisor matrix's world hold, plus a few the matrix lacks
(a person past their day, a chat line pulled into the chat, a slipped follow-up), each judged at item.shown by the demo's scripted
brain - the same answers the demo gives - and graded against what a careful assistant would light:

    ok      - the verbs that are right here (None: saying nothing is right)
    never   - verbs that are wrong whatever the line says
    needs   - what the PROMPT must carry for the right answer to be reachable at all (a real model reads the same prompt)

A verb in `ok` is right; one in `never`, or any other verb, is wrong; silence where `ok` has no None is a gap. Invented Northwind
people only. Used by tests/test_advisor_cases.py; run it alone (python -m tests.advisor_cases) for the table."""
import json, os, re, tempfile
from datetime import datetime, timedelta
from unittest import mock

# (title or key fragment, ok verbs, never verbs, prompt needs) - graded against THE ONE DECISION (advisor.decide, the design phase A,
# 2026-10-23): `next` is Next lit and nothing said, None is nothing lit; `needs` is checked only where the model was asked (the rule
# decides the rest from the item's facts, and no prompt is written)
CASES = [
    # the same sender asking two things is not a duplicate (the design, 2026-10-23): with nothing on its thread, the ask is answered
    ('Month-end close is short', {'reply', 'regular_agent', 'defer'}, {'not_ours', 'close'}, []),
    ('New starter on Monday', {'reply', 'regular_agent'}, {'not_ours'}, []),
    # a draft that cannot go from here: Copy lit, said by nothing - the reason is its hover (the owner, 2026-10-22)
    ('did the overnight import finish', {'copy'}, {'not_ours', 'approve'}, []),
    ('Invoice 88213', {'redraft'}, {'approve'}, ["Friday's payment run", 'ATTACHED TO THE DRAFT: nothing']),
    ('AP cutover - Thursday?', {'approve'}, {'not_ours'}, ['Thursday still works']),
    ('Lease renewal for the Elm Street office', {'new_task', 'fix'}, {'redraft', 'approve'}, ['WHAT FAILED', 'no such user']),
    ('Badge access for the new AP clerk', {'reply'}, {'not_ours'}, []),
    ('Can you resend the Q3 numbers', {'redraft'}, {'approve'}, ['Sending the Q3 pack now', 'ATTACHED TO THE DRAFT: nothing']),
    ('Year-end audit', {'reply', 'regular_agent'}, {'not_ours'}, ['THE LAST 3 MESSAGES']),
    ('Spendly card limits', {'mine', 'defer', 'not_ours', 'regular_agent'}, set(), []),
    ('Vendor master clean-up', {'reply'}, {'close'}, ['A REPLY WAS ALREADY SENT']),
    ('Trainly seats', {'reply'}, {'close'}, []),
    ('importers#214', {'regular_agent', 'coding_agent'}, {'reply', 'not_ours'}, ['Traceback']),
    ('Q3 accruals file', {'close'}, {'reply'}, []),
    ('Helpdesk tickets by day', {'next'}, set(), []),
    ('Vendor portal maintenance', {'next', 'not_ours'}, {'mine', 'regular_agent'}, []),
    ('importers#215', {'next', 'regular_agent', 'mine'}, {'not_ours'}, []),
    # an agent at work on it: Next, and nothing said (the owner, 2026-10-13)
    ('Reconcile the August GL export', {'next'}, {'not_ours', 'reply'}, []),
    # an asking agent is answered in its own pane - no button lights for it (the owner, 2026-10-20: "we don't need that button")
    ('agent asking (general)', {None}, {'stop_agent', 'answer_agent'}, []),
    ('agent asking (coding)', {None}, {'stop_agent', 'answer_agent'}, []),
    ('agent finished (general)', {'close'}, set(), []),
    ('agent finished (coding)', {'close', 'review_changes'}, set(), []),
    # a failed general run is tried again from its saved conversation, never made a task of (owner-approved, 2026-10-21)
    ('agent failed (general)', {'continue'}, {'new_task', 'stop_agent'}, ['WHAT FAILED', 'test database was not reachable']),
    ('agent failed (coding)', {'new_task'}, {'continue'}, ['WHAT FAILED', 'test database was not reachable']),
    ('agent stopped-saved (general)', {'next', 'defer'}, set(), []),
    ('agent stopped-saved (coding)', {'continue'}, set(), []),
    ('agent working (coding)', {'next'}, set(), []),
    ('agent working (general)', {'next'}, set(), []),
    ('Close the August books', {'close'}, set(), []),
    ('Renew the PhishGuard licence', {'next', 'defer'}, {'not_ours'}, []),
    # a goal on track is Next; a step past its day is Chase, named in the line (the design, states 17 and 18)
    ('Move payroll to Payworth', {'next'}, {'not_ours'}, []),
    ('Migrate the census export', {'chase'}, {'not_ours'}, []),
    # ...and the step itself, due two days ago, is late on its header's own clock: Chase, as its goal says (the Advisor audit's judge, 2026-10-26)
    ('Ray: schema sign-off', {'chase'}, {'not_ours', 'defer'}, []),
    # ...the states the matrix lacks
    ('Vendor W-9 for the new supplier', {'chase'}, {'let_go', 'close'}, []),
    ('Budget figures for Q4', {'chase'}, {'let_go'}, []),
    ('can you cover the Thursday call', {'reply'}, {'not_ours'}, ['whatsapp']),
    # the owner's own usual (slice 4, 2026-10-25): Marcus is answered within the hour, and this ask has waited 3h - Reply, its lateness
    # the one line beside it, with what it was counted from in the prompt
    ('Q4 forecast numbers', {'reply'}, {'not_ours', 'defer'}, ['HOW SOON YOU ANSWER marcus@northwind.example: within the hour']),
    # ...whom the owner hands this sender's asks to, and the day their mail is put off to - read from the How you work line the owner can
    # correct, never from the count (the memory follow-ups, 2026-10-25)
    ('Night shift overtime rate', {'reply', 'forward'}, {'not_ours'}, ['WHOM YOU HANDED THEIR ASKS TO: ray@northwind.example, 2 of 2 times']),
    ('Payworth seat count renewal', {'reply', 'defer'}, {'not_ours'},
     ['WHEN YOU PUT THEIR MAIL OFF (a How you work line the owner can correct): "You put mail from renewals@payworth.example off to Friday"']),
]
LINES = {'Q4 forecast numbers': 'You usually answer Marcus within the hour; this is 3h.'}

RAIL = {'Vendor W-9 for the new supplier', 'Move payroll to Payworth', 'Migrate the census export'}     # judged as the processing rail draws them
# a duplicate whose agent is at work while the case is judged: "an agent is on it" now needs a live session or run, not the task's
# in_progress status a stopped agent leaves behind (advisor.related_line, 2026-10-22) - the demo seeds no live session, so the case says one
AGENT_ON = {'Month-end close is short': 'Reconcile the August GL export'}


def world():
    """(store, {case title: item}) - the demo, the matrix's world, and the extra states. Needs a scratch TASKUARY_HOME."""
    from taskuary import demo, faults, funnel, terminal, advisor
    from taskuary.store import MemoryStore
    from taskuary.funnel import _item as mk
    from taskuary.testing import Factory
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    demo.seed(s)
    with mock.patch.dict(os.environ, {faults.ENV: '1'}):
        assert faults.active(), 'the eval needs a scratch home'
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
    # ...and the processing rail's cards, where a real install draws them: a person past their day and a goal's facts are its reading
    from taskuary import processing_unread
    try:
        s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[]); funnel.invalidate()
        rail = processing_unread.build(s, live_state=[], include_read=True)['items']
    except Exception: rail = []
    by = {}
    for title, *_ in CASES:
        hit = next((i for i in rail if title in RAIL and title.lower() in str(i.get('title') or '').lower()), None)
        hit = hit or next((i for i in items if title.lower() in str(i.get('title') or '').lower()), None)
        # ...and a row the legacy pile cut (its `hidden` tail - read before the processing reads are on) is still on the rail a real
        # install draws: the demo's calendar rows pushed the GL-export notice past that cut (2026-10-20)
        hit = hit or next((i for i in rail if title.lower() in str(i.get('title') or '').lower()), None)
        if not hit:
            t = next((x for x in s.list_tasks() if title.lower() in str(x.get('Title') or '').lower()), None)
            hit = advisor._item(s, 'task', t['TaskId']) if t else None
        if hit and title == 'can you cover the Thursday call': hit = funnel.item_for_key(s, f'task:{wt}') or hit   # pulled in by hand
        by[title] = hit
    return s, by, syn


def judge(s, item, syn, llm=None):
    """(verb or None, line, prompt) for one item: THE ONE DECISION every surface reads (advisor.decide, the design phase A) - the rule's
    move from the item's facts, and where the state asks the model (rulebook `ask`), the scripted brain's read of it at item.shown,
    tier 2, through the real advisor.judge. `prompt` is '' where the rule decided alone - no model was asked."""
    from taskuary import advisor, demo
    calls = []
    base = llm or demo.brain()
    def rec(system, user, **kw): out = base(system, user, **kw); calls.append(user); return out
    tgt = advisor.target_of(s, item.get('key'))
    if not tgt: return None, 'no target', ''
    orig = advisor._item
    with mock.patch.object(advisor, '_item', lambda store, tk, ti, key=None: syn.get(key) or (item if key == item.get('key') else orig(store, tk, ti, key))):
        if not advisor._at_work(s, *tgt):
            advisor.judge(s, advisor.SHOWN, tgt[0], tgt[1], advisor.revision(s, *tgt), tier=2, llm=rec, key=item.get('key'))
        with mock.patch.object(advisor, 'notice'): d = advisor.decide(s, item.get('key'), preread=False)
    return d.get('verb'), d.get('line') or d.get('state') or d.get('none') or '', calls[-1] if calls else ''


def grade(verb, ok, never) -> str:
    if verb is None: return 'right' if None in ok else 'gap'
    return 'right' if verb in ok and verb not in never else 'wrong'


def run(llm=None) -> list:
    s, by, syn = world()
    out = []
    for title, ok, never, needs in CASES:
        it = by.get(title)
        if not it: out.append({'case': title, 'grade': 'missing', 'verb': None, 'line': 'no item', 'missing': needs}); continue
        on = {t['TaskId'] for t in s.list_tasks() if AGENT_ON.get(title) and AGENT_ON[title].lower() in str(t.get('Title') or '').lower()}
        from taskuary import workerstate as ws
        live = ws._live
        with mock.patch.object(ws, '_live', lambda tid: object() if tid in on else live(tid)): verb, line, prompt = judge(s, it, syn, llm)
        out.append({'case': title, 'key': it.get('key'), 'verb': verb, 'line': line, 'grade': grade(verb, ok, never), 'asked': bool(prompt),
                    'missing': [n for n in needs if prompt and n.lower() not in prompt.lower()], 'prompt': prompt})
    return out


if __name__ == '__main__':
    os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='tq-advcases-'))
    from taskuary import advisor; advisor.BACKGROUND = False
    res = run()
    for r in res: print(f"{r['grade']:6} {r['case'][:40]:40} {str(r['verb']):14} {r['line'][:70]}" + (f"  MISSING {r['missing']}" if r['missing'] else ''))
    from collections import Counter
    print(dict(Counter(r['grade'] for r in res)), 'prompt gaps:', sum(bool(r['missing']) for r in res))
