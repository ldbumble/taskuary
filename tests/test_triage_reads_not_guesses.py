"""Nothing in triage decides what a message MEANS from the words it uses (the owner, 2026-10-11: "Everything should be ai").

Three word lists survived the earlier sweeps, each misfiring on an ordinary mail:
  - heuristic_intent's _FYI/_ACT/_ASK: with no AI the "do not reply" footer under a real ask read as fyi
  - routing.ask_line's GREETING: "Hi-res scans ..." is not a hello, and "Dear team," titled nothing - triage's own title does
  - strip_boilerplate's _VALEDICTION: everything after a bare "Thanks," was cut, so a P.S. ask never reached the model
Parsing (mail-client stamps, quote heads, phone numbers, addresses) stays; meaning is the model's.
"""
import json, unittest

from taskuary import ingest, routing, triage
from taskuary.store import MemoryStore

FOOTER = ('Can you sign the Q3 vendor contract before Friday? Payworth needs it back.\n\n'
          'This is an automated notification - do not reply to this address.')
PS = ('The Q3 file for Northwind is attached for your review.\n\nThanks,\nErin Blake\n\n'
      'P.S. can you also send me the October numbers by Monday?')


class NoAiIsNotAVerdictTests(unittest.TestCase):
    def test_the_heuristic_is_gone(self):
        for name in ('heuristic_intent', '_ASK', '_ACT', '_FYI', '_VALEDICTION'):self.assertFalse(hasattr(triage, name), name)
        for name in ('GREETING', 'ask_line', '_ASKS', 'route'): self.assertFalse(hasattr(routing, name), name)

    def test_with_no_ai_classify_judges_nothing(self):
        v = triage.classify_intent({'subject': 'Contract', 'body': FOOTER})
        self.assertIsNone(v['intent']); self.assertNotIn('degraded', v)

    def test_a_do_not_reply_footer_with_no_ai_waits_for_triage_and_is_never_fyi(self):
        s = MemoryStore()
        out = ingest.ingest_message(s, {'external_id': 'f1', 'channel': 'email', 'from_email': 'erin@northwind.example',
                                        'subject': 'Q3 vendor contract', 'body': FOOTER}, llm=None)
        self.assertEqual((out['status'], out['task_id']), ('error', None))
        row = next(r for r in s.feed(limit=5) if r['MessageId'] == out['message_id'])
        self.assertNotEqual(row['MsgStatus'], 'filed')
        self.assertIn('awaiting AI triage', row['RouteReason'])

    def test_an_unusable_answer_carries_no_guessed_intent(self):
        v = triage.classify_intent({'subject': 'Contract', 'body': FOOTER}, llm=lambda *a, **k: 'not json')
        self.assertTrue(v['degraded']); self.assertIsNone(v['intent'])


class TitleIsTriagesTests(unittest.TestCase):
    CHAT = {'channel': 'teams', 'conversation_id': 'teams:19:ops', 'from_name': 'Gail Moreno', 'subject': 'Teams chat with Gail Moreno'}

    def test_a_chat_task_wears_triages_title_not_a_greeting_rule(self):
        s = MemoryStore()
        llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'task', 'why': 'an ask', 'title': 'Resend the Q3 file', 'summary': 'Resend it.'})
        out = ingest.ingest_message(s, {**self.CHAT, 'external_id': 't1',
                                        'body': 'Dear team,\nthe Q3 file is missing its last tab - can you resend it today?'}, llm=llm)
        self.assertEqual(s.get_task(out['task_id'])['Title'], 'Resend the Q3 file')

    def test_with_no_verdict_a_chat_title_is_its_first_line_whatever_word_opens_it(self):
        # GREETING skipped "Hi-res scans ..." as a hello and titled the task with the line under it
        f = routing.draft_task_fields({**self.CHAT, 'body': 'Hi-res scans of the Q3 file are missing\nthe export cut them'})
        self.assertEqual(f['title'], 'Hi-res scans of the q3 file are missing'.capitalize())

    def test_a_split_off_message_keeps_its_triaged_title(self):
        s = MemoryStore()
        titles = iter(['Fix the payroll export', 'Check the license for job code 325'])
        llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'task', 'why': 'x', 'title': next(titles), 'summary': 'x'})
        a = ingest.ingest_message(s, {**self.CHAT, 'conversation_id': 'c9', 'channel': 'email', 'subject': 'Chat', 'external_id': 's1',
                                      'body': 'Hello\nthe payroll export failed again'}, llm=llm)
        b = ingest.ingest_message(s, {**self.CHAT, 'conversation_id': 'c9', 'channel': 'email', 'subject': 'Chat', 'external_id': 's2',
                                      'body': 'Hello\nshould job code 325 have a license?'}, llm=llm)
        self.assertEqual(b['task_id'], a['task_id'])
        tid = ingest.split_message(s, b['message_id'], 'owner')
        self.assertEqual(s.get_task(tid)['Title'], 'Check the license for job code 325')


class SignOffIsNotTheEndTests(unittest.TestCase):
    def test_a_ps_after_thanks_survives_the_cleaner(self):
        self.assertIn('P.S. can you also send me the October numbers', triage.strip_boilerplate(PS))
        self.assertIn('P.S. can you also send me the October numbers', triage.own_words(PS))

    def test_a_ps_ask_reaches_the_triage_prompt(self):
        s, seen = MemoryStore(), {}
        def llm(sys_, usr_, **kw): seen['user'] = usr_; return json.dumps({'intent': 'task', 'why': 'x'})
        ingest.ingest_message(s, {'external_id': 'p1', 'channel': 'email', 'from_email': 'erin@northwind.example',
                                  'subject': 'Q3 file', 'body': PS}, llm=llm)
        self.assertIn('October numbers', seen['user'])

    def test_a_last_line_that_opens_with_a_contact_word_is_the_senders(self):
        body = 'The Q3 file for Northwind is attached for your review.\nAddress the two flagged rows before Friday, please.'
        self.assertEqual(triage.strip_boilerplate(body), body)
        # ...while a real contact line is still a shape, and goes
        self.assertEqual(triage.strip_boilerplate(body + '\nPhone: 555-0100\nray@northwind.example').strip(), body)

    def test_a_confidentiality_sentence_the_sender_wrote_stays(self):
        body = ('Please keep this between us for now.\nThis message is confidential until the board meets - '
                'can you draft the Q3 summary for Gail?')
        self.assertIn('draft the Q3 summary', triage.strip_boilerplate(body))

    def test_a_legal_footer_is_hidden_on_screen_and_read_whole_by_the_model(self):
        """The owner's 2026-09-23 ruling governs what is SHOWN - the footer triage named (its verdict's `wrapper`, never a phrase
        list: 2026-10-28) - and what triage reads is never cut by it."""
        notice = 'NOTICE: This message is confidential and intended solely for the addressee.'
        body = f'The Q3 file for Northwind is attached - can you approve it today?\n\n{notice}'
        shown = triage.read_text(body, wrapper=(notice,))
        self.assertNotIn('NOTICE', shown); self.assertIn('approve it today', shown); self.assertIn('NOTICE', triage.read_text(body))
        self.assertIn('NOTICE', triage.strip_boilerplate(body))
        s, seen = MemoryStore(), {}
        def llm(sys_, usr_, **kw): seen['user'] = usr_; return json.dumps({'intent': 'task', 'why': 'x'})
        ingest.ingest_message(s, {'external_id': 'n1', 'channel': 'email', 'from_email': 'erin@northwind.example',
                                  'subject': 'Q3 file', 'body': body}, llm=llm)
        self.assertIn('intended solely for the addressee', seen['user'])


if __name__ == '__main__':
    unittest.main()
