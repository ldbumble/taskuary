"""Trust their organisation (the owner, 2026-10-22: "hit trust domain and then all users from that domain are good"). A Teams
colleague from a sister organisation - another Microsoft tenant - read as a stranger: the directory lookup 404s outside the owner's
own tenant and nothing said the two were one company. One press now names the sender's organisation as the owner's: its mail
domain, and the Teams tenant it was learned with, from the chat's own member list when the line did not carry it."""
import json
from unittest import mock

import pytest

from taskuary import origin, senders
from taskuary.store import MemoryStore


def _task(s, **m):
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': m.get('Channel', 'email')}, 'router')
    s.add_message({'TaskId': t, 'Status': 'routed', **m}); return t


def test_trusting_a_mail_sender_s_organisation_trusts_everyone_at_that_domain():
    s = MemoryStore()
    t = _task(s, Channel='email', FromEmail='gail@partner.example')
    assert origin.of_task(s, t)[0] == 'stranger'
    assert senders.trust_org(s, t, 'owner') == {'domain': 'partner.example', 'tenant': ''}
    assert origin.of_task(s, t)[0] == 'trusted'
    later = _task(s, Channel='email', FromEmail='omar@partner.example')                 # a colleague of theirs, never seen
    assert origin.of_task(s, later)[0] == 'trusted'
    assert origin.of_task(s, _task(s, Channel='email', FromEmail='x@elsewhere.example'))[0] == 'stranger'


def test_a_public_mail_domain_is_never_one_organisation():
    s = MemoryStore(); t = _task(s, Channel='email', FromEmail='someone@gmail.com')
    with pytest.raises(ValueError, match='public mail service'): senders.trust_org(s, t, 'owner')
    assert senders.trusted_orgs(s) == [] and origin.of_task(s, t)[0] == 'stranger'


def test_a_teams_sender_from_another_tenant_is_placed_by_the_chat_s_members():
    s = MemoryStore()
    line = dict(Channel='teams', FromEmail='teams:aaaa-1', SourceName='alex@northwind.example', ConversationId='teams:19:room@thread.v2')
    t = _task(s, **line)
    member = {'tenant': 'tenant-sister', 'email': 'ethan@sister.example'}
    with mock.patch('taskuary.channels.teams_member', return_value=member) as ask:
        assert senders.trust_org(s, t, 'owner') == {'domain': 'sister.example', 'tenant': 'tenant-sister'}
        # a colleague of theirs in another chat, recorded with their tenant at ingest: trusted without asking anyone
        other = _task(s, **{**line, 'FromEmail': 'teams:bbbb-2', 'MailMetaJson': json.dumps({'tenant': 'tenant-sister'})})
        assert origin.of_task(s, other)[0] == 'trusted'
    assert ask.call_count == 1
