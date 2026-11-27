"""A blank left in a draft (the owner, 2026-10-30): an agent's letter holding a slot like "[REASON]" is refused at its raise (wrapup.blank_why),
so no card ever shows one - and what the owner typed himself goes as he left it, with no second press. Only template slots count, never the
brackets real mail carries. The edge cases are shared with the draft box's own marks (website/test/blanks.test.mjs)."""
import json, unittest
from taskuary import card
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import blanks, outbound, server, verdicts
from taskuary.store import MemoryStore

CASES = json.loads((Path(__file__).parent / 'fixtures' / 'blanks_cases.json').read_text(encoding='utf-8'))['cases']


class RuleTests(unittest.TestCase):
    def test_every_shared_case(self):
        for text, want in CASES:
            with self.subTest(text=text): self.assertEqual(blanks.find(text), want)

    def test_spans_point_at_the_slot_in_the_text(self):
        t = 'See you on [DATE].'
        (a, b, s), = blanks.spans(t)
        self.assertEqual((t[a:b], s), ('[DATE]', '[DATE]'))


def _reply(s, text, external='graph:BL1'):
    tid = s.create_task({'Title': 'answer Erin', 'Kind': 'general', 'Status': 'open'}, 'o')
    mid = s.add_message({'TaskId': tid, 'ExternalId': external, 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'FromEmail': 'erin@northwind.example', 'Subject': 'Friday', 'BodyText': 'Can you make Friday?', 'Status': 'routed'})
    return tid, s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': text})


def _sent(seen):
    return mock.patch.object(outbound, 'reply_to_message', side_effect=lambda st, m, b, to=None, cc=None, attachments=None:
                             (seen.append(b), {'channel': 'email', 'to': ['erin@northwind.example'], 'cc': []})[1])


class DoorTests(unittest.TestCase):
    def test_what_he_sends_goes_as_he_left_it_blank_and_all(self):
        # the ruling, 2026-11-27: one card, one press - no "Send anyway" second step; a blank is refused at the agent's raise, not at his press
        s, seen = MemoryStore(), []
        _tid, rid = _reply(s, 'The review is in [ROOM]. I will confirm by ___.')
        with _sent(seen): out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertTrue(out['ok'], out)
        self.assertEqual(seen, ['The review is in [ROOM]. I will confirm by ___.'])

    def test_the_agents_letter_with_a_blank_is_refused_at_the_raise_with_the_fix(self):
        from taskuary import slots, wrapup
        s = MemoryStore()
        tid, _rid = _reply(s, 'x')
        out = wrapup.agent_reply(s, tid, 'Hi Erin, I moved it to {{day}}.', 'assistant')
        self.assertFalse(out['ok']); self.assertIn('{{day}}', out['why'])
        out = slots.draft(s, tid, 'Hi Erin, the room is [ROOM].', to='erin@northwind.example', subject='Friday', agent='assistant')
        self.assertFalse(out['ok']); self.assertIn('[ROOM]', out['why'])


def server_client(): return TestClient(server.app)


if __name__ == '__main__':
    unittest.main()
