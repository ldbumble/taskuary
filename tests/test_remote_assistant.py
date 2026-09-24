"""A phone chat is a private remote view of the SAME assistant walk, not another inbox bot.

WhatsApp and Telegram both reach the concierge on the dock task: the item on the table is the walk's
own, the choices arrive as words because a chat has no buttons, and a handoff locks the tab so two
screens cannot answer the same item.
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import channels, concierge, funnel, general, llm as llm_mod, messengers, phone, \
    remote_assistant, server, terminal
from taskuary.store import MemoryStore


JID = '15551234567@s.whatsapp.net'
TG_CHAT = '900100'


def armed_store(channel='whatsapp', chat=JID, on='1'):
    store = MemoryStore()
    store.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): store.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    cid = store.get_connector_by_type(channel)['ConnectorId']
    store.save_connector({'ConnectorId': cid, 'Active': 1, 'Roles': 'trigger,tool', 'Secret': 'tok',
                          'ConfigJson': json.dumps({'assistant_chat': chat})}, 'test')
    store.set_setting('phone_assistant', on, 'test')
    return store, store.get_connector(cid, with_secret=True)


def waiting(store, subject='Export still broken'):
    """One thing in the pipe: a drafted reply, the kind the walk opens with."""
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    t = store.create_task({'Title': subject, 'Kind': 'coding', 'Status': 'waiting'}, 'o')
    m = store.add_message({'TaskId': t, 'ExternalId': f'x:{subject}', 'ConversationId': f'c:{subject}',
                           'Channel': 'email', 'Subject': subject, 'FromName': 'Dana',
                           'FromEmail': 'dana@vendor.com', 'SentAt': now, 'BodyText': 'Send the corrected file?',
                           'Status': 'routed'})
    r = store.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Attached.', 'Status': 'pending'})
    return t, m, r


class DoorwayBoundaryTests(unittest.TestCase):
    def test_it_is_opt_in_owner_only_exact_chat_and_never_a_group(self):
        store, connector = armed_store()
        with mock.patch.object(remote_assistant.threading, 'Thread') as thread:
            self.assertTrue(remote_assistant.intercept(store, 'whatsapp', JID, 'What needs me?',
                                                       from_me=True, connector=connector))
            thread.assert_called_once()
        self.assertFalse(remote_assistant.intercept(store, 'whatsapp', JID, 'someone else', from_me=False,
                                                    connector=connector))
        self.assertFalse(remote_assistant.intercept(store, 'whatsapp', 'other@s.whatsapp.net', 'mine',
                                                    from_me=True, connector=connector))
        self.assertFalse(remote_assistant.intercept(
            store, 'whatsapp', 'private@g.us', 'mine', from_me=True,
            connector={**connector, 'ConfigJson': json.dumps({'assistant_chat': 'private@g.us'})}))
        store.set_setting('phone_assistant', '0', 'test')
        self.assertFalse(remote_assistant.intercept(store, 'whatsapp', JID, 'mine', from_me=True, connector=connector))

    def test_a_live_handoff_is_the_permission_while_it_lasts(self):
        """The switch is standing permission; the button is the owner asking for it right now."""
        store, connector = armed_store(on='0')
        self.assertFalse(remote_assistant.enabled(store, 'whatsapp', JID, connector))
        with mock.patch.object(remote_assistant, 'send'), mock.patch.object(concierge, 'brain', return_value=None):
            remote_assistant.start_handoff(store, 'whatsapp')
        self.assertTrue(remote_assistant.enabled(store, 'whatsapp', JID, connector))
        remote_assistant.end_handoff(store)
        self.assertFalse(remote_assistant.enabled(store, 'whatsapp', JID, connector))

    def test_the_owners_own_message_yourself_chat_is_not_a_group(self):
        """WhatsApp gives that thread a legacy GROUP jid, and refusing it refused the one chat the
        pairing box points people at (the owner, 2026-09-07: "i said reply and nothing happened")."""
        mine, theirs = '15550100100-1600000001@g.us', '120363000000000001@g.us'
        store, connector = armed_store('whatsapp', mine)
        with mock.patch.object(messengers, 'wa_self_number', return_value='15550100100'):
            self.assertTrue(remote_assistant.is_private(store, connector, mine))
            self.assertFalse(remote_assistant.is_private(store, connector, theirs))
            self.assertEqual([d['chat'] for d in remote_assistant.doorways(store)], [mine])
            with mock.patch.object(remote_assistant.threading, 'Thread') as thread:
                self.assertTrue(remote_assistant.intercept(store, 'whatsapp', mine, 'what needs me?',
                                                           from_me=True, connector=connector))
                thread.assert_called_once()
        # a REAL group named as the assistant chat is still refused, and offers no doorway at all
        store2, connector2 = armed_store('whatsapp', theirs)
        with mock.patch.object(messengers, 'wa_self_number', return_value='15550100100'):
            self.assertFalse(remote_assistant.enabled(store2, 'whatsapp', theirs, connector2))
            self.assertEqual(remote_assistant.doorways(store2), [])

    def test_the_paired_number_is_asked_for_once_and_remembered(self):
        store, connector = armed_store('whatsapp', '15550100100-1600000001@g.us')
        with mock.patch.object(messengers, '_wa', return_value={'jid': '15550100100:30@s.whatsapp.net'}) as bridge:
            self.assertEqual(messengers.wa_self_number(store, connector), '15550100100')
        fresh = store.get_connector(connector['ConnectorId'], with_secret=True)
        self.assertEqual(json.loads(fresh['ConfigJson'])['me_number'], '15550100100')
        with mock.patch.object(messengers, '_wa', side_effect=AssertionError('asked twice')):
            self.assertEqual(messengers.wa_self_number(store, fresh), '15550100100')

    def test_taskuary_bridge_echo_is_claimed_without_starting_an_answer(self):
        store, connector = armed_store()
        with mock.patch.object(remote_assistant.threading, 'Thread') as thread:
            self.assertTrue(remote_assistant.intercept(store, 'whatsapp', JID, 'a notification',
                                                       from_me=True, taskuary=True, connector=connector))
            thread.assert_not_called()

    def test_poll_routes_owner_question_and_discards_taskuary_output(self):
        store, connector = armed_store()
        feed = {'seq': 9, 'messages': [
            {'id': 'q', 'jid': JID, 'text': 'Walk me through important email', 'fromMe': True},
            {'id': 'a', 'jid': JID, 'text': 'Taskuary: answer', 'fromMe': True, 'taskuary': True},
        ]}
        with mock.patch.object(messengers, '_wa', return_value=feed), \
             mock.patch.object(remote_assistant, 'intercept', return_value=True) as intercept:
            self.assertEqual(messengers.poll_whatsapp(store, connector, [], llm=None), 0)
        intercept.assert_called_once_with(store, 'whatsapp', JID, 'Walk me through important email',
                                          from_me=True, connector=connector, message_id='q')
        self.assertEqual(json.loads(store.get_connector(connector['ConnectorId'])['ConfigJson'])['wa_seq'], 9)

    def test_telegram_routes_only_the_named_private_chat(self):
        """A bot hears no fromMe: the named private chat is what says the words are the owner's."""
        store, connector = armed_store('telegram', TG_CHAT)
        ups = [{'update_id': 1, 'message': {'message_id': 1, 'text': 'what needs me?',
                                            'chat': {'id': int(TG_CHAT), 'type': 'private'}, 'from': {'first_name': 'Alex'}}},
               {'update_id': 2, 'message': {'message_id': 2, 'text': 'from a stranger',
                                            'chat': {'id': 555, 'type': 'private'}, 'from': {'first_name': 'Stranger'}}}]
        with mock.patch.object(messengers, 'tg', return_value=ups), \
             mock.patch.object(remote_assistant.threading, 'Thread') as thread:
            messengers.poll_telegram(store, connector, [], llm=None)
        thread.assert_called_once()
        self.assertEqual(thread.call_args.kwargs['args'][1:4], ('telegram', TG_CHAT, 'what needs me?'))
        # the stranger was not answered and did not become work either - registered OFF, as ever
        self.assertEqual([s['Address'] for s in store.list_sources(active_only=False)
                          if s.get('Channel') == 'telegram'], ['555'])

    def test_a_card_carrying_the_assistant_chat_is_polled_for_that_alone(self):
        for channel, chat in (('whatsapp', JID), ('telegram', TG_CHAT)):
            with self.subTest(channel=channel):
                store, connector = armed_store(channel, chat)
                store.save_connector({'ConnectorId': connector['ConnectorId'], 'Roles': 'tool'}, 'test')
                with mock.patch.object(llm_mod, 'build_llm', return_value=None), \
                     mock.patch.object(messengers, f'poll_{channel}', return_value=0) as poll:
                    channels.poll_channels(store)
                poll.assert_called_once()


class WordsInsteadOfButtonsTests(unittest.TestCase):
    def test_a_turn_carries_the_action_words_the_desktop_would_have_drawn(self):
        said = {'say': 'Dana wants the corrected file.',
                'chips': [{'verb': 'approve', 'label': 'Send the reply'}, {'verb': 'next', 'label': 'Next'}]}
        self.assertEqual(remote_assistant.turn_text(said),
                         'Dana wants the corrected file.\n\nReply with one of:\n1 · Send the reply\n2 · Next')

    def test_a_line_wears_the_mark_of_its_lane_and_says_where_it_came_from(self):
        """The desktop identifies a row by an icon; a chat has only emoji, and it uses the SAME ones
        (website/src/funnelPile.js). The owner, 2026-09-10: "we need emojis ... also on what the task
        comes from like email or teams"."""
        said = {'say': 'A reply is drafted and waits for you.', 'options': ['Send it', 'Next'],
                'item': {'lane': 'approve', 'kind': 'review', 'who': 'Craig Sherman', 'channel': 'email'}}
        self.assertEqual(remote_assistant.turn_text(said),
                         '📧 Craig Sherman · email\n✉️ A reply is drafted and waits for you.'
                         '\n\nReply with one of:\n1 · Send it\n2 · Next')

    def test_a_report_wears_the_report_mark_and_a_finished_agent_its_own(self):
        report = {'say': 'Process Error Check - 0 rows landed 8 min ago.', 'item': {'lane': 'report', 'kind': 'report'}}
        self.assertTrue(remote_assistant.turn_text(report).startswith('📄 Process Error Check'))
        done = {'say': 'coder finished TQ-0491.', 'item': {'lane': 'report', 'kind': 'agentdone'}}
        self.assertTrue(remote_assistant.turn_text(done).startswith('✅ coder finished'), 'the kind outranks the lane')

    def test_an_fyi_batch_is_its_items_one_per_line_and_no_summary(self):
        """"4 things people told you, nothing to do: someone - 4 fyi; Alex - Run failed..." and under it
        "fyi - people told you things; nothing to do" - on a phone that read as nothing (the owner,
        2026-09-18: "don't need random summary, just show the items")."""
        batch = {'say': '2 things people told you, nothing to do: Alex - Run failed: ci; Erin - Rebecca is back Tuesday.',
                 'chips': [{'verb': 'next', 'label': 'All read, next'}],
                 'item': {'kind': 'fyis', 'lane': 'fyi', 'why': 'people told you things; nothing to do',
                          'items': [{'who': 'Alex', 'title': 'Run failed: ci', 'channel': 'github'},
                                    {'who': 'Erin', 'title': 'Rebecca is back Tuesday', 'channel': 'email'}]}}
        text = remote_assistant.turn_text(batch)
        self.assertNotIn('people told you', text)
        head = text.split('\n\n')[0].split('\n')
        # ...numbered, so a number opens one; the chips take the numbers after the members
        self.assertEqual(head[1:], [f"1 · {funnel.CHANNEL_MARKS['github']} Alex - Run failed: ci",
                                    f"2 · {funnel.CHANNEL_MARKS['email']} Erin - Rebecca is back Tuesday"])
        self.assertTrue(head[0].endswith('2 fyi · nothing to do'), head[0])
        # ...and the line says what a number DOES: "open one" describes a door on a screen that is not
        # here, and on a phone the number is the only way to see what a line is about (2026-09-22)
        self.assertIn('Reply with a number to read that message in full, or:\n3 · All read, next', text)
        self.assertNotIn('4 · ', text, 'the walk already offered the way on under its own name')

    def test_a_number_on_an_fyi_batch_opens_that_one(self):
        """The desktop's "Talk about it" on one member; the chat had four lines and no door into any of
        them (the owner, 2026-09-20: "how do you dig into one specific one?")."""
        store, connector = armed_store()
        batch = {'kind': 'fyis', 'lane': 'fyi', 'items': [{'key': 'msg:7', 'who': 'Alex', 'title': 'Run failed: ci', 'channel': 'github'},
                                                          {'key': 'msg:8', 'who': 'Erin', 'title': 'Back Tuesday', 'channel': 'email'}]}
        text = remote_assistant.turn_text({'say': 'x', 'chips': [{'verb': 'next', 'label': 'All read, next'}], 'item': batch})
        remote_assistant.remember_offered(store, 'whatsapp', JID, text)
        with mock.patch.object(concierge, 'restore_current', return_value=batch), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'Erin: back Tuesday.', 'options': [], 'chips': [],
                                                                   'item': {'kind': 'fyi', 'lane': 'fyi'}}) as opened, \
             mock.patch.object(messengers, 'wa_send') as send:
            remote_assistant.respond(store, 'whatsapp', JID, '2', connector['ConnectorId'])
        self.assertEqual(opened.call_args.args[1], 'msg:8')
        self.assertIn('Erin: back Tuesday.', send.call_args.args[2])

    def test_an_unknown_source_gets_no_invented_mark(self):
        said = {'say': 'Something landed.', 'item': {'lane': 'fyi', 'kind': 'fyi', 'who': 'Someone', 'channel': 'carrier_pigeon'}}
        self.assertEqual(remote_assistant.turn_text(said), 'Someone · carrier pigeon\n👀 Something landed.')

    def test_a_bare_number_answers_the_options_we_just_numbered(self):
        """The number is answerable because WE numbered it a moment ago: the code indexes what it
        offered, it never reads words (no hardcoded verbs)."""
        s = MemoryStore()
        remote_assistant.remember_offered(s, 'whatsapp', JID, 'Reply with one of:\n1 · Run it again\n2 · Hand it to an agent\n3 · Next')
        self.assertEqual(remote_assistant.resolve_index(s, 'whatsapp', JID, '2'), ('Hand it to an agent', True))
        self.assertEqual(remote_assistant.resolve_index(s, 'whatsapp', JID, '3.'), ('Next', True))
        self.assertEqual(remote_assistant.resolve_index(s, 'whatsapp', JID, '9'), ('9', False), "out of range stays the owner's own words")
        self.assertEqual(remote_assistant.resolve_index(s, 'whatsapp', JID, 'run it again'), ('run it again', False))

    def test_a_proposal_is_waiting_on_a_yes_and_nothing_else_is_offered(self):
        said = {'say': 'File it: Dana - invoice.', 'chips': [{'verb': 'next', 'label': 'Next'}],
                'proposal': {'id': 'op1', 'status': 'proposed'}}
        self.assertEqual(remote_assistant.choices(said), ['yes, go ahead', 'no, leave it'])

    def test_desktop_only_links_are_never_sent_to_a_chat(self):
        self.assertEqual(remote_assistant.turn_text({'say': 'Start with [TQ-0001](#task=1) today.'}),
                         'Start with TQ-0001 today.')

    def test_a_long_walkthrough_is_sent_in_several_messages(self):
        store, connector = armed_store()
        with mock.patch.object(messengers, 'wa_send') as send:
            remote_assistant.send(store, 'whatsapp', JID, 'paragraph words ' * 700, connector['ConnectorId'])
        self.assertGreater(send.call_count, 1)
        self.assertTrue(all(len(call.args[2]) <= 4000 for call in send.call_args_list))

    def test_telegram_answers_go_back_through_the_bot(self):
        store, connector = armed_store('telegram', TG_CHAT)
        with mock.patch.object(messengers, 'tg_send') as send:
            remote_assistant.send(store, 'telegram', TG_CHAT, 'hello', connector['ConnectorId'])
        self.assertEqual(send.call_args.args[1], TG_CHAT)


class SameWalkTests(unittest.TestCase):
    def test_a_question_is_answered_by_the_walk_on_the_same_conversation(self):
        store, connector = armed_store()
        waiting(store)
        seen = {}
        brain = lambda system, user, **kw: seen.update(system=system, user=user) or 'Dana is waiting on the corrected file.'
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(concierge, 'brain', return_value=brain), \
             mock.patch.object(messengers, 'wa_send') as send:
            remote_assistant.respond(store, 'whatsapp', JID, 'what needs me?', connector['ConnectorId'])
        # the phone is told it is a phone - no cards, no buttons, no "click"
        self.assertIn('on their phone', seen['system'])
        self.assertNotIn('Assistant tab', seen['system'])
        # ...and it is the SAME conversation the tab reads
        rows = general.chat_rows(store, general.dock_task(store)[0]['TaskId'])
        self.assertEqual([r['ActorType'] for r in rows], [general.USER_TYPE, general.ASSISTANT_TYPE])
        self.assertIn('Dana is waiting on the corrected file.', send.call_args.args[2])

    def test_next_moves_the_walk_and_the_next_item_comes_with_it(self):
        """The tab's own JavaScript surfaces the next card; a chat has no page, so this must."""
        store, connector = armed_store()
        _t, _m, r = waiting(store)
        concierge.set_current(store, general.dock_task(store)[0]['TaskId'], f'review:{r}')
        with mock.patch.object(concierge, 'brain', return_value=lambda *a, **k: 'Ok.\nDECIDE: next'), \
             mock.patch.object(concierge, 'surface', return_value={'say': "That's everything for now.",
                                                                   'options': [], 'chips': []}) as nxt, \
             mock.patch.object(messengers, 'wa_send') as send:
            remote_assistant.respond(store, 'whatsapp', JID, 'next', connector['ConnectorId'])
        nxt.assert_called_once()
        self.assertIn("That's everything for now.", send.call_args.args[2])

    def test_a_settle_the_assistant_decided_runs_here_because_no_page_will(self):
        store, connector = armed_store()
        ran = {}
        turn = {'say': 'Marking it handled.', 'options': [], 'chips': [],
                'proposal': {'id': 'op1', 'version': 1, 'kind': 'item.settle', 'auto': True,
                             'status': 'proposed', 'settles': True, 'key': 'msg:1'}}
        with mock.patch.object(concierge, 'run_proposal', side_effect=lambda s, p, a: ran.update(op=p['id']) or {'status': 'done'}), \
             mock.patch.object(concierge, 'receipt', return_value='Done - Mark it handled.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'Next up: the payroll thread.', 'chips': []}):
            text = remote_assistant.carry_out(store, turn, {'key': 'msg:1'})
        self.assertEqual(ran['op'], 'op1')
        self.assertIn('Done - Mark it handled.', text)
        self.assertIn('Next up: the payroll thread.', text)

    def test_a_hand_off_from_plain_words_does_not_staple_the_next_item_on(self):
        """The desktop walks on only when the item ON THE TABLE was settled; a hand-off started from words settles
        nothing there, and the phone used to append the next email under its receipt (2026-09-24 chat audit)."""
        store, connector = armed_store()
        turn = {'say': 'Starting the researcher on it.', 'options': [], 'chips': [],
                'proposal': {'id': 'op2', 'version': 1, 'kind': 'task.create_from_text', 'auto': True,
                             'status': 'proposed', 'settles': True, 'key': None}}
        with mock.patch.object(concierge, 'run_proposal', return_value={'status': 'done'}), \
             mock.patch.object(concierge, 'receipt', return_value='Done - it is with the researcher.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'Next up: the budget tab.', 'chips': []}):
            text = remote_assistant.carry_out(store, turn, {'key': 'msg:9'})
        self.assertIn('Done - it is with the researcher.', text)
        self.assertNotIn('Next up', text)

    def test_a_reply_the_owner_asked_for_is_actually_drafted(self):
        store, connector = armed_store()
        _t, m, _r = waiting(store)
        turn = {'say': "I'll draft that.", 'chips': [], 'decision': {'verb': 'reply', 'text': 'tell her it is sent'}}
        with mock.patch.object(remote_assistant, '_draft', return_value=77) as draft, \
             mock.patch.object(concierge, 'surface', return_value={'say': 'Here is the draft.', 'chips': []}) as nxt:
            text = remote_assistant.carry_out(store, turn, {'mid': m})
        draft.assert_called_once()
        self.assertEqual(nxt.call_args.args[1], 'review:77')
        self.assertIn('Here is the draft.', text)

    def test_a_reply_aimed_at_someone_else_drafts_to_them_not_to_what_is_on_the_table(self):
        """"reply to Erin ..." while Dovid's mail is on the table drafted to DOVID: the phone read the
        item and ignored the target the interpreter resolved, which the desktop's decide() honours."""
        store, connector = armed_store()
        _t, m, _r = waiting(store)
        elsewhere = {'mid': m + 900, 'key': f'message:{m + 900}', 'ref': 'TQ-0099'}
        turn = {'say': "I'll draft that.", 'chips': [],
                'decision': {'verb': 'reply', 'text': 'tell her it is sent', 'target': elsewhere}}
        with mock.patch.object(remote_assistant, '_draft', return_value=77) as draft,              mock.patch.object(concierge, 'surface', return_value={'say': 'Here is the draft.', 'chips': []}):
            remote_assistant.carry_out(store, turn, {'mid': m})
        self.assertEqual(draft.call_args.args[1]['mid'], m + 900)


class HandoffTests(unittest.TestCase):
    def test_handing_over_says_hello_there_and_locks_the_tab(self):
        store, connector = armed_store()
        waiting(store)
        with mock.patch.object(concierge, 'brain', return_value=None), \
             mock.patch.object(messengers, 'wa_send') as send:
            out = remote_assistant.start_handoff(store, 'whatsapp')
        self.assertEqual(out['channel'], 'whatsapp')
        self.assertIn('Reply in this chat', send.call_args.args[2])
        self.assertEqual(remote_assistant.handoff(store)['chat'], JID)
        with mock.patch.object(server, 'store', store):
            r = TestClient(server.app).post('/api/concierge/say', json={'text': 'hello'})
        self.assertEqual(r.status_code, 409)
        self.assertIn('WhatsApp', r.json()['detail'])

    def test_taking_it_back_ends_the_chat_walk_and_unlocks_the_tab(self):
        store, _connector = armed_store()
        with mock.patch.object(concierge, 'brain', return_value=None), mock.patch.object(messengers, 'wa_send'):
            remote_assistant.start_handoff(store, 'whatsapp')
        with mock.patch.object(messengers, 'wa_send') as send:
            self.assertTrue(remote_assistant.end_handoff(store)['ended'])
        self.assertIn('this walk is over here', send.call_args.args[2])
        self.assertIsNone(remote_assistant.handoff(store))
        with mock.patch.object(server, 'store', store), mock.patch.object(concierge, 'brain', return_value=None):
            self.assertEqual(TestClient(server.app).post('/api/concierge/say', json={'text': 'hello'}).status_code, 200)

    def test_a_card_turned_off_never_leaves_the_desktop_locked_out(self):
        store, connector = armed_store()
        with mock.patch.object(concierge, 'brain', return_value=None), mock.patch.object(messengers, 'wa_send'):
            remote_assistant.start_handoff(store, 'whatsapp')
        store.save_connector({'ConnectorId': connector['ConnectorId'], 'Active': 0}, 'test')
        self.assertIsNone(remote_assistant.handoff(store))

    def test_only_a_connected_chat_that_names_an_assistant_chat_is_offered(self):
        store, connector = armed_store()
        self.assertEqual([d['channel'] for d in remote_assistant.doorways(store)], ['whatsapp'])
        store.save_connector({'ConnectorId': connector['ConnectorId'], 'ConfigJson': json.dumps({})}, 'test')
        self.assertEqual(remote_assistant.doorways(store), [])
        with self.assertRaises(ValueError):
            remote_assistant.start_handoff(store, 'telegram')

    def test_the_tab_is_told_where_the_walk_is(self):
        store, _connector = armed_store()
        with mock.patch.object(server, 'store', store):
            state = TestClient(server.app).get('/api/concierge').json()
        self.assertEqual([d['label'] for d in state['doorways']], ['WhatsApp'])
        self.assertIsNone(state['handoff'])


class InterruptionsReachThePhoneTests(unittest.TestCase):
    """The desktop's by-the-way strip is on the tab the handoff locked - the wrong place to raise
    an agent's question (the owner, 2026-09-07)."""
    def pile(self, key='agent:tq412', text='coder asked you something', ref='TQ-0412'):
        return {'items': [{'key': key, 'ref': ref}],
                'alerts': [{'key': f'alert:{key}', 'item': key, 'kind': 'agent', 'text': text}]}

    def handed_over(self):
        store, connector = armed_store()
        with mock.patch.object(concierge, 'brain', return_value=None), mock.patch.object(messengers, 'wa_send'):
            remote_assistant.start_handoff(store, 'whatsapp')
        return store, connector

    def test_an_agents_question_is_sent_to_the_chat_once_and_kept_in_the_conversation(self):
        store, _c = self.handed_over()
        with mock.patch.object(funnel, 'pile', return_value=self.pile()),              mock.patch.object(messengers, 'wa_send') as send:
            self.assertEqual(remote_assistant.push_alerts(store, force=True), 1)
            self.assertEqual(remote_assistant.push_alerts(store, force=True), 0)     # said once per handoff
        sent = send.call_args.args[2]
        self.assertIn('By the way', sent)
        self.assertIn('coder asked you something (TQ-0412)', sent)
        self.assertIn('Say TQ-0412 to take it now', sent)                            # a ref lookup() can find
        rows = general.chat_rows(store, general.dock_task(store)[0]['TaskId'])
        self.assertTrue(any('By the way' in (r['Body'] or '') for r in rows))        # answerable next turn

    def test_nothing_is_sent_when_the_walk_is_at_the_desk(self):
        store, _connector = armed_store()
        with mock.patch.object(funnel, 'pile', return_value=self.pile()),              mock.patch.object(messengers, 'wa_send') as send:
            self.assertEqual(remote_assistant.push_alerts(store, force=True), 0)
        send.assert_not_called()

    def test_the_item_already_on_the_table_is_not_announced(self):
        store, _c = self.handed_over()
        concierge.set_current(store, general.dock_task(store)[0]['TaskId'], 'agent:tq412')
        with mock.patch.object(funnel, 'pile', return_value=self.pile()),              mock.patch.object(messengers, 'wa_send') as send:
            self.assertEqual(remote_assistant.push_alerts(store, force=True), 0)
        send.assert_not_called()

    def test_taking_it_back_forgets_what_was_told(self):
        store, _c = self.handed_over()
        with mock.patch.object(messengers, 'wa_send'):
            with mock.patch.object(funnel, 'pile', return_value=self.pile()):
                remote_assistant.push_alerts(store, force=True)
                self.assertTrue(remote_assistant.handoff(store)['told'])
            remote_assistant.end_handoff(store)
            with mock.patch.object(concierge, 'brain', return_value=None):
                remote_assistant.start_handoff(store, 'whatsapp')                    # a fresh walk...
            with mock.patch.object(funnel, 'pile', return_value=self.pile()):
                self.assertEqual(remote_assistant.push_alerts(store, force=True), 1)  # ...hears it again


class PhoneApprovalsStillWorkTests(unittest.TestCase):
    def test_natural_question_does_not_edit_the_last_review_when_the_doorway_is_on(self):
        store, _ = armed_store()
        store.set_setting('phone_approvals', '1', 'test')
        t, m, rid = waiting(store)
        phone.ping_tail(store, rid)
        self.assertFalse(phone.intercept(store, 'whatsapp', JID, 'What should I handle first?'))
        self.assertEqual(store.get_review(rid)['Status'], 'pending')


class CardParityTests(unittest.TestCase):
    """A chat message carries what the desktop card carries. The owner, 2026-09-18: "certain parts you
    can't render like buttons (as they are not clickable) but everything else should be the same" - the
    card showed a task list, a whole body and how many messages triage combined; the chat showed a
    300-character teaser and none of the rest."""

    BODY = ('## What & why\n\n'
            'Two things that make allowed_hosts hard to use from a container, found while putting '
            'Taskuary behind a reverse proxy. Two commits, reviewable separately.\n\n'
            '- The TOML array form appears not to work. config._tval writes a list as a TOML array '
            'and tomllib reads one back, but allowed_hosts() only ever did str().split(comma).')

    def armed(self, body=None, checklist=('Review the proposed changes', 'Assess the tests', 'Decide whether to merge')):
        store = MemoryStore()
        tid = store.create_task({'Title': 'GitHub PR fixes allowed_hosts config behavior', 'Status': 'waiting'}, 'o')
        if checklist: store.set_task_checklist(tid, list(checklist), 'owner')
        mid = store.add_message({'TaskId': tid, 'ExternalId': 'gh:50', 'ConversationId': 'c:gh50',
                                 'Channel': 'github', 'Subject': 'GitHub PR fixes allowed_hosts config behavior',
                                 'FromName': 'Robin Vale', 'FromEmail': 'code@personal.example',
                                 'SentAt': '2026-09-17 23:03:00', 'BodyText': body or self.BODY, 'Status': 'routed'})
        return store, tid, mid

    def test_the_task_list_stays_on_the_task(self):
        """On the phone as on the desktop (the owner, 2026-09-23: "let's keep the detail task list on the
        actual task tab") - the card is who wants what and what is ready, not the task's whole record."""
        store, tid, mid = self.armed()
        block = remote_assistant.decision_block(store, {'tid': tid, 'mid': mid})
        self.assertNotIn('TASK LIST', block)
        self.assertNotIn('\u2610 Review the proposed changes', block)

    def test_a_task_with_no_list_says_nothing_about_one(self):
        store, tid, mid = self.armed(checklist=())
        self.assertNotIn('TASK LIST', remote_assistant.decision_block(store, {'tid': tid, 'mid': mid}))

    def test_the_body_arrives_whole_and_stays_quoted_all_the_way_down(self):
        """A 300-character teaser cut mid-word and the rest existed only on the desktop. send() splits
        on paragraph boundaries, so a long body costs extra bubbles, never the words themselves."""
        store, tid, mid = self.armed()
        block = remote_assistant.decision_block(store, {'tid': tid, 'mid': mid})
        self.assertIn('str().split(comma)', block, 'the tail of the body must survive')
        self.assertNotIn('\u2026', block)
        body = block.split('THEY WROTE', 1)[1]
        said = [l for l in body.splitlines() if l.strip()]
        self.assertTrue(all(l.startswith('>') for l in said), f'every body line stays quoted: {said}')

    def test_a_combined_thread_says_how_many_triage_put_together(self):
        store, tid, mid = self.armed()
        store.add_message({'TaskId': tid, 'ExternalId': 'gh:50#2', 'ConversationId': 'c:gh50',
                           'Channel': 'github', 'Subject': 'Re: GitHub PR fixes allowed_hosts config behavior',
                           'FromName': 'Robin Vale', 'FromEmail': 'code@personal.example',
                           'SentAt': '2026-09-17 23:40:00', 'BodyText': 'One more thought.', 'Status': 'routed'})
        self.assertIn('2 messages combined by triage', remote_assistant.decision_block(store, {'tid': tid, 'mid': mid}))

    def test_a_source_keeps_its_own_spelling_in_the_thread_line(self):
        """A brand name is not a word to title-case: the card would have said GitHub, not Github."""
        store, tid, mid = self.armed()
        store.add_message({'TaskId': tid, 'ExternalId': 'gh:50#2', 'ConversationId': 'c:gh50',
                           'Channel': 'github', 'Subject': 'Re: GitHub PR fixes allowed_hosts config behavior',
                           'FromName': 'Robin Vale', 'FromEmail': 'code@personal.example',
                           'SentAt': '2026-09-17 23:40:00', 'BodyText': 'One more thought.', 'Status': 'routed'})
        self.assertIn('GitHub context', remote_assistant.decision_block(store, {'tid': tid, 'mid': mid}))

    def test_a_report_is_not_dressed_up_as_something_a_person_wrote(self):
        """The digest is Taskuary's OWN output. "THEY WROTE" over a >-quoted block says a person sent
        it to you, and the card never quotes it - it prints the sections (the owner, 2026-09-18:
        "this is morning digest report on whatsapp vs assistant??? still wrong")."""
        store = MemoryStore()
        mid = store.add_message({'TaskId': None, 'ExternalId': 'report:1:x', 'ConversationId': 'report:1',
                                 'Channel': 'report', 'Subject': 'Morning digest', 'FromName': 'Morning digest',
                                 'SentAt': '2026-09-18 08:05:00', 'Status': 'feed',
                                 'BodyText': '\U0001F4C5 Meetings today\n\n1. 10:00 \u00b7 ESS link\n\n\U0001F64B People want\n\n1. Autumn asked about a refund'})
        block = remote_assistant.decision_block(store, {'mid': mid, 'kind': 'report'})
        self.assertNotIn('THEY WROTE', block)
        self.assertFalse([l for l in block.splitlines() if l.startswith('>')], 'a report is not quoted')
        self.assertIn('Meetings today', block)                       # its first section, in the open
        self.assertIn('People want', remote_assistant.more_text(store, {'mid': mid, 'kind': 'report'}))   # the rest behind More

    def test_a_person_still_gets_the_quote_marks(self):
        store, tid, mid = self.armed()
        self.assertIn('THEY WROTE', remote_assistant.decision_block(store, {'tid': tid, 'mid': mid}))

    def test_markdown_is_read_not_shown_as_its_own_punctuation(self):
        """Neither sender sets parse_mode - both post PLAIN text - so a sender's **bold**, `code`,
        ## headings and [links](url) arrived as their own punctuation once the body stopped being
        truncated. The desktop renders them; a chat has to be given the words without the marks."""
        body = ('## Summary\n\n'
                'The **export** job fails on `--dry-run` when the _config_ is empty.\n\n'
                '- [ ] reproduce it\n'
                '- [x] find the cause\n\n'
                'See [the PR](https://github.com/x/y/pull/50) for the fix.')
        store, tid, mid = self.armed(body=body, checklist=())
        block = remote_assistant.decision_block(store, {'tid': tid, 'mid': mid})
        for raw in ('**', '`', '## ', '](', '- [ ]', '- [x]'):
            self.assertNotIn(raw, block, f'{raw!r} is punctuation, not words')
        for word in ('Summary', 'export', '--dry-run', 'reproduce it', 'the PR'):
            self.assertIn(word, block, f'{word!r} must survive the stripping')
        self.assertIn('\u2610 reproduce it', block)
        self.assertIn('\u2611 find the cause', block)

    def test_the_draft_is_never_rewritten_on_its_way_to_you(self):
        """YOUR DRAFT is the literal text that goes out in your name - approving a cleaned-up copy
        of it would mean approving something other than what is sent."""
        store, tid, mid = self.armed(checklist=())
        rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft',
                                'DraftText': 'Totals are in the **attached** sheet (`Q3.xlsx`).',
                                'Status': 'pending'})
        block = remote_assistant.decision_block(store, {'tid': tid, 'mid': mid, 'rid': rid})
        self.assertIn('**attached**', block)
        self.assertIn('`Q3.xlsx`', block)

    def test_a_single_message_is_not_announced_as_a_thread(self):
        store, tid, mid = self.armed()
        self.assertNotIn('combined by triage', remote_assistant.decision_block(store, {'tid': tid, 'mid': mid}))

    def test_the_source_line_carries_the_ref_the_desktop_prints_in_its_corner(self):
        """So the owner can say "open TQ-0630" when they get back to a desktop."""
        item = {'who': 'Robin Vale', 'channel': 'github', 'ref': 'TQ-0630'}
        self.assertEqual(remote_assistant.source_line(item), '\U0001f419 Robin Vale \u00b7 github \u00b7 TQ-0630')

    def test_the_status_line_speaks_the_one_vocabulary(self):
        """lanes.json is the single table the desktop and the chat both read - never a second copy."""
        out = {'say': 'Robin Vale wrote on github.', 'options': ['Next'],
               'item': {'lane': 'queued', 'kind': 'todo', 'who': 'Robin Vale', 'channel': 'github',
                        'why': 'handed to an agent, not started yet'}}
        text = remote_assistant.turn_text(out)
        self.assertIn(f'{funnel.LANE_WORDS["queued"][0]} - handed to an agent, not started yet', text)

    def test_a_body_that_looks_like_our_own_numbering_cannot_hijack_the_reply(self):
        """remember_offered scanned the WHOLE message for "N - word". Now that a full body rides along, a
        body line shaped like our own list would silently re-point the numbers the owner answers with."""
        store = MemoryStore()
        text = ('THEY WROTE\n> Ranking:\n> 1 \u00b7 drop the database\n> 2 \u00b7 email everyone\n\n'
                'Reply with one of:\n1 \u00b7 Send the reply\n2 \u00b7 Next')
        self.assertEqual(remote_assistant.remember_offered(store, 'whatsapp', JID, text), ['Send the reply', 'Next'])
        self.assertEqual(remote_assistant.resolve_index(store, 'whatsapp', JID, '1'), ('Send the reply', True))


if __name__ == '__main__':
    unittest.main()


def test_a_phone_turn_tells_the_desktop_when_it_starts_and_when_it_is_answered():
    """The owner, 2026-09-24: "it takes 20 seconds from when message is responded to in whatsapp to show up on the
    assistant". The tab read its conversation on a 30 s tick; the turn now announces itself both ways - and the
    end is announced even when answering failed, or the dots would spin for ever."""
    from unittest import mock
    from taskuary import live, remote_assistant
    from taskuary.store import MemoryStore
    said = []
    with mock.patch.object(live, 'emit', lambda kind, **kw: said.append((kind, kw.get('thinking')))), \
         mock.patch.object(remote_assistant, 'respond', side_effect=RuntimeError('model down')):
        try: remote_assistant._locked_respond(MemoryStore(), 'whatsapp', 'me@s.test', 'hello', None)
        except RuntimeError: pass
    assert said == [(live.CHAT, True), (live.CHAT, False)]
