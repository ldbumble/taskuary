"""THE CALENDAR AND A SHARE, SET UP LIKE AN EMAIL (the owner, 2026-11-08: "fix it like email or all other actions"). An invite that comes in is
read by the agent with the calendar, and its answer - Accept, Decline or Propose with the slot - is a card waiting on the owner's press; the
agent sets up a new meeting (who from the owner's mail, a free time, a Teams link) as an invite card with Send invite, never an .ics; a
dashboard it made is shared with one press on the person's own chat. Nothing reaches a calendar or a chat before the press. Invented people.
"""
import json
from unittest import mock

from taskuary import calwrite, ingest, server
from taskuary.store import MemoryStore
from test_agent_toolbox import c, hdr
from test_calendar_write import BUSY, ERIN, INVITE, Fake, arrive, outlook_store, send

GAIL = 'gail@northwind.example'


def call(tid, name, **a):
    r = c.post(f'/api/mcp?task={tid}', headers=hdr(tid), json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                                               'params': {'name': name, 'arguments': a}}).json()['result']
    return (r['content'][0]['text'] if r['isError'] else json.loads(r['content'][0]['text'])), r['isError']


def env(s, rid): return json.loads(s.get_review(rid)['Deliver'])


def test_the_agent_answers_an_invite_with_a_new_time_and_only_the_press_tells_the_calendar():
    s = outlook_store(); out = arrive(s); tid = out['task_id']
    g = Fake()
    with mock.patch.object(server, 'store', s), mock.patch.object(calwrite, 'busy', return_value=BUSY), mock.patch.object(calwrite, 'requests', g):
        got, bad = call(tid, 'answer_invite', answer='propose', note='Budget review runs then - would this work?')
        assert not bad and got['ok'] and 'Nothing reaches the calendar' in got['says'] and g.calls == []
        e = env(s, got['review'])
        assert (e['act'], e['to']) == ('propose', [ERIN]) and e['new_start'] and not calwrite.clashes(s, e['new_start'], e['new_end'], events=BUSY)
        assert s.get_review(got['review'])['DraftText'] == 'Budget review runs then - would this work?'
        # ...set up again as an accept: one card, the new one
        again, _ = call(tid, 'answer_invite', answer='accept')
        assert s.get_review(got['review'])['Status'] == 'rejected' and env(s, again['review'])['act'] == 'accept'
        assert send(s, again['review'])['ok'] and g.calls[0][1].endswith('/events/ev-1/accept')


def test_no_invite_waiting_is_said_to_the_agent():
    s = outlook_store(); tid = s.create_task({'Title': 'Q4 plan', 'Kind': 'general', 'Status': 'open'}, 'owner')
    with mock.patch.object(server, 'store', s):
        said, bad = call(tid, 'answer_invite', answer='accept')
    assert bad and 'no invite' in said


def test_a_meeting_the_agent_sets_up_is_an_invite_card_with_a_teams_link_sent_only_on_the_press():
    s = outlook_store(); tid = s.create_task({'Title': 'Plan the Q4 review', 'Kind': 'general', 'Status': 'open'}, 'owner')
    g = Fake()
    with mock.patch.object(server, 'store', s), mock.patch.object(calwrite, 'busy', return_value=BUSY), \
            mock.patch.object(calwrite, 'their_busy', return_value=([], [ERIN], [])), mock.patch.object(calwrite, 'requests', g):
        got, bad = call(tid, 'set_up_meeting', **{'with': [ERIN], 'title': 'Q4 review', 'minutes': 30, 'note': 'Walking the Q4 numbers.'})
        assert not bad and got['ok'] and got['link'] == 'Teams' and g.calls == []
        rv = s.get_review(got['review']); e = env(s, got['review'])
        assert rv['TaskId'] == tid and (e['act'], e['to'], e['link']) == ('schedule', [ERIN], 'Teams')
        assert not calwrite.clashes(s, e['start'], e['end'], events=BUSY)
        assert send(s, got['review'])['ok']
    body = json.loads(g.calls[0][2]['data'])
    assert body['isOnlineMeeting'] is True and body['onlineMeetingProvider'] == 'teamsForBusiness' and body['subject'] == 'Q4 review'


def test_a_name_nobody_can_place_comes_back_to_the_agent_never_guessed():
    s = outlook_store(); tid = s.create_task({'Title': 'Plan the Q4 review', 'Kind': 'general', 'Status': 'open'}, 'owner')
    with mock.patch.object(server, 'store', s):
        said, bad = call(tid, 'set_up_meeting', **{'with': ['Ray Colton'], 'title': 'Q4 review'})
    assert bad and 'Ray Colton' in said and not s._rows("SELECT * FROM review WHERE TaskId=?", (tid,))


def test_a_dashboard_is_shared_on_the_chat_the_person_wrote_on():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Vendor spend as a dashboard?', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': 'tm-1', 'ConversationId': 'teams:ops', 'Channel': 'teams', 'SourceName': 'Ops chat',
                   'FromName': 'Gail Moreno', 'FromEmail': GAIL, 'Subject': 'Vendor spend', 'BodyText': 'could we have vendor spend weekly?',
                   'SentAt': '2026-11-08 09:00:00', 'Status': 'routed'})
    sid = s.save_source({'Channel': 'report', 'Address': 'Vendor spend, weekly', 'Active': 1,
                         'ConfigJson': json.dumps({'type': 'dashboard', 'title': 'Vendor spend, weekly'})}, 'agent')
    with mock.patch.object(server, 'store', s):
        got, bad = call(tid, 'share', report=sid, to='Gail Moreno', text='Hi Gail - vendor spend is a dashboard now.')
        nope, bad2 = call(tid, 'share', report=9999, to='Gail Moreno', text='Hi')
    assert not bad and got['via'] == 'chat' and 'Nothing is sent' in got['says']
    rv = s.get_review(got['review'])
    assert rv['Status'] == 'pending' and rv['DraftText'].startswith('Hi Gail') and env(s, got['review'])['share'] == {
        'report': sid, 'title': 'Vendor spend, weekly', 'to': 'Gail Moreno'}
    assert bad2 and '9999' in nope


def test_an_invite_goes_to_the_agent_where_one_may_start_by_itself():
    s = outlook_store(); started = []
    with mock.patch.object(ingest, 'auto_start_ok', return_value=(True, '')), mock.patch.object(ingest, '_spawn', lambda *a: started.append(a)):
        out = arrive(s)
    t = s.get_task(out['task_id'])
    assert t['Kind'] == 'general'
    (fn, _, tid, job, deep), = [a for a in started if a[0] is ingest._auto_general]
    assert tid == t['TaskId'] and deep and 'answer_invite' in job and INVITE['subject'] in job


def test_with_no_agent_to_start_an_invite_stays_the_owners_reply():
    s = outlook_store()
    with mock.patch.object(ingest, '_spawn', lambda *a: None):
        out = arrive(s)
    assert s.get_task(out['task_id'])['Kind'] == 'reply' and calwrite.of_task(s, out['task_id'])['invite']


def test_a_guessed_invitee_goes_on_the_invite_and_the_card_says_so():
    # invites follow the emails' guess-and-mark rule (the owner, 2026-11-09): no address on record, the agent guesses and marks it
    s = outlook_store(); tid = s.create_task({'Title': 'Plan the Q4 review', 'Kind': 'general', 'Status': 'open'}, 'owner')
    guess = 'ray@northwind.example'
    with mock.patch.object(server, 'store', s), mock.patch.object(calwrite, 'busy', return_value=BUSY), \
            mock.patch.object(calwrite, 'their_busy', return_value=([], [guess], [])), mock.patch.object(calwrite, 'requests', Fake()):
        got, bad = call(tid, 'set_up_meeting', **{'with': [guess], 'title': 'Q4 review', 'guessed': [guess]})
    assert not bad and got['ok'] and 'guessed, check before Send: ' + guess in s.get_review(got['review'])['Reason']
    from taskuary import agenttools
    assert 'name it in `guessed`' in agenttools.TOOLS['set_up_meeting'][1] and 'never guess' not in agenttools.TOOLS['set_up_meeting'][1]
