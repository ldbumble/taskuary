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

# (title or key fragment, ok verbs, never verbs, prompt needs)
CASES = [
    ('Month-end close is short', {'reply', 'regular_agent'}, {'not_ours', 'close'}, ['POSSIBLE DUPLICATES', 'Reconcile the August GL export']),
    ('New starter on Monday', {'reply', 'regular_agent'}, {'not_ours'}, []),
    ('did the overnight import finish', {'close'}, {'not_ours', 'approve'}, ['It finished at 04:10']),
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
    ('Q3 accruals file', {'close'}, {'reply'}, ['NOTHING HAS COME IN SINCE IT WENT']),
    ('Helpdesk tickets by day', {None}, set(), []),
    ('Vendor portal maintenance', {None, 'not_ours'}, {'mine', 'regular_agent'}, []),
    ('importers#215', {None, 'regular_agent', 'mine'}, {'not_ours'}, []),
    ('Reconcile the August GL export', {'reply', 'regular_agent', 'close'}, {'not_ours'}, []),
    ('agent asking (general)', {'answer_agent'}, {'stop_agent'}, ['THE AGENT IS ASKING']),
    ('agent asking (coding)', {'answer_agent'}, {'stop_agent'}, ['THE AGENT IS ASKING']),
    ('agent finished (general)', {'close'}, set(), ["RUN ENDED (finished)"]),
    ('agent finished (coding)', {'close'}, set(), ["RUN ENDED (finished)"]),
    ('agent failed (general)', {'new_task'}, {'continue', 'stop_agent'}, ['WHAT FAILED', 'test database was not reachable']),
    ('agent failed (coding)', {'new_task'}, {'continue'}, ['WHAT FAILED', 'test database was not reachable']),
    ('agent stopped-saved (general)', {None, 'defer', 'stop_agent'}, set(), []),
    ('agent stopped-saved (coding)', {'continue'}, set(), []),
    ('agent working (coding)', {None}, set(), []),
    ('agent working (general)', {None}, set(), []),
    ('Close the August books', {'close'}, set(), ['EVERY TODO ON THE TASK IS TICKED']),
    ('Renew the PhishGuard licence', {None, 'defer'}, {'not_ours'}, ['remind me on']),
    ('Move payroll to Payworth', {'defer'}, {'not_ours'}, ['THE GOAL']),
    ('Migrate the census export', {'defer'}, {'not_ours'}, ['THE GOAL', 'late']),
    ('Ray: schema sign-off', {None, 'defer'}, {'not_ours'}, []),
    # ...the states the matrix lacks
    ('Vendor W-9 for the new supplier', {'chase'}, {'let_go', 'close'}, ['quiet']),
    ('Budget figures for Q4', {'chase'}, {'let_go'}, ['quiet']),
    ('can you cover the Thursday call', {'reply'}, {'not_ours'}, ['whatsapp']),
]

RAIL = {'Vendor W-9 for the new supplier', 'Move payroll to Payworth', 'Migrate the census export'}     # judged as the processing rail draws them


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
    """(verb or None, line, prompt) for one item at item.shown, tier 2, through the real advisor.judge."""
    from taskuary import advisor, demo
    calls = []
    base = llm or demo.brain()
    def rec(system, user, **kw): out = base(system, user, **kw); calls.append(user); return out
    tgt = advisor.target_of(s, item.get('key'))
    if not tgt: return None, 'no target', ''
    if advisor._at_work(s, *tgt): return None, 'working', ''          # for_key shows nothing over an agent at work
    orig = advisor._item
    with mock.patch.object(advisor, '_item', lambda store, tk, ti, key=None: syn.get(key) or (item if key == item.get('key') else orig(store, tk, ti, key))):
        rid = advisor.judge(s, advisor.SHOWN, tgt[0], tgt[1], advisor.revision(s, *tgt), tier=2, llm=rec, key=item.get('key'))
        r = s._one('SELECT * FROM advice WHERE Id=?', (rid,)) or {}
    return r.get('Verb'), r.get('Line') or r.get('Dropped') or '', calls[-1] if calls else ''


def grade(verb, ok, never) -> str:
    if verb is None: return 'right' if None in ok else 'gap'
    return 'right' if verb in ok and verb not in never else 'wrong'


def run(llm=None) -> list:
    s, by, syn = world()
    out = []
    for title, ok, never, needs in CASES:
        it = by.get(title)
        if not it: out.append({'case': title, 'grade': 'missing', 'verb': None, 'line': 'no item', 'missing': needs}); continue
        verb, line, prompt = judge(s, it, syn, llm)
        out.append({'case': title, 'key': it.get('key'), 'verb': verb, 'line': line, 'grade': grade(verb, ok, never),
                    'missing': [n for n in needs if n.lower() not in prompt.lower()], 'prompt': prompt})
    return out


if __name__ == '__main__':
    os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='tq-advcases-'))
    from taskuary import advisor; advisor.BACKGROUND = False
    res = run()
    for r in res: print(f"{r['grade']:6} {r['case'][:40]:40} {str(r['verb']):14} {r['line'][:70]}" + (f"  MISSING {r['missing']}" if r['missing'] else ''))
    from collections import Counter
    print(dict(Counter(r['grade'] for r in res)), 'prompt gaps:', sum(bool(r['missing']) for r in res))
