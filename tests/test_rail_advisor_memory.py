"""THE RAIL ADVISOR AND THE MEMORY, WITHOUT A MODEL (2026-10-26). A live A/B (tests/test_rail_advisor_memory_live.py) showed the memory
makes the clock Advisor raise what the owner asked for - and that a standing promise line ("you owe Ray the accruals") came back run
after run, in worlds with no word from Ray, under a fresh slug each time so the owner's No never stuck. What is pinned here: each memory
line reaches the prompt with its key and the heading says when a line is worth raising, an idea resting on one is keyed by it so a No
sticks, the receipts say which run and which idea used which line, and the scheduled Advisor runs on its own brain. Invented Northwind
people only; the brain is scripted (tests/rail_advisor_cases.py)."""
import json, re
from unittest import mock
import pytest
from taskuary import assistant, faults, learned_cut, memoryedit
from tests import rail_advisor_cases as C

RAY = 'You owe Ray Colton (ray@northwind.example) the vendor accruals before the month-end close'


@pytest.fixture(autouse=True)
def _scratch():
    with mock.patch.object(faults, 'scratch_home', lambda: True): yield


def world():
    s = C.store()
    memoryedit.remember(s, RAY, section='promises')
    memoryedit.remember(s, 'Bring up anything about the Q4 budget', section='bring')
    return s, None


def ray_mail(s):
    return s.add_message({'ConversationId': 'email:accruals', 'Channel': 'email', 'Subject': 'Vendor accruals', 'FromName': 'Ray Colton',
                          'FromEmail': 'ray@northwind.example', 'SentAt': C.at(h=3), 'Status': 'filed', 'SenderClass': 'person',
                          'BodyText': 'Can you get me the vendor accruals before close on Thursday?'})


def model(cite=True, mid=None, key=None):
    """A model that raises the Ray line every run under a NEW slug - as a real one did - citing the memory key it read beside the line."""
    n, seen = [0], []
    def extra(user):
        seen.append(user); n[0] += 1
        k = key or re.search(r'You owe Ray.*\[memory:([^\]]+)\]', user).group(1)
        return [{'key': f'idea:ray-accruals-{n[0]}', 'text': 'You owe Ray the vendor accruals before month-end.', 'why': 'the Promises line',
                 'section': 'ideas', 'mid': mid, 'memory': k if cite else None}]
    return extra, seen


def ray(lines): return [l for l in lines if 'Ray' in l['text']]


def test_each_memory_line_reaches_the_prompt_with_its_key_and_the_heading_says_when_it_is_worth_a_line():
    s, _ = world()
    extra, seen = model()
    C.run(s, extra)
    user = seen[-1]
    k = memoryedit._key(RAY)
    assert f'{RAY}  [memory:{k}]' in user
    head = user[user.index('WHAT YOU KNOW ABOUT HOW THE OWNER WORKS ('):][:1200]
    # the owner's "bring up" is an instruction, not background - and a standing fact needs something current behind it
    assert "What to bring up is the owner's OWN instruction" in head and 'never restate it as news' not in head
    assert 'ONLY when something else you were given in THIS check bears on it' in head and 'not that evidence' in head


def test_a_memory_idea_put_down_with_no_does_not_come_back_under_a_new_slug():
    s, _ = world()
    extra, _ = model()
    first = ray(C.run(s, extra))
    assert [l['key'] for l in first] == [f'idea:memory-{memoryedit._key(RAY)}']
    C.put_all_down(s, first)
    assert not ray(C.run(s, extra)), 'the No stuck: a new slug for the same memory line is the same idea'


def test_the_control_without_the_key_the_no_did_not_stick():
    """What the key fixes: a model that cites no memory line mints a slug per run, and the put-down line is back the next."""
    s, _ = world()
    extra, _ = model(cite=False)
    C.put_all_down(s, ray(C.run(s, extra)))
    assert ray(C.run(s, extra))


def test_a_line_about_a_mail_keeps_the_mails_key_so_the_mail_that_bears_on_a_put_down_fact_is_still_said():
    s, _ = world()
    extra, _ = model()
    C.put_all_down(s, ray(C.run(s, extra)))
    extra, _ = model(mid=ray_mail(s))
    got = ray(C.run(s, extra))
    assert got and not got[0]['key'].startswith('idea:memory-')


def test_a_key_the_document_does_not_hold_is_not_a_memory_key():
    s, _ = world()
    extra, _ = model(key='made-up-line')
    got = ray(C.run(s, extra))
    assert got and got[0]['key'] == 'idea:ray-accruals-1' and 'memory' not in (got[0].get('action') or {})


def test_the_receipts_say_which_run_and_which_idea_used_which_line():
    s, _ = world()
    extra, _ = model()
    line = ray(C.run(s, extra))[0]
    k = memoryedit._key(RAY)
    run = learned_cut.used(s, target='rail:advisor', reader='assistant')
    assert run and k in run[0]['keys']
    assert learned_cut.used(s, target=line['key'], reader='assistant')[0]['keys'] == [k]


def test_the_scheduled_advisor_runs_on_the_advisor_brain_and_other_reports_on_the_report_brain():
    from taskuary import reports
    srcs = [{'SourceId': 1, 'Address': 'Advisor', 'ConfigJson': json.dumps({'type': 'assistant'})},
            {'SourceId': 2, 'Address': 'AP aging', 'ConfigJson': json.dumps({'type': 'rest'})}]
    got = {}
    with mock.patch.object(reports, 'due_reports', return_value=srcs), \
         mock.patch('taskuary.llm.build_llm', side_effect=lambda store, *a, job=None, **kw: f'brain:{job}'), \
         mock.patch.object(reports, 'run_one', side_effect=lambda st, src, llm, *a: got.update({src['SourceId']: llm}) or {}):
        assert reports.run_due_reports(C.store()) == 2
    assert got == {1: 'brain:advisor', 2: 'brain:report'}
