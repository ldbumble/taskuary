"""Standing notes were taken in ROW ORDER and the joined text cut at 2000 characters, so past
the twentieth note - or the two-thousandth character - verdicts the owner had already given
stopped being applied, and nothing anywhere said so. These cover the retrieval that replaced
it: the right notes first, whole notes only, and the count of what did not fit said out loud.
"""
import unittest

from taskuary import agents
from taskuary.ingest import NOTE_CAP, ingest_message, notes_for, relevant_notes
from taskuary.store import MemoryStore

DANA = 'dana@vendor.com'


def _store(*notes):
    s = MemoryStore()
    for scope, key, note, src in notes:
        s.add_memory({'Scope': scope, 'ScopeKey': key, 'Note': note, 'Source': src,
                      'Active': 1, 'CreatedBy': 'test'})
    return s


LEDGER = ('sender', DANA, 'Mail like "Quarterly ledger reconciliation" from Dana is other '
                          "people's work - file it, do not open a task.", 'verdict')
INVOICE = ('sender', DANA, 'Dana asking about invoices always needs a reply, never an agent.', 'verdict')
SHIPPING = ('sender_domain', 'vendor.com', 'Vendor mail about shipping schedules is not ours.', 'learned')
GLOBAL = ('global', None, 'Never open tasks from newsletters or digests.', 'verdict')
STRANGER = ('sender', 'someone@else.com', 'Unrelated note about somebody else entirely.', 'verdict')


class RankingTests(unittest.TestCase):
    def test_the_note_the_message_is_actually_about_comes_first(self):
        """The whole point: which note leads depends on what the message SAYS, not on the order
        the rows happen to be in. Row order put the newest note first, forever - and this is the
        case that matters, because "Not our task" writes SENDER notes, so a busy sender's notes
        all share a scope and the message's own words are the only thing left to rank them by."""
        s = _store(LEDGER, INVOICE, SHIPPING, GLOBAL)
        first = lambda text: relevant_notes(s, [DANA], text)[0][0]
        self.assertIn('Quarterly ledger', first('Quarterly ledger reconciliation - attached'))
        self.assertIn('invoices', first('question about the invoices you sent'))

    def test_scope_outranks_relevance_across_tiers_but_not_within_one(self):
        """Where the weights land, said plainly: a note about THIS sender leads even when a
        broader one shares more words, because a verdict about the person in front of you is
        better evidence than a rule about their whole company. Below that tier the words decide."""
        s = _store(LEDGER, SHIPPING, GLOBAL)
        notes, _left = relevant_notes(s, [DANA], 'shipping schedules for next month')
        self.assertIn('Quarterly ledger', notes[0])       # sender scope, barely matching
        self.assertIn('shipping', notes[1])               # domain scope, matching - beats global
        self.assertIn('newsletters', notes[2])

    def test_specificity_and_a_real_verdict_decide_when_nothing_matches(self):
        """Nothing in the message to go on, so the ranking falls back to what it knows: a note
        about this sender beats one about their domain, which beats a global rule; and a verdict
        the owner gave beats a pattern a model distilled."""
        s = _store(GLOBAL, SHIPPING, LEDGER)
        notes, left = relevant_notes(s, [DANA], 'zzz')
        self.assertEqual(left, 0)
        self.assertIn('Quarterly ledger', notes[0])       # sender scope
        self.assertIn('shipping', notes[1])               # domain scope
        self.assertIn('newsletters', notes[2])            # global

    def test_only_notes_that_apply_and_only_active_ones(self):
        s = _store(LEDGER, STRANGER, GLOBAL)
        self.assertEqual(notes_for(s, {'from_email': 'nobody@nowhere.com', 'subject': 'hi', 'body': 'x'}),
                         ['Never open tasks from newsletters or digests.'])
        # switching a note off in the UI has to actually silence it
        mid = next(m['MemoryId'] for m in s.list_memories() if m['Scope'] == 'global')
        s.set_memory_active(mid, False)
        self.assertEqual(notes_for(s, {'from_email': 'nobody@nowhere.com', 'subject': 'hi', 'body': 'x'}), [])

    def test_a_verdict_is_never_cut_in_half(self):
        """Half a verdict reads as a DIFFERENT verdict - "file it, do not open a task" cut early
        can end at "file it, do not". So a note goes in whole or waits its turn."""
        s = _store(LEDGER, INVOICE, SHIPPING, GLOBAL)
        notes, left = relevant_notes(s, [DANA], 'ledger', budget=80)
        self.assertEqual((len(notes), left), (1, 3))
        self.assertTrue(notes[0].endswith('do not open a task.'))
        # and the first note always survives, however tight the budget - some memory beats none
        notes, left = relevant_notes(s, [DANA], 'ledger', budget=1)
        self.assertEqual((len(notes), left), (1, 3))

    def test_past_the_twentieth_note_the_owner_is_told(self):
        """The reported gap: note twenty-one simply vanished. It still does not fit - but the
        count comes back with it, so the funnel can say so instead of implying it applied."""
        s = _store(*[('sender', DANA, f'Verdict number {i} about Dana.', 'verdict') for i in range(25)])
        notes, left = relevant_notes(s, [DANA], 'Dana')
        self.assertEqual((len(notes), left), (NOTE_CAP, 25 - NOTE_CAP))


class ItSaysSoTests(unittest.TestCase):
    def test_the_timeline_says_how_many_notes_were_applied(self):
        s = _store(*[('sender', DANA, f'Verdict number {i} about Dana, at some length.', 'verdict')
                     for i in range(25)])
        out = ingest_message(s, {'external_id': 'x1', 'channel': 'email', 'from_email': DANA,
                                 'subject': 'Ledger', 'body': 'Attaching the ledger.'},
                             llm=lambda *a, **k: '{"intent": "fyi", "why": "informational"}')
        self.assertEqual(out['status'], 'filed')
        reason = s.feed(limit=5)[0]['RouteReason']
        self.assertIn(f'{NOTE_CAP} of 25 standing notes applied', reason)

    def test_nothing_is_said_when_everything_fit(self):
        s = _store(LEDGER, GLOBAL)
        ingest_message(s, {'external_id': 'x2', 'channel': 'email', 'from_email': DANA,
                           'subject': 'Ledger', 'body': 'Attaching the ledger.'},
                       llm=lambda *a, **k: '{"intent": "fyi", "why": "informational"}')
        self.assertNotIn('standing notes applied', s.feed(limit=5)[0]['RouteReason'])

    def test_the_classifier_is_told_when_notes_did_not_fit(self):
        """Otherwise the model reasons from a partial picture and reports it as a complete one."""
        from taskuary.triage import classify_intent
        seen = {}
        def llm(system, user, images=None):
            seen['system'] = system
            return '{"intent": "fyi", "why": "x"}'
        classify_intent({'from_email': DANA, 'subject': 's', 'body': 'b'}, llm=llm,
                        notes=['one note'], notes_left=4)
        self.assertIn('4 further note(s) also apply', seen['system'])
        classify_intent({'from_email': DANA, 'subject': 's', 'body': 'b'}, llm=llm, notes=['one note'])
        self.assertNotIn('further note(s)', seen['system'])

    def test_the_agent_block_ranks_the_thread_and_stops_growing_forever(self):
        """It had no cap at all - every matching note, however many the owner had given."""
        s = _store(LEDGER, INVOICE, GLOBAL,
                   *[('sender', DANA, f'Verdict number {i} about Dana, at some length.', 'learned')
                     for i in range(25)])
        block = agents.memory_block(s, [{'FromEmail': DANA, 'Subject': 'Quarterly ledger reconciliation',
                                         'BodyText': 'the ledger again'}])
        self.assertIn('Quarterly ledger', block.splitlines()[1])      # ranked to the top
        self.assertLessEqual(len(block.splitlines()), NOTE_CAP + 3)    # header + notes + the count line
        self.assertIn('did not fit', block)
        self.assertEqual(agents.memory_block(s, [{'FromEmail': 'nobody@nowhere.com'}]).splitlines()[1],
                         '- Never open tasks from newsletters or digests.')


if __name__ == '__main__':
    unittest.main()
