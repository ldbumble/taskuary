"""Approval is interrupted when the context materially changed - and only then (PW-239 to PW-241).

A click on Approve sent whatever the draft said, or was refused with a line of text. Now a material
change - a new inbound message on the thread, a triage update that rewrote the task - stops the
click with an interruption the owner can act on: the new message and the triage change are shown,
the owner's own edited text is kept for comparison rather than discarded, the draft is refreshed and
needs a fresh yes. An unrelated arrival - an FYI triage filed with nothing to do - does not stop
anything: invalidation follows the draft's pinned context revision and the material state of the
thread, never a polling timestamp. A reply the owner sent outside is the missing verdict: the draft
is superseded and the click says so.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import channels, operations, server, verdicts
from taskuary.store import MemoryStore


def thread(s):
    tid = s.create_task({'Title': 'August export', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    first = s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'ConversationId': 'AAQk-x', 'Channel': 'email', 'SourceName': 'me@northwind.example',
                           'Subject': 'August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': '2026-09-06 09:00:00',
                           'BodyText': 'Could you send the August export?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': first, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Here it is.', 'Reason': 'needs a reply'})
    s.pin_review_context(rid, first, operations.message_revision(s, tid))
    return tid, first, rid


def arrives(s, tid, status='routed', body='Actually - September too, please.', at='2026-09-06 10:30:00'):
    return s.add_message({'TaskId': tid, 'ExternalId': f'm-{at}', 'ConversationId': 'AAQk-x', 'Channel': 'email', 'SourceName': 'me@northwind.example',
                          'Subject': 'RE: August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': at, 'BodyText': body, 'Status': status})


SENT = {'channel': 'email', 'to': ['dana@vendor.example'], 'cc': []}


class InterruptTests(unittest.TestCase):
    def approve(self, s, rid, text):
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.responder.draft_reply', return_value='Both months are attached.'), \
             mock.patch('taskuary.outbound.reply_to_message', return_value=SENT) as send:
            data = TestClient(server.app).post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': text, 'note': None}).json()
        return data, send

    def test_a_material_new_message_interrupts_the_click_and_keeps_the_owners_edit(self):
        s = MemoryStore(); tid, first, rid = thread(s)
        later = arrives(s, tid)
        s.add_comment(tid, 'triage', 'agent', 'Triage: the ask now covers September as well - checklist updated.')
        data, send = self.approve(s, rid, 'Here it is - my edited version.')
        self.assertFalse(data['ok']); self.assertTrue(data['stale']); send.assert_not_called()
        it = data['interrupt']
        self.assertEqual(it['title'], 'A new message arrived. Review it before sending.')
        self.assertEqual(it['latest']['MessageId'], later); self.assertIn('September too', it['latest']['preview'])
        self.assertIn('covers September', it['triage'])                                  # the relevant triage change, shown
        self.assertEqual(it['yours'], 'Here it is - my edited version.')                  # the owner's edit, kept for comparison
        self.assertIn('Both months', it['refreshed'])                                     # the refreshed draft, needing its own yes
        rv = s.get_review(rid)
        self.assertEqual((rv['Status'], rv['MessageId']), ('pending', later))
        self.assertTrue(any('my edited version' in (c['Body'] or '') for c in s.list_comments(tid)))   # not discarded

    def test_an_fyi_filed_with_nothing_to_do_does_not_interrupt(self):
        s = MemoryStore(); tid, first, rid = thread(s)
        arrives(s, tid, status='filed', body='FYI - the vendor newsletter.')
        data, send = self.approve(s, rid, 'Here it is.')
        self.assertTrue(data['ok']); send.assert_called_once(); self.assertNotIn('interrupt', data)

    def test_a_change_while_approval_is_open_is_caught_by_the_pinned_revision_not_a_flag(self):
        s = MemoryStore(); tid, first, rid = thread(s)
        arrives(s, tid)                                                                   # Stale flag never set: nobody marked it
        self.assertEqual(s.get_review(rid)['Stale'], 0)
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT) as send:
            out = verdicts.decide(s, s.get_review(rid), 'approve', 'Here it is.')
        self.assertEqual((out['ok'], out.get('stale')), (False, True)); send.assert_not_called()

    def test_the_previous_approval_is_never_applied_to_a_changed_draft(self):
        s = MemoryStore(); tid, first, rid = thread(s)
        arrives(s, tid)
        data, _ = self.approve(s, rid, 'Here it is.')
        self.assertTrue(data['stale'])
        arrives(s, tid, body='And October.', at='2026-09-06 10:45:00')                     # it moved again before the second look
        data2, send = self.approve(s, rid, data['interrupt']['refreshed'])
        self.assertTrue(data2['stale']); send.assert_not_called()
        data3, send3 = self.approve(s, rid, data2['interrupt']['refreshed'])               # the reviewed, current draft goes out
        self.assertTrue(data3['ok']); send3.assert_called_once()

    def test_a_reply_the_owner_sent_outside_supersedes_the_draft_and_the_click_says_so(self):
        s = MemoryStore(); tid, first, rid = thread(s)
        channels.retire_draft_answered_elsewhere(s, tid, {'ConversationId': 'AAQk-x', 'SentAt': '2026-09-06 11:00:00', 'Channel': 'email', 'BodyText': 'Sent it from Outlook.'})
        self.assertEqual(s.get_review(rid)['Status'], 'superseded')
        data, send = self.approve(s, rid, 'Here it is.')
        self.assertFalse(data['ok']); self.assertTrue(data.get('already')); send.assert_not_called()

    def test_the_review_list_marks_stale_by_material_change_only(self):
        s = MemoryStore(); tid, first, rid = thread(s)
        arrives(s, tid, status='filed', body='FYI')
        with mock.patch.object(server, 'store', s):
            rows = TestClient(server.app).get('/api/reviews', params={'status': 'pending'}).json()['data']
        self.assertFalse(rows[0]['Stale'])
        later = arrives(s, tid)
        with mock.patch.object(server, 'store', s):
            rows = TestClient(server.app).get('/api/reviews', params={'status': 'pending'}).json()['data']
        self.assertTrue(rows[0]['Stale']); self.assertEqual(rows[0]['LatestMessageId'], later)


if __name__ == '__main__':
    unittest.main()
