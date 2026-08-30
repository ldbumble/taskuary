"""A robot's mail can make a task. It cannot start a coding session.

Owner, 2026-08-30 (TQ-0253), after a CyberHoot training reminder got a full coder run and a
drafted reply back to the mailer: "narrow the dispatch for automated senders - if obviously
not for a coding agent then just create task."

The task is still real - the training IS due 2026-09-06 - so it lands on the Board and waits
for a click. What it no longer does is open a session that can only read a vendor's mailshot
and say "nothing to do here". The gate is the SENDER (categories.sender_class, the same
classifier that tags these rows on the Timeline), never the model's `kind`, so it is
deterministic and a person's task still goes to the agent exactly as before.
"""
import unittest
from unittest import mock

from taskuary import senders
from taskuary.ingest import auto_code_ok, ingest_message
from taskuary.store import MemoryStore

TASK_LLM = lambda sy, u: '{"intent": "task", "kind": "coding", "why": "asks for something"}'
NOTICE = ('Your assignment "Common Scams and How to Avoid Them" is outstanding, due 2026-09-06. '
          'Please complete it.\nYou are receiving this email because you are enrolled.')


def mail(**kw):
    base = {'external_id': 'x1', 'channel': 'email', 'subject': 'Outstanding Assignment', 'body': NOTICE,
            'from_email': 'hoots@cyberhoot.com', 'from_name': 'CyberHoot', 'conversation_id': None,
            'sent_at': '2026-08-30 09:00', 'source_link': None, 'source_name': 'uri@mfaheritage.net'}
    return {**base, **kw}


def ingested(s, m, llm=TASK_LLM):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True):
        out = ingest_message(s, m, llm=llm)
    return out, [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


def store():
    s = MemoryStore()
    s.set_setting('coder_auto_enabled', '1', 't')
    s.set_setting('owner_email', 'uri@mfaheritage.net', 't')
    return s


class GateTests(unittest.TestCase):
    def test_a_robots_notice_makes_the_task_and_stops_there(self):
        s = store()
        out, spawned = ingested(s, mail())
        self.assertEqual(out['status'], 'created')
        t = s.get_task(out['task_id'])
        self.assertEqual((t['Kind'], t['Status']), ('coding', 'open'))     # on the Board, not worked
        self.assertEqual(spawned, [])
        self.assertTrue(any('not auto-started' in c['Body'] for c in s.list_comments(out['task_id'])))
        # the Timeline says why, in the sender's terms rather than the stranger wording
        reason = s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason']
        self.assertIn('not a person', reason)
        self.assertIn('send it yourself if real', reason)

    def test_a_person_asking_the_same_thing_still_goes_to_the_agent(self):
        """The rule that must not move: err toward the coding agent for people."""
        s = store()
        _out, spawned = ingested(s, mail(external_id='p1', from_email='leah@mfaheritage.net', from_name='Leah',
                                         subject='the importer is down', body='the importer throws in jobs/import.py'))
        self.assertEqual(spawned, ['_auto_code'])

    def test_the_robot_gate_runs_before_the_sent_items_search(self):
        """The cheap gate first: a newsletter used to pay for a mailbox round-trip and then get
        an agent anyway."""
        s = store()
        with mock.patch('taskuary.ingest._spawn'), mock.patch.object(senders, 'wrote_to') as wrote:
            ingest_message(s, mail(external_id='n1'), llm=TASK_LLM)
        wrote.assert_not_called()

    def test_an_internal_system_address_is_a_robot_too(self):
        """Own-domain is not a free pass: noreply-securityapp@ is a system, whoever runs it."""
        s = store()
        _out, spawned = ingested(s, mail(external_id='i1', from_email='no-reply@mfaheritage.net',
                                         subject='backup finished', body='Nightly backup completed. Please review.'))
        self.assertEqual(spawned, [])

    def test_chat_is_never_gated(self):
        s = store()
        _out, spawned = ingested(s, mail(external_id='c1', channel='teams', conversation_id='c1',
                                         from_email='colleague@elsewhere.example', from_name='Sam',
                                         subject='exporter', body='can you fix the exporter, it dies in jobs/export.py'))
        self.assertEqual(spawned, ['_auto_code'])


class AutoCodeOkTests(unittest.TestCase):
    """The gate on its own, so the reason strings are pinned where the Timeline reads them."""
    def _msg(self, s, from_email, body):
        mid = s.add_message({'ExternalId': 'x', 'Channel': 'email', 'Subject': 's', 'FromEmail': from_email,
                             'SentAt': '2026-08-30 09:00', 'BodyText': body, 'Status': 'routed'})
        return mid

    def test_robot_first_person_falls_through_to_the_stranger_gate(self):
        s = store()
        ok, why = auto_code_ok(s, {'channel': 'email', 'from_email': 'hoots@cyberhoot.com'},
                               self._msg(s, 'hoots@cyberhoot.com', NOTICE))
        self.assertEqual((ok, 'not a person' in why), (False, True))
        with mock.patch.object(senders, 'wrote_to', return_value=False):
            ok, why = auto_code_ok(s, {'channel': 'email', 'from_email': 'stranger@evil.example'},
                                   self._msg(s, 'stranger@evil.example', 'the importer is down'))
        self.assertEqual((ok, 'never written to them' in why), (False, True))
        with mock.patch.object(senders, 'wrote_to', return_value=True):
            ok, _why = auto_code_ok(s, {'channel': 'email', 'from_email': 'client@partner.example'},
                                    self._msg(s, 'client@partner.example', 'the importer is down'))
        self.assertTrue(ok)


if __name__ == '__main__':
    unittest.main()
