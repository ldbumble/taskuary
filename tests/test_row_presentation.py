"""How a row reads - who, its state word, your move, when it comes back - is worked out ONCE, on the server
(funnel_presentation), and the phone and the desktop draw it. Each surface had its own copy and they drifted: the fix for
"why does fyi say my name??" (2026-10-13) reached the desktop only, and a drafted reply read "draft ready" on the phone."""
import re
from datetime import datetime, timedelta
from pathlib import Path

from taskuary import funnel_presentation as fp, remote_assistant as ra


def test_a_services_mail_names_the_service_not_the_name_it_borrowed():
    assert fp.who_of({'who': 'Alex', 'email': 'notifications@github.com', 'title': '[northwind/ledger] Run failed: ci', 'lane': 'fyi'}) == 'github'
    assert fp.who_of({'who': 'Card alerts', 'email': 'alerts@mail.bank.example', 'title': 'Statement ready', 'lane': 'fyi'}) == 'bank'
    assert fp.who_of({'who': 'Shop', 'email': 'noreply@shop.co.uk', 'title': 'Order', 'lane': 'fyi'}) == 'shop'
    assert fp.who_of({'who': 'Erin Blake', 'email': 'erin@northwind.example', 'title': 'Lunch', 'lane': 'fyi'}) == 'Erin Blake'   # a person stays one
    # an address shows its name part
    assert fp.who_of({'who': 'noreply-securityapp@vendor.example', 'email': 'noreply-securityapp@vendor.example', 'title': 'x', 'lane': 'fyi'}) == 'securityapp'
    assert fp.who_of({'kind': 'asked', 'who': 'erin@northwind.example', 'title': 'Q3 numbers'}) == 'erin'


def test_an_agents_row_names_the_agent_and_a_report_says_report():
    assert fp.who_of({'kind': 'agent', 'lane': 'stopped', 'who': 'You', 'agent': 'coding', 'title': 'Why so many emails'}) == 'coding'
    assert fp.who_of({'kind': 'asked', 'lane': 'asked', 'who': 'Gail Moreno', 'agent': 'coding', 'title': 'Budget'}) == 'Gail Moreno'   # not an agent's row
    assert fp.who_of({'kind': 'report', 'lane': 'report', 'who': 'AP ageing over 30 days', 'title': 'AP ageing over 30 days, weekly - 5 rows'}) == 'Report'
    assert fp.who_of({'kind': 'asked', 'title': 'Q3'}) == 'someone'


def test_the_state_word_is_the_lanes_except_an_agents_proposed_action():
    assert fp.state_of({'lane': 'approve', 'kind': 'review'}) == 'ready to close out'
    assert fp.state_of({'lane': 'approve', 'kind': 'action'}) == 'wants a yes'
    assert fp.state_of({'lane': 'approve', 'kind': 'action', 'closeout': 'merges the pull request'}) == 'ready to close out'
    assert fp.state_of({'lane': 'no-such-lane'}) == fp._LANE_WORDS['fyi']


def test_back_in_reads_forward_in_the_rails_words():
    now = datetime(2026, 10, 18, 9, 0)
    at = lambda m: (now + timedelta(minutes=m)).strftime('%Y-%m-%d %H:%M:%S')
    assert [fp.back_in(at(m), now) for m in (10, 45, 185, 3000, -5)] == ['in 30m', 'in 1h', 'in 3h', 'in 2d', '']
    assert fp.back_in(None, now) == '' and fp.back_in('not a date', now) == ''


def test_back_in_says_what_the_rails_railBack_says():
    # the rail counts down live in funnelPile.railBack; its test's cases hold this twin to the same words
    js = (Path(__file__).resolve().parents[1] / 'website' / 'test' / 'pileLevels.test.mjs').read_text(encoding='utf-8')
    cases = re.findall(r'railBack\(at\(([-\d *]+)\), now\), "([^"]*)"', js)
    assert len(cases) >= 4, cases
    now = datetime(2026, 10, 18, 9, 0)
    for expr, want in cases:
        m = eval(expr, {'__builtins__': {}})
        assert fp.back_in((now + timedelta(minutes=m)).strftime('%Y-%m-%d %H:%M:%S'), now) == want, (expr, want)


def test_the_move_line_is_one_function_the_phone_reads():
    assert ra.move_title is fp.move_of and ra.story_who is fp.story_who and ra.is_own is fp.is_own
    assert fp.move_of({'kind': 'review', 'lane': 'approve', 'who': 'Doyle, Alex at Northwind', 'draft': 'Yes'}) == 'reply to Alex Doyle'
    assert fp.move_of({'kind': 'review', 'lane': 'approve', 'who': 'Erin Blake'}) == 'no reply drafted yet'
    assert fp.move_of({'kind': 'agent', 'lane': 'working'}) == ''


def test_every_presented_card_carries_its_words_and_a_stale_one_is_redone():
    out = fp.present(None, {'items': [{'key': 'a', 'kind': 'fyi', 'lane': 'fyi', 'who': 'Alex', 'email': 'notifications@github.com', 'title': 'Run failed'},
                                      {'key': 'b', 'kind': 'asked', 'lane': 'asked', 'who': 'Erin Blake', 'title': 'Q3',
                                       'shows': {'who': 'stale', 'state': 'stale', 'move': ''}}]})
    a, b = out['items']
    assert a['shows'] == {'who': 'github', 'state': fp._LANE_WORDS['fyi'], 'move': ''}
    assert b['shows']['who'] == 'Erin Blake' and b['shows']['state'] == fp._LANE_WORDS['asked']
    # the words are a pure function of the card: the same card, the same stamp
    again = fp.present(None, {'items': [dict(a)]})['items'][0]
    assert again['presentation_revision'] == a['presentation_revision']


def test_the_phone_draws_the_servers_words():
    row = {'key': 'f', 'lane': 'fyi', 'kind': 'fyi', 'who': 'Alex', 'email': 'notifications@github.com', 'title': 'Run failed: ci', 'order_band': 4}
    assert '· github - Run failed: ci' in ra.who_wants_what([row])
    # ...and what the server set, when it set it
    assert '· the server - Run failed: ci (its word)' in ra.who_wants_what([row | {'shows': {'who': 'the server', 'state': 'its word', 'move': ''}}])


def test_for_later_says_back_in_once():
    soon = (datetime.now() + timedelta(minutes=200)).strftime('%Y-%m-%d %H:%M:%S')
    row = {'key': 'l', 'lane': 'asked', 'kind': 'asked', 'who': 'Gail Moreno', 'title': 'Budget tab', 'surfaced': True, 'put_down': True,
           'order_band': 2, 'back_at': soon}
    text = ra.who_wants_what([row])
    assert 'FOR LATER · 1' in text and '(back in 3h)' in text, text
