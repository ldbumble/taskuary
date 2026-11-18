"""Every line the owner sends is kept the moment it is sent (the owner, 2026-11-07: "a word typed is a word kept").

The audit's stress run: a first turn ran fourteen minutes, and the five lines typed in its first seconds lived only in the server's memory and
the page's own state - a page opened mid-turn showed none of them, a restart would have lost them, and when they finally drew they were stamped
with the time the next turn took them. And a line held behind a turn that failed came back "reload the page and ask again", red in the box,
where the first line's road started again quietly. One road now: kept at once with its typed time, shown on every screen as waiting for the
agent, taken together when the turn ends, and started again on a fresh session where the old one ended under it.
"""
import json, threading, time, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, server
from taskuary.store import MemoryStore



class Brain:
    "The model: answers after `delay`, fails the turns named in `fail`, keeps what each turn was handed."
    def __init__(self, delay=0.0, fail=()): self.delay, self.fail, self.calls = delay, set(fail), []
    def __call__(self, system, user, **k):
        self.calls.append(user); n = len(self.calls); time.sleep(self.delay)
        if n in self.fail: raise RuntimeError('the model gave up')
        return f'Answer {n}.'


class OwnerLineIsKept(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Compare expense tools for Northwind', 'Kind': 'general'}, 'o')
        self.brain = Brain(delay=1.0)
        for p in [mock.patch.object(general.llm_mod, 'build_llm', side_effect=lambda *a, **k: self.brain),
                  mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli', 'label': 'Claude Code', 'model': ''}]),
                  mock.patch('taskuary.agents.ready_brains', return_value=['claude']),
                  mock.patch('taskuary.hooks.judge_ended', lambda *a, **k: None),
                  mock.patch.object(server, 'store', self.s)]:
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.end)

    def end(self):
        if (g := general.session_for(self.tid)): g.close(learn=False, report=False)
        general.drop_session(self.tid); general.IDLED.pop(self.tid, None); general.answered(self.tid, every=True)

    def said(self): return [(c['ActorType'], c['Body']) for c in general.chat_rows(self.s, self.tid)]

    def test_a_line_typed_mid_turn_is_kept_at_once_with_its_time_and_taken_with_the_next_turn(self):
        # waits for the state, never a fixed sleep: CI's macOS box had not started the first turn 0.3s in, so nothing was held (2026-11-08)
        def until(ok, secs=10):
            end = time.time() + secs
            while not ok() and time.time() < end: time.sleep(0.02)
        first = threading.Thread(target=lambda: general.take_line(self.s, self.tid, 'Compare three tools.')); first.start()
        until(lambda: getattr(general.session_for(self.tid), 'busy', False))
        held = [threading.Thread(target=lambda w=w: general.take_line(self.s, self.tid, w)) for w in ('Make it cheapest first.', 'And add Trainly.')]
        for i, t in enumerate(held): t.start(); until(lambda n=i + 1: len(general.waiting_lines(self.s, self.tid)) >= n)
        kept = general.waiting_lines(self.s, self.tid)
        self.assertEqual([w['text'] for w in kept], ['Make it cheapest first.', 'And add Trainly.'])      # kept the moment they were sent...
        self.assertEqual([w['text'] for w in server._assistant_payload(self.tid)['waiting']], [w['text'] for w in kept])   # ...on every screen
        self.assertNotIn('And add Trainly.', [b for _, b in self.said()])                                # ...waiting, not yet a turn of its own
        typed = {w['text']: w['at'] for w in kept}
        for t in [first, *held]: t.join(15)
        self.assertEqual(self.said(), [(general.USER_TYPE, 'Compare three tools.'), (general.ASSISTANT_TYPE, 'Answer 1.'),
                                       (general.USER_TYPE, 'Make it cheapest first.'), (general.USER_TYPE, 'And add Trainly.'),
                                       (general.ASSISTANT_TYPE, 'Answer 2.')])                         # one turn took both, after the first
        rows = {c['Body']: c['CreatedAt'] for c in self.s.list_comments(self.tid)}
        self.assertEqual({w: rows[w] for w in typed}, typed)                                          # ...each at the time it was typed
        self.assertEqual(general.waiting_lines(self.s, self.tid), [])

    def test_lines_kept_when_the_server_restarted_stay_by_the_box_and_go_in_as_one_turn_when_the_agent_is_ready(self):
        """The owner, 2026-11-11: "yes pending should go in when agent ready" - they came back as text in his box, his to send again."""
        from taskuary import conversation, waitroom
        for w in ('And copy Erin Blake.', 'Before Friday.'): general.wait_line(self.s, self.tid, w)    # typed mid-turn; then the process went away
        self.assertFalse(hasattr(general, 'to_box') or hasattr(server, 'lines_to_box'))
        self.assertNotIn('box', server._assistant_payload(self.tid))
        # ...and the turn the restart cut says so without asking him to type: his lines carry on by themselves
        with mock.patch('taskuary.sessionrecord.cut_turns', return_value=[(self.tid, [])]), mock.patch('taskuary.sessionrecord.keep_turn'):
            general.keep_cut_turns(self.s)
        self.assertEqual(self.said()[-1][1], general.CUT_ON); self.assertNotIn('type to', general.CUT_ON)
        self.assertEqual([x['text'] for x in conversation.items(self.s, self.tid)['pending']], ['And copy Erin Blake.', 'Before Friday.'])   # ...by the box
        self.brain.delay = 0
        waitroom.tick(self.s)                                                              # the clock: nobody is taking them, so one turn begins
        self.assertFalse(general.run_kept(self.s, self.tid))                               # ...one, not one a tick
        end = time.time() + 15
        while (general.ASSISTANT_TYPE, 'Answer 1.') not in self.said() and time.time() < end: time.sleep(0.05)
        self.assertEqual(self.said()[-3:], [(general.USER_TYPE, 'And copy Erin Blake.'), (general.USER_TYPE, 'Before Friday.'), (general.ASSISTANT_TYPE, 'Answer 1.')])
        self.assertEqual(len(self.brain.calls), 1)                                         # both in one turn, each said once
        self.assertEqual(general.waiting_lines(self.s, self.tid), [])
        time.sleep(0.2); waitroom.tick(self.s); time.sleep(0.2)
        self.assertEqual(len(self.brain.calls), 1)                                         # ...and nothing left to start another

    def test_a_held_line_behind_a_turn_that_failed_starts_the_agent_again_quietly(self):
        "Bug 10: the held road had no restart - the line came back 'reload the page and ask again'."
        self.brain.fail = {1}
        c = TestClient(server.app)
        first = threading.Thread(target=lambda: c.post(f'/api/tasks/{self.tid}/assistant/messages', json={'text': 'Compare three tools.'})); first.start()
        time.sleep(0.3)
        r = c.post(f'/api/tasks/{self.tid}/assistant/messages', json={'text': 'Cheapest first, please.'})
        first.join(15)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get('kept'))                                             # a line sent while a turn works is kept and answered at once...
        end = time.time() + 15
        while (general.ASSISTANT_TYPE, 'Answer 2.') not in self.said() and time.time() < end: time.sleep(0.05)
        self.assertIn((general.ASSISTANT_TYPE, 'Answer 2.'), self.said())                 # ...and answered on a fresh session
        self.assertEqual([b for t, b in self.said() if t == general.USER_TYPE].count('Cheapest first, please.'), 1)    # ...the line said once
        self.assertNotIn('reload the page', general.ENDED)

    def test_a_cancelled_line_is_taken_back(self):
        ses = general.start_session(self.s, self.tid)
        threading.Thread(target=lambda: ses.send_prompt('Compare three tools.'), daemon=True).start(); time.sleep(0.2)
        cancel = threading.Event(); threading.Timer(0.2, cancel.set).start()
        with self.assertRaises(RuntimeError): ses.send_prompt('Never mind.', cancel=cancel)
        self.assertEqual(general.waiting_lines(self.s, self.tid), [])

    def test_a_line_keeps_the_name_its_page_gave_it_while_it_waits_and_as_the_turn_it_becomes(self):
        """THE SPINE AUDIT, 2026-11-09: the page that sent a line draws it at once and has to know when the conversation has it. It knew by
        the line's words and by counting the owner's lines, so a line from another window retired one the server did not have yet, and "ok"
        sent twice stood once. The page names its line; the name is kept on the waiting row and on the turn it becomes, and comes back on both."""
        def until(ok, secs=10):
            end = time.time() + secs
            while not ok() and time.time() < end: time.sleep(0.02)
        say = lambda w, name: threading.Thread(target=lambda: general.take_line(self.s, self.tid, w, line_id=name))
        first = say('Compare three tools.', 'held-1'); first.start()
        until(lambda: getattr(general.session_for(self.tid), 'busy', False))
        held = [say('ok', 'held-2'), say('ok', None), say('ok', 'held-3')]
        for i, t in enumerate(held): t.start(); until(lambda n=i + 1: len(general.waiting_lines(self.s, self.tid)) >= n)
        # ...and a line the page gave no name gets one here (general.new_line_id): the ledger says by it that the agent heard it
        waits = [(w['text'], w.get('line')) for w in server._assistant_payload(self.tid)['waiting']]
        self.assertEqual([(w, n) for w, n in waits if n in ('held-2', 'held-3')], [('ok', 'held-2'), ('ok', 'held-3')])
        made = waits[1][1]; self.assertTrue(made and made.startswith('s'))
        for t in [first, *held]: t.join(15)
        mine = [(m['content'][0]['text'], m.get('line')) for m in server._assistant_payload(self.tid)['messages'] if m['role'] == 'user']
        self.assertEqual(mine, [('Compare three tools.', 'held-1'), ('ok', 'held-2'), ('ok', made), ('ok', 'held-3')])

    def test_a_line_typed_while_a_chat_poll_holds_its_lock_is_kept_and_answered_never_refused(self):
        """The owner's live task, 2026-11-12: his agent at rest with no process left, a chat poll holding its lock - the start waited 45 s on
        it, was refused, and his line came back red with that glued to it. And 2026-11-16: the turn then went on under "The newest mail could
        not be read first" - about mail, on a line he typed. His line is kept and heard at once, nothing is fetched or said first."""
        from taskuary import conversation
        self.brain.delay = 0
        refused = mock.patch.object(server, '_refresh_chat_context', side_effect=RuntimeError('messages are still syncing; I did not use stale chat context - try again in a moment'))
        with refused as read:
            self.assertIsNone(general.session_for(self.tid))
            r = TestClient(server.app).post(f'/api/tasks/{self.tid}/assistant/messages', json={'text': 'Compare three tools.', 'line_id': 'l-sync'})
        self.assertEqual(r.status_code, 200, r.text)
        got = conversation.items(self.s, self.tid)['items']
        self.assertEqual([x['id'] for x in got if x['kind'] == 'line'], ['l-sync'])
        self.assertFalse(read.called)
        self.assertEqual([x['text'] for x in got if x['kind'] == 'note'], [])
        self.assertEqual([x['text'] for x in got if x['kind'] == 'turn'], ['Answer 1.'])
        self.assertNotIn('syncing', json.dumps(got))

    def test_the_chats_door_takes_the_name_and_a_long_one_is_cut(self):
        self.brain.delay = 0
        out = TestClient(server.app).post(f'/api/tasks/{self.tid}/assistant/messages', json={'text': 'Compare three tools.', 'line_id': 'h' * 200}).json()
        self.assertEqual([m.get('line') for m in out['messages'] if m['role'] == 'user'], ['h' * 80])


if __name__ == '__main__':
    unittest.main()


# EVERY FILE HE ATTACHES REACHES THE AGENT, AND STAYS ON HIS LINE (the owner, 2026-11-17: "if you attach item on prompt it's not being sent to
# agnet. Make sure all attachmetns work"): on a coding task the picture he attached stayed in Taskuary's own attachments folder, and the
# agent's Read of it was refused as "Taskuary's own data"; and once a turn took his line its files were dropped, so his bubble drew the words
# alone. Every door copies what he attached into the task's own folder first, and his line keeps its files once heard
class AttachedFilesReachTheAgent(unittest.TestCase):
    def setUp(self):
        from taskuary import config
        self.s = MemoryStore()
        self.d = config.home() / 'attachments' / 'prompt' / '209901'; self.d.mkdir(parents=True, exist_ok=True)
        self.pic = self.d / '20991231-235959-abc123-the person.png'; self.pic.write_bytes(b'\x89PNG fake')
        self.addCleanup(self.pic.unlink, missing_ok=True)
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)

    def inside(self, tid, path):
        from taskuary import outputs
        return str(path).startswith(str(outputs.folder(tid)))

    def test_a_coding_tasks_line_hands_over_a_file_in_its_own_folder(self):
        from taskuary import waitroom
        tid = self.s.create_task({'Title': 'Check the Relias account', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        with mock.patch.object(waitroom, 'deliver', return_value={'delivered': 0, 'state': 'working'}):
            general.take_line(self.s, tid, 'it was this person', [str(self.pic)], 'owner')
        files = general.waiting_lines(self.s, tid)[0]['files']
        self.assertEqual(len(files), 1); self.assertTrue(self.inside(tid, files[0]), files)

    def test_a_heard_line_keeps_its_files_in_the_chat(self):
        from taskuary import conversation
        tid = self.s.create_task({'Title': 'Check the Relias account', 'Kind': 'general', 'Status': 'in_progress'}, 'o')
        general.wait_line(self.s, tid, 'it was this person', [str(self.pic)])
        general.take_kept(self.s, tid)
        line = next(x for x in conversation.items(self.s, tid)['items'] if x['kind'] == 'line')
        self.assertEqual((line['text'], line['files']), ('it was this person', [str(self.pic)]))

    def test_a_task_new_makes_with_a_file_names_it_in_its_own_folder(self):
        c = TestClient(server.app)
        tid = c.post('/api/tasks', json={'Title': 'Who is this', 'Summary': f'Who is this?\n\nATTACHED IMAGES (read these files)\n{self.pic}'}).json()['taskId']
        summary = self.s.get_task(tid)['Summary']
        self.assertNotIn(str(self.pic), summary)
        from taskuary import outputs
        self.assertIn(str(outputs.folder(tid)), summary)


# ...AND SEND TO AGENT ON A REPORT, A DASHBOARD OR AN FYI IS THE SAME (the stress round, 2026-11-18): his words and the picture he put on the
# box ride the dispatch's instruction, which never went through the task's folder - the agent was told the upload's path under Taskuary's own
# attachments, and on a held sender's task the line waited with the files block spelled out as words, no pill
class SendToAgentCarriesItsFiles(AttachedFilesReachTheAgent):
    class Session:
        quick, provider, model = False, 'Claude Code', ''
        def __init__(self): self.said = []
        def send_prompt(self, prompt, brief=False): self.said.append(prompt)
        def info(self, tail=0): return {}

    def send(self, mid, words):
        from fastapi import BackgroundTasks
        bg, ses = BackgroundTasks(), self.Session()
        with mock.patch.object(general, 'start_session', return_value=ses), mock.patch('taskuary.ingest._reads_quick', return_value=False):
            out = server.dispatch_message(mid, server.DispatchBody(kind='general', instruction=f'{words}\n\nATTACHED IMAGES (read these files)\n{self.pic}'), bg)
            for t in bg.tasks: t.func(*t.args, **t.kwargs)
        return out, ses.said

    def test_a_report_sent_on_with_a_picture_names_it_in_the_tasks_folder(self):
        mid = self.s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'SourceName': 'Weekly AR aging', 'Subject': 'Weekly AR aging', 'BodyText': '| Payworth | 95 |'})
        with mock.patch('taskuary.origin.hold', return_value=None):
            out, said = self.send(mid, 'Is this invoice on it?')
        self.assertEqual(len(said), 1, out)
        self.assertNotIn(str(self.pic), said[0]); self.assertIn(str(outputs_folder(out['taskId'])), said[0])

    def test_a_held_senders_fyi_keeps_his_line_with_its_files_as_files(self):
        mid = self.s.add_message({'ExternalId': 'f1', 'Channel': 'email', 'FromEmail': 'billing@vendor.example', 'FromName': 'Trainly',
                                  'Subject': 'Renewal notice', 'BodyText': 'Your plan renews on Dec 1.', 'Status': 'filed'})
        with mock.patch('taskuary.origin.hold', return_value={'line': 'You have not trusted Trainly yet.'}):
            out, said = self.send(mid, 'Is this invoice theirs?')
        self.assertEqual((out['dispatch'], said), ('held', []))
        line = general.waiting_lines(self.s, out['taskId'])[0]
        self.assertEqual(line['text'], 'Is this invoice theirs?')
        self.assertEqual(len(line['files']), 1); self.assertTrue(self.inside(out['taskId'], line['files'][0]), line['files'])


def outputs_folder(tid):
    from taskuary import outputs
    return outputs.folder(tid)
