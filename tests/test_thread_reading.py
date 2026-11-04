"""The verdict's `thread`: triage reads the whole conversation on every verdict - who asks what, the owner's part, which mails are aside."""
import json
from taskuary import triage


def test_the_schema_asks_for_the_reading_on_every_verdict():
    t = triage.verdict_schema()['schema']['properties']['thread']
    assert t['type'] == ['object','null'] and t['additionalProperties'] is False
    assert set(t['required']) == {'asking','your_part','others','asks','aside','on_you'}


def test_a_reading_keeps_only_mids_it_was_shown():
    j = {'thread': {'asking': 'Ray wants the pay date', 'asks': [{'mid': 11, 'about': 'pay date'}, {'mid': 99, 'about': 'made up'}],
                    'aside': [{'mid': 0, 'why': 'thanks only'}]}}
    th = triage.thread_of(j, {11, 12})
    assert th['asks'] == [{'mid': 11, 'about': 'pay date'}] and th['aside'] == [{'mid': 0, 'why': 'thanks only'}]


def test_an_older_or_partial_reading_is_no_reading_or_filled():
    assert triage.thread_of({}, set()) is None and triage.thread_of({'thread': 'text'}, set()) is None
    assert triage.thread_of({'thread': {'asking': 'x'}}, set())['asks'] == []
    assert triage.thread_of({'thread': {'asks': [{'mid': 'eleven'}], 'aside': None}}, {11}) is None


def test_classify_carries_the_reading():
    llm = lambda system, user, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'x', 'title': 't', 'summary': 's',
        'thread': {'asking': 'Ray', 'your_part': 'pay', 'others': [], 'asks': [{'mid': 11, 'about': 'pay date'}], 'aside': [], 'on_you': []}})
    out = triage.classify_intent({'subject': '', 'body': 'ok'}, llm=llm, thread={'exchange': ['[#11] Ray Colton · 11-02 09:00: when do you pay?']})
    assert out['thread']['asks'][0]['mid'] == 11


def _task(s):
    return s.create_task({'Title': 'Pay date', 'Kind': 'general', 'Status': 'open'}, 't')

def test_a_route_with_a_reading_copies_it_to_the_task():
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = _task(s)
    s.add_route(7, tid, 'create', None, 'x', [], 'triage', verdict={'intent': 'reply_only', 'thread': {'asking': 'Ray', 'asks': [], 'aside': [{'mid': 0, 'why': 'thanks only'}]}})
    assert s.task_thread(tid)['aside'][0]['mid'] == 7 and s.aside_mids(tid) == {7}

def test_old_rows_have_no_reading():
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = _task(s)
    s.add_route(7, tid, 'create', None, 'x', [], 'triage', verdict={'intent': 'fyi'})
    s._exec('INSERT INTO route (MessageId,TaskId,Decision,CreatedAt,VerdictJson) VALUES (8,?,?,?,?)', (tid, 'attach', 'now', 'not json'))
    assert s.task_thread(tid) is None and s.aside_mids(tid) == set()
