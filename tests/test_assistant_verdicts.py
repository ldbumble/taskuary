"""The assistant reads the owner's standing verdicts, the same ones triage reads.

The brief kept raising a subject the owner had already ruled out. Triage honoured the verdict -
it files those threads - but assistant.inputs never looked at the memory store, so the ruling was
true on one surface and news on the other. A verdict given once should hold everywhere.
"""
import unittest
from datetime import datetime, timedelta

from taskuary import assistant
from taskuary.store import MemoryStore

ME, RIVKA = 'owner@ours.com', 'rivka@clinic.example'
def _ago(h=1): return (datetime.now() - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')


def _store():
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 't'); s.set_setting('owner_email', ME, 't')
    s.add_message({'ExternalId': 'm1', 'ConversationId': 'c1', 'Channel': 'email', 'SourceName': ME,
                   'Subject': 'Fw: Resident Refund Request - Watson, Lisa', 'FromName': 'Rivka',
                   'FromEmail': RIVKA, 'SentAt': _ago(), 'BodyText': 'the refund is still open', 'Status': 'filed'})
    return s


CANDS = [{'key': 'asked:c1', 'kind': 'asked',
          'facts': 'Rivka asked today re "Resident Refund Request - Watson, Lisa": no answer from you.'}]


class VerdictsReachTheBrief(unittest.TestCase):
    def test_a_topic_verdict_is_put_in_front_of_the_model(self):
        s = _store()
        s.add_memory({'Scope': 'subject', 'ScopeKey': 'resident refund',
                      'Note': 'Resident refunds are not our problem - billing owns them.',
                      'Active': 1, 'CreatedBy': 'owner'})
        text = assistant.inputs(s, CANDS)
        self.assertIn('WHAT THE OWNER HAS ALREADY DECIDED', text)
        self.assertIn('not our problem', text)

    def test_it_matches_the_SOURCE_not_the_models_paraphrase(self):
        """The one that got through. A subject-scoped verdict is matched against the words it was
        learned from - "resident refund request approved" - and a candidate's `facts` is the
        model's summary of a thread: "Barnes and Watson stall the same way" carries none of them.
        So the ruling missed and the brief raised a subject the owner had closed. The threads and
        subject lines the model is handed are what the matcher reads now."""
        s = _store()
        s.add_message({'ExternalId': 'refund1', 'ConversationId': 'c-ref', 'Channel': 'email',
                       'SourceName': ME, 'Subject': 'RE: Resident Refund Request - Watson, Lisa',
                       'FromName': 'Rivka', 'FromEmail': RIVKA, 'SentAt': _ago(),
                       'BodyText': 'still waiting for a response', 'Status': 'filed'})
        s.add_memory({'Scope': 'subject', 'ScopeKey': 'resident refund request approved',
                      'Note': 'resident refunds are not ours', 'Active': 1, 'CreatedBy': 'owner'})
        paraphrase = [{'key': 'asked:c-ref', 'kind': 'asked',
                       'facts': 'Barnes and Watson stall the same way: the BOM answers in-thread '
                                'and Rivka threatens rejection.'}]
        text = assistant.inputs(s, paraphrase)
        self.assertIn('WHAT THE OWNER HAS ALREADY DECIDED', text)
        self.assertIn('resident refunds are not ours', text)

    def test_a_global_verdict_always_applies(self):
        s = _store()
        s.add_memory({'Scope': 'global', 'Note': 'Never chase a vendor before Wednesday.',
                      'Active': 1, 'CreatedBy': 'owner'})
        self.assertIn('Never chase a vendor before Wednesday.', assistant.inputs(s, CANDS))

    def test_a_switched_off_verdict_is_silent(self):
        s = _store()
        s.add_memory({'Scope': 'global', 'Note': 'Retired ruling nobody stands behind.',
                      'Active': 0, 'CreatedBy': 'owner'})
        self.assertNotIn('Retired ruling', assistant.inputs(s, CANDS))

    def test_a_verdict_about_something_else_costs_nothing(self):
        """Scoped by the candidates' own words: an unrelated topic note stays out of the prompt."""
        s = _store()
        s.add_memory({'Scope': 'subject', 'ScopeKey': 'parking permits',
                      'Note': 'Parking permits go to facilities.', 'Active': 1, 'CreatedBy': 'owner'})
        self.assertNotIn('Parking permits', assistant.inputs(s, CANDS))

    def test_no_verdicts_adds_no_heading(self):
        """An empty memory must not put an empty section in front of the model."""
        self.assertNotIn('ALREADY DECIDED', assistant.inputs(_store(), CANDS))


if __name__ == '__main__':
    unittest.main()
