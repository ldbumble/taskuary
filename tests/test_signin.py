"""SIGNING IN FOR THE BROWSER AGENT (signin.py): the page's own origin decides where a password goes, never the agent's word or a
mail's; a fill link works once and not for long; nothing typed reaches a prompt, a log, the audit or a comment; a sign-in is kept only
when the owner ticks it, sealed, and filled by itself next time; Remove takes the password and the site's cookies with it."""
import json, os, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest import mock
import pytest
from fastapi.testclient import TestClient
from loguru import logger

from taskuary import browserview, config, selfclose, server, signin, vault, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

PW, USER = 'correct-horse-9!', 'alex@northwind.example'
c = TestClient(server.app)
AGENT = {'X-Taskuary-Token': config.load()['server']['agent_token']}


class FakeKeyring:
    def __init__(self): self.d = {}
    def set_password(self, s, k, v): self.d[(s, k)] = v
    def get_password(self, s, k): return self.d.get((s, k))
    def delete_password(self, s, k): self.d.pop((s, k), None)


# a saved sign-in is sealed somewhere real: DPAPI on Windows, an in-memory keychain elsewhere (CI's Linux and macOS have none)
def setUpModule():
    if sys.platform != 'win32':
        p = mock.patch.object(vault, '_keyring', return_value=FakeKeyring()); p.start(); unittest.addModuleCleanup(p.stop)


def on_page(url): return mock.patch.object(browserview, 'state', return_value={'open': True, 'url': url, 'port': 1})


class Sites(unittest.TestCase):
    def test_a_name_under_the_site_is_the_site(self):
        self.assertTrue(signin.on_site('https://login.bank.example/auth?x=1', 'bank.example'))
        self.assertTrue(signin.on_site('https://bank.example/', 'bank.example'))
        self.assertEqual(signin.site_of('https://www.bank.co.uk/login'), 'bank.co.uk')       # not co.uk: that would be every UK site

    def test_a_lookalike_is_another_site(self):
        for url in ('https://bank.example.evil.example/', 'https://bank-example.example/', 'https://evilbank.example/',
                    'https://xn--bnk-sna.example/', 'https://bаnk.example/',              # a Cyrillic а: its punycode is another name
                    'https://bank.example@evil.example/'):                                 # the user-info is not the host
            self.assertFalse(signin.on_site(url, 'bank.example'), url)

    def test_only_https_and_a_local_app_are_places_a_password_goes(self):
        self.assertEqual(signin.site_of('http://bank.example/login'), '')
        self.assertEqual(signin.site_of('javascript:alert(1)'), '')
        self.assertEqual(signin.site_of('file:///C:/x.html'), '')
        self.assertEqual(signin.site_of('http://127.0.0.1:8765/'), '127.0.0.1')

    def test_shared_hosting_siblings_are_not_one_site(self):
        self.assertEqual(signin.site_of('https://alice.github.io/'), 'alice.github.io')
        self.assertFalse(signin.on_site('https://mallory.github.io/', 'alice.github.io'))
        self.assertEqual(signin.registrable('co.uk'), '')                                  # a bare suffix belongs to nobody

    def test_the_marker_is_read_and_never_shown(self):
        self.assertEqual(selfclose.signin_marker('Opened the portal.\n[[TASKUARY-SIGNIN: bank.example]]'), ('Opened the portal.', 'bank.example'))
        self.assertEqual(selfclose.signin_marker('nothing here'), ('nothing here', None))
        self.assertNotIn('SIGNIN', selfclose.for_screen('going to sign in [[TASKUARY-SIGNIN: bank.example]]'))


class Links(unittest.TestCase):
    def setUp(self): self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll')

    def test_a_link_works_once_and_only_its_hash_is_kept(self):
        tok = signin.mint(self.s, self.tid, 'sid1', 'bank.example', 'signin:bank.example')
        self.assertEqual(signin.peek(self.s, tok)['Site'], 'bank.example')
        self.assertEqual(signin.peek(self.s, tok)['Site'], 'bank.example')               # reading does not spend it
        self.assertIsNotNone(signin.take(self.s, tok))
        self.assertIsNone(signin.take(self.s, tok))
        self.assertIsNone(signin.peek(self.s, tok))
        self.assertNotIn(tok, json.dumps(self.s._rows('SELECT * FROM signin_token')))

    def test_a_link_expires(self):
        tok = signin.mint(self.s, self.tid, 'sid1', 'bank.example', 'signin:bank.example')
        with mock.patch.object(signin, '_now', return_value=time.time() + signin.TTL + 1):
            self.assertIsNone(signin.peek(self.s, tok))
            self.assertIsNone(signin.take(self.s, tok))
        self.assertIsNone(signin.take(self.s, 'not-a-token'))

    def test_two_presses_at_once_spend_it_once(self):
        tok = signin.mint(self.s, self.tid, 'sid1', 'bank.example', 'signin:bank.example')
        got = []
        ts = [threading.Thread(target=lambda: got.append(signin.take(self.s, tok))) for _ in range(6)]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertEqual(sum(1 for g in got if g), 1)


class FakePage:
    """A stand-in for the browser tab: where it is, what it has, and everything typed into it."""
    def __init__(self, href='https://login.bank.example/', password=True, user=True, top=True, frames=(), moves_to=None, two_step=False):
        self.href, self.pw, self.user, self.top, self.frames_, self.moves_to, self.two_step = href, password, user, top, list(frames), moves_to, two_step
        self.typed, self.focus, self.looks = [], None, 0
    def fields(self, want=''):
        self.looks += 1
        if want: self.focus = want
        return {'href': self.href, 'origin': self.href, 'top': self.top, 'password': self.pw, 'user': self.user, 'frames': self.frames_,
                'focused': bool(want) and (self.pw if want == 'password' else self.user)}
    def js(self, expr):
        if self.moves_to: self.href = self.moves_to                 # the page navigated after the box was focused
        return {'href': self.href, 'password': self.focus == 'password'}
    def type(self, text): self.typed.append((self.focus, text))
    def enter(self):
        self.typed.append((self.focus, '<enter>'))
        if self.two_step and self.focus == 'user': self.pw = True


class Filling(unittest.TestCase):
    def test_it_types_into_the_pinned_site(self):
        p = FakePage()
        signin.fill_page(p, 'bank.example', USER, PW)
        self.assertEqual(p.typed, [('user', USER), ('password', PW), ('password', '<enter>')])

    def test_a_two_step_sign_in_waits_for_its_password_page(self):
        p = FakePage(password=False, two_step=True)
        with mock.patch.object(signin.time, 'sleep'): signin.fill_page(p, 'bank.example', USER, PW, wait=5)
        self.assertEqual(p.typed, [('user', USER), ('user', '<enter>'), ('password', PW), ('password', '<enter>')])

    def test_another_site_gets_nothing(self):
        for p in (FakePage(href='https://bank.example.evil.example/'), FakePage(href='https://evil.example/'), FakePage(top=False),
                  FakePage(href='http://bank.example/')):
            with self.assertRaises(signin.SignInError): signin.fill_page(p, 'bank.example', USER, PW)
            self.assertEqual(p.typed, [])

    def test_a_page_that_moves_under_the_password_gets_no_password(self):
        p = FakePage(moves_to='https://evil.example/')
        with self.assertRaises(signin.SignInError): signin.fill_page(p, 'bank.example', USER, PW)
        self.assertNotIn(PW, [t for _, t in p.typed])

    def test_a_form_that_also_asks_for_a_third_box_says_so_instead_of_blaming_the_password(self):
        """A portal's sign-in asked for a Customer ID beside the email and password; Taskuary keeps two, the form stayed up, and the
        saved password was called wrong (the browser-agent walk, 2026-11-04). The box it also needs is named."""
        p = FakePage(); f = p.fields
        p.fields = lambda want='': {**f(want), 'others': ['Customer ID']}
        out = signin.fill_page(p, 'bank.example', USER, PW)
        self.assertEqual(out['others'], ['Customer ID'])
        said = signin.refused('bank.example', out['others'])
        self.assertIn("bank.example also asks for 'Customer ID'", said); self.assertNotIn('did not accept that password', said)
        self.assertEqual(signin.refused('bank.example', []), 'bank.example did not accept that password')

    def test_a_saved_sign_in_with_no_user_name_says_so_instead_of_blaming_the_password(self):
        """A sign-up whose user name no box named (a wizard asked the email a page earlier) is kept with its password alone. Signing in with
        it, only the password went in, the form stayed up, and the owner was told "The saved password ... did not work" - it was right."""
        class Page(FakePage):
            def __init__(self): super().__init__(); self.cleared = False
            def js(self, expr): return {} if expr == signin.CLEAR else super().js(expr)
            def close(self): pass
        s = MemoryStore(); tid = Factory(s).task('Market data'); signin.save(s, 'bank.example', '', PW)
        with mock.patch.object(signin, 'connect', return_value=Page()), mock.patch.object(browserview, 'filling', mock.MagicMock()), \
             mock.patch.object(signin, 'SETTLE', 0), mock.patch.object(signin, 'accepted', return_value=False), \
             mock.patch.object(signin, 'asks_code', return_value=False):
            asked = []
            signin._auto(s, tid, 'sess1', 'bank.example', 'signin:bank.example', signin.type_in, lambda said=None: asked.append(said))
        said = ' '.join(c['Body'] for c in s.list_comments(tid))
        self.assertIn('user name', said); self.assertNotIn('did not work', said)
        self.assertEqual(asked, [], 'a saved sign-in the site refused goes back to the agent, never to him')

    def test_a_third_box_the_vault_keeps_is_filled_by_its_label_before_the_user_name(self):
        p = FakePage(); f = p.fields
        def fields(want=''):
            d = f(want if not want.startswith('other:') else '')
            if want.startswith('other:'): p.focus = want; d['focused'] = True
            return {**d, 'others': [] if any(w == 'other:Account code' for w, _ in p.typed) else ['Account code']}
        p.fields = fields
        out = signin.fill_page(p, 'bank.example', USER, PW, extra={'account CODE': 'NW-0042'})
        self.assertEqual(p.typed[:3], [('other:Account code', 'NW-0042'), ('user', USER), ('password', PW)])
        self.assertEqual(out['others'], [])

    def test_a_form_inside_another_sites_frame_is_refused_and_said(self):
        p = FakePage(password=False, user=False, frames=['https://idp.evil.example/login'])
        with self.assertRaises(signin.SignInError) as e: signin.fill_page(p, 'bank.example', USER, PW)
        self.assertIn('frame from another site', str(e.exception))
        self.assertEqual(p.typed, [])


class Asking(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll'); self.sid = 'sess1'
        signin._TRIED.clear()
        self.logs = []; self.h = logger.add(lambda m: self.logs.append(str(m)), level='DEBUG')

    def tearDown(self): logger.remove(self.h)

    def everything_written(self) -> str:
        rows = [self.s._rows(f'SELECT * FROM {t}') for t in ('audit', 'comment', 'worker_event', 'signin_token')]
        vault_rows = self.s._rows('SELECT * FROM signin_vault')
        return json.dumps(rows, default=str) + json.dumps(vault_rows, default=str) + '\n'.join(self.logs)

    def wait_for(self, pred, secs=5):
        end = time.time() + secs
        while time.time() < end and not pred(): time.sleep(.02)
        self.assertTrue(pred())

    def test_the_site_is_the_pages_not_the_agents_word(self):
        with on_page('https://login.bank.example/'): out = signin.needs(self.s, self.tid, self.sid, 'evil.example')
        self.assertEqual(out, {'site': 'bank.example', 'auto': False})
        req = ws.status(self.s, self.tid)['requests'][-1]
        self.assertEqual((req['request_id'], req['text']), ('signin:bank.example', 'Sign in to bank.example to continue'))
        self.assertEqual(signin.pending(self.s, self.tid)['site'], 'bank.example')
        self.assertEqual(signin.phone_line(self.s, self.tid), 'Sign in to bank.example on your PC to continue')

    def test_no_sign_in_page_no_fill_ever(self):
        with on_page('http://bank.example/'): out = signin.needs(self.s, self.tid, self.sid, 'bank.example')
        self.assertEqual(out['site'], '')
        self.assertIsNone(signin.pending(self.s, self.tid))
        with self.assertRaises(LookupError): signin.link(self.s, self.tid)

    def test_save_is_off_unless_ticked(self):
        self.assertIn('<input type="checkbox" name="save" value="1">', signin.form_html('bank.example', 15))
        self.assertNotIn('checked', signin.form_html('bank.example', 15))
        with on_page('https://login.bank.example/'): signin.needs(self.s, self.tid, self.sid)
        typed = []
        tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]
        out = signin.by_owner(self.s, tok, USER, PW, False, fill=lambda *a: typed.append(a))
        self.assertEqual((out['saved'], typed), (False, [(self.sid, 'bank.example', USER, PW)]))
        self.assertIsNone(signin.saved(self.s, 'bank.example'))
        self.assertNotIn(PW, self.everything_written())

    def test_a_ticked_save_is_sealed_and_fills_by_itself_next_time(self):
        with on_page('https://login.bank.example/'): signin.needs(self.s, self.tid, self.sid)
        tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]
        self.assertTrue(signin.by_owner(self.s, tok, USER, PW, True, fill=lambda *a: None)['saved'])
        row = signin.saved(self.s, 'bank.example')
        self.assertTrue(vault.sealed(row['Secret']) and vault.sealed(row['User']))
        self.assertEqual(vault.unseal(row['Secret']), PW)
        # ...the agent asks again on another task, on the same site: the server types it, the owner does nothing
        t2, typed = Factory(self.s).task('Pay the next toll'), []
        with on_page('https://www.bank.example/signin'): out = signin.needs(self.s, t2, 'sess2', 'bank.example', fill=lambda *a: typed.append(a))
        self.assertTrue(out['auto'])
        self.wait_for(lambda: any(r['Action'] == 'signin_fill' and r['EntityId'] == t2 for r in self.s._rows('SELECT * FROM audit')))
        self.assertEqual(typed, [('sess2', 'bank.example', USER, PW)])
        audit = [json.loads(r['Detail']) for r in self.s._rows("SELECT * FROM audit WHERE Action='signin_fill' AND EntityId=?", (t2,))]
        self.assertEqual(audit, [{'site': 'bank.example', 'how': 'vault', 'ok': True}])
        self.assertIsNotNone(signin.saved(self.s, 'bank.example')['LastUsed'])
        self.assertNotIn(PW, self.everything_written())
        self.assertNotIn(USER, json.dumps(signin.listing(self.s)))
        # ...and a site that asks AGAIN minutes later is not tried twice
        with on_page('https://www.bank.example/signin'): self.assertFalse(signin.needs(self.s, t2, 'sess2', fill=lambda *a: typed.append(a))['auto'])

    def test_a_saved_sign_in_goes_straight_in_and_never_asks_the_owner(self):
        """The owner's ruling (2026-11-05): with the sign-in saved, the run goes straight in. An open `signin:` ask is what draws the
        browser on the owner's screen, so none is ever raised - not even for the seconds the server types."""
        signin.save(self.s, 'bank.example', USER, PW)
        class Chat:
            sid, alive, task_id = 'sess1', True, None
            def __init__(self): self.said = []
            def send_prompt(self, text, as_owner=True): self.said.append(text)
        sess, typed, raised, rec = Chat(), [], [], ws.record
        sess.task_id = self.tid
        def spy(store, tid, sid, kind, request_id=None, *a, **k):
            if kind == 'input_needed': raised.append(request_id)
            return rec(store, tid, sid, kind, request_id, *a, **k)
        def fill(*a, **k):
            raised.append(('open while typing', signin.pending(self.s, self.tid))); typed.append(a)
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}),              mock.patch.object(ws, 'record', spy):
            self.assertTrue(signin.needs(self.s, self.tid, 'sess1', 'bank.example', fill=fill)['auto'])
            # ...the answer that handed the sign-in over is filed a moment after the ask (general._file), as the saved one goes in
            from taskuary import conversation, general
            self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'The sign-in page is open. Once you have signed in I will read the balance.')
            self.wait_for(lambda: sess.said)
        # ...and is a step of the work, never an answer telling him to sign in where nobody was asked to (the recorded walk, 2026-11-11)
        # ...read once its taking back is written down (take_back follows the prompt it sent - on a slow runner a read between the two found
        # the answer not yet taken back, macOS 2026-11-12): waited on as state, never a sleep
        last = lambda: next((x for x in reversed(conversation.items(self.s, self.tid)['items']) if x['kind'] == 'turn'), None)
        self.wait_for(lambda: (last() or {}).get('steps'), secs=15)
        turn = last()
        self.assertEqual((turn['text'], [st['text'] for st in turn['steps']][-1]), ('', 'Signed in to bank.example with the saved sign-in.'))
        self.assertEqual(typed, [('sess1', 'bank.example', USER, PW)])
        self.assertEqual(raised, [('open while typing', None)])
        self.assertIsNone(signin.pending(self.s, self.tid))
        self.assertEqual(sess.said, ["Signed in to bank.example - continue. Taskuary signed in with the owner's saved sign-in; the owner did nothing on the page."])

    def test_while_the_saved_sign_in_is_typed_the_chat_reads_at_work_over_the_answer_that_handed_it_over(self):
        """Recorded on the real CLI (the browser audit, 2026-11-15): the agent's turn ended asking for the sign-in, its answer was filed, and
        for the ~3 s Taskuary typed the saved one the chat's payload said nothing was at work - the header read "agent waiting on you" with
        nothing on him. A turn whose answer is filed after the newest hand-over is finished, but the typing is a hand-over on its way to the
        next turn (general.starting): the chat reads at work from the start of the typing until the agent is told."""
        import threading
        from taskuary import conversation, general
        signin.save(self.s, 'bank.example', USER, PW)
        class Chat:
            sid, alive, task_id = 'sess1', True, self.tid
            def __init__(self): self.said = []
            def send_prompt(self, text, as_owner=True): self.said.append(text)
        sess, typing, go = Chat(), threading.Event(), threading.Event()
        def fill(*a, **k): typing.set(); go.wait(10)
        def working():     # ...read as the chat reads it, the turn at work its last
            with mock.patch.dict('taskuary.terminal.SESSIONS', clear=True):
                c = conversation.items(self.s, self.tid); turn = next(x for x in reversed(c['items']) if x['kind'] == 'turn')
                return c['working'] and turn['state'] == 'working'
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            self.assertTrue(signin.needs(self.s, self.tid, 'sess1', 'bank.example', fill=fill)['auto'])
            self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'I need the site signed in to go on.')
            self.assertTrue(typing.wait(10))
            self.assertTrue(working(), 'at work while the saved sign-in is typed, over the answer that handed it over')
            # ...and the chat's session says so of itself, where the header and the rail read it: not parked waiting on him
            parked = general.GeneralSession.__new__(general.GeneralSession)
            parked.alive, parked.busy, parked.spoke, parked.task_id = True, False, True, self.tid
            self.assertFalse(parked.waiting(), 'the session is not waiting on him while the saved sign-in is typed')
            go.set(); self.wait_for(lambda: sess.said)
            self.wait_for(lambda: not general.starting(self.tid), secs=15)
        self.assertTrue(parked.waiting(), 'and waits on him again once it has handed on')

    def test_while_the_saved_sign_in_is_typed_the_answer_that_handed_it_over_is_already_a_step(self):
        """Recorded (the browser round, 2026-11-14): the agent ended its turn "I have no saved sign-in for it ... once the sign-in is done I
        will read it", and for the seconds Taskuary typed the saved one that stood in the chat as its answer - untrue, and gone a beat
        later. It is a step of the work from the moment the saved sign-in starts, under a line that says what is happening; the line
        says how it ended once it has."""
        import threading
        from taskuary import conversation, general
        signin.save(self.s, 'bank.example', USER, PW)
        class Chat:
            sid, alive, task_id = 'sess1', True, self.tid
            def __init__(self): self.said = []
            def send_prompt(self, text, as_owner=True): self.said.append(text)
        sess, typing, go = Chat(), threading.Event(), threading.Event()
        def fill(*a, **k): typing.set(); go.wait(10)
        def last():        # ...read as the chat reads it; the stand-in session is no session to read steps from
            with mock.patch.dict('taskuary.terminal.SESSIONS', clear=True):
                return next((x for x in reversed(conversation.items(self.s, self.tid)['items']) if x['kind'] == 'turn'), None)
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            self.assertTrue(signin.needs(self.s, self.tid, 'sess1', 'bank.example', fill=fill)['auto'])
            # ...the answer is filed a moment after the ask (general._file), while the saved one is going in
            self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'I have no saved sign-in for it. Once the sign-in is done I will read the balance.')
            self.assertTrue(typing.wait(10))
            turn = last()
            self.assertEqual((turn['text'], [st['text'] for st in turn['steps']][-1]), ('', 'Signing in to bank.example with the saved sign-in.'))
            go.set(); self.wait_for(lambda: sess.said)
            self.wait_for(lambda: [st['text'] for st in last()['steps']][-1] == 'Signed in to bank.example with the saved sign-in.', secs=15)
        self.assertEqual(last()['text'], '')

    def test_an_answer_taken_back_on_a_chat_already_in_its_log_is_a_step_and_says_how_it_ended(self):
        """The chat is its log (chatlog): a task already drawn once never reads the old list again, so the take-back is written there - the
        answer that only handed the sign-in over lands as the turn's step, and the step says how it ended in the same line."""
        from taskuary import chatlog, conversation, general
        with mock.patch.dict('taskuary.terminal.SESSIONS', clear=True):
            self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'Looking at the toll account first.')
            self.s._exec("UPDATE comment SET CreatedAt=datetime('now','localtime','-1 minute')")        # ...said a minute before the ask
            conversation.items(self.s, self.tid); self.assertTrue(chatlog.migrated(self.s, self.tid))
            since = time.time()
            conversation.take_back(self.s, self.tid, why='Signing in to bank.example with the saved sign-in.', since=since, ahead=True)
            self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'I have no saved sign-in for it. Once the sign-in is done I will read it.')
            turns = lambda: [x for x in conversation.items(self.s, self.tid)['items'] if x['kind'] == 'turn']
            self.assertEqual((turns()[-1]['text'], [st['text'] for st in turns()[-1]['steps']]), ('', ['Signing in to bank.example with the saved sign-in.']))
            self.assertEqual(turns()[0]['text'], 'Looking at the toll account first.', 'only the answer after the mark is taken back')
            conversation.take_back(self.s, self.tid, why='Signed in to bank.example with the saved sign-in.', since=since, ahead=True)
            self.assertEqual([st['text'] for st in turns()[-1]['steps']], ['Signed in to bank.example with the saved sign-in.'], 'one line, ended in place')
            self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'The balance is $12.')
            self.assertEqual(turns()[-1]['text'], 'The balance is $12.', 'the next answer is an answer')

    def test_while_the_saved_sign_in_is_typed_the_task_is_at_work_not_done(self):
        """Seen in the browser round (2026-11-14): for the seconds a saved sign-in was typed the agent's turn had ended and nothing of its
        own was at work, so the header read "agent done" with Mark done lit. Something IS doing the next step: the task reads at work from
        the moment the typing starts until it has handed on - to the agent's next turn, or to the owner where it did not go in."""
        import threading
        from taskuary import general
        signin.save(self.s, 'bank.example', USER, PW)
        class Chat:
            sid, alive, task_id = 'sess1', True, self.tid
            def __init__(self): self.said, self.during = [], None
            def send_prompt(s, text, as_owner=True): s.said.append(text)
            def phase(s): return 'parked'                      # told, and its turn not yet at work: the beat this holds through
        sess, typing, go = Chat(), threading.Event(), threading.Event()
        def fill(*a, **k): typing.set(); go.wait(10)
        self.assertFalse(general.starting(self.tid))
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}), mock.patch.object(signin, 'HANDED_ON', 1.5):
            self.assertTrue(signin.needs(self.s, self.tid, 'sess1', 'bank.example', fill=fill)['auto'])
            self.assertTrue(typing.wait(10))
            self.assertTrue(general.starting(self.tid), 'at work while the saved sign-in is typed')
            self.assertTrue(general.working(self.s, self.tid))
            go.set(); self.wait_for(lambda: sess.said)
            # ...and through the beat between "signed in" told and the agent's next turn at work (2-3 s of "agent waiting on you" over a turn
            # with no words, watched on the real CLI 2026-11-15) - then let go, by itself, where no turn begins
            time.sleep(0.5); self.assertTrue(general.starting(self.tid), 'still at work in the beat after the agent is told')
            self.wait_for(lambda: not general.starting(self.tid), secs=15)
        # ...and one that does not go in hands on to the agent, to find the way past it: nothing is left reading at work
        def boom(*a, **k): raise signin.NotAccepted('bank.example kept its sign-in form up')
        signin._TRIED.clear(); sess.said.clear()
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            signin.needs(self.s, self.tid, 'sess1', fill=boom, watch=None)
            self.wait_for(lambda: sess.said, secs=15)
        self.wait_for(lambda: not general.starting(self.tid), secs=15)

    def test_a_saved_sign_in_that_does_not_go_in_goes_back_to_the_agent(self):
        """The vendor walk, 2026-11-19: "The saved sign-in for 127.0.0.7 did not work - sign in on the page" was handed to the owner for an account
        the agent itself had made minutes before - he never had its password, and the agent sat idle on him. A refused saved sign-in is the
        agent's to get past first (a reset, the emailed code, a sign-up never finished); nothing is asked of him."""
        signin.save(self.s, 'bank.example', USER, PW)
        def boom(*a, **k): raise signin.NotAccepted('bank.example kept its sign-in form up')
        class Chat:
            sid, alive, task_id = 'sess1', True, self.tid
            def __init__(self): self.said = []
            def send_prompt(s, text, as_owner=True, **k): s.said.append(text)
        sess = Chat()
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            self.assertTrue(signin.needs(self.s, self.tid, 'sess1', fill=boom, watch=None)['auto'])
            self.wait_for(lambda: sess.said)
        self.assertIsNone(signin.pending(self.s, self.tid), 'nothing is handed to him')
        self.assertIn('did not go in', sess.said[0]); self.assertIn('agent-browser signup', sess.said[0])
        # ...and a sign-in kept anew since (the agent reset it) is tried at once, never "asked again within minutes"
        typed = []
        signin.save(self.s, 'bank.example', USER, 'a-new-one-9!')
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            self.assertTrue(signin.needs(self.s, self.tid, 'sess1', fill=lambda sid, site, u, pw, **k: typed.append(pw) or {}, watch=None)['auto'])
            self.wait_for(lambda: typed)
        self.assertEqual(typed, ['a-new-one-9!'])

    def test_a_code_asked_after_the_saved_sign_in_is_the_owners_step_and_the_agent_is_not_told_it_is_signed_in(self):
        """The recorded walk, 2026-11-11: the saved password went in, the site asked for an authenticator code nobody keeps, the agent was
        told "Signed in - continue", read the code page, said so and ended its turn - with nothing asked of anyone."""
        signin.save(self.s, 'bank.example', USER, PW)
        class Chat:
            sid, alive, task_id = 'sess1', True, self.tid
            said = []
            def send_prompt(s, text, as_owner=True): s.said.append(text)
        sess = Chat()
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}), \
             mock.patch.object(signin, 'asks_code', return_value=True):
            self.assertTrue(signin.needs(self.s, self.tid, 'sess1', 'bank.example', fill=lambda *a, **k: {}, watch=None)['auto'])
            # ...THE CODE PAGE IS MADE READY FIRST (the owner, 2026-11-15: "why can't you click save for 30 days"): its agent is told to tick
            # whatever the page offers to remember this browser and to hand the code step back - never that it is signed in
            self.wait_for(lambda: sess.said)
            self.assertEqual(sess.said, [signin.READY_CODE.format(site='bank.example')])
            self.assertIsNone(signin.pending(self.s, self.tid))
            # ...its turn ends with the marker: the code step is his at once - nothing typed again, no "asked again within minutes"
            self.assertFalse(signin.needs(self.s, self.tid, 'sess1', 'bank.example', fill=lambda *a, **k: self.fail('typed again'), watch=None)['auto'])
            # ...and that turn is a step of the work, never an answer standing in the chat
            from taskuary import conversation, general
            self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'I need the site signed in to go on.')
        with mock.patch.dict('taskuary.terminal.SESSIONS', clear=True):
            turn = next(x for x in reversed(conversation.items(self.s, self.tid)['items']) if x['kind'] == 'turn')
        self.assertEqual((turn['text'], [st['text'] for st in turn['steps']][-1]), ('', 'Made the code page of bank.example ready for you.'))
        self.assertEqual(signin.pending(self.s, self.tid)['text'], 'bank.example took the saved sign-in and asks for a code - type it on the page to continue')
        self.assertFalse(any('asked to sign in again' in r['Body'] for r in self.s._rows('SELECT Body FROM comment WHERE TaskId=?', (self.tid,))))
        self.assertEqual(len(sess.said), 1)

    def test_a_saved_sign_in_is_never_typed_on_another_site(self):
        signin.save(self.s, 'bank.example', USER, PW)
        typed = []
        with on_page('https://bank-example.example/login'): out = signin.needs(self.s, self.tid, self.sid, 'bank.example', fill=lambda *a: typed.append(a))
        self.assertEqual((out['site'], out['auto']), ('bank-example.example', False))
        time.sleep(.1)
        self.assertEqual(typed, [])

    def test_the_agent_is_told_only_that_it_is_signed_in(self):
        class Chat:
            sid, alive, task_id = 'sess1', True, None
            def __init__(self): self.said = []
            def send_prompt(self, text, as_owner=True): self.said.append((text, as_owner))
        sess = Chat(); sess.task_id = self.tid
        with on_page('https://login.bank.example/'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            signin.needs(self.s, self.tid, 'sess1')
            self.assertFalse(ws.status(self.s, self.tid)['requests'][-1]['choices'])     # no presses: the question and its link (2026-11-03)
            tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]
            signin.by_owner(self.s, tok, USER, PW, False, fill=lambda *a: None)
            self.wait_for(lambda: sess.said)
            self.wait_for(lambda: not ws.status(self.s, self.tid)['requests'])
        self.assertEqual(sess.said, [('Signed in to bank.example - continue. The owner signed in on the page themselves.', False)])

    def test_a_failed_fill_is_audited_without_the_secret(self):
        with on_page('https://login.bank.example/'): signin.needs(self.s, self.tid, self.sid)
        tok = signin.link(self.s, self.tid)['url'].rsplit('/', 1)[1]
        def boom(*a): raise signin.SignInError('the page is no longer on bank.example - nothing was typed')
        with self.assertRaises(signin.SignInError): signin.by_owner(self.s, tok, USER, PW, True, fill=boom)
        self.assertIsNone(signin.saved(self.s, 'bank.example'))                        # a sign-in that did not go in is not kept
        self.assertNotIn(PW, self.everything_written())

    def test_no_keychain_no_save(self):
        with mock.patch.dict(os.environ, {'TASKUARY_VAULT': 'plain'}), self.assertRaises(ValueError): signin.save(self.s, 'bank.example', USER, PW)
        self.assertIsNone(signin.saved(self.s, 'bank.example'))


class WatchPage:
    """The task's tab as Taskuary's own DevTools connection sees it while it watches a sign-in: `pages` is what each look reads, in turn;
    `sent` is what the page's script hands over (one capture per look) - the owner's typing, sent with the form."""
    def __init__(self, pages, sent=()):
        self.pages, self.sent, self.calls = list(pages), list(sent), []
    def call(self, method, params=None, **kw): self.calls.append(method); return {}
    def js(self, expr): return None
    def fields(self, want=''): return self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
    def drain(self):
        if not self.sent: return []
        return [{'method': 'Runtime.bindingCalled', 'params': {'name': '__tqSignin', 'payload': json.dumps(self.sent.pop(0))}}]
    def close(self): pass


def form(href, password=True, user=True): return {'top': True, 'href': href, 'password': password, 'user': user, 'otp': False}


class StaleTab(unittest.TestCase):
    def test_a_tab_id_agent_browser_left_stale_falls_to_the_page_the_browser_holds(self):
        """agent-browser's .target kept a tab id after the tab was replaced: the attach reached nothing, so neither a fill nor a watch saw
        the sign-in page (the browser-agent walk, 2026-11-03)."""
        c = signin.Cdp.__new__(signin.Cdp)
        infos = [{'targetId': 'NEWTAB', 'type': 'page', 'url': 'chrome://newtab/'}, {'targetId': 'LIVE', 'type': 'page', 'url': 'https://login.bank.example/'},
                 {'targetId': 'W', 'type': 'service_worker', 'url': 'https://bank.example/sw.js'}]
        c.call = lambda m, p=None, top=False, timeout=10.0: {'targetInfos': infos}
        self.assertEqual(c.tab('GONE'), 'LIVE')
        self.assertEqual(c.tab('NEWTAB'), 'NEWTAB')                 # still there: agent-browser's word stands


class TheOwnerSignsInOnThePage(Asking):
    """The owner, 2026-11-03: no card, no Signed in press - "when we have browser it should just save what i type in". The ask is the
    question alone; the page going past the sign-in is the signal, and what the owner sent on the form is sealed to the vault for next time."""
    def ask(self, sess):
        with on_page('https://login.bank.example/signin'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            signin.needs(self.s, self.tid, 'sess1', watch=None)
        return signin.pending(self.s, self.tid)

    def chat(self):
        class Chat:
            sid, alive = 'sess1', True
            def __init__(s, tid): s.said, s.task_id = [], tid
            def send_prompt(s, text, as_owner=True): s.said.append(text); s.open_then = bool(signin.pending(self.s, self.tid))
        return Chat(self.tid)

    def test_a_password_page_still_loading_is_not_taken_for_signed_in(self):
        """The owner, 2026-11-05: between a site's user-name page and its password page, one look found no user box and no password box at
        another address - the agent was told "signed in" on the password page, and nothing watched when the owner did sign in. Past is
        past only once it stays past (PAST_STEADY looks in a row)."""
        sess = self.chat(); p = self.ask(sess)
        loading = form('https://login.bank.example/password', False, False)
        page = WatchPage([form('https://login.bank.example/signin', password=False), loading, form('https://login.bank.example/password', user=False), form('https://login.bank.example/password', user=False)]
                         + [form('https://app.bank.example/home', False, False)] * signin.PAST_STEADY)
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            self.assertTrue(signin.watch(self.s, self.tid, 'sess1', 'bank.example', p['request_id'], conn=page, every=0))
        self.assertEqual(len(sess.said), 1)                         # told once - after the real sign-in, not on the loading page
        self.assertEqual(page.pages, [form('https://app.bank.example/home', False, False)])   # ...it read through to the page past it

    def test_a_sign_in_done_on_the_page_wakes_the_open_chat(self):
        """The chat no longer reads its task every 2.5 s while it only waits on the page (2026-11-17): what brings the ask's end to a
        quiet pane is the task-changed this road sends - with the ask already closed when it is read."""
        sess = self.chat(); p = self.ask(sess); woke, poke = [], self.s._poke
        def spy(*kinds, **kw):
            if 'task-changed' in kinds and kw.get('task_id') == self.tid: woke.append(signin.pending(self.s, self.tid))
            return poke(*kinds, **kw)
        page = WatchPage([form('https://login.bank.example/signin')] + [form('https://app.bank.example/home', False, False)] * signin.PAST_STEADY)
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}), mock.patch.object(self.s, '_poke', spy):
            self.assertTrue(signin.watch(self.s, self.tid, 'sess1', 'bank.example', p['request_id'], conn=page, every=0))
        self.assertIn(None, woke)

    def test_a_two_step_sign_in_typed_on_the_page_is_seen_saved_and_used_next_time(self):
        sess = self.chat(); p = self.ask(sess)
        self.assertEqual((p['text'], ws.status(self.s, self.tid)['requests'][-1]['choices']), ('Sign in to bank.example to continue', []))
        page = WatchPage([form('https://login.bank.example/signin', password=False), form('https://login.bank.example/signin', user=False),
                          form('https://login.bank.example/signin', user=False), form('https://app.bank.example/home', False, False)],
                         sent=[{'u': USER, 'p': '', 'o': {'Account code': 'NW-0042'}, 'href': 'https://login.bank.example/signin'},
                               {'u': '', 'p': PW, 'href': 'https://login.bank.example/signin'}])
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            self.assertTrue(signin.watch(self.s, self.tid, 'sess1', 'bank.example', p['request_id'], conn=page, every=0))
        self.assertIn('Runtime.addBinding', page.calls)
        self.assertEqual(sess.said, ['Signed in to bank.example - continue. The owner signed in on the page themselves.'])        # the agent hears the words, never what was typed
        self.assertFalse(ws.status(self.s, self.tid)['requests'])
        # ...the ask was over BEFORE the agent's turn ran (a chat agent's turn runs inside the telling): nothing read "sign in" over it at work
        self.assertFalse(sess.open_then)
        # ...and the site asking AGAIN on this session (it signed the session out, it wants a code) is a new ask: the first one's answer
        # closed every later ask of the same site, so nothing was shown and nothing lit
        with on_page('https://login.bank.example/signin'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            signin._TRIED[(self.tid, 'bank.example')] = signin._now(); signin.needs(self.s, self.tid, 'sess1', watch=None)
        # ...asked again, it is an ask of its own (round 3, 2026-11-22: under the answered id it was never shown - a dead end), for the same site
        again = (signin.pending(self.s, self.tid) or {}).get('request_id')
        self.assertEqual((again, signin.ask_site(again)), ('signin:bank.example~2', 'bank.example'))
        ws.record(self.s, self.tid, 'sess1', 'answered', request_id=again, text='Signed in', source='owner')
        # ...and his sign-in is one line of the chat in his voice, saying it is kept and where to remove it
        from taskuary import general
        self.assertEqual([m['content'][0]['text'] for m in general.press_lines(self.s, self.tid)],
                         ['You signed in to bank.example - saved for next time (remove it under Settings → Agent permissions → Saved sign-ins).'])
        row = signin.saved(self.s, 'bank.example')
        self.assertEqual((vault.unseal(row['User']), vault.unseal(row['Secret'])), (USER, PW))
        self.assertEqual(signin.extra_of(row), {'Account code': 'NW-0042'})          # ...and the other box it typed, by its label
        said = ' '.join(c['Body'] for c in self.s.list_comments(self.tid))
        self.assertIn('Saved your bank.example sign-in to the vault - remove it under Settings → Agent permissions → Saved sign-ins.', said)
        # NOWHERE in the clear: not the comments, the events, the audit, the logs - the vault row is sealed
        self.assertNotIn(PW, self.everything_written()); self.assertNotIn(USER, json.dumps(signin.listing(self.s)))
        # ...and the next ask on the site is filled from the vault by itself
        t2, typed = Factory(self.s).task('Pay the toll again'), []
        with on_page('https://login.bank.example/signin'):
            self.assertTrue(signin.needs(self.s, t2, 'sess2', fill=lambda sid, site, u, pw, **k: typed.append((site, u, pw)), watch=None)['auto'])
        self.wait_for(lambda: typed)
        self.assertEqual(typed, [('bank.example', USER, PW)])

    def test_a_password_the_site_refused_is_not_kept_and_another_sites_form_is_not_heard(self):
        sess = self.chat(); p = self.ask(sess)
        # sent on a lookalike's page: not heard. Sent on the site, and the form comes back: not past, nothing kept, the ask stays
        page = WatchPage([form('https://login.bank.example/signin')] * 4,
                         sent=[{'u': USER, 'p': PW, 'href': 'https://bank-example.example/signin'},
                               {'u': USER, 'p': 'wrong', 'href': 'https://login.bank.example/signin'}])
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            self.assertFalse(signin.watch(self.s, self.tid, 'sess1', 'bank.example', p['request_id'], conn=page, every=0, until=.2))
        self.assertIsNone(signin.saved(self.s, 'bank.example')); self.assertEqual(sess.said, [])
        self.assertTrue(signin.pending(self.s, self.tid)); self.assertNotIn(self.tid, signin._TYPED)

    def test_a_sign_in_typed_a_page_at_a_time_with_a_code_after_is_kept_whole(self):
        """The owner's own sign-ins (2026-11): typed on the page several times, seen through, none kept. User name on one page, password on the
        next, a code on a third, each sent by a control that fires no submit - so what is typed is handed over as it is typed, a box at a
        time; and the code typed after the password is not the user name."""
        sess = self.chat(); p = self.ask(sess)
        at = 'https://login.bank.example/signin'
        code = {'top': True, 'href': at, 'password': False, 'user': False, 'otp': True}
        page = WatchPage([form(at, password=False), form(at, user=False), code, code, form('https://app.bank.example/home', False, False)],
                         sent=[{'u': USER[:3], 'p': '', 'href': at}, {'u': USER, 'p': '', 'href': at},        # ...each key of it
                               {'u': '', 'p': PW[:4], 'href': at}, {'u': '', 'p': PW, 'href': at},
                               {'u': '482913', 'p': '', 'href': at}])                                          # an older page's script: the code as "user"
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            self.assertTrue(signin.watch(self.s, self.tid, 'sess1', 'bank.example', p['request_id'], conn=page, every=0))
        from taskuary import vault
        row = signin.saved(self.s, 'bank.example')
        self.assertEqual((vault.unseal(row['User']), vault.unseal(row['Secret'])), (USER, PW))
        # ...and the page's own script hears typing, a change and the page going, and takes no code box for the user name
        for want in ("addEventListener('input'", "addEventListener('change'", "addEventListener('pagehide'", '!coded(e)'): self.assertIn(want, signin.CAPTURE)
        # ...nor is a code page's one box "a user box" to the look that tells a code prompt from a sign-in form
        self.assertIn("const alone = ins.filter((e) => texty(e) && !isCode(e));", signin.FIELDS)

    def test_a_sign_in_page_handed_over_as_his_turn_is_a_sign_in_all_the_same(self):
        """The agent may hand a sign-in it cannot type over as its turn (browserview.TURN_LINE). That road tried no saved sign-in and kept
        nothing he typed: a page asking for a password or a code is raised as the sign-in it is."""
        from taskuary import browserview
        sess = self.chat()
        with on_page('https://login.bank.example/signin'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}), \
             mock.patch.object(signin, 'on_signin_page', return_value=True), mock.patch.object(signin, 'watch') as watched:
            rid = browserview.your_turn(self.s, self.tid, 'sess1', 'sign in and type the code from your phone', watch=None)
            self.wait_for(lambda: watched.called)
        self.assertEqual((rid, signin.pending(self.s, self.tid)['site']), ('signin:bank.example', 'bank.example'))
        # ...and asked as the step the agent named, never as a bare "sign in" (design round 5)
        self.assertEqual(signin.pending(self.s, self.tid)['text'], 'Your turn in the browser on bank.example: sign in and type the code from your phone')

    def test_a_human_check_on_a_sign_up_page_at_a_bare_address_is_named_for_the_site_and_the_step(self):
        """The walks, design round 5 (2026-11-19): a vendor's sign-up page with a human check on it, at a local address, was handed over as
        "Sign in to 127.0.0.6 to continue" - a raw address, and "sign in" on a sign-up. It is named by the page's own title and the step the
        agent named; what a fill is pinned to stays the address."""
        from taskuary import browserview
        sess = self.chat()
        class Title:
            def js(self, src): return json.dumps(['  PermitWatch — Create your account ', '', 'http://127.0.0.6:18791/s/permitwatch/signup'])
            def close(self): pass
        with on_page('http://127.0.0.6:18791/s/permitwatch/signup'), mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}), \
             mock.patch.object(signin, 'on_signin_page', return_value=True), mock.patch.object(signin, 'connect', return_value=Title()), \
             mock.patch.object(signin, 'watch'):
            rid = browserview.your_turn(self.s, self.tid, 'sess1', 'answer the human check.', watch=None)
        p = signin.pending(self.s, self.tid)
        self.assertEqual((rid, p['site']), ('signin:127.0.0.6', '127.0.0.6'))
        self.assertEqual(p['text'], 'Your turn in the browser on PermitWatch: answer the human check')
        self.assertNotIn('Sign in', p['text']); self.assertNotIn('127.0.0.6', p['text'])
        # ...and a named site is called by its name, with nothing read off the page
        with mock.patch.object(signin, 'connect', side_effect=AssertionError('not read')): self.assertEqual(signin.page_name('s', 'bank.example'), 'bank.example')

    def test_a_step_giving_way_to_the_next_is_not_through_and_through_is_taken_back(self):
        """The owner's own sign-in, in its order (2026-11-14): the user name on one page, the password on the next, then a code page on
        another name of the site, moved by its fragment, the code split over six unnamed numeric boxes - read as "no box at all", so the
        sign-in was called through as the code page came up, the page was taken from him and handed straight back. Then the page behind
        the sign-in, with a search box - read as "a user box", so it was never taken back at all."""
        sess = self.chat(); p = self.ask(sess)
        step = lambda href, **k: {'top': True, 'href': href, 'password': False, 'user': False, 'otp': False, 'digits': 0, 'named': False, **k}
        code = step('https://accounts.bank.example/#/mfa/verify', digits=6)
        home = step('https://www.bank.example/home/home.jsp', user=True)                      # its search box, alone on the page
        page = WatchPage([step('https://login.bank.example/signin', user=True), step('https://login.bank.example/signin', password=True),
                          *[code] * 8, home])
        told = []
        sess.send_prompt = lambda text, as_owner=True: told.append((text, page.pages[0]['href']))
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'sess1': sess}):
            self.assertTrue(signin.watch(self.s, self.tid, 'sess1', 'bank.example', p['request_id'], conn=page, every=0))
        self.assertEqual(told, [('Signed in to bank.example - continue. The owner signed in on the page themselves.', home['href'])])     # once, and only on the page behind it
        self.assertFalse(ws.status(self.s, self.tid)['requests'])
        # ...and each step by itself: a code row is a step, one fragment to another is a move, a lone unnamed box behind it is no step
        self.assertFalse(signin.past(code, 'bank.example', 'https://login.bank.example/signin'))
        self.assertTrue(signin.past(step('https://accounts.bank.example/#/home'), 'bank.example', code['href']))
        self.assertFalse(signin.past(step('https://www.bank.example/reset', user=True, named=True), 'bank.example', code['href']))
        for want in ('digits,', "named: !!user && (named(user)"): self.assertIn(want, signin.FIELDS)

    def test_done_typed_in_the_chat_box_still_says_signed_in(self):
        self.assertTrue(signin.said_done('signin:bank.example', 'done'))
        self.assertTrue(signin.said_done('signin:bank.example', 'Signed in.'))
        self.assertFalse(signin.said_done('signin:bank.example', 'not yet'))
        self.assertFalse(signin.said_done('abc123', 'done'))


class FromAHook(unittest.TestCase):
    """A CLI's Stop hook carries the marker in its last message: it becomes the sign-in ask, and no judge reads the turn for one."""
    def test_the_stop_hook_raises_the_sign_in(self):
        from types import SimpleNamespace
        from taskuary import hooks, terminal as term
        s = MemoryStore(); tid = Factory(s).task('Pay the toll', kind='coding'); signin._TRIED.clear()
        pty = SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd=r'C:\code\repo', agent='coding', label='coding', argv=['claude'],
                              last=1.0, ext_id='c-sess', started='2026-10-24 09:00:00', typed=[], files=lambda: [], tail=lambda n=3: [],
                              idle=lambda: 0.0, witness=SimpleNamespace(note=lambda n: None), store=s, bg={})
        with mock.patch.dict(term.SESSIONS, {'run1': pty}, clear=True), mock.patch.object(term, 'bind_ext', lambda t, sid: None), \
                on_page('https://login.bank.example/'):
            hooks.receive({'hook_event_name': 'Stop', 'session_id': 'c-sess', 'cwd': r'C:\code\repo',
                           'last_assistant_message': 'The toll portal wants a sign-in.\n[[TASKUARY-SIGNIN: bank.example]]'}, cli='claude')
            st = ws.status(s, tid)
        self.assertEqual([r['request_id'] for r in st['requests']], ['signin:bank.example'])
        self.assertEqual(st['requests'][0]['choices'], [])                    # a pty is answered in words, never by typing "1"
        self.assertNotIn('SIGNIN', st['said'])


class Removing(unittest.TestCase):
    def test_remove_takes_the_password_and_the_sites_cookies(self):
        s = MemoryStore()
        signin.save(s, 'bank.example', USER, PW)
        d = Path(tempfile.mkdtemp()); (d / 'sessions').mkdir()
        kept = {'cookies': [{'name': 'sid', 'domain': '.bank.example', 'value': 'x'}, {'name': 'a', 'domain': 'login.bank.example', 'value': 'y'},
                            {'name': 'keep', 'domain': '.other.example', 'value': 'z'}, {'name': 'nope', 'domain': 'bank.example.evil.example', 'value': 'w'}],
                'origins': [{'origin': 'https://login.bank.example', 'localStorage': []}, {'origin': 'https://other.example', 'localStorage': []}]}
        (d / 'sessions' / 'taskuary-tq-abc.json').write_text(json.dumps(kept), encoding='utf-8')
        (d / 'sessions' / 'someone-else.json').write_text(json.dumps(kept), encoding='utf-8')
        with mock.patch.dict(os.environ, {'AGENT_BROWSER_HOME': str(d)}):
            self.assertEqual(signin.remove(s, 'bank.example')['kind'], 'signin')
        self.assertIsNone(signin.saved(s, 'bank.example'))
        self.assertEqual(signin.listing(s), [])
        left = json.loads((d / 'sessions' / 'taskuary-tq-abc.json').read_text(encoding='utf-8'))
        self.assertEqual([k['name'] for k in left['cookies']], ['keep', 'nope'])
        self.assertEqual([o['origin'] for o in left['origins']], ['https://other.example'])
        self.assertEqual(json.loads((d / 'sessions' / 'someone-else.json').read_text(encoding='utf-8')), kept)   # not Taskuary's: untouched


class Routes(unittest.TestCase):
    def setUp(self):
        self.s = server.store; self.tid = Factory(self.s).task('Pay the toll'); signin._TRIED.clear()
        with on_page('https://login.bank.example/'): signin.needs(self.s, self.tid, f'route-{self.tid}')

    def test_the_fill_page_names_the_site_and_works_once(self):
        r = c.post(f'/api/tasks/{self.tid}/signin/link'); self.assertEqual(r.status_code, 200, r.text)
        url = r.json()['url']
        page = c.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn('<p class="site">bank.example</p>', page.text)
        self.assertIn("frame-ancestors 'none'", page.headers['content-security-policy'])
        with mock.patch.object(signin, 'type_in') as typed:
            r = c.post(url, data={'username': USER, 'password': PW})
            self.assertEqual(r.status_code, 200, r.text)
            typed.assert_called_once_with(f'route-{self.tid}', 'bank.example', USER, PW)
            self.assertEqual(c.post(url, data={'username': USER, 'password': PW}).status_code, 410)
        self.assertEqual(c.get(url).status_code, 410)

    def test_another_site_cannot_post_the_form(self):
        url = c.post(f'/api/tasks/{self.tid}/signin/link').json()['url']
        with mock.patch.object(signin, 'type_in') as typed:
            r = c.post(url, data={'password': PW}, headers={'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(r.status_code, 403)
        typed.assert_not_called()

    def test_a_sign_in_saved_ahead_of_time_is_sealed_for_its_site_and_said_back_by_site_only(self):
        """Connections > Sign-ins (the owner, 2026-11-03): a site's sign-in kept before any agent asks - the vault's one store."""
        signin.remove(self.s, 'portal.example')
        r = c.post('/api/signins', json={'site': 'https://login.portal.example/start?x=1', 'user': USER, 'password': PW})
        self.assertEqual((r.status_code, r.json()), (200, {'ok': True, 'site': 'portal.example'}))
        row = signin.saved(self.s, 'portal.example')
        self.assertEqual((vault.unseal(row['User']), vault.unseal(row['Secret'])), (USER, PW))
        self.assertNotIn(PW, c.get('/api/signins').text); self.assertNotIn(USER, c.get('/api/signins').text)
        # ...with the other box its form asks for: sealed with it, listed by its label only, kept when the password is saved again
        r = c.post('/api/signins', json={'site': 'portal.example', 'user': USER, 'password': PW, 'fields': {'Account code': 'NW-0042'}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(signin.extra_of(signin.saved(self.s, 'portal.example')), {'Account code': 'NW-0042'})
        self.assertNotIn('NW-0042', c.get('/api/signins').text)
        row = next(x for x in c.get('/api/signins').json()['data'] if x['site'] == 'portal.example')
        self.assertEqual(row['fields'], ['Account code'])
        signin.save(self.s, 'portal.example', USER, 'new-' + PW)
        self.assertEqual(signin.extra_of(signin.saved(self.s, 'portal.example')), {'Account code': 'NW-0042'})
        self.assertEqual(c.post('/api/signins', json={'site': 'co.uk', 'password': PW}).status_code, 400)
        self.assertEqual(c.post('/api/signins', json={'site': 'http://portal.example', 'password': PW}).status_code, 400)
        self.assertEqual(c.post('/api/signins', json={'site': 'portal.example', 'password': PW}, headers=AGENT).status_code, 403)
        signin.remove(self.s, 'portal.example')

    def test_an_agent_reaches_none_of_it(self):
        self.assertEqual(c.post(f'/api/tasks/{self.tid}/signin/link', headers=AGENT).status_code, 403)
        self.assertEqual(c.get('/api/signins', headers=AGENT).status_code, 403)
        self.assertEqual(c.delete('/api/signins/bank.example', headers=AGENT).status_code, 403)
        self.assertEqual(c.get('/signin/whatever', headers=AGENT).status_code, 403)

    def test_settings_lists_and_removes(self):
        signin.save(self.s, 'bank.example', USER, PW)
        self.assertEqual([r['site'] for r in c.get('/api/signins').json()['data']], ['bank.example'])
        with mock.patch.object(browserview, 'forget_site', return_value=0), mock.patch.object(signin, '_forget_live'):
            self.assertEqual(c.delete('/api/signins/bank.example').status_code, 200)
            self.assertEqual(c.delete('/api/signins/bank.example').status_code, 404)
        self.assertEqual(c.get('/api/signins').json()['data'], [])

    # ONE PRESS, AND AN UNDO THAT IS TRUE (the owner, 2026-11-15: Remove asks nothing, and leaves an Undo line as a removed task does).
    # Undo puts back the whole saved sign-in - the password, the authenticator key and the other boxes it fills - not a row with holes
    def test_remove_answers_with_an_undo_that_puts_the_whole_sign_in_back(self):
        from taskuary import recentlydeleted, totp, vault
        key = 'JBSWY3DPEHPK3PXP'
        self.addCleanup(lambda: self.s._exec("DELETE FROM signin_vault WHERE Site='bank.example'"))
        signin.save(self.s, 'bank.example', USER, PW, key=key, extra={'Customer ID': 'NW-7'})
        was = signin.saved(self.s, 'bank.example')
        with mock.patch.object(browserview, 'forget_site', return_value=0), mock.patch.object(signin, '_forget_live'), \
                mock.patch.object(vault, 'forget') as forgot:
            out = c.delete('/api/signins/bank.example').json()
            self.assertEqual((out['kind'], out['title']), ('signin', 'bank.example')); did = out['deleted']
            # ...out of the vault at once: nothing types it from the press on, and nothing lists it
            self.assertIsNone(signin.saved(self.s, 'bank.example')); self.assertEqual(c.get('/api/signins').json()['data'], [])
            self.assertEqual([x for x in recentlydeleted.listing(self.s) if x['kind'] == 'signin'], [], "the Undo line's alone - not a shelf of kept passwords")
            forgot.assert_not_called()                         # its keychain entries wait for the Undo line to pass
            self.assertEqual(c.post(f'/api/deleted/{did}/restore').status_code, 200)
            forgot.assert_not_called()
        back = signin.saved(self.s, 'bank.example')
        self.assertEqual(vault.unseal(back['Secret']), PW); self.assertEqual(vault.unseal(back['User']), USER)
        self.assertEqual(totp.loads(vault.unseal(back['Totp'])), totp.loads(vault.unseal(was['Totp'])))
        self.assertEqual(signin.extra_of(back), {'Customer ID': 'NW-7'})
        self.assertEqual([(r['site'], r['code']) for r in c.get('/api/signins').json()['data']], [('bank.example', True)])
        self.assertEqual(c.post(f'/api/deleted/{did}/restore').status_code, 404, 'an Undo is one press')

    def test_an_undo_left_unpressed_forgets_the_keychain_and_never_overwrites_a_newer_sign_in(self):
        import time
        from taskuary import recentlydeleted, vault
        self.addCleanup(lambda: self.s._exec("DELETE FROM signin_vault WHERE Site='bank.example'"))
        signin.save(self.s, 'bank.example', USER, PW)
        old = signin.saved(self.s, 'bank.example')['Secret']
        with mock.patch.object(browserview, 'forget_site', return_value=0), mock.patch.object(signin, '_forget_live'):
            did = c.delete('/api/signins/bank.example').json()['deleted']
        # the owner signs in again on the page before pressing Undo: the new one stands
        signin.save(self.s, 'bank.example', USER, 'a newer password')
        self.assertEqual(c.post(f'/api/deleted/{did}/restore').status_code, 409)
        self.assertEqual(vault.unseal(signin.saved(self.s, 'bank.example')['Secret']), 'a newer password')
        # ...and once the line's minutes pass, the kept row goes and its sealed values are forgotten
        with mock.patch.object(vault, 'forget') as forgot:
            self.assertIn(did, recentlydeleted.purge(self.s, time.time() + recentlydeleted.UNDO_SECONDS + 1))
        self.assertIn(mock.call(old), forgot.call_args_list)
        self.assertEqual(c.post(f'/api/deleted/{did}/restore').status_code, 404)


if __name__ == '__main__': unittest.main()


class CodeByMail(unittest.TestCase):
    """THE REAL-CLI WALK, 2026-11-16: signed up, the site emailed "Your LienLens verification code is 383972" and asked for it on its page.
    Triage filed the mail, the task kept saying "press its button" over a code page, and nobody knew the code was in the inbox. The watch
    of the open ask finds a mail from the page's own site and types its one code on the pinned page, naming the mail."""
    def setUp(self): self.s = MemoryStore(); self.tid = Factory(self.s).task('Market data from ten vendors')

    def mail(self, frm, body):
        return self.s.add_message({'Channel': 'email', 'FromEmail': frm, 'FromName': 'LienLens', 'Subject': 'Your LienLens code', 'BodyText': body, 'Status': 'filed'})

    def test_only_a_mail_from_the_pages_own_site_since_the_ask_and_its_one_code(self):
        before = self.mail('no-reply@lienlens.example', 'Your code is 111111.')
        after = (self.s._one('SELECT MAX(MessageId) AS m FROM message') or {})['m']
        self.assertIsNone(signin.mailed_code(self.s, 'lienlens.example', after), 'a mail from before the ask is not this one')
        self.mail('alerts@lienlens.example.evil.example', 'Your code is 222222.')
        self.assertIsNone(signin.mailed_code(self.s, 'lienlens.example', after), 'a lookalike sender is another site')
        mid = self.mail('no-reply@mail.lienlens.example', 'Your LienLens verification code is 383972. It expires in 30 minutes.')
        self.assertEqual(signin.mailed_code(self.s, 'lienlens.example', after), (mid, '383972'))
        two = self.mail('no-reply@lienlens.example', 'Code 123456 or 654321, whichever.')
        self.assertEqual(signin.mailed_code(self.s, 'lienlens.example', after), (two, ''), 'two codes: his to read, never a guess')
        self.assertTrue(before)

    def test_a_code_mail_with_other_numbers_has_its_code_read_by_the_model(self):
        """Real code mails carry other numbers - the year in the footer, a street address, a zip. Every such mail read as "several codes",
        so none was ever typed. Which number is the code is the model's to read; it may only answer one of the numbers the mail holds."""
        after = (self.s._one('SELECT MAX(MessageId) AS m FROM message') or {})['m'] or 0
        mid = self.mail('no-reply@lienlens.example', 'Your LienLens verification code is 383972. It expires in 30 minutes.\n\n'
                                                     'LienLens Inc, 1200 Harbor Way, Millbrook 02139\n(c) 2026 LienLens')
        seen = []
        def brain(system, user, **k): seen.append(user); return '{"code": "383972"}'
        self.assertEqual(signin.mailed_code(self.s, 'lienlens.example', after, brain=brain), (mid, '383972'))
        self.assertEqual(len(seen), 1)
        self.assertEqual(signin.mailed_code(self.s, 'lienlens.example', after, brain=lambda *a, **k: '{"code": "999999"}'), (mid, ''),
                         'a number the mail does not hold is never typed')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual(signin.mailed_code(self.s, 'lienlens.example', after), (mid, ''), 'no AI: his to read')

    def test_the_code_is_typed_on_the_pinned_page_and_the_mail_goes_on_the_task(self):
        mid = self.mail('no-reply@lienlens.example', 'Your LienLens verification code is 383972.')
        typed = []
        with mock.patch.object(signin, '_type_code', lambda c, site, code: typed.append((site, code()))):
            self.assertTrue(signin._code_from_mail(self.s, self.tid, 'lienlens.example', object(), mid, '383972'))
        self.assertEqual(typed, [('lienlens.example', '383972')])
        # ...the mail stays where it was filed: on the task, a site's no-reply mail made his own task a stranger's, held for Trust
        self.assertIsNone(self.s.get_message(mid)['TaskId'])
        said = [c['Body'] for c in self.s.list_comments(self.tid)]
        self.assertIn('Typed the code lienlens.example emailed you ("Your LienLens code").', said)
        self.assertNotIn('383972', json.dumps([said, self.s._rows('SELECT * FROM audit')]))


class TheAgentsOwnCode(unittest.TestCase):
    """THE VENDOR WALKS, 2026-11-18: the agent pressed Create account itself, the site emailed its code, and the code landed on his rail as four
    "unverified sender" FYI rows while the agent asked for it again. A code from the site the agent just acted on is its own act returning:
    kept off the inbox ahead of triage (triage itself unchanged), typed into that site's page only, and never shown to the agent."""
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Market data from every vendor'); signin._TYPING.clear()
        self.addCleanup(signin._TYPING.clear)

    def msg(self, frm, body, ext='m1'):
        return {'external_id': ext, 'channel': 'email', 'from_email': frm, 'from_name': 'LienLens', 'subject': 'Your LienLens code', 'body': body,
                'to': ['alex@northwind.example']}

    def test_a_code_from_the_site_the_agent_just_pressed_on_is_taken_off_his_rail_and_watched_for(self):
        from taskuary import ingest
        signin.acting(self.s, self.tid, 'sess1', 'lienlens.example')
        watched = []
        reads = lambda store, text, found, brain=None: '383972' if '383972' in found else ''
        with mock.patch.object(signin, '_pick_code', reads), mock.patch.object(signin, 'code_watch', lambda *a: watched.append(a)):
            out = ingest.ingest_message(self.s, self.msg('no-reply@lienlens.example', 'Your LienLens verification code is 383972.'))
            self.assertEqual((out['status'], out['task_id']), ('skipped', None), 'never an arrival of its own: no FYI, no task')
            end = time.time() + 5
            while not watched and time.time() < end: time.sleep(.01)
            self.assertEqual(watched, [(self.s, self.tid, 'sess1', 'lienlens.example')])
            # ...an invoice from the same site holds numbers too, and is his: the model reads it as no code
            self.assertIsNone(signin.take_code(self.s, self.msg('billing@lienlens.example', 'Invoice 48210 is due.', 'm2'), watch=None))
            # ...and a code from a site no agent of his acted on is mail like any other
            self.assertIsNone(signin.take_code(self.s, self.msg('no-reply@other.example', 'Your code is 555123.', 'm3'), watch=None))
        signin._TYPING[(self.tid, 'lienlens.example')] = (0, time.time() - signin.CODE_FRESH - 1, 'sess1')
        with mock.patch.object(signin, '_pick_code', reads):
            self.assertIsNone(signin.take_code(self.s, self.msg('no-reply@lienlens.example', 'Code 383972.', 'm4'), watch=None), 'stale: his mail')

    def test_the_code_is_typed_when_that_sites_page_asks_and_the_agent_told_to_look(self):
        from taskuary import browsergate
        signin.acting(self.s, self.tid, 'sess1', 'lienlens.example')
        self.s.add_message({'Channel': 'email', 'FromEmail': 'no-reply@lienlens.example', 'FromName': 'LienLens', 'Subject': 'Your LienLens code',
                            'BodyText': 'Your LienLens verification code is 383972.', 'Status': 'skipped'})
        form_page = {'top': True, 'href': 'http://lienlens.example/signup', 'otp': False}
        code_page = {'top': True, 'href': 'https://lienlens.example/verify', 'otp': True}
        typed, told = [], []
        with mock.patch.object(signin, '_type_code', lambda c, st, code: typed.append((st, code()))),              mock.patch.object(browsergate, '_tell', lambda s, t, text, **k: told.append(text)):
            self.assertTrue(signin.code_watch(self.s, self.tid, 'sess1', 'lienlens.example', every=0, until=5, conn=WatchPage([form_page, code_page])))
        self.assertEqual(typed, [('lienlens.example', '383972')])
        self.assertIn('Taskuary typed the code lienlens.example emailed', told[0]); self.assertNotIn('383972', told[0])


def test_a_sign_up_the_site_crashed_on_or_never_answered_is_no_account():
    """The vendor walk, 2026-11-18: a site that crashed on its form showed a 500 page with no password box, and Taskuary kept "an account"
    nobody could sign in to; one that never answered read "the browser could not be reached". What the site answered is read by its status,
    and a document still leaving after the wait is a site that did not answer."""
    from taskuary import browsergate
    class Page:
        def __init__(self, status, ready='complete', leaving=False): self.v = {browsergate.STATUS_JS: {'status': status}, 'document.readyState': ready,
                                                                              'window.__tqLeaving === true': leaving}
        def js(self, expr): return self.v[expr]
    assert signin.answered(Page(500)) == 500 and signin.answered(Page(200)) == 200
    assert signin.answered(Page(200, leaving=True), wait=0.6) is None, 'the old page, still leaving: no answer'


def test_a_saved_sign_in_whose_site_emails_a_code_types_the_code_from_the_mail():
    """The saved sign-in went in and the site emailed a login code as the password was sent. The code step was raised a turn later (its agent
    made the page ready first), and its watch read mail only from then on - the code, already in the inbox, was never typed."""
    s = MemoryStore(); tid = Factory(s).task('Rent data'); signin._TRIED.clear()
    site, rid = 'rentscope.example', 'signin:rentscope.example'
    signin.save(s, site, USER, PW)
    def fill(sid, st, user, pw, **k):
        s.add_message({'Channel': 'email', 'FromEmail': 'no-reply@rentscope.example', 'FromName': 'RentScope', 'Subject': 'Your sign-in code',
                       'BodyText': 'Your RentScope sign-in code is 552019.', 'Status': 'filed'})
        return {}
    asked = []
    with mock.patch.object(signin, 'asks_code', side_effect=[False, True]), mock.patch.object(signin, '_ready_code', return_value=False):
        signin._auto(s, tid, 'sess1', site, rid, fill, lambda said=None: asked.append(said))
    assert asked == [signin.CODE_ASK.format(site=site)], asked
    ws.record(s, tid, 'sess1', 'input_needed', request_id=rid, text=asked[0], choices=None, source='api')
    code_page = {'top': True, 'href': 'https://rentscope.example/verify', 'otp': True}
    page = WatchPage([code_page, code_page, {'top': True, 'href': 'https://rentscope.example/data'}])
    typed = []
    with mock.patch.object(signin, '_type_code', lambda c, st, code: typed.append(code())), mock.patch.object(signin, '_continue', lambda *a, **k: True):
        assert signin.watch(s, tid, 'sess1', site, rid, conn=page, every=0)
    assert typed == ['552019']


# ── A SIGN-UP IS ONE COMMAND IN THE AGENT'S TURN (design round 4, 2026-11-19) ──────────────────────────────────────────────────────────
class UpPage:
    """A vendor's sign-up as Taskuary's own DevTools connection sees it: its form (`pwbox` - a wizard's first step has none), then, sent, the
    page the site answers with (go). `pw`: what its password box holds - typed by the agent itself."""
    def __init__(self, href='https://www.rentscope.example/signup', user=USER, pw='', pwbox=True):
        self.href, self.user, self.pw, self.pwbox, self.state, self.ran = href, user, pw, pwbox, 'form', []
        self.fields_ = [{'k': 'name', 't': 'text', 'v': 'Alex Doyle'}, {'k': 'email', 't': 'email', 'v': USER}, {'k': 'terms', 't': 'checkbox', 'v': 'yes'}]
    def go(self, state, href): self.state, self.href = state, href
    def form(self): return self.state == 'form' and self.pwbox
    def js(self, expr):
        from taskuary import browsergate
        self.ran.append(expr)
        if expr == signin.FORM: return {'href': self.href, 'top': True, 'title': self.state.title(), 'user': self.user if self.state == 'form' else '',
                                        'pw': bool(self.pw), 'password': self.form(), 'fields': self.fields_}
        if expr == signin.FORM_PW: return self.pw
        if expr.startswith(signin.REFILL): self.user = USER; return 3
        if expr == 'location.href': return self.href
        if expr == 'document.readyState': return 'complete'
        if expr == browsergate.STATUS_JS: return {'status': 200}
        return False if 'tqLeaving ===' in expr else None
    def fields(self, want=''): return {'top': True, 'href': self.href, 'password': self.form(), 'otp': self.state == 'code'}
    def close(self): pass


def gate(hold):
    "The browser gate's verdict on sending the form, stood in: his ask makes it go (hold False), or it is one card for his press."
    from contextlib import ExitStack
    from taskuary import browsergate
    st = ExitStack()
    st.enter_context(mock.patch.object(browsergate, 'judge', return_value=[{'hold': hold, 'what': 'creates an account on the site', 'why': "it can't be undone"}]))
    st.enter_context(mock.patch.object(browsergate, 'page', return_value={})); st.enter_context(mock.patch.object(browsergate, 'asked', return_value=''))
    st.enter_context(mock.patch.object(signin, 'SETTLE', 0)); st.enter_context(mock.patch.object(signin, 'REJECT_WAIT', 0))
    return st


def signing_up(s, tid, page, send, typed=None, code=None):
    typed = [] if typed is None else typed
    with gate(False) as st, on_page(page.href), mock.patch.object(signin, 'connect', return_value=page), \
         mock.patch.object(signin, 'type_new', lambda sid, site, pw, c: typed.append(pw) or 1), mock.patch.object(signin, 'send_new', send):
        if code: st.enter_context(mock.patch.object(signin, '_type_code', code))
        return signin.signup(s, tid, 'sess1')


def test_the_sign_up_command_sends_the_form_he_asked_for_with_a_password_kept_before_it_goes():
    """Thirteen vendors, a turn ended per site with the [[TASKUARY-SIGNUP]] marker and the agent woken a turn later: 25-35 minutes, and what it
    made lost. `agent-browser signup` does it inside the turn: Taskuary makes the password, types it, keeps it BEFORE the form goes, sends it,
    and the command's own output says what the site answered - an account only where it let the agent in."""
    s = MemoryStore(); tid = Factory(s).task('Market data'); page, typed = UpPage(), []
    def send(sid, site, c):
        assert vault.unseal(signin.saved(s, site)['Secret']) == typed[0], 'kept before the form goes'
        c.go('data', 'https://www.rentscope.example/data'); return {'ok': True, 'user': USER}
    ok, said = signing_up(s, tid, page, send, typed)
    assert ok and said.startswith(f'Signed up on rentscope.example as {USER}, and signed in: the page shows "Data"'), said
    row = signin.saved(s, 'rentscope.example')
    assert (vault.unseal(row['Secret']), vault.unseal(row['User'])) == (typed[0], USER) and len(typed[0]) >= 16
    assert typed[0] not in json.dumps([s._rows('SELECT * FROM audit'), s._rows('SELECT * FROM comment'), said], default=str)


def test_a_sign_up_the_site_turned_down_puts_back_the_sign_in_it_replaced():
    """An agent that signed up twice on one site ("An account with that email already exists") must not cost the owner the sign-in that works."""
    s = MemoryStore(); tid = Factory(s).task('Market data'); signin.save(s, 'rentscope.example', USER, PW)
    refused = lambda sid, site, c: {'ok': False, 'why': 'An account with that email already exists - sign in instead.'}
    ok, said = signing_up(s, tid, UpPage(), refused)
    assert not ok and 'already exists' in said and 'Nothing was kept' in said, said
    assert vault.unseal(signin.saved(s, 'rentscope.example')['Secret']) == PW
    s2 = MemoryStore(); tid2 = Factory(s2).task('Market data')
    signing_up(s2, tid2, UpPage(), refused)
    assert signin.saved(s2, 'rentscope.example') is None


def test_a_failed_sign_up_card_a_later_sign_up_made_good_reads_done_not_a_red_failure():
    """Design round 6, D3 (the vendor walk): his press on a held sign-up failed - "No account: the site kept its sign-up form up" - and stood red
    under the agent's later line that the account was active. The failure a later step overcame is that outcome, where it happened."""
    from taskuary import conversation, general
    s = MemoryStore(); tid = Factory(s).task('Market data')
    rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'Submit the sign-up on RentScope',
                        'DraftText': json.dumps({'action': 'browser_act', 'sid': 'sess1', 'args': ['signup'], 'signup': 'rentscope.example',
                                                 'site': 'rentscope.example', 'what': 'Submit the sign-up on RentScope'})})
    s.review_act_failed(rid, f'No account: rentscope.example kept its sign-up form up. {general.AGENT_TOLD}', 'owner')
    other = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'Pay on DealFlow',
                          'DraftText': json.dumps({'action': 'browser_act', 'sid': 'sess1', 'args': ['click', '@e4'], 'site': 'dealflow.example', 'what': 'Pay $49'})})
    s.review_act_failed(other, 'the page covers that control', 'owner')
    ok, _ = signing_up(s, tid, UpPage(), lambda sid, site, c: c.go('data', 'https://www.rentscope.example/data') or {'ok': True, 'user': USER})
    assert ok
    r = s.get_review(rid)
    assert (r['Status'], r['ActError']) == ('approved', None) and conversation._card(r)['status'] == 'approved'
    assert 'the account on rentscope.example was made' in json.loads(r['FinalText'])['result']['performed']
    assert s.get_review(other)['ActError'], 'a failure on another site is not overcome by this one'


def test_a_wizards_last_step_is_kept_under_the_email_its_first_step_named():
    """A two-step sign-up: the email on step one, Company and password on step two. Kept with no user name, the account was said "created"
    and every sign-in after was refused ("Wrong email or password"). The agent's press on step one is heard, and its email kept for the step
    that sends - and a page with no password box types nothing."""
    s = MemoryStore(); tid = Factory(s).task('Market data'); signin._USERS.clear()
    step1 = UpPage('https://capratehub.example/signup', pwbox=False)
    ok, said = signing_up(s, tid, step1, lambda *a: {'ok': True})
    assert not ok and 'no password box' in said and signin.saved(s, 'capratehub.example') is None
    signin.pressing(s, tid, 'sess1', 'capratehub.example', conn=step1)                     # ...its Next, pressed by the agent
    step2 = UpPage('https://capratehub.example/step2', user='')
    ok, said = signing_up(s, tid, step2, lambda sid, site, c: c.go('data', 'https://capratehub.example/data') or {'ok': True, 'user': ''})
    assert ok and said.startswith(f'Signed up on capratehub.example as {USER}'), said
    assert vault.unseal(signin.saved(s, 'capratehub.example')['User']) == USER


def test_a_code_the_site_emails_is_typed_inside_the_command():
    """The site emailed its code as the form went, and the code landed on his rail as FYI rows while the agent asked for it again. Inside the
    command the mail is waited for and its one code typed on the page; past the wait the code watch goes on, on that page."""
    s = MemoryStore(); tid = Factory(s).task('Market data'); codes = []
    def send(sid, site, c):
        s.add_message({'Channel': 'email', 'FromEmail': 'no-reply@lienlens.example', 'FromName': 'LienLens', 'Subject': 'Your LienLens code',
                       'BodyText': 'Your LienLens verification code is 383972. It expires in 30 minutes.', 'Status': 'skipped'})
        c.go('code', 'https://lienlens.example/verify'); return {'ok': True, 'user': USER}
    def code(c, site, make): codes.append(make()); c.go('data', 'https://lienlens.example/data')
    ok, said = signing_up(s, tid, UpPage('https://lienlens.example/signup'), send, code=code)
    assert codes == ['383972'] and ok and said.startswith(f'Signed up on lienlens.example as {USER}, and signed in'), said
    assert 'The code it emailed was typed' in said and '383972' not in said
    # ...no mail within the wait: not an account yet, said so, and the code watch keeps that page
    watched = []
    with mock.patch.object(signin, 'CODE_INLINE', 0.2), mock.patch.object(signin, 'code_watch', lambda *a, **k: watched.append(k)):
        ok, said = signing_up(s, tid, UpPage('https://lienlens.example/signup'), lambda sid, site, c: c.go('code', 'https://lienlens.example/verify') or {'ok': True})
    end = time.time() + 5
    while not watched and time.time() < end: time.sleep(.02)
    assert said.startswith('Not an account yet') and watched == [{'url': 'https://lienlens.example/verify'}], (said, watched)


def test_a_password_the_agents_own_press_sends_is_kept_and_put_back_when_refused():
    """The vendor walk, 2026-11-19: accounts made in the owner's name and lost - the agent pressed the sign-up form itself, nothing kept what
    its password box held, and later it called them accounts that "already existed". A press of the agent's that sends a password seals it
    first, keeps it once the site takes it, and the command's output says so; refused, the row it replaced comes back."""
    s = MemoryStore(); tid = Factory(s).task('Market data')
    page = UpPage(pw='typed-by-the-agent-1!')
    signin.pressing(s, tid, 'sess1', 'rentscope.example', conn=page)
    page.go('data', 'https://www.rentscope.example/data')
    line = signin.settled(s, 'sess1', conn=page)
    assert 'kept' in line and 'agent-browser signup' in line
    assert vault.unseal(signin.saved(s, 'rentscope.example')['Secret']) == 'typed-by-the-agent-1!'
    signin.save(s, 'vacancyiq.example', USER, PW)
    page = UpPage('https://vacancyiq.example/signup', pw='weak')
    signin.pressing(s, tid, 'sess1', 'vacancyiq.example', conn=page)
    with mock.patch.object(signin, 'REJECT_WAIT', 0): assert signin.settled(s, 'sess1', conn=page) == ''
    assert vault.unseal(signin.saved(s, 'vacancyiq.example')['Secret']) == PW, 'the sign-in that works is back'


def test_a_held_sign_up_is_sent_on_its_own_tab_only_never_the_tab_shown():
    """Walk 5, 2026-11-19: a sign-up held on one site's tab stayed lit while another site's tab was shown, and his Approve ran on that other
    site's page. The card names the tab it was held on; his press sends the form there only - while that tab is on its page - and where it
    left, nothing is sent and he reads why."""
    from taskuary import browsergate
    s = MemoryStore(); tid = Factory(s).task('Trial accounts for Erin'); page = UpPage(); page.target = 'T1'
    with gate(True), on_page(page.href), mock.patch.object(signin, 'connect', return_value=page):
        ok, said = signin.signup(s, tid, 'sess1')
    assert ok and said.startswith('HELD for the owner')
    from taskuary import cardqueue
    assert cardqueue.SCREEN_HEAD[:40] in said, 'what stands, told from the record as every card tool tells it'
    [rv] = s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))
    p = json.loads(rv['DraftText'])
    assert (p['action'], p['signup'], p['tab']) == ('browser_act', 'rentscope.example', 'T1')
    shown = {'id': 'T2', 'url': 'http://127.0.0.12:8080/quota'}
    attached, told = [], []
    def exact(url, tab, exact=False): attached.append((tab, exact)); return UpPage(user='')
    with mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': p['url']}, shown]), mock.patch.object(signin, 'Cdp', exact),          mock.patch.object(signin, '_cdp_url', return_value='ws://x'), mock.patch.object(signin, 'type_new', lambda *a: 1),          mock.patch.object(signin, 'send_new', lambda sid, site, c: c.go('data', 'https://www.rentscope.example/data') or {'ok': True}),          mock.patch.object(signin, 'SETTLE', 0), mock.patch.object(browsergate, '_tell', lambda s_, t, text, **k: told.append(text)),          mock.patch.object(browserview, 'state', return_value={'open': True, 'url': shown['url']}):
        browsergate.perform(s, tid, p)
    assert attached == [('T1', True)], 'on the tab it was held on, never the one shown'
    assert told and told[0].startswith('The owner approved the sign-up on rentscope.example. Signed up on rentscope.example as'), told
    # WALK 8 (2026-11-20): the agent took that tab on to the next vendor - as it was told it could - and the held card went off the chat. A held
    # sign-up stays lit wherever its tab goes; his press opens its form again in a tab of Taskuary's own, fills back the boxes kept with it, sends
    left = [{'id': 'T1', 'url': shown['url']}]
    with mock.patch.object(browserview, 'pages', return_value=left), mock.patch.object(browsergate, '_tell'):
        assert browsergate.left_page(s, tid, 'sess1') == [] and s.get_review(rv['ReviewId'])['Status'] == 'pending'
    again, told = UpPage(user=''), []
    class Own:
        def __init__(self, sid, url): self.url = url
        def __enter__(self): again.href = self.url; return again, True
        def __exit__(self, *a): pass
    with mock.patch.object(browserview, 'pages', return_value=left), mock.patch.object(signin, 'tab_at', Own), mock.patch.object(signin, 'type_new', lambda *a: 1), \
         mock.patch.object(signin, 'send_new', lambda sid, site, c: c.go('data', 'https://www.rentscope.example/data') or {'ok': True}), \
         mock.patch.object(signin, 'SETTLE', 0), mock.patch.object(browsergate, '_tell', lambda s_, t, text, **k: told.append(text)):
        browsergate.perform(s, tid, p)
    assert any(x.startswith(signin.REFILL) and 'Alex Doyle' in x for x in again.ran), 'the boxes kept with the card filled back'
    assert told[0].startswith('The owner approved the sign-up on rentscope.example. Signed up on rentscope.example as'), told


def test_an_agent_that_still_ends_its_turn_with_the_sign_up_marker_gets_the_commands_answer():
    s = MemoryStore(); tid = Factory(s).task('Market data'); told = []
    with on_page('https://www.rentscope.example/signup'), mock.patch.object(signin, 'signup', return_value=(True, f'Signed up on rentscope.example as {USER}, and signed in: x')), \
         mock.patch.object(signin, '_continue', lambda *a, **k: told.append(k['words'])):
        signin.needs(s, tid, 'sess1', 'new:rentscope.example', watch=None)
        end = time.time() + 5
        while not told and time.time() < end: time.sleep(.02)
    assert told[0] == (f'Signed up on rentscope.example as {USER}', f'Signed up on rentscope.example as {USER}, and signed in: x'), told


def test_a_sign_up_with_no_page_a_password_goes_to_is_asked_as_a_sign_up():
    """A sign-up marker over a plain-http form (or no page at all) was asked of the owner as "Sign in to ... then say Signed in"."""
    s = MemoryStore(); tid = Factory(s).task('Market data')
    for url in ('http://rentscope.example/signup', 'about:blank'):
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': url}):
            signin.needs(s, tid, 'sess1', 'new:rentscope.example', watch=None)
        said = ws.status(s, tid)['requests'][-1]['text']
        assert said.startswith('Sign up on rentscope.example') and 'Sign in' not in said, said


def test_a_browser_socket_that_times_out_is_a_browser_that_did_not_answer():
    """The vendor walk, 2026-11-19: a page hung on a site that never answered, the DevTools socket raised its own TimeoutError, and the code
    watch died on it (no caller expects one) - the code LienLens emailed was never typed."""
    c = signin.Cdp.__new__(signin.Cdp); c.n, c.session, c.events = 0, None, []
    class Ws:
        def send(self, m): pass
        def recv(self, timeout=None): raise TimeoutError('timed out in 10.0s')
    c.ws = Ws()
    with pytest.raises(signin.SignInError): c.call('Runtime.evaluate')
    c.ws.send = lambda m: (_ for _ in ()).throw(ConnectionError('no close frame received or sent'))
    with pytest.raises(signin.SignInError): c.fields('')


# ONE NAME FOR A SITE (the roads audit, 2026-11-19): one payment step read www.toll.example on its card, toll.example on its hand-over and
# toll.example:8443 on the page - every surface names it by signin.site_name
def test_a_site_is_named_one_way_on_every_card_and_hand_over():
    for where in ('https://www.toll.example:8443/pay?x=1', 'https://pay.toll.example/', 'toll.example', 'WWW.Toll.Example.'):
        assert signin.site_name(where) == 'toll.example', where
    assert signin.site_name('http://127.0.0.6:8080/x') == '127.0.0.6'
    with mock.patch.object(signin, 'page_name', return_value='Northwind vendor portal'):
        assert signin.site_name('http://127.0.0.6:8080/x', 's1') == 'Northwind vendor portal'
    assert signin.site_name('') == ''
    from taskuary import browsergate
    pg = {'url': 'https://www.toll.example:8443/pay', 'elements': '- button "Pay $412.50" [ref=e12]'}
    assert browsergate.target({'verb': 'click', 'args': ['click', '@e12']}, pg).endswith(' on toll.example')


# WHICH KIND OF ASK, SAID BY THE SERVER (the roads audit, 2026-11-19): the page read `signin:` / `yourturn:` off the id in five places
def test_every_open_ask_carries_its_kind_and_site_so_the_page_never_reads_the_id():
    assert ws.ask_of(f'{signin.PREFIX}toll.example') == {'ask': 'signin', 'site': 'toll.example'}
    assert ws.ask_of(f'{browserview.TURN_PREFIX}ab12') == {'ask': 'turn', 'site': ''}
    assert ws.ask_of('q:where') == {'ask': 'question', 'site': ''}
    e = {'RequestId': f'{signin.PREFIX}toll.example', 'Kind': 'input_needed', 'Text': 'Sign in to toll.example', 'Sid': 's1', 'CreatedAt': 'now'}
    assert ws._public_request(e)['ask'] == 'signin' and ws._public_request(e)['site'] == 'toll.example'


# WHETHER HE HAS A PART ON THE PAGE is the server's one answer (taskstate.needs_owner) - the page rebuilt it from the ask's id
def test_the_server_says_whether_he_is_needed_on_the_page():
    from taskuary import taskstate
    act = lambda sid: {'DraftText': json.dumps({'action': 'browser_act', 'sid': sid})}
    assert not taskstate.needs_owner(None) and not taskstate.needs_owner({'ask': 'question'})
    assert taskstate.needs_owner({'ask': 'signin', 'site': 'bank.example'}) and taskstate.needs_owner({'ask': 'turn'})
    assert taskstate.needs_owner(None, [act('s1')], 's1') and not taskstate.needs_owner(None, [act('s2')], 's1')
    assert not taskstate.needs_owner(None, [{'DraftText': json.dumps({'action': 'shell_act', 'sid': 's1'})}], 's1')


# ...AND IT RIDES THE PAYLOAD THAT CARRIES THE ASK (chatlog.beside), every kind's: a coding task read its chat's own state once at opening, so
# its agent's hand-over never drew the page (the design loop, 2026-11-20)
def test_the_chat_payload_says_whether_he_is_needed_on_the_page():
    from taskuary import chatlog, taskstate
    s = MemoryStore()
    tid = s.create_task({'Title': 'Comment the ledger totals', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
    with mock.patch.object(taskstate, 'asking', return_value={'ask': 'turn', 'request_id': 'yourturn:1', 'text': 'sign in'}):
        assert chatlog.beside(s, tid, [], False, None)['needsOwner'] is True
    with mock.patch.object(taskstate, 'asking', return_value={'ask': 'question', 'request_id': 'q1', 'text': 'which month?'}):
        assert chatlog.beside(s, tid, [], False, None)['needsOwner'] is False


def test_a_press_of_done_is_told_as_a_press_never_as_a_sign_in():
    """Round 3, 2026-11-22: I'm done pressed on a sign-up page with nothing typed told the agent "the owner signed in on the page themselves".
    Seen on the page, he signed in; only pressed, the agent is told he pressed, and looks before it goes on."""
    from unittest import mock
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Sign up for DealFlow', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    with mock.patch.object(signin, '_continue') as told, mock.patch.object(signin, 'keep_typed', return_value=''):
        signin._through(s, tid, 'signin:dealflow.example', 'dealflow.example', seen=False)
    did, said = told.call_args.kwargs['words']
    assert did == f'You pressed {signin.DONE} on dealflow.example' and 'themselves' not in said and 'Look at the page' in said


def test_a_site_on_a_bare_address_is_named_by_its_title_s_site_part_never_the_whole_title():
    "Round 2, 2026-11-22: the hand-over read \"Sign in to Sign in - DealFlow Pro to continue\" - the page's whole title used as the site's name."
    from unittest import mock
    from taskuary import signin
    class C:
        def js(self, _): return '["Sign in - DealFlow Pro", "", "http://127.0.0.1:18791/s/dealflow/login"]'
        def close(self): pass
    with mock.patch.object(signin, 'connect', return_value=C()):
        assert signin.page_name('s1', '127.0.0.1') == 'DealFlow Pro'
