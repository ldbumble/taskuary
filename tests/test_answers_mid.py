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


def drafted(s, tid, ids, said, channel=None):
    from taskuary import responder
    if channel: s.cx.execute('UPDATE message SET Channel=?', (channel,))
    rid = s.add_review({'TaskId': tid, 'MessageId': ids[2], 'Kind': 'draft_reply', 'Status': 'pending'})
    responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: said)
    return rid


def test_why_is_taken_off_and_kept():
    s, tid, ids = thread(asks=[0], aside=[1, 2])
    r = s.get_review(drafted(s, tid, ids, 'Friday works.' + chr(10) + 'WHY: He asked for a pay date; the run is Friday.' + chr(10) + 'FILES PROMISED: unnamed'))
    assert r['DraftText'].startswith('Friday works.') and 'WHY:' not in r['DraftText'] and r['DraftWhy'].startswith('He asked') and r['FilesPromised'] == '{"named": []}'


def test_the_drafter_answers_the_ask_to_everyone_on_it():
    s, tid, ids = thread(asks=[0], aside=[1, 2])
    rid = drafted(s, tid, ids, 'Hi Ray - done.'); r, env = s.get_review(rid), s.review_envelope(rid)
    assert (r['AnswersMid'], r['MessageId']) == (ids[0], ids[2]) and 'ray@northwind.example' in json.dumps(env['to']) and 'gail@northwind.example' in json.dumps(env['cc'])


def test_a_chat_has_no_reply_all():
    s, tid, ids = thread(asks=[0], aside=[1, 2])
    rid = drafted(s, tid, ids, 'Hi Ray - done.', channel='teams')
    assert s.review_envelope(rid) == {} and s.get_review(rid)['AnswersMid'] == ids[0]


def test_no_reading_no_change():
    s, tid, ids = thread()
    rid = drafted(s, tid, ids, 'Hi Ray - done.'); r = s.get_review(rid)
    assert r['AnswersMid'] is None and not r['DraftWhy'] and r['MessageId'] == ids[2]


def test_no_reading_outbound_last_keeps_the_prompt_from_the_last_message():
    from taskuary import responder
    s, tid, ids = thread()
    s.add_message({'TaskId': tid, 'ExternalId': 'e9', 'ConversationId': 'conv-1', 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'Direction': 'out',
                   'Subject': 'Export', 'FromName': 'Alex Doyle', 'FromEmail': 'alex@northwind.example', 'SentAt': '2026-11-04 09:30:00', 'BodyText': 'On it.',
                   'Status': 'routed', 'RecipientsJson': json.dumps({'to': ['ray@northwind.example']})})
    seen = []
    responder.draft_reply(s, tid, llm=lambda sys, user, **k: seen.append(user) or 'Done.')
    assert 'From: Alex Doyle <alex@northwind.example>' in seen[0]


def test_a_wrapped_why_is_all_taken_off():
    from taskuary import responder
    nl = chr(10)
    assert responder._answer(lambda *a, **k: 'Hi.' + nl + 'WHY: he asked' + nl + 'for a date.', 's', 'u', 10) == ('Hi.', None, 'he asked for a date.')
    assert responder._answer(lambda *a, **k: 'Hi.' + nl + 'FILES PROMISED: a.pdf' + nl + 'WHY: one' + nl + 'two', 's', 'u', 10) == ('Hi.', ['a.pdf'], 'one two')
    assert responder._answer(lambda *a, **k: 'Hi.' + nl + 'WHY: one' + nl + 'two' + nl + 'FILES PROMISED: a.pdf', 's', 'u', 10) == ('Hi.', ['a.pdf'], 'one two')
    assert responder._answer(lambda *a, **k: 'NO REPLY' + nl + 'WHY: nothing owed' + nl + 'to them.', 's', 'u', 10) == ('NO REPLY', None, 'nothing owed to them.')
