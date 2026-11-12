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

from taskuary import wrapup, selfclose, server
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
    def setUp(self): self._prev, wrapup.REFRESH = wrapup.REFRESH, None
    def tearDown(self): wrapup.REFRESH = self._prev


class AgentReplyTests(NoHook):
    def test_the_agents_reply_is_the_tasks_pending_reply(self):
        s = MemoryStore(); tid, mid = task_with(s)
        out = wrapup.agent_reply(s, tid, OWN, 'coding')
        rv = s.get_review(out['review_id'])
        self.assertEqual((rv['Status'], rv['DraftText'], rv['DraftBy'], rv['MessageId']), ('pending', OWN, 'agent:coding', mid))

    def test_finishing_keeps_it_and_no_second_model_redrafts(self):
        s = MemoryStore(); tid, _ = task_with(s)
        wrapup.agent_reply(s, tid, OWN, 'coding')
        with mock.patch('taskuary.responder.write_draft') as redraft:
            out = wrapup.finish(s, tid, REP, None, 'coding')
        redraft.assert_not_called()
        self.assertTrue(out['drafting'])
        rvs = s.list_reviews('pending')
        self.assertEqual(len(rvs), 1); self.assertEqual(rvs[0]['DraftText'], OWN)
        self.assertIn("coding's own reply", rvs[0]['Reason'])

    def test_without_one_no_writer_drafts_it_and_it_waits_owed(self):
        """The owner, 2026-11-10: "no more triage creates draft. agent should be doing it" - at a run's end too."""
        s = MemoryStore(); tid, _ = task_with(s)
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed.') as redraft:
            out = wrapup.finish(s, tid, REP, None, 'coding')
        redraft.assert_not_called()
        rv = s.get_review(out['owed'])
        self.assertEqual((rv['Status'], rv.get('DraftText') or ''), ('pending', ''))

    def test_a_reply_that_already_went_out_is_not_put_back_on_the_table(self):
        # a resumed session saved its first session's reply again after the owner had sent it, and the sender's "Thanks!"
        # got the same letter queued as a new draft (2026-10-16) - Send would have sent it twice
        s = MemoryStore(); tid, mid = task_with(s)
        rid = wrapup.agent_reply(s, tid, OWN, 'coding')['review_id']
        s._exec("UPDATE review SET Status='approved', FinalText=?, DecidedBy='owner', DecidedAt='2026-09-06 10:00:00' WHERE ReviewId=?", (OWN, rid))
        s.add_message({'TaskId': tid, 'ExternalId': 'x-2', 'ConversationId': 'AAQk-x', 'Channel': 'email', 'FromName': 'Dana',
                       'FromEmail': 'dana@vendor.example', 'SentAt': '2026-09-06 11:00:00', 'BodyText': 'Thanks!', 'Status': 'routed'})
        out = wrapup.agent_reply(s, tid, '  ' + OWN.replace(' - ', '  -  ') + chr(10), 'coding')     # the same words, spaced differently
        self.assertFalse(out['ok']); self.assertTrue(out.get('already_sent'))
        self.assertIn('already went out', out['why'])
        self.assertEqual([r for r in s.list_reviews('pending') if r['TaskId'] == tid], [])
        # ...and a different reply is still saved as usual
        self.assertTrue(wrapup.agent_reply(s, tid, 'Glad it helped, Dana.', 'coding')['ok'])

    def test_a_triage_draft_held_for_the_session_is_the_one_it_fills(self):
        s = MemoryStore(); tid, mid = task_with(s)
        held = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'held', 'Reason': 'held while the agent works'})
        out = wrapup.agent_reply(s, tid, OWN, 'coding')
        self.assertEqual(out['review_id'], held)
        self.assertEqual(s.get_review(held)['Status'], 'pending')
        self.assertEqual(len([r for r in s.list_reviews('pending') if r['TaskId'] == tid]), 1)

    def test_an_ai_redraft_takes_the_mark_off_so_finishing_redrafts_again(self):
        s = MemoryStore(); tid, _ = task_with(s)
        rid = wrapup.agent_reply(s, tid, OWN, 'coding')['review_id']
        s.update_review_draft(rid, 'An AI rewrite.', None)                       # "Draft with AI" pressed
        self.assertFalse(wrapup.agent_drafted(s.get_review(rid)))

    def test_nobody_to_answer_keeps_it_as_the_result(self):
        s = MemoryStore(); tid, _ = task_with(s, inbound=False)
        out = wrapup.agent_reply(s, tid, OWN, 'coding')
        self.assertEqual((out['ok'], out['saved']), (True, 'result')); self.assertEqual(s.list_reviews('pending'), [])
        self.assertIn(OWN, kept(s, tid))

    def test_work_the_owner_started_has_nobody_to_reply_to(self):
        """A brief typed in the chat is the task's only message ('own', from You): the agent's checklist was
        filed as a reply "waiting on your approval", addressed to the owner themself (2026-09-23)."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'AP clerk checklist', 'Kind': 'general', 'Status': 'in_progress'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': 'own-1', 'Channel': 'own', 'Subject': 'AP clerk checklist',
                       'FromName': 'You', 'BodyText': 'write a short checklist', 'Status': 'routed'})
        out = wrapup.agent_reply(s, tid, OWN, 'assistant')
        self.assertEqual(s.list_reviews('pending'), [])
        # ...but the answer is what the owner asked for: refusing it threw a whole review away (2026-10-06)
        self.assertEqual(out['saved'], 'result'); self.assertIn(OWN, kept(s, tid))

    def test_the_run_record_carries_the_answer(self):
        from taskuary import session_artifacts
        s = MemoryStore(); tid, _ = task_with(s, inbound=False)
        wrapup.agent_reply(s, tid, OWN, 'coding')
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
        out = wrapup.agent_reply(s, tid, 'Hi Dana - the list is attached.', 'coding', files=[('review.xlsx', self.XLSX)])
        self.assertEqual(out['attached'], ['review.xlsx'])
        (f,) = envelope(s, out['review_id'])
        self.assertEqual((f['name'], f['size']), ('review.xlsx', len(self.XLSX)))

    def test_attach_alone_adds_to_the_reply_already_saved(self):
        s = MemoryStore(); tid, _ = task_with(s)
        rid = wrapup.agent_reply(s, tid, OWN, 'coding')['review_id']
        out = wrapup.agent_reply(s, tid, '', 'coding', files=[('review.xlsx', self.XLSX)])
        self.assertEqual(out['review_id'], rid); self.assertEqual(s.get_review(rid)['DraftText'], OWN)
        self.assertEqual([f['name'] for f in envelope(s, rid)], ['review.xlsx'])

    def test_attach_alone_with_no_reply_says_so(self):
        s = MemoryStore(); tid, _ = task_with(s)
        out = wrapup.agent_reply(s, tid, '', 'coding', files=[('review.xlsx', self.XLSX)])
        self.assertFalse(out['ok']); self.assertIn('--reply', out['why'])

    def test_a_file_that_cannot_ride_says_why(self):
        s = MemoryStore(); tid, _ = task_with(s)
        out = wrapup.agent_reply(s, tid, OWN, 'coding', files=[('empty.csv', b'')])
        self.assertEqual(out['attached'], []); self.assertIn('empty.csv', out['not_attached'][0])

    # THREE NAMED, TWO RIDE (2026-11-04): an agent built three reports with long, near-identical names and wrote "here are the three"; the
    # third was over the mailbox's cap, so it was refused - said only in a comment under the agent's pane, while Close out showed two chips
    # and nothing more. The refusal now rides on the envelope, by name and why, where the card draws the files, and the draft keeps the
    # names the agent handed over, so the card can count them against what is attached.
    THREE = [('_ Summary - Erin_ Gail_ Paula.xlsx', XLSX), ('_ Summary - Ray_ Marcus_ Omar_ Alex.xlsx', XLSX), ('% Summary - 15 east sites.xlsx', None)]

    def _three(self, s, tid):
        from taskuary import outbound
        return [(n, d or b'x' * (outbound.ATTACH_MAX + 1)) for n, d in self.THREE]

    def test_three_named_two_ride_and_the_card_is_told_which_did_not_and_why(self):
        import json
        s = MemoryStore(); tid, _ = task_with(s)
        out = wrapup.agent_reply(s, tid, 'Hi Dana - here are the three summaries, one for each group.', 'assistant', files=self._three(s, tid))
        self.assertEqual(len(out['attached']), 2); self.assertEqual(len(envelope(s, out['review_id'])), 2)
        rv = s.get_review(out['review_id'])
        (no,) = json.loads(rv['Deliver'])['not_attached']
        self.assertEqual(no['name'], '% Summary - 15 east sites.xlsx'); self.assertIn('25MB', no['why'])
        self.assertEqual(json.loads(rv['FilesPromised'])['named'], [n for n, _ in self.THREE])

    def test_saving_the_same_files_again_says_the_refusal_once(self):
        import json
        s = MemoryStore(); tid, _ = task_with(s)
        text = 'Hi Dana - here are the three summaries, one for each group.'
        wrapup.agent_reply(s, tid, text, 'assistant', files=self._three(s, tid))
        rid = wrapup.agent_reply(s, tid, text + ' They tie out.', 'assistant', files=self._three(s, tid))['review_id']
        self.assertEqual(len(json.loads(s.get_review(rid)['Deliver'])['not_attached']), 1)

    def test_the_owner_attaching_it_after_all_takes_the_line_off(self):
        import json
        from taskuary import verdicts
        s = MemoryStore(); tid, _ = task_with(s)
        rid = wrapup.agent_reply(s, tid, 'Hi Dana - here are the three summaries.', 'assistant', files=self._three(s, tid))['review_id']
        verdicts.attach(s, rid, '% Summary - 15 east sites.xlsx', b'a smaller copy')
        env = json.loads(s.get_review(rid)['Deliver'])
        self.assertEqual(env.get('not_attached') or [], []); self.assertEqual(len(env['attachments']), 3)

    # ...AND THE AGENT HEARS IT: told only in a comment it never reads, it went on telling the owner "the three files are attached"
    def test_the_reply_tool_tells_the_agent_which_file_did_not_ride_and_what_to_offer(self):
        s = MemoryStore(); tid, _ = task_with(s)
        out = wrapup.agent_reply(s, tid, 'Hi Dana - here are the three summaries.', 'assistant', files=self._three(s, tid))
        self.assertIn('% Summary - 15 east sites.xlsx', out['tell']); self.assertIn('25MB', out['tell'])
        self.assertIn('link', out['tell']); self.assertIn('smaller copy', out['tell'])

    def test_saving_the_words_again_without_files_still_says_the_file_that_did_not_ride(self):
        s = MemoryStore(); tid, _ = task_with(s)
        wrapup.agent_reply(s, tid, 'Hi Dana - here are the three summaries.', 'assistant', files=self._three(s, tid))
        out = wrapup.agent_reply(s, tid, 'Hi Dana - here are two of the three summaries.', 'assistant')     # propose_reply carries no files
        self.assertEqual([w.split(':')[0] for w in out['not_attached']], ['% Summary - 15 east sites.xlsx'])
        self.assertIn('% Summary - 15 east sites.xlsx', out['tell'])

    def test_all_attached_tells_nothing(self):
        s = MemoryStore(); tid, _ = task_with(s)
        out = wrapup.agent_reply(s, tid, 'Hi Dana - the list is attached.', 'assistant', files=[('review.xlsx', self.XLSX)])
        self.assertNotIn('tell', out); self.assertEqual(out['not_attached'], [])

    def test_the_next_turn_is_told_too(self):
        from taskuary import general
        s = MemoryStore(); tid, _ = task_with(s)
        wrapup.agent_reply(s, tid, 'Hi Dana - here are the three summaries.', 'assistant', files=self._three(s, tid))
        system, _ = general._prompt(s, tid)
        self.assertIn('% Summary - 15 east sites.xlsx', system); self.assertIn(wrapup.REFUSED_HEAD, system)

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
        self.assertTrue(any('secret.key was not attached' in str(c.get('Body')) for c in s.list_comments(tid)))

    def test_every_chat_brain_is_told(self):
        self.assertIn('TASKUARY-ATTACH', selfclose.REPLY_LINE)

    def test_a_chat_turn_puts_the_file_on_the_reply_and_keeps_the_marker_out_of_it(self):
        import json
        from taskuary import general
        f = self.home / 'scratch' / 'review.xlsx'; f.write_bytes(b'xlsx')
        s = MemoryStore(); tid, _ = task_with(s)
        s._exec('UPDATE task SET TrustedThrough=? WHERE TaskId=?', (10 ** 9, tid))      # a thread he trusts: an untrusted sender's task starts no agent (origin.hold)
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


class SaidOnceTests(NoHook):
    """The email walk, 2026-10-29: one reply saved by its marker and by `--reply` in the same turn wrote "agent drafted the reply
    itself" and "assistant drafted the reply itself" one under the other, and the close then said the reply "is being written"."""
    def notes(self, s, tid, words): return [c['Body'] for c in s.list_comments(tid) if words in str(c.get('Body') or '')]

    def test_the_same_letter_saved_twice_is_noted_once(self):
        s = MemoryStore(); tid, _ = task_with(s)
        wrapup.agent_reply(s, tid, OWN, 'agent')
        wrapup.agent_reply(s, tid, OWN + '\n', 'assistant')
        self.assertEqual(len(self.notes(s, tid, 'drafted the reply itself')), 1)
        wrapup.agent_reply(s, tid, OWN.replace('fixed', 'fixed it'), 'assistant')       # a new letter is said
        self.assertEqual(len(self.notes(s, tid, 'drafted the reply itself')), 2)

    def test_closing_a_chat_whose_agent_wrote_the_reply_does_not_say_one_is_being_written(self):
        from taskuary import general
        s = MemoryStore(); tid, _ = task_with(s)
        s.update_task(tid, {'Kind': 'general'}, 't')
        s.add_comment(tid, 'owner', general.USER_TYPE, 'Fix the export and answer Dana')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Fixed. The reply to Dana is saved.')
        wrapup.agent_reply(s, tid, OWN, 'assistant')
        with mock.patch('taskuary.responder.write_draft') as redraft:
            wrapup.wrap(s, tid, close=True, actor='assistant')
        redraft.assert_not_called()
        self.assertEqual(self.notes(s, tid, 'is being written'), [])
        self.assertEqual(len(self.notes(s, tid, 'Closed out the assistant conversation')), 1)


def test_the_agent_is_told_where_the_card_ends_otherwise_than_it_wrote():
    "Asked to sign a reply with the first name only, it wrote that, the card kept the saved signature - and it told the owner 'it is signed Alex'."
    s = MemoryStore(); s.set_setting('owner_name', 'Alex Doyle', 't')
    tid, _ = task_with(s)
    out = wrapup.agent_reply(s, tid, 'Hi Dana, it is fixed.\n\nAlex', 'assistant')
    assert s.get_review(out['review_id'])['DraftText'].endswith('Alex Doyle') and 'Alex Doyle' in out['ends_with']
    assert 'ends_with' not in wrapup.agent_reply(s, tid, 'Hi Dana, it is fixed now.\n\nAlex Doyle', 'assistant')      # ...as it wrote it: nothing to say


def test_a_letter_with_a_blank_left_to_fill_is_no_card():
    "A reply filed for the owner's Send read 'Hi [NAME FROM ACCOUNT PAGE]': refused at the door, with the two ways on - a structure check."
    s = MemoryStore(); s.set_setting('owner_name', 'Alex Doyle', 't')
    tid, _ = task_with(s)
    out = wrapup.agent_reply(s, tid, 'Hi [NAME FROM ACCOUNT PAGE],\n\nYour export is fixed.', 'assistant')
    assert out['ok'] is False and '[NAME FROM ACCOUNT PAGE]' in out['why'] and 'ask the owner' in out['why']
    assert not s.pending_review(tid, 'draft_reply', live_only=False)
    assert wrapup.blanks('Date: [date] and {{venue}}') == ['[date]', '{{venue}}']
    # ...never what a letter may carry in brackets: a link's text, a numbered note, a ticked box, a ticket's tag
    for fine in ('See [the notes](https://northwind.example/n).', 'As agreed [1], it is done.', '- [x] exported', 'Re: [TQ-0012] export'):
        assert wrapup.blanks(fine) == [], fine
    assert wrapup.agent_reply(s, tid, 'Hi Dana, the August export is fixed [1].', 'assistant')['ok']


if __name__ == '__main__':
    unittest.main()
