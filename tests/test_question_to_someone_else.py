"""A question put to someone ELSE by name is theirs, even with the owner on the To line beside them (2026-11-02). A sender wrote to
the owner and two colleagues, opening with one colleague's name - "<name>, let me know if you want to get on a call" - and triage
made it a reply task for the owner, the writer drafting "That works for me" to everyone. With the owner on To, triage had been told
only `addressed_to_you: "to"`: nothing tied the name the mail opened with to a person on it. No gate decides it (the owner: "never
use hard coded rules, let the AI see everything") - these pin the EVIDENCE and the guide's words, never what a model answers."""
import json
from unittest import mock

import pytest

from taskuary import ingest, responder, triage
from taskuary.store import MemoryStore

ME, GAIL, PAULA, ERIN = 'alex@northwind.example', 'gail@northwind.example', 'paula@northwind.example', 'erin@northwind.example'
ASK = 'Paula, let me know if you want to get on a call to review this.'


@pytest.fixture
def s():
    value = MemoryStore()
    value.set_setting('owner_email', ME, 'test')
    yield value
    value.close()


def say(s, frm, name, body, at, to=(), cc=(), tid=None):
    return s.add_message({'TaskId': tid, 'ExternalId': f'graph:{name}-{at}', 'ConversationId': 'docs', 'Channel': 'email', 'SourceName': ME,
                          'Subject': 'RE: Docs', 'FromEmail': frm, 'FromName': name, 'BodyText': body, 'SentAt': at, 'Status': 'routed',
                          'Direction': 'in', 'RecipientsJson': json.dumps({'to': list(to), 'cc': list(cc)})})


def mail(to, cc=(), body=ASK):
    return {'from_email': GAIL, 'from_name': 'Gail Moreno', 'channel': 'email', 'subject': 'RE: Docs', 'body': body, 'conversation_id': 'docs',
            'source_name': ME, 'to': list(to), 'cc': list(cc), 'sent_at': '2026-10-05 10:00:00'}


def thread_of(s, msg):
    seen = {}
    def judge(m, **kw): seen.update(kw.get('thread') or {}); return {'intent': 'fyi', 'why': 'x'}
    with mock.patch.object(ingest, 'classify_intent', side_effect=judge): ingest.judge(s, msg, llm=lambda *a, **k: '{}', mine={ME}, me={ME})
    return seen


def history(s):
    # Paula and Erin have written on the thread, so it knows their names; the sender once wrote to the owner by name
    say(s, PAULA, 'Paula Vance', 'Sent the file over.', '2026-10-01 09:00:00', to=(ME,))
    say(s, ERIN, 'Erin Blake', 'Looks fine to me.', '2026-10-01 10:00:00', to=(ME,))
    say(s, GAIL, 'Gail Moreno', 'Alex, I have reviewed the new file - two comments on the mapping.', '2026-10-02 09:00:00', to=(ME,))


def test_on_the_to_line_beside_others_triage_is_told_the_whole_line_by_name(s):
    history(s)
    t = thread_of(s, mail([ME, PAULA, 'omar@vendor.example'], [ERIN]))
    assert t['addressed_to'] == ['you', 'Paula Vance', 'someone at vendor.example']     # was nothing at all with the owner on To
    assert t['copied'] == ['Erin Blake']


def test_only_copied_the_to_line_still_names_who_its_you_means(s):
    history(s)
    t = thread_of(s, mail([PAULA], [ME]))
    assert t['addressed_to'] == ['Paula Vance'] and 'copied' not in t                    # the owner alone on Cc: addressed_to_you says it


def test_the_owner_alone_says_nothing_more_than_addressed_to_you(s):
    t = thread_of(s, mail([ME]))
    assert 'addressed_to' not in t and 'copied' not in t


def test_the_classifier_reads_the_names_beside_the_opening_line_and_never_an_address(s):
    history(s)
    seen = {}
    def llm(system, user, **kw): seen.update(sys=system, usr=json.loads(user)); return '{"intent": "fyi", "why": "Gail asks Paula"}'
    msg = mail([ME, PAULA], [ERIN])
    triage.classify_intent(msg, llm=llm, system='Judge it.', mine={ME}, thread=thread_of(s, msg))
    u = seen['usr']
    assert u['addressed_to_you'] == 'to' and u['addressed_to'] == ['you', 'Paula Vance'] and u['copied'] == ['Erin Blake']
    assert u['body'].startswith('Paula, let me know')
    assert triage.FIELDS['addressed_to'] in seen['sys'] and triage.FIELDS['copied'] in seen['sys']   # a doc that never names them
    assert not any(a in json.dumps(u) for a in (ME, PAULA, ERIN))


def test_the_guide_says_a_question_to_a_named_other_is_theirs_and_one_to_everyone_can_be_the_owners():
    for doc in (triage.INTENT_SYSTEM, triage.SHIPPED):
        assert 'Being on the To line is not being asked either' in doc
        assert 'asks THAT person, even with the owner on the To line beside them' in doc and 'unless the owner is asked too' in doc
        assert 'A question put to everyone on the mail' in doc and 'can be the owner\'s' in doc
        assert 'Read who a line is turned to from THIS message' in doc and 'never whose the question is' in doc
        assert '`copied` - the Cc line the same way' in doc


def test_the_writer_sees_the_to_line_by_name_and_is_told_a_named_question_is_not_yours(s):
    history(s)
    tid = s.create_task({'Title': 'Review call', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    say(s, GAIL, 'Gail Moreno', ASK, '2026-10-05 10:00:00', to=(ME, PAULA), cc=(ERIN,), tid=tid)
    got = {}
    def llm(system, user, **k): got.update(system=system, user=user); return 'NO REPLY'
    with pytest.raises(responder.NoReply): responder.draft_reply(s, tid, llm=llm)
    assert 'To: you, Paula Vance\n' in got['user'] and 'Cc: Erin Blake\n' in got['user'] and 'You are: on the To line' in got['user']
    assert 'The same holds on the To line beside others' in got['system'] and 'is theirs to answer, not yours' in got['system']


# ── a bare "<name>?" after the owner already answered (2026-11-02): the sender chased the colleague on Cc two minutes after the
# owner had sent their times, and it came out a reply task with "Yes, let's include <name>" drafted. The owner's reply WAS in the
# exchange, but the line being judged was already stored, so "last on the thread" was always its own sender.
NUDGE = 'Paula?'


def scheduling(s, tid=None):
    say(s, PAULA, 'Paula Vance', 'Here are the questions.', '2026-10-05 08:00:00', to=(ME, GAIL))
    say(s, GAIL, 'Gail Moreno', 'Alex, can we schedule a call today?', '2026-10-05 09:00:00', to=(ME,), cc=(PAULA,), tid=tid)
    s.add_message({'TaskId': tid, 'ExternalId': 'graph:mine', 'ConversationId': 'docs', 'Channel': 'email', 'SourceName': ME, 'Subject': 'RE: Docs',
                   'FromEmail': ME, 'FromName': 'You', 'BodyText': 'Gail, I can do today after 1pm. After 4 is better. What time works for you?',
                   'SentAt': '2026-10-05 09:30:00', 'Status': 'context', 'Direction': 'out'})
    return say(s, GAIL, 'Gail Moreno', NUDGE, '2026-10-05 09:32:00', to=(ME,), cc=(PAULA,), tid=tid)


def judged(mid, to=(ME,), cc=(PAULA,), body=NUDGE):
    return {**mail(to, cc, body=body), 'external_id': 'graph:Gail Moreno-2026-10-05 09:32:00', '_mid': mid, 'sent_at': '2026-10-05 09:32:00'}


def test_a_name_nudge_tells_triage_the_owner_answered_last_and_who_the_name_is(s):
    t = thread_of(s, judged(scheduling(s)))
    assert t['last_on_thread_is_you'] is True and t['copied'] == ['Paula Vance'] and 'addressed_to' not in t
    assert any('you' in l and 'After 4 is better' in l for l in t['exchange'])        # what the owner said, as their own line


def test_the_owner_last_with_nobody_else_on_the_thread_is_said_too(s):
    say(s, GAIL, 'Gail Moreno', 'Alex, can we talk today?', '2026-10-05 09:00:00', to=(ME,))
    s.add_message({'ExternalId': 'graph:mine', 'ConversationId': 'docs', 'Channel': 'email', 'SourceName': ME, 'Subject': 'RE: Docs',
                   'FromEmail': ME, 'FromName': 'You', 'BodyText': 'After 4 works.', 'SentAt': '2026-10-05 09:30:00', 'Direction': 'out'})
    mid = say(s, GAIL, 'Gail Moreno', 'Great.', '2026-10-05 09:32:00', to=(ME,))
    assert ingest.others_on_thread(s, judged(mid, cc=(), body='Great.'), mine={ME}) == {'last_on_thread': 'you', 'last_on_thread_is_you': True}


def test_the_guide_says_a_name_nudge_is_that_persons_and_an_answered_follow_up_is_not_the_owners():
    for doc in (triage.INTENT_SYSTEM, triage.SHIPPED):
        assert 'A nudge that is only a name' in doc and 'It never asks the owner to add, include or invite them' in doc
        assert 'When the owner has already answered' in doc and "is not the owner's to answer: fyi, `asks_owner` false" in doc
        assert "`last_on_thread_is_you` - true when that was the owner's own reply" in doc
    assert 'last_on_thread_is_you' in triage.FIELDS


def test_the_writer_reads_the_owners_last_reply_and_the_name_nudge_rule(s):
    tid = s.create_task({'Title': 'Call today', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    scheduling(s, tid)
    got = {}
    def llm(system, user, **k): got.update(system=system, user=user); return 'NO REPLY'
    with pytest.raises(responder.NoReply): responder.draft_reply(s, tid, llm=llm)
    assert 'After 4 is better' in got['user'] and 'Cc: Paula Vance\n' in got['user']
    assert 'A nudge that is only a name ("Paula?") asks that person to answer' in got['system']
    assert 'never asks you to add or include them' in got['system'] and 'Read your own last reply' in got['system']
