"""THE BROWSER IS IN THE AGENT'S CANVAS (the owner, 2026-10-28). A general agent signing him up for a webinar asked, in a text card, "Do you
approve completing the 'I'm not a robot' check and submitting this registration? (Approve / Hold)" - with no page to do it on. "It should
show up as a BROWSER inside the agent canvas instead of this ... so it flows better to go back and continue."

The server's half: an agent never solves a CAPTCHA and never asks in words whether to submit - it hands the page over with
[[TASKUARY-YOURTURN: <what>]], raised as a `yourturn:` request the view draws as "Your turn", answered by Done; a held submit is already
browsergate's proposal, drawn on the view. And the view outlives its session: the last frame is kept by task and served for it.
Invented site and people only.
"""
import base64, json, os, tempfile, unittest
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import browserview, config, general, hooks, selfclose, server, terminal, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

PAGE = 'https://events.trainly.example/onboarding/register'
JPEG = base64.b64encode(b'\xff\xd8\xff\xe0fixture-frame\xff\xd9').decode()


def on_page(url=PAGE): return mock.patch.object(browserview, 'state', return_value={'open': True, 'url': url, 'port': 1})


class TheMarker(unittest.TestCase):
    def test_it_is_read_and_never_shown(self):
        said = 'The form is filled in.\n[[TASKUARY-YOURTURN: tick the "I\'m not a robot" box]]'
        self.assertEqual(selfclose.turn_marker(said), ('The form is filled in.', 'tick the "I\'m not a robot" box'))
        self.assertEqual(selfclose.turn_marker('[[TASKUARY-YOURTURN]]'), ('', ''))
        self.assertEqual(selfclose.turn_marker('nothing here'), ('nothing here', None))
        self.assertNotIn('YOURTURN', selfclose.for_screen(said))


class TheBrief(unittest.TestCase):
    def test_a_captcha_is_the_owners_and_is_handed_over_on_the_view(self):
        for held in (True, False):
            b = browserview.brief(held=held)
            self.assertIn(browserview.TURN_LINE, b)
            self.assertIn('NEVER SOLVE, CLICK OR WORK AROUND A CAPTCHA', b)
            self.assertIn('[[TASKUARY-YOURTURN:', b)
            self.assertNotIn('card number is for the owner to type in the pane: ask with the ask marker', b)
        # where the hold exists the agent runs the submit and the hold asks; where it does not, the agent still asks first
        self.assertIn('never ask the owner in words whether to submit, register or pay', browserview.brief(held=True))
        self.assertNotIn('never ask the owner in words whether to submit', browserview.brief(held=False))
        self.assertIn(browserview.ASK_FIRST_LINE, browserview.brief(held=False))


class YourTurn(unittest.TestCase):
    def setUp(self): self.s = MemoryStore(); self.tid = Factory(self.s).task('Sign up for the Trainly webinar', kind='general')

    def test_a_chat_agent_hands_the_page_over_with_done_as_its_press(self):
        sess = SimpleNamespace(sid='chat1', task_id=self.tid, alive=True, send_prompt=lambda *a, **k: '')
        with mock.patch.dict(terminal.SESSIONS, {'chat1': sess}, clear=True), on_page('https://www.events.trainly.example/x'):
            rid = browserview.your_turn(self.s, self.tid, 'chat1', 'tick the box')
            req = ws.status(self.s, self.tid)['requests']
        self.assertTrue(rid.startswith(browserview.TURN_PREFIX))
        self.assertEqual([r['request_id'] for r in req], [rid])
        self.assertEqual(req[0]['text'], 'Your turn in the browser on events.trainly.example: tick the box')
        self.assertEqual(req[0]['choices'], [browserview.TURN_DONE])

    def test_a_terminal_cli_gets_no_chooser_and_a_page_with_no_address_still_says_what(self):
        pty = SimpleNamespace(sid='run1', task_id=self.tid, alive=True)
        with mock.patch.dict(terminal.SESSIONS, {'run1': pty}, clear=True), on_page('about:blank'):
            browserview.your_turn(self.s, self.tid, 'run1', '')
            req = ws.status(self.s, self.tid)['requests'][0]
        self.assertEqual(req['choices'], [])                                 # a pty is answered in words, never by typing "1"
        self.assertEqual(req['text'], 'Your turn in the browser: the agent needs you to do a step on the page')

    def test_the_stop_hook_raises_it_and_no_judge_reads_the_turn(self):
        s, tid = self.s, self.tid
        pty = SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd=r'C:\code\repo', agent='general', label='general', argv=['claude'],
                              last=1.0, ext_id='c-sess', started='2026-10-28 09:00:00', typed=[], files=lambda: [], tail=lambda n=3: [],
                              idle=lambda: 0.0, witness=SimpleNamespace(note=lambda n: None), store=s, bg={})
        judged = []
        with mock.patch.dict(terminal.SESSIONS, {'run1': pty}, clear=True), mock.patch.object(terminal, 'bind_ext', lambda t, sid: None), \
                on_page(), mock.patch.object(hooks, 'judge_turn', lambda *a, **k: judged.append(a)):
            hooks.receive({'hook_event_name': 'Stop', 'session_id': 'c-sess', 'cwd': r'C:\code\repo',
                           'last_assistant_message': 'Filled in.\n[[TASKUARY-YOURTURN: tick the robot box]]'}, cli='claude')
            st = ws.status(s, tid)
        self.assertEqual(len(st['requests']), 1)
        self.assertTrue(st['requests'][0]['request_id'].startswith(browserview.TURN_PREFIX))
        self.assertEqual(judged, [])
        self.assertNotIn('YOURTURN', st['said'])


class AGeneralTurn(unittest.TestCase):
    def test_a_turn_ending_on_the_marker_waits_on_the_owner_and_is_not_judged_short(self):
        from taskuary import agents
        real, conns = config.load, {'claude': {'cmd': 'claude', 'args': ['-p']}}
        s = MemoryStore()
        tid = s.create_task({'Title': 'Sign me up for the Trainly webinar', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        reply = 'I filled in your name and email.\n[[TASKUARY-YOURTURN: tick the "I\'m not a robot" box]]'
        ended = []
        with mock.patch.object(config, 'load', side_effect=lambda: {**real(), 'cli_connections': conns}), \
                mock.patch.object(agents, 'connection_brains', getattr(agents.connection_brains, 'real', agents.connection_brains)), \
                mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch('taskuary.agents.run_cli', return_value=(reply, None, None)), \
                mock.patch.object(hooks, 'judge_ended', side_effect=lambda *a, **k: ended.append(a)), on_page():
            sess = general.start_session(s, tid, pick='cli:claude')
            out = sess.send_prompt('Sign me up from the invite', pick='cli:claude')
            req = ws.status(s, tid)['requests']
            info = sess.info()
        self.assertEqual(out, 'I filled in your name and email.')
        self.assertEqual(ended, [])                                          # handed over, not ended short
        self.assertEqual(len(req), 1)
        self.assertTrue(req[0]['request_id'].startswith(browserview.TURN_PREFIX))
        self.assertIn('tick the "I\'m not a robot" box', req[0]['text'])
        self.assertEqual(req[0]['choices'], [browserview.TURN_DONE])
        self.assertTrue(info['waiting'])


class TheLastFrame(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        p = mock.patch.dict(os.environ, {'TASKUARY_HOME': self.home}); p.start(); self.addCleanup(p.stop)
        browserview.LAST.pop('s1', None); browserview.FILLING.discard('s1')
        self.addCleanup(lambda: (browserview.LAST.pop('s1', None), browserview.FILLING.discard('s1')))

    def frame(self, url=PAGE): browserview.LAST['s1'] = {'frame': json.dumps({'type': 'frame', 'data': JPEG}), 'url': url, 'at': 5.0}

    def test_close_keeps_it_by_task_and_the_route_serves_it(self):
        self.frame()
        with mock.patch.object(browserview.shutil, 'which', return_value=None): browserview.close('s1', 42)
        k = browserview.last_frame(42)
        self.assertEqual((k['url'], k['at']), (PAGE, 5.0))
        self.assertEqual(k['path'].read_bytes(), base64.b64decode(JPEG))
        r = TestClient(server.app).get('/api/tasks/42/browser/last', headers={'X-Taskuary-Token': config.load()['server']['token']})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {'url': PAGE, 'at': 5.0, 'src': f'data:image/jpeg;base64,{JPEG}'})
        self.assertEqual(TestClient(server.app).get('/api/tasks/43/browser/last', headers={'X-Taskuary-Token': config.load()['server']['token']}).json(), {})

    def test_nothing_while_a_sign_in_is_typed_and_nothing_without_a_task_or_a_frame(self):
        self.frame(); browserview.FILLING.add('s1')
        self.assertFalse(browserview.keep_frame(42, 's1'))
        browserview.FILLING.discard('s1')
        self.assertFalse(browserview.keep_frame(None, 's1'))
        browserview.LAST.pop('s1')
        self.assertFalse(browserview.keep_frame(42, 's1'))
        self.assertIsNone(browserview.last_frame(42))


if __name__ == '__main__': unittest.main()
