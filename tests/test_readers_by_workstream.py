"""READERS GET THE ITEM'S WORKSTREAM (the design's S4, 2026-11-01): the event Advisor read the first 600 characters of SOUL.md and
JOB.md, so a second workstream's section never reached it; an agent read every hat's section on every task. Now the Advisor and the
agents read the item's own section whole, the others left out, and triage and the memory's reflection read every section first, cut.
Invented people only (CLAUDE.md)."""
import pytest
from taskuary import advisor, brief, triage, workstreams as W
from taskuary.store import MemoryStore
from taskuary.testing import Factory

OMAR = 'omar@ledger.example'


@pytest.fixture
def s():
    s = MemoryStore()
    s.save_doc('job', '## The job\n- **My role:** Director of finance systems at Northwind\n\n' + 'A long history block. ' * 80, 'owner')
    s.save_doc('soul', '# SOUL.md\nOwner: Alex Doyle, finance systems at Northwind.', 'owner')
    W.save(s, [{'name': 'Northwind finance systems', 'domains': ['northwind.example']}, {'name': 'Ledger app', 'people': [OMAR]}])
    W.write_section(s, 'ledger-app', '- A product Alex builds with Omar and Marcus; a tester\'s bug report is fixed in code, never answered by mail')
    W.write_section(s, 'northwind-finance-systems', '- Erin Blake is the manager; budget asks are answered the same day')
    return s


def _task(s, who):
    f = Factory(s); t = f.task(title='Export greyed'); f.message(task_id=t, channel='email', from_email=who); return t


def test_the_advisor_reads_the_items_own_section_whole_and_not_the_other_hats(s):
    t = _task(s, OMAR)
    line = advisor.owner_line(s, ('task', t))
    assert "This item is under Ledger app" in line and 'fixed in code, never answered by mail' in line
    assert 'budget asks are answered the same day' not in line
    assert "the owner's workstreams: Northwind finance systems, Ledger app" in line
    # ...and an item under no workstream reads the opening, as before
    plain = advisor.owner_line(s, ('task', _task(s, 'stranger@nowhere.example')))
    assert 'JOB.md (its opening)' in plain and 'This item is under' not in plain


def test_an_agent_reads_its_tasks_section_and_not_the_others(s):
    bg = brief.background(s, workstream='ledger-app')
    assert 'fixed in code, never answered by mail' in bg and 'budget asks are answered the same day' not in bg
    assert '- **Ledger app**' in bg and '- **Northwind finance systems**' in bg          # the index of every hat stays
    both = brief.background(s)
    assert 'fixed in code' in both and 'budget asks are answered' in both


def test_triage_and_the_reflection_read_every_section_first_so_a_cut_never_drops_a_hat(s):
    job = triage.job_doc(s, triage.JOB_CHARS)
    assert job.index('fixed in code') < job.index('A long history block')
    assert 'budget asks are answered the same day' in job and 'fixed in code' in job
    from taskuary import learn
    assert 'budget asks are answered the same day' in learn._job(s) and 'fixed in code' in learn._job(s)
