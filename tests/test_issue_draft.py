"""THE ASSISTANT DRAFTS A REPORT WHEN ASKED (the owner, 2026-11-01: "can the advisor/assistant create bug report for you to send or a new
feature request? ... they will file issues"). The model reads the intent - no trigger words here - and CALLs issue.draft; the app puts the
Report popup's own button under the answer, carrying what was asked. Pressed, the popup drafts it through the scrub (bugreport.draft) and the
owner submits it on GitHub. Nothing is drafted over a stranger's task, on a turn the owner did not type, or on a phone with no popup to read."""
import json, unittest
from unittest import mock

from taskuary import buttons, concierge, ingest, terminal, toolcatalog
from test_assistant_router import proposals, store

WISH = {'kind': 'feature', 'trying': 'see what is waiting at a glance', 'happened': 'a way to sort the rail by date'}


def the_model(call, answer='Drafted - Request a feature, under this, opens it for you to check and submit.'):
    "the CALL first; then the answer, once it read what the tool said"
    seen = []
    def llm(system, user, **kw):
        if 'You looked up issue.draft' in user: seen.append(user); return answer
        return 'CALL: ' + json.dumps({'kind': 'issue.draft', 'params': call})
    llm.seen = seen
    return llm


class AssistantDrafts(unittest.TestCase):
    def ask(self, s, text, call, key=None, **kw):
        model = the_model(call)
        with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(ingest, '_spawn') as spawn:
            out = concierge.say(s, text, key=key, llm=model, **kw)
        spawn.assert_not_called(); self.assertEqual(proposals(s), [], 'never a card to confirm, never an operation')
        return out, model

    def test_a_wish_brings_up_request_a_feature_carrying_what_they_asked(self):
        s = store()
        out, model = self.ask(s, 'I wish I could sort the rail by date', WISH)
        self.assertEqual(out['chips'], [{'verb': 'bug', 'label': buttons.label('report_bug', 'feature'),
                                         'report': {**WISH, 'screen': 'Assistant', 'withLast': False}}])
        self.assertIn('nothing is sent from here', model.seen[0])
        # ...and the button stays on the line, for the chat read back later
        self.assertEqual(out['say'], 'Drafted - Request a feature, under this, opens it for you to check and submit.')

    def test_a_bug_brings_up_report_this_bug_read_beside_the_last_failure(self):
        s = store()
        out, _ = self.ask(s, "that's a bug - the export button did nothing", {'kind': 'bug', 'trying': 'export the board', 'happened': 'nothing happened'})
        (c,) = out['chips']
        self.assertEqual((c['verb'], c['label'], c['report']['kind'], c['report']['withLast']), ('bug', buttons.label('report_bug'), 'bug', True))

    def test_nothing_over_a_strangers_task(self):
        s = store()
        tid = s.create_task({'Title': 'Look at this', 'Kind': 'task', 'Status': 'open', 'OriginBase': 'stranger'}, 'triage')
        out, model = self.ask(s, 'file this as a bug', {'kind': 'bug', 'trying': 'x', 'happened': 'y'}, key=f'task:{tid}')
        self.assertFalse([c for c in out.get('chips') or [] if c.get('report')], out.get('chips'))
        self.assertIn('Nothing was drafted', model.seen[0])

    def test_nothing_on_a_phone(self):
        s = store()
        with concierge.delivering(concierge.PHONE):
            out, model = self.ask(s, 'feature request: sort by date', WISH)
        self.assertFalse([c for c in out.get('chips') or [] if c.get('report')])
        self.assertIn('Nothing was drafted', model.seen[0])

    def test_nothing_on_a_turn_they_did_not_type(self):
        s = store()
        out, model = self.ask(s, 'they pressed Save', WISH, react='pressed Save')
        self.assertFalse([c for c in out.get('chips') or [] if c.get('report')])
        self.assertIn('Nothing was drafted', model.seen[0])


class TheTool(unittest.TestCase):
    def test_it_is_in_the_catalogue_and_runs_in_the_turn(self):
        self.assertTrue(toolcatalog.runs_now('issue.draft'))
        self.assertIn('issue.draft(kind, trying, happened)', toolcatalog.block())
        self.assertIn('nothing is filed from here', toolcatalog.describe('issue.draft'))

    def test_it_needs_a_kind_and_something_said(self):
        v = toolcatalog.valid
        self.assertEqual(v('issue.draft', {'kind': 'feature', 'happened': 'sort by date'}), '')
        self.assertEqual(v('issue.draft', {'kind': 'bug'}), 'issue.draft needs trying or happened')
        self.assertEqual(v('issue.draft', {'trying': 'x'}), 'issue.draft needs kind')
        self.assertEqual(v('issue.draft', {'kind': 'gossip', 'trying': 'x'}), 'issue.draft needs kind: bug or feature')
        self.assertEqual(v('app.repair', {'name': 'whatsapp'}), 'app.repair needs how')


if __name__ == '__main__':
    unittest.main()
