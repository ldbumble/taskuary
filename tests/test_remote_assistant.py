"""WhatsApp is a private remote view of the same Taskuary guide, not another inbox bot."""
import json, unittest
from unittest import mock

from taskuary import channels, general, llm as llm_mod, messengers, phone, remote_assistant, terminal
from taskuary.store import MemoryStore


JID = '15551234567@s.whatsapp.net'


def armed_store():
    store = MemoryStore()
    store.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
    cid = store.get_connector_by_type('whatsapp')['ConnectorId']
    store.save_connector({'ConnectorId': cid, 'Active': 1, 'Roles': 'trigger,tool',
                          'ConfigJson': json.dumps({'assistant_chat': JID})}, 'test')
    store.set_setting('phone_assistant', '1', 'test')
    return store, store.get_connector(cid, with_secret=True)


class RemoteAssistantBoundaryTests(unittest.TestCase):
    def test_it_is_opt_in_owner_only_exact_chat_and_never_a_group(self):
        store, connector = armed_store()
        with mock.patch.object(remote_assistant.threading, 'Thread') as thread:
            self.assertTrue(remote_assistant.intercept(store, JID, 'What needs me?', from_me=True,
                                                       connector=connector))
            thread.assert_called_once()
        self.assertFalse(remote_assistant.intercept(store, JID, 'someone else', from_me=False,
                                                    connector=connector))
        self.assertFalse(remote_assistant.intercept(store, 'other@s.whatsapp.net', 'mine', from_me=True,
                                                    connector=connector))
        self.assertFalse(remote_assistant.intercept(store, 'private@g.us', 'mine', from_me=True,
                                                    connector={**connector, 'ConfigJson': json.dumps({'assistant_chat': 'private@g.us'})}))
        store.set_setting('phone_assistant', '0', 'test')
        self.assertFalse(remote_assistant.intercept(store, JID, 'mine', from_me=True, connector=connector))

    def test_taskuary_bridge_echo_is_claimed_without_starting_an_answer(self):
        store, connector = armed_store()
        with mock.patch.object(remote_assistant.threading, 'Thread') as thread:
            self.assertTrue(remote_assistant.intercept(store, JID, 'a notification', from_me=True,
                                                       taskuary=True, connector=connector))
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
        intercept.assert_called_once_with(store, JID, 'Walk me through important email',
                                          from_me=True, connector=connector)
        self.assertEqual(json.loads(store.get_connector(connector['ConnectorId'])['ConfigJson'])['wa_seq'], 9)

    def test_notify_only_whatsapp_is_polled_when_remote_guide_is_on(self):
        store, connector = armed_store()
        with mock.patch.object(llm_mod, 'build_llm', return_value=None), \
             mock.patch.object(messengers, 'poll_whatsapp', return_value=0) as poll:
            channels.poll_channels(store)
        poll.assert_called_once()


class RemoteAssistantConversationTests(unittest.TestCase):
    def test_answer_uses_desktop_conversation_fresh_snapshot_and_same_history(self):
        store, connector = armed_store()
        tid = store.create_task({'Title': 'Fix payroll export', 'Kind': 'coding', 'Status': 'waiting'}, 'test')
        mid = store.add_message({'TaskId': tid, 'ExternalId': 'mail:payroll', 'Channel': 'email',
                                 'Subject': 'Payroll file is still wrong', 'FromName': 'Dana',
                                 'SentAt': '2026-09-02 09:00:00', 'BodyText': 'Please fix the totals.',
                                 'Status': 'routed'})
        store.add_route(mid, tid, 'create', .9, 'needs an answer', [], 'router')
        store.add_comment(tid, 'coder', 'agent', 'CODER REPORT\nFixed rounding and added three regression tests.')
        seen = {}

        def brain(system, user, **kwargs):
            seen.update(system=system, user=user)
            return 'Start with [TQ-0001](#task=1): review the corrected payroll file.'

        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(llm_mod, 'build_llm', return_value=brain), \
             mock.patch.object(messengers, 'wa_send', return_value={'channel': 'whatsapp', 'chat': JID}) as send:
            remote_assistant.respond(store, JID, 'What needs me and what did the coder do?',
                                     connector['ConnectorId'])

        dock, created = general.dock_task(store)
        self.assertFalse(created)
        rows = general.chat_rows(store, dock['TaskId'])
        self.assertEqual([r['ActorType'] for r in rows], [general.USER_TYPE, general.ASSISTANT_TYPE])
        self.assertEqual(rows[0]['Body'], 'What needs me and what did the coder do?')
        self.assertIn('WORKSPACE SNAPSHOT', seen['user'])
        self.assertIn('Payroll file is still wrong', seen['user'])
        self.assertIn('Fixed rounding', seen['user'])
        self.assertIn('HOVERING GUIDE', seen['system'])
        self.assertIn('WHATSAPP TEXT-ONLY DELIVERY', seen['system'])
        self.assertIn('2-4 short numbered choices', seen['system'])
        self.assertEqual(send.call_args.args[1], JID)
        self.assertEqual(send.call_args.args[2], 'Taskuary:\nStart with TQ-0001: review the corrected payroll file.')

    def test_long_walkthrough_is_sent_in_multiple_whatsapp_messages(self):
        store, connector = armed_store()
        with mock.patch.object(messengers, 'wa_send') as send:
            remote_assistant._send(store, JID, ('paragraph words ' * 700), connector['ConnectorId'])
        self.assertGreater(send.call_count, 1)
        self.assertTrue(all(len(call.args[2]) <= 4000 for call in send.call_args_list))

    def test_natural_question_does_not_edit_the_last_review_when_guide_is_on(self):
        store, _ = armed_store()
        store.set_setting('phone_approvals', '1', 'test')
        tid = store.create_task({'Title': 'Reply', 'Kind': 'reply', 'Status': 'waiting'}, 'test')
        mid = store.add_message({'TaskId': tid, 'ExternalId': 'mail:reply', 'Channel': 'email',
                                 'Subject': 'Reply', 'BodyText': 'hello', 'Status': 'routed'})
        rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft',
                                'DraftText': 'draft', 'Status': 'pending'})
        phone.ping_tail(store, rid)
        self.assertFalse(phone.intercept(store, 'whatsapp', JID, 'What should I handle first?'))
        self.assertEqual(store.get_review(rid)['Status'], 'pending')


if __name__ == '__main__':
    unittest.main()
