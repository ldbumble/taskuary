"""THE MEMORY YARDSTICK IN CI (slice 0 of the memory redesign, 2026-10-25): the numbers tests/data/memory_baseline.json recorded before
the redesign, held for every slice after it - triage's priority at its boundaries, its intent on the same mail (it must not get worse),
whether a press count still moves the lit button, and the world's planted traits. A case that misses is listed with the slice that
fixes it, strictly: one that passes without being crossed off fails too."""
import json, re
import pytest
from tests import memory_cases as C

# what misses today, and which slice fixes it
KNOWN_PRIORITY = {
    'manager_next_week': 'slice 3: triage has no word for important yet',
    'cared_person_question': 'slice 3: triage has no word for important, and reads no people lines',
    'cared_topic': 'slice 3: triage has no word for important, and reads no "What you care about"',
}
KNOWN_SAME_DOMAIN = None      # slice 1 (2026-10-25): no press count lights a button any more


@pytest.fixture(scope='module')
def base(): return json.loads(C.BASELINE.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def now(): return {'priority': C.run_priority(), 'same_domain': C.same_domain()}


def test_the_baseline_is_written_and_whole(base):
    assert base['priority']['n'] == len(C.PRIORITY_CASES) and base['world']['traits'] == len(C.TRAITS)
    assert set(base['advisor_cases']) == {'right'}, 'the Advisor eval started from all right'
    assert not base['rail_advisor_cases'].get('miss') and not base['rail_advisor_cases'].get('noise')


@pytest.mark.parametrize('case', [c['id'] for c in C.PRIORITY_CASES])
def test_each_priority_boundary(now, case):
    r = next(x for x in now['priority'] if x['id'] == case)
    assert r['intent_got'] == r['intent'], f"{case}: intent {r['intent_got']} - the priority work must not move the intent"
    if case in KNOWN_PRIORITY:
        if r['got'] != r['want']: pytest.xfail(KNOWN_PRIORITY[case])
        pytest.fail(f'{case} lands right now ({r["got"]}) - cross it off KNOWN_PRIORITY')
    assert r['got'] == r['want'], f"{case}: landed {r['got']}, right is {r['want']}"


def test_triage_is_never_worse_than_the_baseline(base, now):
    pr = now['priority']
    assert sum(r['got'] == r['want'] for r in pr) >= base['priority']['right']
    assert sum(r['intent_got'] == r['intent'] for r in pr) >= base['priority']['intent_right']
    assert sum(not r['needs_missing'] for r in pr) >= base['priority']['needs_met']


def test_a_press_count_does_not_choose_the_button(now):
    sd = now['same_domain']
    if KNOWN_SAME_DOMAIN and sd['moved']: pytest.xfail(KNOWN_SAME_DOMAIN)
    assert 'habit' not in sd['by'] and sd['verbs'] == sd['bare'], sd


def test_the_world_plants_every_trait_in_what_the_owner_did():
    s, facts = C.world()
    assert all(len(facts[k]) >= 3 for k, *_ in C.TRAITS), {k: len(v) for k, v in facts.items()}
    # the repository is public: every address in the world is a reserved one (RFC 2606)
    addrs = {str(r['FromEmail'] or '').lower() for r in s._rows('SELECT FromEmail FROM message')}
    assert addrs and all(re.search(r'\.(example|test|invalid)$', a) for a in addrs), addrs
