""""Ignore this sender" is two different acts, and the owner is asked which.

A RULE (Settings → Rules) stops the sender reaching triage at all and pulls their history off the
timeline; a MEMORY leaves the mail arriving and readable and teaches the classifier the verdict.
Picking one silently is how mail quietly disappears later, so neither is the default (the owner,
2026-09-04: "shoudl I add it to exclusion rule in setting or just a memory").
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server
from taskuary.store import MemoryStore


def _mail(s, sub, frm='noreply@bank.example'):
    return s.add_message({'ExternalId': f'x:{frm}:{sub}', 'Channel': 'email', 'Subject': sub,
                          'FromName': 'Bank', 'FromEmail': frm, 'SentAt': '2026-09-04 06:00:00',
                          'BodyText': 'Your file is ready to download.', 'Status': 'filed'})


class IgnoreSenderTests(unittest.TestCase):
    def test_the_rule_door_writes_a_skip_rule_and_reaches_backwards(self):
        s = MemoryStore()
        old, mid = _mail(s, 'Balance Reporting 1'), _mail(s, 'Balance Reporting 2')
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post(f'/api/messages/{mid}/ignore-sender', json={'how': 'rule'})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d['how'], d['sender']), ('rule', 'noreply@bank.example'))
        pol = next(p for p in s.list_policies(active_only=False) if p['PolicyId'] == d['policyId'])
        self.assertEqual((pol['Kind'], pol['Pattern'], pol['Action']), ('sender', 'noreply@bank.example', 'skip'))
        self.assertEqual(s.get_message(old)['Status'], 'skipped')      # their history leaves the timeline too

    def test_the_memory_door_teaches_the_verdict_and_writes_no_rule(self):
        s = MemoryStore()
        mid = _mail(s, 'Balance Reporting')
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post(f'/api/messages/{mid}/ignore-sender', json={'how': 'memory'})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d['how'], d['scope'], d['scopeKey']), ('memory', 'sender', 'noreply@bank.example'))
        self.assertEqual([m['Scope'] for m in s.list_memories()], ['sender'])
        self.assertEqual(s.list_policies(active_only=False), [])       # the mail keeps arriving
        self.assertEqual(s.get_message(mid)['Status'], 'ignored')

    def test_a_message_with_no_sender_is_refused_rather_than_keyed_on_nothing(self):
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'x:anon', 'Channel': 'email', 'Subject': 'no from',
                             'FromName': 'Nobody', 'FromEmail': '', 'SentAt': '2026-09-04 06:00:00',
                             'BodyText': 'x', 'Status': 'filed'})
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            self.assertEqual(c.post(f'/api/messages/{mid}/ignore-sender', json={'how': 'rule'}).status_code, 422)
            self.assertEqual(c.post('/api/messages/999999/ignore-sender', json={'how': 'rule'}).status_code, 404)
            self.assertEqual(c.post(f'/api/messages/{mid}/ignore-sender', json={'how': 'sideways'}).status_code, 422)


class IgnoreScopeInstructionTests(unittest.TestCase):
    def test_the_chat_is_told_to_ask_which_ignore_was_meant(self):
        """A bare "ignore it" names the act and not the scope, and scope is the part that lasts."""
        from taskuary import concierge
        blob = ' '.join(str(getattr(concierge, n)) for n in dir(concierge)
                        if n.isupper() and isinstance(getattr(concierge, n), str))
        self.assertIn('OPTIONS: just this once | this kind from now on | everything from this sender', blob)
        for verb in ('not_ours', 'not_ours_remember', 'not_ours_sender'):
            self.assertIn(verb, blob, verb)

    def test_an_fyi_says_why_triage_filed_it_and_what_can_be_done(self):
        """"nothing - read it if you like" is not an offer, and the verdict without its reason is
        not an explanation (the owner, 2026-09-04: "ask we processed as fyi because of x")."""
        from taskuary import concierge
        item = {'kind': 'fyi', 'mid': 7, 'who': 'DES-B2B-PROD', 'channel': 'email',
                'title': 'FCB_prod Success File Notification',
                'why': 'triage: fyi - an automated success-file notification'}
        said = concierge.fallback(item, opening=True)
        self.assertIn('triage filed it as fyi - an automated success-file notification', said)
        self.assertNotIn('fyi - triage: fyi', said)              # the verdict word is not said twice
        self.assertIn('make it a task', said); self.assertIn('ignore this sender', said)

    def test_a_reason_that_never_names_the_verdict_is_passed_through_whole(self):
        from taskuary import concierge
        said = concierge.fallback({'kind': 'fyi', 'mid': 7, 'who': 'A', 'title': 'T',
                                   'why': 'a newsletter nobody asked for'}, opening=True)
        self.assertIn('triage filed it as fyi - a newsletter nobody asked for', said)


if __name__ == '__main__':
    unittest.main()
