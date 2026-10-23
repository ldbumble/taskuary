"""What the phone walk asks you, it has to show you - and a number is an answer, not a suggestion.

Driving a real ADP walk from WhatsApp, the owner was asked to "approve the draft below" with nothing
below it, picked "1 · Send the reply" and was asked "1 · yes, go ahead" for the same decision, waited
on the mail connector's 30-second clock for each of those round trips, and got no sign the hub had
even heard them (the owner, 2026-09-15: "this is confusing? I wrote 1 but it asked me again?" / "what
am i approving?" / "talking to whatsapp through assistant should be instant" / "can we also
automatically do thumbs up to know the ai agent got the whatsapp").
"""
import json, unittest
from unittest import mock

from taskuary import messengers, remote_assistant
from taskuary.store import MemoryStore

JID = '15551234567@s.whatsapp.net'


def store_with_a_draft():
    """A task with an arrived message and a reply waiting on the owner's yes."""
    s = MemoryStore()
    tid = s.create_task({'Title': 'Refund question', 'Kind': 'reply', 'Status': 'open'}, 'owner')
    mid = s.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'FromName': 'Tess', 'FromEmail': 'tess@x.com',
                         'Subject': 'Reply to Tess check-in', 'BodyText': 'Are we still on for Thursday, and did the refund land?',
                         'Status': 'open'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                        'DraftText': 'Yes - Thursday still works, and the refund cleared this morning.'})
    return s, {'key': f'review:{rid}', 'kind': 'review', 'lane': 'approve', 'rid': rid, 'mid': mid, 'tid': tid,
               'who': 'Tess', 'channel': 'whatsapp', 'title': 'Reply to Tess check-in'}


class PlainAnswerTests(unittest.TestCase):
    def test_a_plain_answer_always_offers_the_way_on(self):
        """"walk me through my tasks" ended on "Shall we begin with the rejected refund form?" and nothing to tap: the lone
        Next had been dropped as noise (2026-09-24 audit), which left the owner stuck (2026-10-06: "we should never get stuck")."""
        text = remote_assistant.turn_text({'say': 'One reply is waiting on you.', 'chips': [{'label': 'Next', 'verb': 'next'}]}, store=MemoryStore())
        self.assertIn('One reply is waiting on you.', text); self.assertIn('1 · Next', text)

    def test_a_proposal_still_numbers_its_yes_and_no(self):
        text = remote_assistant.turn_text({'say': 'Put it on my list: Friday: renew the domain.', 'proposal': {'id': 'op1'},
                                           'options': ['yes, go ahead', 'no, leave it']}, store=MemoryStore())
        self.assertIn('1 · yes, go ahead', text)


class ShowWhatYouAreApprovingTests(unittest.TestCase):
    def test_the_turn_carries_the_draft_and_what_they_wrote_is_one_number_away(self):
        """The desktop card's grammar (2026-09-23): the draft in the open, what they wrote behind More,
        and the options in the card's order - the verb, Next, More, then the rest."""
        s, item = store_with_a_draft()
        out = {'say': 'Tess is owed a reply - the draft is below.', 'item': item,
               'chips': [{'verb': 'approve', 'label': 'Send the reply'}, {'verb': 'redraft', 'label': 'Redraft it'},
                         {'verb': 'next', 'label': 'Next'}]}
        text = remote_assistant.turn_text(out, store=s)
        self.assertIn('🟤 **You** · reply to', text)
        self.assertIn('the refund cleared this morning', text)          # in full: it is sent in your name
        self.assertLess(text.index('🟤 **You**'), text.index('Reply with one of:'))   # read it, then choose
        self.assertNotIn('THEY WROTE', text)
        # no line explaining the first word (the design, phase A): the phone reads the desk's one decision, and Send says itself
        self.assertNotIn('sends the draft above', text)
        # the draft's own words first, as the screen draws them under the draft (2026-10-06), then Next and More
        self.assertIn('Reply with one of:\n1 · Send the reply\n2 · Redraft it\n3 · Next\n4 · More', text)
        folded = remote_assistant.more_text(s, item)
        self.assertIn('THEY WROTE', folded); self.assertIn('did the refund land?', folded)

    def test_more_sends_what_is_folded_and_offers_the_rest_again(self):
        s, item = store_with_a_draft()
        sent = []
        s.set_setting(f'{remote_assistant.OFFERED_KEY}:whatsapp:{JID}', json.dumps(['Send the reply', 'Next', 'More']), 't')
        with mock.patch.object(remote_assistant, 'send', side_effect=lambda st, ch, chat, text, cid=None: sent.append(text)), \
             mock.patch('taskuary.concierge.restore_current', return_value=item), \
             mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)):
            remote_assistant.respond(s, 'whatsapp', JID, '3', 1)
        self.assertEqual(len(sent), 1)
        self.assertIn('did the refund land?', sent[0])
        self.assertIn('Reply with one of:\n1 · Send the reply\n2 · Next', sent[0])
        self.assertNotIn('· More', sent[0])

    def test_an_item_with_nothing_to_show_says_nothing_extra(self):
        s, _ = store_with_a_draft()
        out = {'say': 'Something landed.', 'item': {'kind': 'fyi', 'lane': 'fyi', 'who': 'Someone'}}
        text = remote_assistant.turn_text(out, store=s)
        self.assertNotIn('THEY WROTE', text)
        self.assertNotIn('YOUR DRAFT', text)

    def test_an_action_proposal_is_never_read_out_as_prose(self):
        """An `action` review keeps the proposal's JSON in DraftText; that is machinery, not a draft."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'Hand-off', 'Kind': 'general', 'Status': 'open'}, 'owner')
        rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending',
                            'DraftText': json.dumps({'op': 'task.create_from_text'})})
        text = remote_assistant.turn_text({'say': 'File it.', 'item': {'kind': 'action', 'lane': 'approve', 'rid': rid}}, store=s)
        self.assertNotIn('YOUR DRAFT', text)
        self.assertNotIn('task.create_from_text', text)


class ANumberIsTheAnswerTests(unittest.TestCase):
    def test_a_pick_says_so_and_free_words_do_not(self):
        s = MemoryStore()
        remote_assistant.remember_offered(s, 'whatsapp', JID, 'Reply with one of:\n1 · Send the reply\n2 · Next')
        self.assertEqual(remote_assistant.resolve_index(s, 'whatsapp', JID, '1'), ('Send the reply', True))
        self.assertEqual(remote_assistant.resolve_index(s, 'whatsapp', JID, 'send it'), ('send it', False))
        self.assertEqual(remote_assistant.resolve_index(s, 'whatsapp', JID, '7'), ('7', False))

    def test_a_picked_action_runs_instead_of_asking_the_same_thing_again(self):
        s, item = store_with_a_draft()
        prop = {'id': 'op1', 'status': 'proposed', 'settles': True, 'label': 'Send the reply'}
        out = {'say': 'Send the reply: Tess.', 'item': item, 'proposal': prop, 'decision': {'verb': 'approve'}}
        from taskuary import concierge
        with mock.patch.object(concierge, 'run_proposal', return_value={'status': 'done'}) as ran, \
             mock.patch.object(concierge, 'receipt', return_value='Done - Send the reply.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'Next up: nothing.', 'item': None}):
            text = remote_assistant.carry_out(s, out, item, picked=True)
        ran.assert_called_once()
        self.assertIn('Done - Send the reply.', text)
        self.assertNotIn('yes, go ahead', text)              # the number WAS the yes

    def test_words_we_only_interpreted_still_wait_for_a_yes(self):
        s, item = store_with_a_draft()
        prop = {'id': 'op1', 'status': 'proposed', 'settles': True, 'label': 'Send the reply'}
        out = {'say': 'Send the reply: Tess.', 'item': item, 'proposal': prop, 'decision': {'verb': 'approve'}}
        from taskuary import concierge
        with mock.patch.object(concierge, 'run_proposal') as ran:
            text = remote_assistant.carry_out(s, out, item, picked=False)
        ran.assert_not_called()
        self.assertIn('yes, go ahead', text)


class HeardYouTests(unittest.TestCase):
    def test_whatsapp_reacts_through_the_bridge(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('whatsapp')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'tok'}, 'test')
        with mock.patch.object(messengers, '_wa', return_value={'ok': True, 'reacted': 1}) as wa:
            self.assertTrue(messengers.react(s, 'whatsapp', JID, 'MSG1'))
        self.assertEqual(wa.call_args[0][1], '/react')
        self.assertEqual(wa.call_args[0][2]['id'], 'MSG1')

    def test_telegram_reacts_through_the_bot_api(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('telegram')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'tok'}, 'test')
        with mock.patch.object(messengers, 'tg', return_value={'ok': True}) as tg:
            self.assertTrue(messengers.react(s, 'telegram', '900100', '55'))
        self.assertEqual(tg.call_args[0][1], 'setMessageReaction')
        self.assertEqual(tg.call_args[1]['message_id'], 55)

    def test_a_reaction_that_fails_never_costs_the_answer(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('whatsapp')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'tok'}, 'test')
        with mock.patch.object(messengers, '_wa', side_effect=RuntimeError('bridge is down')):
            self.assertFalse(messengers.react(s, 'whatsapp', JID, 'MSG1'))


class DoorwayReadsEveryTickTests(unittest.TestCase):
    """The doorway loop ticks every second, but its read went through the chat clock's due-check, so the
    assistant chat was actually read once per poll_seconds - and "next" on the phone waited up to thirty
    seconds for anything to hear it (the owner, 2026-09-20: "hitting next or 3 in whatsapp takes a while")."""
    def test_the_doorway_reads_the_assistant_chat_on_every_tick(self):
        from taskuary import server, channels
        s = server.store
        cid = s.get_connector_by_type('whatsapp')['ConnectorId']
        was = s.get_connector(cid, with_secret=True)
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'tok',
                          'ConfigJson': json.dumps({'poll_seconds': 30, 'assistant_chat': JID})}, 'test')
        # the shared server store: left on, every later test that lists send targets dialled a bridge that isn't there
        self.addCleanup(s.save_connector, {'ConnectorId': cid, 'Active': was.get('Active') or 0, 'Secret': was.get('Secret') or '',
                                           'ConfigJson': was.get('ConfigJson') or '{}'}, 'test')
        reads = []
        ticket = mock.Mock(error=None); ticket.wait.return_value = True
        with mock.patch.object(channels, 'poll_channels', side_effect=lambda *a, **k: reads.append(k.get('only')) or 0), \
             mock.patch.object(server, '_drain_worker', return_value=mock.Mock(submit=mock.Mock(return_value=ticket))):
            server._QUICK_LAST.pop('whatsapp', None)
            server._poll_on_quick_clock(['whatsapp'])                     # the chat clock: due, so it reads
            server._poll_on_quick_clock(['whatsapp'])                     # a moment later: not due for 29 s more
            self.assertEqual(len(reads), 1)
            server._poll_on_quick_clock(['whatsapp'], timer=False)        # the doorway: a conversation, not a mailbox
            self.assertEqual(len(reads), 2)


class AnsweredOnceTests(unittest.TestCase):
    def test_two_readers_of_the_same_message_answer_it_once(self):
        """The fast doorway loop and the connector's own poll both see it (server.doorway_forever)."""
        remote_assistant._ANSWERED.clear()
        self.assertTrue(remote_assistant._claim('whatsapp', 'ABC'))
        self.assertFalse(remote_assistant._claim('whatsapp', 'ABC'))
        self.assertTrue(remote_assistant._claim('telegram', 'ABC'))      # a different chat's id is its own
        self.assertTrue(remote_assistant._claim('whatsapp', None))       # nothing to dedupe on: always answer


class OneMeansOneOnBothScreensTests(unittest.TestCase):
    """The phone numbers its options because a chat has no buttons; the owner, having answered by
    number there, typed "1" on the desktop too - where it was a digit the model interpreted, so it
    answered about something else (the owner, 2026-09-15)."""

    def test_a_bare_number_is_the_action_word_in_that_position(self):
        from taskuary import concierge
        s, item = store_with_a_draft()
        words = [c['label'] for c in concierge.chips_for(s, item)]
        self.assertTrue(words, 'a review item must offer action words for this to mean anything')
        seen = {}
        def brain(system, user, **kw):
            seen['user'] = user
            return 'Right you are.'
        with mock.patch.object(concierge, '_brain_for', return_value=brain),              mock.patch.object(concierge, 'chips_for', wraps=concierge.chips_for):
            concierge.say(s, '1', item=item)
        self.assertIn(words[0], seen['user'], 'the model should have been handed the action, not the digit')

    def test_a_number_nobody_offered_stays_the_owners_own_words(self):
        from taskuary import concierge
        s, item = store_with_a_draft()
        seen = {}
        def brain(system, user, **kw):
            seen['user'] = user
            return 'Right you are.'
        with mock.patch.object(concierge, '_brain_for', return_value=brain):
            concierge.say(s, '97', item=item)
        self.assertIn('97', seen['user'])


def asking_agent(question='Which branch should I build from?', choices=('main', 'dev')):
    return {'key': 'agent:7', 'kind': 'agent', 'lane': 'blocked', 'tid': 7, 'ref': 'TQ-0007',
            'title': 'Ship the release', 'agent': 'codex', 'asking': True,
            'tail': [question], 'choices': list(choices), 'request_id': 'r7', 'request_kind': 'input_needed'}


class AnAgentsQuestionComesBackAnsweredTests(unittest.TestCase):
    """An agent blocked on a question reaches the phone, and what the owner picks has to reach the RUN -
    as the agent's own words. Numbered, the chip "Answer it" carries no text at all, and concierge
    sends an empty answer_agent to a blocked agent as the literal word "yes" (measured 2026-09-15)."""

    def test_the_question_and_its_answers_are_both_in_the_message(self):
        s = MemoryStore()
        item = asking_agent()
        text = remote_assistant.turn_text({'say': 'codex asked you something.', 'item': item,
                                           'chips': [{'verb': 'answer_agent', 'label': 'Answer it'},
                                                     {'verb': 'next', 'label': 'Next'}]}, store=s)
        self.assertIn('🟤 **You** · answer the agent', text)
        self.assertIn('Which branch should I build from?', text)
        self.assertIn('1 · main', text)                      # the agent's own answers, numbered first
        self.assertIn('2 · dev', text)
        self.assertIn('Answer it', text)                     # the chips still follow

    def test_a_picked_answer_goes_to_the_run_verbatim(self):
        from taskuary import workerstate as ws
        s = MemoryStore()
        with mock.patch.object(ws, 'answer_open', return_value={'delivered': True, 'state': 'delivered'}) as sent:
            said = remote_assistant.answer_the_agent(s, asking_agent(), 'dev', picked=True)
        sent.assert_called_once()
        self.assertEqual(sent.call_args[0][2], 'dev', 'the agent must hear its own word, never "yes"')
        self.assertIn('Told codex: "dev"', said)

    def test_words_that_are_not_one_of_its_answers_take_the_ordinary_walk(self):
        s = MemoryStore()
        self.assertEqual(remote_assistant.answer_the_agent(s, asking_agent(), 'stop it', picked=True), '')
        # ...words typed to an agent that is NOT asking are the assistant's
        self.assertEqual(remote_assistant.answer_the_agent(s, {**asking_agent(), 'asking': False}, 'main', picked=False), '')

    def test_typed_words_to_an_asking_agent_are_the_ais_to_read_and_an_answer_still_goes_straight_in(self):
        # 2026-10-08: typed words go to the AI, as on the desktop ("ai should match to pill action") - typed "next" was sent to
        # the agent as its answer. What the AI matches to the Answer pill runs at once (AUTO), so an answer still goes straight in
        # (2026-10-02: "if agent asks you a question in whatsapp and you respond it should go directly to the agent")
        from taskuary import concierge, workerstate as ws
        s = MemoryStore()
        with mock.patch.object(ws, 'answer_open') as sent:
            for words in ('use the staging branch', 'next'):
                self.assertEqual(remote_assistant.answer_the_agent(s, asking_agent(), words, picked=False), '')
        sent.assert_not_called()
        self.assertIn('answer_agent', concierge.AUTO)
        self.assertNotIn('answer_agent', concierge.AGENT_STARTS)

    def test_answer_it_with_no_words_asks_instead_of_saying_yes(self):
        s = MemoryStore()
        item = asking_agent(choices=())
        out = {'say': 'codex asked you something.', 'item': item, 'decision': {'verb': 'answer_agent', 'text': ''},
               'proposal': {'id': 'op9', 'status': 'proposed', 'settles': True}}
        from taskuary import concierge
        with mock.patch.object(concierge, 'run_proposal') as ran:
            text = remote_assistant.carry_out(s, out, item, picked=True)
        ran.assert_not_called()
        self.assertIn('What should I tell codex?', text)

    def test_a_run_that_stopped_waiting_says_so_instead_of_swallowing_it(self):
        from taskuary import workerstate as ws
        s = MemoryStore()
        from taskuary import waitroom
        with mock.patch.object(ws, 'answer_open', return_value={'delivered': False, 'state': 'no_request'}),              mock.patch.object(waitroom, 'add') as saved:
            said = remote_assistant.answer_the_agent(s, asking_agent(), 'main', picked=True)
        # A12: the answer is kept for the agent, as the desktop keeps it - never just reported as lost
        saved.assert_called_once()
        self.assertEqual(saved.call_args[0][2], 'main')
        self.assertIn('is saved and reaches it when it next stops', said)


if __name__ == '__main__':
    unittest.main()


class FyiGroupOnAPhoneTests(unittest.TestCase):
    """Four things nobody has to do, on a screen with no buttons.

    The desktop card carries its own "All read, next" button, so concierge.CHIPS leaves `next` off a
    batch on purpose. A chat has no buttons: the phone printed four numbered lines, said nothing about
    what a number was for, and offered no way past them (the owner, 2026-09-22: "fyi groups should say
    hit number to see full message ... and next to go to next group").
    """

    ITEM = {'kind': 'fyis', 'key': 'fyis:a,b',
            'items': [{'key': 'msg:1', 'channel': 'email', 'who': 'noreply@vendor.example', 'title': 'File - SUCCESS!'},
                      {'key': 'msg:2', 'channel': 'email', 'who': 'bank@vendor.example', 'title': 'Balance Reporting'}]}

    def turn(self, chips=()):
        from taskuary import concierge
        return remote_assistant.turn_text({'item': self.ITEM, 'say': '2 things people told you',
                                           'chips': [{'label': concierge.CHIP_WORDS[v]} for v in chips]})

    def test_a_number_is_told_what_it_does(self):
        text = self.turn(('not_ours_sender',))
        self.assertIn('Reply with a number to read that message in full', text)
        self.assertIn('1 · ', text); self.assertIn('2 · ', text)

    def test_the_way_on_is_offered_even_though_the_card_keeps_it_in_a_button(self):
        from taskuary import concierge
        self.assertNotIn('next', concierge.CHIPS['fyis'], 'the desktop card still keeps its own button')
        text = self.turn(('not_ours_sender', 'block_sender'))
        self.assertIn('1 · Got it', text, 'an FYI is passed with Got it (A8), and the batch leads with it (2026-10-22)')
        self.assertIn('4 · Ignore this sender', text); self.assertEqual(text.count('Got it'), 1)

    def test_it_is_offered_even_when_the_walk_sends_no_chips(self):
        text = self.turn(())
        self.assertIn('1 · Got it\n2 · ', text)

    def test_an_ordinary_card_still_says_open_one(self):
        text = remote_assistant.turn_text({'item': {'kind': 'report', 'key': 'report:1'},
                                           'say': 'Process Error Check landed', 'chips': [{'label': 'Run it again'}]})
        self.assertNotIn('read that message in full', text)
        self.assertIn('Reply with one of:', text)


class TheWalkOpensWithWhoWantsWhatTests(unittest.TestCase):
    """The phone opens the day with THE RAIL (the owner, 2026-10-02: "it should just read from the rail no?"): its bands,
    in its order, under its names - funnel.level_of, the server's mirror of funnelPile.levelOf."""

    def test_the_rails_bands_and_the_lead(self):
        items = [{'key': 'a', 'lane': 'approve', 'kind': 'review', 'who': 'Erin Blake', 'title': 'Q3 numbers', 'order_band': 2},
                 {'key': 'c', 'lane': 'working', 'kind': 'agent', 'agent': 'coding', 'title': 'Reconcile the GL', 'order_band': 2},
                 {'key': 'd', 'lane': 'report', 'kind': 'report', 'who': 'Spend report', 'title': 'Spend report - 3 over', 'order_band': 3},
                 {'key': 'f', 'lane': 'fyi', 'kind': 'fyi', 'who': 'Omar Keller', 'title': 'Portal is back', 'order_band': 4}]
        text = remote_assistant.who_wants_what(items)
        # every open task under Tasks, the one an agent is working included (the owner, 2026-10-21)
        self.assertTrue(text.startswith('4 things: 2 tasks, 1 report, 1 FYI.'), text)
        # a drafted reply says its lane's word, as the desktop row does (funnel_presentation.state_of) - not "draft ready"
        self.assertIn('TASKS · 2\n· Erin Blake - Q3 numbers (ready to send)', text)
        self.assertNotIn('AGENTS WORKING', text); self.assertIn('· Report - Spend report - 3 over', text)
        self.assertLess(text.index('TASKS'), text.index('REPORTS ·')); self.assertLess(text.index('REPORTS ·'), text.index('FYI ·'))
        self.assertEqual(remote_assistant.who_wants_what([]), 'Nothing is waiting on you.')

    def test_a_finished_agents_task_is_on_you_as_on_the_rail(self):
        # the owner's screenshot, 2026-10-02: the rail had it On you, the opener said "Agents waiting" - no agent was working
        done = {'key': 'agentdone:9', 'lane': 'report', 'kind': 'agentdone', 'agent': 'coding', 'title': 'Investigate the export'}
        self.assertEqual(remote_assistant.group_of(done), 'task')
        self.assertIn('TASKS · 1', remote_assistant.who_wants_what([done]))

    def test_what_you_passed_stays_in_tasks_and_remind_me_is_for_later_as_on_the_rail(self):
        # Next moves on and the task stays under Tasks; Remind me puts it in For later (the owner, 2026-10-21)
        items = [{'key': 'a', 'lane': 'stopped', 'kind': 'agent', 'who': 'Erin Blake', 'title': 'Budget tab', 'surfaced': True, 'put_down': True, 'order_band': 2},
                 {'key': 'b', 'lane': 'asked', 'kind': 'asked', 'who': 'Gail Moreno', 'title': 'Q3 numbers', 'order_band': 2}]
        text = remote_assistant.who_wants_what(items)
        self.assertTrue(text.startswith('2 things: 2 tasks.'), text)
        items[0] = items[0] | {'put_down': False, 'surfaced': False, 'deferred': True}
        text = remote_assistant.who_wants_what(items)
        self.assertTrue(text.startswith('2 things: 1 task, 1 for later.'), text)

    def test_it_names_the_bands_exactly_as_the_rail_does(self):
        # both sides read lanes.json's `sections`: the page's lanes.js builds LEVEL_ORDER and SECTION_WORDS from it, as this does
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        secs = json.loads((root / 'taskuary' / 'lanes.json').read_text(encoding='utf-8'))['sections']
        self.assertEqual(remote_assistant.groups(), [(s['key'], s['word']) for s in secs])
        js = (root / 'website' / 'src' / 'lanes.js').read_text(encoding='utf-8')
        self.assertIn('export const LEVEL_ORDER = SECTIONS.map', js); self.assertIn('export const SECTION_WORDS = Object.fromEntries(SECTIONS', js)


class TheVerbDoesTheThingTests(unittest.TestCase):
    def test_a_reply_with_no_draft_leads_with_drafting_it_not_closing(self):
        out = {'say': 'Sam is owed a reply.', 'item': {'kind': 'review', 'lane': 'approve'},
               'chips': [{'verb': 'close', 'label': 'Close without sending'}, {'verb': 'redraft', 'label': 'Redraft it'},
                         {'verb': 'not_ours', 'label': 'Not ours'}, {'verb': 'next', 'label': 'Next'}]}
        text = remote_assistant.turn_text(out, store=MemoryStore())
        self.assertIn('Reply with one of:\n1 · Redraft it\n2 · Next\n3 · Close without sending\n4 · Not ours', text)


class NoHintUnderAnAnswerTests(unittest.TestCase):
    """F12: the model's "Yes to what?" came with "Reply: writes a draft for you to approve here" under it, about nothing on
    screen; and typed next printed "Next." above the card it brought up."""

    def test_a_model_answer_has_no_then_line(self):
        from taskuary import concierge
        table = {'key': 'msg:3', 'kind': 'asked', 'mid': 3, 'title': 'Thursday'}
        chips = [{'verb': 'reply', 'label': 'Reply'}, {'verb': 'next', 'label': 'Next'}]
        with mock.patch.object(concierge, 'chips_for', return_value=chips):
            text = remote_assistant.carry_out(MemoryStore(), {'say': 'Yes to what?', 'chips': chips, 'decision': None}, table)
        self.assertIn('Yes to what?', text)
        self.assertNotIn('Reply: writes a draft', text)

    def test_typed_next_shows_the_card_without_echoing_next(self):
        from taskuary import concierge
        table = {'key': 'msg:3', 'kind': 'fyi', 'mid': 3, 'title': 'Thursday'}
        with mock.patch.object(concierge, 'surface', return_value={'say': 'Ray Colton sent the budget.', 'item': None}):
            text = remote_assistant.carry_out(MemoryStore(), {'say': concierge.RECEIPTS['next'], 'chips': [], 'decision': {'verb': 'next'}}, table)
        self.assertIn('Ray Colton sent the budget.', text)
        self.assertFalse(text.startswith('Next.'), text)


class LongMailTests(unittest.TestCase):
    """F17: an 8-paragraph mail - its card led with "Hi Alex," as the summary, and More sent the body as one wall cut wherever the
    chat's limit fell, the cut-off half of a quote going on as plain text."""
    PARA = ('The vendor sent the revised schedule for the Lakeview move, and it changes three of the dates we agreed with the '
            'facilities team last month, so I have gone through each one and noted what it means for us. ') * 2

    def setUp(self):
        self.s = MemoryStore()
        self.t = self.s.create_task({'Title': 'Revised move schedule', 'Kind': 'reply', 'Status': 'open',
                                     'Summary': 'Hi Alex, 1. Gail Moreno wants you to confirm the revised move dates. She needs it by Friday.'}, 'o')
        body = 'Hi Alex,\n\n' + '\n\n'.join(f'{n}. {self.PARA}' for n in range(1, 9)) + '\n\nThanks,\nGail'
        self.mid = self.s.add_message({'TaskId': self.t, 'Channel': 'email', 'Subject': 'Revised move schedule', 'FromName': 'Gail Moreno',
                                       'FromEmail': 'gail@northwind.example', 'BodyText': body, 'Status': 'open'})
        self.item = {'key': f'task:{self.t}', 'kind': 'asked', 'lane': 'asked', 'tid': self.t, 'mid': self.mid, 'who': 'Gail Moreno',
                     'channel': 'email', 'title': 'Revised move schedule'}

    def test_the_summary_line_is_a_sentence_not_a_salutation(self):
        story = remote_assistant.story_block(self.s, self.item)
        self.assertEqual(story.splitlines()[2], 'Gail Moreno wants you to confirm the revised move dates.', story)
        self.assertFalse([l for l in story.splitlines() if l.startswith(('Hi Alex', '1.'))], story)

    def test_more_pages_the_body_at_paragraphs(self):
        from taskuary import chatformat
        got = []
        with mock.patch.object(messengers, 'tg_send', side_effect=lambda st, chat, body, connector_id=None, buttons=None: got.append(body)):
            remote_assistant.send(self.s, 'telegram', '900100', remote_assistant.more_text(self.s, self.item), None)
        self.assertGreater(len(got), 2)
        self.assertTrue(all(len(b) <= 1300 for b in got), [len(b) for b in got])
        body = [b.split('Taskuary:\n', 1)[-1] for b in got]
        self.assertTrue(all(l.startswith('>') for b in body[1:] for l in b.splitlines() if l.strip()), body[1][:200])
        self.assertEqual([sum(b.count(f'{n}. The vendor') for b in got) for n in range(1, 9)], [1] * 8, 'each paragraph once')

    def test_a_quote_cut_mid_line_stays_a_quote(self):
        from taskuary import chatformat
        parts = chatformat.split('> ' + 'word ' * 400, 500)
        self.assertTrue(all(p.startswith('>') for p in parts), [p[:10] for p in parts])


class TypedActsMoveOnTests(unittest.TestCase):
    """F19: a Remind me typed (or said) and confirmed said "Away until ..." and sat on the card it had put away - the next "mark this
    done" closed the reminded task. The poll's Remind me moves on; the typed one now does too. Every acting reply has a way on."""

    def test_a_typed_remind_and_its_yes_walk_on_to_the_next_card(self):
        from taskuary import concierge
        s = MemoryStore()
        table = {'key': 'task:5', 'kind': 'task', 'tid': 5, 'ref': 'TQ-0005', 'title': 'Renew the domain'}
        nxt = {'say': 'Gail Moreno asked about Thursday.', 'item': {'key': 'task:6', 'kind': 'task', 'tid': 6, 'ref': 'TQ-0006', 'title': 'Thursday'},
               'chips': [{'verb': 'close', 'label': 'Mark done'}, {'verb': 'next', 'label': 'Next'}]}
        prop = {'id': 'op1', 'status': 'proposed', 'kind': 'task.defer', 'target': 5, 'params': {'until': 'tomorrow'}, 'label': 'Remind me'}
        got = []
        with mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'done', 'outcome': {'when': 'Thu 22 Oct'}}), \
             mock.patch.object(concierge, 'receipt', return_value='TQ-0005 is away until Thu 22 Oct.'), \
             mock.patch.object(concierge, 'surface', return_value=nxt) as surfaced, \
             mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: got.append((body, poll))):
            text = remote_assistant.carry_out(s, {'say': 'Remind you about TQ-0005 tomorrow?', 'proposal': prop, 'decision': None}, table, picked=True)
            remote_assistant.send(s, 'whatsapp', JID, text, None)
        surfaced.assert_called_once()
        self.assertIn('TQ-0005 is away until Thu 22 Oct.', got[0][0])
        self.assertIn('Mark done', got[-1][1])
        self.assertEqual(remote_assistant.acts_for(s, 'whatsapp', JID)['Mark done']['key'], 'task:6', 'Mark done is the next card, not the reminded one')

    def test_bring_it_back_keeps_the_cards_choices(self):
        from taskuary import concierge, remind
        s = MemoryStore()
        table = {'key': 'task:6', 'kind': 'task', 'tid': 6, 'ref': 'TQ-0006', 'title': 'Thursday'}
        with mock.patch.object(remind, 'set_reminder', return_value={'remindAt': None}), \
             mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
             mock.patch.object(concierge, 'restore_current', return_value=table), \
             mock.patch.object(concierge, 'chips_for', return_value=[{'verb': 'close', 'label': 'Mark done'}, {'verb': 'next', 'label': 'Next'}]):
            text = remote_assistant.run_act(s, {'t': 'remind', 'tid': 5, 'until': 'none'}, table)
        self.assertIn('It is back on your rail now.', text)
        self.assertIn('· Mark done', text); self.assertIn('· Next', text)

    def test_an_older_list_answer_brings_the_current_choices(self):
        s, got = MemoryStore(), []
        remote_assistant._offer([('Mark done', {'t': 'stay'}), ('Next', {'t': 'next'})])
        remote_assistant.remember_offered(s, 'whatsapp', JID, 'Reply with one of:\n1 · Mark done\n2 · Next')
        with mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: got.append((body, poll))):
            remote_assistant.stale_tap(s, 'whatsapp', JID)
        self.assertIn('older list', got[-1][0])
        self.assertEqual(got[-1][1], ['Mark done', 'Next'])


class MarkDoneOnAnUnsentDraftTests(unittest.TestCase):
    """F24: Mark done on a card whose reply was still waiting for its yes said "TQ-0001 closed." - the draft was dropped unsent."""
    def test_the_receipt_says_the_reply_was_not_sent(self):
        from taskuary import concierge, server
        s, item = store_with_a_draft()
        with mock.patch.object(server, 'store', s):
            out = server._run_kind({'kind': 'task.complete', 'target': item['tid'], 'params': {}}, None)
        self.assertTrue(out.get('unsent'))
        with concierge.delivering(concierge.PHONE):
            said = concierge.receipt_turn(s, {'kind': 'task.complete', 'targetKind': 'task', 'target': item['tid'], 'status': 'done', 'outcome': out})['say']
        self.assertEqual(said, f"TQ-{item['tid']:04d} closed - the reply was not sent.")

    def test_a_close_with_nothing_drafted_is_just_closed(self):
        from taskuary import concierge, server
        s = MemoryStore(); t = s.create_task({'Title': 'Renew the domain', 'Kind': 'task', 'Status': 'open'}, 'owner')
        with mock.patch.object(server, 'store', s):
            out = server._run_kind({'kind': 'task.complete', 'target': t, 'params': {}}, None)
        with concierge.delivering(concierge.PHONE):
            said = concierge.receipt_turn(s, {'kind': 'task.complete', 'targetKind': 'task', 'target': t, 'status': 'done', 'outcome': out})['say']
        self.assertEqual(said, f'TQ-{t:04d} closed.')


class EndOfWalkAndFyiCountTests(unittest.TestCase):
    """F26: the walk's end named six tasks and offered Open for three; the FYI batch said "4 fyi" over a rail of fourteen; two lines
    alike were told apart by "(2)"."""

    def test_the_end_of_the_walk_offers_an_open_for_every_named_task_on_the_phone(self):
        from taskuary import concierge, funnel, terminal
        from tests.test_funnel import mail, store
        s = store()
        for n, who in enumerate(('Gail Moreno', 'Ray Colton', 'Paula Vance', 'Erin Blake', 'Omar Keller', 'Marcus Reed')):
            t = s.create_task({'Title': f'Question {n} from {who}', 'Kind': 'reply', 'Status': 'open'}, 'o')
            mail(s, f'Question {n}', who=who, email=f'p{n}@northwind.example', tid=t, hours=n + 1)
        with mock.patch.object(terminal, 'live_sessions', return_value=[]), concierge.delivering(concierge.PHONE):
            out, here = concierge.surface(s, llm=lambda *a, **k: 'never'), None
            for _ in range(10):
                if not out.get('item'): break
                here = out['item']['key']
                out = concierge.surface(s, llm=lambda *a, **k: 'never', leaving=here, exclude=here)
        self.assertIn("That's everything for now", out['say'])
        opens = [c for c in out.get('chips') or [] if c.get('verb') == 'open']
        self.assertGreater(len(opens), 3, out.get('chips'))

    def test_the_batch_says_how_many_of_how_many(self):
        items = [{'key': f'msg:{n}', 'kind': 'fyi', 'who': f'Sender {n}', 'title': f'Note {n}'} for n in range(4)]
        batch = {'key': 'fyis:' + ','.join(i['key'] for i in items), 'kind': 'fyis', 'lane': 'fyi', 'items': items}
        pile = {'items': [{'key': f'msg:{n}', 'kind': 'fyi', 'lane': 'fyi', 'order_band': 4} for n in range(4, 14)]}
        with mock.patch('taskuary.funnel.pile', return_value=pile):
            text = remote_assistant.turn_text({'say': 'x', 'item': batch}, store=MemoryStore())
        self.assertIn('4 of 14 fyi · nothing to do', text)

    def test_lines_alike_are_told_apart_by_who_sent_them(self):
        items = [{'key': 'msg:1', 'kind': 'fyi', 'who': 'Payworth', 'title': 'Statement ready', 'email': 'billing@payworth.example'},
                 {'key': 'msg:2', 'kind': 'fyi', 'who': 'Payworth', 'title': 'Statement ready', 'email': 'payroll@payworth.example'}]
        lines = [l for _k, l in remote_assistant.member_lines({'kind': 'fyis', 'items': items})]
        self.assertEqual(len(set(lines)), 2)
        self.assertFalse(any(l.endswith('(2)') for l in lines), lines)
        self.assertTrue(lines[1].endswith('(payroll@payworth.example)'), lines)


class ReceiptSaidOnceTests(unittest.TestCase):
    """F13: the bubble that reported Done still said "Nothing happens until you say yes."; an act run at once was said twice, its
    card line ("Answer it - general - ...") above its receipt; a bare "Ok." sat over "Not done"; Remind me said where, not what."""

    def test_the_yes_bubble_does_not_ask_for_the_yes(self):
        from taskuary import concierge
        prop = {'id': 'op1', 'status': 'proposed', 'settles': False, 'label': 'Send the reply'}
        out = {'say': f'Send the reply to Gail Moreno. {concierge.WAITS}', 'proposal': prop, 'decision': {'verb': 'approve'}}
        with mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'done'}), \
             mock.patch.object(concierge, 'receipt', return_value='Sent to Gail Moreno · TQ-0001.'):
            text = remote_assistant.carry_out(MemoryStore(), out, None, picked=True)
        self.assertIn('Sent to Gail Moreno · TQ-0001.', text)
        self.assertNotIn(concierge.WAITS, text)

    def test_an_act_run_at_once_is_said_once(self):
        from taskuary import concierge
        prop = {'id': 'op2', 'status': 'proposed', 'auto': True, 'settles': False, 'say': 'Answer it - general - Thursday.', 'say_card': ''}
        with mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'done'}), \
             mock.patch.object(concierge, 'receipt', return_value='Done - Answer it · TQ-0001.'):
            text = remote_assistant.carry_out(MemoryStore(), {'say': prop['say'], 'proposal': prop}, None)
        self.assertNotIn('Answer it - general', text)
        self.assertIn('Done - Answer it · TQ-0001.', text)

    def test_no_bare_ok_over_an_act_that_did_not_happen(self):
        from taskuary import concierge
        prop = {'id': 'op3', 'status': 'proposed', 'settles': False, 'label': 'Mark done'}
        with mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'error', 'error': 'it is locked'}), \
             mock.patch.object(concierge, 'receipt_turn', return_value={'say': 'Not done - it is locked. TQ-0001 is where it was.', 'chips': []}):
            text = remote_assistant.carry_out(MemoryStore(), {'say': 'Ok.', 'proposal': prop, 'decision': {'verb': 'close'}}, None, picked=True)
        self.assertFalse(text.startswith('Ok.'), text)
        self.assertIn('Not done - it is locked.', text)

    def test_remind_me_says_the_task_is_away_until_the_day(self):
        from taskuary import concierge, remind
        s = MemoryStore(); t = s.create_task({'Title': 'Renew the domain', 'Kind': 'task', 'Status': 'open'}, 'owner')
        with mock.patch.object(remind, 'set_reminder', return_value={'remindAt': '2026-10-22 07:00:00', 'when': 'Thu 22 Oct'}), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'Nothing else is waiting.', 'item': None}), \
             mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
             mock.patch.object(concierge, 'restore_current', return_value=None):
            text = remote_assistant.run_act(s, {'t': 'remind', 'tid': t, 'until': 'tomorrow'}, None)
        self.assertIn(f'TQ-{t:04d} is away until Thu 22 Oct.', text)


class WalkOffTheOpenerTests(unittest.TestCase):
    """F9: "Walk me through my tasks" tapped under the day's opener printed the whole opener again above the first card."""

    def test_the_tap_under_the_opener_goes_straight_to_the_first_card(self):
        from datetime import datetime
        from taskuary import concierge
        s = MemoryStore(); s.set_setting('phone_morning_line', '1', 't')
        sent = []
        doors = [{'channel': 'whatsapp', 'chat': JID, 'connectorId': 7, 'label': 'WhatsApp', 'name': 'WhatsApp'}]
        card = {'say': 'Gail Moreno asked about Thursday.', 'item': None, 'chips': [{'verb': 'next', 'label': 'Next'}]}
        with mock.patch.object(remote_assistant, 'doorways', return_value=doors), \
             mock.patch.object(remote_assistant, 'greeting', return_value='Good evening.'), \
             mock.patch.object(remote_assistant, 'send', side_effect=lambda st, ch, chat, text, cid=None, **k: (remote_assistant.remember_offered(st, ch, chat, text), sent.append(text))), \
             mock.patch('taskuary.funnel.pile', return_value={'items': [{'key': 'msg:1', 'lane': 'approve', 'title': 'Thursday'}]}), \
             mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
             mock.patch.object(concierge, 'restore_current', return_value=None), \
             mock.patch.object(concierge, 'resume', return_value=card), \
             mock.patch.object(concierge, 'say', side_effect=AssertionError('a pick never reaches the model')),              mock.patch.object(remote_assistant, 'quiet', return_value=True),              mock.patch.object(remote_assistant, 'handoff', return_value=None):
            # quiet/handoff read state other tests in this process leave for the same chat (0 sent on Windows CI, 2026-10-22)
            self.assertEqual(remote_assistant.morning_line(s, now=datetime(2026, 10, 21, 20, 0)), 1)
            self.assertIn('Good evening', sent[-1])
            remote_assistant.respond(s, 'whatsapp', JID, 'Walk me through my tasks', 7, poll=True)
        self.assertNotIn('Good evening', sent[-1])
        self.assertIn('Gail Moreno asked about Thursday.', sent[-1])

    def test_the_walk_picked_anywhere_else_still_opens_with_the_summary(self):
        from taskuary import concierge
        with mock.patch.object(remote_assistant, 'greeting', return_value='Good evening.'), \
             mock.patch('taskuary.funnel.pile', return_value={'items': []}), \
             mock.patch.object(concierge, 'resume', return_value={'say': 'Nothing is waiting.', 'item': None}):
            self.assertIn('Good evening', remote_assistant.run_act(MemoryStore(), {'t': 'walk'}, None))

    def test_a_typed_walk_starts_at_the_card_on_the_table(self):
        from taskuary import concierge
        table = {'key': 'msg:3', 'kind': 'fyi', 'mid': 3, 'title': 'The Thursday plan'}
        prop = {'id': 'op1', 'status': 'proposed', 'auto': True, 'kind': 'script.start', 'params': {'name': 'walk me through my tasks'}}
        with mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'done', 'outcome': {'script': 'walk me through my tasks'}}), \
             mock.patch.object(concierge, 'receipt', return_value='Done - Start a script. Starting: walk me through my tasks.'), \
             mock.patch('taskuary.funnel.pile', return_value={'items': []}), \
             mock.patch.object(concierge, 'resume', return_value={'say': 'The Thursday plan.', 'item': None}) as resumed, \
             mock.patch.object(concierge, 'surface', side_effect=AssertionError('the walk starts at the table, it does not skip it')):
            text = remote_assistant.carry_out(MemoryStore(), {'say': 'Starting.', 'proposal': prop}, table)
        resumed.assert_called_once()
        self.assertIn('The Thursday plan.', text)
        self.assertNotIn('Done - Start a script', text)


def canonical_world():
    """Two tasks with mail, on a rail that reads canonical processing membership (the shipped default)."""
    from taskuary import funnel, processing_unread
    from tests.test_funnel import ago, mail, store
    s = store()
    t = s.create_task({'Title': 'Confirm Thursday with Gail', 'Kind': 'reply', 'Status': 'open'}, 'o')
    mid = mail(s, 'Can you confirm Thursday?', who='Gail Moreno', email='gail@northwind.example', body='Are we on for Thursday?', tid=t)
    t2 = s.create_task({'Title': 'Budget numbers', 'Kind': 'reply', 'Status': 'open'}, 'o')
    mail(s, 'Budget numbers', who='Ray Colton', email='ray@northwind.example', body='Numbers?', tid=t2, hours=1)
    s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        processing_unread.build(s, live_state=[])
    s.activate_processing_reads(fixed_now=ago(0), live_state=[]); funnel.invalidate()
    return s, t, mid


class ReplyWritesTheDraftAndShowsItTests(unittest.TestCase):
    """F4: Reply on a task with no draft wrote one, then looked it up by its review key before membership had caught up - and
    answered "I can't find that one" over the draft it had just written."""

    def test_reply_on_a_plain_task_leads_to_its_ready_to_send_card(self):
        s, t, mid = canonical_world()
        def draft(store, item, verb, instruction):
            return s.add_review({'TaskId': t, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Yes - Thursday at 2 works.'})
        item = {'key': f'task:{t}', 'kind': 'asked', 'tid': t, 'mid': mid, 'title': 'Confirm Thursday with Gail'}
        with mock.patch.object(remote_assistant, '_draft', side_effect=draft), \
             mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            text = remote_assistant.run_act(s, {'t': 'verb', 'verb': 'reply', 'key': f'task:{t}'}, item)
        self.assertNotIn("can't find", text)
        self.assertIn('Yes - Thursday at 2 works.', text)
        self.assertIn('ready to send', text)
