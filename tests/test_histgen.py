"""Generate-from-history: Graph mail faked, LLM faked - the splice, the fallbacks and the
guardrails are what's under test.
"""
import unittest
from unittest import mock
from taskuary import histgen
from taskuary.store import MemoryStore

GUIDE = ('### What history shows gets answered\n- payroll and import failures, same day\n'
         '### What history shows is ignorable\n- vendor newsletters\n'
         '### Senders and domains that matter\n- corp.example colleagues')
STYLE = ('### Greeting & sign-off\n- "Hi <first>", signs "Best, {{owner_first}}"\n'
         '### Tone & length\n- two sentences, answer first\n'
         '### Characteristic phrasing\n- "on it"\n'
         '### How they push back or say no\n- offers the alternative in the same breath')

def fake_llm(system, user, max_tokens=0):
    return GUIDE if 'TRIAGE' in system else STYLE

def graph(sent, inbox, n=1):
    return mock.patch.object(histgen, '_graph_mail', return_value=(sent, inbox, n))

SENT = [{'id': 's1', 'subject': 'RE: PTO import', 'receivedDateTime': '2026-08-01T10:00:00Z',
         'conversationId': 'c1', 'body': {'content': 'Fixed - rerunning tonight.\nFrom: Sarah\nSent: old'}}]
INBOX = [{'id': 'i1', 'subject': 'PTO import failing', 'receivedDateTime': '2026-08-01T09:00:00Z',
          'conversationId': 'c1', 'from': {'emailAddress': {'address': 'sarah@corp.example'}}},
         {'id': 'i2', 'subject': 'Weekly vendor newsletter', 'receivedDateTime': '2026-08-02T09:00:00Z',
          'conversationId': 'c2', 'from': {'emailAddress': {'address': 'news@vendor.com'}}}]


class HistgenTests(unittest.TestCase):
    def test_cut_quoted(self):
        self.assertEqual(histgen.cut_quoted('Answer.\nFrom: Someone <a@b.c>\nold text'), 'Answer.')
        self.assertEqual(histgen.cut_quoted('Yes.\nOn Mon, Aug 3, Sarah wrote:\n> hi'), 'Yes.')
        self.assertEqual(histgen.cut_quoted('plain\nreply'), 'plain\nreply')

    def test_triage_generates_into_marker_block(self):
        s = MemoryStore()
        with graph(SENT, INBOX), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            detail = histgen.generate(s, 'triage')
        doc = s.get_doc('triage')
        self.assertIn('2 inbound + 1 sent', detail)
        self.assertIn(histgen.HIST_START, doc)
        self.assertIn('vendor newsletters', doc)
        self.assertIn('Classify one inbound work message', doc)   # the shipped prompt survives

    def test_regenerate_replaces_not_duplicates(self):
        s = MemoryStore()
        with graph(SENT, INBOX), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            histgen.generate(s, 'triage'); histgen.generate(s, 'triage')
        doc = s.get_doc('triage')
        self.assertEqual(doc.count(histgen.HIST_START), 1)
        self.assertEqual(doc.count('vendor newsletters'), 1)

    def test_style_falls_back_to_taskuary_record(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 't', 'Kind': 'reply', 'Status': 'open'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': 'x1', 'Channel': 'email', 'Subject': 'q',
                       'SentAt': '2026-08-20 10:00:00', 'Status': 'context',
                       'BodyText': 'Hi Sarah - yes, rerunning tonight and will confirm before payroll.'})
        with graph([], [], 0), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            detail = histgen.generate(s, 'style')
        self.assertIn('Taskuary itself has seen', detail)
        self.assertIn('Greeting & sign-off', s.get_doc('style'))
        self.assertEqual(s.get_doc('style').count(histgen.HIST_START), 1)   # template block reused

    def test_no_data_and_no_ai_are_loud(self):
        s = MemoryStore()
        with graph([], [], 0), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            with self.assertRaises(RuntimeError): histgen.generate(s, 'style')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            with self.assertRaises(RuntimeError): histgen.generate(s, 'triage')
        with self.assertRaises(ValueError): histgen.generate(s, 'soul')

    def test_broken_answer_never_lands(self):
        s = MemoryStore()
        before = s.get_doc('triage')
        with graph(SENT, INBOX), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: '<!-- evil -->'):
            with self.assertRaises(RuntimeError): histgen.generate(s, 'triage')
        self.assertEqual(s.get_doc('triage'), before)

    def test_style_doc_gate(self):
        from taskuary.responder import style_doc
        s = MemoryStore()
        self.assertEqual(style_doc(s), '')                 # untouched template: headers + placeholders only
        with graph(SENT, INBOX), mock.patch('taskuary.llm.build_llm', return_value=fake_llm):
            histgen.generate(s, 'style')
        out = style_doc(s)
        self.assertIn('Tone & length', out)
        self.assertNotIn('<!--', out)


if __name__ == '__main__':
    unittest.main()


class TopicRollUpTests(unittest.TestCase):
    """"Generate from history should see no responses on it." It already marked each mail
    ANSWERED or not - one line at a time. So a fortnight of resident-refund mail, each with a
    different resident in the subject and none of them ever answered, arrived as seventeen
    unrelated no-reply lines, and the prompt's own rule ("never a rule from a single
    conversation") forbade the model from saying the one thing the mailbox was shouting."""
    REFUNDS = [{'id': f'r{i}', 'subject': f'Re: Resident Refund Request - {name}',
                'receivedDateTime': f'2026-08-{10 + i:02d}T09:00:00Z', 'conversationId': f'rc{i}',
                'from': {'emailAddress': {'address': f'{name.split(",")[0].lower()}@regencyhealthrehab.com'}}}
               for i, name in enumerate(['Doe, Jane', 'PAYNE, MICHAEL', 'Watson, Lisa',
                                         'Foote, Marie Grace', 'Smith, Rosemary'])]

    def _payload(self, sent, inbox):
        seen = {}
        def llm(system, user, max_tokens=0):
            seen['user'] = user
            return GUIDE
        s = MemoryStore()
        with graph(sent, inbox), mock.patch('taskuary.llm.build_llm', return_value=llm):
            histgen.generate(s, 'triage')
        return seen['user'], histgen.STATUS['evidence']

    def test_a_recurring_never_answered_topic_is_counted_and_named(self):
        user, ev = self._payload(SENT, self.REFUNDS + INBOX)
        self.assertIn('TOPIC ROLL-UP', user)
        # one topic, five mails, none answered - and the changing resident is not part of it
        self.assertIn('"resident refund request": 5 mails, 0 answered', user)
        self.assertIn('never answered', user)
        self.assertNotIn('doe', user.split('INBOUND MAIL:')[0])   # not in the roll-up
        # and the receipts show the owner the same thing, so the guidance is inspectable
        self.assertTrue(any('never-answered first' in e for e in ev))

    def test_an_answered_topic_is_not_dressed_up_as_ignorable(self):
        """The signal has to cut both ways or it is not a signal."""
        answered = [{'id': 's9', 'subject': 'RE: Resident Refund Request - PAYNE, MICHAEL',
                     'receivedDateTime': '2026-08-11T10:00:00Z', 'conversationId': 'rc1',
                     'body': {'content': 'Approved, processing today.'}}]
        user, _ev = self._payload(SENT + answered, self.REFUNDS)
        self.assertIn('"resident refund request": 5 mails, 1 answered', user)
        self.assertNotIn('never answered', user)

    def test_a_one_off_subject_is_not_a_topic(self):
        """Three sightings is routine work; one is a conversation."""
        user, _ev = self._payload(SENT, INBOX)
        self.assertNotIn('TOPIC ROLL-UP', user)
