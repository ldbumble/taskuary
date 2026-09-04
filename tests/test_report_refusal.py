"""A refused TOOL is a failed run, however long and however well laid out the excuse is.

`_blocked` used to trust "short AND shapeless": a run that never reached its source was assumed
to answer briefly, so a long or structured answer was never second-guessed. A capable agent does
not fail briefly. Asked for a report it could not gather, Claude returned a 31-line document -
headings, a table whose every Result cell read "Blocked - permission not granted", a "What is
therefore missing" section and five numbered recommendations. Both halves of the guard passed it,
so the apology filed as the morning report and triage sent it on as work (the owner, 2026-09-04:
"the ai task said it fixed this, but it's not fixed").

The body below is the real one from that run, trimmed and with the owner's path made generic.
"""
import unittest

from taskuary import reports

# 31 lines: over REPORT_LINES, and _outline() finds both the headings and the table columns
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


class RefusedToolIsAFailedRunTests(unittest.TestCase):
    def test_the_real_refusal_that_filed_as_a_report_is_now_a_failed_run(self):
        self.assertGreater(len(REAL_REFUSAL.splitlines()), reports.REPORT_LINES)   # long...
        self.assertTrue(reports._outline(REAL_REFUSAL))                            # ...and structured
        self.assertEqual(reports._blocked(REAL_REFUSAL), 'permission not granted')

    def test_a_real_report_of_the_same_size_and_shape_is_left_alone(self):
        self.assertGreater(len(REAL_REPORT.splitlines()), reports.REPORT_LINES)
        self.assertTrue(reports._outline(REAL_REPORT))
        self.assertEqual(reports._blocked(REAL_REPORT), '')

    def test_every_refusal_wording_is_conclusive_at_any_length(self):
        """These are the CLI's own words, which no genuine report has reason to contain - so unlike
        the generic BLOCKED phrases they are not held to short-and-shapeless."""
        padding = '\n'.join(f'## Section {i}\n\nSome real looking prose here.' for i in range(12))
        for phrase in reports.REFUSED:
            body = f'# A Report\n\n{padding}\n\nThe run hit: {phrase} for WebFetch.\n'
            self.assertGreater(len(body.splitlines()), reports.REPORT_LINES, phrase)
            self.assertEqual(reports._blocked(body), phrase, phrase)

    def test_a_generic_inability_still_needs_to_be_short_and_shapeless(self):
        """"unable to fetch" is a phrase a real report may legitimately contain, so it keeps the
        old guard - otherwise a database report mentioning one unreachable row would be binned."""
        self.assertEqual(reports._blocked('unable to fetch the page'), 'unable to fetch')
        long_real = REAL_REPORT + '\n(One row was unable to fetch its upstream and is omitted.)\n'
        self.assertEqual(reports._blocked(long_real), '')

    def test_a_refusal_makes_run_agent_raise_instead_of_filing_a_document(self):
        """The point of the detector: run_agent RAISES, so the reports pipeline files a FAILED run
        and the owner sees FAILED rather than an apology dressed as the morning report."""
        from unittest import mock
        from taskuary.store import MemoryStore
        cfg = {'type': 'agent', 'agent': 'coder', 'prompt': 'fetch the trending page',
               'title': 'GitHub Trending', 'store': MemoryStore()}
        with mock.patch('taskuary.llm.make_cli_llm', return_value=lambda *a, **k: REAL_REFUSAL):
            with self.assertRaises(RuntimeError) as e:
                reports.run_agent(cfg)
        self.assertIn('could not run this report', str(e.exception))
        self.assertIn('permission not granted', str(e.exception))

    def test_the_same_agent_answering_a_real_report_is_filed_normally(self):
        from unittest import mock
        from taskuary.store import MemoryStore
        cfg = {'type': 'agent', 'agent': 'coder', 'prompt': 'fetch the trending page',
               'title': 'GitHub Trending', 'store': MemoryStore()}
        with mock.patch('taskuary.llm.make_cli_llm', return_value=lambda *a, **k: REAL_REPORT):
            subject, body = reports.run_agent(cfg)
        self.assertIn('coder ran a prompt', subject)
        self.assertIn('mattpocock/skills', body)


if __name__ == '__main__':
    unittest.main()
