"""A draft remembers which mail it answers (delivery target), apart from the newest mail it saw (freshness)."""
from taskuary.store import MemoryStore


def test_a_review_keeps_its_target_and_why_apart_from_its_freshness():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Repair the export', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    rid = s.add_review({'TaskId': tid, 'MessageId': 10, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Done.'})
    s.update_review_message(rid, 12); s.set_review_answers(rid, 11); s.set_review_why(rid, 'Erin asked for the export. ' + 'x' * 600)
    r = s.get_review(rid)
    assert (r['MessageId'], r['AnswersMid']) == (12, 11) and r['DraftWhy'].startswith('Erin asked') and len(r['DraftWhy']) <= 400
    s.cx.execute("UPDATE review SET DeliveryState='sent' WHERE ReviewId=?", (rid,))
    s.set_review_answers(rid, 10); s.set_review_why(rid, 'later')
    r = s.get_review(rid)
    assert r['AnswersMid'] == 11 and r['DraftWhy'].startswith('Erin asked')
    s.set_review_answers(s.add_review({'TaskId': tid, 'MessageId': 1, 'Kind': 'draft_reply', 'Status': 'pending'}), None)


import json
from taskuary import wrapup, floor


def thread(asks=(), aside=()):
    s = MemoryStore(); tid = s.create_task({'Title': 'Repair the export', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    rows = [('ray@northwind.example', 'Ray Colton', 'Can you repair the export?', {'to': ['alex@northwind.example'], 'cc': ['gail@northwind.example']}),
            ('gail@northwind.example', 'Gail Moreno', 'Thanks!', {'to': ['alex@northwind.example', 'ray@northwind.example']}),
            ('ray@northwind.example', 'Ray Colton', 'thanks', {'to': ['alex@northwind.example'], 'cc': ['gail@northwind.example']})]
    ids = [s.add_message({'TaskId': tid, 'ExternalId': f'e{i}', 'ConversationId': 'conv-1', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                          'Subject': 'Export', 'FromName': n, 'FromEmail': a, 'SentAt': f'2026-11-04 09:0{i}:00', 'BodyText': b, 'Status': 'routed',
                          'RecipientsJson': json.dumps(r)}) for i, (a, n, b, r) in enumerate(rows)]
    th = {'asks': [{'mid': ids[i], 'about': 'the export'} for i in asks], 'aside': [{'mid': ids[i], 'why': 'thanks'} for i in aside]}
    s.cx.execute('UPDATE task SET ThreadJson=? WHERE TaskId=?', (json.dumps(th), tid))
    return s, tid, ids


def test_the_reply_answers_the_mail_that_holds_the_ask():
    s, tid, ids = thread(asks=[0], aside=[1, 2])
    out = wrapup.agent_reply(s, tid, 'Hi Ray - the export is repaired and re-run.', 'coding')
    r = s.get_review(out['review_id']); env = s.review_envelope(out['review_id'])
    assert (r['MessageId'], r['AnswersMid']) == (ids[2], ids[0])
    assert 'ray@northwind.example' in json.dumps(env['to']) and 'gail@northwind.example' in json.dumps(env['cc'])


def test_a_thread_of_only_thanks_answers_the_newest_as_today():
    s, tid, ids = thread(aside=[1, 2])
    out = wrapup.agent_reply(s, tid, 'Hi Ray - you are welcome.', 'coding')
    r = s.get_review(out['review_id'])
    assert (r['MessageId'], r['AnswersMid']) == (ids[2], None) and 'ray@northwind.example' in json.dumps(s.review_envelope(out['review_id']))


def test_answers_names_the_mail_the_owner_means():
    s, tid, ids = thread(asks=[0], aside=[1, 2])
    out = wrapup.agent_reply(s, tid, 'Hi Gail - noted.', 'coding', answers=ids[1])
    assert s.get_review(out['review_id'])['AnswersMid'] == ids[1] and 'gail@northwind.example' in json.dumps(s.review_envelope(out['review_id'])['to'])
    bad = wrapup.agent_reply(s, tid, 'Hi - noted again.', 'coding', answers=999)
    assert bad == {'ok': False, 'why': '#999 is not a mail on this task'}


def test_the_cli_and_floor_know_answers():
    assert floor._taskuary_cmd(['taskuary', '--reply', 'hi', '--answers', '11']) == []
    from taskuary import server
    assert server.AgentReplyBody(task_id=1, answers=11).answers == 11 and server.AgentReplyBody(task_id=1).answers is None
    import inspect, taskuary.cli as cli
    assert "'--answers'" in inspect.getsource(cli) and "'answers': args.answers" in inspect.getsource(cli)


def test_a_second_save_pointed_at_another_mail_replaces_the_recipients():
    s, tid, ids = thread(asks=[0], aside=[1, 2])
    rid = wrapup.agent_reply(s, tid, 'Hi Ray - repaired.', 'coding')['review_id']
    assert 'gail@northwind.example' in json.dumps(s.review_envelope(rid)['cc'])
    wrapup.agent_reply(s, tid, 'Hi Gail - noted.', 'coding', answers=ids[1])
    env = s.review_envelope(rid)
    assert s.get_review(rid)['AnswersMid'] == ids[1] and 'gail@northwind.example' in json.dumps(env['to']) and 'ray@northwind.example' in json.dumps(env['to'])


def test_a_plain_re_save_keeps_the_answers_mid_already_pinned():
    s, tid, ids = thread(aside=[1, 2])
    rid = wrapup.agent_reply(s, tid, 'Hi Ray - first.', 'coding')['review_id']
    s.set_review_answers(rid, ids[0])
    wrapup.agent_reply(s, tid, 'Hi Ray - second.', 'coding')
    assert s.get_review(rid)['AnswersMid'] == ids[0]
