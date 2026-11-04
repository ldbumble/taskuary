"""The owner's exact words under YOU, never the Assistant's rewording (the owner, 2026-11-04).

Answered through the bottom box, "Go with option B, three years." reached the agent's chat as "Option B: book the 3-year renewal at
6,000." under YOU - the Assistant's version of it. The owner's words go under YOU as typed; whatever the Assistant adds - its context,
its rephrase - is Taskuary's, folded with its other instructions. The agent is handed both."""
import time, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, general, server, terminal, waitroom, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

OWNER, RELAY = 'Go with option B, three years.', 'Option B: book the 3-year PhishGuard renewal at 6,000.'


def said(s, tid):
    "the chat's user rows, as the pane reads them: (Taskuary or the owner, the words)"
    return [('taskuary' if general.is_brief(c) else c['Actor'], c['Body']) for c in s.list_comments(tid) if c['ActorType'] == general.USER_TYPE]


class Chat:
    "A live general session's chat: it keeps what it is handed."
    def __init__(self, s, tid): self.store, self.task_id, self.sid, self.alive, self.buf, self.sent = s, tid, 'g', True, '', []
    def send_prompt(self, text, **kw): self.sent.append((text, kw))
    def waiting(self): return True


def test_relayed_is_only_what_the_assistant_added():
    assert general.relayed(OWNER, RELAY) == RELAY
    assert general.relayed(OWNER, '  go with option b,  three years. ') == ''           # the same words: nothing added
    assert general.relayed('', RELAY) == ''                                               # no owner's words to keep: nothing to split


def test_an_answer_puts_the_owners_words_under_you_and_folds_the_rest():
    s = MemoryStore(); tid = Factory(s).task(title='PhishGuard renewal', kind='general', status='in_progress'); chat = Chat(s, tid)
    general.say_relayed(chat, OWNER, RELAY)
    assert said(s, tid) == [('owner', OWNER), ('taskuary', f'{general.RELAY} {RELAY}')]
    [(turn, kw)] = chat.sent
    assert turn == f'FROM THE OWNER: {OWNER}\n\n{general.RELAY} {RELAY}' and kw == {'kept': True, 'brief': True}
    # ...and the same words, nothing added, are the owner's turn as before
    s2 = MemoryStore(); t2 = Factory(s2).task(title='x', kind='general', status='in_progress'); c2 = Chat(s2, t2)
    general.say_relayed(c2, OWNER, OWNER)
    assert c2.sent == [(OWNER, {})] and said(s2, t2) == []                                 # send_prompt files it, as it always did


def test_the_answer_door_hands_the_owners_words_on():
    s = MemoryStore(); tid = Factory(s).task(title='PhishGuard renewal', kind='general', status='in_progress'); chat = Chat(s, tid)
    ws.record(s, tid, 'g', 'working'); ws.record(s, tid, 'g', 'input_needed', text='Which option should Marcus book?')
    with mock.patch.dict(terminal.SESSIONS, {'g': chat}, clear=True):
        out = ws.answer_open(s, tid, RELAY, 'owner', owner=OWNER)
    assert out['delivered'] and said(s, tid)[0] == ('owner', OWNER) and chat.sent[0][0].startswith(f'FROM THE OWNER: {OWNER}')


def test_a_note_held_for_a_working_agent_keeps_both_and_files_them_apart():
    s = MemoryStore(); tid = Factory(s).task(title='Vendor list', kind='general', status='in_progress')
    chat = Chat(s, tid)
    with mock.patch.dict(terminal.SESSIONS, {'g': chat}, clear=True), mock.patch.object(waitroom, 'state', return_value=('parked', chat)), \
         mock.patch.object(general, 'GeneralSession', Chat):        # the parked chat is a general agent's (waitroom.to_general)
        out = waitroom.add(s, tid, 'Also add Northwind Payroll to vendors-2026.txt, sorted in.', owner='Also put Northwind Payroll on the list, please.')
        time.sleep(0.3)
    assert out['delivered'] == 1
    rows = said(s, tid)
    assert rows[-1] == ('owner', 'Also put Northwind Payroll on the list, please.')
    assert rows[0][0] == 'taskuary' and 'Also add Northwind Payroll to vendors-2026.txt' in rows[0][1]
    assert 'Also put Northwind Payroll on the list, please.' in chat.sent[0][0] and 'sorted in' in chat.sent[0][0]


class AssistantDoors(unittest.TestCase):
    def test_the_assistant_passes_the_typed_words_with_its_version(self):
        s = MemoryStore(); tid = Factory(s).task(title='PhishGuard renewal', kind='general', status='in_progress')
        seen = []
        with mock.patch.object(concierge, 'run_proposal', side_effect=lambda st, op, a: (seen.append(op['params']), {'status': 'done', 'outcome': {'delivered': True}})[1]):
            concierge._answer_now(s, general.dock_task(s, 'owner')[0]['TaskId'], None, tid, RELAY, 'owner', owner=OWNER)
        self.assertEqual(seen, [{'text': RELAY, 'owner': OWNER}])

    def test_continue_from_the_box_files_the_owners_note_and_folds_the_assistants(self):
        s = MemoryStore(); tid = s.create_task({'Title': 'Vendor notes', 'Kind': 'general', 'Status': 'open'}, 'router')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Wrote two of five.')
        ses = Chat(s, tid)
        with mock.patch.object(server, 'store', s), mock.patch.object(general, 'start_session', return_value=ses), \
             mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude'}]):
            r = TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'carry on, skip the zip', 'context': 'Carry on; leave q3-receipts.zip out.'})
            self.assertEqual(r.status_code, 200, r.text)
            time.sleep(0.3)
        rows = said(s, tid)
        self.assertIn(('owner', 'carry on, skip the zip'), rows)
        self.assertTrue(any(w == 'taskuary' and f'{general.RELAY} Carry on; leave q3-receipts.zip out.' in b for w, b in rows))
