"""The demo: the whole app, none of the world.

A product whose point is connectors cannot be shown by screenshots, and cannot be shown by a
real instance either - a public Taskuary with a mailbox behind it is somebody's mailbox on the
internet. So it is the real application over invented data, with every door out nailed shut at
the API layer.

These tests are the lock. They check what is REFUSED, not what is hidden: a button that does
nothing is a design, a deny list is a control - and the list is written so that an endpoint
added next month is refused until somebody decides otherwise.
"""
import os
import unittest
from unittest import mock

from taskuary import demo
from taskuary.store import MemoryStore


def on():
    return mock.patch.dict(os.environ, {demo.FLAG: '1'})


class OffByDefaultTests(unittest.TestCase):
    def test_a_normal_install_is_not_a_demo(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(demo.FLAG, None)
            self.assertFalse(demo.enabled())
            self.assertEqual(demo.refuse('POST', '/api/connectors'), '')   # refuses nothing at all

    def test_the_flag_is_read_the_way_people_write_it(self):
        for value, want in (('1', True), ('true', True), ('YES', True), ('on', True),
                            ('0', False), ('', False), ('no', False)):
            with mock.patch.dict(os.environ, {demo.FLAG: value}):
                self.assertEqual(demo.enabled(), want, value)


class TheDoorsAreShutTests(unittest.TestCase):
    def test_nothing_sends(self):
        with on():
            for path in ('/api/reviews/3/send', '/api/review/3/send', '/api/tasks/7/handoff'):
                self.assertIn('Nothing sends', demo.refuse('POST', path), path)

    def test_no_connector_can_be_made_edited_or_given_a_secret(self):
        with on():
            for path in ('/api/connectors', '/api/connectors/3', '/api/connectors/3/test',
                         '/api/connectors/3/ai-setup', '/api/connectors/3/wa/bridge/start'):
                self.assertTrue(demo.refuse('POST', path), path)

    def test_no_tool_runs_against_anything(self):
        with on():
            self.assertTrue(demo.refuse('POST', '/api/tools/run'))
            self.assertTrue(demo.refuse('POST', '/api/agents/coder/test'))

    def test_no_cli_starts_on_the_machine_this_is_hosted_on(self):
        with on():
            self.assertTrue(demo.refuse('POST', '/api/terminals'))
            self.assertTrue(demo.refuse('DELETE', '/api/terminals/abc'))
            self.assertTrue(demo.refuse('PUT', '/api/agents/coder'))

    def test_nothing_is_fetched_or_received(self):
        with on():
            for path in ('/api/sync', '/api/ingest/push', '/api/hooks/claude', '/api/msauth/start'):
                self.assertTrue(demo.refuse('POST', path), path)

    def test_an_endpoint_nobody_thought_about_is_refused_by_default(self):
        """The list says what MAY happen. Anything else - including something added next month -
        is refused until somebody decides it is safe."""
        with on():
            self.assertTrue(demo.refuse('POST', '/api/something/invented/tomorrow'))
            self.assertTrue(demo.refuse('DELETE', '/api/tasks/3'))

    def test_reading_is_always_allowed(self):
        with on():
            for path in ('/api/feed', '/api/connectors', '/api/tools/run', '/api/terminals'):
                self.assertEqual(demo.refuse('GET', path), '', path)


class TheDemoStillWorksTests(unittest.TestCase):
    """A demo that cannot be used is a screenshot. Everything the visitor is there to try has
    to work - the triage verdicts, the chat, the board's wall, making a task."""
    def test_the_funnel_and_the_chat_are_usable(self):
        with on():
            for path in ('/api/tasks', '/api/tasks/3', '/api/messages/9/file',
                         '/api/tasks/3/assistant/messages', '/api/tasks/3/assistant/stream',
                         '/api/board/notes', '/api/tasks/3/comments'):
                self.assertEqual(demo.refuse('POST', path), '', path)

    def test_the_walk_is_something_a_visitor_can_actually_take(self):
        """It is a tour of the app that touches nothing real - which is the entire demo. The
        checklist stays hidden there (TaskHubPage hides SetupChip), because a list of connections
        nobody can make is not a demo of anything."""
        with on():
            for path in ('/api/setup/walk', '/api/setup/walk/reset', '/api/setup/seen'):
                self.assertEqual(demo.refuse('POST', path), '', path)

    def test_the_walk_being_open_does_not_open_the_connectors(self):
        with on():
            self.assertNotEqual(demo.refuse('POST', '/api/connectors'), '')


class TheScriptedBrainTests(unittest.TestCase):
    def test_it_answers_without_a_key_a_cli_or_a_network(self):
        said = demo.brain()('you are an assistant', 'CONVERSATION\nUSER: what should I do first?')
        self.assertIn('You asked', said)
        self.assertIn('what should I do first?', said)

    def test_it_quotes_only_what_the_person_typed(self):
        said = demo.brain()('sys', 'TASK TQ-1\nSOUL.md: secrets and documents\nUSER: hello there')
        self.assertNotIn('SOUL.md', said)
        self.assertIn('hello there', said)

    def test_triage_still_gets_the_json_it_expects(self):
        import json
        out = json.loads(demo.brain()('Answer ONLY with JSON: {"intent": ...}', 'a message'))
        self.assertIn(out['intent'], ('fyi', 'task', 'reply_only'))


class TheWorldTests(unittest.TestCase):
    def test_the_seed_builds_a_morning_worth_looking_at(self):
        s = MemoryStore()
        self.assertGreaterEqual(demo.seed(s), 5)
        rows = s.feed(limit=50)
        self.assertGreaterEqual(len(rows), 5)
        self.assertTrue(any(r.get('RouteReason') for r in rows))        # verdicts with their reasons
        self.assertIn('Dana Whitfield', s.get_doc('soul') or '')
        self.assertGreaterEqual(len(s.notes()), 3)                      # ...and a wall to read

    def test_it_refuses_to_write_over_a_home_that_has_work_in_it(self):
        s = MemoryStore()
        s.create_task({'Title': 'a real task'}, 'o')
        self.assertEqual(demo.seed(s), 0)

    def test_nobody_real_is_in_it(self):
        """Every address in the demo world is on a RESERVED domain. This used to name the one real
        domain it was guarding against, which put that domain in the repository the guard exists to
        keep it out of; the invariant catches any real domain, including the ones nobody thought of."""
        import re
        s = MemoryStore()
        demo.seed(s)
        blob = ' '.join(str(r) for r in s.feed(limit=50)) + (s.get_doc('soul') or '')
        found = set(re.findall(r'[\w.+-]+@([\w.-]+)', blob))
        self.assertTrue(found, 'the demo world has addresses in it')
        # RFC 2606's reserved names, and anything under one of them (vendor.example.com)
        ok = ('.example', '.test', '.invalid', '.localhost', 'example.com', 'example.net', 'example.org')
        for domain in found:
            self.assertTrue(domain.endswith(ok) or '.example.' in domain,
                            f'{domain} is not a reserved domain - the demo may only invent people')

    def test_a_replayed_session_looks_like_a_session(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'the export', 'Kind': 'coding'}, 'o')
        r = demo.Replay(s, tid, lines=[('working…', 0.01), ('done', 0.01)])
        info = r.info(tail=2)
        self.assertEqual((info['taskId'], info['mode'], info['alive']), (tid, 'demo', True))
        self.assertIn('phase', info)
        r.close()
        self.assertFalse(r.alive)

    def test_the_replay_takes_no_dictation(self):
        """It is a recording. Typing at it must not pretend to reach an agent."""
        s = MemoryStore()
        r = demo.Replay(s, 1, lines=[('x', 0.01)])
        r.write('rm -rf /\\n')                                            # goes nowhere, by design
        self.assertNotIn('rm -rf', r.scrollback())


if __name__ == '__main__':
    unittest.main()
