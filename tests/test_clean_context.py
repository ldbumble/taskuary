"""Clean, complete context for triage (PW-026 to PW-030).

The model used to see a 12-line, 300-characters-a-line excerpt of the thread and the current body
cut at 1,500 characters - silently, as if that were the whole conversation - with the corporate
wrapper (external-sender banner, "Sent from my iPhone", unsubscribe footers) riding along and the
quoted copy of every earlier mail repeated inside every reply. Now one cleaner
(`triage.strip_boilerplate`) serves every connector and surface; quoted copies are dropped only when
their words are already in the assembled chain (`triage.dedupe_quoted`), so unique forwarded material
and inline answers survive; the exchange carries every message's substantive words under a
character budget and SAYS when it had to drop the oldest; and the current body is cut only under a
large budget, with the cut disclosed. Stored messages are never edited - cleaning is a triage
representation.
"""
import json, unittest

from taskuary import ingest, triage
from taskuary.store import MemoryStore

BANNER = 'This email was sent from outside of the organization. Do not click links unless you recognize the sender.\n'
HINT = "[You don't often get email from dana@vendor.example. Learn why this is important at https://aka.ms/LearnAboutSenderIdentification]\n"
SIG = '\n\nBest regards,\nDana Whitfield\nDirector of Finance\nPhone: 555-0100\n'
LEGAL = '\n\nCONFIDENTIALITY NOTICE: This message is intended solely for the addressee and may contain privileged information.'


class CleanerTests(unittest.TestCase):
    def test_banners_hints_and_footer_clutter_go_and_the_words_stay(self):
        body = BANNER + HINT + 'Can you send the reconciled ledger by Friday?\n\nSent from my iPhone\n'
        clean = triage.strip_boilerplate(body)
        self.assertEqual(clean.strip(), 'Can you send the reconciled ledger by Friday?')
        self.assertEqual(triage.strip_boilerplate('Please approve the invoice.\n\nGet Outlook for iOS\n').strip(), 'Please approve the invoice.')
        self.assertEqual(triage.strip_boilerplate('New prices below.\n\nUnsubscribe | Manage your email preferences | View this email in your browser\n').strip(), 'New prices below.')

    def test_signature_and_legal_footer_still_go(self):
        clean = triage.strip_boilerplate('Please fix the importer today, it drops the last row.' + SIG + LEGAL)
        self.assertEqual(clean.strip(), 'Please fix the importer today, it drops the last row.')

    def test_a_request_about_a_notice_or_security_is_not_stripped(self):
        body = 'Notice the error at the top of the security settings page - can you fix the login before Friday?\nThe signature block on the PDF is also wrong.'
        self.assertEqual(triage.strip_boilerplate(body), body)


PRIOR = 'Hi Uri,\n\nCould you look at the export job? It failed twice this week.\n\nThanks,\nDana'


class QuotedTests(unittest.TestCase):
    def test_a_quoted_copy_of_a_retained_message_is_dropped_and_the_new_words_kept(self):
        reply = ('Yes - it failed again this morning, log attached.\n\nOn Tue, 6 Sep 2026 at 09:00, Dana <dana@vendor.example> wrote:\n'
                 + '\n'.join('> ' + l for l in PRIOR.splitlines()))
        self.assertEqual(triage.dedupe_quoted(reply, [PRIOR]).strip(), 'Yes - it failed again this morning, log attached.')

    def test_an_outlook_style_quoted_history_is_dropped_when_retained(self):
        reply = ('Approved, go ahead.\n\n-----Original Message-----\nFrom: Dana Whitfield\nSent: Tuesday, September 6, 2026 9:00 AM\n'
                 'To: Uri\nSubject: Export job\n\n' + PRIOR)
        self.assertEqual(triage.dedupe_quoted(reply, [PRIOR]).strip(), 'Approved, go ahead.')

    def test_unique_forwarded_material_is_kept(self):
        fwd = ('FYI - see what the vendor said below.\n\n---------- Forwarded message ---------\nFrom: Vendor <ops@vendor.example>\n\n'
               'Your contract renews on 1 October at the new rate unless cancelled in writing.')
        out = triage.dedupe_quoted(fwd, [PRIOR])
        self.assertIn('renews on 1 October', out); self.assertIn('see what the vendor said', out)

    def test_inline_answers_survive_and_the_quoted_questions_they_answer_do_not_repeat(self):
        questions = 'Two things:\n1. Which environment failed?\n2. Do you need the old export kept?'
        reply = '> 1. Which environment failed?\nProduction, both nights.\n> 2. Do you need the old export kept?\nNo, overwrite it.'
        out = triage.dedupe_quoted(reply, [questions])
        self.assertEqual([l for l in out.splitlines() if l.strip()], ['Production, both nights.', 'No, overwrite it.'])

    def test_a_quote_of_something_not_in_the_chain_is_kept(self):
        reply = 'Agreed.\n\nOn Mon, Alex wrote:\n> Let us move the release to Thursday.'
        self.assertIn('move the release to Thursday', triage.dedupe_quoted(reply, [PRIOR]))


class ExchangeBudgetTests(unittest.TestCase):
    def chain(self, s, n, words=40, conv='AAQk-long'):
        mids = []
        for i in range(n):
            mids.append(s.add_message({'ExternalId': f'x{i}', 'ConversationId': conv, 'Channel': 'email', 'Subject': 'Export job',
                                       'FromName': f'Sender {i}', 'FromEmail': f's{i}@vendor.example',
                                       'BodyText': f'message {i}: ' + ' '.join(f'word{i}_{k}' for k in range(words)) + SIG + LEGAL,
                                       'SentAt': f'2026-09-06 {8 + i // 60:02d}:{i % 60:02d}:00', 'Status': 'filed'}))
        return mids

    def test_every_message_of_a_long_chain_reaches_the_model_when_the_budget_allows(self):
        s = MemoryStore(); self.chain(s, 20)
        lines = ingest.exchange_lines(s, {'conversation_id': 'AAQk-long', 'subject': 'Re: Export job', 'sent_at': '2026-09-06 12:00:00'})
        self.assertEqual(len(lines), 20)
        self.assertTrue(all('CONFIDENTIALITY' not in l and 'Director of Finance' not in l for l in lines))
        self.assertIn('message 0:', lines[0]); self.assertIn('message 19:', lines[-1])

    def test_substantive_words_beyond_the_old_300_character_cut_survive(self):
        s = MemoryStore(); self.chain(s, 1, words=300)                       # about 2,400 characters of substance
        lines = ingest.exchange_lines(s, {'conversation_id': 'AAQk-long', 'subject': 'Re: Export job', 'sent_at': '2026-09-06 12:00:00'})
        self.assertIn('word0_299', lines[0])

    def test_over_budget_the_oldest_go_first_and_the_cut_is_disclosed(self):
        s = MemoryStore(); self.chain(s, 20)
        lines = ingest.exchange_lines(s, {'conversation_id': 'AAQk-long', 'subject': 'Re: Export job', 'sent_at': '2026-09-06 12:00:00'}, budget=1500)
        self.assertTrue(lines[0].startswith('…'), lines[0])
        self.assertRegex(lines[0], r'(\d+) earlier message')
        self.assertIn('message 19:', lines[-1])
        self.assertLessEqual(sum(len(l) for l in lines[1:]), 1500)

    def test_quoted_copies_are_not_repeated_across_the_chain(self):
        s = MemoryStore()
        first = 'Could you look at the export job? It failed twice this week.'
        s.add_message({'ExternalId': 'a', 'ConversationId': 'q', 'Channel': 'email', 'Subject': 'Export', 'FromName': 'Dana', 'FromEmail': 'd@v.example',
                       'BodyText': first, 'SentAt': '2026-09-06 09:00:00', 'Status': 'filed'})
        quoted = 'Yes, twice.\n\nOn Tue, Dana wrote:\n> Could you look at the export job? It failed twice this week.'
        s.add_message({'ExternalId': 'b', 'ConversationId': 'q', 'Channel': 'email', 'Subject': 'Re: Export', 'FromName': 'Uri', 'FromEmail': 'me@ours.example',
                       'BodyText': quoted, 'SentAt': '2026-09-06 09:30:00', 'Status': 'context'})
        lines = ingest.exchange_lines(s, {'conversation_id': 'q', 'subject': 'Re: Export', 'sent_at': '2026-09-06 10:00:00'})
        self.assertEqual(sum('failed twice this week' in l for l in lines), 1)
        self.assertEqual(s.get_message(2)['BodyText'], quoted)                 # stored history untouched


class PayloadTests(unittest.TestCase):
    def test_the_model_sees_the_clean_body_whole_and_no_forced_verdict(self):
        seen = {}
        def llm(sys_, usr_, **k): seen['sys'], seen['usr'] = sys_, json.loads(usr_); return '{"intent": "task", "kind": "general", "why": "x"}'
        body = BANNER + 'Please review the attached ' + ' '.join(f'item{k}' for k in range(600)) + ' and confirm by Friday.' + SIG + LEGAL
        notes = ['2026-08-25: "Export" - NOT OURS: x', '2026-08-26: "Export" - NOT OURS: y']
        triage.classify_intent({'from_email': 'd@v.example', 'subject': 'Re: Export', 'body': body}, llm=llm, notes=notes)
        self.assertIn('item599', seen['usr']['body']); self.assertIn('confirm by Friday', seen['usr']['body'])
        self.assertNotIn('outside of the organization', seen['usr']['body']); self.assertNotIn('CONFIDENTIALITY', seen['usr']['body'])
        self.assertNotIn('body_truncated', seen['usr'])
        self.assertNotIn('SETTLED BY YOUR OWNER', seen['sys']); self.assertIn('EVIDENCE', seen['sys'])

    def test_a_body_past_the_budget_is_cut_with_the_cut_disclosed(self):
        seen = {}
        def llm(sys_, usr_, **k): seen['usr'] = json.loads(usr_); return '{"intent": "fyi", "why": "x"}'
        body = 'Please read: ' + ' '.join(f'w{k}' for k in range(5000))
        triage.classify_intent({'from_email': 'd@v.example', 'subject': 's', 'body': body}, llm=llm)
        self.assertTrue(seen['usr'].get('body_truncated'))
        self.assertLessEqual(len(seen['usr']['body']), triage.BODY_BUDGET + 100)


if __name__ == '__main__':
    unittest.main()
