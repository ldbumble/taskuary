"""How the assistant PRESENTS (PW-151 to PW-155): four fyi together with a summary for each, and an action on
one of them that reaches only that one; a single item with its whole grouped context, the task summary and
the checklist; the introduction written by the model per COUNSEL, with the facts as the fallback; and the
rule under all of it - presenting marks nothing read, runs nothing, moves nothing.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, funnel, general, ingest, operations, server, terminal
from taskuary.store import MemoryStore


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('coder_auto_enabled', '1', 't'); s.set_setting('team_domains', 'ours.com', 't'); s.set_setting('owner_email', 'owner@ours.com', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._SOURCES.update(at=0.0, by={})
    return s


def brain(intent='task', kind='coding'):
    def llm(system, user, **kw):
        out = {'intent': intent, 'why': 'because'}
        if intent == 'task' and kind: out['kind'] = kind
        return json.dumps(out)
    return llm


def arrive(s, subject, body, who='Chana', email='chana@ours.com', hours=1, llm=None, conv=None):
    msg = {'external_id': f'x:{subject}', 'channel': 'email', 'conversation_id': conv or f'c:{subject}', 'subject': subject, 'from_name': who,
           'from_email': email, 'sent_at': ago(hours), 'body': body, 'to': ['owner@ours.com'], 'source_name': 'owner@ours.com'}
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, msg, llm=llm or brain('fyi', None))


def five_fyi(s):
    return [arrive(s, f'FYI {n} - {t}', f'Just so you know: {t}.', hours=5 - n)
            for n, t in enumerate(('Rebecca is back Tuesday', 'lunch moved to Thursday', 'the printer is fixed', 'parking lot closed Friday', 'new badge photos'))]


def quiet(): return mock.patch.object(terminal, 'live_sessions', return_value=[])


def client(s):
    return TestClient(server.app)


class FyiHandfulTests(unittest.TestCase):
    def test_four_come_together_each_with_its_own_summary_from_the_model(self):
        s = store(); got = five_fyi(s)
        seen = {}
        def model(system, user, **kw):
            seen['system'], seen['user'] = system, user
            return '1. Chana says Rebecca is back Tuesday.\n2. Chana moved lunch to Thursday.\n3. Chana says the printer is fixed.\n4. Chana warns the lot is closed Friday.'
        with quiet(): out = concierge.surface(s, llm=model)
        card = out['item']
        self.assertEqual((card['kind'], len(card['items']), out['left']), ('fyis', 4, 1))
        self.assertEqual([i['summary'] for i in card['items']],
                         ['Chana says Rebecca is back Tuesday.', 'Chana moved lunch to Thursday.', 'Chana says the printer is fixed.', 'Chana warns the lot is closed Friday.'])
        self.assertIn('I am Taskuary', seen['system'])                                          # COUNSEL is the voice
        self.assertIn('exactly 4 numbered lines', seen['user'])                                   # the shape is code's
        # the summaries survive a refresh: the pile's own batch carries them (they ride on the shown-state)
        again = funnel.batch_item(s, card['key'])
        self.assertEqual([i['summary'] for i in again['items']], [i['summary'] for i in card['items']])
        # ...and without a model, or with an answer the shape does not fit, each entry keeps its gist
        s2 = store(); five_fyi(s2)
        with quiet(), mock.patch.object(concierge, 'brain', return_value=None): out2 = concierge.surface(s2)
        self.assertTrue(all(i['summary'] == i['preview'] for i in out2['item']['items']))
        self.assertIn('4 things people told you', out2['say'])

    def test_an_action_on_one_entry_reaches_that_one_and_its_siblings_stay_unread(self):
        s = store(); got = five_fyi(s)
        with quiet(), mock.patch.object(concierge, 'brain', return_value=None): card = concierge.surface(s)['item']
        first, second = card['items'][0], card['items'][1]
        with mock.patch.object(server, 'store', s), quiet():
            c = client(s)
            p = c.post('/api/concierge/propose', json={'verb': 'mine', 'key': first['key']}).json()
            self.assertEqual((p['kind'], p['target'], p['params']['kind'], p['settles'], p['label']),
                             ('task.create_from_message', first['mid'], 'task', False, 'Put it on my list'))
            self.assertIsNone(s.get_message(first['mid'])['TaskId'])                             # proposed, not done
            r = c.post(f"/api/operations/{p['id']}/execute", json={'version': p['version']}).json()
            self.assertEqual(r['status'], 'done')
        self.assertTrue(s.get_message(first['mid'])['TaskId'])                                   # that one is a task now
        self.assertEqual(s.get_message(second['mid'])['Status'], 'filed')                          # its sibling is untouched...
        states = s.funnel_states()
        self.assertEqual({states[i['key']]['Status'] for i in card['items'][1:]}, {'surfaced'})    # ...shown, not read
        self.assertTrue(all(any(x.get('mid') == i['mid'] for x in funnel.build(s, keep_surfaced=True)['items']) for i in card['items'][1:]))
        # the agent roads on an entry are the same proposals, with the kind in them
        with mock.patch.object(server, 'store', s), quiet():
            c = client(s)
            self.assertEqual(c.post('/api/concierge/propose', json={'verb': 'coder', 'key': second['key']}).json()['params']['kind'], 'coding')
            self.assertEqual(c.post('/api/concierge/propose', json={'verb': 'regular_agent', 'key': second['key']}).json()['params']['kind'], 'general')
            self.assertEqual(c.post('/api/concierge/propose', json={'verb': 'juggle', 'key': second['key']}).status_code, 422)
            self.assertEqual(c.post('/api/concierge/propose', json={'verb': 'mine', 'key': 'msg:999'}).status_code, 422)
        self.assertEqual(s.get_message(second['mid'])['Status'], 'filed')                          # three proposals, no effect

    def test_reply_on_one_entry_drafts_at_once_and_marks_nothing(self):
        s = store(); got = five_fyi(s)
        with quiet(), mock.patch.object(concierge, 'brain', return_value=None): card = concierge.surface(s)['item']
        first = card['items'][0]
        with mock.patch.object(server, 'store', s), quiet(), mock.patch('taskuary.responder.draft_for_message', return_value='Welcome back, Rebecca!'), \
             mock.patch('taskuary.outbound.reply_to_message') as send:
            r = client(s).post(f"/api/messages/{first['mid']}/reply", json={'draft': True}).json()
        self.assertTrue(r['reviewId']); self.assertEqual(s.get_review(r['reviewId'])['Status'], 'pending')
        send.assert_not_called()
        self.assertEqual({s.funnel_states()[i['key']]['Status'] for i in card['items']}, {'surfaced'})


class SingleItemTests(unittest.TestCase):
    def test_the_card_reaches_the_whole_grouped_context_the_task_summary_and_the_checklist(self):
        s = store()
        first = arrive(s, 'Reorder the seven steps', 'Step one goes last.', who='Gabi', email='gabi@ours.com', hours=3, llm=brain('task', 'coding'), conv='c:steps')
        tid = first['task_id']
        s.add_message({'TaskId': tid, 'ExternalId': 'x:two', 'ConversationId': 'c:steps', 'Channel': 'email', 'Subject': 'RE: Reorder the seven steps',
                       'FromName': 'Gabi', 'FromEmail': 'gabi@ours.com', 'SentAt': ago(2), 'BodyText': 'And step four before three.', 'Status': 'routed'})
        s.add_message({'TaskId': tid, 'ExternalId': 'x:ctx', 'ConversationId': 'c:steps', 'Channel': 'email', 'Subject': 'RE: Reorder the seven steps',
                       'FromName': 'You', 'FromEmail': 'owner@ours.com', 'SentAt': ago(1), 'BodyText': 'Noted.', 'Status': 'context'})
        s.update_task(tid, {'Summary': 'Gabi wants the onboarding steps reordered: one last, four before three.'}, 'owner')
        s.set_task_checklist(tid, ['Move step one to the end', 'Put step four before three'], 'triage')
        with quiet(): out = concierge.surface(s, llm=lambda *a, **k: 'never asked')
        card = out['item']
        self.assertEqual((card['tid'], bool(card['mid'])), (tid, True))                          # the card can fetch the task
        with mock.patch.object(server, 'store', s), quiet(): d = client(s).get(f'/api/tasks/{tid}').json()
        self.assertEqual([m['BodyText'] for m in d['messages'] if m.get('Status') != 'context'], ['Step one goes last.', 'And step four before three.'])
        self.assertIn('one last, four before three', d['task']['Summary'])
        self.assertEqual([c['text'] for c in d['checklist']], ['Move step one to the end', 'Put step four before three'])
        with quiet(): fx = concierge.facts(s, card)
        self.assertIn('TRIAGE COMBINED THESE 2 MESSAGES', fx); self.assertIn('step four before three', fx)   # the model has it all too


class CounselIntroductionTests(unittest.TestCase):
    def _asked(self):
        s = store()
        out = arrive(s, 'Can you fix the export?', 'The nightly export drops inter-company rows.', who='Craig', email='craig@vendor.com', llm=brain('task', 'coding'))
        return s, out

    def test_the_introduction_is_the_models_per_counsel_and_the_beats_are_not_dictated(self):
        s, out = self._asked()
        seen = {}
        def model(system, user, **kw):
            seen['system'], seen['user'] = system, user
            return 'Craig at the vendor says the nightly export drops inter-company rows - a coding fix. Send it to the coding agent, or reply first?'
        self.assertTrue(concierge.INTRO_AI)
        with quiet(): said = concierge.surface(s, llm=model)
        self.assertTrue(said['say'].startswith('Craig at the vendor says'))
        self.assertIn('I am Taskuary', seen['system']); self.assertIn('THE CONTRACT', seen['system'])   # COUNSEL, then the contract code reads
        self.assertNotIn('THREE BEATS', seen['user']); self.assertNotIn('name the button', seen['user'])
        self.assertIn('Introduce the item on the table', seen['user'])
        self.assertIn('what they wrote:', seen['user'])                                             # code supplies the verified context

    def test_the_facts_are_the_fallback_not_the_normal_path(self):
        s, out = self._asked()
        with quiet(), mock.patch.object(concierge, 'brain', return_value=None): no = concierge.surface(s)
        self.assertIn('Craig wrote on email', no['say'])                                            # no AI: the facts
        s, out = self._asked()
        with quiet(): broke = concierge.surface(s, llm=lambda *a, **k: "I'm in Claude Code, so I don't have access to the queue.")
        self.assertIn('Craig wrote on email', broke['say'])                                         # out of character: the facts
        s, out = self._asked()
        with quiet(): off = concierge.surface(s, llm=lambda *a, **k: 'Mindy asked to deploy gpt-4.1 (TQ-0312).')
        self.assertIn('Craig wrote on email', off['say'])                                           # another subject: the facts


class PresentingMarksNothingTests(unittest.TestCase):
    def test_a_single_item_shown_is_not_read_handled_or_acted_on(self):
        s = store()
        out = arrive(s, 'Can you fix the export?', 'Rows drop.', who='Craig', email='craig@vendor.com', llm=brain('task', 'coding'))
        tid = out['task_id']
        with quiet(): card = concierge.surface(s, llm=lambda *a, **k: 'Craig wants the export fixed.')['item']
        self.assertEqual(s.funnel_states()[card['key']]['Status'], 'surfaced')
        with quiet(): self.assertEqual(funnel.next_item(s, card['key'], include_surfaced=True)['key'], card['key'])   # still on the table
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        self.assertEqual(s.get_message(out['message_id'])['Status'], 'routed')
        self.assertEqual([h['type'] for h in operations.history(s, task_id=tid)], ['discussion'])   # what was said is kept (PW-132)
        self.assertEqual([h for h in operations.history(s, task_id=tid) if h['type'] != 'discussion'], [])   # nothing proposed, nothing run
        dock = general.dock_task(s)[0]['TaskId']
        self.assertEqual([h['role'] for h in concierge.history(s, dock)], ['assistant'])             # one line, no receipt, no move

    def test_a_handful_shown_is_not_read_either(self):
        s = store(); got = five_fyi(s)
        with quiet(), mock.patch.object(concierge, 'brain', return_value=None): card = concierge.surface(s)['item']
        self.assertEqual({s.funnel_states()[i['key']]['Status'] for i in card['items']}, {'surfaced'})
        self.assertEqual({s.get_message(i['mid'])['Status'] for i in card['items']}, {'filed'})
        self.assertEqual(len(funnel.build(s, keep_surfaced=True)['items']), 5)                       # all five still unread
        self.assertEqual(operations.history(s, message_id=card['items'][0]['mid']), [])


if __name__ == '__main__':
    unittest.main()
