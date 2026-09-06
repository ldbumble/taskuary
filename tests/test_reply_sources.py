"""Replies are written from STYLE.md, SOUL.md and the verified conversation - triage's learning stays with triage (PW-058 to PW-062).

Every draft carried LEARNED.md - what the system has learned about which mail deserves a task -
and the owner's standing triage verdicts (NOT A TASK, NOT OURS), so a reply prompt was half a
routing manual. Now a draft, a redraft, a message-only draft and a new outbound message are
written from STYLE.md for voice and signature, SOUL.md for identity and responsibilities, the
refreshed conversation and the verified result for what to say, and - as separately retrieved
notes - only explicit writing instructions. An edited draft's note goes to STYLE.md as a writing
instruction; a rejection's note stays triage feedback for LEARNED.md.
"""
import json, unittest
from unittest import mock

from taskuary import learn, outbox, responder, verdicts
from taskuary.store import MemoryStore

STYLE = ('## Reply style\n\n- Two sentences, answer first.\n- Sign off: "Best, Uri" - the quokka signature line.\n')
LEARNED = '## Active\n- Mail from vendors about invoices deserves a task (the capybara rule) [s:3 | ev: rv1 | seen: 2026-08-01]\n'


def store():
    s = MemoryStore()
    s.save_doc('style', STYLE, 'owner'); s.save_doc('learned', LEARNED, 'owner')
    s.add_memory({'Scope': 'global', 'ScopeKey': None, 'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner',
                  'Note': '2026-08-30: "resident refund" from x@y.com - NOT A TASK: the marmoset verdict'})
    s.add_memory({'Scope': 'global', 'ScopeKey': None, 'Source': 'writing', 'Active': 1, 'CreatedBy': 'owner',
                  'Note': 'Never open with "I hope this finds you well" - the wombat instruction'})
    return s


def thread(s):
    tid = s.create_task({'Title': 'August export', 'Kind': 'reply', 'Status': 'open', 'Priority': 'normal', 'Source': 'email'}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'ConversationId': 'AAQk-x', 'Channel': 'email', 'SourceName': 'me@northwind.example',
                         'Subject': 'August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': '2026-09-06 09:00:00',
                         'BodyText': 'Could you send the August export? The distinctive phrase is quetzal.', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
    return tid, mid, rid


def capture():
    seen = {}
    return seen, (lambda system, user, **k: (seen.update(system=system, user=user), 'Here it is.\n\nBest, Uri')[1])


class VoiceTests(unittest.TestCase):
    def assertVoice(self, seen):
        self.assertIn('quokka', seen['system'])                      # STYLE.md: voice and signature
        self.assertIn('You ARE', seen['system'])                     # SOUL identity
        self.assertIn('wombat', seen['system'])                      # an explicit writing instruction
        self.assertNotIn('capybara', seen['system'])                 # LEARNED.md is triage's
        self.assertNotIn('marmoset', seen['system'])                 # a triage verdict is not a writing note
        self.assertNotIn('learned profile', seen['system'].lower())

    def test_a_task_draft_and_its_redraft(self):
        s = store(); tid, mid, rid = thread(s)
        seen, llm = capture()
        responder.draft_for_review(s, tid, rid, llm=llm)
        self.assertVoice(seen); self.assertIn('quetzal', seen['user'])
        seen2, llm2 = capture()
        responder.draft_for_review(s, tid, rid, llm=llm2)
        self.assertVoice(seen2)

    def test_a_message_only_draft(self):
        s = store(); tid, mid, rid = thread(s)
        m = s.get_message(mid); seen, llm = capture()
        responder.draft_for_message(s, m, rid, llm=llm)
        self.assertVoice(seen); self.assertIn('quetzal', seen['user'])

    def test_a_new_outbound_message(self):
        s = store(); seen, llm = capture()
        outbox.draft_message(s, 'email', ['dana@vendor.example'], 'tell Dana the export ships Friday', llm=llm)
        self.assertVoice(seen)


class FeedbackRoutingTests(unittest.TestCase):
    def test_an_edited_drafts_note_becomes_a_writing_instruction_in_style_md_not_triage_learning(self):
        s = store(); tid, mid, rid = thread(s)
        s.update_review_draft(rid, 'Here it is.\n\nBest, Uri', None)
        events = []
        with mock.patch.object(learn, 'learn_from', side_effect=lambda st, ev, **k: events.append(ev)), \
             mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['dana@vendor.example']}):
            out = verdicts.decide(s, s.get_review(rid), 'edit', 'Attached. Best, Uri', 'shorter, and never say "please find attached"')
        self.assertTrue(out['ok'])
        style = s.get_doc('style')
        self.assertIn('## Owner notes', style); self.assertIn('never say "please find attached"', style)
        self.assertNotIn('quokka', style.split('## Owner notes')[1])                  # appended outside the generated block, once
        self.assertTrue(events); self.assertNotIn('please find attached', events[0])  # triage learning keeps the verdict, not the writing note
        self.assertIn('quokka', s.get_doc('style'))                                   # nothing of the owner's own lines lost

    def test_a_rejections_note_stays_triage_feedback(self):
        s = store(); tid, mid, rid = thread(s)
        s.update_review_draft(rid, 'Here it is.', None)
        events = []
        with mock.patch.object(learn, 'learn_from', side_effect=lambda st, ev, **k: events.append(ev)):
            verdicts.decide(s, s.get_review(rid), 'reject', None, 'this never needed a reply - it is a notification')
        self.assertIn('never needed a reply', events[0]); self.assertNotIn('## Owner notes', s.get_doc('style') or '')

    def test_writing_notes_can_be_saved_by_hand(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = store()
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post('/api/memory', json={'note': 'Always close with a next step - the numbat note', 'scope': 'global', 'source': 'writing'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('numbat', ' '.join(responder.writing_notes(s)))
        self.assertNotIn('marmoset', ' '.join(responder.writing_notes(s)))


if __name__ == '__main__':
    unittest.main()
