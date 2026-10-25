"""The reply writer is told who a copied mail is put to, by name, and how triage read it - and judges (2026-10-24). With the
owner only on Cc, a question one colleague put to another came back as the owner's draft asking that same question back. No gate
holds such a draft (the owner: "it should not be a hard coded rule, just normally it's not you unless it mentions you"), so
these pin the EVIDENCE and the wording the writer gets, never what a model writes."""
import json

import pytest

from taskuary import responder
from taskuary.store import MemoryStore

ME, ERIN, GAIL = 'alex@northwind.example', 'erin@northwind.example', 'gail@northwind.example'


@pytest.fixture
def s():
    value = MemoryStore()
    value.set_setting('owner_email', ME, 'test')
    yield value
    value.close()


def thread(s, body, to=(ERIN,), cc=(ME,), verdict=None):
    tid = s.create_task({'Title': 'Badge list', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': tid, 'ExternalId': f'graph:erin-{tid}', 'ConversationId': f'badges-{tid}', 'Channel': 'email',
                   'SourceName': ME, 'Subject': 'Badge list', 'FromEmail': ERIN, 'FromName': 'Erin Blake', 'BodyText': 'Sent the list.',
                   'SentAt': '2026-10-01 08:00:00', 'Status': 'routed', 'Direction': 'in'})
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'graph:gail-{tid}', 'ConversationId': f'badges-{tid}', 'Channel': 'email',
                         'SourceName': ME, 'Subject': 'RE: Badge list', 'FromEmail': GAIL, 'FromName': 'Gail Moreno', 'BodyText': body,
                         'SentAt': '2026-10-01 09:00:00', 'Status': 'routed', 'Direction': 'in',
                         'RecipientsJson': json.dumps({'to': list(to), 'cc': list(cc)})})
    if verdict: s.add_route(mid, tid, 'attach', 1.0, f"triage: {verdict['why']}", [], 'triage', verdict=verdict)
    return tid


def prompt(s, tid, said='NO REPLY'):
    got = {}
    def llm(system, user, **k): got.update(system=system, user=user); return said
    try: responder.draft_reply(s, tid, llm=llm)
    except responder.NoReply: pass
    return got['system'], got['user']


def test_a_copied_mail_tells_the_writer_who_it_is_to_by_name_and_how_triage_read_it(s):
    v = {'intent': 'fyi', 'why': 'Gail asks Erin whether the list is final; Alex is only copied'}
    system, user = prompt(s, thread(s, 'Erin, is this the final list? Can you confirm before Friday?', verdict=v))
    assert 'To: Erin Blake\n' in user and 'Cc: you\n' in user and 'You are: only copied (Cc)' in user
    assert ERIN not in user.split('From:')[1].split('\n', 1)[1]          # names on the To/Cc lines, never the addresses
    assert 'HOW TRIAGE READ THIS MESSAGE' in user and 'fyi - Gail asks Erin whether the list is final' in user
    assert 'only copied, a question in it is for the person on the To line' in system and 'NO REPLY' in system
    assert "Never hand someone else's question back" in system


def test_an_unknown_recipient_is_their_domain_never_their_address(s):
    _, user = prompt(s, thread(s, 'Can you confirm?', to=('paula@vendor.example',)))
    assert 'To: someone at vendor.example\n' in user and 'paula@' not in user


def test_named_on_the_cc_line_nothing_stops_the_reply(s):
    """The judgment cuts both ways: "Alex, can you..." is the owner's to answer, and nothing in code holds that draft."""
    v = {'intent': 'reply_only', 'why': 'Gail asks Alex directly to confirm the room'}
    tid = thread(s, 'Alex, can you confirm the room is booked?', verdict=v)
    system, user = prompt(s, tid, said='Yes - the room is booked for Friday.')
    assert 'Cc: you\n' in user and 'reply_only - Gail asks Alex directly' in user
    assert 'unless it names you' in system and 'answer it like any other' in system
    assert responder.draft_reply(s, tid, llm=lambda *a, **k: 'Yes - the room is booked for Friday.') == 'Yes - the room is booked for Friday.'


def test_on_the_to_line_the_writer_is_told_so(s):
    _, user = prompt(s, thread(s, 'Can you send the list?', to=(ME,), cc=(ERIN,)))
    assert 'To: you\n' in user and 'Cc: Erin Blake\n' in user and 'You are: on the To line' in user and 'HOW TRIAGE' not in user
