"""THE ONE AGENT BOX (the owner, 2026-10-23: "start a agent on fyi email or any email you need to write prompt what about the email or
attachment is the issue?? ... Same for sending to agent ... a report we need to be able to write prompt what part of the report you
want to update"). Every door that starts an agent on an item asks what first - the desktop's box (website RunForm.jsx), the phone's
"What should it do?" - and the start carries the owner's words and the agent chosen, the words leading what the agent is told and
the item (the mail and its files, the report's rows) behind them as its material."""
import json, unittest
from unittest import mock

from taskuary import concierge, funnel, general, messengers, remote_assistant as ra, server
from taskuary.store import MemoryStore

JID = '15550001234@s.whatsapp.net'


def store():
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'coding_auto_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    return s


def fyi(s):
    mid = s.add_message({'ExternalId': 'n1', 'Channel': 'email', 'Subject': 'March invoice batch', 'FromName': 'Gail Moreno',
                         'FromEmail': 'gail@northwind.example', 'SentAt': '2026-10-23 09:00:00',
                         'BodyText': 'Attached is the March batch.', 'Status': 'filed'})
    return mid, {'kind': 'fyi', 'lane': 'fyi', 'mid': mid, 'key': f'msg:{mid}', 'title': 'March invoice batch'}


class ProposalCarriesTheBox(unittest.TestCase):
    def test_a_hand_off_on_a_message_carries_the_words_and_the_agent_chosen(self):
        s = store(); mid, item = fyi(s)
        dock = general.dock_task(s, 'owner')[0]['TaskId']
        prop = concierge.propose_for(s, dock, {'verb': 'regular_agent', 'text': 'the attachment total is off by one invoice',
                                               'agent': 'analyst', 'pick': 'cli:claude', 'model': 'm1', 'brain': ''}, item, '')
        self.assertEqual((prop['kind'], prop['target']), ('task.create_from_message', mid))
        self.assertEqual(prop['params'], {'kind': 'general', 'instructions': 'the attachment total is off by one invoice',
                                          'agent': 'analyst', 'pick': 'cli:claude', 'model': 'm1'})

    def test_make_a_task_never_carries_an_agent(self):
        s = store(); mid, item = fyi(s)
        dock = general.dock_task(s, 'owner')[0]['TaskId']
        prop = concierge.propose_for(s, dock, {'verb': 'mine', 'agent': 'analyst'}, item, '')
        self.assertNotIn('agent', prop['params'])

    def test_the_box_reaches_the_proposal_through_the_press(self):
        s = store(); mid, item = fyi(s)
        with mock.patch.object(funnel, 'next_item', return_value=item):
            prop = concierge.propose_direct(s, 'coding_agent', item['key'], 'why did the export drop a row?', table=True, exact=True,
                                            picks={'brain': 'claude', 'model': None, 'nope': 'x'})
        self.assertEqual(prop['params']['instructions'], 'why did the export drop a row?')
        self.assertEqual(prop['params']['brain'], 'claude')
        self.assertNotIn('nope', prop['params']); self.assertNotIn('model', prop['params'])

    def test_an_item_with_no_message_keeps_the_item_under_the_owners_words(self):
        s = store()
        t = s.create_task({'Title': 'Weekly AP aging', 'Kind': 'task', 'Status': 'open', 'Summary': 'Aging by vendor'}, 'o')
        item = {'kind': 'task', 'lane': 'yours', 'tid': t, 'key': f'task:{t}', 'title': 'Weekly AP aging'}
        dock = general.dock_task(s, 'owner')[0]['TaskId']
        prop = concierge.propose_for(s, dock, {'verb': 'regular_agent', 'text': 'update the Payworth row only', 'on_item': True}, item, '')
        self.assertEqual(prop['kind'], 'task.create_from_text')
        text = prop['params']['text']
        self.assertTrue(text.startswith('update the Payworth row only\n\n'), text)
        self.assertIn('Weekly AP aging', text)                            # the item rides behind the words


class GeneralStartTakesTheWords(unittest.TestCase):
    def test_a_general_hand_off_with_words_starts_with_them_and_the_bare_one_opens_the_chat(self):
        s = store(); mid, _ = fyi(s)
        with mock.patch.object(server, 'store', s), mock.patch.object(server, 'dispatch_message', return_value={'started': True}) as go, \
             mock.patch.object(server, 'chat_message', return_value={'chat': True}) as chat:
            server._run_kind({'kind': 'task.create_from_message', 'target': mid,
                              'params': {'kind': 'general', 'instructions': 'what about the attachment is wrong?', 'pick': 'cli:claude'}}, None)
            body = go.call_args.args[1]
            self.assertEqual((body.kind, body.instruction, body.pick), ('general', 'what about the attachment is wrong?', 'cli:claude'))
            chat.assert_not_called()
            server._run_kind({'kind': 'task.create_from_message', 'target': mid, 'params': {'kind': 'general'}}, None)
            chat.assert_called_once()


class OwnerWordsLeadThePrompt(unittest.TestCase):
    def test_the_owners_words_head_the_prompt_over_the_mail_they_are_about(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'March invoice batch', 'Summary': 'Gail sent the batch', 'Kind': 'general', 'Status': 'open'}, 'owner')
        s.add_message({'TaskId': t, 'Channel': 'email', 'Subject': 'March invoice batch', 'FromName': 'Gail Moreno',
                       'FromEmail': 'gail@northwind.example', 'BodyText': 'Attached is the March batch.', 'Status': 'routed'})
        s.add_comment(t, 'owner', general.USER_TYPE, 'the total on page two does not match the sheet')
        _system, user = general._prompt(s, t)
        self.assertTrue(user.startswith("THE OWNER'S ASK"), user[:120])
        self.assertLess(user.index('the total on page two'), user.index('SOURCE MATERIAL'))     # the mail (or its file, from a stranger)

    def test_no_material_no_lead(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Plan the launch', 'Kind': 'general', 'Status': 'open'}, 'owner')
        s.add_comment(t, 'owner', general.USER_TYPE, 'three options please')
        self.assertTrue(general._prompt(s, t)[1].startswith('TASK'))


def armed():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    cid = s.get_connector_by_type('whatsapp')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1, 'Roles': 'trigger,tool', 'Secret': 'tok',
                      'ConfigJson': json.dumps({'assistant_chat': JID})}, 'test')
    s.set_setting('phone_assistant', '1', 'test')
    return s


def said(s, text, poll=False, **patches):
    got = []
    with mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: got.append((body, poll))), \
         mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
         mock.patch.object(concierge, 'restore_current', return_value=None), \
         mock.patch.object(concierge, 'say', side_effect=AssertionError('a pick never reaches the model')):
        ra.respond(s, 'whatsapp', JID, text, None, poll=poll)
    return got


ITEM = {'key': 'msg:7', 'kind': 'message', 'mid': 7, 'title': 'The export job failed again'}


class PhoneAsksWhatFirst(unittest.TestCase):
    def offer(self, s):
        s.set_setting(f'{ra.OFFERED_KEY}:whatsapp:{JID}', json.dumps(['Send to agent', 'Next']), 't')
        s.set_setting(f'{ra.ACTS_KEY}:whatsapp:{JID}', json.dumps({'Send to agent': {'t': 'verb', 'verb': 'regular_agent', 'key': 'msg:7'}}), 't')

    def test_send_to_agent_asks_then_the_next_line_is_the_job(self):
        s = armed(); self.offer(s)
        with mock.patch.object(concierge, 'propose_direct') as pd, mock.patch.object(funnel, 'next_item', return_value=ITEM):
            got = said(s, 'Send to agent', poll=True)
        pd.assert_not_called()                                         # nothing starts at the tap
        self.assertIn('What should it do?', got[0][0])
        self.assertEqual(json.loads(s.get_setting(f'{ra.AGENT_KEY}:whatsapp:{JID}')), {'key': 'msg:7', 'verb': 'regular_agent'})
        prop = {'id': 'op9', 'status': 'proposed', 'verb': 'regular_agent', 'label': 'Send to agent', 'key': 'msg:7', 'settles': True,
                'alts': [{'verb': 'coding_agent'}], 'kind': 'task.create_from_message', 'params': {'kind': 'general'}}
        with mock.patch.object(concierge, 'propose_direct', return_value=prop) as pd, \
             mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'done'}) as run, \
             mock.patch.object(concierge, 'receipt', return_value='Handed off.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'All clear.', 'item': None}), \
             mock.patch.object(funnel, 'next_item', return_value=ITEM):
            said(s, 'the attachment is the wrong month')               # typed, or a voice note's words
        self.assertEqual(pd.call_args.args[1:3], ('regular_agent', 'msg:7'))
        self.assertEqual(pd.call_args.kwargs['text'], 'the attachment is the wrong month')
        self.assertTrue(pd.call_args.kwargs['exact'])
        run.assert_called_once()                                       # the words were the answer: no second question
        self.assertFalse(s.get_setting(f'{ra.AGENT_KEY}:whatsapp:{JID}'))

    def test_its_own_button_hands_it_over_as_it_is(self):
        s = armed(); self.offer(s)
        with mock.patch.object(funnel, 'next_item', return_value=ITEM):
            said(s, 'Send to agent', poll=True)
        prop = {'id': 'op9', 'status': 'proposed', 'verb': 'regular_agent', 'label': 'Send to agent', 'key': 'msg:7', 'settles': True, 'alts': []}
        with mock.patch.object(concierge, 'propose_direct', return_value=prop) as pd, \
             mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'done'}), \
             mock.patch.object(concierge, 'receipt', return_value='Handed off.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'All clear.', 'item': None}), \
             mock.patch.object(funnel, 'next_item', return_value=ITEM):
            said(s, 'Send to agent', poll=True)
        self.assertEqual(pd.call_args.kwargs['text'], '')
