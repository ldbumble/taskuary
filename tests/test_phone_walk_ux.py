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
        self.assertIn('Send the reply: sends the draft above, in your name.', text)
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
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'tok',
                          'ConfigJson': json.dumps({'poll_seconds': 30, 'assistant_chat': JID})}, 'test')
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

    def test_typed_words_to_an_asking_agent_go_straight_to_it(self):
        # the owner, 2026-10-02: "if agent asks you a question in whatsapp and you respond it should go directly to the agent"
        from taskuary import workerstate as ws
        s = MemoryStore()
        with mock.patch.object(ws, 'answer_open', return_value={'delivered': True, 'state': 'delivered'}) as sent:
            said = remote_assistant.answer_the_agent(s, asking_agent(), 'use the staging branch', picked=False)
        self.assertEqual(sent.call_args[0][2], 'use the staging branch')
        self.assertIn('Told codex: "use the staging branch"', said)

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
        self.assertIn('5 · Next', text, 'after the two members and the two sender rules')

    def test_it_is_offered_even_when_the_walk_sends_no_chips(self):
        text = self.turn(())
        self.assertIn('3 · Next', text)
        self.assertIn('read that message in full', text)

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
                 {'key': 'c', 'lane': 'working', 'kind': 'agent', 'agent': 'coder', 'title': 'Reconcile the GL', 'order_band': 5},
                 {'key': 'd', 'lane': 'report', 'kind': 'report', 'who': 'Spend report', 'title': 'Spend report - 3 over', 'order_band': 3},
                 {'key': 'f', 'lane': 'fyi', 'kind': 'fyi', 'who': 'Omar Keller', 'title': 'Portal is back', 'order_band': 4}]
        text = remote_assistant.who_wants_what(items)
        self.assertTrue(text.startswith('4 things: 1 on you, 1 agents working, 1 reports, 1 FYI.'), text)
        self.assertIn('ON YOU · 1\n· Erin Blake - Q3 numbers (draft ready)', text)
        self.assertIn('AGENTS WORKING · 1', text); self.assertIn('· Report - Spend report - 3 over', text)
        self.assertLess(text.index('ON YOU'), text.index('AGENTS WORKING')); self.assertLess(text.index('REPORTS ·'), text.index('FYI ·'))
        self.assertEqual(remote_assistant.who_wants_what([]), 'Nothing is waiting on you.')

    def test_a_finished_agents_task_is_on_you_as_on_the_rail(self):
        # the owner's screenshot, 2026-10-02: the rail had it On you, the opener said "Agents waiting" - no agent was working
        done = {'key': 'agentdone:9', 'lane': 'report', 'kind': 'agentdone', 'agent': 'coder', 'title': 'Investigate the export'}
        self.assertEqual(remote_assistant.group_of(done), 'task')
        self.assertIn('ON YOU · 1', remote_assistant.who_wants_what([done]))

    def test_what_you_passed_is_for_later_as_on_the_rail(self):
        items = [{'key': 'a', 'lane': 'stopped', 'kind': 'agent', 'who': 'Erin Blake', 'title': 'Budget tab', 'surfaced': True, 'order_band': 2},
                 {'key': 'b', 'lane': 'asked', 'kind': 'asked', 'who': 'Gail Moreno', 'title': 'Q3 numbers', 'order_band': 2}]
        text = remote_assistant.who_wants_what(items)
        self.assertTrue(text.startswith('2 things: 1 on you, 1 for later.'), text)

    def test_it_names_the_bands_exactly_as_the_rail_does(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1] / 'website' / 'src' / 'funnelPile.js').read_text(encoding='utf-8')
        self.assertIn('export const LEVEL_ORDER = [' + ', '.join(f'"{k}"' for k in remote_assistant.LEVEL_ORDER) + '];', js)
        for k, word in remote_assistant.groups(): self.assertIn(f'{k}: "{word}"', js)


class TheVerbDoesTheThingTests(unittest.TestCase):
    def test_a_reply_with_no_draft_leads_with_drafting_it_not_closing(self):
        out = {'say': 'Sam is owed a reply.', 'item': {'kind': 'review', 'lane': 'approve'},
               'chips': [{'verb': 'close', 'label': 'Close without sending'}, {'verb': 'redraft', 'label': 'Redraft it'},
                         {'verb': 'not_ours', 'label': 'Not ours'}, {'verb': 'next', 'label': 'Next'}]}
        text = remote_assistant.turn_text(out, store=MemoryStore())
        self.assertIn('Reply with one of:\n1 · Redraft it\n2 · Next\n3 · Close without sending\n4 · Not ours', text)
