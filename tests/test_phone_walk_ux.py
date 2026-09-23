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


class ShowWhatYouAreApprovingTests(unittest.TestCase):
    def test_the_turn_carries_the_draft_and_what_they_wrote_is_one_number_away(self):
        """The desktop card's grammar (2026-09-23): the draft in the open, what they wrote behind More,
        and the options in the card's order - the verb, Next, More, then the rest."""
        s, item = store_with_a_draft()
        out = {'say': 'Tess is owed a reply - the draft is below.', 'item': item,
               'chips': [{'verb': 'approve', 'label': 'Send the reply'}, {'verb': 'redraft', 'label': 'Redraft it'},
                         {'verb': 'next', 'label': 'Next'}]}
        text = remote_assistant.turn_text(out, store=s)
        self.assertIn('YOUR DRAFT', text)
        self.assertIn('the refund cleared this morning', text)          # in full: it is sent in your name
        self.assertLess(text.index('YOUR DRAFT'), text.index('Reply with one of:'))   # read it, then choose
        self.assertNotIn('THEY WROTE', text)
        self.assertIn('Send the reply: sends the draft above, in your name.', text)
        self.assertIn('Reply with one of:\n1 · Send the reply\n2 · Next\n3 · More\n4 · Redraft it', text)
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
        self.assertIn('IT ASKED', text)
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
        self.assertEqual(remote_assistant.answer_the_agent(s, asking_agent(), 'main', picked=False), '')

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
        with mock.patch.object(ws, 'answer_open', return_value={'delivered': False, 'state': 'no_request'}):
            said = remote_assistant.answer_the_agent(s, asking_agent(), 'main', picked=True)
        self.assertIn('waiting room', said)


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
    """The phone opens the day the way the desktop does (2026-09-23): the count, then the four groups."""

    def test_the_groups_and_the_lead(self):
        items = [{'key': 'a', 'lane': 'approve', 'kind': 'review', 'who': 'Erin Blake', 'title': 'Q3 numbers'},
                 {'key': 'b', 'lane': 'yours', 'kind': 'todo', 'channel': 'own', 'who': 'you', 'title': 'Renew Trainly'},
                 {'key': 'c', 'lane': 'blocked', 'kind': 'agent', 'agent': 'coder', 'title': 'Reconcile the GL'},
                 {'key': 'd', 'lane': 'report', 'kind': 'report', 'who': 'Spend report', 'title': 'Spend report - 3 over'},
                 {'key': 'e', 'lane': 'working', 'kind': 'agent', 'title': 'busy'},
                 {'key': 'f', 'lane': 'time', 'kind': 'meeting', 'who': 'Omar Keller', 'title': 'Portal sync'}]
        text = remote_assistant.who_wants_what(items)
        self.assertTrue(text.startswith('4 things. 1 is ready - you only approve, 1 needs a word, 1 is on your list, 1 you can skip.'))
        self.assertIn('PEOPLE WANT · 1\n· Erin Blake - Q3 numbers (draft ready)', text)
        self.assertIn('YOU WANTED · 1', text); self.assertIn('AGENTS WAITING · 1', text)
        self.assertIn('· Report - Spend report - 3 over', text)          # a report's sender is its title
        self.assertNotIn('busy', text)                                   # working rows wait on nobody
        self.assertEqual(remote_assistant.who_wants_what([]), 'Nothing is waiting on you.')

    def test_it_groups_exactly_as_the_desktop_does(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1] / 'website' / 'src' / 'walkSummary.js').read_text(encoding='utf-8')
        for lane in remote_assistant._AGENT_LANES: self.assertIn(f'"{lane}"', js.split('AGENT_LANES')[1].split(';')[0])
        self.assertEqual([w for _, w in remote_assistant.GROUPS], ['People want', 'You wanted', 'Agents waiting', 'Nothing to decide'])
        for _, word in remote_assistant.GROUPS: self.assertIn(f'word: "{word}"', js)


class TheVerbDoesTheThingTests(unittest.TestCase):
    def test_a_reply_with_no_draft_leads_with_drafting_it_not_closing(self):
        out = {'say': 'Sam is owed a reply.', 'item': {'kind': 'review', 'lane': 'approve'},
               'chips': [{'verb': 'close', 'label': 'Close without sending'}, {'verb': 'redraft', 'label': 'Redraft it'},
                         {'verb': 'not_ours', 'label': 'Not ours'}, {'verb': 'next', 'label': 'Next'}]}
        text = remote_assistant.turn_text(out, store=MemoryStore())
        self.assertIn('Reply with one of:\n1 · Redraft it\n2 · Next\n3 · Close without sending\n4 · Not ours', text)
