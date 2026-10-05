"""A name becomes an address from the owner's own mail - the people who wrote in AND the people the owner wrote to
(spec 2026-10-05-assistant-remembers-asks-design.md, section 5). One match fills it; several are offered; none is a '?'."""
import json
from unittest import mock

import pytest

from taskuary import lookups, people, slots
from taskuary.store import MemoryStore


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def sent(s, to, cc=(), n=1):
    for i in range(n):
        s.add_message({'ExternalId': f'out-{to[0]}-{i}-{len(cc)}', 'ConversationId': f'c-{to[0]}-{i}', 'Channel': 'email',
                       'SourceName': 'alex@northwind.example', 'FromName': 'You', 'FromEmail': 'alex@northwind.example',
                       'Subject': 'Numbers', 'BodyText': 'See attached.', 'SentAt': f'2026-10-0{1 + i} 09:00:00',
                       'Status': 'context', 'Direction': 'out', 'RecipientsJson': json.dumps({'to': list(to), 'cc': list(cc)})})


def wrote_in(s, name, email):
    s.add_message({'ExternalId': f'in-{email}', 'ConversationId': f'c-in-{email}', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                   'FromName': name, 'FromEmail': email, 'Subject': 'Hello', 'BodyText': 'Hi', 'SentAt': '2026-10-01 08:00:00', 'Status': 'routed'})


def test_a_name_only_the_owner_wrote_to_resolves(s):
    sent(s, ['gail.moreno@northwind.example'])
    assert people.resolve(s, 'Gail Moreno') == {'address': 'gail.moreno@northwind.example'}


def test_initial_and_surname_and_copies_count(s):
    sent(s, ['erin@northwind.example'], cc=['gmoreno@vendor.example'])
    assert people.resolve(s, 'Gail Moreno') == {'address': 'gmoreno@vendor.example'}


def test_someone_who_wrote_in_resolves_by_their_name(s):
    wrote_in(s, 'Paula Vance', 'pv@vendor.example')
    assert people.resolve(s, 'Paula Vance') == {'address': 'pv@vendor.example'}


def test_two_matches_are_offered_never_picked(s):
    sent(s, ['gail.moreno@northwind.example'], n=3); sent(s, ['gail.moreno@vendor.example'])
    out = people.resolve(s, 'Gail Moreno')
    assert 'address' not in out and out['candidates'][0] == 'gail.moreno@northwind.example' and len(out['candidates']) == 2


def test_nobody_is_nothing_and_an_address_passes_through(s):
    assert people.resolve(s, 'Omar Keller') == {}
    assert people.resolve(s, 'omar@northwind.example') == {'address': 'omar@northwind.example'}


def test_a_slot_named_by_a_person_takes_the_one_address(s):
    sent(s, ['gail.moreno@northwind.example'])
    tid = s.create_task({'Title': 'Tabs'}, 'owner')
    slots.add(s, tid, [{'to': 'Gail Moreno', 'about': 'tab 3'}, {'to': 'Omar Keller', 'about': 'tab 4'}], 'owner')
    outs = [i['out'] for i in slots.all_(s, tid)]
    assert outs[0]['to'] == 'gail.moreno@northwind.example' and outs[1]['to'] == 'Omar Keller' and not outs[1].get('candidates')


def test_a_slot_with_two_matches_keeps_the_name_and_lists_them(s):
    sent(s, ['gail.moreno@northwind.example']); sent(s, ['gail.moreno@vendor.example'])
    tid = s.create_task({'Title': 'Tabs'}, 'owner')
    slots.add(s, tid, [{'to': 'Gail Moreno'}], 'owner')
    out = slots.all_(s, tid)[0]['out']
    assert out['to'] == 'Gail Moreno' and len(out['candidates']) == 2
    md = s.checklist_markdown(tid)
    assert 'could be' in md and 'gail.moreno@northwind.example' in md and 'gail.moreno@vendor.example' in md


def test_sender_read_finds_someone_the_owner_only_wrote_to(s):
    sent(s, ['gail.moreno@northwind.example'], n=2)
    said = lookups.read(s, 'sender.read', {'who': 'Gail Moreno'})
    assert 'gail.moreno@northwind.example' in said and 'wrote to' in said


# ── final review: a part of a name is never enough to fill an address ───────────────────
def test_a_name_inside_another_name_is_offered_never_filled(s):
    sent(s, ['murray.jones@vendor.example'])
    assert people.resolve(s, 'Ray') == {'candidates': ['murray.jones@vendor.example']}
    wrote_in(s, 'Murray Jones', 'mj@vendor.example')
    assert 'address' not in people.resolve(s, 'Ray')


def test_a_whole_name_still_fills(s):
    sent(s, ['murray.jones@vendor.example'], n=2); sent(s, ['ray@northwind.example'])
    assert people.resolve(s, 'Ray') == {'address': 'ray@northwind.example'}


def test_the_sent_mail_is_read_once_until_new_mail_arrives(s):
    sent(s, ['gail.moreno@northwind.example'])
    people.resolve(s, 'Gail Moreno')
    with mock.patch.object(s, '_rows', side_effect=AssertionError('scanned again')):
        people.written_to(s)
    sent(s, ['erin@northwind.example'])
    assert 'erin@northwind.example' in people.written_to(s)


def test_a_new_store_never_sees_another_stores_sent_mail():
    """CI 2026-10-05: the cache was keyed by id(store); a closed store's id came back for the next one, and its
    recipients answered for it."""
    import gc
    for _ in range(200):
        a = MemoryStore(); sent(a, ['gail.moreno@northwind.example']); people.written_to(a); aid = id(a); a.close(); del a; gc.collect()
        b = MemoryStore(); sent(b, ['murray.jones@vendor.example'])
        try:
            if id(b) == aid:
                assert list(people.written_to(b)) == ['murray.jones@vendor.example']; return
        finally: b.close()
    pytest.skip('no id reuse to provoke here')
