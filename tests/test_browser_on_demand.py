"""NO URL, NO BROWSER (the owner, 2026-11-04: "no browser should open if we don't have a URL").

A general task triage read as work on the web ("find flight options") was tagged needs:browser, and every door that started its agent
launched Chrome up front on about:blank - before the agent had looked anything up. The agent searched the web with its own search,
asked the owner where, who and which dates, and the canvas was a black empty browser beside the question. Now the browser launches on
the agent's first navigate (with the owner's saved sign-ins), or on the page the task's browser was last on; never on an empty tab.
"""
import unittest
from unittest import mock

from taskuary import browserview as bv, general, hooks, terminal, workerstate as ws
from taskuary.store import MemoryStore


def flights(s, tags=bv.WANTS):
    return s.create_task({'Title': 'Find flight options for the offsite', 'Summary': 'Erin Blake asks for options', 'Kind': 'general',
                          'Status': 'open', 'Tags': tags}, 'owner')


class NothingLaunchesWithoutAnAddress(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = flights(self.s)
        p = [mock.patch.object(bv, 'installed', return_value=True), mock.patch.object(bv, 'last_page', return_value=''),
             mock.patch.object(bv, 'state', return_value={'open': False, 'url': '', 'port': 0})]
        for x in p: x.start(); self.addCleanup(x.stop)

    def _turn(self):
        from taskuary import llm as llm_mod
        session = general.GeneralSession(self.s, self.tid)
        session.pick, session.provider, session.model, session.browser_wanted = 'cli:claude', 'Claude Code (your CLI)', '', True
        seen = {}
        def build(store, **kw): seen.update(kw); return None                  # no brain: the turn stops here
        with mock.patch.object(llm_mod, 'build_llm', side_effect=build), mock.patch.object(bv, 'start', return_value=True) as started:
            with self.assertRaises(RuntimeError): session.send_prompt('go', echo=False)
        return seen, started

    def test_a_turn_on_a_browser_task_starts_no_browser_and_offers_it(self):
        seen, started = self._turn()
        started.assert_not_called()
        self.assertTrue(seen.get('cli_tools'), 'it can still RUN agent-browser - its first open launches the browser')
        self.assertIn('AGENT_BROWSER_SESSION', seen.get('extra_env') or {})

    def test_starting_the_session_launches_nothing(self):
        from taskuary import agents
        with mock.patch.object(agents, 'runs_here', lambda p: True), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(general, '_selected', return_value=('cli:claude', 'Claude Code', '')), \
             mock.patch.object(general.threading, 'Thread') as th, mock.patch.object(bv, 'start') as started:
            general.start_session(self.s, self.tid, pick='cli:claude')
            self.assertFalse([c for c in th.call_args_list if c.kwargs.get('target') is bv.start])
        started.assert_not_called()

    def test_a_terminal_on_the_task_launches_nothing_and_is_told_it_is_offered(self):
        with mock.patch.object(terminal.shutil, 'which', return_value='/usr/bin/agent-browser'):
            text = terminal.seed_text(self.s, self.tid, repo=None, cwd='')
        self.assertNotIn('A BROWSER IS OPEN', text)
        self.assertIn('agent-browser open <url>', text)

    def _restart(self):
        from taskuary import agents
        with mock.patch.object(bv, 'last_page', return_value='https://portal.example/login'),              mock.patch.object(general.threading, 'Thread') as th, mock.patch.dict(terminal.SESSIONS, {}, clear=True),              mock.patch.object(general, '_selected', return_value=('cli:claude', 'Claude Code', '')),              mock.patch.object(agents, 'runs_here', lambda p: True):
            ses = general.start_session(self.s, self.tid, pick='cli:claude')
        return ses, [c.kwargs['args'] for c in th.call_args_list if c.kwargs.get('target') is bv.start]

    def test_a_page_it_was_last_on_stays_down_when_nothing_on_it_waits_for_the_owner(self):
        # agent-flow audit 2026-11-07: "forget the portal", a restart, and Chrome came back on the dead page
        self.assertEqual(self._restart()[1], [])
        self.assertEqual(general.page_needs_owner(self.s, self.tid), '')

    def test_a_page_it_was_last_on_is_an_address(self):
        # a restart mid sign-in: the agent's ask still points at a real page, so that page opens with the session
        from taskuary import signin
        ws.record(self.s, self.tid, 'run-before', 'input_needed', request_id=f'{signin.PREFIX}portal.example', text='Sign in to the portal')
        self.assertTrue(general.page_needs_owner(self.s, self.tid))
        with mock.patch.object(bv, 'last_page', return_value='https://portal.example/login'), \
             mock.patch.object(general.threading, 'Thread') as th, mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(general, '_selected', return_value=('cli:claude', 'Claude Code', '')):
            from taskuary import agents
            with mock.patch.object(agents, 'runs_here', lambda p: True): ses = general.start_session(self.s, self.tid, pick='cli:claude')
        go = [c for c in th.call_args_list if c.kwargs.get('target') is bv.start]
        self.assertEqual([c.kwargs['args'] for c in go], [(ses.sid, 'https://portal.example/login')])


class TheFirstNavigateLaunchesIt(unittest.TestCase):
    """The agent's own `agent-browser open <url>` is the moment: the hook launches Taskuary's browser on that address first, restored
    from the owner's saved sign-ins (browserview.start), so a sign-in task opens signed in."""

    def _hook(self, cmd, open_=False):
        from taskuary import gatecmd
        with mock.patch.object(bv, 'start', return_value=True) as started, \
             mock.patch.object(bv, 'state', return_value={'open': open_, 'url': '', 'port': 0}), \
             mock.patch('taskuary.browsergate.check', return_value={}):
            gatecmd.judge(MemoryStore(), 1, 's-1', cmd)       # the server's side of the session's own `agent-browser` (gatecmd)
        return started

    def test_open_launches_on_its_address(self):
        self._hook('agent-browser open https://air.example/search?from=BOS').assert_called_once_with('s-1', 'https://air.example/search?from=BOS')
        self._hook('npx agent-browser goto "https://portal.example/login"').assert_called_once_with('s-1', 'https://portal.example/login')

    def test_no_address_no_launch(self):
        self._hook('agent-browser snapshot -i').assert_not_called()
        self._hook('agent-browser open about:blank').assert_not_called()
        self._hook('curl https://air.example/').assert_not_called()

    def test_a_magic_link_is_never_the_address_launched_before_it_is_judged(self):
        """The launch on demand ran BEFORE the gate: a first `open` of a one-click approve link launched the browser on it, and the link
        did its work while the gate was still judging it. A link that carries a token launches on its site's own page; the gate judges the rest."""
        magic = 'https://bank.example/approve?t=9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c'
        self._hook(f'agent-browser open {magic}').assert_called_once_with('s-1', 'https://bank.example/')
        self._hook('agent-browser open "javascript:document.forms[0].submit()"').assert_not_called()

    def test_an_open_browser_is_not_launched_again(self):
        self._hook('agent-browser open https://air.example/', open_=True).assert_not_called()


class TheAgentAsksForIt(unittest.TestCase):
    """A CLI with no hook to launch the browser at its first `open` asks Taskuary for the page (`taskuary --browser <url>`): on the real
    Codex CLI the agent's own launch ran inside its sandbox and died on every open (recorded, the browser round 2026-11-14). The ask
    takes the hook's own launch - one road - and nothing is launched on a turn that never asks."""
    def setUp(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.server, self.c, self.s = server, TestClient(server.app), server.store
        self.tid = flights(self.s, tags='')
        self.sess = mock.Mock(sid='s-9', alive=True, task_id=self.tid, pick='cli:codex')
        p = [mock.patch.dict(terminal.SESSIONS, {'s-9': self.sess}), mock.patch.object(bv, 'installed', return_value=True),
             mock.patch.object(general, 'browser_offered', return_value=True)]
        for x in p: x.start(); self.addCleanup(x.stop)

    def _ask(self, url, open_=False, tid=None, sid='s-9'):
        with mock.patch.object(bv, 'start', return_value=True) as started, mock.patch.object(bv, 'navigate', side_effect=lambda s, u: u) as nav, \
             mock.patch.object(bv, 'state', return_value={'open': open_, 'url': '', 'port': 0}):
            r = self.c.post('/api/agent/browser', json={'task_id': tid or self.tid, 'url': url, 'sid': sid})
        return r, started, nav

    def test_it_is_launched_on_the_address_asked_for_by_the_hooks_own_launch(self):
        r, started, nav = self._ask('https://portal.example/login?app=1')
        self.assertEqual((r.status_code, r.json()['launched']), (200, True))
        started.assert_called_once_with('s-9', 'https://portal.example/login?app=1'); nav.assert_not_called()
        self.assertIs(bv.on_demand.__globals__['launch'], bv.launch)            # the hook's road and this one are the same launch

    def test_a_browser_already_up_is_pointed_at_the_page_not_launched_again(self):
        r, started, nav = self._ask('portal.example/invoices', open_=True)
        self.assertEqual((r.status_code, r.json()['launched']), (200, False))
        started.assert_not_called(); nav.assert_called_once_with('s-9', 'https://portal.example/invoices')

    def test_a_dead_browser_the_agents_own_launch_left_is_closed_and_a_whole_one_launched(self):
        """Recorded on the real Codex CLI: the agent tried `agent-browser open` first, which died in its sandbox and left a daemon that
        answered its port with no Chrome under it - the ask then met an "open" browser that refused every command."""
        with mock.patch.object(bv, 'start', return_value=True) as started, mock.patch.object(bv, 'close') as closed, \
             mock.patch.object(bv, 'navigate', side_effect=ValueError('Auto-launch failed: CDP response channel closed')), \
             mock.patch.object(bv, 'state', return_value={'open': True, 'url': '', 'port': 5}):
            r = self.c.post('/api/agent/browser', json={'task_id': self.tid, 'url': 'https://portal.example/', 'sid': 's-9'})
        self.assertEqual((r.status_code, r.json()['launched']), (200, True))
        closed.assert_called_once_with('s-9'); started.assert_called_once_with('s-9', 'https://portal.example/')

    def test_no_page_no_launch_and_the_answer_says_why(self):
        for url in ('about:blank', 'file:///C:/x.html', ''):
            r, started, _ = self._ask(url)
            self.assertEqual(r.status_code, 422); started.assert_not_called()

    def test_a_strangers_task_and_a_task_with_no_session_get_none(self):
        with mock.patch.object(general, 'browser_offered', return_value=False):
            r, started, _ = self._ask('https://portal.example/')
        self.assertEqual(r.status_code, 403); started.assert_not_called()
        other = flights(self.s, tags='')
        r, started, _ = self._ask('https://portal.example/', tid=other, sid='nobody')
        self.assertEqual(r.status_code, 409); started.assert_not_called()

    def test_an_api_cards_agent_is_asked_of_by_the_road_it_runs_on(self):
        """The HIPAA walk, 2026-11-22: HIPAA AI's agent runs on its Codex harness and its prompt offered the browser - asked of the card's own
        pick, its first `taskuary --browser` was refused, said as "a message from someone the owner has not vouched for" on his New task."""
        self.sess.pick, self.sess.road = 'gateway:23', mock.Mock(return_value='cli:codex')
        seen = []
        with mock.patch.object(general, 'browser_offered', side_effect=lambda st, t, pick: seen.append(pick) or pick.startswith('cli:')):
            r, started, _ = self._ask('https://portal.example/')
        self.assertEqual((r.status_code, seen), (200, ['cli:codex'])); started.assert_called_once()

    def test_the_agent_is_told_of_it_in_one_sentence_where_it_is_told_its_browser(self):
        self.assertIn('taskuary --browser <url>', bv.guide()); self.assertEqual(bv.guide().count('taskuary --browser'), 1)

    def test_every_agent_is_told_one_road_whatever_its_ai(self):
        """Recorded on Codex (the browser audit, 2026-11-15): `agent-browser open` died in its sandbox launching Chrome. The session's own
        `agent-browser` asks the server before it runs (gatecmd), and the server launches the page - so every AI is told the same road."""
        for told in (bv.offer(), bv.brief(open_now=False)):
            self.assertIn('run `agent-browser open <url>` and it opens for you', told)


class YourTurnNeedsAPage(unittest.TestCase):
    def test_a_hand_over_with_no_page_is_a_question_in_words(self):
        s = MemoryStore(); tid = flights(s)
        with mock.patch.object(bv, 'state', return_value={'open': False, 'url': '', 'port': 0}):
            rid = bv.your_turn(s, tid, 's-1', 'tell me the dates')
        self.assertFalse(rid.startswith(bv.TURN_PREFIX), rid)
        with mock.patch.object(bv, 'state', return_value={'open': True, 'url': 'about:blank', 'port': 1}):
            self.assertFalse(bv.your_turn(s, tid, 's-1', 'which airport').startswith(bv.TURN_PREFIX))
        with mock.patch.object(bv, 'state', return_value={'open': True, 'url': 'https://air.example/captcha', 'port': 1}):
            self.assertTrue(bv.your_turn(s, tid, 's-1', 'tick the box').startswith(bv.TURN_PREFIX))
        asks = [e for e in ws.events(s, tid, 's-1') if e.get('Kind') == 'input_needed']
        self.assertIn('tell me the dates', asks[0]['Text'])


if __name__ == '__main__': unittest.main()
