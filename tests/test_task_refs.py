"""A task number is any width: TQ-0796 is written with padding, TQ-10000 with none to spare, and a person
types TQ-796 (the owner, 2026-09-28: "what about task numbers, leading zeros or more than 4 digits?")."""
from taskuary import channels, digest
from taskuary.store import MemoryStore, task_ref


def test_a_ref_is_padded_to_four_and_grows_past_it():
    assert (task_ref(7), task_ref(796), task_ref(10000)) == ('TQ-0007', 'TQ-0796', 'TQ-10000')


def test_search_finds_a_task_by_its_ref_with_or_without_the_padding():
    s = MemoryStore()
    tid = [s.create_task({'Title': f'job {i}', 'Kind': 'general', 'Status': 'open'}, 'o') for i in range(3)][1]
    for q in ('TQ-0002', 'TQ-2', 'tq-00002', 'TQ2'):
        assert [t['TaskId'] for t in s.list_tasks(q=q)] == [tid], q
    assert s.list_tasks(q='TQ-9') == []


def test_the_coders_own_pull_request_is_skipped_at_any_width():
    # past TQ-9999 a four-digit pattern stopped recognising the coder's own PRs, and the poll took them in as new work
    assert channels.TQ_ISSUE.match('[TQ-0796] Fix the export') and channels.TQ_ISSUE.match('[TQ-10000] Fix the export')
    assert not channels.TQ_ISSUE.match('Fix TQ-0796')


def test_the_brief_links_a_five_digit_ref():
    assert 'task=10000' in digest._linked('- TQ-10000 waits on you')
    assert 'task=796' in digest._linked('- TQ-0796 waits on you')
