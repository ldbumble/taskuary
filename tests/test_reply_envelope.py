"""Email replies default to Reply all with an editable, persisted envelope, and carry the owner's signature once (PW-063 to PW-066).

A reply went to the sender alone, with a CC the owner could add at the last click, and the
signature was whatever the model chose to write. Now an email draft is pinned to a recipient
envelope when it is written - Reply all by default: the sender (or the Reply-To), the original To
and CC participants, the sending mailbox's own addresses excluded, deduplicated, never a BCC - the
owner can switch to Reply to or edit To/CC, approval sends exactly the envelope reviewed, and the
owner's email signature is applied once when a draft is written or saved by hand - visible before
approval, never at send time, never on chat, never twice.
"""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import outbound, responder, server, verdicts
from taskuary.store import MemoryStore

STYLE = '## Reply style\n\n- Two sentences, answer first.\n- Sign off: "Best,\nUri Nussbaum\nMFA Heritage"\n'


def store():
    s = MemoryStore()
    s.set_setting('owner_email', 'uri@northwind.example', 't')
    s.save_doc('style', STYLE, 'owner')
    return s


def mail(s, tid=None, to=('uri@northwind.example', 'sam@vendor.example'), cc=('pat@vendor.example', 'Uri@Northwind.example'), meta=None, ext='m1'):
    return s.add_message({'TaskId': tid, 'ExternalId': ext, 'ConversationId': 'AAQk-x', 'Channel': 'email', 'SourceName': 'uri@northwind.example',
                          'Subject': 'August export', 'FromName': 'Dana', 'FromEmail': 'dana@vendor.example', 'SentAt': '2026-09-06 09:00:00',
                          'BodyText': 'Could you send the August export?', 'Status': 'routed',
                          'RecipientsJson': json.dumps({'to': list(to), 'cc': list(cc)}), 'MailMetaJson': json.dumps(meta) if meta else None})


class EnvelopeTests(unittest.TestCase):
    def test_reply_all_is_the_default_and_excludes_the_mailbox_deduplicates_and_never_bccs(self):
        s = store(); mid = mail(s)
        env = outbound.reply_envelope(s, s.get_message(mid))
        self.assertEqual(env['mode'], 'reply_all')
        self.assertEqual(env['to'], ['dana@vendor.example', 'sam@vendor.example'])
        self.assertEqual(env['cc'], ['pat@vendor.example'])
        self.assertNotIn('bcc', env)

    def test_reply_to_is_the_sender_or_the_reply_to_header(self):
        s = store(); mid = mail(s, meta={'reply_to': 'helpdesk@vendor.example'})
        env = outbound.reply_envelope(s, s.get_message(mid), mode='reply_to')
        self.assertEqual((env['to'], env['cc']), (['helpdesk@vendor.example'], []))
        env_all = outbound.reply_envelope(s, s.get_message(mid))
        self.assertEqual(env_all['to'][0], 'helpdesk@vendor.example'); self.assertNotIn('dana@vendor.example', env_all['to'])

    def test_a_chat_message_has_no_envelope(self):
        s = store()
        mid = s.add_message({'ExternalId': 't1', 'ConversationId': 'teams:x', 'Channel': 'teams', 'SourceName': 'Mindy', 'Subject': 'chat',
                             'FromName': 'Mindy', 'SentAt': '2026-09-06 09:00:00', 'BodyText': 'hi', 'Status': 'routed'})
        self.assertIsNone(outbound.reply_envelope(s, s.get_message(mid)))


class PinnedAndSentTests(unittest.TestCase):
    def thread(self):
        s = store()
        tid = s.create_task({'Title': 'August export', 'Kind': 'reply', 'Status': 'open', 'Priority': 'normal', 'Source': 'email'}, 'router')
        mid = mail(s, tid)
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
        return s, tid, mid, rid

    def test_the_draft_is_pinned_to_its_envelope_and_approval_sends_exactly_that(self):
        s, tid, mid, rid = self.thread()
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Here it is.')
        env = json.loads(s.get_review(rid)['Deliver'])
        self.assertEqual((env['kind'], env['mode'], env['to'], env['cc']), ('reply', 'reply_all', ['dana@vendor.example', 'sam@vendor.example'], ['pat@vendor.example']))
        sent = {}
        with mock.patch.object(outbound, 'reply_to_message', side_effect=lambda st, m, body, to=None, cc=None: sent.update(to=to, cc=cc, body=body) or {'channel': 'email', 'to': to, 'cc': cc}):
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertTrue(out['ok']); self.assertEqual((sent['to'], sent['cc']), (env['to'], env['cc']))

    def test_the_owner_edits_the_envelope_and_approval_sends_the_edited_one(self):
        s, tid, mid, rid = self.thread()
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Here it is.')
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            r = c.put(f'/api/reviews/{rid}/envelope', json={'mode': 'reply_to'}).json()
            self.assertEqual((r['to'], r['cc']), (['dana@vendor.example'], []))
            r2 = c.put(f'/api/reviews/{rid}/envelope', json={'to': ['dana@vendor.example', 'boss@vendor.example'], 'cc': ['me@elsewhere.example', 'me@elsewhere.example']}).json()
            self.assertEqual((r2['to'], r2['cc']), (['dana@vendor.example', 'boss@vendor.example'], ['me@elsewhere.example']))
        sent = {}
        with mock.patch.object(outbound, 'reply_to_message', side_effect=lambda st, m, body, to=None, cc=None: sent.update(to=to, cc=cc) or {'channel': 'email', 'to': to, 'cc': cc}):
            verdicts.decide(s, s.get_review(rid), 'approve')
        self.assertEqual((sent['to'], sent['cc']), (['dana@vendor.example', 'boss@vendor.example'], ['me@elsewhere.example']))

    def test_the_approved_text_leaves_exactly_as_reviewed(self):
        s, tid, mid, rid = self.thread()
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Here it is.')
        sent = {}
        with mock.patch.object(outbound, 'reply_to_message', side_effect=lambda st, m, body, to=None, cc=None: sent.update(body=body) or {'channel': 'email', 'to': to, 'cc': cc}):
            verdicts.decide(s, s.get_review(rid), 'edit', 'Attached - the numbers are final.\n\nBest,\nUri Nussbaum\nMFA Heritage')
        self.assertEqual(sent['body'], 'Attached - the numbers are final.\n\nBest,\nUri Nussbaum\nMFA Heritage')


class SignatureTests(unittest.TestCase):
    def thread(self, channel='email'):
        s = store()
        tid = s.create_task({'Title': 'August export', 'Kind': 'reply', 'Status': 'open', 'Priority': 'normal', 'Source': channel}, 'router')
        mid = mail(s, tid) if channel == 'email' else s.add_message({'TaskId': tid, 'ExternalId': 't1', 'ConversationId': 'teams:x', 'Channel': 'teams',
                                                                      'SourceName': 'Mindy', 'Subject': 'chat', 'FromName': 'Mindy', 'SentAt': '2026-09-06 09:00:00',
                                                                      'BodyText': 'hi', 'Status': 'routed'})
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
        return s, tid, mid, rid

    def test_the_signature_comes_from_style_md_or_the_setting(self):
        s = store()
        self.assertEqual(responder.signature_for(s), 'Best,\nUri Nussbaum\nMFA Heritage')
        s.set_setting('email_signature', 'Regards,\nUri', 'owner')
        self.assertEqual(responder.signature_for(s), 'Regards,\nUri')

    def test_a_draft_a_redraft_and_a_manual_draft_carry_it_exactly_once(self):
        s, tid, mid, rid = self.thread()
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Here it is.')
        text = s.get_review(rid)['DraftText']
        self.assertTrue(text.endswith('Best,\nUri Nussbaum\nMFA Heritage')); self.assertEqual(text.count('MFA Heritage'), 1)
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Here it is again.\n\nBest,\nUri Nussbaum\nMFA Heritage')   # the model signed already
        self.assertEqual(s.get_review(rid)['DraftText'].count('MFA Heritage'), 1)
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).patch(f'/api/reviews/{rid}', json={'body': 'Attached.'}).json()
        self.assertEqual(r['draft'].count('MFA Heritage'), 1); self.assertTrue(r['draft'].startswith('Attached.'))
        with mock.patch.object(server, 'store', s):
            r2 = TestClient(server.app).patch(f'/api/reviews/{rid}', json={'body': r['draft']}).json()
        self.assertEqual(r2['draft'].count('MFA Heritage'), 1)                              # saving again adds nothing

    def test_chat_gets_no_signature(self):
        s, tid, mid, rid = self.thread('teams')
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'on it')
        self.assertNotIn('MFA Heritage', s.get_review(rid)['DraftText'])


if __name__ == '__main__':
    unittest.main()
