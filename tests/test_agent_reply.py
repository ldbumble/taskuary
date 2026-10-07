"""The agent that did the work can write the reply itself, and that reply is the one kept.

An agent finished, asked "should I draft the reply to Dana?", the owner said yes, and it wrote a good
one on its own screen - where the task's reply never saw it. The end of the run then had a second
model redraft the answer from the transcript (the owner, 2026-09-23: "sometimes the agent that did
the work is better for response than another ai generating it based off of transcript"). Now the
agent hands it over - `taskuary --reply` from a shell, a [[TASKUARY-REPLY]] block from the general
chat - it becomes the task's pending reply as written, and finishing keeps it.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import coder, selfclose, server
from taskuary.store import MemoryStore

REP = {'summary': 'fixed the export', 'outcome': 'did_work', 'determination': '', 'actions': ''}
OWN = 'Hi Dana - the August export was dropping rows over 10k; fixed and re-run, the file is in the share now.'


def task_with(s, inbound=True):
    tid = s.create_task({'Title': 'August export', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'x-1', 'ConversationId': 'AAQk-x', 'Channel': 'email',
                         'SourceName': 'alex@northwind.example', 'Subject': 'August export', 'FromName': 'Dana',
                         'FromEmail': 'dana@vendor.example', 'SentAt': '2026-09-06 09:00:00',
                         'BodyText': 'Could you fix the August export?', 'Status': 'routed' if inbound else 'context'})
    return tid, mid


def kept(s, tid):
    from taskuary import session_artifacts
    a = [a for a in s.list_task_artifacts(tid) if a['Kind'] == 'agent_result']
    return session_artifacts.confined(a[0]['Path']).read_text(encoding='utf-8') if a else ''


class NoHook(unittest.TestCase):
    def setUp(self): self._prev, coder.REFRESH = coder.REFRESH, None
    def tearDown(self): coder.REFRESH = self._prev


class AgentReplyTests(NoHook):
    def test_the_agents_reply_is_the_tasks_pending_reply(self):
        s = MemoryStore(); tid, mid = task_with(s)
        out = coder.agent_reply(s, tid, OWN, 'coder')
        rv = s.get_review(out['review_id'])
        self.assertEqual((rv['Status'], rv['DraftText'], rv['DraftBy'], rv['MessageId']), ('pending', OWN, 'agent:coder', mid))

    def test_finishing_keeps_it_and_no_second_model_redrafts(self):
        s = MemoryStore(); tid, _ = task_with(s)
        coder.agent_reply(s, tid, OWN, 'coder')
        with mock.patch('taskuary.responder.write_draft') as redraft:
            out = coder.finish(s, tid, REP, None, 'coder')
        redraft.assert_not_called()
        self.assertTrue(out['drafting'])
        rvs = s.list_reviews('pending')
        self.assertEqual(len(rvs), 1); self.assertEqual(rvs[0]['DraftText'], OWN)
        self.assertIn("coder's own reply", rvs[0]['Reason'])

    def test_without_one_the_responder_drafts_as_before(self):
        s = MemoryStore(); tid, _ = task_with(s)
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.') as redraft:
            coder.finish(s, tid, REP, None, 'coder')
        redraft.assert_called_once()

    def test_a_triage_draft_held_for_the_session_is_the_one_it_fills(self):
        s = MemoryStore(); tid, mid = task_with(s)
        held = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'held', 'Reason': 'held while the agent works'})
        out = coder.agent_reply(s, tid, OWN, 'coder')
        self.assertEqual(out['review_id'], held)
        self.assertEqual(s.get_review(held)['Status'], 'pending')
        self.assertEqual(len([r for r in s.list_reviews('pending') if r['TaskId'] == tid]), 1)

    def test_an_ai_redraft_takes_the_mark_off_so_finishing_redrafts_again(self):
        s = MemoryStore(); tid, _ = task_with(s)
        rid = coder.agent_reply(s, tid, OWN, 'coder')['review_id']
        s.update_review_draft(rid, 'An AI rewrite.', None)                       # "Draft with AI" pressed
        self.assertFalse(coder.agent_drafted(s.get_review(rid)))

    def test_nobody_to_answer_keeps_it_as_the_result(self):
        s = MemoryStore(); tid, _ = task_with(s, inbound=False)
        out = coder.agent_reply(s, tid, OWN, 'coder')
        self.assertEqual((out['ok'], out['saved']), (True, 'result')); self.assertEqual(s.list_reviews('pending'), [])
        self.assertIn(OWN, kept(s, tid))

    def test_work_the_owner_started_has_nobody_to_reply_to(self):
        """A brief typed in the chat is the task's only message ('own', from You): the agent's checklist was
        filed as a reply "waiting on your approval", addressed to the owner themself (2026-09-23)."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'AP clerk checklist', 'Kind': 'general', 'Status': 'in_progress'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': 'own-1', 'Channel': 'own', 'Subject': 'AP clerk checklist',
                       'FromName': 'You', 'BodyText': 'write a short checklist', 'Status': 'routed'})
        out = coder.agent_reply(s, tid, OWN, 'assistant')
        self.assertEqual(s.list_reviews('pending'), [])
        # ...but the answer is what the owner asked for: refusing it threw a whole review away (2026-10-06)
        self.assertEqual(out['saved'], 'result'); self.assertIn(OWN, kept(s, tid))

    def test_the_run_record_carries_the_answer(self):
        from taskuary import session_artifacts
        s = MemoryStore(); tid, _ = task_with(s, inbound=False)
        coder.agent_reply(s, tid, OWN, 'coder')
        art = session_artifacts.coding(s, tid, 'Summary: reviewed it', 'transcript', final_message='Saved the reply file.')
        body = session_artifacts.confined(art['Path']).read_text(encoding='utf-8')
        self.assertLess(body.index(OWN), body.index('## Session result'))

    def test_the_shell_door(self):
        s = MemoryStore(); tid, _ = task_with(s)
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post('/api/agent/reply', json={'task_id': tid, 'text': OWN, 'agent': 'claude'})
        self.assertTrue(r.json()['ok'])
        self.assertEqual(s.list_reviews('pending')[0]['DraftBy'], 'agent:claude')

    def test_the_seed_tells_every_session_how(self):
        self.assertIn('taskuary --reply', selfclose.SEED_LINE); self.assertIn('--attach', selfclose.SEED_LINE)


def envelope(s, rid):
    import json
    return json.loads(s.get_review(rid).get('Deliver') or '{}').get('attachments') or []


class AttachTests(NoHook):
    """A session rebuilt a workbook and wrote "the list is attached (review.xlsx)" - and the reply carried
    nothing, because --reply took words only. The file it made now rides on the same review."""
    XLSX = b'PK\x03\x04 a workbook'

    def test_the_file_rides_with_the_reply(self):
        s = MemoryStore(); tid, _ = task_with(s)
        out = coder.agent_reply(s, tid, 'Hi Dana - the list is attached.', 'coder', files=[('review.xlsx', self.XLSX)])
        self.assertEqual(out['attached'], ['review.xlsx'])
        (f,) = envelope(s, out['review_id'])
        self.assertEqual((f['name'], f['size']), ('review.xlsx', len(self.XLSX)))

    def test_attach_alone_adds_to_the_reply_already_saved(self):
        s = MemoryStore(); tid, _ = task_with(s)
        rid = coder.agent_reply(s, tid, OWN, 'coder')['review_id']
        out = coder.agent_reply(s, tid, '', 'coder', files=[('review.xlsx', self.XLSX)])
        self.assertEqual(out['review_id'], rid); self.assertEqual(s.get_review(rid)['DraftText'], OWN)
        self.assertEqual([f['name'] for f in envelope(s, rid)], ['review.xlsx'])

    def test_attach_alone_with_no_reply_says_so(self):
        s = MemoryStore(); tid, _ = task_with(s)
        out = coder.agent_reply(s, tid, '', 'coder', files=[('review.xlsx', self.XLSX)])
        self.assertFalse(out['ok']); self.assertIn('--reply', out['why'])

    def test_a_file_that_cannot_ride_says_why(self):
        s = MemoryStore(); tid, _ = task_with(s)
        out = coder.agent_reply(s, tid, OWN, 'coder', files=[('empty.csv', b'')])
        self.assertEqual(out['attached'], []); self.assertIn('empty.csv', out['not_attached'][0])

    def test_the_shell_door_carries_bytes_not_a_path(self):
        import base64
        s = MemoryStore(); tid, _ = task_with(s)
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post('/api/agent/reply', json={'task_id': tid, 'text': OWN, 'agent': 'claude',
                                                                      'files': [{'name': 'review.xlsx', 'data': base64.b64encode(self.XLSX).decode()}]})
        self.assertEqual(r.json()['attached'], ['review.xlsx'])
        with open(envelope(s, r.json()['review_id'])[0]['path'], 'rb') as fh: self.assertEqual(fh.read(), self.XLSX)


class ChatAttachTests(NoHook):
    """The chat (an API brain, or a CLI answering in the chat) has no `--attach` it can use - it names the file in
    its reply, and only its working folder or a file the turn was handed may go to an outside recipient."""
    def setUp(self):
        super().setUp()
        import tempfile
        from pathlib import Path
        self.home = Path(tempfile.mkdtemp()); (self.home / 'scratch').mkdir()
        self._p = mock.patch('taskuary.config.home', return_value=self.home); self._p.start()

    def tearDown(self): self._p.stop(); super().tearDown()

    def test_the_line_comes_out_of_the_reply_and_names_the_path(self):
        text = f'Done.\n{selfclose.REPLY_OPEN}\n{OWN}\n[[TASKUARY-ATTACH: C:\\work\\review list.xlsx]]\n{selfclose.REPLY_CLOSE}'
        rest, named = selfclose.attach_markers(text)
        self.assertEqual(named, ['C:\\work\\review list.xlsx'])
        self.assertEqual(selfclose.reply_marker(rest)[1], OWN)

    def test_a_file_from_the_working_folder_rides(self):
        from taskuary import general
        f = self.home / 'scratch' / 'review.xlsx'; f.write_bytes(b'xlsx')
        s = MemoryStore(); tid, _ = task_with(s)
        self.assertEqual(general._files_to_attach(s, tid, [str(f)], []), [('review.xlsx', b'xlsx')])

    def test_a_file_the_turn_was_handed_rides(self):
        from taskuary import general
        f = self.home / 'in.pdf'; f.write_bytes(b'pdf')
        s = MemoryStore(); tid, _ = task_with(s)
        self.assertEqual(general._files_to_attach(s, tid, [str(f)], [str(f)]), [('in.pdf', b'pdf')])

    def test_any_other_path_is_refused_and_the_task_says_so(self):
        from taskuary import general
        f = self.home / 'secret.key'; f.write_bytes(b'k')
        s = MemoryStore(); tid, _ = task_with(s)
        self.assertEqual(general._files_to_attach(s, tid, [str(f)], []), [])
        self.assertTrue(any('Not attached' in str(c.get('Body')) for c in s.list_comments(tid)))

    def test_every_chat_brain_is_told(self):
        self.assertIn('TASKUARY-ATTACH', selfclose.REPLY_LINE)

    def test_a_chat_turn_puts_the_file_on_the_reply_and_keeps_the_marker_out_of_it(self):
        import json
        from taskuary import general
        f = self.home / 'scratch' / 'review.xlsx'; f.write_bytes(b'xlsx')
        s = MemoryStore(); tid, _ = task_with(s)
        answer = f'Here it is.\n{selfclose.REPLY_OPEN}\n{OWN}\n[[TASKUARY-ATTACH: {f}]]\n{selfclose.REPLY_CLOSE}'
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
            sess = general.GeneralSession(s, tid)
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda system, user, **kw: answer):
            shown = sess.send_prompt('send Dana the list')
        self.assertNotIn('TASKUARY-ATTACH', shown)
        (rv,) = [r for r in s.list_reviews('pending') if r['TaskId'] == tid]
        self.assertEqual(rv['DraftText'], OWN)
        self.assertEqual([a['name'] for a in json.loads(rv['Deliver'])['attachments']], ['review.xlsx'])


class ChatBlockTests(unittest.TestCase):
    def test_the_marked_block_is_the_reply_and_stays_readable(self):
        text, said = selfclose.reply_marker(f'Done - here is what I would send.\n[[TASKUARY-REPLY]]\n{OWN}\n[[/TASKUARY-REPLY]]')
        self.assertEqual(said, OWN)
        self.assertNotIn('TASKUARY', text); self.assertIn(OWN, text)

    def test_no_block_no_reply(self):
        self.assertEqual(selfclose.reply_marker('Should I draft the reply to Dana?'), ('Should I draft the reply to Dana?', None))


def test_a_missing_reply_file_is_one_plain_line_not_a_traceback(monkeypatch, capsys):
    from taskuary import cli
    monkeypatch.setenv('TASKUARY_TASK', '1')
    monkeypatch.setattr('sys.argv', ['taskuary', '--reply-file', 'does-not-exist.txt'])
    cli.main()
    assert capsys.readouterr().out.strip() == 'not saved: cannot read does-not-exist.txt: No such file or directory'


def test_an_undecodable_reply_file_says_why(monkeypatch, capsys, tmp_path):
    from taskuary import cli
    f = tmp_path/'reply.txt'; f.write_bytes(bytes([0xff, 0xfe, 0x80]))
    monkeypatch.setenv('TASKUARY_TASK', '1')
    monkeypatch.setattr('sys.argv', ['taskuary', '--reply-file', str(f)])
    cli.main()
    assert capsys.readouterr().out.startswith(f'not saved: cannot read {f}: ')


if __name__ == '__main__':
    unittest.main()
