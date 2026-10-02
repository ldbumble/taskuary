"""Typed words in the Assistant, after the owner's rulings on the 2026-10-01 press audit:

1. typed words never start an agent without the owner's yes - the assistant proposes, he presses;
2. the assistant only offers or runs actions that are real buttons for the item on the table - "what is this about?"
   over a report came back as a "File it" card, and File it is not a button a report has;
3. a typed question reads the item on the table first, another task when the words name one, and a search when they
   ask to find one - and naming a task by its person and subject finds it ("Omar's Spendly lockout" matched nothing,
   because the search wanted the literal phrase);
4. an idea or a meeting has no thread and no task, and the model invented TQ refs for it - it is told so, and a
   reference that does not exist is never put in front of the owner.
"""
import json, unittest
from unittest import mock

from taskuary import concierge, funnel, lookups, operations, terminal
import tests.test_assistant_reactions as T
from tests.test_table_context import ask, call, scripted, two_tasks


def an_idea(s, text='The Payworth contract auto-renews on 15 Oct and nobody has reviewed the seat count - review it?'):
    s.upsert_idea({'key': 'idea:payworth', 'kind': 'idea', 'text': text, 'sig': 'p', 'action': {}}, T.ago(hours=1))
    return next(i for i in T.pile(s) if i.get('kind') == 'idea')


def a_report(s):
    s.save_source({'Channel': 'report', 'Address': 'Nightly AR aging', 'Owner': 'o', 'Active': 1,
                   'ConfigJson': json.dumps({'type': 'agent', 'title': 'Nightly AR aging'})}, 'o')
    m = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Nightly AR aging', 'Subject': 'Nightly AR aging - 214 open invoices',
                       'FromName': 'Nightly AR aging', 'SentAt': T.ago(1), 'BodyText': 'Open invoices: 214 (up from 198).', 'Status': 'feed'})
    s.add_route(m, None, 'feed', None, 'a report you set up', [], 'feed')
    return next(i for i in T.pile(s) if i.get('kind') == 'report')


def tasks(s): return len(s.list_tasks())


class TypedWordsNeverStartAnAgent(unittest.TestCase):
    def test_an_agent_asked_for_over_an_idea_is_a_card_the_owner_presses(self):
        s = T.store()
        s.upsert_agent('researcher', 'research', 'cli', json.dumps({'cmd': 'claude'}))
        item, before = an_idea(s), tasks(s)
        llm, _ = scripted('I would have it researched.\n' + call('regular_agent', text='review the Payworth seat count', **{'as': 'researcher'}))
        p = ask(s, 'what should I do next?', item['key'], llm).get('proposal')
        self.assertIsNotNone(p)
        self.assertFalse(p.get('auto'), 'typed words started an agent with no yes')
        self.assertEqual(tasks(s), before)

    def test_a_new_hand_off_with_a_named_checkout_still_waits_for_the_yes(self):
        s = T.store()
        s.save_doc('soul', '# SOUL.md\n## Repository map\n- **northwind/ledger**: the ledger app\n', 'owner')
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd_map': {'northwind/ledger': 'C:/x/ledger'}}))
        llm, _ = scripted('CALL: ' + json.dumps({'kind': 'task.create_from_text', 'params': {'kind': 'coding', 'text': 'fix the login crash', 'repo': 'ledger'}}))
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            p = concierge.say(s, 'start a coding agent on ledger to fix the login crash', llm=llm).get('proposal')
        self.assertIsNotNone(p)
        self.assertFalse(p.get('auto'))
        self.assertNotIn('Starting', p['say'])

    def test_continue_session_in_words_is_a_card_but_the_button_still_runs_at_once(self):
        self.assertIn('continue', concierge.AGENT_STARTS)
        self.assertIn('continue', concierge.AUTO)        # the chip under the composer is a press: it runs


class OnlyRealButtons(unittest.TestCase):
    def test_a_question_over_a_report_is_answered_not_filed(self):
        s = T.store(); item = a_report(s)
        llm, _ = scripted("It is your AR aging report: 214 open invoices, up from 198.\n" + call('message.file'))
        out = ask(s, 'what is this about?', item['key'], llm)
        self.assertIsNone(out.get('proposal'), 'File it is not a button a report has')
        self.assertIn('214 open invoices', out['say'])
        self.assertIsNone(concierge.open_proposal(s, concierge.general.dock_task(s, 'owner')[0]['TaskId']))

    def test_a_decision_that_is_not_a_button_falls_back_to_words(self):
        s = T.store(); item = a_report(s)
        llm, seen = scripted(call('not_ours'), 'It is the nightly AR aging report - 214 open invoices.')
        out = ask(s, 'what is this about?', item['key'], llm)
        self.assertIsNone(out.get('proposal'))
        self.assertIn('214 open invoices', out['say'])
        self.assertIn('not one of', seen[-1])

    def test_a_real_button_is_still_offered(self):
        s, a, b, item = two_tasks()
        item = dict(item)
        llm, _ = scripted(call('not_ours'))
        p = ask(s, 'not ours', item['key'], llm).get('proposal')
        self.assertIsNotNone(p, 'Not ours is a button on a mail that asks for something')


class ANamedTaskIsFound(unittest.TestCase):
    def test_the_timeline_finds_a_task_by_its_person_and_subject_words(self):
        s, a, b, item = two_tasks()
        hits = concierge.search_timeline(s, {'contains': "Omar's Spendly lockout"})
        self.assertTrue(hits, 'the literal phrase is not in the mail; its person and subject are')
        self.assertEqual(hits[0]['ref'], f'TQ-{a:04d}')
        with mock.patch.object(s, 'message_search', return_value=None):        # a store with no index scans the feed the same way
            self.assertEqual(concierge.search_timeline(s, {'contains': "Omar's Spendly lockout"})[0]['ref'], f'TQ-{a:04d}')
        self.assertEqual(concierge.search_timeline(s, {'contains': 'quarterly budget forecast'}), [])

    def test_tasks_list_finds_it_the_same_way(self):
        s, a, b, item = two_tasks()
        out = lookups.tasks_list(s, {'contains': 'Omar Spendly lockout'})
        self.assertTrue(out.startswith(f'TQ-{a:04d}'), out)

    def test_the_turn_is_told_to_read_the_table_first_then_a_named_task_then_search(self):
        s = T.store(); item = an_idea(s)
        llm, seen = scripted('The seat count.')
        ask(s, "what's left to do?", item['key'], llm)
        self.assertIn('never the whole pipe', seen[0])
        self.assertIn('ANOTHER task', seen[0])


if __name__ == '__main__': unittest.main()
