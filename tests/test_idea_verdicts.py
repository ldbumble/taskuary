"""What the owner does with an Advisor idea teaches the next run (the owner, 2026-10-02: "feedback on assistant ideas even on
desktop does it teach it anything? we should have that"), Not ours on an idea asks how far like it does on mail, and a
meeting card is read and passed with Next alone."""
import unittest
from datetime import datetime, timedelta

from taskuary import assistant, concierge, remote_assistant
from taskuary.store import MemoryStore


def ago(**kw): return (datetime.now() - timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')


def _idea(s, key='idea:renewals', text='Three vendor renewals land in one week - put them on one calendar?'):
    return s.upsert_idea({'key': key, 'kind': 'idea', 'text': text, 'sig': 'a', 'action': {}}, ago(hours=2))


class HowFarTests(unittest.TestCase):
    ITEM = {'key': 'idea:7', 'kind': 'idea', 'idea': 7, 'title': 'Put the renewals on one calendar'}

    def test_not_ours_on_an_idea_asks_this_one_or_this_kind(self):
        alts = concierge.alts_for(MemoryStore(), self.ITEM, 'not_ours')
        self.assertEqual([(a['verb'], a['label']) for a in alts],
                         [('not_ours', 'Just this one'), ('not_ours_kind', 'No more ideas like this')])
        self.assertTrue(alts[0]['current'])

    def test_the_phone_asks_the_same_question(self):
        alts = concierge.alts_for(MemoryStore(), self.ITEM, 'not_ours')
        q, rows = remote_assistant.proposal_choices({'id': 'op1', 'verb': 'not_ours', 'key': 'idea:7', 'settles': True, 'alts': alts})
        self.assertEqual(q, 'How far?')
        self.assertEqual([label for label, _ in rows], ['Just this one', 'No more ideas like this', 'Cancel'])

    def test_no_more_like_this_belongs_to_ideas_only(self):
        mail = {'key': 'msg:3', 'kind': 'fyi', 'mid': 3, 'title': 'The export failed'}
        self.assertTrue(concierge.cannot(mail, 'not_ours_kind'))
        self.assertEqual(concierge.cannot(self.ITEM, 'not_ours_kind'), '')


class VerdictTests(unittest.TestCase):
    def test_every_verdict_reaches_the_advisors_prompt_newest_first(self):
        s = MemoryStore()
        a, b, c = _idea(s), _idea(s, 'idea:budget', 'The travel budget is 80% spent.'), _idea(s, 'idea:digest', 'Fold the two digests into one.')
        assistant.act(s, a['IdeaId'], 'task', 'owner')
        assistant.act(s, b['IdeaId'], 'dismiss_kind', 'owner')
        assistant.act(s, c['IdeaId'], 'dismiss', 'owner')
        self.assertEqual(s.get_idea(b['IdeaId'])['Status'], 'dismissed')
        said = assistant._said(s)
        lines = said[said.index('WHAT THE OWNER DID WITH YOUR IDEAS'):].splitlines()[1:]
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith('- turned it down (') and lines[0].endswith('Fold the two digests into one.'))
        self.assertTrue(lines[1].startswith('- turned it down - no more ideas like this (') and 'travel budget' in lines[1])
        self.assertTrue(lines[2].startswith('- took it up - made it a task (') and 'renewals' in lines[2])

    def test_the_log_is_capped_and_one_row_per_idea(self):
        s = MemoryStore(); i = _idea(s)
        for n in range(assistant.VERDICTS_CAP + 5):
            assistant.act(s, _idea(s, f'idea:n{n}', f'Idea {n}')['IdeaId'], 'dismiss', 'owner')
        assistant.act(s, i['IdeaId'], 'dismiss', 'owner'); assistant.act(s, i['IdeaId'], 'dismiss_kind', 'owner')
        v = assistant.verdicts(s)
        self.assertEqual(len(v), assistant.VERDICTS_CAP)
        self.assertEqual([r['verdict'] for r in v if r['key'] == 'idea:renewals'], ['dismiss_kind'])

    def test_another_reports_verdicts_stay_its_own(self):
        s = MemoryStore()
        other = _idea(s, 'report:99:idea:x', 'A line from another report.')
        assistant.act(s, other['IdeaId'], 'dismiss_kind', 'owner')
        self.assertNotIn('A line from another report', assistant._said(s))

    def test_snoozing_is_not_a_verdict(self):
        s = MemoryStore(); i = _idea(s)
        assistant.act(s, i['IdeaId'], 'snooze', 'owner', days=2)
        self.assertEqual(assistant.verdicts(s), [])


class MeetingTests(unittest.TestCase):
    def test_a_meeting_offers_next_alone(self):
        # the owner, 2026-10-02: "Meeting card should only have a next button like what it has on desktop no?"
        self.assertEqual(concierge.CHIPS['meeting'], ('next',))
        item = {'key': 'meeting:1', 'kind': 'meeting', 'title': 'Weekly sync with Northwind finance'}
        self.assertEqual([c['verb'] for c in concierge.chips_for(MemoryStore(), item)], ['next'])


if __name__ == '__main__': unittest.main()
