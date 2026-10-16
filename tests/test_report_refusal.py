"""A run the agent could not do is a failed run - and the AGENT says so, not a phrase list.

A phrase list (`_blocked`: BLOCKED/REFUSED) used to read the answer for "rate limit", "unable to
fetch", "permission not granted". It missed the 31-line apology below once (2026-09-04), was patched
to trust the CLI's own refusal words, and still filed a real short report that MENTIONED a rate
limit as FAILED. The owner, 2026-10-11: "everything should be ai". AGENT_SYSTEM now asks the agent
to end a run it could not do with `VERDICT: failed: <why>`, and run_agent reads that one line.
"""
import unittest
from unittest import mock

from taskuary import reports
from taskuary.store import MemoryStore

# the 31-line apology that once filed as the morning report - now with the line the contract asks for
REAL_REFUSAL = """# Morning Report - GitHub Trending - 2026-09-04

## What happened

| Step | Tool | Result |
|---|---|---|
| Fetch `https://github.com/trending` | WebFetch | **Blocked** - permission not granted for WebFetch in this run |
| Fetch `https://github.com/trending?since=daily` (fallback URL) | WebFetch | **Blocked** - same permission error |
| Search for a mirror of today's trending list | WebSearch | **Blocked** - permission not granted for WebSearch |
| Look for a cached snapshot in the working dir `~/.taskuary/scratch` | Glob `**/*` | Empty - no files at all |
| Look for a stored snapshot in the agent memory dir | Glob `**/*.md` | Empty - no memory files exist |

## What is therefore missing

Everything the instruction asked for. No repository data was obtained, so this report contains:

- **No top-15 list** - no repository names, no owners, no links.
- **No descriptions** for any repo.
- **No language breakdown** (e.g. counts of Python / TypeScript / Rust / Go entries).
- **No star counts or star-gain deltas**, and therefore no comparison against the previous run.
- **No themes, notable projects, or standout trends** - any such summary would be invented.

Note: no prior run's data was available locally either, so even a "delta vs. last week" fallback
was not possible.

## To fix before the next run

1. **Grant WebFetch permission for `github.com`** in the scheduled run's tool policy.
2. **Grant WebSearch** as a secondary path, so the run can fall back to a mirror.
3. **Consider the API instead of HTML scraping**.
4. **Persist each run's top-15 to a snapshot file** so the next report has a baseline.
5. **Fail loudly at schedule level** if the run produces zero repositories twice in a row.

VERDICT: failed: WebFetch and WebSearch were not granted, so github.com could not be read.
"""

# what a REAL report of the same size and shape looks like - it must never be flagged
REAL_REPORT = """# Morning Report - GitHub Trending - 2026-09-04

## Top 15

| # | Repo | Language | Stars today |
|---|---|---|---|
| 1 | mattpocock/skills | TypeScript | +812 |
| 2 | openai/codex | Rust | +604 |
| 3 | microsoft/markitdown | Python | +588 |

## Themes

- Agent tooling keeps the top three, and all three are CLI-first rather than hosted.
- Rust continues to take systems work that used to be Go, though Go holds the infra tail.
- Two of the fifteen are pure documentation repositories, which is unusual for a Thursday.

## Notable

- `mattpocock/skills` is a skills catalogue, not a library, and that shape is new to the top ten.
- The Python entries are all data-extraction tools; none of them are frameworks.
- No entry today is an LLM wrapper, which is the first time that has been true this month.

## Languages

TypeScript 5, Python 4, Rust 3, Go 2, unspecified 1.

## Against the previous run

Eight of the fifteen carried over from yesterday; the seven new ones are all agent tooling.
"""


# a REAL short report whose subject is limits - the phrase list filed exactly this as FAILED
RATE_REPORT = """Vendor API usage, 2026-10-10

- Payworth: 41,200 of 50,000 calls (82%) - the rate limit resets at 00:00 UTC.
- Trainly: usage limit raised to 10,000/day last week; 3,100 used.
- Spendly: quota exceeded once at 14:02 and recovered within the minute."""


def _run(answer):
    cfg = {'type': 'agent', 'agent': 'coding', 'prompt': 'fetch the trending page', 'title': 'GitHub Trending', 'store': MemoryStore()}
    with mock.patch('taskuary.llm.make_cli_llm', return_value=lambda *a, **k: answer): return reports.run_agent(cfg)


class AgentSaysItFailedTests(unittest.TestCase):
    def test_the_contract_is_in_the_agents_instructions(self):
        self.assertIn(reports.FAILED_MARK, reports.AGENT_SYSTEM)

    def test_a_short_report_about_rate_limits_files_as_a_report(self):
        subject, body = _run(RATE_REPORT)
        self.assertIn('coding ran a prompt', subject)
        self.assertIn('rate limit resets', body)

    def test_the_agents_failure_line_makes_run_agent_raise(self):
        with self.assertRaises(RuntimeError) as e: _run(REAL_REFUSAL)
        self.assertIn('could not run this report', str(e.exception))
        self.assertIn('WebFetch and WebSearch were not granted', str(e.exception))

    def test_a_real_report_of_the_same_size_and_shape_is_left_alone(self):
        subject, body = _run(REAL_REPORT)
        self.assertIn('mattpocock/skills', body)

    def test_only_the_last_line_counts_and_it_is_stripped(self):
        quoted = f'# Report\n\nThe contract says to write {reports.FAILED_MARK} when blocked.\n\n- 3 rows'
        self.assertEqual(reports.agent_failed(quoted)[0], '')
        why, body = reports.agent_failed('partial notes\n**VERDICT: failed: the mailbox refused the login**')
        self.assertEqual((why, body), ('the mailbox refused the login', 'partial notes'))

    def test_the_phrase_lists_are_gone(self):
        for name in ('BLOCKED', 'REFUSED', '_blocked'): self.assertFalse(hasattr(reports, name), name)


if __name__ == '__main__':
    unittest.main()
