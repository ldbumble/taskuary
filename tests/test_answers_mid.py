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
    assert bad['ok'] is False and bad['why'].startswith('#999 is not a mail on this task - use a number from THE MAIL ON THIS TASK')


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
    assert responder._answer(lambda *a, **k: 'Hi.' + nl + nl + 'WHY: he asked' + nl + 'for a date.', 's', 'u', 10) == ('Hi.', None, 'he asked for a date.')
    assert responder._answer(lambda *a, **k: 'Hi.' + nl + 'FILES PROMISED: a.pdf' + nl + nl + 'WHY: one' + nl + 'two', 's', 'u', 10) == ('Hi.', ['a.pdf'], 'one two')
    assert responder._answer(lambda *a, **k: 'Hi.' + nl + nl + 'WHY: one' + nl + 'two' + nl + 'FILES PROMISED: a.pdf', 's', 'u', 10) == ('Hi.', ['a.pdf'], 'one two')
    assert responder._answer(lambda *a, **k: 'NO REPLY' + nl + nl + 'WHY: nothing owed' + nl + 'to them.', 's', 'u', 10) == ('NO REPLY', None, 'nothing owed to them.')


def test_a_why_heading_inside_the_body_is_not_a_why():
    from taskuary import responder
    nl = chr(10); body = nl.join(['Hi Ray.', 'Why: the run moved.', 'It is Friday now and the file goes Thursday.', 'Thanks, Alex'])
    assert responder._answer(lambda *a, **k: body, 's', 'u', 10) == (body, None, None)
    assert responder._answer(lambda *a, **k: body + nl + 'WHY: he asked.', 's', 'u', 10) == (body, None, 'he asked.')


# SEND GOES TO THE ASK; AN ASIDE MOVES NOTHING (2026-11-04): a "thanks" on the thread is not news the draft is behind, and Send answers the
# mail that asked (AnswersMid), not the newest line it saw (MessageId, the freshness marker). Invented people; the provider is a stub.
from unittest import mock
from taskuary import verdicts, ingest
SENT = {'channel': 'email', 'to': ['ray@northwind.example'], 'cc': []}
ASIDE = {'intent': 'fyi', 'why': 'thanks', 'thread': {'asks': [], 'aside': [{'mid': 0, 'why': 'a thanks'}]}}


def line(s, tid, i, who, body, aside=False, conv='conv-9'):
    a, n = who
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'x{i}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'Subject': 'Export', 'FromName': n, 'FromEmail': a, 'SentAt': f'2026-11-04 10:{i:02d}:00', 'BodyText': body, 'Status': 'routed',
                         'RecipientsJson': json.dumps({'to': ['alex@northwind.example'], 'cc': ['gail@northwind.example']})})
    s.add_route(mid, tid, 'attach', 1.0, 'triage', [], 'triage', verdict=ASIDE if aside else {'intent': 'reply_only', 'why': 'asks'})
    return mid


RAY, GAIL, ERIN = ('ray@northwind.example', 'Ray Colton'), ('gail@northwind.example', 'Gail Moreno'), ('erin@northwind.example', 'Erin Blake')


def asked():
    s = MemoryStore(); tid = s.create_task({'Title': 'Repair the export', 'Kind': 'task', 'Status': 'open', 'Source': 'email'}, 'router')
    ask = line(s, tid, 11, RAY, 'Can you repair the export?')
    rid = s.add_review({'TaskId': tid, 'MessageId': ask, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Hi Ray - repaired.'})
    return s, tid, ask, rid


def test_a_thanks_does_not_mark_the_draft_stale():
    s, tid, ask, rid = asked(); line(s, tid, 12, GAIL, 'Thanks!', aside=True)
    assert verdicts.context_moved(s, s.get_review(rid)) == (False, None)


def test_a_real_reply_still_moves_it():
    s, tid, ask, rid = asked(); line(s, tid, 12, GAIL, 'Thanks!', aside=True); real = line(s, tid, 14, RAY, 'Also the September one?')
    moved, latest = verdicts.context_moved(s, s.get_review(rid))
    assert moved and latest['MessageId'] == real


def test_send_goes_to_the_ask():
    s, tid, ask, rid = asked(); last = line(s, tid, 13, GAIL, 'Thanks!', aside=True)
    s.update_review_message(rid, last); s.set_review_answers(rid, ask)
    seen = []
    out = verdicts._deliver_review(s, s.get_review(rid), 'Hi Ray - repaired.', 'approve', 'owner', send_fn=lambda snap: seen.append(snap) or SENT)
    assert out['ok'] and seen[0]['message']['MessageId'] == ask and 'ray@northwind.example' in json.dumps(seen[0]['envelope'])
    assert s.get_message(ask)['Status'] == s.get_message(last)['Status'] == 'sent'


def test_a_review_with_no_answers_mid_sends_to_its_message_as_before():
    s, tid, ask, rid = asked(); seen = []
    verdicts._deliver_review(s, s.get_review(rid), 'Hi Ray - repaired.', 'approve', 'owner', send_fn=lambda snap: seen.append(snap) or SENT)
    assert seen[0]['message']['MessageId'] == ask and s.get_message(ask)['Status'] == 'sent'


def test_two_drafts_answer_their_own_mails():
    s, tid, ask, a = asked(); erin = line(s, tid, 15, ERIN, 'And can you send me the new totals?')
    b = s.add_review({'TaskId': tid, 'MessageId': erin, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Hi Erin - attached.'})
    for r in (a, b): s.update_review_message(r, erin)
    s.set_review_answers(a, ask); s.set_review_answers(b, erin)
    line(s, tid, 16, GAIL, 'Thanks both!', aside=True)
    seen = []
    with mock.patch('taskuary.outbound.reply_to_message', lambda st, msg, body, to=None, cc=None, attachments=None: seen.append((msg['MessageId'], to)) or SENT):
        for r in (a, b): verdicts.decide(s, s.get_review(r), 'approve', s.get_review(r)['DraftText'])
    assert [m for m, _ in seen] == [ask, erin] and 'ray@northwind.example' in json.dumps(seen[0][1]) and 'erin@northwind.example' in json.dumps(seen[1][1])
    assert 'erin@northwind.example' not in json.dumps(seen[0][1])
    assert [s.get_review(r)['Stale'] for r in (a, b)] == [0, 0]


def test_an_aside_mail_is_not_redrafted():
    s, tid, ask, rid = asked()
    judged = lambda system, user, **k: json.dumps({'intent': 'reply_only', 'why': 'a thanks', 'title': 'Repair the export', 'summary': 'Gail says thanks.',
                                                   'thread': {'asks': [], 'aside': [{'mid': 0, 'why': 'a thanks'}]}})
    with mock.patch.object(ingest, '_spawn') as spawned:
        out = ingest.ingest_message(s, {'external_id': 'x17', 'channel': 'email', 'from_email': GAIL[0], 'from_name': GAIL[1], 'conversation_id': 'conv-9',
                                        'subject': 'RE: Export', 'body': 'Thanks!', 'sent_at': '2026-11-04 10:17:00'}, llm=judged)
    r = s.get_review(rid)
    assert out.get('task_id') == tid and (r['MessageId'], r['Stale']) == (ask, 0) and not spawned.called


def test_a_reply_with_a_merge_close_out_goes_to_the_ask():
    s, tid, ask, rid = asked()
    pr = s.add_message({'TaskId': tid, 'ExternalId': 'gh-7', 'Channel': 'github', 'SourceName': 'northwind/ledger', 'Subject': 'Fix the export',
                        'FromName': 'Ray Colton', 'FromEmail': RAY[0], 'SentAt': '2026-11-04 10:20:00', 'BodyText': 'Can you merge this?', 'Status': 'routed'})
    last = line(s, tid, 21, GAIL, 'Thanks!', aside=True)
    s.update_review_message(rid, last); s.set_review_answers(rid, pr)
    co = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'approved', 'DraftText': json.dumps({'action': 'merge_pr', 'repo': 'northwind/ledger', 'number': 7})})
    assert verdicts._carried(s, s.get_review(co), s.get_review(rid))
    from taskuary import github
    with mock.patch('taskuary.ci._conn', lambda st: {'Secret': 'x'}), mock.patch.object(github, 'comment_issue', return_value='u') as say:
        out = verdicts._post_with_closeout(s, s.get_review(co), s.get_review(rid), '', 'owner')
    assert out['ok'] and say.called and s.get_message(pr)['Status'] == 'sent'


def chat_asked(revision=False):
    from taskuary import operations
    s = MemoryStore(); tid = s.create_task({'Title': 'Repair the export', 'Kind': 'task', 'Status': 'open', 'Source': 'whatsapp'}, 'router')
    add = lambda i, who, body, aside=False: (lambda mid: s.add_route(mid, tid, 'attach', 1.0, 'triage', [], 'triage',
                                                                      verdict=ASIDE if aside else {'intent': 'reply_only', 'why': 'asks'}) and mid)(
        s.add_message({'TaskId': tid, 'ExternalId': f'w{i}', 'Channel': 'whatsapp', 'SourceName': 'alex', 'FromName': who[1], 'FromEmail': who[0],
                       'SentAt': f'2026-11-04 11:{i:02d}:00', 'BodyText': body, 'Status': 'routed'}))
    ask = add(1, RAY, 'Can you repair the export?')
    rid = s.add_review({'TaskId': tid, 'MessageId': ask, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Done.',
                        **({'ContextRevision': operations.message_revision(s, tid)} if revision else {})})
    return s, tid, ask, rid, add


def test_a_thanks_with_no_thread_to_measure_by_moves_nothing():
    for rev in (False, True):
        s, tid, ask, rid, add = chat_asked(rev); add(2, GAIL, 'Thanks!', aside=True)
        assert verdicts._own_lines(s, s.get_review(rid)) is None
        assert verdicts.context_moved(s, s.get_review(rid))[0] is False, rev
        real = add(3, RAY, 'And September?')
        moved, latest = verdicts.context_moved(s, s.get_review(rid))
        assert moved and latest['MessageId'] == real, rev
    # ...and a draft pinned to the thanks it last saw (MessageId) while answering the ask is not moved by the older ask
    s, tid, ask, rid, add = chat_asked(); thanks = add(2, GAIL, 'Thanks!', aside=True)
    s.update_review_message(rid, thanks); s.set_review_answers(rid, ask)
    assert verdicts.context_moved(s, s.get_review(rid))[0] is False
    assert verdicts.context_moved(s, s.get_review(rid) | {'MessageId': ask})[0] is False
    real = add(3, RAY, 'And September?')
    assert verdicts.context_moved(s, s.get_review(rid)) == (True, s.get_message(real))


def test_an_aside_mail_opens_no_new_draft():
    s = MemoryStore(); tid = s.create_task({'Title': 'Repair the export', 'Kind': 'task', 'Status': 'open', 'Source': 'email'}, 'router')
    line(s, tid, 11, RAY, 'Can you repair the export?')
    judged = lambda system, user, **k: json.dumps({'intent': 'reply_only', 'why': 'a thanks', 'title': 'Repair the export', 'summary': 'Gail says thanks.',
                                                   'thread': {'asks': [], 'aside': [{'mid': 0, 'why': 'a thanks'}]}})
    with mock.patch.object(ingest, '_spawn') as spawned:
        out = ingest.ingest_message(s, {'external_id': 'x18', 'channel': 'email', 'from_email': GAIL[0], 'from_name': GAIL[1], 'conversation_id': 'conv-9',
                                        'subject': 'RE: Export', 'body': 'Thanks!', 'sent_at': '2026-11-04 10:18:00'}, llm=judged)
    assert out.get('task_id') == tid and s.pending_review(tid) is None and not spawned.called
