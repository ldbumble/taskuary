"""The sender's own words lead every prompt, and the chain they wrote on top of follows them.

Ray wrote one sentence on top of a forwarded chain. The cleaner reads the TAIL of a body - the
signature, the legal footer - so the whole 8,400-character chain went to the model as the message,
the ask was the first line of it, and the context budget cut the wrong end (TQ-0665). Now one door
(`triage.sender_body`) composes what a model is shown of one message: their words first, the chain
quoted underneath, and the cut taken out of the chain. Where the mailbox itself says where the ask
ends - Graph's `uniqueBody`, stored as OwnText - that is believed over any guess made from text.
"""
import json, unittest
from unittest import mock

from taskuary import channels, ingest, triage
from taskuary.store import MemoryStore

ASK = 'Alex,\n\nCan you send me the link on the 2027 budgets?\n\nThanks,\n\nRay Colton\nVP Marketing\n'
CHAIN = ('From: Barnes, Michael L. <m@northwind.example>\nSent: Thursday, September 17, 2026 2:07 PM\n'
         'To: Colton, Ray <b@northwind.example>\nSubject: Fw: 2027 Budgets\n\n'
         'The attached workbook replaces the one I sent Tuesday - the depreciation tab was wrong.\n')
MAIL = ASK + '\n' + CHAIN


class SenderBodyTests(unittest.TestCase):
    def test_their_words_lead_and_the_chain_follows_them_marked(self):
        body, cut = triage.sender_body(MAIL)
        self.assertTrue(body.startswith('Alex,'))
        self.assertIn('link on the 2027 budgets', body.split(triage.CHAIN_HEAD)[0])
        self.assertIn('depreciation tab was wrong', body)          # nothing is thrown away
        self.assertNotIn('Sent: Thursday', body)                   # the quoted header block is wrapper
        self.assertFalse(cut)

    def test_the_budget_cuts_the_chain_and_never_the_ask(self):
        body, cut = triage.sender_body(ASK + '\n' + CHAIN + ' '.join(f'w{k}' for k in range(4000)), budget=900)
        self.assertIn('link on the 2027 budgets', body)
        self.assertTrue(cut)
        self.assertLessEqual(len(body), 900)

    def test_a_message_with_no_chain_is_its_own_words_whole(self):
        plain = 'The payroll export failed again overnight - same KeyError as last week.'
        self.assertEqual(triage.sender_body(plain), (plain, False))

    def test_the_mailbox_saying_where_the_ask_ends_beats_guessing_at_it(self):
        """A forward whose chain opens on nothing this module recognises: no '>' run, no 'On ...
        wrote:', no From:/Sent: pair. Graph's uniqueBody knows anyway."""
        quiet = 'Please approve this today.\n\n===== 2027 Budgets =====\n' + 'ledger line\n' * 200
        blind, _ = triage.sender_body(quiet)
        self.assertIn('ledger line', blind)                         # unaided, the chain rides along
        told, _ = triage.sender_body(quiet, own='Please approve this today.')
        self.assertTrue(told.startswith('Please approve this today.'))
        self.assertIn(triage.CHAIN_HEAD, told)

    def test_a_uniquebody_that_is_the_whole_conversation_is_ignored(self):
        """Graph hands back the entire thread here often enough to be a known bug
        (microsoftgraph/msgraph-sdk-php#1576), so it is believed only where it is SHORTER."""
        body, _ = triage.sender_body(MAIL, own=MAIL + 'and more')
        self.assertNotIn('Sent: Thursday', body)
        self.assertEqual(body.split(triage.CHAIN_HEAD)[0].strip(), triage.own_words(MAIL).strip())

    def test_a_chain_the_thread_already_holds_is_not_sent_twice(self):
        known = triage.known_lines((CHAIN,))
        body, _ = triage.sender_body(MAIL, known=known)
        self.assertNotIn('depreciation tab', body)
        self.assertIn('link on the 2027 budgets', body)

    def test_split_own_hands_back_both_halves(self):
        own, chain = triage.split_own(MAIL)
        self.assertEqual(own, triage.own_words(MAIL))
        self.assertIn('depreciation tab was wrong', chain)


class GraphFieldTests(unittest.TestCase):
    def test_the_bodies_call_asks_for_uniquebody_and_the_listing_does_not(self):
        self.assertIn('uniqueBody', channels.MAIL_BODY_SELECT.split(','))
        self.assertNotIn('uniqueBody', channels.MAIL_LIST_SELECT.split(','))
        self.assertIn('uniqueBody', channels.MAIL_FULL_SELECT.split(','))

    def test_a_shorter_uniquebody_is_kept_and_a_missing_one_costs_nothing(self):
        m = {'body': {'content': '<p>Please approve.</p><blockquote>' + 'old news ' * 400 + '</blockquote>'},
             'uniqueBody': {'content': '<p>Please approve.</p>'}}
        self.assertEqual(channels._own(m), 'Please approve.')
        self.assertEqual(channels._own({'body': {'content': '<p>Please approve.</p>'}}), '')
        self.assertEqual(channels._own({'body': {'content': '<p>hi</p>'}, 'uniqueBody': {'content': '<p>hi</p>'}}), '')


class StoredAndReadTests(unittest.TestCase):
    def test_the_mailbox_answer_is_stored_beside_the_whole_body_and_read_back(self):
        s = MemoryStore()
        ingest.ingest_message(s, {'external_id': 'graph:1', 'channel': 'email', 'source_name': 'me@x.com',
                                  'subject': 'RE: 2027 Budgets', 'from_email': 'b@northwind.example', 'from_name': 'Ray Colton',
                                  'conversation_id': 'c1', 'sent_at': '2026-09-21 09:00:00',
                                  'body': MAIL, 'own_text': ASK})
        row = next(m for m in s.scan_messages() if m['Subject'] == 'RE: 2027 Budgets')
        stored = s.get_message(row['MessageId'])
        self.assertEqual(stored['BodyText'], MAIL, 'the panel still shows the real mail')
        self.assertEqual(stored['OwnText'], ASK)

    def test_the_exchange_leads_with_what_each_person_typed(self):
        s = MemoryStore()
        s.add_message({'ExternalId': 'g1', 'Channel': 'email', 'ConversationId': 'c9', 'Subject': '2027 Budgets',
                       'FromEmail': 'b@northwind.example', 'FromName': 'Ray Colton', 'SentAt': '2026-09-21 09:00:00',
                       'BodyText': MAIL, 'OwnText': ASK})
        line = ingest.exchange_lines(s, {'conversation_id': 'c9', 'subject': '2027 Budgets', 'sent_at': None})[0]
        self.assertLess(line.index('link on the 2027 budgets'), line.index('depreciation tab'))

    def test_the_judge_reads_the_ask_first(self):
        seen = {}
        def llm(sys_, usr_, **k):
            seen['usr'] = json.loads(usr_)
            return '{"intent": "task", "kind": "task", "why": "x", "title": "t", "summary": "s"}'
        triage.classify_intent({'from_email': 'b@northwind.example', 'subject': 'RE: 2027 Budgets',
                                'body': MAIL, 'own_text': ASK}, llm=llm)
        body = seen['usr']['body']
        self.assertTrue(body.startswith('Alex,'))
        self.assertLess(body.index('2027 budgets'), body.index(triage.CHAIN_HEAD))

    def test_the_exchange_says_what_it_carried_and_the_chain_is_not_paid_for_twice(self):
        """The words the exchange already shows the model are left out of the quoted chain under the
        message being judged - but only the ones it really shows: a message the budget dropped is
        nowhere else in the prompt, so its quoted copy has to stay."""
        s = MemoryStore()
        old = 'The depreciation tab in the October workbook is wrong and needs redoing before close.'
        for i, (who, text) in enumerate([('m@northwind.example', old), ('b@northwind.example', 'Any word on this?')]):
            s.add_message({'ExternalId': f'g{i}', 'Channel': 'email', 'ConversationId': 'c4', 'Subject': '2027 Budgets',
                           'FromEmail': who, 'SentAt': f'2026-09-2{i} 09:00:00', 'BodyText': text})
        carried = set()
        ingest.exchange_lines(s, {'conversation_id': 'c4', 'subject': '2027 Budgets', 'sent_at': None}, seen=carried)
        self.assertIn('Any word on this?', carried)
        quoting = 'Sending it today.\n\nFrom: Barnes <m@northwind.example>\nSent: Monday\n\n' + old
        self.assertNotIn('depreciation tab', triage.sender_body(quoting, known=carried)[0])
        self.assertIn('depreciation tab', triage.sender_body(quoting)[0])

        tight = set()
        ingest.exchange_lines(s, {'conversation_id': 'c4', 'subject': '2027 Budgets', 'sent_at': None},
                              budget=30, seen=tight)
        self.assertNotIn(triage._norm_line(old), tight, 'a message the budget dropped is not "already said"')

    def test_the_hand_made_task_carries_the_ask_not_the_chain(self):
        out = triage.extract_ask({'Subject': 'RE: 2027 Budgets', 'BodyText': MAIL, 'OwnText': ASK})
        self.assertIn('link on the 2027 budgets', out['summary'])
        self.assertNotIn('depreciation tab', out['summary'])


if __name__ == '__main__':
    unittest.main()
