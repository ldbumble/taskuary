"""Triage's offer is work an agent can do with what is connected, and it goes once its work is done (B25, the email walk 2026-10-29).

A colleague asked for one quarter's totals out of an expense tool the install had no connection to; triage offered "I can pull the
Q3 totals", and the agent the press started said there was no connection and apologised for the offer. Another task kept offering
"I can draft a reply" over the draft that already stood in Close out. Triage is now shown `connected_systems` and told an offer is
only what those reach; and a verdict says whether all its offer makes is the reply, so offer_of drops it once a reply is drafted -
read off the task's state, never the offer's words."""
import json
from unittest import mock

from taskuary import ingest, triage
from taskuary.store import MemoryStore

ME = 'alex@northwind.example'


def test_the_guide_ties_an_offer_to_the_connected_systems():
    g = ' '.join(triage.SHIPPED.split())
    assert 'reach the systems `connected_systems` names' in g and 'is not named there is no offer' in g
    assert '`connected_systems` - what this install can reach' in g
    assert '"offer_is_reply": false' in g and '**offer_is_reply**' in triage.OFFER     # rides with the offer bullet an older doc is given
    assert 'offer_is_reply' in triage.verdict_schema([], None, [], [])['schema']['properties']


def test_triage_is_shown_what_the_install_can_reach():
    seen = {}
    def llm(system, user, **k):
        seen['user'] = json.loads(user)
        return json.dumps({'intent': 'task', 'kind': 'task', 'why': 'w', 'title': 't', 'summary': 's', 'offer': None})
    triage.classify_intent({'from_email': 'gail@northwind.example', 'subject': 'Q3 totals', 'body': 'Can you send the Q3 totals?'},
                           llm=llm, connected=['Sage Intacct (intacct)'])
    assert seen['user']['connected_systems'] == ['Sage Intacct (intacct)']


def test_ingest_hands_triage_the_active_connections_only():
    s = MemoryStore()
    cid = next(c['ConnectorId'] for c in s.list_connectors() if c['Type'] == 'intacct')
    s.save_connector({'ConnectorId': cid, 'Active': 1}, 't')
    names = ingest.connected_systems(s)
    assert 'Sage Intacct (intacct)' in names
    assert not any('(quickbooks)' in n for n in names)                    # a card that is not switched on reaches nothing


def _task_with_offer(s, offer, is_reply):
    llm = lambda sy, u, **k: json.dumps({'intent': 'task', 'kind': 'task', 'why': 'w', 'title': 'Answer Gail', 'summary': 's',
                                         'sender_class': 'person', 'asks_owner': True, 'offer': offer, 'offer_is_reply': is_reply})
    with mock.patch('taskuary.ingest._spawn'):
        out = ingest.ingest_message(s, {'external_id': f'm-{offer[:5]}', 'channel': 'email', 'subject': 'Two things',
                                        'body': 'Could you look at this for me?', 'from_email': 'gail@northwind.example',
                                        'from_name': 'Gail Moreno', 'conversation_id': f'c-{offer[:5]}', 'sent_at': '2026-10-29 09:00',
                                        'source_name': ME}, llm=llm)
    return out['task_id']


def test_an_offer_that_only_drafts_the_reply_goes_once_a_reply_is_drafted():
    s = MemoryStore(); s.set_setting('owner_email', ME, 't')
    tid = _task_with_offer(s, 'I can draft a reply for you to send', True)
    assert ingest.offer_of(s, tid) == 'I can draft a reply for you to send'
    s.add_review({'TaskId': tid, 'Kind': 'reply', 'DraftText': 'Hi Gail, here it is.', 'Status': 'pending'})
    assert ingest.offer_of(s, tid) == ''


def test_an_offer_that_does_other_work_stays_beside_a_draft():
    s = MemoryStore(); s.set_setting('owner_email', ME, 't')
    tid = _task_with_offer(s, 'I can register you for the webinar', False)
    s.add_review({'TaskId': tid, 'Kind': 'reply', 'DraftText': 'Hi Gail, thanks.', 'Status': 'pending'})
    assert ingest.offer_of(s, tid) == 'I can register you for the webinar'
