"""The verdict's `thread`: triage reads the whole conversation on every verdict - who asks what, the owner's part, which mails are aside."""
import json
from taskuary import triage


def test_the_schema_asks_for_the_reading_on_every_verdict():
    t = triage.verdict_schema()['schema']['properties']['thread']
    assert t['type'] == ['object','null'] and t['additionalProperties'] is False
    assert set(t['required']) == {'asking','your_part','others','asks','aside'}      # thread on_you went with triage's readings (2026-11-23)


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


def test_the_thread_task_carries_the_last_reading_and_report():
    from taskuary import ingest
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = _task(s)
    assert 'reading' not in ingest.thread_task(s, tid) and 'agent_said' not in ingest.thread_task(s, tid)
    s._exec('UPDATE task SET ThreadJson=? WHERE TaskId=?', (json.dumps({'asking': 'Ray wants the pay date'}), tid))
    s.add_comment(tid, 'agent', 'agent', 'AGENT REPORT\nSummary: the pay run is Friday')
    ht = ingest.thread_task(s, tid)
    assert ht['reading']['asking'] == 'Ray wants the pay date' and 'Friday' in ht['agent_said']


def test_the_chat_payload_carries_the_reading():
    from taskuary import server    # TASKUARY_HOME is set to a temp dir before this import: importing it migrates the live home
    s = server.store
    tid = s.create_task({'Title': 'Export date', 'Kind': 'general', 'Status': 'open'}, 'test')
    assert server._assistant_payload(tid)['thread'] is None
    s._exec('UPDATE task SET ThreadJson=? WHERE TaskId=?', (json.dumps({'asking': 'Ray wants the export date', 'your_part': 'Confirm'}), tid))
    assert server._assistant_payload(tid)['thread']['asking'] == 'Ray wants the export date'


def test_a_filed_mail_keeps_its_reading():
    """An FYI or a report has no task to hold triage's reading: it stays on the message's own route, and the item's payload carries it."""
    from taskuary import server
    s = server.store
    mid = s.add_message({'Channel': 'email', 'Subject': 'Regional newsletter', 'BodyText': 'Sharing for visibility.', 'FromName': 'Erin Blake', 'Status': 'filed'})
    assert s.message_thread(mid) is None and server.get_message(mid)['reading'] is None
    s.add_route(mid, None, 'file', None, 'triage: fyi', [], 'triage', verdict={'intent': 'fyi', 'thread': {'asking': 'Erin shares the newsletter', 'your_part': 'Nothing - the Lakeview move is in it', 'asks': [], 'aside': [{'mid': 0, 'why': 'shared only'}]}})
    th = server.get_message(mid)['reading']
    assert th['asking'] == 'Erin shares the newsletter' and th['aside'][0]['mid'] == mid and s.message_thread(mid) == th
    s.add_route(mid, None, 'file', None, 'retriaged', [], 'triage', verdict={'intent': 'fyi'})   # a newer verdict with no reading: the last one stands
    assert s.message_thread(mid)['asking'] == 'Erin shares the newsletter'


def test_a_closed_thread_task_is_shown_closed_with_nothing_awaited():
    """Walk 18 (L2): Erin's agent asked her where the data lives; she pressed Mark done; Alex sent the ask again and triage filed it - "TQ-0001
    already waits on Erin's answer". The close let that question go: triage is shown the task closed, nothing owed or awaited on it, and
    of its last reading only what the thread was about."""
    from taskuary import concierge, ingest, workerstate as ws
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = _task(s)
    s._exec('UPDATE task SET ThreadJson=? WHERE TaskId=?', (json.dumps({'asking': 'Alex wants the vendor sheet', 'your_part': 'say where the data lives',
                                                                       'asks': [], 'aside': [], 'on_you': ['Answer where the data lives']}), tid))
    s.set_task_checklist(tid, ['Build the sheet'], 'agent')
    ws.record(s, tid, 'sid1', 'input_needed', text='Where does the vendor data live?', source='api')
    assert 'waiting for your input' in ingest.thread_task(s, tid)['stands']
    concierge.close_task(s, tid)
    ht = ingest.thread_task(s, tid)
    assert (ht['status'], ht['stands']) == ('closed', 'closed - no input awaited from anyone')
    assert ht['reading'] == {'asking': 'Alex wants the vendor sheet', 'asks': [], 'aside': []}
    assert 'open_todos' not in ht and 'data live' not in json.dumps(ht)
