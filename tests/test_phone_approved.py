"""The owner-approved phone changes of 2026-10-22 (the overnight review's A1-A18), each pinned by what the phone SHOWS - a typed line or a
tap in through the channel's own poll, the bubbles out of its own send (tests/phone_transcript.py). The owner's rule over all of them:
someone can manage Taskuary from the phone alone, so every message ends with what to do next, and no state is a dead end.
Invented people only: Alex Doyle, Gail Moreno, Ray Colton, northwind.example."""
import json, re, time, unittest
from unittest import mock

from taskuary import remote_assistant as ra
from tests.phone_transcript import GAIL, ME, RAY, Phone, call, text_of


def _two_asks(f):
    a, _ = f._work('Badge access for the new hire', subject='Badge access for the new hire', from_name=RAY[0], from_email=RAY[1],
                   body='Alex, the new AP clerk starts Monday. Can you get her a badge for floors 2 and 3?', sent_at=f.ago(hours=3))
    b, _ = f._work('Visitor parking for Friday', subject='Visitor parking for Friday', from_name=GAIL[0], from_email=GAIL[1],
                   body='Can we get a visitor parking list for Friday? Security needs it by Thursday.', sent_at=f.ago(hours=2))
    return a, b


class PhoneCase(unittest.TestCase):
    channel, brain = 'whatsapp', None

    def setUp(self):
        self.ph = Phone(self.channel, brain=self.brain)
        self.addCleanup(self.ph.close)
        self.s, self.f = self.ph.s, self.ph.f

    def ends_with_choices(self, got):
        self.assertTrue(got and got[-1][1], f'a dead end - nothing to tap under: {text_of(got)!r}')


class RemindHasNoUndoTests(PhoneCase):
    """A15: "Bring it back now" - the undo for the task just put away - rode under the NEXT task's card. The owner dislikes undo buttons,
    and it is gone from the phone; the receipt says when it is back, and the next card's own choices follow."""

    def test_a_remind_offers_no_bring_it_back(self):
        a, b = _two_asks(self.f); self.ph.ready()
        self.ph.walk(); self.ph.tap('Remind me')
        got = self.ph.tap('Tomorrow')
        self.assertRegex(text_of(got), r'TQ-\d{4} is away until')
        self.assertNotIn('Bring it back now', [w for _t, b_ in got for w in b_])
        self.ends_with_choices(got)


class EndOfWalkTests(PhoneCase):
    """A1: the walk's end offered only Open picks, and outside a hand-off there was no way to start again. It offers "Walk me through my
    tasks" first, and the new walk shows every open task again from the top (next-is-seen-in-this-walk)."""

    def test_the_end_offers_a_new_walk_that_shows_every_open_task_again(self):
        a, b = _two_asks(self.f); self.ph.ready()
        first = text_of(self.ph.walk())
        self.ph.tap('Next')
        end = self.ph.tap('Next')
        self.assertIn("That's everything for now", text_of(end))
        self.assertEqual(end[-1][1][0], 'Walk me through my tasks', end[-1][1])
        again = self.ph.tap('Walk me through my tasks')
        ref = next(f'TQ-{t:04d}' for t in (a, b) if f'TQ-{t:04d}' in first)
        self.assertIn(ref, text_of(again))                                    # the first task again, not "nothing waiting"
        self.assertIn('Next', again[-1][1])


class PositionTests(PhoneCase):
    """A11: a long walk gave no sense of progress. Each card's first line says where it is in its section: "📋 on you · TQ-0001 · 1 of 3"."""
    channel = 'telegram'

    def test_each_card_says_where_it_is_in_its_section(self):
        _two_asks(self.f)
        self.f._work('Printer on 3 is jammed again', subject='Printer on 3 is jammed again', from_name=RAY[0], from_email=RAY[1],
                     body='The big printer on floor 3 is jammed again, can someone call the vendor?', sent_at=self.f.ago(hours=1))
        self.ph.ready()
        firsts = [text_of(self.ph.walk()).split('\n')[0]] + [text_of(self.ph.tap('Next')).split('\n')[0] for _ in range(2)]
        for n, line in enumerate(firsts, 1): self.assertRegex(line, rf'^\S+ on you · TQ-\d{{4}} · {n} of 3$', firsts)

    def test_a_section_of_one_says_nothing(self):
        self.f._work('Printer on 3 is jammed again', subject='Printer on 3 is jammed again', from_name=RAY[0], from_email=RAY[1],
                     body='The big printer on floor 3 is jammed again, can someone call the vendor?', sent_at=self.f.ago(hours=1))
        self.ph.ready()
        self.assertNotIn(' of 1', text_of(self.ph.walk()).split('\n')[0])


def _report(ph, title='Helpdesk tickets by day'):
    """A scheduled report that landed: eight rows of helpdesk tickets."""
    rows = '\n'.join('{"day": "2026-10-%02d", "tickets": %d}' % (d, 30 + d) for d in range(12, 20))
    sid = ph.s.save_source({'Channel': 'report', 'Address': title, 'Active': 1, 'ConfigJson': json.dumps({'type': 'mssql', 'title': title})}, 't')
    ph.s.touch_source(sid)
    mid = ph.f.message(task_id=None, status='filed', channel='report', subject=f'{title} - 8 rows',
                       source_name=title, from_name=title, conversation_id=f'report:{sid}', body=rows)
    ph.f.route(mid, None, 'file', 'scheduled report', by='report')
    return mid


class FyiLeadsWithGotItTests(PhoneCase):
    """A8: an FYI led with "Put it on my list", and one tap sent a newsletter to an agent. FYI cards lead with Got it - their read-and-next
    - and offer no Send to agent."""

    def setUp(self):
        super().setUp()
        for s in ('FW: Quarterly newsletter', 'Office closed Monday'): self.f.filed_fyi(subject=s)
        self.ph.ready()

    def test_the_batch_leads_with_got_it_and_its_lines_are_numbered_as_the_poll_carries_them(self):
        """The owner, 2026-10-22: the batch leads with Got it too - 1 is Got it, the lines 2 on, so a typed number is the poll's own."""
        got = self.ph.walk()
        text, btns = got[-1]
        self.assertEqual(btns[0], 'Got it', btns)
        numbered = re.findall(r'(?m)^(\d+) · (.+)$', text)
        self.assertEqual([w for _n, w in numbered], btns[:len(numbered)], text)          # the text's numbers ARE the poll's order
        self.assertEqual([int(n) for n, _w in numbered], list(range(1, len(numbered) + 1)))
        self.assertEqual(btns.count('Got it'), 1)
        two = text_of(self.ph.type('2'))                                                   # 2 is the first line: it opens
        self.assertIn(numbered[1][1].split(' - ', 1)[1], two)

    def test_the_batch_is_passed_with_got_it_and_never_sent_to_an_agent(self):
        got = self.ph.walk()
        btns = got[-1][1]
        self.assertIn('Got it', btns); self.assertNotIn('Next', btns); self.assertNotIn('Send to agent', btns)
        self.assertNotIn('Got it', self.ph.tap('Got it')[-1][1])            # passed: the walk moved on

    def test_one_fyi_opened_leads_with_got_it_and_can_still_go_on_your_list(self):
        batch = self.ph.walk()
        one = self.ph.tap(next(b for b in batch[-1][1] if 'Quarterly newsletter' in b))
        btns = one[-1][1]
        self.assertEqual(btns[0], 'Got it', btns)
        self.assertNotIn('Send to agent', btns); self.assertIn('Should be a task', btns); self.assertIn('Not ours', btns)   # an FYI's Put it on my list (2026-10-29)
        self.assertNotIn('Should be a task:', text_of(one))                    # no "then" line for a verb that does not lead
        self.assertRegex(text_of(self.ph.tap('Should be a task')), r'TQ-\d{4} is on your list\.')


class ReportLeadsWithNextTests(PhoneCase):
    """A9: a report "needs nothing", yet its first choice was Put it on my list, which made it a to-do that then offered Reply to a report.
    A report card leads with Next, and Put it on my list goes."""

    def test_a_report_card_leads_with_next(self):
        _report(self.ph); self.ph.ready(); self.ph.opener()
        got = self.ph.tap('Walk Reports')
        self.assertIn('Helpdesk tickets by day', text_of(got))
        btns = got[-1][1]
        self.assertEqual(btns[0], 'Next', btns)
        self.assertNotIn('Put it on my list', btns)
        self.assertNotIn('Put it on my list:', text_of(got))


class ShortOpenerTests(PhoneCase):
    """A7: the day's opener offered nine options, walks beside section walks beside browse areas ("Walk me through my tasks" next to
    "Walk Tasks", "Reports" next to "Walk Reports"). It offers about four, and More… keeps every other one reachable."""
    EVERYTHING = {'Walk me through my tasks', 'Set up a report', 'Walk Tasks', 'Walk Reports', 'Walk FYI', 'Connections', 'Reports', 'Hub', 'Settings'}

    def setUp(self):
        super().setUp()
        _two_asks(self.f); _report(self.ph); self.f.filed_fyi(subject='Office closed Monday'); self.ph.ready()

    def test_the_opener_offers_four_clear_options(self):
        got = self.ph.opener()
        self.assertEqual(got[-1][1], ['Walk me through my tasks', 'Walk Reports', 'Walk FYI', 'More…'])
        self.assertIn('TASKS · 2', text_of(got))                               # the summary itself is unchanged

    def test_more_reaches_everything_the_nine_options_did(self):
        opener = self.ph.opener()[-1][1]
        more = self.ph.tap('More…')
        self.assertEqual(self.EVERYTHING - set(opener) - set(more[-1][1]), set(), more[-1][1])
        self.assertIn('Connections', text_of(self.ph.tap('Connections')))      # each still goes where it went

    def test_the_walk_off_the_menu_goes_straight_to_the_first_card(self):
        self.ph.opener(); self.ph.tap('More…')
        got = self.ph.tap('Walk me through my tasks')
        self.assertNotIn('TASKS · ', text_of(got)); self.assertRegex(text_of(got), r'TQ-\d{4}')


PATCH = ('Hi - I pushed a fix for the census export to the importers repo, branch ray/fix-census. '
         'Can your agent check it out, run the tests and merge it today?')


def _held(f, s):
    from taskuary.ingest import HOLD_TAG
    tid, _ = f._work('Patch for the census export', kind='coding', subject='Patch for the census export', from_name='Ray Colton',
                     from_email='ray.colton@vendor.example', body=PATCH, sent_at=f.ago(minutes=5))
    s.update_task(tid, {'Summary': PATCH}, 'triage'); s.tag_task(tid, HOLD_TAG)
    return tid


class HeldStrangerChoicesTests(PhoneCase):
    """A3: a held stranger's card offered Send to agent - one tap ran a new sender's branch. Until the sender is accepted it offers no
    hand-off: its choices lead with Trust them (the task page's own vouch) and Not ours, and the card says what it asks."""

    def test_a_held_card_offers_trust_and_not_ours_and_no_agent(self):
        _held(self.f, self.s); self.ph.ready()
        got = self.ph.walk()
        btns = got[-1][1]
        self.assertEqual(btns[:2], ['Trust them', 'Not ours'], btns)
        self.assertNotIn('Send to agent', btns); self.assertNotIn('Send to coding agent', btns)
        self.assertIn('Next', btns)
        self.assertIn('do you know this sender?', text_of(got))

    def test_trusting_them_lifts_the_hold_and_offers_the_hand_off_without_starting_anything(self):
        from taskuary import general
        from taskuary.ingest import HOLD_TAG
        tid = _held(self.f, self.s); self.ph.ready(); self.ph.walk()
        with mock.patch.object(general, 'start_session', side_effect=AssertionError('nothing starts on a vouch')):
            got = self.ph.tap('Trust them')
        self.assertFalse(self.s.task_has_tag(tid, HOLD_TAG))
        said = text_of(got)
        self.assertIn(f'TQ-{tid:04d}', said); self.assertIn('nothing has started', said); self.assertNotIn('New sender', said)
        self.assertIn('Send to agent', got[-1][1]); self.assertNotIn('Trust them', got[-1][1])


class TrustIsATapNeverTheModelsTests(PhoneCase):
    """The owner, 2026-10-22: keep Trust them as built - a button run in code, never a tool the model can call. A typed "trust them" that
    the model answers with a CALL of task.trust lifts nothing: only the tap does."""
    brain = staticmethod(lambda said: 'Ok.\n' + call('task.trust') if 'trust' in said.lower() else 'Ok.')

    def test_the_model_cannot_vouch_and_the_tap_can(self):
        from taskuary import toolcatalog
        from taskuary.ingest import HOLD_TAG
        self.assertNotIn('task.trust', toolcatalog.PURPOSE)
        tid = _held(self.f, self.s); self.ph.ready(); self.ph.walk()
        self.ph.type('trust them, I know Ray')
        self.assertTrue(self.s.task_has_tag(tid, HOLD_TAG), 'typed words never vouch')
        self.ph.tap('Trust them')
        self.assertFalse(self.s.task_has_tag(tid, HOLD_TAG))


class AfterTheRunTests(PhoneCase):
    """A2: R2 on the phone. A failed agent offered Stop and save | Next | Remind me - nothing that tries again; a finished one never offered
    Mark done, and on a task the rail shows as yours read "No agent yet". A failed agent leads with Try again (and Connect an AI when no AI
    is why); a finished one leads with Mark done."""
    STALE = 'The run stopped: the staging database refused the login.'

    def _ended(self, how, why=STALE, live=False):
        from types import SimpleNamespace as NS
        from taskuary import terminal, workerstate as ws
        p = self.f.running('Fix the export', agent='claude')
        if live:
            rows = [{'taskId': p.tid, 'sid': 'sF', 'agent': 'claude', 'label': 'claude', 'waiting': True, 'idle': 300,
                     'started': self.f.ago(minutes=10), 'state': 'asking', 'tail': ['Which database should I use?']}]
            for x in (mock.patch.dict(terminal.SESSIONS, {'sF': NS(sid='sF', task_id=p.tid, alive=True, started=0, agent='claude', mode='')}),
                      mock.patch.object(terminal, 'live_sessions', return_value=rows)):
                x.start(); self.addCleanup(x.stop)
        ws.record(self.s, p.tid, 'sF', 'working')
        ws.record(self.s, p.tid, 'sF', how, text=why if how == 'failed' else 'Kept the inter-company rows; the export matches the bank feed.')
        if not live: self.s.update_run(p.run_id, {'Status': 'failed' if how == 'failed' else 'done'}, finished=True)
        self.ph.ready()
        return p.tid

    def test_a_failed_agent_with_its_session_open_leads_with_try_again_and_one_tap_runs_it(self):
        from taskuary import server
        tid = self._ended('failed', live=True)
        card = self.ph.walk()
        self.assertEqual(card[-1][1][0], 'Try again', card[-1][1])
        with mock.patch.object(server, 'continue_work', return_value={'continued': True}) as go:
            got = self.ph.tap('Try again')
        self.assertEqual(go.call_args.args[0], tid)
        self.assertIn(f'Continuing TQ-{tid:04d}', text_of(got)); self.ends_with_choices(got)

    def test_a_failed_task_leads_with_try_again_not_the_desks_continue(self):
        self._ended('failed')
        btns = self.ph.walk()[-1][1]
        self.assertEqual(btns[0], 'Try again', btns); self.assertNotIn('Continue', btns)

    def test_no_ai_is_why_so_connect_an_ai_comes_with_it(self):
        self._ended('failed', why='no AI connector is set up for this agent')
        btns = self.ph.walk()[-1][1]
        self.assertEqual(btns[:2], ['Try again', 'Connect an AI'], btns)
        got = self.ph.tap('Connect an AI')
        self.assertIn('CONNECTIONS · AI', text_of(got)); self.ends_with_choices(got)

    def test_a_finished_agent_says_so_and_leads_with_mark_done(self):
        tid = self._ended('finished')
        card = self.ph.walk()
        self.assertNotIn('No agent yet', text_of(card)); self.assertIn('finished', text_of(card))
        self.assertEqual(card[-1][1][0], 'Mark done', card[-1][1])
        self.assertIn(f'TQ-{tid:04d} closed', text_of(self.ph.tap('Mark done')))
        self.assertEqual(self.s.get_task(tid)['Status'], 'done')

    def test_a_finished_agents_task_asks_no_who_should_take_it_on_either_surface(self):
        """The owner, 2026-10-22: a task its agent finished leads with Mark done on the phone AND the desktop - one move, read in one place
        (funnel_presentation.move_of): the desk's card reads it off the item's `shows`, the phone off the same."""
        from taskuary import concierge, funnel
        tid = self._ended('finished')
        card = self.ph.walk()
        self.assertNotIn('who should take it?', text_of(card)); self.assertIn('You* · Mark done', text_of(card))
        self.assertEqual(card[-1][1][0], 'Mark done')
        row = next(i for i in funnel.pile(self.s)['items'] if str(i.get('tid')) == str(tid))
        self.assertEqual(row['shows']['move'], 'Mark done')                                # what the desk's card reads
        self.assertEqual(concierge.surface(self.s, row['key'])['item']['shows']['move'], 'Mark done')

    def test_the_follow_up_of_a_failed_agent_leads_with_try_again(self):
        tid = self._ended('failed', live=True)
        self.s.set_setting(ra.PROMISES_KEY, json.dumps([{'tid': tid, 'channel': 'whatsapp', 'chat': self.ph.chat, 'connector_id': self.ph.cid,
                                                          'at': time.time(), 'lane': 'working', 'armed': True}]), 't')
        got = self.ph.push(lambda: ra.keep_promises(self.s, force=True))
        self.assertEqual(got[-1][1][0], 'Try again', got[-1][1])


MODEL = 'THE MODEL ANSWERED'


def _no_model(said): return MODEL                     # what reaches the phone if a built-in word went to the model


class HelpAndStopTests(PhoneCase):
    """A16: "/help" and "/stop" went to the model and came back "Ok.". help, /help (and Telegram's /start) show what the phone can do in a
    few lines; stop and /stop end the walk cleanly. No model, both channels, and a way on under each."""
    brain = staticmethod(_no_model)

    def setUp(self):
        super().setUp()
        self.a, self.b = _two_asks(self.f); self.ph.ready()

    def test_help_says_what_you_can_do_with_the_way_back_to_the_card(self):
        first = text_of(self.ph.walk())
        ref = next(f'TQ-{t:04d}' for t in (self.a, self.b) if f'TQ-{t:04d}' in first)
        for said in ('help', '/help'):
            got = self.ph.type(said)
            self.assertNotIn(MODEL, text_of(got))
            self.assertIn('What you can do here', text_of(got)); self.assertIn('"stop" ends the walk', text_of(got))
            self.assertEqual(got[-1][1][:2], [f'Back to {ref}', 'Walk me through my tasks'], got[-1][1])
        self.assertIn(ref, text_of(self.ph.tap(f'Back to {ref}')))

    def test_stop_ends_the_walk_and_the_next_one_starts_from_the_top(self):
        first = text_of(self.ph.walk()); self.ph.tap('Next')
        got = self.ph.type('/stop')
        self.assertNotIn(MODEL, text_of(got))
        self.assertIn('Stopped - the walk is over', text_of(got))
        self.assertIn('Walk me through my tasks', got[-1][1])
        again = text_of(self.ph.tap('Walk me through my tasks'))
        self.assertEqual(re.findall(r'TQ-\d{4}', again)[:1], re.findall(r'TQ-\d{4}', first)[:1])

    def test_a_request_with_the_word_in_it_is_still_words(self):
        self.ph.walk()
        with mock.patch.object(self.ph, 'brain_fn', lambda said: 'Which agent do you mean?') as _:
            self.assertIn('Which agent do you mean?', text_of(self.ph.type('stop the agent on the export')))


class TelegramHelpTests(HelpAndStopTests):
    channel = 'telegram'

    def test_telegrams_own_start_is_help(self):
        self.assertIn('What you can do here', text_of(self.ph.type('/start')))
        self.assertIn('What you can do here', text_of(self.ph.type('/help@TaskuaryBot')))


class VoiceEchoTests(PhoneCase):
    """A17: a voice note was acted on and the owner could not tell what had been transcribed. The answer says it back first."""
    channel = 'telegram'
    brain = staticmethod(lambda said: 'It is the new AP clerk\'s badge, for floors 2 and 3.')
    SAID = 'what is this one about'

    def _voice(self):
        from taskuary import voice
        with mock.patch.object(voice, 'transcribe', return_value={'text': self.SAID}): return self.ph.voice()

    def test_a_voice_note_is_said_back_before_the_answer(self):
        _two_asks(self.f); self.ph.ready(); self.ph.walk()
        got = self._voice()
        self.assertTrue(got[0][0].removeprefix('Taskuary:\n').startswith(f'🎤 Heard: "{self.SAID}"'), got[0][0])
        self.assertIn("new AP clerk's badge", text_of(got)); self.ends_with_choices(got)
        self.assertEqual(text_of(got).count('Heard:'), 1)
        self.assertNotIn('Heard:', text_of(self.ph.type('and who sent it?')))       # typed words are not said back


class WhatsAppVoiceEchoTests(VoiceEchoTests):
    channel = 'whatsapp'

    def _voice(self):
        import os, tempfile
        from taskuary import voice
        fd, path = tempfile.mkstemp(suffix='.ogg'); os.write(fd, b'OggS fake'); os.close(fd)
        self.addCleanup(os.remove, path)
        self.ph.queue.append({'id': 'v1', 'jid': self.ph.chat, 'text': '', 'audio': path, 'mime': 'audio/ogg', 'fromMe': True, 'ts': time.time()})
        with mock.patch.object(voice, 'transcribe', return_value={'text': self.SAID}): return self.ph._took(self.ph._poll)

    def test_a_voice_note_is_said_back_before_the_answer(self):
        super().test_a_voice_note_is_said_back_before_the_answer()


class RedraftAsksTests(PhoneCase):
    """A18 (a): Redraft rewrote the draft at once, with no word on what should change. It asks - Shorter, Just rewrite, or the change typed -
    and Cancel goes back to the draft."""

    ai, draft = True, 'Hi Gail - yes, renew it for Q3.'

    def setUp(self):
        super().setUp()
        from taskuary import capabilities
        hold = mock.patch.object(capabilities, 'has_ai', return_value=self.ai); hold.start(); self.addCleanup(hold.stop)
        p = self.f.pending_draft(title='Q3 vendor contract renewal', subject='Q3 vendor contract renewal', from_name=GAIL[0],
                                           from_email=GAIL[1], body='Are we renewing the Payworth contract for Q3?',
                                           draft=self.draft, sent_at=self.f.ago(hours=1))
        self.tid, self.rid = p.tid, p.rid
        self.ph.ready(); self.card = self.ph.walk()

    def _rewrite(self, go):
        from taskuary import server
        with mock.patch.object(server, 'open_reply', return_value={'reviewId': self.rid}) as wrote: got = go()
        return got, wrote

    def test_redraft_asks_what_should_change_and_the_typed_line_is_the_instruction(self):
        asked = self.ph.tap('Redraft')
        self.assertIn('What should change?', text_of(asked))
        self.assertEqual(asked[-1][1], ['Shorter', 'Just rewrite', 'Cancel'])
        got, wrote = self._rewrite(lambda: self.ph.type('say we renew for two years, not one'))
        body = wrote.call_args.args[1]
        self.assertTrue(body.redraft); self.assertEqual(body.instruction, 'say we renew for two years, not one')
        self.assertIn('Send', got[-1][1])                                     # the draft again, with its own choices

    def test_shorter_is_one_tap(self):
        self.ph.tap('Redraft')
        _got, wrote = self._rewrite(lambda: self.ph.tap('Shorter'))
        self.assertEqual(wrote.call_args.args[1].instruction, 'Make it shorter.')

    def test_cancel_goes_back_to_the_draft_and_the_next_line_is_words_again(self):
        self.ph.tap('Redraft')
        back = self.ph.tap('Cancel')
        self.assertEqual(back[-1][1], self.card[-1][1])
        from taskuary import server
        with mock.patch.object(server, 'open_reply', side_effect=AssertionError('no redraft after Cancel')): self.ph.type('next')


class RedraftWithNoAiTests(RedraftAsksTests):
    """A18 (b), the 2026-10-22 walk: with no AI, Draft with AI asked "What should change?", wrote nothing and asked again - round and
    round with no reason. It says no AI is connected, with Connect an AI, and never asks what to change."""
    ai = False

    def test_redraft_says_no_ai_with_connect_an_ai(self):
        from taskuary import server
        with mock.patch.object(server, 'open_reply', side_effect=AssertionError('nothing can write it')):
            got = self.ph.tap(next(w for w in self.card[-1][1] if w in ('Redraft', 'Draft with AI')))
        self.assertIn('No AI is connected to write the draft', text_of(got))
        self.assertNotIn('What should change?', text_of(got))
        self.assertEqual(got[-1][1], ['Connect an AI', 'Next'])

    def test_set_up_a_report_says_no_ai_too(self):
        self.assertIn('No AI is connected to put a report together', ra.script_words(self.s, 'set up a report'))

    # the A18 (a) asks are an AI's: with none they are this class's own tests above
    test_redraft_asks_what_should_change_and_the_typed_line_is_the_instruction = test_shorter_is_one_tap = None
    test_cancel_goes_back_to_the_draft_and_the_next_line_is_words_again = None


class EmptyDraftTests(RedraftAsksTests):
    """...and over an EMPTY draft there is nothing for "What should change?" to be about: Draft with AI writes it."""
    draft = ''

    def test_an_empty_draft_is_written_without_asking(self):
        got, wrote = self._rewrite(lambda: self.ph.tap(next(w for w in self.card[-1][1] if w in ('Redraft', 'Draft with AI'))))
        self.assertNotIn('What should change?', text_of(got))
        self.assertTrue(wrote.called)

    test_redraft_asks_what_should_change_and_the_typed_line_is_the_instruction = test_shorter_is_one_tap = None
    test_cancel_goes_back_to_the_draft_and_the_next_line_is_words_again = None


def _brain(calls):
    """A scripted model: the first typed words it knows CALL their tool, anything else is "Ok."."""
    return staticmethod(lambda said: next((f'On it.\n' + call(k, **p) for w, (k, p) in calls.items() if w in said.lower()), 'Ok.'))


class TypedActBringsUpThePickerTests(PhoneCase):
    """A6: a typed act came back as "Remind me: Fri 23 Oct: TQ-0001. Nothing happens until you say yes." with yes/no under it - a confirm
    card the owner does not want (the router rule: light the real button). A typed Remind me brings up the card's own day picker, the typed
    day first; an act that is one of the card's buttons brings the card up with that button first. A set of items keeps its yes/no."""
    brain = _brain({'remind me': ('task.defer', {'until': 'friday'}), 'close it': ('task.complete', {})})

    def setUp(self):
        super().setUp()
        self.a, self.b = _two_asks(self.f); self.ph.ready()
        first = text_of(self.ph.walk())
        self.tid = next(t for t in (self.a, self.b) if f'TQ-{t:04d}' in first)

    def test_remind_me_friday_is_the_day_picker_with_friday_first(self):
        got = self.ph.type('remind me about this friday')
        btns = got[-1][1]
        self.assertNotIn('yes, go ahead', btns); self.assertNotIn('Nothing happens until you say yes', text_of(got))
        self.assertRegex(btns[0], r'^Fri \d+ \w{3}$', btns)
        self.assertEqual(btns[1:], ['Tomorrow', 'Next week', 'In 2 weeks', 'In a month', 'Cancel'])
        self.assertRegex(text_of(self.ph.tap(btns[0])), rf'TQ-{self.tid:04d} is away until Fri')

    # ...but a PUT-DOWN typed is done at once (the owner, 2026-10-23: "it should be the pill saying i have closed this task for you"):
    # no yes/no, no card brought up to tap - the short receipt, and the walk goes on
    def test_close_it_is_done_at_once_with_a_short_receipt(self):
        got = self.ph.type('close it, it is handled')
        said = text_of(got)
        self.assertNotIn('yes, go ahead', [b for _t, bs in got for b in bs]); self.assertNotIn('Nothing happens until you say yes', said)
        self.assertIn(f'TQ-{self.tid:04d} closed', said)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')

    def test_a_set_of_items_keeps_its_yes_or_no(self):
        for subj in ('Weekly platform digest', 'Office closed Monday'): self.f.filed_fyi(subject=subj)
        self.ph.ready()
        with mock.patch.object(self.ph, 'brain_fn', lambda said: 'Ok.\n' + call('pipe.clear', select={'kind': 'fyi'})):
            self.assertIn('yes, go ahead', self.ph.type('clear all the FYI')[-1][1])


class AfterTheHandBackTests(PhoneCase):
    """A5: a walk handed back to the desktop said "Message me any time and I will pick it up again" - and a chat that listens only during a
    walk then ignored the next message. After a hand-back the chat keeps listening: the next message picks the walk up again, and says so."""

    def setUp(self):
        super().setUp()
        ra.set_listens(self.s, self.channel, 'walk')                          # the standing phone assistant is off for this chat
        self.a, self.b = _two_asks(self.f); self.ph.ready()

    def test_the_next_message_after_a_hand_back_picks_the_walk_up_again(self):
        self.ph.push(lambda: ra.start_handoff(self.s, self.channel))
        bye = self.ph.type('stop')                                            # the walk goes back to the desktop
        self.assertIsNone(ra.handoff(self.s))
        self.assertIn('Message me any time', text_of(bye)); self.assertIn('Walk me through my tasks', bye[-1][1])
        got = self.ph.type('next')
        self.assertTrue(got, 'the message after the hand-back was ignored')
        self.assertIn('Picking the walk up here again', text_of(got)); self.ends_with_choices(got)
        self.assertNotIn('Picking the walk up here again', text_of(self.ph.tap('Next')))    # said once

    def test_the_hand_back_s_own_choice_walks_again(self):
        self.ph.push(lambda: ra.start_handoff(self.s, self.channel))
        self.ph.push(lambda: ra.end_handoff(self.s))                           # Walk it here, pressed on the desktop
        got = self.ph.tap('Walk me through my tasks')
        self.assertRegex(text_of(got), r'TQ-\d{4}'); self.ends_with_choices(got)

    def test_a_chat_never_handed_anything_still_hears_nothing(self):
        self.assertEqual(self.ph.type('next'), [])


class TelegramFirstContactTests(PhoneCase):
    """A4: on Telegram, /start and "hello" from a chat nobody chose got total silence, and picking the chat on the desktop sent nothing. An
    unchosen private chat gets one fixed line - nothing about the owner in it, at most every few hours - and a chat just picked says hello."""
    channel = 'telegram'

    def _from(self, chat, text):
        mid = next(self.ph.ids)
        self.ph.queue.append({'update_id': mid, 'message': {'message_id': mid, 'text': text, 'date': int(time.time()),
                              'chat': {'id': int(chat), 'type': 'private'}, 'from': {**ME, 'id': int(chat)}}})
        return self.ph._took(self.ph._poll)

    def test_an_unchosen_chat_gets_one_fixed_line_and_no_data(self):
        _two_asks(self.f); self.ph.ready()
        (said, btns), = self._from('777001', '/start')
        self.assertIn('choose this chat on the desktop', said); self.assertEqual(btns, [])
        for private in ('Badge access', 'Visitor parking', 'Ray', 'Gail', 'TQ-'): self.assertNotIn(private, said)
        self.assertEqual(self._from('777001', 'hello?'), [], 'once, not on every message')

    def test_picking_the_chat_on_the_desktop_says_hello_with_the_way_in(self):
        from taskuary import server
        from tests.phone_transcript import _Sync
        self.s.save_source({'Channel': 'telegram', 'Address': '900200', 'Active': 0, 'Owner': 'discovered: Alex Doyle'}, 't')
        with mock.patch.object(server.threading, 'Thread', _Sync):
            got = self.ph._took(lambda: server.set_assistant_doorway(server.DoorwayBody(channel='telegram', chat='900200')))
        (said, btns), = got
        self.assertIn(ra.PICKED, said); self.assertEqual(btns, ['Walk me through my tasks', 'More…'])


class WhileClosedTests(PhoneCase):
    """A10: messages sent while Taskuary was closed were each answered and acted on when it opened - an hour-old "next" included - and
    nothing said the app had been closed. Only the newest is acted on; the older ones get their thumb and are named, not acted on."""
    channel = 'telegram'

    def _queue(self, *texts):
        for t in texts:
            if self.channel == 'telegram': self.ph.queue.append({'update_id': next(self.ph.ids), 'message': {'message_id': next(self.ph.ids), 'text': t,
                                     'date': int(time.time()) - 600, 'chat': {'id': int(self.ph.chat), 'type': 'private'}, 'from': ME}})
            else: self.ph.queue.append({'id': f'in{next(self.ph.ids)}', 'jid': self.ph.chat, 'text': t, 'fromMe': True, 'poll': False, 'ts': time.time() - 600})

    def test_only_the_newest_queued_message_is_acted_on_and_the_rest_are_named(self):
        a, b = _two_asks(self.f); self.ph.ready()
        first = text_of(self.ph.walk())
        with mock.patch.object(ra, 'STARTED', time.time(), create=True):                 # Taskuary just opened; the three waited ten minutes
            self._queue('next', 'next', 'help')
            got = self.ph._took(self.ph._poll)
        said = text_of(got)
        self.assertEqual(said.count('Taskuary was closed - picking up from your last message.'), 1, said)
        self.assertIn('2 earlier messages were not acted on: "next"; "next".', said)
        self.assertIn('What you can do here', said)                           # the newest, "help", answered
        self.assertEqual(said.count('What you can do here'), 1)
        ref = next(f'TQ-{t:04d}' for t in (a, b) if f'TQ-{t:04d}' in first)
        self.assertIn(f'Back to {ref}', got[-1][1])                           # neither "next" moved the walk
        if self.channel == 'telegram': self.assertEqual(getattr(self.ph, 'reacted', 0), 3, 'every one gets its thumb')

    def test_a_message_sent_while_it_runs_is_acted_on_as_ever(self):
        _two_asks(self.f); self.ph.ready(); self.ph.walk()
        self.assertNotIn('Taskuary was closed', text_of(self.ph.type('help')))


class WhatsAppWhileClosedTests(WhileClosedTests):
    channel = 'whatsapp'


class TelegramSendRetryTests(PhoneCase):
    """A13: a failed Telegram send was only logged - the phone got nothing and never knew. It is tried again with backoff; still failing, the
    next message that gets through says so first."""
    channel = 'telegram'

    def _flaky(self, fails):
        left = [fails]
        def tg(tok, method, **p):
            if method == 'sendMessage' and left[0]:
                left[0] -= 1; raise RuntimeError('telegram sendMessage: Bad Gateway')
            return self.ph._tg(tok, method, **p)
        return mock.patch('taskuary.messengers.tg', side_effect=tg)

    def setUp(self):
        super().setUp()
        _two_asks(self.f); self.ph.ready(); self.ph.walk()

    def test_a_blip_is_tried_again_and_the_message_arrives(self):
        with self._flaky(2), mock.patch.object(ra, '_pause', create=True) as waited:
            got = self.ph.tap('Next')
        self.assertTrue(got and got[-1][1], 'the card arrived, with its buttons')
        self.assertEqual([c.args[0] for c in waited.call_args_list], [1.0, 3.0])          # backing off

    def test_a_message_that_never_arrived_is_said_on_the_next_one(self):
        with self._flaky(99), mock.patch.object(ra, '_pause', create=True):
            self.assertEqual(self.ph.tap('Next'), [])
        got = self.ph.type('help')
        self.assertTrue(got[0][0].startswith('My last message did not reach you ("'), got[0][0])
        self.assertIn('What you can do here', text_of(got))
        self.assertNotIn('did not reach you', text_of(self.ph.type('help')))             # said once


class UrgentMidWalkTests(PhoneCase):
    """A12: an urgent mail from Gail landed while the owner walked a section, and the walk went on past it without a word. The next card
    says so in one short line, with an Open for it - once in a walk."""

    def _urgent(self):
        tid, _ = self.f._work('Payroll file rejected', subject='Payroll file rejected', from_name=GAIL[0], from_email=GAIL[1],
                              body='The bank rejected the payroll file - staff will not be paid Friday unless we resend today.', sent_at=self.f.ago(minutes=1))
        self.s.update_task(tid, {'Priority': 'urgent'}, 'triage'); self.ph.ready()
        return tid

    def test_walking_a_section_the_next_card_names_it_with_an_open(self):
        _report(self.ph); _report(self.ph, 'Open purchase orders'); self.ph.ready()
        self.ph.opener(); self.ph.tap('Walk Reports')
        tid = self._urgent()
        got = self.ph.tap('Next')
        said = text_of(got)
        self.assertIn('New since you started: Gail Moreno - Payroll file rejected (urgent).', said)
        self.assertIn(f'Open TQ-{tid:04d}', got[-1][1])
        self.assertEqual(said.count('New since you started'), 1)
        self.assertIn('Payroll file rejected', text_of(self.ph.tap(f'Open TQ-{tid:04d}')))

    def test_said_once_in_a_walk(self):
        _two_asks(self.f)
        for s in ('Office closed Monday', 'Weekly platform digest'): self.f.filed_fyi(subject=s)
        self.ph.ready(); self.ph.opener(); self.ph.tap('More…'); self.ph.tap('Walk Tasks')
        self._urgent()
        self.assertIn('New since you started', text_of(self.ph.tap('Next')))
        self.assertNotIn('New since you started', text_of(self.ph.tap('Next')))

    def test_when_the_walk_brings_it_next_there_is_nothing_to_say(self):
        _two_asks(self.f); self.ph.ready(); self.ph.walk()
        self._urgent()
        # urgent is walked in its place (the owner, 2026-10-22): Next reaches it in rail order - the other ask first, then it - and on
        # its own card the heads-up is not said again, nor under the walk's end after it
        seen = [text_of(self.ph.tap('Next')) for _ in range(2)]
        self.assertIn('Visitor parking for Friday', seen[0])
        self.assertIn('Payroll file rejected', seen[1]); self.assertNotIn('New since you started', seen[1])
        self.assertNotIn('New since you started', text_of(self.ph.tap('Next')))


class NoPickEndsTests(PhoneCase):
    """Found while building (the owner's principle - no dead ends): "no, leave it" under a yes/no answered "Left it - nothing moved." with
    nothing to tap. A pick's answer that offers nothing gets the way on: back to the card on the table, the walk, everything else."""
    brain = staticmethod(lambda said: 'Ok.\n' + call('pipe.clear', select={'kind': 'fyi'}) if 'clear' in said.lower() else 'Ok.')

    def test_no_leave_it_comes_back_to_the_card(self):
        for subj in ('Weekly platform digest', 'Office closed Monday'): self.f.filed_fyi(subject=subj)
        a, b = _two_asks(self.f); self.ph.ready()
        first = text_of(self.ph.walk())
        ref = next(f'TQ-{t:04d}' for t in (a, b) if f'TQ-{t:04d}' in first)
        self.ph.type('clear all the FYI')
        got = self.ph.tap('no, leave it')
        self.assertIn('Left it - nothing moved.', text_of(got))
        self.assertEqual(got[-1][1][:2], [f'Back to {ref}', 'Walk me through my tasks'], got[-1][1])
        self.assertIn(ref, text_of(self.ph.tap(f'Back to {ref}')))


class FreshInstallNoAiTests(PhoneCase):
    """Found while building: a fresh install with no AI and nothing waiting answered "hi" with "Nothing's waiting. Connect an AI ..." and
    nothing to tap. It offers Connect an AI - the phone's list of AI connections - and More…."""

    def test_the_first_hi_has_a_way_on(self):
        got = self.ph.type('hi')
        self.assertIn('Connect an AI', text_of(got))
        self.assertEqual(got[-1][1], ['Connect an AI', 'More…'])
        self.assertIn('CONNECTIONS · AI', text_of(self.ph.tap('Connect an AI')))


class TelegramBareNumberTests(PhoneCase):
    """A18 (b): Telegram shows its choices as buttons with no numbers, yet a bare "2" silently ran button 2. It is not acted on: the answer
    says what the choices are, under them."""
    channel = 'telegram'

    def test_a_number_the_buttons_never_showed_runs_nothing(self):
        a, b = _two_asks(self.f); self.ph.ready()
        card = self.ph.walk()
        (said, btns), = self.ph.type('2')
        self.assertIn('"2" is not one of the choices', said); self.assertIn('Next', said)
        self.assertEqual(btns, card[-1][1])
        refs = {f'TQ-{t:04d}' for t in (a, b)}
        first = next(r for r in refs if r in text_of(card))
        self.assertIn((refs - {first}).pop(), text_of(self.ph.tap('Next')))  # "2" moved nothing: Next brings the second task


if __name__ == '__main__': unittest.main()
