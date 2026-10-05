"""A yes sends the draft the owner was shown - never whatever the draft says by the time the yes lands.

WhatsApp showed draft A. Before the owner answered "1", the task's agent ran `taskuary --reply` and wrote draft B over
it, and B went out under the yes given to A. The stale check pinned only the thread (its messages and status), so a
new draft - or new recipients, or a file attached - on the same thread passed it.
"""
import json, unittest
from unittest import mock

from taskuary import coder, concierge, operations, remote_assistant, verdicts
from taskuary.store import MemoryStore

JID = '15551234567@s.whatsapp.net'
A, B = 'Yes - Thursday still works.', 'Thursday is off, sorry - can we do Monday?'


def a_draft():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Thursday check-in', 'Kind': 'task', 'Status': 'open'}, 'owner')
    mid = s.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                         'Subject': 'Thursday check-in', 'BodyText': 'Are we still on for Thursday?', 'Status': 'open'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': A})
    return s, {'key': f'review:{rid}', 'kind': 'review', 'lane': 'approve', 'rid': rid, 'mid': mid, 'tid': tid,
               'who': 'Erin Blake', 'channel': 'whatsapp', 'title': 'Thursday check-in'}


class ProposalTests(unittest.TestCase):
    def confirm(self, s, op):
        ran = []
        return operations.execute(s, op['id'], op['version'], lambda: ran.append(1) or {'ok': True}), ran

    def test_a_new_draft_after_the_proposal_refuses_the_yes(self):
        s, item = a_draft()
        op = operations.propose(s, 'review.approve', item['rid'])
        coder.agent_reply(s, item['tid'], B, 'claude')
        out, ran = self.confirm(s, op)
        self.assertEqual(out['status'], 'stale'); self.assertFalse(ran, 'draft B went out under the yes given to draft A')
        self.assertTrue(out.get('draft_changed')); self.assertIn('draft changed', out['error'])

    def test_new_recipients_or_files_refuse_it_too(self):
        s, item = a_draft()
        op = operations.propose(s, 'review.approve', item['rid'])
        s.set_review_envelope(item['rid'], {'kind': 'reply', 'to': ['gail@northwind.example'], 'attachments': ['payroll.xlsx']})
        out, ran = self.confirm(s, op)
        self.assertEqual(out['status'], 'stale'); self.assertFalse(ran)

    def test_the_same_draft_still_goes(self):
        s, item = a_draft()
        out, ran = self.confirm(s, operations.propose(s, 'review.approve', item['rid']))
        self.assertEqual(out['status'], 'done'); self.assertTrue(ran)


class PhoneTests(unittest.TestCase):
    def shown(self, s, item):
        text = remote_assistant.turn_text({'say': 'Erin is owed a reply - the draft is below.', 'item': item,
                                           'chips': [{'verb': 'approve', 'label': 'Send the reply'}, {'verb': 'next', 'label': 'Next'}]}, store=s)
        self.assertIn(A, text)
        remote_assistant.remember_offered(s, 'whatsapp', JID, text)       # what send() keeps beside the words
        return remote_assistant.acts_for(s, 'whatsapp', JID)['Send the reply']

    def pick(self, s, item, act):
        ran = []
        prop = {'id': 'op1', 'status': 'proposed', 'kind': 'review.approve', 'key': item['key'], 'settles': True}
        with mock.patch.object(concierge, 'propose_direct', return_value=prop), \
             mock.patch.object(concierge, 'run_proposal', side_effect=lambda *a, **k: ran.append(1) or {'status': 'done', 'id': 'op1'}), \
             mock.patch.object(concierge, 'receipt', return_value='Done - sent.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'Erin is owed a reply - the draft is below.', 'item': item,
                                                                  'chips': [{'verb': 'approve', 'label': 'Send the reply'}]}), \
             mock.patch.object(remote_assistant, '_on', side_effect=lambda st, actor, said, **kw: '\n\n'.join(said)):
            return remote_assistant.run_act(s, act, item), ran

    def test_a_draft_rewritten_after_the_phone_showed_it_is_not_sent(self):
        s, item = a_draft()
        act = self.shown(s, item)
        coder.agent_reply(s, item['tid'], B, 'claude')                     # the session's --reply, before the owner's "1"
        text, ran = self.pick(s, item, act)
        self.assertFalse(ran, 'draft B went out under the yes given to draft A')
        self.assertIn('draft changed', text); self.assertIn(B, text)      # ...and the new one is shown, to say yes to

    def test_a_yes_confirmed_after_the_draft_moved_shows_the_new_one(self):
        """Typed words propose; the confirm lands later. operations.execute refuses it, and the phone shows what waits now."""
        s, item = a_draft()
        op = operations.propose(s, 'review.approve', item['rid'])
        coder.agent_reply(s, item['tid'], B, 'claude')
        done = operations.execute(s, op['id'], op['version'], lambda: self.fail('sent'))
        with mock.patch.object(concierge, 'surface', return_value={'say': 'Erin is owed a reply.', 'item': item}):
            text = remote_assistant._ran(s, {**op, 'key': item['key'], 'settles': True}, done, item, 'owner')
        self.assertIn('draft changed', text); self.assertIn(B, text)

    def test_the_draft_that_was_shown_still_sends_on_one_pick(self):
        s, item = a_draft()
        text, ran = self.pick(s, item, self.shown(s, item))
        self.assertTrue(ran); self.assertIn('Done - sent.', text)


class RevisionTests(unittest.TestCase):
    def test_the_revision_is_what_a_yes_would_send(self):
        s, item = a_draft()
        first = verdicts.draft_revision(s, item['rid'])
        s.add_comment(item['tid'], 'owner', 'human', 'a note on the task is not the draft')
        self.assertEqual(verdicts.draft_revision(s, item['rid']), first)
        s.update_review_draft(item['rid'], B, None)
        self.assertNotEqual(verdicts.draft_revision(s, item['rid']), first)
