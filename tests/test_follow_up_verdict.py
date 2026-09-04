"""A reply that lands on an open task is still asked what it IS.

The router attaches a reply by its thread and the message then wore the TASK's kind for ever: a
bare "Thank you!" on an open coding task read as "asked you" in the pipe (the owner, 2026-09-03:
"why is it in asked you? they wrote thank you on what i wrote" / "Thank you is a close should not
be hard coded. the triage should realize that"). So triage judges a follow-up like any other
message, and an fyi verdict keeps it on the task for the chain and off the owner's pile.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import funnel, ingest, terminal
from taskuary.store import MemoryStore


def ago(hours=0, minutes=0):
    """The pipe is a WINDOW (funnel.HOURS_DEFAULT, 12h), not an archive: a wall-clock date here
    passes until the run crosses 12h past it, then the ask ages out and a wrapup takes its row.
    So every stamp is relative to the run - the same helper test_funnel.py uses."""
    return (datetime.now() - timedelta(hours=hours, minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states()
    return s


def opened(s, subject='PTO', body='Can you import pto for Aug 9 thru Aug 22?'):
    """The ask that started the task, its message on the thread, and the owner's own reply back."""
    t = s.create_task({'Title': subject.title(), 'Kind': 'coding', 'Status': 'waiting'}, 'o')
    s.add_message({'TaskId': t, 'ExternalId': 'x:ask', 'ConversationId': 'c1', 'Channel': 'email', 'Subject': subject,
                   'FromName': 'Chana', 'FromEmail': 'chana@hrtgcs.com', 'SentAt': ago(hours=8),
                   'BodyText': body, 'Status': 'routed'})
    s.add_message({'TaskId': t, 'ExternalId': 'x:mine', 'ConversationId': 'c1', 'Channel': 'email', 'Subject': f'RE: {subject}',
                   'FromName': 'You', 'FromEmail': 'owner@ours.com', 'SentAt': ago(hours=3),
                   'BodyText': 'Done. All PTO batches posted.', 'Status': 'context'})
    return t


def reply(body='Thank you!', subject='RE: PTO'):
    return {'external_id': 'x:thanks', 'channel': 'email', 'conversation_id': 'c1', 'subject': subject,
            'from_name': 'Chana', 'from_email': 'chana@hrtgcs.com', 'sent_at': ago(hours=1), 'body': body}


def brain(intent, why='because', kind=None):
    return lambda system, user, **kw: json.dumps({'intent': intent, 'why': why, **({'kind': kind} if kind else {})})


class FollowUpVerdictTests(unittest.TestCase):
    def test_an_fyi_follow_up_is_filed_onto_the_task_and_leaves_the_pipe_alone(self):
        s = store(); t = opened(s)
        out = ingest.ingest_message(s, reply(), llm=brain('fyi', 'only says thanks - nothing left to do'))
        self.assertEqual((out['status'], out['task_id']), ('filed', t))
        row = s.get_message(out['message_id'])
        self.assertEqual((row['Status'], row['TaskId']), ('filed', t))                 # on the chain, off the pile
        reason = s.list_routes(t)[-1]['Reason']
        self.assertIn('triage: fyi', reason); self.assertIn('only says thanks', reason); self.assertIn('for the chain', reason)
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            items = funnel.build(s)['items']
        self.assertEqual([(i['kind'], i['lane']) for i in items], [('wrapup', 'report')])   # your reply went out; close it?

    def test_a_follow_up_with_something_in_it_stays_work_on_the_task(self):
        s = store(); t = opened(s)
        out = ingest.ingest_message(s, reply('Thanks! Can you also do the M44 period?'),
                                    llm=brain('task', 'asks for the M44 period too', kind='coding'))
        self.assertEqual((out['status'], out['task_id']), ('attached', t))
        self.assertEqual(s.get_message(out['message_id'])['Status'], 'routed')
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            self.assertEqual([(i['kind'], i['lane']) for i in funnel.build(s)['items']], [('todo', 'asked')])

    def test_the_round_trip_an_agent_is_waiting_for_is_never_second_guessed(self):
        s = store(); t = opened(s)
        s.start_run(t, 'codex', 'work it', 'owner')
        asked = []
        out = ingest.ingest_message(s, reply('Use the 8/17 file.'), llm=lambda *a, **k: asked.append(1) or '{}')
        self.assertEqual((out['status'], out['task_id']), ('attached', t))
        self.assertEqual(asked, [])                              # no verdict is asked for while the agent waits

    def test_without_a_brain_a_follow_up_attaches_as_it_always_did(self):
        s = store(); t = opened(s)
        out = ingest.ingest_message(s, reply(), llm=None)
        self.assertEqual((out['status'], out['task_id']), ('attached', t))
        self.assertEqual(s.get_message(out['message_id'])['Status'], 'routed')

    def test_the_prior_thread_reaches_triage_as_the_exchange(self):
        """The evidence the verdict needs: what was asked before, and what the owner already sent -
        with the signature and the legal footer trimmed off both."""
        s = store()
        opened(s, body=('Where are we holding with the AI generated comments?\n\nThank you!\n\nChana\n'
                        'Phone:\nEmail:\n\n732‑905‑6440 x505\nchana@hrtgcs.com\n\n'
                        'NOTICE: This confidential message contains information intended for a specific individual.'))
        seen = {}
        def fake(system, user, **kw):
            seen.update(system=system, user=json.loads(user)); return json.dumps({'intent': 'fyi', 'why': 'x'})
        ingest.ingest_message(s, reply(), llm=fake)
        ex = seen['user']['exchange']
        self.assertEqual(len(ex), 2)
        self.assertIn('Where are we holding', ex[0]); self.assertIn('you ·', ex[1])
        for junk in ('NOTICE:', '732', 'Phone:', 'chana@hrtgcs.com'):
            self.assertNotIn(junk, ex[0], junk)

    def test_a_document_that_never_names_a_signal_is_told_what_it_means(self):
        """This install's TRIAGE.md was machine-generated before the exchange existed, and an
        owner-written doc replaces the shipped instructions wholesale - so the prior thread arrived
        as a key with nothing said about it (2026-09-03)."""
        s = store(); opened(s)
        s.save_doc('triage', 'Classify one inbound work message. Answer JSON only: {"intent": "task|reply_only|fyi"}.', 'histgen')
        seen = {}
        def fake(system, user, **kw):
            seen.update(system=system); return json.dumps({'intent': 'fyi', 'why': 'x'})
        ingest.ingest_message(s, reply(), llm=fake)
        self.assertIn('THE PAYLOAD ALSO CARRIES:', seen['system'])
        self.assertIn('exchange is the recent back-and-forth', seen['system'])
        self.assertIn('STILL THE ASK', seen['system'])            # and how to read it
        # ...while the shipped document, which explains the field itself, is left alone
        s2 = store(); opened(s2); seen.clear()
        ingest.ingest_message(s2, reply(), llm=fake)
        self.assertNotIn('THE PAYLOAD ALSO CARRIES:', seen['system'])


if __name__ == '__main__':
    unittest.main()
