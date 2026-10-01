"""The item on the table is what every round of a turn is about - unless the owner's words are about something else.

The 2026-10-01 press audit asked the Assistant the same questions over every kind of card, and found three ways the
table slipped out from under a turn:
- a look-up round, and the retry after a miss, were sent without the item - asked "what is this about?" over one
  lockout, the model read a twin task, came back with nothing on the table, and described the twin;
- a tool called with no target ("rerun it" as report.rerun {}) was not aimed at the report on the table, and the retry
  - again with no table - picked another report by name;
- an answer about a DIFFERENT task was written onto this task's notes, where the next turn read it back as this task's.
And the model was never told which actions the card under its line offers, so "send it" over a draft could not be
matched to the button that sends it.
"""
import json, unittest
from unittest import mock

from taskuary import concierge, ingest, operations
import tests.test_assistant_reactions as T


def scripted(*answers):
    """A brain that answers in order and keeps every prompt it was sent."""
    seen, left = [], list(answers)
    def llm(system, user, **kw):
        seen.append(user)
        return left.pop(0) if left else 'Ok.'
    return llm, seen


def ask(s, text, key, llm):
    with mock.patch.object(T.terminal, 'live_sessions', return_value=[]):
        return concierge.say(s, text, key=key, llm=llm)


def two_tasks():
    s = T.store()
    with mock.patch.object(ingest, '_spawn'):
        a = T.arrive(s, subject='Spendly locked me out', body='The old password login stopped working.', who='Omar Keller',
                     email='omar@northwind.example', conv='c:a', hours=1, llm=T.brain('task', 'general'))
        b = T.arrive(s, subject='Spendly login locked', body='SSO change locked me out, not urgent.', who='Gail Moreno',
                     email='gail@northwind.example', conv='c:b', hours=2, llm=T.brain('task', 'general'))
    item = next(i for i in T.pile(s) if i.get('tid') == a['task_id'])
    return s, a['task_id'], b['task_id'], item


def call(kind, **params): return 'CALL: ' + json.dumps({'kind': kind, 'params': params})


class EveryRoundCarriesTheTable(unittest.TestCase):
    def test_a_look_up_round_still_names_the_item_on_the_table(self):
        s, a, b, item = two_tasks()
        llm, seen = scripted(call('task.read', ref=f'TQ-{b:04d}'), 'They are two different people.')
        ask(s, 'is this the same as the other lockout?', item['key'], llm)
        self.assertEqual(len(seen), 2)
        self.assertIn('Spendly locked me out', seen[1], 'the look-up round lost the item on the table')
        self.assertIn(f'TQ-{a:04d}', seen[1])

    def test_the_retry_after_a_miss_still_names_the_item_on_the_table(self):
        s, a, b, item = two_tasks()
        llm, seen = scripted(call('report.pause', title='nothing by this name'), 'Which report did you mean?')
        ask(s, 'pause it', item['key'], llm)
        self.assertEqual(len(seen), 2)
        self.assertIn('Spendly locked me out', seen[1], 'the retry round lost the item on the table')


class NoTargetMeansTheTable(unittest.TestCase):
    def _report(self):
        s = T.store()
        for title in ('Advisor', 'Nightly AR aging'):
            s.save_source({'Channel': 'report', 'Address': title, 'Owner': 'o', 'Active': 1,
                           'ConfigJson': json.dumps({'type': 'agent', 'title': title})}, 'o')
        sid = s.save_source({'Channel': 'report', 'Address': 'Payroll sync check', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Payroll sync check'})}, 'o')
        m = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Payroll sync check',
                           'Subject': 'Payroll sync check - FAILED', 'FromName': 'Payroll sync check', 'SentAt': T.ago(1),
                           'BodyText': 'error: timed out', 'Status': 'feed'})
        s.add_route(m, None, 'feed', None, 'a report you set up', [], 'feed')
        item = T.pile(s)[0]
        self.assertEqual(item['source_id'], sid)
        return s, sid, item

    def test_rerun_it_with_no_report_named_reruns_the_report_on_the_table(self):
        s, sid, item = self._report()
        llm, _ = scripted('Running it again.\n' + call('report.rerun'))
        p = ask(s, 'rerun it', item['key'], llm).get('proposal')
        self.assertIsNotNone(p, 'the report on the table is what "it" means')
        self.assertEqual((p['kind'], p['target']), ('report.rerun', sid))

    def test_a_named_report_still_wins_over_the_table(self):
        s, sid, item = self._report()
        llm, _ = scripted(call('report.rerun', title='Advisor'))
        p = ask(s, 'rerun the advisor', item['key'], llm)['proposal']
        self.assertNotEqual(p['target'], sid)


class AnAnswerAboutAnotherTaskStaysOffThisOne(unittest.TestCase):
    def _kept_on(self, s, tid):
        return ' '.join([c.get('Body') or '' for c in s.list_comments(tid)]
                        + [d.get('Body') or '' for d in operations.discussion(s, task_id=tid)])

    def test_a_turn_that_read_another_task_is_not_written_onto_this_one(self):
        s, a, b, item = two_tasks()
        llm, _ = scripted(call('task.read', ref=f'TQ-{b:04d}'), 'Gail wants a reset after the SSO change; not urgent.')
        out = ask(s, "what did Gail's lockout say?", item['key'], llm)
        self.assertIn('Gail wants a reset', out['say'])
        kept = self._kept_on(s, a)
        self.assertNotIn('Gail wants a reset', kept, "another task's answer became this task's notes")
        self.assertNotIn("what did Gail's lockout say?", kept)
        self.assertTrue(any('Gail wants a reset' in r for r in T.receipts(s)), 'the chat itself still has the answer')

    def test_a_turn_about_the_item_is_still_kept_on_it(self):
        s, a, b, item = two_tasks()
        llm, _ = scripted('Omar is locked out of the old password login.')
        ask(s, 'what is this about?', item['key'], llm)
        kept = self._kept_on(s, a)
        self.assertIn('Omar is locked out of the old password login.', kept)
        self.assertIn('what is this about?', kept)

    def test_reading_its_own_task_is_still_about_it(self):
        s, a, b, item = two_tasks()
        llm, _ = scripted(call('task.read', ref=f'TQ-{a:04d}'), 'Omar needs the old login back.')
        ask(s, 'summarize it', item['key'], llm)
        self.assertIn('Omar needs the old login back.', self._kept_on(s, a))


class TheModelIsToldTheActionsOnTheTable(unittest.TestCase):
    def test_the_prompt_names_each_button_on_the_card_and_the_tool_it_is(self):
        s, a, b, item = two_tasks()
        llm, seen = scripted('Ok.')
        ask(s, 'hm', item['key'], llm)
        chips = concierge.chips_for(s, item)
        self.assertTrue(chips)
        self.assertIn('ACTIONS FOR THE ITEM ON THE TABLE', seen[0])
        for c in chips: self.assertIn(f'"{c["label"]}"', seen[0])

    def test_a_drafts_send_button_is_named_as_approve(self):
        lines = concierge.table_actions(None, {'kind': 'review', 'key': 'review:1', 'rid': 1, 'tid': 1, 'lane': 'review'},
                                        chips=[{'verb': 'approve', 'label': 'Close out'}, {'verb': 'next', 'label': 'Next'}])
        self.assertIn('"Close out" = approve', lines)
        self.assertIn('sends the reply as it stands', lines)


if __name__ == '__main__': unittest.main()
