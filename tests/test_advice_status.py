"""WHAT THE STRIP SAYS, AND WHEN IT SAYS NOTHING (the owner's rulings, 2026-10-23; the design, phase A). "Thinking about this one..." ran
20 s and then showed nothing, and "No suggestion on this one - the choice is yours" stood over items whose move was plain. /api/advice
answers at once with the Advisor's one decision - a lit verb and a line that is '' when the move is obvious - and only no AI connected,
where the move needs one, is said as a reason. There is no "pending" any more: the rule's button is lit while the model reads."""
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import advisor, server, words
from taskuary.store import MemoryStore
from tests.test_advisor import _Rail, brain_saying


class StatusTests(_Rail):
    def test_a_line_is_the_line(self):
        s = MemoryStore(); t = self._asked_task(s)
        advisor.notice(s, 'reply.arrived', 'task', t, wait=True, llm=brain_saying({'verb': 'forward', 'line': 'Ray Colton owns the exports.', 'evidence': []}))
        with mock.patch.object(advisor, 'notice'): got = advisor.status(s, f'task:{t}')
        self.assertEqual((got['verb'], got['line'], got['by']), ('forward', 'Ray Colton owns the exports.', 'model'))

    def test_nothing_is_ever_pending_the_rules_button_is_lit_at_once(self):
        s = MemoryStore(); t = self._asked_task(s)
        rev = advisor.revision(s, 'task', t)
        with mock.patch.object(advisor, 'notice'), mock.patch.object(advisor, '_INFLIGHT', {('task', t, rev, 2, None)}):
            got = advisor.status(s, f'task:{t}')
        self.assertEqual((got['verb'], got['line'], 'pending' in got), ('reply', '', False))

    def test_an_obvious_move_is_silent_whatever_the_model_dropped(self):
        s = MemoryStore(); t = self._stopped_task(s)
        rev = advisor.revision(s, 'task', t)
        for dropped in ('left to the item', 'no actions', 'cap', 'nothing to say'):
            s._exec('DELETE FROM advice')
            advisor._write(s, target_kind='task', target_id=t, key=f'task:{t}', event=advisor.SHOWN, revision=rev, dropped=dropped)
            with mock.patch.object(advisor, 'notice'): got = advisor.status(s, f'task:{t}')
            self.assertEqual((got['verb'], 'none' in got), ('continue', False), dropped)

    def test_an_agent_at_work_is_next_and_a_switched_off_advisor_lights_nothing(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); t = self._stopped_task(s)
        with mock.patch.object(advisor, 'notice'), mock.patch.object(ws, 'status', return_value={'state': 'working'}):
            got = advisor.status(s, f'task:{t}')
        self.assertEqual((got['verb'], got['line'], got['state']), ('next', '', 'working'))
        s.set_setting(advisor.ON_KEY, '0', 'test')
        with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.status(s, f'task:{t}')['none'], 'off')

    def test_nothing_to_advise_on_is_said_as_nothing(self):
        with mock.patch.object(advisor, 'notice'): self.assertEqual(advisor.status(MemoryStore(), 'meeting:3'), {'none': 'nothing'})

    def test_only_no_ai_is_a_sentence(self):
        """Every sentence explaining a silence went (the owner, 2026-10-23: "No suggestion...", "Nothing to decide...", "Thinking..."):
        the one reason with a way out - no AI, where the move needs one - is the only line words.json keeps for a reason."""
        self.assertEqual(set(words.ADVICE_NONE), {'no_ai'})
        self.assertEqual(advisor.REASONS, ('no_ai',))
        said = ' '.join(v['line'] for v in words.ADVICE_NONE.values())
        for gone in ('No suggestion', 'Nothing to decide', 'Thinking', 'the choice is yours'): self.assertNotIn(gone, said)

    def test_the_endpoint_answers_with_the_decision(self):
        s = MemoryStore(); t = self._asked_task(s)
        with mock.patch.object(server, 'store', s), mock.patch.object(advisor, 'notice'):
            got = TestClient(server.app).get('/api/advice', params={'key': f'task:{t}'}).json()
        self.assertEqual((got['verb'], got['label'], got['line'], got['state'], got['by']), ('reply', 'Reply', '', 'asked', 'rule'))
