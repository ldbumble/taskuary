"""The three doors a prompt can leave this machine by, each shut on credentials.

Every model call in the app goes out through one of these:

* ``llm.build_llm``      - the hosted brains (triage, assistant, concierge, drafter, digest).
                           Its own docstring says "everything in the app asks for its brain here".
* ``agents.run_cli``     - a headless CLI run. This is the one the owner asked about: the coder
                           prompt is built by ``agents.task_context``, which writes each message's
                           ``BodyText`` in verbatim.
* ``terminal.open_session`` - the first prompt of an interactive pane, by either road: handed to
                           the CLI in argv (claude, codex, gemini, copilot, devin) or typed in.

A door test is worth more than a pattern test: patterns can be right while a call site forgets
to use them, which is exactly how this leaked in the first place.
"""
import json
import unittest
from unittest import mock

from taskuary import agents, llm, redact, terminal
from taskuary.store import MemoryStore

KEY = 'AKIA' + 'IOSFODNN7EXAMPLE'
MAIL = f'Hi - the deploy box needs {KEY} to reach S3. Can you wire it up?'


def _coder(s):
    s.upsert_agent('claude', 'coding', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p']}))


class TheHostedBrainDoorTests(unittest.TestCase):
    def test_a_credential_never_reaches_the_model(self):
        s = MemoryStore()
        row = [c for c in s.list_connectors() if c['Type'] == 'anthropic'][0]
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
        s.set_setting('triage_ai', 'connector:anthropic', 't')
        seen = {}
        def recorder(system, user, **kw): seen.update(system=system, user=user); return 'ok'
        with mock.patch.object(llm, 'make_llm', return_value=recorder):
            brain = llm.build_llm(s)
            self.assertEqual(brain(f'You sort mail. {KEY}', MAIL), 'ok')
        self.assertNotIn(KEY, seen['user']); self.assertNotIn(KEY, seen['system'])
        self.assertIn('[redacted:aws-key]', seen['user'])
        self.assertIn('wire it up', seen['user'])                      # the ask still reads

    def test_the_wrapper_keeps_the_attributes_callers_read_off_it(self):
        """`llm.build_llm(...).session_id` is how a resumed CLI thread is carried; a wrapper that
        swallows it would silently break session continuity rather than fail loudly."""
        s = MemoryStore()
        row = [c for c in s.list_connectors() if c['Type'] == 'anthropic'][0]
        s.save_connector({'ConnectorId': row['ConnectorId'], 'Secret': 'k', 'Active': 1, 'ConfigJson': '{}'}, 'o')
        s.set_setting('triage_ai', 'connector:anthropic', 't')
        def recorder(system, user, **kw): return 'ok'
        recorder.session_id = 'thread-7'
        with mock.patch.object(llm, 'make_llm', return_value=recorder):
            brain = llm.build_llm(s)
            brain('sys', 'user')
            self.assertEqual(getattr(brain, 'session_id', None), 'thread-7')


class _FakeProc:
    """Enough of a Popen for run_cli to finish one turn, recording what was fed to stdin."""
    def __init__(self, fed): self.fed, self.returncode = fed, 0
    class _In:
        def __init__(self, fed): self.fed = fed
        def write(self, s): self.fed.append(s)
        def close(self): pass
    @property
    def stdin(self): return self._In(self.fed)
    @property
    def stdout(self): return iter(['{"type": "result", "result": "done"}'])
    @property
    def stderr(self):
        class _E:
            def read(self): return ''
        return _E()
    def poll(self): return 0
    def wait(self, timeout=None): return 0
    def kill(self): pass


class TheHeadlessCliDoorTests(unittest.TestCase):
    def test_a_credential_never_reaches_the_subprocess(self):
        fed = []
        with mock.patch.object(agents, '_resolve_cmd', return_value=['claude']), \
             mock.patch.object(agents.spawn, 'popen', side_effect=lambda *a, **k: _FakeProc(fed)):
            agents.run_cli({'cmd': 'claude', 'args': ['-p']}, f'Work this task:\n{MAIL}', lambda *a: None)
        self.assertTrue(fed)
        self.assertNotIn(KEY, fed[0]); self.assertIn('[redacted:aws-key]', fed[0])

    def test_the_stored_trace_of_the_prompt_is_scrubbed_too(self):
        """`run_cli` traces the prompt it sent, and that trace is saved on the run."""
        traced, fed = [], []
        with mock.patch.object(agents, '_resolve_cmd', return_value=['claude']), \
             mock.patch.object(agents.spawn, 'popen', side_effect=lambda *a, **k: _FakeProc(fed)):
            agents.run_cli({'cmd': 'claude', 'args': ['-p']}, MAIL,
                           lambda kind, name, text='': traced.append(str(text)))
        self.assertNotIn(KEY, ' '.join(traced))


class TheInteractivePaneDoorTests(unittest.TestCase):
    def _open(self, cmd, seed, tmp):
        s = MemoryStore()
        s.upsert_agent(cmd, 'coding', 'cli', json.dumps({'cmd': cmd, 'args': ['-p']}))
        tid = s.create_task({'Title': 'wire up S3', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        with mock.patch.object(agents, '_resolve_cmd', return_value=[cmd]), \
             mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(terminal, 'Term') as Term:
            Term.return_value.sid, Term.return_value.task_id, Term.return_value.store = 'p1', tid, s
            Term.return_value.agent, Term.return_value.cwd, Term.return_value.ext_id = cmd, str(tmp), ''
            terminal.open_session(s, cmd, tid, None, str(tmp), actor='owner', seed_fn=lambda here: seed)
        return Term

    def test_a_prompt_handed_over_in_argv_is_scrubbed(self):
        import tempfile
        Term = self._open('claude', MAIL, tempfile.gettempdir())
        argv = ' '.join(str(a) for a in Term.call_args.args[0])
        self.assertNotIn(KEY, argv); self.assertIn('[redacted:aws-key]', argv)

    def test_a_prompt_that_has_to_be_typed_in_is_scrubbed(self):
        import tempfile
        Term = self._open('cursor-agent', MAIL, tempfile.gettempdir())
        typed = ' '.join(str(a) for a in (Term.return_value.seed.call_args.args or ()))
        self.assertNotIn(KEY, typed); self.assertIn('[redacted:aws-key]', typed)


class NothingLeavesCarryingAPlaceholderTests(unittest.TestCase):
    def test_a_draft_still_holding_a_placeholder_is_not_sent(self):
        """A placeholder in outbound text means the scrub ran on something the owner meant to
        send. That is a bug to catch, not a message to deliver."""
        self.assertTrue(redact.holds_placeholder('I rotated [redacted:aws-key] for you'))
        self.assertFalse(redact.holds_placeholder('I rotated the key for you'))



class APlaceholderNeverGoesOutTests(unittest.TestCase):
    """The scrub runs on prompts, never on the owner's mail - so a placeholder appearing in
    something ADDRESSED TO A PERSON means a prompt's text was reused as a reply. Refuse it: the
    recipient would read `[redacted:aws-key]` where a sentence should be, and neither they nor
    the owner would know why."""

    def test_an_outbound_report_carrying_a_placeholder_is_refused(self):
        from taskuary import outbound
        s = MemoryStore()
        with self.assertRaises(RuntimeError) as e:
            outbound.send_out(s, 'email', 'dana@example.com', 'Keys', 'I rotated [redacted:aws-key] today')
        self.assertIn('redacted', str(e.exception).lower())

    def test_a_reply_carrying_a_placeholder_is_refused(self):
        from taskuary import outbound
        s = MemoryStore()
        msg = {'Channel': 'email', 'ExternalId': 'x1', 'FromEmail': 'dana@example.com'}
        with self.assertRaises(RuntimeError) as e:
            outbound.reply_to_message(s, msg, 'Sure - the key is [redacted:aws-key]')
        self.assertIn('redacted', str(e.exception).lower())

    def test_an_ordinary_reply_is_not_blocked_by_the_guard(self):
        """The guard must not become a reason a normal reply cannot be sent - it fails LATER,
        on the missing mailbox, which is a different complaint entirely."""
        from taskuary import outbound
        s = MemoryStore()
        msg = {'Channel': 'email', 'ExternalId': 'x1', 'FromEmail': 'dana@example.com'}
        with self.assertRaises(RuntimeError) as e:
            outbound.reply_to_message(s, msg, 'Sure - I rotated it this morning.')
        self.assertNotIn('redacted', str(e.exception).lower())
if __name__ == '__main__':
    unittest.main()
