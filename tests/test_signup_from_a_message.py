"""SIGN THE OWNER UP FROM A FORWARDED MAIL (2026-10-28). Asked to follow the registration link in "message m1073" and prepare the sign-up
for approval, a general agent failed every step and said only that it "could not verify the current page address":
- read_message and `taskuary --message` refused 'm1073' - Taskuary's own spelling of a message id - as no number, twice each;
- the task was not marked "needs a browser", so the agent was never told of Taskuary's and reached for its CLI's own browser tools;
- a page whose address the gate could not read was held with no address: never approvable, or matched blank to blank.
Now: the id is read in any spelling Taskuary writes; the browser is offered to the owner's own tasks; the page address is asked of the
browser itself; the form is typed, the submit is held for Approve/Dismiss; and every failure says why and what the owner can do.
"""
import json, time, unittest
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import browsergate as bg, browserview, cli, config, general, guard, mailsearch, server, verdicts
from taskuary.store import MemoryStore

c = TestClient(server.app)
SRV = config.load()['server']
REGISTER = 'https://events.vendor.example/webinar/register'
FORM = ('- heading "Register for the Q4 product webinar" [level=1]\n- textbox "Full name" [ref=e1]\n- textbox "Work email" [ref=e2]\n'
        '- textbox "Company" [ref=e3]\n- checkbox "Send me the recording" [ref=e4]\n- button "Register" [ref=e5]')


def hdr(tid): return {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, tid)}


def world(stranger=False):
    "The owner's task carrying the webinar mail: forwarded by the owner themselves, or (stranger) sent by a vendor nobody vouched for."
    s = MemoryStore()
    tid = s.create_task({'Title': 'Sign me up for the vendor webinar', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    who = ({'FromName': 'Webinar team', 'FromEmail': 'events@vendor.example', 'Direction': 'in'} if stranger else
           {'FromName': 'Alex Doyle', 'FromEmail': 'alex@northwind.example', 'Direction': 'out'})
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'w1', 'ConversationId': 'conv-w', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         **who, 'Subject': 'Fwd: Q4 product webinar',
                         'BodyText': f'Worth joining? Register here: {REGISTER}', 'SentAt': '2026-10-27 09:00:00', 'Status': 'routed'})
    other = s.add_message({'TaskId': None, 'ExternalId': 'w2', 'ConversationId': 'conv-x', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                           'FromName': 'Ray Colton', 'FromEmail': 'ray@northwind.example', 'Subject': 'Budget', 'BodyText': 'Numbers attached.',
                           'SentAt': '2026-10-26 09:00:00', 'Status': 'routed'})
    return s, tid, mid, other


def tool(tid, name, **args):
    r = c.post(f'/api/mcp?task={tid}', headers=hdr(tid), json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                                               'params': {'name': name, 'arguments': args}})
    assert r.status_code == 200, r.text
    res = r.json()['result']
    return res['content'][0]['text'], res['isError']


class TheMessageId(unittest.TestCase):
    def test_every_spelling_taskuary_writes_is_read(self):
        for x in ('m12', 'M12', 12, '12', ' m12 ', '[12]', '#12', '(m12)'): self.assertEqual(mailsearch.message_id(x), 12, x)

    def test_anything_else_is_said_plainly(self):
        for x in ('abc', '', None, True, 'm', '12a', 'm-12'):
            with self.assertRaises(ValueError) as e: mailsearch.message_id(x)
            self.assertIn('not a message id', str(e.exception)); self.assertIn('m1073', str(e.exception))


class ReadMessage(unittest.TestCase):
    def setUp(self):
        self.s, self.tid, self.mid, self.other = world()
        self.p = mock.patch.object(server, 'store', self.s); self.p.start()

    def tearDown(self): self.p.stop()

    def test_by_m_id_by_number_and_by_digits(self):
        for x in (f'm{self.mid}', self.mid, str(self.mid)):
            text, err = tool(self.tid, 'read_message', id=x)
            self.assertFalse(err, text); self.assertIn(REGISTER, text)

    def test_a_missing_or_malformed_id_says_what_to_do(self):
        text, err = tool(self.tid, 'read_message', id='m999999')
        self.assertTrue(err); self.assertIn('no saved message m999999', text); self.assertIn('search_messages', text)
        text, err = tool(self.tid, 'read_message', id='the webinar one')
        self.assertTrue(err); self.assertIn('not a message id', text)

    def test_a_strangers_task_reads_nothing_until_trusted_then_its_own_mail(self):
        "A full-tools session never reads an unvouched sender's words (agenttools.UNVOUCHED), nor other mail; Trust opens the task's own."
        s, tid, mid, other = world(stranger=True)
        with mock.patch.object(server, 'store', s):
            text, err = tool(tid, 'read_message', id=f'm{mid}')
            self.assertTrue(err); self.assertNotIn(REGISTER, text); self.assertIn('Trust', text)
            text, err = tool(tid, 'read_message', id=f'm{other}')
            self.assertTrue(err); self.assertNotIn('Numbers attached', text)
            self.assertIn('not vouched for', text); self.assertIn('press Trust', text)               # why, and the owner's way on
            s.update_task(tid, {'TrustedThrough': mid}, 'owner')
            text, err = tool(tid, 'read_message', id=f'm{mid}')
            self.assertFalse(err, text); self.assertIn(REGISTER, text)

    def test_the_route_and_the_cli_take_the_m_spelling(self):
        r = c.get(f'/api/agent/messages/m{self.mid}', params={'task_id': self.tid}, headers=hdr(self.tid))
        self.assertEqual(r.status_code, 200, r.text); self.assertIn(REGISTER, r.json()['body'])
        r = c.get('/api/agent/messages/m999999', params={'task_id': self.tid}, headers=hdr(self.tid))
        self.assertEqual(r.status_code, 404); self.assertIn('no saved message m999999', r.json()['detail'])
        asked = []
        args = SimpleNamespace(message=f'm{self.mid}', search=None)
        with mock.patch.dict('os.environ', {'TASKUARY_TASK': str(self.tid)}), \
                mock.patch.object(cli, '_get', lambda path, params, stranger: asked.append(path)):
            cli._history(args, False)
        self.assertEqual(asked, [f'/api/agent/messages/{self.mid}'])


class TheBrowser:
    "agent-browser stood in: a page at `url` (None: the browser cannot say where it is), `state_url` what its state file holds."
    def __init__(self, url=REGISTER, state_url='', open_=True): self.url, self.state_url, self.open, self.ran = url, state_url, open_, []
    def state(self, sid, fresh=False): return {'open': self.open, 'url': self.state_url, 'port': 1}
    def run(self, sid, args, wait, tag):
        self.ran.append(list(args))
        if args[:2] == ['get', 'url']: return (0, f'{self.url}\n') if self.url else (1, 'no page')
        if args[0] == 'snapshot': return 0, FORM
        return 0, '✓ Done'

    def __enter__(self):
        self.ps = [mock.patch.object(browserview, 'state', self.state), mock.patch.object(bg, '_run', self.run)]
        for p in self.ps: p.start()
        return self

    def __exit__(self, *a):
        for p in self.ps: p.stop()


class SignUp(unittest.TestCase):
    def setUp(self):
        self.s, self.tid, self.mid, _ = world()
        self.told = []
        self.sess = SimpleNamespace(sid='run1', send_prompt=lambda text, as_owner=True: self.told.append(text))
        self.noai = mock.patch('taskuary.llm.build_llm', return_value=None); self.noai.start()

    def tearDown(self): self.noai.stop()

    def pending(self): return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
    def check(self, cmd): return bg.check(self.s, self.tid, 'run1', cmd)

    def test_open_verify_fill_then_the_submit_waits_for_approve(self):
        with TheBrowser() as b:
            self.assertEqual(self.check(f'agent-browser open {REGISTER}'), {})                 # opening a page is a look
            self.assertEqual(bg.page('run1')['url'], REGISTER)                               # no state file: the browser itself was asked
            self.assertIn(['get', 'url'], b.ran)
            self.assertEqual(self.check('agent-browser fill @e1 "Alex Doyle" && agent-browser fill @e2 "alex@northwind.example" && '
                                        'agent-browser fill @e3 "Northwind"'), {})            # typing the form leaves nothing
            self.assertEqual(self.pending(), [])
            out = self.check('agent-browser click @e5')
        d = out['hookSpecificOutput']
        self.assertEqual(d['permissionDecision'], 'deny'); self.assertIn('held this for the owner', d['permissionDecisionReason'])
        self.assertIn('the "Register" button', d['permissionDecisionReason'])
        [rv] = self.pending()
        p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['args'], p['url']), ('browser_act', ['click', '@e5'], REGISTER))
        self.assertIn('vendor.example', p['site'])
        with TheBrowser() as b, mock.patch('taskuary.workerstate._live', return_value=self.sess):
            out = verdicts.decide(self.s, rv, 'approve')
            self.assertTrue(out['ok'], out); self.assertIn(['click', '@e5'], b.ran)
        end = time.time() + 5
        while not self.told and time.time() < end: time.sleep(.01)
        self.assertIn('The owner approved it', self.told[0])

    def test_a_page_nobody_can_name_is_not_held_and_the_agent_is_told_what_to_say(self):
        with TheBrowser(url=None): out = self.check('agent-browser click @e5')
        why = out['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('could not read which page your browser is on', why); self.assertIn('nothing was done', why)
        self.assertIn('send another message', why)
        self.assertEqual(self.pending(), [])                                                # no card that could never be approved

    def test_approve_on_a_closed_or_unnamed_browser_does_nothing_and_says_why(self):
        with TheBrowser(): self.check('agent-browser click @e5')
        [rv] = self.pending()
        for b, said in ((TheBrowser(open_=False), 'browser is closed'), (TheBrowser(url=None), 'could not read which page'),
                        (TheBrowser(url='https://events.vendor.example/other'), 'moved on')):
            with b:
                out = verdicts.decide(self.s, rv, 'approve')
                self.assertFalse(out['ok']); self.assertIn(said, out['send_error']); self.assertIn('nothing was done', out['send_error'])
                self.assertNotIn(['click', '@e5'], b.ran)
        self.assertEqual(len(self.pending()), 1)                                            # still the owner's to dismiss


class TheOffer(unittest.TestCase):
    def test_an_owners_task_on_a_cli_is_offered_the_browser(self):
        s, tid, _, _ = world()
        self.assertTrue(general.browser_offered(s, tid, 'cli:claude'))
        self.assertFalse(general.browser_offered(s, tid, 'api:openai'))                     # no shell, no browser
        s.set_setting('general_agent_hands', 'look', 'owner')
        self.assertFalse(general.browser_offered(s, tid, 'cli:claude'))                     # the owner said look only
        s2, theirs, _, _ = world(stranger=True)
        self.assertFalse(general.browser_offered(s2, theirs, 'cli:claude'))                 # a stranger's words get no browser...
        line = browserview.STRANGER_LINE.format(why='a new sender')                         # ...and its agent can say so
        self.assertIn('a new sender', line); self.assertIn('press Trust by their name', line); self.assertIn('open the link yourself', line)

    def test_the_offer_names_only_taskuarys_browser_and_asks_for_a_plain_reason(self):
        b = browserview.brief(held=True, open_now=False)
        self.assertIn('NO BROWSER IS OPEN', b); self.assertIn('agent-browser open <url>', b)
        self.assertIn('never a browser tool of your own CLI', b); self.assertIn('IF A STEP FAILS OR IS REFUSED', b)
        self.assertIn("HELD for the owner's press", b)
        self.assertIn('never a browser tool of your own CLI', browserview.brief())          # the open browser says it too
        gone = browserview.NOT_SET_UP.format(where='Connections')
        self.assertIn('The browser is not set up - install agent-browser under Connections', gone)


class TheTurn(unittest.TestCase):
    "A turn on a task nobody marked for a browser: offered (and held, on Claude), opened by the agent, the task's from then on."
    def turn(self, stranger=False, opened=False, installed=True):
        from taskuary import llm
        from test_general import connect_cli
        connect_cli(self, claude={'cmd': 'claude', 'args': ['-p']})
        s, tid, _, _ = world(stranger)
        sess = general.GeneralSession(s, tid, pick='cli:claude')
        seen = {}
        def answer(system, user, **kw): seen.update(system=system); return 'Done.'
        with mock.patch.object(browserview, 'start') as start, mock.patch.object(browserview, 'installed', return_value=installed), \
                mock.patch.object(browserview, 'state', return_value={'open': opened, 'url': REGISTER if opened else '', 'port': 1}), \
                mock.patch.object(browserview, 'keep_page'), \
                mock.patch.object(llm, 'build_llm', return_value=answer) as build:
            sess.send_prompt('Sign me up for the webinar in its mail and prepare the registration for my approval', pick='cli:claude')
        start.assert_not_called()                                                           # offered, not launched
        return s, tid, sess, seen['system'], build.call_args.kwargs

    def test_an_unmarked_owners_task_is_offered_the_browser_and_holds_it(self):
        s, tid, sess, system, kw = self.turn()
        self.assertIn('NO BROWSER IS OPEN', system); self.assertNotIn('A BROWSER IS OPEN', system)
        self.assertEqual(kw.get('hold_sid'), sess.sid)                                     # Claude's hook holds the submit
        self.assertNotIn(browserview.WANTS, str(s.get_task(tid).get('Tags') or ''))

    def test_a_browser_the_agent_opened_is_the_tasks_next_turn(self):
        s, tid, sess, _, _ = self.turn(opened=True)
        self.assertIn(browserview.WANTS, str(s.get_task(tid).get('Tags') or '')); self.assertTrue(sess.browser_wanted)

    def test_no_agent_browser_and_a_strangers_task_each_say_why(self):
        _, _, _, system, kw = self.turn(installed=False)
        self.assertIn('install agent-browser under', system); self.assertIsNone(kw.get('hold_sid'))
        _, _, _, system, _ = self.turn(stranger=True)
        self.assertIn('NO BROWSER ON THIS TASK', system); self.assertNotIn('NO BROWSER IS OPEN', system)


if __name__ == '__main__': unittest.main()
