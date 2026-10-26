"""COMPUTER USE, AS THE OWNER MEETS IT (the computer-use walk, 2026-10-25): a general agent's browser acts are held where its brain can
be held and nowhere is a hold promised that isn't there; a browser that did not open, a CLI that isn't signed in and a brain that can't
use the browser are each said; the one-time sign-in page works from Chrome, tells a refused password from a sign-in, names its task and
says the truth about what happens next."""
import json, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from taskuary import (agents, brainroute, browsergate as bg, browserview, failures, general, hooks, llm, signin, terminal, totp,
                      workerstate as ws)
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from test_general import connect_cli

USER = 'alex@northwind.example'


def browser_task(store, title='Pay the Payworth invoice'):
    return store.create_task({'Title': title, 'Summary': 'Open the vendor portal and pay it', 'Kind': 'general', 'Status': 'open',
                              'Tags': browserview.WANTS}, 'owner')


class TheGeneralAgentsBrowserIsHeld(unittest.TestCase):
    """GeneralSession has no argv and no cwd, so the hook's pane lookup never found it: Pay now went straight through on the one road
    computer-use work takes, while the brief told the agent it was held."""
    def setUp(self):
        self.s = MemoryStore(); self.tid = browser_task(self.s)
        self.sess = general.GeneralSession(self.s, self.tid)
        terminal.SESSIONS[self.sess.sid] = self.sess; self.addCleanup(terminal.SESSIONS.pop, self.sess.sid, None)
        self.pay = {'tool_name': 'Bash', 'tool_input': {'command': "agent-browser click '@e2'"}, 'session_id': 'claude-conv-1', 'cwd': ''}

    def test_its_own_hook_names_it_by_session(self):
        with mock.patch.object(bg, 'check', return_value={'held': 1}) as check:
            self.assertEqual(hooks.browser(self.pay, sid=self.sess.sid), {'held': 1})
        self.assertEqual(check.call_args.args[1:4], (self.tid, self.sess.sid, "agent-browser click '@e2'"))

    def test_the_user_wide_hook_finds_it_by_its_cli_conversation(self):
        self.sess.cli_sid = 'claude-conv-1'
        with mock.patch.object(bg, 'check', return_value={'held': 1}) as check:
            self.assertEqual(hooks.browser(self.pay), {'held': 1})
        self.assertEqual(check.call_args.args[1], self.tid)

    def test_a_session_that_is_not_ours_is_left_alone(self):
        with mock.patch.object(bg, 'check') as check:
            self.assertEqual(hooks.browser(self.pay, sid='nobody'), {})
            self.sess.alive = False
            self.assertEqual(hooks.browser(self.pay, sid=self.sess.sid), {})
        check.assert_not_called()

    def test_the_hook_file_carries_the_session_and_the_browser_matcher(self):
        f = Path(hooks.browser_settings(self.sess.sid))
        d = json.loads(f.read_text(encoding='utf-8'))
        [entry] = d['hooks']['PreToolUse']
        self.assertEqual(entry['matcher'], hooks.BROWSER_MATCH)
        self.assertIn(f'{hooks.BROWSER_MARK}?sid={self.sess.sid}', entry['hooks'][0]['command'])
        self.assertGreater(entry['hooks'][0]['timeout'], hooks.BROWSER_WAIT)

    def test_a_claude_chat_with_a_browser_gets_its_hook_and_the_hold_promise(self):
        connect_cli(self, claude={'cmd': 'claude', 'args': ['-p']})
        seen = self._turn('cli:claude')
        self.assertEqual(seen['kw'].get('hold_sid'), seen['sid'])
        self.assertIn('HELD for the owner', seen['system'])
        self.assertNotIn('CANNOT HOLD', seen['system'])

    def test_a_codex_chat_is_told_to_ask_first_never_that_it_is_held(self):
        connect_cli(self, codex={'cmd': 'codex', 'args': ['exec']})
        seen = self._turn('cli:codex')
        self.assertIsNone(seen['kw'].get('hold_sid'))
        self.assertIn('TASKUARY CANNOT HOLD YOUR BROWSER COMMANDS', seen['system'])
        self.assertNotIn('HELD for the owner', seen['system'])

    def test_claudes_argv_carries_the_hook_and_codexs_does_not(self):
        connect_cli(self, claude={'cmd': 'claude', 'args': ['-p']}, codex={'cmd': 'codex', 'args': ['exec']})
        got = {}
        def run_cli(prof, prompt, trace, **kw): got[prof['cmd']] = list(prof.get('args') or []); return ('ok', 's1', None)
        with mock.patch.object(agents, 'run_cli', run_cli):
            for cli in ('claude', 'codex'):
                llm.make_cli_llm(self.s, cli, cli_tools=True, hold_sid='abc', task_id=self.tid)('sys', 'user')
        self.assertIn('--settings', got['claude']); self.assertTrue(got['claude'][got['claude'].index('--settings') + 1].endswith('browser-abc.json'))
        self.assertNotIn('--settings', got['codex'])

    def _turn(self, pick):
        s = MemoryStore(); tid = browser_task(s)
        sess = general.GeneralSession(s, tid, pick=pick)
        seen = {'sid': sess.sid}
        def answer(system, user, **kw): seen.update(system=system); return 'Done.'
        with mock.patch.object(browserview, 'start', return_value=True), mock.patch.object(llm, 'build_llm', return_value=answer) as build:
            sess.send_prompt('Pay it', pick=pick)
        seen['kw'] = build.call_args.kwargs
        return seen


class TheBriefAndItsWords(unittest.TestCase):
    def test_refs_are_quoted_for_powershell(self):
        b = browserview.brief()
        self.assertIn("agent-browser click '@e3'", b); self.assertIn('ALWAYS QUOTE A @ref', b)
        self.assertNotIn('click @ref3', b)

    def test_a_browser_that_did_not_open_is_said_in_the_turn_and_to_the_agent(self):
        s = MemoryStore(); tid = browser_task(s)
        connect_cli(self, claude={'cmd': 'claude', 'args': ['-p']})
        sess = general.GeneralSession(s, tid, pick='cli:claude')
        seen = {}
        def answer(system, user, **kw): seen.update(system=system); return 'The browser did not open.'
        with mock.patch.object(browserview, 'start', return_value=False), mock.patch.object(browserview, 'installed', return_value=True), \
                mock.patch.object(llm, 'build_llm', return_value=answer):
            sess.send_prompt('Pay it', pick='cli:claude')
        self.assertIn('THE BROWSER DID NOT OPEN', seen['system']); self.assertIn(browserview.FAILED_WHY, seen['system'])
        self.assertNotIn('A BROWSER IS OPEN', seen['system'])
        self.assertTrue(any('The browser did not open' in str(e.get('detail')) for e in sess.trace))


class SignedOutClisAreSignIns(unittest.TestCase):
    def test_gemini_and_qwen_words_read_as_not_signed_in_with_a_fix(self):
        for said in ('session/new: Gemini API key is missing or not configured.',
                     'session/new: Authentication required: Use Qwen Code CLI to authenticate first.', 'Please set an Auth method'):
            self.assertTrue(agents._SIGNED_OUT.search(said), said)
            msg = agents.signed_out_msg('gemini', said, 'gemini')
            self.assertIn("isn't signed in on this machine", msg); self.assertNotIn('session/new', msg)
            c = failures.classify(RuntimeError(msg))
            self.assertEqual(c['fix']['label'], 'Sign it in'); self.assertFalse(c['retry'])

    def test_a_signed_out_cli_opens_no_browser_at_the_start(self):
        s = MemoryStore(); tid = browser_task(s)
        connect_cli(self, gemini={'cmd': 'gemini'})
        with mock.patch.object(agents, 'cli_tests', return_value={'gemini': False}), mock.patch.object(general.threading, 'Thread') as th:
            sess = general.start_session(s, tid, pick='cli:gemini')
        self.addCleanup(terminal.SESSIONS.pop, sess.sid, None)
        self.assertFalse([c for c in th.call_args_list if (c.kwargs.get('target') is browserview.start)])


class BrowserWorkStaysOnAShell(unittest.TestCase):
    """The router kept coding on CLIs; browser work needs hands as much, and an API backup took over a portal job with no shell."""
    def test_a_browser_tasks_chain_holds_only_clis(self):
        s = MemoryStore(); tid = browser_task(s); plain = Factory(s).task('Summarise the thread')
        route = lambda t: brainroute.choose(s, 'general', t)
        with mock.patch.object(brainroute, '_fixed', return_value=('cli:claude', '', 'main', ['connector:7', 'cli:codex'])):
            self.assertEqual(route(tid).chain, ['cli:codex'])
            self.assertEqual(route(plain).chain, ['connector:7', 'cli:codex'])


class TheHeldActInWords(unittest.TestCase):
    SNAP = '- heading "Invoice INV-1001"\n- button "Pay $412.50" [ref=e12]\n- link "Back" [ref=e3]'

    def test_the_card_names_the_control_from_the_snapshot(self):
        pg = {'url': 'https://billing.vendor.example/inv/1001', 'elements': self.SNAP}
        self.assertEqual(bg.target(bg.acts("agent-browser click '@e12'")[0], pg), 'click the "Pay $412.50" button on billing.vendor.example')
        self.assertEqual(bg.target(bg.acts('agent-browser click @e99')[0], pg), 'click an element the page no longer shows on billing.vendor.example')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual(bg.judge(MemoryStore(), bg.acts('agent-browser click @e12')[0], pg)['what'],
                             'click the "Pay $412.50" button on billing.vendor.example')

    def test_a_slow_verdict_holds_inside_the_hooks_limit(self):
        slow = lambda *a, **k: time.sleep(2) or {'hold': False, 'what': 'x', 'why': ''}
        with mock.patch.object(bg, '_judge', slow):
            t0 = time.time(); v = bg.judge(MemoryStore(), bg.acts('agent-browser click @e12')[0], {'url': 'https://x.example/'}, wait=.2)
        self.assertTrue(v['hold']); self.assertIn('did not answer in time', v['why']); self.assertLess(time.time() - t0, 1.5)
        self.assertLess(bg.JUDGE_WAIT + 20, hooks.BROWSER_WAIT)       # verdict + snapshot always land before curl gives up

    def test_approve_returns_before_the_agents_turn_and_a_failed_tell_is_on_the_task(self):
        s = MemoryStore(); tid = Factory(s).task('Pay')
        def turn(text, as_owner=True): time.sleep(1); raise RuntimeError('still answering')
        sess = SimpleNamespace(sid='r1', send_prompt=turn)
        with mock.patch.object(ws, '_live', return_value=sess):
            t0 = time.time(); bg._tell(s, tid, 'The owner approved it.'); self.assertLess(time.time() - t0, .5)
        end = time.time() + 5
        while time.time() < end and not any('could not be told' in (c.get('Body') or '') for c in s.list_comments(tid)): time.sleep(.05)
        self.assertTrue(any('could not be told' in (c.get('Body') or '') for c in s.list_comments(tid)))

    def test_a_dead_approve_says_the_way_on(self):
        with mock.patch.object(browserview, 'state', return_value={'open': False}):
            with self.assertRaises(RuntimeError) as e: bg.perform(MemoryStore(), 1, {'sid': 'r1', 'args': ['click', '@e1']})
        self.assertIn('Dismiss this, and ask the agent to open the page again', str(e.exception))


class ThePaneSaysWhatIsHappening(unittest.TestCase):
    def test_a_dead_browsers_address_is_not_the_relaunched_ones(self):
        browserview.LAST['s9'] = {'frame': '', 'url': 'http://127.0.0.1:5000/account', 'port': 5000, 'at': 0}
        self.addCleanup(browserview.LAST.pop, 's9', None)
        with mock.patch.object(browserview, '_read', side_effect=lambda n, e: '6000' if e == 'stream' else '{"url": "about:blank"}'), \
                mock.patch.object(browserview, '_listening', return_value=True):
            self.assertEqual(browserview.state('s9', fresh=True)['url'], 'about:blank')

    def test_filling_is_on_the_state_only_while_it_types(self):
        with mock.patch.object(browserview, '_read', return_value=''):
            self.assertNotIn('filling', browserview.state('s8', fresh=True))
            with browserview.filling('s8'): self.assertTrue(browserview.state('s8', fresh=True)['filling'])

    def test_a_snapshot_is_shown_in_the_conversation(self):
        s = MemoryStore(); f = Factory(s); tid = f.task('Pay'); f.message(task_id=tid)
        mid = s.list_messages(tid)[0]['MessageId']
        import base64, tempfile
        from taskuary import artifacts, session_artifacts
        d = Path(tempfile.mkdtemp())
        browserview.LAST['s7'] = {'frame': json.dumps({'type': 'frame', 'data': base64.b64encode(b'\xff\xd8jpeg').decode()}), 'url': 'https://x.example/'}
        self.addCleanup(browserview.LAST.pop, 's7', None)
        with mock.patch.object(artifacts, 'attachment_dir', return_value=d), mock.patch.object(session_artifacts, 'root', return_value=d / 'arts'):
            browserview.snapshot(s, 's7', 'owner', tid)
        self.assertEqual([a['Kind'] for a in s.list_task_artifacts(tid)], ['shown'])
        self.assertTrue(mid)


class Page:
    """A stand-in tab after the submit: the password box still up (refused) or gone (accepted)."""
    def __init__(self, password=True, href='https://login.northwind.example/'): self.pw, self.href = password, href
    def fields(self, want=''): return {'top': True, 'href': self.href, 'password': self.pw, 'otp': False}


class TheSignInPage(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll'); signin._TRIED.clear()
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': 'https://login.northwind.example/', 'port': 1}):
            signin.needs(self.s, self.tid, 'sess1')
        self.tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]

    def test_a_kept_password_box_is_not_a_sign_in(self):
        with mock.patch.object(signin.time, 'sleep'):
            self.assertFalse(signin.accepted(Page(password=True), 'northwind.example', wait=0))
            self.assertTrue(signin.accepted(Page(password=False), 'northwind.example', wait=0))
            self.assertTrue(signin.accepted(Page(password=True, href='https://idp.example/login'), 'northwind.example', wait=0))

    def test_a_refused_password_is_not_saved_nor_told_and_the_form_comes_back(self):
        def refused(*a, **k): raise signin.NotAccepted('northwind.example did not accept that password')
        with self.assertRaises(signin.NotAccepted) as e:
            signin.by_owner(self.s, self.tok, USER, 'wrong', True, fill=refused)
        self.assertIsNone(signin.saved(self.s, 'northwind.example'))
        self.assertTrue(signin.peek(self.s, e.exception.again))                 # a fresh link for the form shown again
        self.assertEqual(signin.pending(self.s, self.tid)['site'], 'northwind.example')    # the ask stays open
        self.assertFalse(any('Signed in' in (c.get('Body') or '') for c in self.s.list_comments(self.tid)))

    def test_a_refused_saved_password_says_update_it(self):
        signin.save(self.s, 'northwind.example', USER, 'stale')
        def refused(*a, **k): raise signin.NotAccepted('northwind.example did not accept that password')
        signin._auto(self.s, self.tid, 'sess1', 'northwind.example', 'signin:northwind.example', refused)
        said = ' '.join(c.get('Body') or '' for c in self.s.list_comments(self.tid))
        self.assertIn('The saved password for northwind.example did not work', said); self.assertNotIn('Signed in', said)

    def test_the_page_names_its_task_and_says_what_happens_next(self):
        line = signin.for_line(self.s, self.tid)
        self.assertTrue(line.startswith('for TQ-') and 'Pay the toll' in line)
        self.assertIn(line, signin.form_html('northwind.example', 15, task=line))
        none = signin.done_html('northwind.example', True, told=False, ref='TQ-0001')
        self.assertIn('No agent is running on TQ-0001 - open it to continue', none); self.assertNotIn('the agent goes on', none)
        self.assertIn('Settings &gt; Agent permissions &gt; Saved sign-ins', none)
        self.assertIn('the agent goes on', signin.done_html('northwind.example', False, told=True))

    def test_gone_says_used_or_expired_and_the_way_back(self):
        signin.take(self.s, self.tok)
        why, tid = signin.gone_why(self.s, self.tok)
        self.assertTrue(why.startswith('This sign-in page was used already, at ')); self.assertEqual(tid, self.tid)
        self.s._exec('UPDATE signin_token SET UsedAt=NULL, ExpiresAt=1')
        self.assertIn('expired - one lasts 15 minutes', signin.gone_why(self.s, self.tok)[0])
        self.assertIn('Open TQ-0001 in Taskuary and press Sign in here again', signin.gone_html('x', ref='TQ-0001'))

    def test_chrome_gets_a_referrer_policy_that_sends_its_origin(self):
        self.assertEqual(signin.HEADERS['Referrer-Policy'], 'same-origin')
        self.assertIn('content="same-origin"', signin.form_html('northwind.example', 15)); self.assertNotIn('no-referrer', signin.form_html('northwind.example', 15))

    def test_a_page_taskuary_cannot_fill_says_what_to_do(self):
        s = MemoryStore(); tid = Factory(s).task('Intranet')
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': 'http://intranet.northwind.example/login', 'port': 1}):
            signin.needs(s, tid, 'sx', 'intranet.northwind.example')
        txt = ws.status(s, tid)['requests'][-1]['text']
        self.assertIn('yourself in the browser pane, then say Signed in', txt); self.assertIn('secure (https)', txt)

    def test_a_bad_setup_key_is_said_in_plain_words(self):
        for bad in ('not a key!', '!!!!'):
            with self.assertRaises(totp.BadKey) as e: totp.parse(bad)
            self.assertNotIn('base32', str(e.exception)); self.assertIn("Can't scan the QR code?", str(e.exception))
        self.assertNotIn('otpauth://', signin.form_html('northwind.example', 15))


class TheFillPagesOrigin(unittest.TestCase):
    def test_null_origin_passes_only_from_the_same_origin(self):
        from taskuary import server
        self.assertTrue(server._signin_origin_ok({'origin': 'null', 'sec-fetch-site': 'same-origin'}))
        self.assertFalse(server._signin_origin_ok({'origin': 'null', 'sec-fetch-site': 'cross-site'}))
        self.assertFalse(server._signin_origin_ok({'origin': 'null'}))


class SignedInIsAPressOnEveryAgent(unittest.TestCase):
    """A terminal CLI's sign-in ask had no Signed in press, only a box - and the bare words typed into its prompt named no site and no
    "continue". Its Signed in now goes the way a fill's does (signin._continue), never as a chooser's number (2026-10-25)."""
    def test_a_terminals_signed_in_is_told_as_a_fill_is(self):
        s = MemoryStore(); tid = Factory(s).task('Pay the toll', kind='coding'); signin._TRIED.clear()
        pty = SimpleNamespace(sid='run1', alive=True, task_id=tid, agent='coding', label='Claude Code', argv=['claude'])
        typed = []
        with mock.patch.dict(terminal.SESSIONS, {'run1': pty}, clear=True),                 mock.patch.object(browserview, 'state', return_value={'open': True, 'url': 'https://login.toll.example/', 'port': 1}),                 mock.patch.object(terminal, 'type_into', lambda t, text: typed.append((t.sid, text))):
            signin.needs(s, tid, 'run1')
            self.assertEqual(ws.status(s, tid)['requests'][-1]['choices'], [])          # still no chooser on the pty: the card draws it
            out = ws.answer(s, tid, 'signin:toll.example', 'Signed in', 'owner')
            self.assertEqual(ws.status(s, tid)['requests'], [])
        self.assertTrue(out['delivered'], out)
        self.assertEqual(typed, [('run1', 'Signed in to toll.example - continue.')])
        self.assertTrue(any('Signed in to toll.example - the agent goes on.' in (c.get('Body') or '') for c in s.list_comments(tid)))

    def test_other_words_to_a_sign_in_ask_stay_the_owners(self):
        self.assertTrue(signin.said_done('signin:toll.example', ' signed in. '))
        self.assertFalse(signin.said_done('signin:toll.example', 'Signed in but it asks for a code'))
        self.assertFalse(signin.said_done('r1', 'Signed in'))


class TheLastFrameIsKeptOnlyOnAHeldOrFailedAct(unittest.TestCase):
    """The browser closes with its session: a task that stopped on Approve, or on an act the browser refused, showed nothing of the page
    it stood on. Kept then - and only then (the owner, 2026-10-25) - shown in the chat with a plain caption."""
    def setUp(self):
        import base64, tempfile
        from taskuary import session_artifacts
        from test_browser_gate import Brain, on, verdict
        self.on, self.verdict, self.Brain = on, verdict, Brain
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll invoice')
        browserview.LAST['run1'] = {'frame': json.dumps({'type': 'frame', 'data': base64.b64encode(b'\xff\xd8jpeg').decode()}), 'url': ''}
        self.addCleanup(browserview.LAST.pop, 'run1', None); self.addCleanup(browserview.ended_on, 'run1')
        for p in (mock.patch.object(session_artifacts, 'root', return_value=Path(tempfile.mkdtemp())),
                  mock.patch.object(browserview.shutil, 'which', return_value=None)):
            p.start(); self.addCleanup(p.stop)

    def act(self, cmd='agent-browser click @e12', hold=True):
        with self.on(), self.verdict({'irreversible': hold, 'sure': True, 'what': 'pays the order on toll.example'}):
            return bg.check(self.s, self.tid, 'run1', cmd, self.Brain(None))

    def kept(self):
        browserview.close('run1')
        return [(a['Kind'], a['Name'], a['ContentType']) for a in self.s.list_task_artifacts(self.tid)]

    def test_a_session_that_stops_on_a_held_act_keeps_where_it_waited(self):
        self.act(); self.act('agent-browser fill @e1 "Northwind"', hold=False)      # it went on typing; the held act still waits
        self.assertEqual(self.kept(), [('shown', 'Where the browser was when it waited for you', 'image/jpeg')])

    def test_an_act_that_failed_keeps_where_it_stopped(self):
        from taskuary import verdicts
        self.act(); [rv] = self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': 'https://pay.toll.example/somewhere-else'}):
            self.assertFalse(verdicts.decide(self.s, rv, 'approve')['ok'])
        self.assertEqual(self.kept(), [('shown', 'Where the browser was when it stopped', 'image/jpeg')])

    def test_a_normal_end_keeps_nothing(self):
        self.act(hold=False)
        self.assertEqual(self.kept(), [])

    def test_a_held_act_dismissed_before_the_end_keeps_nothing(self):
        from taskuary import verdicts
        self.act(); [rv] = self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
        with mock.patch('taskuary.workerstate._live', return_value=None): self.assertTrue(verdicts.decide(self.s, rv, 'reject')['ok'])
        self.assertEqual(self.kept(), [])


if __name__ == '__main__':
    unittest.main()
