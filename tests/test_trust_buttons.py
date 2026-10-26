"""The held box's Trust buttons, and Slack's workspaces (the owner, 2026-10-26).

"we should have button on untrusted user to either trust user or trust domain and then we won't have issue again": the Agent work box
that says why nothing started carries "Trust <first name>" and the sender's organisation, worded for the channel - and none where there
is no organisation to name. "how will we handle in Slack where there is no domains?": a member of the owner's own Slack workspace is
known like Teams' own organisation; a Slack Connect sender from another workspace is judged per person, and their organisation button
trusts their workspace."""
import json
from unittest import mock

import pytest

from taskuary import channels, funnel, origin, senders
from taskuary.funnel import AUTO_OFF
from taskuary.store import MemoryStore

OWN, OTHER = 'T0NORTHWIND', 'T0VENDOR'
NOBODY = 'so no agent starts on their words by itself.'

def _store():
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't'); return s

def _held(s, ch='email', why='Gail Moreno is not on your domain and you have never written to them, ' + NOBODY, **m):
    "A task held for a new sender, as ingest leaves it: its line, and the route's hold sentence."
    t = s.create_task({'Title': 'Run the export', 'Kind': 'coding', 'Status': 'open', 'Assignee': 'agent:coder', 'Source': ch}, 'triage')
    mid = s.add_message({'TaskId': t, 'Channel': ch, 'Status': 'routed', 'BodyText': 'run the export', 'SourceName': 'alex@northwind.example', **m})
    s.add_route(mid, t, 'create', 0.0, f'triage: work · {AUTO_OFF} {why}', [], 'router')
    return t, mid

def _slack(team=None, **meta):
    return {'Channel': 'slack', 'FromName': 'U0GAIL', 'ConversationId': 'slack:C0CREW', 'SourceName': 'C0CREW',
            **({'MailMetaJson': json.dumps({'team': team, **meta})} if team else {})}

def _slack_msg(team=None, **meta):
    return {'channel': 'slack', 'from_name': 'U0GAIL', 'conversation_id': 'slack:C0CREW', 'source_name': 'C0CREW',
            **({'mail_meta': {'team': team, **meta}} if team else {})}

# ── SLACK: what the poller records ────────────────────────────────────────────────────────────────────────────────────
def test_slack_records_the_sender_s_workspace_and_whether_it_is_the_owner_s():
    m = {'ts': '1755700000.1', 'user': 'U0GAIL', 'text': 'x', 'team': OWN}
    assert channels.slack_msg({'Address': 'C0CREW'}, m, OWN)['mail_meta'] == {'team': OWN, 'internal': True}
    # a Slack Connect sender: their home workspace is user_team, whatever workspace the channel lives in - named when it was read
    guest = {**m, 'user_team': OTHER, 'user_profile': {'real_name': 'Gail  Moreno'}}
    assert channels.slack_msg({'Address': 'C0CREW'}, guest, OWN, {OTHER: 'Vendor Co'})['mail_meta'] == \
        {'team': OTHER, 'internal': False, 'team_name': 'Vendor Co', 'name': 'Gail Moreno'}
    # the connection's own workspace unknown (auth.test refused): no 'internal' - it is re-read on the way in (senders._slack_own)
    assert channels.slack_msg({'Address': 'C0CREW'}, m)['mail_meta'] == {'team': OWN}

def test_the_connection_s_own_workspace_is_asked_once_and_kept():
    s = MemoryStore(); c = s.get_connector_by_type('slack')
    with mock.patch.object(channels, '_slack', return_value={'ok': True, 'team_id': OWN, 'team': 'Northwind'}) as ask:
        assert channels.slack_own_team(s, c, 'xoxb') == OWN
        assert channels.slack_own_team(s, s.get_connector_by_type('slack'), 'xoxb') == OWN
    assert ask.call_count == 1 and json.loads(s.get_connector_by_type('slack')['ConfigJson'])['team_id'] == OWN

# ── SLACK: who is known ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_member_of_the_owner_s_own_workspace_is_known_without_any_history():
    s = _store()
    assert senders.known(s, _slack_msg(OWN, internal=True)) == (True, 'U0GAIL is in your own Slack workspace.')
    # recorded before the poller could ask auth.test: the connection's own workspace, as kept since, says it
    assert not senders.known(s, _slack_msg(OWN))[0]
    s.set_connector_config(s.get_connector_by_type('slack')['ConnectorId'], {'team_id': OWN})
    assert senders.known(s, _slack_msg(OWN))[0]

def test_a_slack_connect_sender_from_another_workspace_is_a_stranger_until_their_workspace_is_trusted():
    s = _store()
    assert not senders.known(s, _slack_msg(OTHER, internal=False))[0]
    t, _ = _held(s, 'slack', "U0GAIL wrote in Slack, and you haven't talked with them one-to-one or answered them there, " + NOBODY,
                 **_slack(OTHER, internal=False, team_name='Vendor Co', name='Gail Moreno'))
    assert senders.trust_offer(s, t) == {'person': 'Trust Gail', 'org': 'Trust Vendor Co'}
    assert senders.trust_org(s, t, 'owner') == {'domain': '', 'tenant': '', 'team': OTHER, 'name': 'Vendor Co'}
    assert senders.trusted_orgs(s) == [{'team': OTHER, 'name': 'Vendor Co'}]
    # a colleague of theirs, never seen: known by the workspace; a third workspace is still nobody's
    ray = {**_slack_msg(OTHER, internal=False), 'from_name': 'U0RAY'}
    assert senders.known(s, ray) == (True, 'U0RAY is in Vendor Co, a workspace you trust.')
    assert not senders.known(s, {**_slack_msg('T0ELSEWHERE', internal=False), 'from_name': 'U0OMAR'})[0]

def test_a_slack_line_recorded_before_its_workspace_was_is_judged_per_person_with_no_organisation_to_offer():
    s = _store(); t, _ = _held(s, 'slack', "U0GAIL wrote in Slack, and you haven't talked with them one-to-one or answered them there, " + NOBODY,
                              **_slack())
    assert senders.trust_offer(s, t) == {'person': 'Trust them', 'org': None}       # a Slack name is a user id - never "Trust U0GAIL"
    with pytest.raises(ValueError, match="can't tell which organisation"): senders.trust_org(s, t, 'owner')
    assert senders.trusted_orgs(s) == []

def test_an_unnamed_workspace_is_still_one_to_trust():
    s = _store(); t, _ = _held(s, 'slack', 'x ' + NOBODY, **_slack(OTHER, internal=False))
    assert senders.trust_offer(s, t)['org'] == 'Trust their Slack workspace'

# ── THE OFFER, PER CHANNEL ──────────────────────────────────────────────────────────────────────────────────────────────
def test_the_offer_is_worded_for_the_sender_s_organisation():
    s = _store()
    mail, _ = _held(s, FromEmail='gail@partner.example', FromName='Gail Moreno')
    assert senders.trust_offer(s, mail) == {'person': 'Trust Gail', 'org': 'Trust everyone at partner.example'}
    public, _ = _held(s, FromEmail='omar@gmail.com', FromName='Omar Keller')
    assert senders.trust_offer(s, public) == {'person': 'Trust Omar', 'org': None}        # nobody's organisation: no button that fails
    bare, _ = _held(s, FromEmail='ray@vendor.example', FromName='ray@vendor.example')
    assert senders.trust_offer(s, bare) == {'person': 'Trust them', 'org': 'Trust everyone at vendor.example'}
    teams = dict(Channel='teams', FromName='Marcus Reed', SourceName='alex@northwind.example', ConversationId='teams:19:crew@thread.v2')
    named, _ = _held(s, 'teams', 'x ' + NOBODY, **teams, FromEmail='marcus@sister.example', MailMetaJson=json.dumps({'tenant': 'tenant-sister'}))
    assert senders.trust_offer(s, named) == {'person': 'Trust Marcus', 'org': 'Trust everyone at sister.example'}
    with mock.patch('taskuary.channels.teams_member', return_value={}):
        placed, _ = _held(s, 'teams', 'x ' + NOBODY, **teams, FromEmail='teams:oid-9', MailMetaJson=json.dumps({'tenant': 'tenant-sister'}))
        assert senders.trust_offer(s, placed)['org'] == 'Trust their organisation on Teams'
        lost, _ = _held(s, 'teams', 'x ' + NOBODY, **teams, FromEmail='teams:oid-8')
        assert senders.trust_offer(s, lost)['org'] is None
    wa, _ = _held(s, 'whatsapp', 'x ' + NOBODY, FromName='Erin Blake', FromEmail='whatsapp:155', ConversationId='whatsapp:g')
    assert senders.trust_offer(s, wa) == {'person': 'Trust Erin', 'org': None}

def test_a_forged_from_offers_no_organisation():
    s = _store()
    t, _ = _held(s, FromEmail='gail@partner.example', FromName='Gail Moreno', MailMetaJson=json.dumps({'auth': 'fail'}))
    assert senders.trust_offer(s, t) == {'person': 'Trust Gail', 'org': None}

# ── THE BOX: its presses, and what a press leaves ───────────────────────────────────────────────────────────────────────
def test_the_held_box_carries_the_presses_and_a_press_lifts_the_hold_without_starting_anything():
    s = _store(); t, _ = _held(s, FromEmail='gail@partner.example', FromName='Gail Moreno')
    story = funnel.agent_story(s, t)
    assert story['kind'] == 'held' and story['line'].startswith('Waiting for you. Gail Moreno is not on your domain')
    assert story['trust'] == {'person': 'Trust Gail', 'org': 'Trust everyone at partner.example'}
    origin.raise_to(s, t, 'trusted', 'owner')                                           # Trust Gail
    story = funnel.agent_story(s, t)
    assert story['kind'] == 'idle' and 'trust' not in story and 'trusted now' in story['line'], story
    assert not s.get_dispatch(t) and not s.list_runs(t)                                 # trusting is not starting
    # ...and Gail is no stranger next time ("then we won't have issue again")
    ok, why = senders.known(s, {'channel': 'email', 'from_email': 'gail@partner.example', 'from_name': 'Gail Moreno',
                                'source_name': 'alex@northwind.example'})
    assert (ok, why) == (True, 'You vouched for Gail Moreno (gail@partner.example).')

def test_a_held_box_trusting_the_organisation_lifts_it_too():
    s = _store(); t, _ = _held(s, FromEmail='gail@partner.example', FromName='Gail Moreno')
    senders.trust_org(s, t, 'owner')
    assert funnel.agent_story(s, t)['kind'] == 'idle'

def test_the_task_page_s_origin_carries_the_same_words():
    from fastapi.testclient import TestClient
    from taskuary import server
    t, _ = _held(server.store, FromEmail='gail@partner.example', FromName='Gail Moreno')
    d = TestClient(server.app).get(f'/api/tasks/{t}').json()
    assert d['origin']['trust'] == {'person': 'Trust Gail', 'org': 'Trust everyone at partner.example'}
    assert d['agentStory']['trust'] == d['origin']['trust']
