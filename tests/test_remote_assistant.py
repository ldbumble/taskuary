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
        mine, theirs = '18483734737-1612296871@g.us', '120363407840479752@g.us'
        store, connector = armed_store('whatsapp', mine)
        with mock.patch.object(messengers, 'wa_self_number', return_value='18483734737'):
            self.assertTrue(remote_assistant.is_private(store, connector, mine))
            self.assertFalse(remote_assistant.is_private(store, connector, theirs))
            self.assertEqual([d['chat'] for d in remote_assistant.doorways(store)], [mine])
            with mock.patch.object(remote_assistant.threading, 'Thread') as thread:
                self.assertTrue(remote_assistant.intercept(store, 'whatsapp', mine, 'what needs me?',
                                                           from_me=True, connector=connector))
                thread.assert_called_once()
        # a REAL group named as the assistant chat is still refused, and offers no doorway at all
        store2, connector2 = armed_store('whatsapp', theirs)
        with mock.patch.object(messengers, 'wa_self_number', return_value='18483734737'):
            self.assertFalse(remote_assistant.enabled(store2, 'whatsapp', theirs, connector2))
            self.assertEqual(remote_assistant.doorways(store2), [])

    def test_the_paired_number_is_asked_for_once_and_remembered(self):
        store, connector = armed_store('whatsapp', '18483734737-1612296871@g.us')
        with mock.patch.object(messengers, '_wa', return_value={'jid': '18483734737:30@s.whatsapp.net'}) as bridge:
            self.assertEqual(messengers.wa_self_number(store, connector), '18483734737')
        fresh = store.get_connector(connector['ConnectorId'], with_secret=True)
        self.assertEqual(json.loads(fresh['ConfigJson'])['me_number'], '18483734737')
        with mock.patch.object(messengers, '_wa', side_effect=AssertionError('asked twice')):
            self.assertEqual(messengers.wa_self_number(store, fresh), '18483734737')

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
                                          from_me=True, connector=connector)
        self.assertEqual(json.loads(store.get_connector(connector['ConnectorId'])['ConfigJson'])['wa_seq'], 9)

    def test_telegram_routes_only_the_named_private_chat(self):
        """A bot hears no fromMe: the named private chat is what says the words are the owner's."""
        store, connector = armed_store('telegram', TG_CHAT)
        ups = [{'update_id': 1, 'message': {'message_id': 1, 'text': 'what needs me?',
                                            'chat': {'id': int(TG_CHAT), 'type': 'private'}, 'from': {'first_name': 'Uri'}}},
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
                         'Dana wants the corrected file.\n\nReply with: Send the reply · Next')

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
                             'status': 'proposed', 'settles': True}}
        with mock.patch.object(concierge, 'run_proposal', side_effect=lambda s, p, a: ran.update(op=p['id']) or {'status': 'done'}), \
             mock.patch.object(concierge, 'receipt', return_value='Done - Mark it handled.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'Next up: the payroll thread.', 'chips': []}):
            text = remote_assistant.carry_out(store, turn, None)
        self.assertEqual(ran['op'], 'op1')
        self.assertIn('Done - Mark it handled.', text)
        self.assertIn('Next up: the payroll thread.', text)

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


if __name__ == '__main__':
    unittest.main()
