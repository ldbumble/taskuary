"""Urgent is triage's call, and Remind me is a word on the walk (the owner, 2026-09-25: "we should make urgent a
triage decision i think. remind me should be a walk button for both whatsapp/telegram and assistant").
"""
import json, unittest
from unittest import mock

from taskuary import concierge, ingest, messengers, remote_assistant as ra, triage
from taskuary.store import MemoryStore


def brain(intent, urgent, kind='task', seen=None):
    def llm(system, user, **k):
        if seen is not None: seen.append(system)
        out = {'intent': intent, 'why': 'the payroll file is due to the bank by noon today', 'title': 'Send the payroll file',
               'summary': 's', 'urgent': urgent}
        if intent == 'task': out['kind'] = kind
        return json.dumps(out)
    return llm


def mail(s, llm, conv='c1', subject='Payroll file for today'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': conv, 'channel': 'email', 'from_email': 'ray@northwind.example',
                                         'from_name': 'Ray Colton', 'conversation_id': conv, 'subject': subject,
                                         'body': 'Can you send the payroll file? The bank needs it by noon.', 'sent_at': '2026-09-25 09:00:00'}, llm=llm)


class TriageDecidesUrgentTests(unittest.TestCase):
    def test_the_prompt_asks_and_the_schema_binds(self):
        seen = []
        mail(MemoryStore(), brain('task', False, seen=seen))
        self.assertTrue(any('"urgent"' in s for s in seen), 'every triage prompt explains the field')
        self.assertIn('urgent', triage.verdict_schema()['schema']['required'])

    def test_an_urgent_ask_makes_an_urgent_task_saying_why(self):
        s = MemoryStore()
        out = mail(s, brain('task', True))
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Priority'], 'urgent')

    def test_not_urgent_is_not(self):
        s = MemoryStore()
        self.assertNotEqual(s.get_task(mail(s, brain('task', False))['task_id']).get('Priority'), 'urgent')

    def test_an_fyi_that_says_urgent_is_still_just_an_fyi(self):
        v = triage.classify_intent({'subject': 'URGENT newsletter', 'body': 'y', 'from_email': 'news@vendor.example'}, brain('fyi', True))
        self.assertEqual(v['intent'], 'fyi')
        self.assertNotIn('urgent', v)
        self.assertTrue(triage.classify_intent({'subject': 'x', 'body': 'y', 'from_email': 'a@b.example'}, brain('task', True))['urgent'])

    def test_a_follow_up_that_is_urgent_marks_the_task_it_lands_on(self):
        s = MemoryStore()
        first = mail(s, brain('task', False))
        tid = first['task_id']
        self.assertNotEqual(s.get_task(tid).get('Priority'), 'urgent')
        ingest._mark_urgent(s, tid, {'why': 'the bank closes at noon'}, 'triage')
        self.assertEqual(s.get_task(tid)['Priority'], 'urgent')
        self.assertIn('the bank closes at noon', s.list_comments(tid)[-1]['Body'])


class RemindMeOnTheWalkTests(unittest.TestCase):
    ITEM = {'key': 'processing:pi_1', 'kind': 'asked', 'lane': 'yours', 'tid': 7, 'mid': 3, 'ref': 'TQ-0007', 'title': 'Renew the domain'}

    def test_it_is_a_word_on_every_card_with_an_open_task(self):
        words = [c['verb'] for c in concierge.chips_for(MemoryStore(), self.ITEM)]
        self.assertIn('defer', words)
        self.assertEqual(concierge.CHIP_WORDS['defer'], 'Remind me')
        no_task = [c['verb'] for c in concierge.chips_for(MemoryStore(), {**self.ITEM, 'tid': None})]
        self.assertNotIn('defer', no_task)

    def test_the_phone_asks_when_and_the_day_runs_the_task_pages_road(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Renew the domain', 'Kind': 'task', 'Status': 'open'}, 'owner')
        item = {**self.ITEM, 'tid': t}
        asked = ra.run_act(s, {'t': 'verb', 'verb': 'defer', 'key': item['key']}, item)
        self.assertIn('when?', asked)
        self.assertIn('Next week', asked)
        with mock.patch.object(concierge, 'surface', return_value={'say': 'All clear.', 'item': None}):
            done = ra.run_act(s, {'t': 'remind', 'tid': t, 'until': '1 week'}, item)
        self.assertTrue(s.get_task(t).get('RemindAt'))
        self.assertIn('Upcoming in Tasks', done)
        self.assertIn('Bring it back now', done)


class SelectorTests(unittest.TestCase):
    """On the owner's real pile "clear all fyis" (kind: fyi) cleared forty and "mark all the fyi read" (category: fyi)
    cleared none - fyi is a kind and a lane, not a category - and "mark them all read" named nothing at all."""
    PIPE = [{'key': 'a', 'lane': 'fyi', 'kind': 'fyi', 'category': 'info'}, {'key': 'b', 'lane': 'report', 'kind': 'report', 'category': 'report'},
            {'key': 'c', 'lane': 'blocked', 'kind': 'agent', 'category': ''}]

    def pick(self, sel):
        with mock.patch.object(concierge, '_pipe', return_value=self.PIPE):
            return [i['key'] for i in concierge.select_items(MemoryStore(), sel)]

    def test_a_set_word_matches_whichever_field_knows_it(self):
        for sel in ({'category': 'fyi'}, {'kind': 'fyi'}, {'lane': 'fyi'}):
            self.assertEqual(self.pick(sel), ['a'], sel)

    def test_everything_is_asked_for_by_name_and_never_sweeps_an_agent(self):
        self.assertEqual(self.pick({'everything': True}), ['a', 'b'])
        self.assertEqual(self.pick({}), [])


class SweepOnlyClearsTests(unittest.TestCase):
    def test_a_reason_in_the_words_writes_no_rule_and_silences_nobody(self):
        """R8: a phrase list decided a sweep was a standing rule; "from now on" is the model's to call as a tool."""
        s = MemoryStore()
        out = concierge.clear_matching(s, "skip all the vendor reports, that is taken care of from now on")
        self.assertEqual(set(out), {'cleared', 'titles', 'mid', 'words'})
        self.assertEqual(s.list_memories(active_only=True), [])
        self.assertIn('preference.exclude_sender', concierge.toolcatalog.PURPOSE['pipe.clear'] if hasattr(concierge, 'toolcatalog') else
                      __import__('taskuary.toolcatalog', fromlist=['PURPOSE']).PURPOSE['pipe.clear'])


if __name__ == '__main__': unittest.main()
