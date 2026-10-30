"""A blank left in a draft (the owner, 2026-10-30): Send refuses while a slot like "[REASON]" remains - at the one door
(verdicts.decide), so the task page, the phone and the assistant all meet it - and only template slots count, never the brackets
real mail carries. The edge cases are shared with the draft box's own marks (website/test/blanks.test.mjs)."""
import json, unittest
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

    def test_the_refusal_names_them_plainly(self):
        self.assertEqual(blanks.refusal('because [REASON].'), 'Fill in [REASON] first')
        self.assertEqual(blanks.refusal('[DATE] and [REASON]'), 'Fill in [DATE] and [REASON] first')
        self.assertEqual(blanks.refusal('[DATE], [TIME] and [REASON]'), 'Fill in [DATE], [TIME] and [REASON] first')
        self.assertEqual(blanks.refusal('Re: [External] all filled in.'), '')


def _reply(s, text, external='graph:BL1'):
    tid = s.create_task({'Title': 'answer Erin', 'Kind': 'general', 'Status': 'open'}, 'o')
    mid = s.add_message({'TaskId': tid, 'ExternalId': external, 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'FromEmail': 'erin@northwind.example', 'Subject': 'Friday', 'BodyText': 'Can you make Friday?', 'Status': 'routed'})
    return tid, s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': text})


def _sent(seen):
    return mock.patch.object(outbound, 'reply_to_message', side_effect=lambda st, m, b, to=None, cc=None, attachments=None:
                             (seen.append(b), {'channel': 'email', 'to': ['erin@northwind.example'], 'cc': []})[1])


class DoorTests(unittest.TestCase):
    def test_a_blank_refuses_the_send_and_leaves_the_draft_pending(self):
        s, seen = MemoryStore(), []
        tid, rid = _reply(s, "I can't make Friday because [REASON].")
        with _sent(seen): out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual((out['ok'], out['send_error'], out['blanks']), (False, 'Fill in [REASON] first', ['[REASON]']))
        self.assertEqual((seen, s.get_review(rid)['Status']), ([], 'pending'))

    def test_the_owners_edit_is_what_is_checked(self):
        s, seen = MemoryStore(), []
        _tid, rid = _reply(s, "I can't make Friday because [REASON].")
        with _sent(seen): out = verdicts.decide(s, s.get_review(rid), 'approve', "I can't make Friday - I'm away.")
        self.assertTrue(out['ok'], out)
        self.assertEqual(len(seen), 1)
        s2 = MemoryStore(); _t, rid2 = _reply(s2, 'All set.')
        with _sent(seen): out = verdicts.decide(s2, s2.get_review(rid2), 'approve', 'Moved to [DATE].')
        self.assertEqual((out['send_error'], len(seen)), ('Fill in [DATE] first', 1))

    def test_a_mail_tag_is_not_a_blank(self):
        s, seen = MemoryStore(), []
        _tid, rid = _reply(s, 'Re: [External] Payworth renewal - signed and attached [1].')
        with _sent(seen): out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertTrue(out['ok'], out)

    def test_the_endpoint_says_it_where_send_was_pressed(self):
        s, seen = server.store, []
        _tid, rid = _reply(s, 'Thanks,\n[Your name]', 'graph:BL3')
        with _sent(seen), mock.patch.object(server, '_refresh_chat_context'):
            r = server_client().post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': 'Thanks,\n[Your name]'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()['ok'], r.json()['send_error']), (False, 'Fill in [Your name] first'))
        self.assertEqual(seen, [])


class CloseOutTests(unittest.TestCase):
    """Close out's one press merges, then sends the reply: a blank in the reply stops it before the merge, not between the two."""
    def test_the_merge_waits_for_the_blank(self):
        from taskuary import github, proposals
        from tests.test_closeout import GREEN, OPEN, armed, finish, with_pr, setUpModule as up, tearDownModule as down
        up(); self.addCleanup(down)
        s = armed(MemoryStore()); tid = with_pr(s); finish(s, tid)
        reply = s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Merged - it ships on [DATE].'})
        with mock.patch.object(github, 'pr', return_value=OPEN), mock.patch.object(github, 'checks', return_value=GREEN), \
             mock.patch.object(github, 'merge_pr', return_value='m') as merge:
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve', reply_text='')
            merge.assert_not_called()
            self.assertEqual((out['ok'], out['send_error']), (False, 'Fill in [DATE] first'))
            out = verdicts.decide(s, proposals.closeout_pending(s, tid), 'approve', reply_text='Merged - it ships Friday.')
        merge.assert_called_once()
        self.assertTrue(out['ok'] and out['reply']['ok'], out)
        self.assertEqual(s.get_review(reply)['FinalText'], 'Merged - it ships Friday.')


def server_client(): return TestClient(server.app)


if __name__ == '__main__':
    unittest.main()
