"""A LINE THE OWNER SENT IS IN THE CHAT ONCE, whatever road carried it (the owner, 2026-11-06: one line typed into a general agent's chat stood
as a "You" bubble, and again under the agent's first step). Each road the chat has: the stream (an API brain, a CLI brain, with files), the
plain message post, the terminal composer, a line typed while a turn runs and taken by the turn ahead, and the ACP road's echo of a prompt."""
import json, threading, time, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import agents, general, handbook, llm, server, terminal
from taskuary.store import MemoryStore
from tests.test_general import connect_cli, general_task

LINE = 'the second site - I see you have it at 4 million?'


def mine(store, tid):
    "The owner's lines as the pane draws them (general.shown_history), by their words."
    return [p['text'] for m in general.shown_history(store, tid) if m['role'] == 'user' and not m.get('brief') for p in m['content'] if p.get('text')]


class EveryRoadFilesItOnceTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = general_task(self.s)

    def _stream(self, pick, brain, attachments=()):
        with mock.patch.object(server, 'store', self.s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(server, '_refresh_for_turn', return_value=({}, '')), mock.patch.object(handbook, 'enabled', return_value=False), \
             mock.patch.object(llm, 'build_llm', side_effect=lambda *a, trace=None, **k: (lambda system, user, **kw: brain(trace, user))):
            r = TestClient(server.app).post(f'/api/tasks/{self.tid}/assistant/stream', json={'text': LINE, 'pick': pick, 'attachments': list(attachments)})
        return [json.loads(x) for x in r.text.splitlines()]

    def test_a_cli_brain_that_echoes_the_prompt_files_the_line_once(self):
        connect_cli(self, claude={'cmd': 'claude'})
        def brain(trace, user):
            trace('prompt', 'prompt_sent_to_agent', user); trace('live', 'claude', LINE)       # a CLI that prints what it was asked
            trace('tool_call', 'Read', {'tool_call_id': 't1', 'args': {'file_path': '1348/a.xlsx'}}); trace('tool_result', 't1', {'result': 'ok'})
            return 'It is 4.2 million.'
        events = self._stream('cli:claude', brain)
        self.assertEqual(events[-1]['type'], 'done', events[-1])
        self.assertEqual([m['role'] for m in events[-1]['payload']['messages']], ['user', 'assistant'])
        self.assertEqual(mine(self.s, self.tid), [LINE])

    def test_a_line_with_files_is_filed_in_its_own_words_once_and_the_files_reach_the_agent(self):
        connect_cli(self, claude={'cmd': 'claude'})
        from taskuary import config
        pic = config.home() / 'attachments' / 'prompt' / 'line-once.png'; pic.parent.mkdir(parents=True, exist_ok=True); pic.write_bytes(b'png')
        said = []
        events = self._stream('cli:claude', lambda trace, user: (said.append(user), 'Read both.')[1], attachments=[str(pic)])
        self.assertEqual(events[-1]['type'], 'done', events[-1])
        self.assertEqual(mine(self.s, self.tid), [LINE], 'the paths ride the turn, never the line the chat draws')
        self.assertIn('line-once.png', said[0])
        # ...and the file is the task's own, in its folder, where sign_form and the propose tools take it (the owner, 2026-11-09)
        from taskuary import outputs
        import shutil
        self.addCleanup(shutil.rmtree, outputs.folder(self.tid), True)
        self.assertEqual((outputs.folder(self.tid) / 'line-once.png').read_bytes(), b'png')
        self.assertIn(str(outputs.folder(self.tid) / 'line-once.png'), said[0])

    def test_an_api_brain_files_the_line_once(self):
        sess = general.GeneralSession(self.s, self.tid); sess.pick, sess.provider = 'connector:1', 'Azure OpenAI'
        with mock.patch.object(llm, 'build_llm', return_value=lambda system, user, **k: 'answered'), mock.patch.object(handbook, 'enabled', return_value=False):
            sess.send_prompt(LINE)
        self.assertEqual(mine(self.s, self.tid), [LINE])

    def test_the_terminal_composer_files_the_line_once(self):
        sess = general.GeneralSession(self.s, self.tid); sess.pick, sess.provider = 'cli:claude', 'Claude Code'
        with mock.patch.object(llm, 'build_llm', return_value=lambda system, user, **k: 'answered'), mock.patch.object(handbook, 'enabled', return_value=False):
            sess.write(LINE + '\r')
            end = time.time() + 5
            while time.time() < end and not any(c['ActorType'] == general.ASSISTANT_TYPE for c in self.s.list_comments(self.tid)): time.sleep(0.05)
        self.assertEqual(mine(self.s, self.tid), [LINE])

    def test_a_line_typed_while_it_works_keeps_its_files_when_the_turn_ahead_takes_it(self):
        """The line waits for the turn ahead; whichever turn takes the waiting lines files each once - and the files sent WITH a line go with
        it. They were dropped: the turn that took the line carried only its own (send_prompt's queue kept the words alone)."""
        sess = general.GeneralSession(self.s, self.tid); sess.pick, sess.provider = 'cli:claude', 'Claude Code'
        seen = []
        def brain(system, user, **k): seen.append(user); time.sleep(0.6); return 'answered'
        with mock.patch.object(llm, 'build_llm', return_value=brain), mock.patch.object(handbook, 'enabled', return_value=False):
            first = threading.Thread(target=lambda: sess.send_prompt('look at the sheet')); first.start(); time.sleep(0.2)
            more = [threading.Thread(target=lambda w=w, a=a: sess.send_prompt(w, attachments=a)) for w, a in ((LINE, ['C:/x/one.png']), ('and this one', ['C:/x/two.png']))]
            for t in more: t.start(); time.sleep(0.1)
            for t in [first, *more]: t.join(15)
        self.assertEqual(mine(self.s, self.tid), ['look at the sheet', LINE, 'and this one'])
        self.assertEqual(len(seen), 2, 'the two lines typed while it worked are one turn')
        self.assertIn('one.png', seen[1]); self.assertIn('two.png', seen[1])


class TheAcpRoadDrawsNoEchoTests(unittest.TestCase):
    def test_a_prompt_the_adapter_echoes_back_is_no_step(self):
        "An ACP adapter may send the prompt back as a user_message_chunk: it is the owner's line, already filed - never a step of the turn."
        got = []
        t = agents.acp_tracer(lambda kind, name, detail: got.append((kind, name, detail)), 'claude')
        t({'sessionUpdate': 'user_message_chunk', 'content': {'type': 'text', 'text': LINE}})
        t({'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': 'It is 4.2 million.'}})
        t.flush('end_turn')
        self.assertFalse([g for g in got if LINE in json.dumps(g[2], default=str)], got)


if __name__ == '__main__':
    unittest.main()
