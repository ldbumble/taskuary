"""The external-sender banner, a mail app's stamp and a legal footer are left off what a screen shows (2026-09-23) - and which
text is one is triage's word (its verdict's `wrapper`), never a phrase list in Python or on the screen (the owner, 2026-10-28)."""
import json, unittest
from unittest import mock
from pathlib import Path

from taskuary import triage

ROOT = Path(__file__).resolve().parents[1]
WRAP = ('This email was sent from outside of Northwind. ** Do not click links or download attachments unless you '
        'know the content is safe.**')
ASK = 'Did you put in my raise to be effective this paycheck? My hire date was September 4.'
SAMPLE = f'{WRAP}\n\n{ASK}'


class WrapperIsTheModelsWordTests(unittest.TestCase):
    def test_no_phrase_list_is_left(self):
        for name in ('_BANNER', '_CLUTTER', '_LEGAL'): self.assertFalse(hasattr(triage, name), name)
        self.assertNotIn('export const BANNER', (ROOT / 'website' / 'src' / 'ui.jsx').read_text(encoding='utf-8'))

    def test_what_triage_named_is_left_out_and_nothing_else(self):
        self.assertEqual(triage.strip_wrapper(SAMPLE, (WRAP,)), ASK)
        self.assertEqual(triage.strip_wrapper(SAMPLE), SAMPLE)                    # not judged: shown as it came
        self.assertEqual(triage.strip_wrapper(WRAP, (WRAP,)), WRAP)               # never cut to nothing

    def test_a_made_up_passage_is_not_kept_on_the_verdict(self):
        self.assertEqual(triage.wrapper_in({'wrapper': [WRAP, 'Unsubscribe here']}, SAMPLE), [WRAP])

    def test_the_verdict_carries_it(self):
        llm = lambda *a, **k: json.dumps({'intent': 'reply_only', 'why': 'asks about pay', 'wrapper': [WRAP, 'not in the mail']})
        v = triage.classify_intent({'subject': 'raise', 'body': SAMPLE, 'from_name': 'Erin Blake'}, llm=llm)
        self.assertEqual(v.get('wrapper'), [WRAP])
        self.assertIn('wrapper', triage.verdict_schema()['schema']['properties'])

    # NAMED BY ITS TWO ENDS (2026-11-11): the model retyped the mail's own banner and footer into every verdict. It names where a
    # passage opens and ends; code finds it, and what is kept is the same exact passage as before.
    def test_a_passage_named_by_its_ends_is_kept_as_the_mail_spells_it(self):
        ends = {'from': 'this email was sent  from outside', 'to': 'know the content\nis safe.**'}     # its own spacing and case
        self.assertEqual(triage.wrapper_in({'wrapper': [ends]}, SAMPLE), [WRAP])
        llm = lambda *a, **k: json.dumps({'intent': 'reply_only', 'why': 'asks about pay', 'wrapper': [ends, {'from': 'Unsubscribe here', 'to': 'at any time'}]})
        v = triage.classify_intent({'subject': 'raise', 'body': SAMPLE, 'from_name': 'Erin Blake'}, llm=llm)
        self.assertEqual(v.get('wrapper'), [WRAP])
        self.assertEqual(triage.strip_wrapper(SAMPLE, triage.wrapper_of(v)), ASK)                      # every screen cuts as it did

    def test_a_passage_code_cannot_find_is_dropped_never_guessed(self):
        foot = 'This message is confidential and intended solely for the addressee. Payworth accepts no liability for any loss caused by viruses.'
        mail = f'{WRAP}\n\n{ASK}\n\n{foot}'
        named = lambda a, b: triage.wrapper_in({'wrapper': [{'from': a, 'to': b}]}, mail)
        self.assertEqual(named('This message is confidential', 'loss caused by viruses.'), [foot])
        self.assertEqual(named('This message is confidential', 'not in the mail at all'), [])          # no closing words: nothing hidden
        self.assertEqual(named('Not in the mail at all', 'loss caused by viruses.'), [])               # no opening words
        self.assertEqual(named('loss caused by viruses.', 'This email was sent from outside'), [])     # the end stands only before the start
        self.assertEqual(named('This', 'viruses.'), [])                                                # an end too short to place
        self.assertEqual(triage.wrapper_in({'wrapper': [{'from': 'This message is confidential'}, {'to': 'viruses.'}, 7, None]}, mail), [])
        self.assertEqual(named('loss caused by viruses.', 'loss caused by viruses.'), ['loss caused by viruses.'])   # one short line, both ends
        long = f'CAUTION: external sender.\n{"x " * 2000}\nEnd of the notice text.'
        self.assertEqual(triage.wrapper_in({'wrapper': [{'from': 'CAUTION: external', 'to': 'End of the notice text.'}]}, long), [])

    def test_opening_words_the_sender_also_wrote_never_hide_their_words(self):
        "The shortest stretch between the two ends: a footer's opening words standing earlier, in the ask, start nothing there."
        foot = 'This message and any attachments are confidential. Delete it if it is not yours.'
        mail = f'This message and any attachments are for Ray - can you check the quote by the 20th?\n\n{foot}'
        self.assertEqual(triage.wrapper_in({'wrapper': [{'from': 'This message and any attachments', 'to': 'if it is not yours.'}]}, mail), [foot])
        self.assertIn('check the quote', triage.strip_wrapper(mail, (foot,)))

    def test_the_old_whole_text_answer_is_still_read(self):
        self.assertEqual(triage.wrapper_in({'wrapper': [WRAP, {'from': 'Did you put in my raise', 'to': 'September 4.'}]}, SAMPLE), [WRAP, ASK])
        self.assertEqual(triage.wrapper_of({'wrapper': [WRAP]}), (WRAP,))                                # a stored verdict, as it was kept

    def test_the_passages_already_kept_say_how_often_two_ends_rebuild_them_with_no_model(self):
        from taskuary import evalset, ingest
        from taskuary.store import MemoryStore
        s = MemoryStore()
        for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
        twice = 'Sent from the Northwind mail app for your phone.'                 # stands twice in its mail: its ends still find it
        said = lambda body, *w: (lambda *a, **k: json.dumps({'intent': 'fyi', 'why': 'x', 'title': 't', 'summary': 's', 'wrapper': list(w)}))
        for i, (body, w) in enumerate(((SAMPLE, WRAP), (f'{ASK}\n\n{twice}\n\nOn Monday Erin wrote:\n{twice}', twice))):
            ingest.ingest_message(s, {'external_id': f'w{i}', 'channel': 'email', 'from_email': 'erin@northwind.example', 'subject': f'raise {i}',
                                      'body': body}, llm=said(body, w))
        self.assertEqual(evalset.wrapper_rebuilt(s), {'passages': 2, 'same': 2, 'other': 0, 'lost': 0})

    def test_the_phone_reads_it_the_same_way(self):
        from taskuary import remote_assistant
        from taskuary.store import MemoryStore
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'b1', 'Channel': 'teams', 'FromName': 'Erin Blake', 'Subject': 'raise',
                             'BodyText': SAMPLE, 'SentAt': '2026-09-23 09:00:00', 'Status': 'open'})
        with mock.patch.object(s, 'message_verdict', lambda m: {'intent': 'fyi', 'wrapper': [WRAP]}):
            block = remote_assistant.decision_block(s, {'mid': mid, 'kind': 'asked'})
        self.assertNotIn('sent from outside', block); self.assertIn('hire date was September 4', block)


if __name__ == '__main__':
    unittest.main()
