"""MEMORY HYGIENE (the design's S5, 2026-11-01): the audit found LEARNED.md's "Your people" holding a mail-system relay and a personal
contact, "Promises" and "What to bring up" empty, nothing ever expiring, and one cap shared by every workstream. Each is pinned here on
its shape, with invented people only (CLAUDE.md)."""
from datetime import datetime, timedelta
from unittest import mock
import pytest
from taskuary import funnel, learn, learned_cut, learnedgraph as lg, memorylines, workstreams as W
from taskuary.store import MemoryStore
from taskuary.testing import Factory

OMAR, ERIN, MOM = 'omar@ledger.example', 'erin@northwind.example', 'mom@family.example'
def ago(**k): return (datetime.now() - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')
TODAY = datetime.now().strftime('%Y-%m-%d')


@pytest.fixture
def s():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 'test')
    W.save(s, [{'name': 'Northwind finance systems', 'domains': ['northwind.example']}, {'name': 'Ledger app', 'people': [OMAR]},
               {'name': 'Personal', 'personal': True, 'people': [MOM]}])
    return s


def test_a_line_whose_habit_went_quiet_for_ninety_days_is_closed_not_kept(s):
    old = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
    stale = lg.fmt({'key': 'answer gail', 'text': 'You answer Gail within the hour', 'ev': ['msg1'], 'score': 5, 'seen': old, 'status': 'live'})
    fresh = lg.fmt({'key': 'answer erin', 'text': 'You answer Erin the same day', 'ev': ['msg2'], 'score': 5, 'seen': TODAY, 'status': 'live'})
    doc = f"# LEARNED\n\n## Your people\n{stale}\n{fresh}\n- My own line about Gail stays\n"
    out = learn.expire(s, doc)
    assert 'You answer Gail within the hour' not in out and 'You answer Erin the same day' in out and 'My own line about Gail stays' in out
    assert [h['Action'] for h in s.learned_history('answer gail')] == ['expired']


def test_the_cap_holds_per_workstream_so_one_busy_hat_does_not_push_another_out(s):
    f = Factory(s)
    led = [f.message(channel='email', from_email=OMAR) for _ in range(learn.CAP + 3)]
    day = f.message(channel='email', from_email=ERIN)
    ls = [lg.fmt({'key': f'led {i}', 'text': f'Ledger habit {i}', 'ev': [f'msg{m}'] * 3, 'score': 9, 'seen': TODAY, 'status': 'live'}) for i, m in enumerate(led)]
    ls.append(lg.fmt({'key': 'day 1', 'text': 'Day-job habit', 'ev': [f'msg{day}'], 'score': 4, 'seen': TODAY, 'status': 'live'}))
    doc = "# LEARNED\n\n## How you work\n" + '\n'.join(ls) + f"\n\n{learn.WATCH_HEADER}\n{learn.HYP_START}\n{learn.HYP_END}\n"
    shared = learn._caps(doc)                 # one shared cap: the day job's weaker line is pushed out
    apart = learn._caps(doc, store=s)         # per workstream: it stays, and only the Ledger app's overflow waits
    live = lambda d: [l['text'] for l in lg.lines(d) if l['status'] == 'live']
    assert 'Day-job habit' not in live(shared) and 'Day-job habit' in live(apart)
    assert len([t for t in live(apart) if t.startswith('Ledger')]) == learn.CAP


def test_promises_come_from_the_owners_sent_words_and_leave_when_kept(s):
    f = Factory(s)
    mid = f.message(channel='email', direction='out', status='context', RecipientsJson='{"to": ["ray@northwind.example"]}', sent_at=ago(days=1))
    s._exec("INSERT INTO sent_verdict (MessageId, Promise, What, Due) VALUES (?,1,'send the accruals file','Thursday')", (mid,))
    doc = learn.promise_lines(s, "# LEARNED\n\n## Promises\n")
    assert "You told ray@northwind.example you'd send the accruals file by Thursday" in doc
    s._exec('UPDATE sent_verdict SET DeliveredBy=1 WHERE MessageId=?', (mid,))
    assert 'accruals' not in learn.promise_lines(s, doc)


def test_each_line_carries_its_workstream_and_a_reader_leaves_out_another_hats_lines(s):
    f = Factory(s)
    t = f.task(title='Export greyed'); m = f.message(task_id=t, channel='email', from_email=OMAR)
    led = lg.fmt({'key': 'led fix', 'text': 'Tester bug reports are fixed in code, never answered', 'ev': [f'msg{m}'] * 3, 'score': 6, 'seen': TODAY, 'status': 'live'})
    e = f.message(channel='email', from_email=ERIN)
    day = lg.fmt({'key': 'day ans', 'text': 'Budget asks are answered the same day', 'ev': [f'msg{e}'] * 3, 'score': 6, 'seen': TODAY, 'status': 'live'})
    s.save_doc('learned', f"# LEARNED\n\n## How you work\n{led}\n{day}\n", 'reflect')
    assert W.tag_lines(s) == 2
    assert {r['Key']: r['Workstream'] for r in s._rows('SELECT Key, Workstream FROM learned_line')} == {'led fix': 'ledger-app', 'day ans': 'northwind-finance-systems'}
    got = learned_cut.for_reader(s, 'agents', {'workstream': 'ledger-app'})
    assert 'fixed in code' in got and 'answered the same day' not in got
    both = learned_cut.for_reader(s, 'agents', {})
    assert 'fixed in code' in both and 'answered the same day' in both


def test_the_owners_done_on_an_idea_teaches_what_to_bring_up(s):
    i = s.upsert_idea({'key': 'idea:q4', 'kind': 'idea', 'text': 'Three Q4 budget changes touch the same app - batch them', 'action': {}}, ago(hours=1))
    with mock.patch.object(memorylines, 'teach_soon') as teach:
        funnel._idea_done(s, f"idea:{i['IdeaId']}", 'owner')
    (args, kw), = teach.call_args_list
    assert args[1:3] == ('idea_done', f"idea{i['IdeaId']}") and kw['section'] == 'bring' and 'batch them' in args[3]
    with mock.patch.object(memorylines, 'teach_soon') as teach:
        j = s.upsert_idea({'key': 'idea:other', 'kind': 'idea', 'text': 'x', 'action': {}}, ago(hours=1))
        funnel._idea_done(s, f"idea:{j['IdeaId']}", 'task')          # put down by its task closing: the owner said nothing
    assert teach.call_args_list == []
