"""The agent decides who a reply goes to (the owner, 2026-11-06: "the agent decides who needs to know what you are responding. if it's
sensitive only to that person and it tells the user that. it can also respond not to the last email on the thread if it thinks that's
next steps"). Its draft carries the envelope it chose - the sender alone, or who else is copied - and the mail it replies to, an earlier one
included; the card says why, and the prompt tells it to say so in its next steps. Invented people throughout.
"""
import json
from taskuary import general, selfclose, server, wrapup, agenttools
from taskuary.store import MemoryStore

RAY, GAIL, ERIN, PAULA = 'ray@northwind.example', 'gail@northwind.example', 'erin@northwind.example', 'paula@vendor.example'


def thread():
    "Ray asks about his own pay with Gail and Erin copied; Gail answers something else; Erin says thanks - three mails, one conversation."
    s = MemoryStore(); tid = s.create_task({'Title': 'Ray asks about his pay correction', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    rows = [(RAY, 'Ray Colton', 'My last check was short - can you look at my pay?', {'to': ['alex@northwind.example'], 'cc': [GAIL, ERIN]}),
            (GAIL, 'Gail Moreno', 'Also, is the team lunch still Friday?', {'to': ['alex@northwind.example', RAY], 'cc': [ERIN]}),
            (ERIN, 'Erin Blake', 'Thanks all!', {'to': ['alex@northwind.example'], 'cc': [RAY, GAIL]})]
    ids = [s.add_message({'TaskId': tid, 'ExternalId': f'e{i}', 'ConversationId': 'conv-1', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                          'Subject': 'Pay', 'FromName': n, 'FromEmail': a, 'SentAt': f'2026-11-06 09:0{i}:00', 'BodyText': b, 'Status': 'routed',
                          'RecipientsJson': json.dumps(r)}) for i, (a, n, b, r) in enumerate(rows)]
    return s, tid, ids


def test_left_alone_it_is_the_reply_all_it_always_was():
    s, tid, ids = thread()
    out = wrapup.agent_reply(s, tid, 'Thanks Erin.', 'assistant')
    env = s.review_envelope(out['review_id'])
    assert env['mode'] == 'reply_all' and env['to'][0] == ERIN and set(env['to'] + env['cc']) >= {RAY, GAIL}
    assert out['recipients'] == {'to': env['to'], 'cc': env['cc']}


def test_something_sensitive_goes_to_that_one_person_only_and_answers_their_earlier_mail():
    s, tid, ids = thread()
    out = wrapup.agent_reply(s, tid, 'Hi Ray - I found the short check and payroll is correcting it this week.', 'assistant',
                             answers=ids[0], only=True, why_to='his own pay - not for the people copied')
    assert out['ok'], out
    rv, env = s.get_review(out['review_id']), s.review_envelope(out['review_id'])
    assert (env['mode'], env['to'], env['cc']) == ('reply_to', [RAY], [])          # Ray alone, nobody copied
    assert rv['AnswersMid'] == ids[0] == rv['MessageId']                            # the mail it answers is its message: its person, channel, thread
    assert 'only to the sender: his own pay - not for the people copied' in rv['Reason']
    assert out['answers'] == ids[0] and out['recipients'] == {'to': [RAY], 'cc': []}


def test_it_picks_who_else_is_copied_and_says_who_was_not_on_the_thread():
    s, tid, ids = thread()
    out = wrapup.agent_reply(s, tid, 'Hi Gail - yes, Friday at noon.', 'assistant', answers=ids[1], cc=[f'Erin Blake <{ERIN}>', PAULA],
                             why_to='the caterer needs the time too')
    env, rv = s.review_envelope(out['review_id']), s.get_review(out['review_id'])
    assert env['to'][0] == GAIL and env['cc'] == [ERIN, PAULA]
    assert out['new_on_thread'] == [PAULA] and f'copies {PAULA}, not on this thread before' in rv['Reason']


# A REPLY'S `cc` ADDS TO THE THREAD'S (the card-tool design, 2026-11-27, the owner's OK): "reply, and copy Paula" dropped everyone already
# copied without a word. Who the thread copied stays on it; `only` is the one way to narrow, and with `cc` it is the sender and those alone
def test_a_cc_adds_to_the_threads_own_copies_and_the_card_names_them_all():
    s, tid, ids = thread()
    out = wrapup.agent_reply(s, tid, 'Hi Ray - payroll has it, and Paula will confirm.', 'assistant', answers=ids[0], cc=[PAULA])
    env = s.review_envelope(out['review_id'])
    assert env['to'][0] == RAY and set(env['cc']) == {GAIL, ERIN, PAULA}, env
    assert out['recipients'] == {'to': env['to'], 'cc': env['cc']}


def test_only_with_a_cc_is_the_sender_and_those_it_names_alone():
    s, tid, ids = thread()
    out = wrapup.agent_reply(s, tid, 'Hi Ray - Paula in payroll is on it.', 'assistant', answers=ids[0], only=True, cc=[PAULA])
    assert out['ok'], out
    env = s.review_envelope(out['review_id'])
    assert (env['to'], env['cc']) == ([RAY], [PAULA]), env


def test_contradictions_and_non_addresses_save_nothing():
    s, tid, ids = thread()
    bad = wrapup.agent_reply(s, tid, 'Hi Ray.', 'assistant', cc='finance team')
    assert bad == {'ok': False, 'why': 'finance team is not an email address - nothing was saved'}
    assert not s._rows("SELECT 1 FROM review WHERE TaskId=?", (tid,))


def test_the_send_goes_to_the_chosen_people_threaded_on_the_mail_it_answers():
    from taskuary import verdicts
    s, tid, ids = thread()
    rid = wrapup.agent_reply(s, tid, 'Hi Ray - payroll is correcting it.', 'assistant', answers=ids[0], only=True)['review_id']
    sent = {}
    def fake(store, msg, body, to=None, cc=None, attachments=None):
        sent.update(mid=msg['MessageId'], to=to, cc=cc); return {'ok': True}
    import taskuary.outbound as ob
    old, ob.reply_to_message = ob.reply_to_message, fake
    try: verdicts.decide(s, s.get_review(rid), 'approve', 'Hi Ray - payroll is correcting it.')
    finally: ob.reply_to_message = old
    assert sent == {'mid': ids[0], 'to': [RAY], 'cc': []}


def test_every_road_carries_the_choice_tool_endpoint_cli_and_the_marker():
    b = server.AgentReplyBody(task_id=1, only=True, cc=[RAY], why_to='w', answers=3)
    assert (b.only, b.cc, b.why_to, b.answers) == (True, [RAY], 'w', 3) and server.AgentReplyBody(task_id=1).cc is None
    props = agenttools.TOOLS['propose'][2]['properties']
    assert {'answers', 'only', 'cc', 'why_to'} <= set(props)
    import inspect, taskuary.cli as cli
    src = inspect.getsource(cli)
    assert "'--only'" in src and "'--cc'" in src and "'only': args.only, 'cc': args.cc, 'why_to': args.why_to" in src
    t = 'Done.\n[[TASKUARY-REPLY answers=#12 only=yes why="his own pay"]]Hi Ray - fixed.[[/TASKUARY-REPLY]]'
    assert selfclose.reply_who(t) == {'answers': 12, 'only': True, 'why_to': 'his own pay'}
    assert selfclose.reply_marker(t)[1] == 'Hi Ray - fixed.'
    assert selfclose.reply_who('[[TASKUARY-REPLY cc="a@x.example; b@y.example"]]Hi[[/TASKUARY-REPLY]]') == {'cc': ['a@x.example', 'b@y.example']}
    assert selfclose.reply_who('[[TASKUARY-REPLY]]Hi[[/TASKUARY-REPLY]]') == {} and selfclose.reply_marker('[[TASKUARY-REPLY]]Hi[[/TASKUARY-REPLY]]')[1] == 'Hi'


