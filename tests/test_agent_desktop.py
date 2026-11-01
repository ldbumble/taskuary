"""AGENT DESKTOP (agentdesktop.py, the owner 2026-10-31): Vercel's agent-desktop as a built-in connector. Off until its card is on; never
on a stranger's task; a look passes, any other act is judged over the control it names, and what can't be undone waits as a proposal
the owner approves - which runs that exact command - or dismisses. The same shape as the browser's gate (test_browser_gate.py)."""
import json, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import agentdesktop as ad, clis, hooks, proposals, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from test_browser_gate import Brain, verdict

SEND = "agent-desktop click '@s8f3k2p9:e8'"
BUTTON = {'role': 'button', 'name': 'Send'}


def turn_on(s, on=True): s.cx.execute('UPDATE connector SET Active=? WHERE Type=?', (1 if on else 0, ad.TYPE))
def installed(where=r'C:\npm\agent-desktop.cmd'): return mock.patch.object(ad, 'path', return_value=where)
def names(ctl=BUTTON): return mock.patch.object(ad, 'control', return_value=ctl)


class ItIsATool(unittest.TestCase):
    def test_a_tool_with_its_install_line_never_an_agent(self):
        with mock.patch('shutil.which', return_value=None):
            t = {x['name']: x for x in clis.tools()}['agent-desktop']
            self.assertEqual((t['installed'], t['install'], t['license'], t['url']),
                             (False, 'npm install -g agent-desktop', 'Apache-2.0', 'https://github.com/vercel-labs/agent-desktop'))
            self.assertEqual([r for r in clis.detect(MemoryStore()) if r['name'] == 'agent-desktop'], [])

    def test_its_card_is_in_the_catalogue_and_seeded_off(self):
        from importlib import resources
        cat = json.loads(resources.files('taskuary').joinpath('connectorcatalog.json').read_text(encoding='utf-8'))
        [c] = [c for c in cat['cards'] if c['type'] == ad.TYPE]
        self.assertEqual((c['group'], c['planned']), ('Agent tools', False))
        s = MemoryStore()
        self.assertFalse(s.get_connector_by_type(ad.TYPE)['Active'])
        with installed(): self.assertFalse(ad.on(s))                           # off by default, installed or not
        turn_on(s)
        with installed(): self.assertTrue(ad.on(s))
        with installed(''): self.assertFalse(ad.on(s))                         # on, but not on this computer: nobody is told of it

    def test_the_cards_test_says_the_version_and_the_grant(self):
        said = '{"version":"2.5","ok":true,"command":"status","data":{"permissions":{"accessibility":{"state":"granted"}},"platform":"windows","version":"1.0.2"}}'
        with mock.patch.object(ad, '_run', return_value=(0, said)): self.assertEqual(ad.test(), 'agent-desktop 1.0.2 on windows - accessibility granted')
        with installed(''), self.assertRaises(RuntimeError) as e: ad.test()
        self.assertIn('npm install -g agent-desktop', str(e.exception))


class Reading(unittest.TestCase):
    def test_looks_are_not_acts(self):
        for cmd in ('agent-desktop snapshot --app Notepad -i --compact', 'agent-desktop list-apps', "agent-desktop get '@s1:e2' --property text",
                    'agent-desktop skills get desktop', 'git status', 'grep -r agent-desktop docs', 'agent-desktop --session s1 find --role button'):
            self.assertEqual(ad.acts(cmd), [], cmd)

    def test_every_other_command_is_an_act_however_it_is_spelled(self):
        self.assertEqual([a['verb'] for a in ad.acts("agent-desktop set-value '@s1:e1' hi && agent-desktop click '@s1:e2'")], ['set-value', 'click'])
        self.assertEqual(ad.acts('npx -y agent-desktop@1.0.2 press ctrl+enter')[0]['args'], ['press', 'ctrl+enter'])     # a pinned version too
        self.assertEqual(ad.acts(r'& "C:\npm\agent-desktop.cmd" close-app Notepad')[0]['verb'], 'close-app')
        self.assertEqual(ad.acts('powershell -Command "agent-desktop click \'@s1:e2\'"')[0]['verb'], 'click')
        self.assertEqual(ad.acts('agent-desktop --headed --session s1 type @s1:e1 x')[0]['verb'], 'type')
        self.assertEqual(ad.acts('agent-desktop click "@s1:e2')[0]['verb'], '?')          # cannot be read: judged, never waved through

    def test_plain_typing_is_read_from_the_verb(self):
        self.assertTrue(ad.typing(ad.acts("agent-desktop set-value '@s1:e1' 'Dear Erin'")[0]))
        self.assertFalse(ad.typing(ad.acts("agent-desktop set-value '@s1:e1' 'line one\nline two'")[0]))      # a line break can be its Enter
        self.assertFalse(ad.typing(ad.acts("agent-desktop click '@s1:e1'")[0]))

    def test_what_says_the_control_it_names(self):
        a = ad.acts(SEND)[0]
        self.assertEqual(ad.what(a, BUTTON), 'click the "Send" button')
        self.assertEqual(ad.what(a, {}), 'agent-desktop click @s8f3k2p9:e8')


class Judging(unittest.TestCase):
    def setUp(self): self.s = MemoryStore(); self.act = ad.acts(SEND)[0]

    def test_the_model_reads_the_control_and_the_command(self):
        b = Brain(None)
        with verdict({'irreversible': True, 'sure': True, 'what': 'sends the reply in the mail app'}):
            self.assertEqual(ad.judge(self.s, self.act, BUTTON, b), {'hold': True, 'what': 'sends the reply in the mail app', 'why': "it can't be undone"})
        self.assertIn('"Send"', b.seen[0]); self.assertIn('agent-desktop click @s8f3k2p9:e8', b.seen[0])

    def test_unsure_unread_or_unjudged_is_a_hold_and_no_ai_lets_only_typing_through(self):
        for v in ({'irreversible': False, 'sure': False}, {'nonsense': 1}, RuntimeError('timed out')):
            with verdict(v): self.assertTrue(ad.judge(self.s, self.act, BUTTON, Brain(None))['hold'], v)
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertTrue(ad.judge(self.s, self.act, BUTTON)['hold'])
            self.assertFalse(ad.judge(self.s, ad.acts("agent-desktop set-value '@s1:e1' hi")[0], {})['hold'])


class Holding(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Reply to Erin about the Payworth invoice'); turn_on(self.s)
        self.told = []
        self.sess = SimpleNamespace(sid='run1', send_prompt=lambda text, as_owner=True: self.told.append(text))

    def check(self, cmd=SEND, v=None):
        with installed(), names(), verdict(v or {'irreversible': True, 'sure': True, 'what': 'sends the reply in the mail app'}):
            return ad.check(self.s, self.tid, 'run1', cmd, Brain(None))

    def heard(self):
        end = time.time() + 5
        while not self.told and time.time() < end: time.sleep(.01)
        return self.told

    def pending(self): return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
    def denied(self, out): return out['hookSpecificOutput']['permissionDecision'] == 'deny'

    def test_off_every_act_is_refused_and_a_look_still_passes(self):
        turn_on(self.s, False)
        self.assertTrue(self.denied(self.check()))
        self.assertIn('Agent Desktop is off', self.check()['hookSpecificOutput']['permissionDecisionReason'])
        self.assertEqual(self.check('agent-desktop snapshot --app Notepad -i'), {})
        self.assertEqual(self.pending(), [])

    def test_a_strangers_task_never_drives_the_desktop(self):
        with mock.patch('taskuary.origin.of_task', return_value=('stranger', 'a sender nobody vouched for')):
            out = self.check(v={'irreversible': False, 'sure': True, 'what': 'types'})
        self.assertTrue(self.denied(out)); self.assertIn('not vouched for', out['hookSpecificOutput']['permissionDecisionReason'])

    def test_an_irreversible_act_is_refused_and_put_on_the_task_once(self):
        out = self.check()
        self.assertTrue(self.denied(out)); self.assertIn('held this for the owner', out['hookSpecificOutput']['permissionDecisionReason'])
        [rv] = self.pending()
        p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['sid'], p['args'], p['command']), ('desktop_act', 'run1', ['click', '@s8f3k2p9:e8'], 'agent-desktop click @s8f3k2p9:e8'))
        self.assertIn('on your desktop: sends the reply in the mail app', rv['Reason'])
        self.check(); self.assertEqual(len(self.pending()), 1)

    def test_a_reversible_act_runs_and_nothing_is_queued(self):
        self.assertEqual(self.check("agent-desktop set-value '@s1:e1' 'Dear Erin'", {'irreversible': False, 'sure': True, 'what': 'types'}), {})
        self.assertEqual(self.pending(), [])

    def test_an_agent_cannot_propose_one_itself(self):
        self.assertEqual(proposals.parse('TASKUARY-PROPOSE {"action": "desktop_act", "sid": "run1", "args": ["click", "@s1:e8"]}'), [])

    def test_approve_runs_that_exact_command_and_tells_the_agent(self):
        self.check(); [rv] = self.pending()
        ran = []
        with installed(), mock.patch('taskuary.workerstate._live', return_value=self.sess), \
                mock.patch.object(ad, '_run', lambda args, wait, tag: ran.append(args) or (0, '{"ok":true,"command":"click","data":{}}')):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertTrue(out['ok'], out)
        self.assertEqual(ran, [['click', '@s8f3k2p9:e8']])
        self.assertIn('The owner approved it', self.heard()[0])
        self.assertEqual(self.pending(), [])

    def test_a_control_gone_since_is_not_pressed_on_a_guess(self):
        self.check(); [rv] = self.pending()
        stale = '{"ok":false,"command":"click","error":{"code":"STALE_REF","message":"@s8f3k2p9:e8 not found in current RefMap"}}'
        with installed(), mock.patch.object(ad, '_run', return_value=(1, stale)):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertFalse(out['ok']); self.assertIn('nothing was done', out['send_error'])
        self.assertEqual(len(self.pending()), 1)

    def test_dismiss_tells_the_agent_it_was_not_done(self):
        self.check(); [rv] = self.pending()
        with mock.patch('taskuary.workerstate._live', return_value=self.sess), mock.patch.object(ad, '_run') as run:
            self.assertTrue(verdicts.decide(self.s, rv, 'reject')['ok'])
        run.assert_not_called()
        self.assertIn('did not approve it', self.heard()[0])


class Hook(unittest.TestCase):
    def test_the_shell_hook_routes_desktop_acts_of_our_panes(self):
        s = MemoryStore(); tid = Factory(s).task('Reply to Erin'); turn_on(s)
        pane = SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd=r'C:\work', argv=['claude'], ext_id='c-1', resumed_from='', store=s)
        send = {'tool_name': 'PowerShell', 'tool_input': {'command': SEND}, 'session_id': 'c-1', 'cwd': r'C:\work'}
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': pane}, clear=True), installed(), names(), \
                verdict({'irreversible': True, 'sure': True, 'what': 'sends'}):
            self.assertEqual(hooks.browser({**send, 'tool_input': {'command': 'agent-desktop list-apps'}}, Brain(None)), {})
            self.assertEqual(hooks.browser({**send, 'session_id': 'someone-else'}, Brain(None)), {})       # not our pane
            self.assertEqual(hooks.browser(send, Brain(None))['hookSpecificOutput']['permissionDecision'], 'deny')


class Brief(unittest.TestCase):
    def test_the_hold_is_promised_only_where_there_is_one(self):
        self.assertIn('HELD for the owner', ad.brief(held=True)); self.assertNotIn('CANNOT HOLD', ad.brief(held=True))
        self.assertIn('CANNOT HOLD', ad.brief(held=False)); self.assertNotIn('HELD for the owner', ad.brief(held=False))
        self.assertIn('never pass --headed', ad.brief().replace('NEVER', 'never'))

    def test_offered_only_when_the_card_is_on(self):
        s = MemoryStore(); tid = Factory(s).task('Reply to Erin')
        with installed(), mock.patch('taskuary.general.browser_offered', return_value=True):
            self.assertFalse(ad.offered(s, tid, 'cli:claude'))
            turn_on(s); self.assertTrue(ad.offered(s, tid, 'cli:claude'))
        with installed(), mock.patch('taskuary.general.browser_offered', return_value=False):      # the dock, a stranger, an API brain
            self.assertFalse(ad.offered(s, tid, 'connector:3'))


if __name__ == '__main__': unittest.main()
